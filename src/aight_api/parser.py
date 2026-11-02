"""The worker invokes this in a separate, network-denied Linux process."""
import ctypes
import errno
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect


def canonical(text: str) -> str:
    return unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))


def paragraphs(text: str) -> list[dict]:
    return [{"number": index + 1, "start": match.start(), "end": match.end()}
            for index, match in enumerate(re.finditer(r"[^\n]+", text)) if match.group().strip()]


def text_page(text: str) -> dict:
    text = canonical(text)
    return {"page_number": 1, "printed_page_label": None, "status": "readable", "text": text,
            "paragraphs": paragraphs(text), "layout_spans": [], "warnings": []}


def coverage(pages: list[dict]) -> dict:
    readable = [page["page_number"] for page in pages if page["status"] != "unreadable"]
    partial = [page["page_number"] for page in pages if page["status"] == "partial"]
    unreadable = [page["page_number"] for page in pages if page["status"] == "unreadable"]
    reasons = (["partial_pages"] if partial else []) + (["unreadable_pages"] if unreadable else [])
    return {"status": "partial" if reasons else "complete", "readable_pages": readable,
            "partial_pages": partial, "unreadable_pages": unreadable, "analyzed_pages": [], "reasons": reasons}


def parse_document(path: Path, max_pages: int = 50, max_text: int = 300_000) -> list[dict]:
    pages, total = [], 0
    with pdfplumber.open(path, password=None) as pdf:
        if len(pdf.pages) > max_pages:
            raise ValueError("page_limit_exceeded")
        for number, page in enumerate(pdf.pages, 1):
            text = canonical(page.extract_text(layout=False) or "")
            total += len(text)
            if total > max_text:
                raise ValueError("extracted_text_limit_exceeded")
            warnings, spans, cursor = [], [], 0
            for word in page.extract_words():
                value = canonical(word["text"])
                start = text.find(value, cursor)
                if start < 0:
                    continue
                end = start + len(value)
                box = [max(0, word["x0"] / page.width), max(0, word["top"] / page.height),
                       min(1, (word["x1"] - word["x0"]) / page.width),
                       min(1, (word["bottom"] - word["top"]) / page.height)]
                spans.append({"start": start, "end": end, "boxes": [box]})
                cursor = end
            suspect_image = False
            for image in page.images:
                area = max(0, image["x1"] - image["x0"]) * max(0, image["bottom"] - image["top"])
                if area < page.width * page.height * 0.20:
                    continue
                covered = [char for char in page.chars
                           if image["x0"] <= (char["x0"] + char["x1"]) / 2 <= image["x1"]
                           and image["top"] <= (char["top"] + char["bottom"]) / 2 <= image["bottom"]]
                if len(covered) < 40:
                    suspect_image = True
            suspect_text = "\ufffd" in text or bool(re.search(r"[\x00-\x08\x0e-\x1f]", text))
            tables = bool(page.find_tables())
            status = "unreadable" if not text.strip() else "partial" if suspect_image or suspect_text or tables else "readable"
            if status != "readable":
                code = "unreadable_page" if status == "unreadable" else "unsupported_layout" if tables else "partial_page"
                message = ("This page has no usable text. OCR is not available." if status == "unreadable" else
                           "Some page content or its layout could not be read reliably. Requirements may be missing.")
                warnings.append({"code": code, "message": message, "page_numbers": [number]})
            pages.append({"page_number": number, "printed_page_label": None, "status": status,
                          "text": text if status != "unreadable" else "",
                          "paragraphs": paragraphs(text) if status != "unreadable" else [],
                          "layout_spans": spans if status != "unreadable" else [], "warnings": warnings})
    return pages


def isolate() -> None:
    if sys.platform != "linux":
        raise ValueError("parser_isolation_unavailable")
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (25, 25))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024, 8 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0:
        raise ValueError("parser_isolation_unavailable")
    seccomp = ctypes.CDLL("libseccomp.so.2")
    seccomp.seccomp_init.argtypes = [ctypes.c_uint32]
    seccomp.seccomp_init.restype = ctypes.c_void_p
    seccomp.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    seccomp.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    seccomp.seccomp_load.argtypes = [ctypes.c_void_p]
    seccomp.seccomp_release.argtypes = [ctypes.c_void_p]
    # Landlock ABI 3+ denies filesystem writes/truncation and limits reads to
    # the input file and installed runtime, excluding other sessions and /proc.
    libc.syscall.restype = ctypes.c_long
    create = seccomp.seccomp_syscall_resolve_name(b"landlock_create_ruleset")
    add = seccomp.seccomp_syscall_resolve_name(b"landlock_add_rule")
    restrict = seccomp.seccomp_syscall_resolve_name(b"landlock_restrict_self")
    if min(create, add, restrict) < 0 or libc.syscall(create, 0, 0, 1) < 3:
        raise ValueError("parser_isolation_unavailable")
    class Ruleset(ctypes.Structure):
        _fields_ = [("handled_access_fs", ctypes.c_uint64)]
    class PathRule(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]
    ruleset = Ruleset((1 << 15) - 1)
    descriptor = libc.syscall(create, ctypes.byref(ruleset), ctypes.sizeof(ruleset), 0)
    if descriptor < 0:
        raise ValueError("parser_isolation_unavailable")
    try:
        paths = {Path(sys.argv[1]).resolve(), Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve(), Path("/usr/lib"), Path("/lib")}
        for path in paths:
            if not path.exists():
                continue
            fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                rule = PathRule((1 << 2) | ((1 << 3) if path.is_dir() else 0), fd)
                if libc.syscall(add, descriptor, 1, ctypes.byref(rule), 0) != 0:
                    raise ValueError("parser_isolation_unavailable")
            finally:
                os.close(fd)
        if libc.syscall(restrict, descriptor, 0) != 0:
            raise ValueError("parser_isolation_unavailable")
    finally:
        os.close(descriptor)
    context = seccomp.seccomp_init(0x7FFF0000)
    if not context:
        raise ValueError("parser_isolation_unavailable")
    try:
        for name in (b"socket", b"socketpair", b"connect", b"socketcall", b"execve", b"execveat", b"fork", b"vfork", b"clone", b"clone3"):
            syscall = seccomp.seccomp_syscall_resolve_name(name)
            if syscall >= 0 and seccomp.seccomp_rule_add(context, 0x00050000 | errno.EPERM, syscall, 0) != 0:
                raise ValueError("parser_isolation_unavailable")
        if seccomp.seccomp_load(context) != 0:
            raise ValueError("parser_isolation_unavailable")
    finally:
        seccomp.seccomp_release(context)


if __name__ == "__main__":
    try:
        isolate()
        print(json.dumps({"pages": parse_document(Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]))}, ensure_ascii=False))
    except PDFPasswordIncorrect:
        print(json.dumps({"error": "encrypted_pdf"}))
    except ValueError as problem:
        code = str(problem)
        print(json.dumps({"error": code if code in {"page_limit_exceeded", "extracted_text_limit_exceeded", "parser_isolation_unavailable"} else "malformed_pdf"}))
    except Exception:
        print(json.dumps({"error": "malformed_pdf"}))
