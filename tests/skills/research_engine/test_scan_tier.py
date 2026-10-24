"""A machine technographic scan is T1 — refused at the write at any other tier.

Regression seed 2's second half, measured 28-09-2026 (QA audit F-J04-015):
on one staged heatmap 5 of 6 technographic rows sat at T3. The research
ladder has said "scans = T1, never T4" for five versions and nothing in the
ledger compared the source with the tier. `contract.scan_source` names the
provider a source carries; the ledger refuses a named scan below T1 and
tells the writer the tier to fix, before the FACT rule can tell it the
label that follows.
"""
import pytest

from engine import contract as C
from engine import ledger as L
from engine.ledger import LedgerRefusal

from fixtures import new_run

EXCERPT = ("Technology profile: Salesforce Financial Services Cloud detected "
           "on the customer portal, Marketo on the marketing domain, last "
           "crawled 2026-06-14 by the technographic scanner.")


def _run(tmp_path):
    run = new_run(tmp_path, n=3, prelim=False)
    wb = run.open()
    return run, wb, wb.selected_subcaps()


def test_the_scan_tier_is_t1_and_the_tokens_name_the_providers_the_ladder_names():
    assert C.SCAN_TIER == "T1" and C.SCAN_TIER in C.FACT_TIERS
    for tok in ("hubbl", "builtwith", "wappalyzer", "explorium", "technographic"):
        assert tok in C.SCAN_SOURCE_TOKENS


@pytest.mark.parametrize("name,url,expect", [
    ("BuiltWith technology profile", "https://builtwith.com/goeasy.com", "builtwith"),
    ("appsruntheworld.com technographic customer record",
     "https://www.appsruntheworld.com/customers-database/customers/view/x", "appsruntheworld"),
    ("Hubbl scan 2026-06", None, "hubbl"),
    ("Vendor page", "https://trends.builtwith.com/x", "builtwith"),
    ("goeasy Q2 2026 earnings call transcript", "https://investing.example/x", None),
    ("Trade press on technographics vendors", "https://news.example/y", "technographics"),
    ("scanning the horizon", "https://x.example/wappalyzers-cousin", None),
])
def test_scan_source_matches_whole_tokens_in_name_or_url(name, url, expect):
    assert C.scan_source(name, url) == expect


@pytest.mark.parametrize("tier", ["T2", "T3", "T4", "T5"])
def test_a_named_scan_below_t1_is_refused_naming_provider_tier_and_t1(tmp_path, tier):
    run, wb, cells = _run(tmp_path)
    with pytest.raises(LedgerRefusal) as exc:
        L.append_evidence(wb, source_name="appsruntheworld.com technographic customer record",
                          source_url="https://www.appsruntheworld.com/customers-database/x",
                          tier=tier, excerpt=EXCERPT, subcaps=[cells[0]])
    msg = str(exc.value)
    assert "appsruntheworld" in msg and tier in msg and "T1" in msg
    assert "SCAN_TIER" in msg


def test_a_scan_at_t1_registers_as_a_fact(tmp_path):
    run, wb, cells = _run(tmp_path)
    eid = L.append_evidence(wb, source_name="BuiltWith technology profile",
                            source_url="https://builtwith.com/goeasy.com",
                            tier="T1", excerpt=EXCERPT, subcaps=[cells[0]])
    for row in wb.rows("Evidence_Detail"):
        if eid in {str(v) for v in row.values()}:
            assert str(row.get("Claim_Type")) == "FACT"
            break
    else:
        raise AssertionError(eid)


def test_a_source_that_is_not_a_scan_still_registers_at_t3(tmp_path):
    run, wb, cells = _run(tmp_path)
    eid = L.append_evidence(wb, source_name="Trade press", source_url="https://news.example/z",
                            tier="T3", excerpt=EXCERPT, subcaps=[cells[0]])
    assert eid


def test_the_scan_rule_speaks_before_the_fact_rule(tmp_path):
    """A scan at T3 typed FACT is told the TIER to fix, not the label: once
    the row is at T1 the FACT is licensed."""
    run, wb, cells = _run(tmp_path)
    with pytest.raises(LedgerRefusal) as exc:
        L.append_evidence(wb, source_name="Wappalyzer profile", source_url="https://www.wappalyzer.com/x",
                          tier="T3", excerpt=EXCERPT, subcaps=[cells[0]], claim_type="FACT")
    assert "SCAN_TIER" in str(exc.value) and "FACT_TIERS" not in str(exc.value)


def test_the_excerpt_refusal_still_comes_first(tmp_path):
    run, wb, cells = _run(tmp_path)
    with pytest.raises(LedgerRefusal) as exc:
        L.append_evidence(wb, source_name="Hubbl scan", source_url="https://hubbl.example/x",
                          tier="T3", excerpt="too short", subcaps=[cells[0]])
    assert "50-500" in str(exc.value)
