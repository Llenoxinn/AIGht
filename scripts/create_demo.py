"""Generate a small synthetic source fixture and its actual PDF using only stdlib."""
import json
import textwrap
from pathlib import Path

PAGES = [
    "AIGht scholarship example\nSynthetic demonstration document\nThese guidelines are fictional and do not describe an actual scholarship. Use this sample to explore explanations, source citations and a page stack.",
    "Academic eligibility\nApplicants must maintain a general weighted average not exceeding 2.00.\nUnder this example's grading convention, lower numeric grades are better. Meeting the GWA condition alone does not establish overall eligibility.",
    "Documentary requirements\nApplicants must submit a certified transcript of records, proof of enrollment, a completed application form, and a copy of their school ID.",
    "Submission deadline\nApplicants shall submit all documentary requirements within fifteen calendar days from receipt of notice.\nCalendar days include weekends and holidays unless another provision changes the counting rule. Confirm the date on which you received the notice.",
    "Details to confirm\nThese sample guidelines do not state an application fee. Missing information does not mean an application is free. If a rule is unclear, ask the issuing office for confirmation."
]


def pdf_bytes(pages):
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    kids = []
    for index, text in enumerate(pages):
        page_id = 4 + index * 2
        kids.append(f"{page_id} 0 R")
        lines = [line for paragraph in text.split("\n") for line in textwrap.wrap(paragraph, 82)]
        commands = ["BT /F1 11 Tf 17 TL 54 752 Td"]
        for line in lines:
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            commands.append(f"({escaped}) Tj T*")
        commands.append("ET")
        stream = "\n".join(commands).encode("ascii")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {page_id+1} 0 R >>".encode())
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    objects[1] = f"<< /Type /Pages /Count {len(kids)} /Kids [{' '.join(kids)}] >>".encode()
    data, offsets = bytearray(b"%PDF-1.4\n%Synthetic AIGht fixture\n"), [0]
    for index, value in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{index} 0 obj\n".encode() + value + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]: data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(data)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1] / "src/AIGht.Web/wwwroot/examples"
    root.mkdir(parents=True, exist_ok=True)
    (root / "scholarship-guidelines.pdf").write_bytes(pdf_bytes(PAGES))
    (root / "scholarship.json").write_text(json.dumps({"pages": [{"page_number": index, "status": "readable", "text": text, "warnings": []} for index, text in enumerate(PAGES, 1)]}, indent=2), encoding="utf-8")
    print("Generated five synthetic source pages and their PDF.")
