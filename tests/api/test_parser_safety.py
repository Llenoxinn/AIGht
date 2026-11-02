import json
import subprocess
import sys
from pathlib import Path

import pytest

from aight_api.parser import coverage, parse_document


def heading_over_image_pdf():
    stream = b"BT /F1 12 Tf 50 750 Td (Scholarship guidelines) Tj ET q 500 0 0 600 50 60 cm /Im1 Do Q"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> /XObject << /Im1 6 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
        b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Length 3 >>\nstream\n\xff\xff\xff\nendstream",
    ]
    data, offsets = bytearray(b"%PDF-1.4\n"), [0]
    for index, value in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{index} 0 obj\n".encode() + value + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]: data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(data)


def test_searchable_heading_does_not_hide_scanned_body(tmp_path):
    path = tmp_path / "mixed.pdf"
    path.write_bytes(heading_over_image_pdf())
    pages = parse_document(path)
    assert pages[0]["text"] == "Scholarship guidelines"
    assert pages[0]["status"] == "partial"
    assert coverage(pages)["status"] == "partial"
    assert coverage(pages)["partial_pages"] == [1]


def test_pdf_limits_and_malformed_input(tmp_path):
    path = tmp_path / "mixed.pdf"
    path.write_bytes(heading_over_image_pdf())
    with pytest.raises(ValueError, match="page_limit_exceeded"):
        parse_document(path, max_pages=0)
    with pytest.raises(ValueError, match="extracted_text_limit_exceeded"):
        parse_document(path, max_text=1)
    path.write_bytes(b"%PDF-1.4\ninvalid synthetic fixture")
    with pytest.raises(Exception):
        parse_document(path)


@pytest.mark.skipif(sys.platform != "linux", reason="PDF isolation requires Linux Landlock ABI 3 and libseccomp")
def test_linux_parser_denies_other_files_writes_network_and_execution(tmp_path):
    source, foreign = tmp_path / "source.txt", tmp_path / "foreign.txt"
    source.write_text("Synthetic allowed source")
    foreign.write_text("Synthetic other session")
    parser = Path(__file__).parents[2] / "src/aight_api/parser.py"
    code = """
import json, runpy, socket, subprocess, sys
from pathlib import Path
parser, source, foreign = sys.argv[1:]
namespace = runpy.run_path(parser)
sys.argv = [parser, source]
try:
    namespace['isolate']()
except (ValueError, OSError):
    print(json.dumps({'unavailable': True}))
    raise SystemExit(0)
assert Path(source).read_text() == 'Synthetic allowed source'
checks = [lambda: Path(foreign).read_text(), lambda: Path(source).write_text('forbidden'),
          lambda: socket.socket(), lambda: subprocess.run(['/bin/true'])]
for operation in checks:
    try:
        operation()
    except PermissionError:
        continue
    raise AssertionError('Parser sandbox allowed a forbidden operation')
print(json.dumps({'denied': len(checks)}))
"""
    process = subprocess.run([sys.executable, "-I", "-c", code, str(parser.resolve()), str(source), str(foreign)],
                             capture_output=True, text=True, timeout=10)
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    if result.get("unavailable"):
        pytest.fail("The Linux test host cannot enforce the required parser sandbox; PDF uploads must remain disabled.")
    assert result["denied"] == 4
