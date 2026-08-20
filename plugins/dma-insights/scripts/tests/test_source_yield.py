"""The source-yield ledger: measured yield decides tomorrow's first search.

The properties that matter: rich beats thin beats empty in the ranking; an
empty is recorded rather than forgotten (a reliably-empty source opens
LAST, and a recorded negative stops a repeat search); a family match
outranks facet-wide performance; and a rich-but-undeclared source surfaces
as a register candidate — the "evidence source list keeps expanding" half
of the owner's instruction.
"""
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import source_yield  # noqa: E402


def test_rich_sources_rank_above_thin_and_empty(tmp_path):
    p = tmp_path / "y.json"
    source_yield.log("ncua.gov", "firmographics", "rich", tier="T1", path=p)
    source_yield.log("ncua.gov", "firmographics", "rich", tier="T1", path=p)
    source_yield.log("prnewswire.com", "firmographics", "thin", path=p)
    source_yield.log("crunchbase.com", "firmographics", "empty", path=p)
    ranked = source_yield.rank("firmographics", path=p)
    assert [r["source"] for r in ranked][:1] == ["ncua.gov"]
    assert ranked[-1]["source"] == "crunchbase.com"
    assert ranked[-1]["yield_score"] < 0


def test_a_family_match_outranks_facet_wide_yield(tmp_path):
    p = tmp_path / "y.json"
    source_yield.log("vendorblog.com", "techstack", "rich", path=p)
    source_yield.log("linkedin.com", "techstack", "rich",
                     family="P4C2.5", path=p)
    ranked = source_yield.rank("techstack", family="P4C2.5", path=p)
    assert ranked[0]["source"] == "linkedin.com"


def test_other_facets_do_not_leak_into_the_ranking(tmp_path):
    p = tmp_path / "y.json"
    source_yield.log("ncua.gov", "firmographics", "rich", path=p)
    assert source_yield.rank("sentiment", path=p) == []


def test_stale_yield_decays(tmp_path):
    p = tmp_path / "y.json"
    d = {"entries": [
        {"source": "old.com", "facet": "why_now", "outcome": "rich",
         "on": "2024-01-01", "raised_by": "t"},
        {"source": "new.com", "facet": "why_now", "outcome": "rich",
         "on": "2026-08-01", "raised_by": "t"},
    ]}
    p.write_text(json.dumps(d))
    ranked = source_yield.rank("why_now", today="2026-08-20", path=p)
    assert ranked[0]["source"] == "new.com"
    assert ranked[0]["yield_score"] > ranked[1]["yield_score"]


def test_rich_undeclared_sources_surface_as_register_candidates(tmp_path):
    p = tmp_path / "y.json"
    reg = tmp_path / "register.json"
    reg.write_text(json.dumps({"declared": ["clay", "first_party"]}))
    source_yield.log("cusotimes.com", "why_now", "rich", path=p)
    source_yield.log("cusotimes.com", "why_now", "rich", path=p)
    source_yield.log("once.com", "why_now", "rich", path=p)      # only once
    source_yield.log("clay", "techstack", "rich", path=p)        # declared
    source_yield.log("clay", "techstack", "rich", path=p)
    out = source_yield.candidates(path=p, register=reg)
    assert out == ["cusotimes.com"]


def test_a_url_is_refused_where_a_domain_belongs(tmp_path):
    with pytest.raises(SystemExit):
        source_yield.log("https://ncua.gov/report", "firmographics", "rich",
                         path=tmp_path / "y.json")


def test_entries_are_taxonomy_never_prose(tmp_path):
    p = tmp_path / "y.json"
    e = source_yield.log("ncua.gov", "firmographics", "rich", tier="t1",
                         family="P1C1.1", raised_by="qa-overseer",
                         note="5300 call reports", path=p)
    assert set(e) <= {"source", "facet", "outcome", "on", "raised_by",
                      "tier", "family", "note"}
    assert e["tier"] == "T1"
