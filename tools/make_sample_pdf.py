"""Generate a small multi-page sample PDF with an outline, for development and tests.

Uses Ghostscript (pdfmark for the outline). Usage:
    python tools/make_sample_pdf.py out.pdf [pages]
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

LOREM = (
    "Photosynthesis converts light energy into chemical energy. "
    "The light reactions happen in the thylakoid membranes. "
    "The Calvin cycle fixes carbon dioxide into sugars. "
    "Chlorophyll absorbs mostly blue and red light. "
)


def _ps_string(text: str) -> str:
    return "(" + text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


def build_ps(pages: int) -> str:
    out = ["%!PS-Adobe-3.0", "/Helvetica findfont 12 scalefont setfont"]
    chapters = []
    for p in range(1, pages + 1):
        chapters.append(p)
        out.append(f"/Helvetica-Bold findfont 20 scalefont setfont 72 720 moveto {_ps_string(f'Chapter {p}: Topic {p}')} show")
        out.append("/Helvetica findfont 12 scalefont setfont")
        y = 690
        for line in range(30):
            out.append(f"72 {y} moveto {_ps_string(f'{p}.{line + 1} ' + LOREM[(line * 7) % 60:(line * 7) % 60 + 70])} show")
            y -= 20
        out.append(f"300 40 moveto {_ps_string(str(p))} show")
        out.append(f"[ /Title {_ps_string(f'Chapter {p}: Topic {p}')} /Page {p} /OUT pdfmark")
        out.append("showpage")
    out.append("[ /Title (Dogear sample) /DOCINFO pdfmark")
    return "\n".join(out) + "\n"


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "sample.pdf")
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    with tempfile.TemporaryDirectory() as tmp:
        ps = Path(tmp) / "sample.ps"
        ps.write_text(build_ps(pages))
        subprocess.run(
            ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=pdfwrite",
             f"-sOutputFile={target}", str(ps)],
            check=True,
        )
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
