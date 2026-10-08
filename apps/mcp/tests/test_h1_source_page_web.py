"""CG-03b (H1) — source_page is for a paged document; a web page has none.

RC-09 / D-30 (SWBC gold audit, 2026-10-04; slice HM-07). The contract said
"source_page REQUIRED", so SWBC served source_page = 1 on all four focus areas
— three of them web pages whose own text reads "(web page, unpaginated)". A
page number on a URL is a default that looks like data (invariant 9). The
contract now reads "required for a paged document; null for an unpaginated
artefact", and a page on a web URL is refused. A Drive-hosted PDF is paged
(Golden 1 cites pages 8, 17 and 19 of one).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.contracts import sections  # noqa: E402
from dma_mcp.validation import _check_prose_shapes  # noqa: E402


def _run(*areas):
    return _check_prose_shapes("heatmap", "focus_areas",
                               {"focus_areas": list(areas)})


def test_source_page_on_a_web_url_is_refused():
    out = _run({"fa_id": "FA-2", "source_page": 1,
                "source_filename": "https://www.swbc.com/about-swbc/press/"
                                   "article/swbc-launches"})
    assert len(out) == 1
    assert out[0]["path"] == "focus_areas.focus_areas[0].source_page"


def test_a_source_marked_unpaginated_is_refused():
    out = _run({"source_page": 1, "source_filename": "notes",
                "source_document": "SWBC newsroom (web page, unpaginated)"})
    assert len(out) == 1


def test_null_on_a_web_page_and_a_page_in_a_pdf_pass():
    assert _run(
        {"source_page": None, "source_filename": "https://www.swbc.com/x"},
        {"source_page": 17, "source_filename": "https://drive.google.com/file/"
                                               "d/1UQo/view"},
        {"source_page": 2, "source_filename": "HHRG-119-BA20-Wstate.pdf"}) == []


def test_the_contract_no_longer_says_required_unconditionally():
    doc = sections("heatmap")["focus_areas"]["fields"]["focus_areas"]["doc"]
    assert "source_page REQUIRED" not in doc
    assert "NULL for an unpaginated artefact" in doc
