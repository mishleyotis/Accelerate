"""The shape-only gold for the six app pages — RC-01, SWBC gold audit 2026-10-04.

For the app pages there was no measurable gold: the gold doc covered the
workbook and the reports, the rest was prose or key names, and nothing carried
row counts, a stated-value share or a per-audience disposition. So "in line
with gold" could be neither met nor checked. `fixtures/surface_gold.json` is
that measure; these tests keep it honest:

  · it has a disposition for every section the contract declares, and that
    disposition is what `redaction.py` actually does — a gold that says
    "served" for a section the API withholds teaches producers the wrong page
  · the connector's copy is byte-identical (the promote path reads it, and
    `fixtures/` is not in the connector's image)
  · it carries no values: shape only, per the owner's 2026-10-04 decision

(The RCA named this file tests/shared/test_surface_gold.py; it lives under
scripts/tests/ because that is the directory CI's pytest job runs.)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "apps" / "mcp"))
sys.path.insert(0, str(ROOT / "apps" / "api"))

GOLD = ROOT / "fixtures" / "surface_gold.json"
MCP_COPY = ROOT / "apps" / "mcp" / "dma_mcp" / "surface_gold.json"


def _gold():
    return json.loads(GOLD.read_text())


def test_every_contract_section_has_a_disposition():
    from dma_mcp.contracts import PAGES, sections
    want = {f"{p}.{s}" for p in PAGES for s in sections(p)}
    have = set(_gold()["dispositions"])
    assert want - have == set(), sorted(want - have)


def test_dispositions_equal_what_redaction_does():
    """Generated from redaction.py; re-derived here so a redaction change
    without a regeneration fails. Regenerate with
    `python3 scripts/gen_surface_gold.py --dispositions-only`."""
    import gen_surface_gold as gen
    gold = _gold()
    assert gold["dispositions"] == gen.dispositions(gold["dispositions"]), (
        "fixtures/surface_gold.json disagrees with redaction.py — run "
        "scripts/gen_surface_gold.py --dispositions-only")


def test_the_never_served_sections_are_never_served():
    from dma_api import redaction as R
    d = _gold()["dispositions"]
    for page, section in R.NEVER_SERVED:
        assert d[f"{page}.{section}"] == {"internal": "never_served",
                                          "customer": "never_served"}


def test_the_connector_reads_the_same_bytes():
    assert MCP_COPY.read_bytes() == GOLD.read_bytes(), (
        "apps/mcp/dma_mcp/surface_gold.json drifted from fixtures/ — "
        "scripts/gen_surface_gold.py writes both")


def test_three_gold_runs_and_all_six_pages():
    runs = _gold()["runs"]
    assert sorted(runs) == ["gold-40971653", "gold-c1351d25", "gold-d7ed1d90"]
    for label, run in runs.items():
        assert set(run["pages"]) == {"overview", "heatmap", "insights",
                                     "platform", "context", "techstack"}, label


def test_the_gold_carries_shape_and_no_values():
    """Only shape tokens survive: identifiers (keys), null-pattern rows, and
    counts. No float, no free text — so no name, no figure, no quote."""
    pattern = re.compile(r"^[10yns\-]*$")
    ident = re.compile(r"^[a-z][a-z0-9_]*$")

    def walk(x, path):
        if isinstance(x, dict):
            for k, v in x.items():
                assert ident.match(k) or k.startswith("gold-"), (path, k)
                walk(v, f"{path}.{k}")
        elif isinstance(x, list):
            for v in x:
                walk(v, path)
        elif isinstance(x, str):
            assert pattern.match(x) or ident.match(x), (path, x[:40])
        elif isinstance(x, bool) or x is None:
            pass
        else:
            assert isinstance(x, int), (path, x)

    for label, run in _gold()["runs"].items():
        walk(run["pages"], label)


def test_the_summary_quotes_what_the_doc_quotes():
    """GOLD-STANDARD-APP-PAGES.md reads its floors from here."""
    s = _gold()["summary"]
    firmo = s["overview.firmographics"]["lists"]["fields"]
    assert firmo["min_n"] >= 15 and firmo["min_stated_share"] >= 0.9
    docs = ROOT / "plugins" / "dma-insights" / "docs"
    doc = (docs / "GOLD-STANDARD-APP-PAGES.md").read_text()
    assert "fixtures/surface_gold.json" in doc
    assert "## App pages" in doc
    # The workbook/report gold doc still points readers at the split file.
    assert "GOLD-STANDARD-APP-PAGES.md" in (docs / "GOLD-STANDARD.md").read_text()


def test_every_gold_run_records_its_sub_vertical_and_run_prefix():
    """CG-PAR prefers gold of the target's sub-vertical and leaves a gold run
    out of its own reference set; both read these two fields (owner decision
    B, 2026-10-04)."""
    from dma_mcp import parity
    for label, run in _gold()["runs"].items():
        assert run.get("sub_vertical") in parity.SUB_VERTICALS, label
        assert label.endswith(run.get("run_id_prefix") or "?"), label


def test_the_generator_refuses_a_gold_run_with_no_sub_vertical():
    import gen_surface_gold as gen
    assert gen.check_meta({"gold-x": {}}, {}) == ["gold-x: sub_vertical None"]
    assert gen.check_meta({"gold-x": {}}, {"gold-x": {"sub_vertical": "IB"}}) \
        == []


def test_a_projected_section_reads_reduced_not_withheld():
    """Owner decision 1: the customer gets a REDUCED sentiment card. The gold
    said `withheld` until the redaction change landed; it now says what
    redaction.py does."""
    assert _gold()["dispositions"]["overview.sentiment"] == {
        "internal": "served", "customer": "reduced"}
