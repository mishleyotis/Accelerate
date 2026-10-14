"""The page index says where a section renders — and that includes "nowhere".

D-35 / RC-01 (SWBC gold audit, 2026-10-04): `03-pages/2-overview.md` and the
O1b / O10 / O11 surface headers said `ceilings` and `evidence_coverage`
"render on D1". Both are NEVER_SERVED: `redaction.py` removes them for every
audience, so a producer told they render on the Overview was writing for a
reader who never sees them — while the sections customers really do not see
(alerts, cohort patterns, starters, the whole context page) carried no mark
at all. The serve boundary lived in `redaction.py` and nowhere a producer
reads.

This keeps the page index in step with the redaction sets, by name.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGES_DIR = (ROOT / "plugins" / "dma-insights" / "skills" /
             "dma-surface-production" / "03-pages")
INDEX = {"heatmap": "1-heatmap.md", "overview": "2-overview.md",
         "insights": "3-insights.md", "platform": "4-platform.md",
         "context": "5-context.md", "techstack": "6-techstack.md"}

sys.path.insert(0, str(ROOT / "apps" / "api"))


def _redaction():
    from dma_api import redaction
    return redaction


def _row(page: str, section: str) -> str:
    text = (PAGES_DIR / INDEX[page]).read_text(encoding="utf-8")
    m = re.search(rf"^\| `{re.escape(section)}` \|.*$", text, re.M)
    assert m, f"{INDEX[page]} has no row for `{section}`"
    return m.group(0)


def test_never_served_sections_are_marked_in_the_page_index():
    R = _redaction()
    for page, section in sorted(R.NEVER_SERVED):
        row = _row(page, section)
        assert "NEVER_SERVED" in row and "D1" not in row.split("|")[-2], (
            f"{INDEX[page]}: `{section}` is NEVER_SERVED but its row reads "
            f"{row!r}")


def test_never_served_surface_headers_do_not_claim_a_dashboard():
    for surface in ("O1b", "O10", "O11"):
        text = (PAGES_DIR / "overview" / f"{surface}.md").read_text(encoding="utf-8")
        head = next(line for line in text.splitlines()
                    if line.startswith("- **Section**"))
        assert "NEVER_SERVED" in head and "renders on** D1" not in head, (
            surface, head)


def test_customer_withheld_sections_are_marked_in_the_page_index():
    R = _redaction()
    for page, section in sorted(R.CUSTOMER_WITHHELD - R.NEVER_SERVED):
        row = _row(page, section)
        assert "customer-withheld" in row or "reduced" in row, (
            f"{INDEX[page]}: `{section}` is withheld from the customer "
            f"audience and its row does not say so: {row!r}")


def test_a_customer_withheld_page_says_so():
    R = _redaction()
    for page in sorted(R.CUSTOMER_WITHHELD_PAGES):
        text = (PAGES_DIR / INDEX[page]).read_text(encoding="utf-8")
        assert "customer-withheld" in text, INDEX[page]
