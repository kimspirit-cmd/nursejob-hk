"""Shared helpers for the nurse-job scrapers."""
import re

# Page-chrome markers that leak into scraped detail text (e.g. JUMP appends
# its "Similar Jobs" footer after the Enquiries block). Cut text at the first
# occurrence of any marker.
_FOOTER_MARKERS = ("Similar Jobs", "相關職位", "You may also like")


def clean_text(t: str) -> str:
    """Normalize scraped free text for display in a <pre> block.

    - normalizes CRLF/CR to LF
    - cuts page-chrome footers (e.g. 'Similar Jobs')
    - strips each line and collapses runs of blank lines to at most one,
      so stray HTML whitespace can never render as a giant blank area
    """
    t = (t or "").replace("\r", "\n")
    for marker in _FOOTER_MARKERS:
        idx = t.find(marker)
        if idx > 0:
            t = t[:idx]
    out_lines: list[str] = []
    blank_run = 0
    for line in t.split("\n"):
        line = line.strip()
        if line:
            out_lines.append(line)
            blank_run = 0
        else:
            blank_run += 1
            if blank_run == 1:
                out_lines.append("")
    return "\n".join(out_lines).strip("\n")
