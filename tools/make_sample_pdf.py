"""Generate a small multi-page sample PDF with an outline, for development and tests.

Uses Ghostscript (pdfmark for the outline). Usage:
    python tools/make_sample_pdf.py out.pdf [pages] [roman] [--no-outline]

[roman] labels the first pages i, ii, ... and the rest 1, 2, ...
--no-outline leaves the outline out, so Dogear makes one from the headings.
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


def _rule(x1: float, x2: float, y: float) -> str:
    return f"newpath {x1} {y} moveto {x2} {y} lineto 0.8 setlinewidth stroke"


# The last page ends with review questions that have answer lines: a blank
# after a label, three ruled lines under a question, and underscores.
WORKSHEET = [
    "/Helvetica-Bold findfont 14 scalefont setfont 72 370 moveto (Review questions) show",
    "/Helvetica findfont 12 scalefont setfont",
    "72 330 moveto (1. Name of the process:) show",
    _rule(210, 520, 328),
    "72 290 moveto (2. Explain the Calvin cycle in your own words.) show",
    _rule(90, 520, 260),
    _rule(90, 520, 236),
    _rule(90, 520, 212),
    "72 170 moveto (3. Plants absorb ________________ and ________________ light.) show",
]


def build_ps(pages: int, roman: int = 0, outline: bool = True) -> str:
    out = ["%!PS-Adobe-3.0", "/Helvetica findfont 12 scalefont setfont"]
    chapters = []
    for p in range(1, pages + 1):
        chapters.append(p)
        out.append(f"/Helvetica-Bold findfont 20 scalefont setfont 72 720 moveto {_ps_string(f'Chapter {p}: Topic {p}')} show")
        out.append("/Helvetica findfont 12 scalefont setfont")
        y = 690
        last = p == pages and pages > 1
        for line in range(14 if last else 30):
            out.append(f"72 {y} moveto {_ps_string(f'{p}.{line + 1} ' + LOREM[(line * 7) % 60:(line * 7) % 60 + 70])} show")
            y -= 20
        if last:
            out += WORKSHEET
        out.append(f"300 40 moveto {_ps_string(str(p))} show")
        if outline:
            out.append(f"[ /Title {_ps_string(f'Chapter {p}: Topic {p}')} /Page {p} /OUT pdfmark")
        out.append("showpage")
    out.append("[ /Title (Dogear sample) /DOCINFO pdfmark")
    if roman:
        # Page labels like a book's: i, ii, ... then 1, 2, ...
        out.append(f"[ {{Catalog}} << /PageLabels << /Nums [ 0 << /S /r >> {roman} << /S /D >> ] >> >> /PUT pdfmark")
    return "\n".join(out) + "\n"


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--no-outline"]
    target = Path(args[0] if args else "sample.pdf")
    pages = int(args[1]) if len(args) > 1 else 6
    roman = int(args[2]) if len(args) > 2 else 0
    with tempfile.TemporaryDirectory() as tmp:
        ps = Path(tmp) / "sample.ps"
        ps.write_text(build_ps(pages, roman, "--no-outline" not in sys.argv))
        subprocess.run(
            # Letter, always: Ghostscript's default paper follows the
            # system (A4 in many places), and the tests click by position.
            ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=pdfwrite",
             "-sPAPERSIZE=letter", "-dFIXEDMEDIA", f"-sOutputFile={target}", str(ps)],
            check=True,
        )
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
