"""A claim label is derived from provenance, never typed.

Regression seed 2, measured live on 28-09-2026 (QA audit F-J04-004): on one
staged heatmap 77 of 285 FACT rows rested on T3/T4 reportage, because
`engine.cli evidence` defaulted `--claim-type` to FACT and nothing in the
ledger, the quality checks or the connector compared the label with the
tier. These rows hold the three halves of the fix:

  * the ledger refuses a STATED FACT on a tier outside `contract.FACT_TIERS`;
  * a writer that states no label gets the one its tier licenses;
  * the notebook path shows the refusal in place instead of laundering it.

The excerpt refusal still fires first, so `test_memory.py`'s "50-500"
expectations are untouched.
"""
import pytest

from engine import contract as C
from engine import ledger as L
from engine import memory as M
from engine.ledger import LedgerRefusal

from fixtures import CAT, new_run

EXCERPT = ("Alkami digital banking went live in Q3 2024 and reached 47 "
           "percent member adoption within ninety days of launch.")
PAGE = "Acme Credit Union annual report 2025.\n" + EXCERPT + "\nEnd."
URL = "https://press.example/acme-ar25"   # not the entity's own site: own-site T1 is refused (MEM-0588)


def _run(tmp_path):
    run = new_run(tmp_path, n=3, prelim=False)
    wb = run.open()
    return run, wb, wb.selected_subcaps()


def _read(run, url, text=PAGE):
    from engine import fetch as F
    F.store_text(run, url, text, content_type="test-fixture")


def _label_of(wb, eid: str) -> str:
    for row in wb.rows("Evidence_Detail"):
        if eid in {str(v) for v in row.values()}:
            return str(row.get("Claim_Type") or "")
    raise AssertionError(f"{eid} not in Evidence_Detail")


def test_fact_tiers_are_t1_and_t2_and_the_derivation_follows_them():
    assert C.FACT_TIERS == ("T1", "T2")
    assert C.claim_label_for("T1") == "FACT"
    assert C.claim_label_for("T2") == "FACT"
    for weak in ("T3", "T4", "T5", C.NO_EVIDENCE):
        assert C.claim_label_for(weak) == "INFERENCE"


@pytest.mark.parametrize("tier", ["T3", "T4", "T5"])
def test_a_stated_fact_on_a_weak_tier_is_refused_naming_tier_and_rule(tmp_path, tier):
    run, wb, cells = _run(tmp_path)
    with pytest.raises(LedgerRefusal) as exc:
        L.append_evidence(wb, source_name="Trade press", source_url=URL,
                          tier=tier, excerpt=EXCERPT, subcaps=[cells[0]],
                          claim_type="FACT")
    msg = str(exc.value)
    assert "FACT" in msg and tier in msg and "T1" in msg and "T2" in msg


@pytest.mark.parametrize("tier", ["T1", "T2"])
def test_a_fact_on_t1_or_t2_registers(tmp_path, tier):
    run, wb, cells = _run(tmp_path)
    eid = L.append_evidence(wb, source_name="Annual report", source_url=URL,
                            tier=tier, excerpt=EXCERPT, subcaps=[cells[0]],
                            claim_type="FACT")
    assert _label_of(wb, eid) == "FACT"


def test_an_inference_on_t3_registers(tmp_path):
    run, wb, cells = _run(tmp_path)
    eid = L.append_evidence(wb, source_name="Trade press", source_url=URL,
                            tier="T3", excerpt=EXCERPT, subcaps=[cells[0]],
                            claim_type="INFERENCE")
    assert _label_of(wb, eid) == "INFERENCE"


@pytest.mark.parametrize("tier,label", [("T1", "FACT"), ("T2", "FACT"),
                                        ("T3", "INFERENCE"), ("T4", "INFERENCE")])
def test_an_unlabelled_row_gets_the_label_its_tier_licenses(tmp_path, tier, label):
    """The old default typed FACT for every row; the derived label is what
    the provenance can carry."""
    run, wb, cells = _run(tmp_path)
    eid = L.append_evidence(wb, source_name="Source", source_url=URL,
                            tier=tier, excerpt=EXCERPT, subcaps=[cells[0]])
    assert _label_of(wb, eid) == label


def test_the_excerpt_refusal_still_comes_before_the_tier_rule(tmp_path):
    """Ordering is part of the contract: a thin T5 note is refused on its
    length (the message the notebook tests assert), not on its label."""
    run, wb, cells = _run(tmp_path)
    with pytest.raises(LedgerRefusal) as exc:
        L.append_evidence(wb, source_name="blog", source_url="https://a.example/x",
                          tier="T5", excerpt="too short", subcaps=[cells[0]],
                          claim_type="FACT")
    assert "50-500" in str(exc.value)


def test_a_note_without_a_label_consolidates_as_inference_on_t3(tmp_path):
    run, wb, cells = _run(tmp_path)
    _read(run, URL)
    M.note(run, category=CAT, subcap=cells[0], facet="works", kind="evidence",
           claim="Alkami live since Q3 2024", url=URL, excerpt=EXCERPT,
           source_name="Trade press", tier="T3", published="2025-03-01")
    out = M.consolidate(run, CAT)
    assert out["consolidated"] == 1 and out["blocked"] == 0
    wb = run.open()
    labels = {str(r.get("Claim_Type") or "") for r in wb.rows("Evidence_Detail")
              if str(r.get("Source_URL") or r.get("URL") or "") == URL
              or EXCERPT[:40] in str(r.get("Excerpt") or "")}
    assert labels == {"INFERENCE"}


def test_a_note_that_states_fact_on_t3_is_blocked_in_place_with_the_reason(tmp_path):
    run, wb, cells = _run(tmp_path)
    _read(run, URL)
    M.note(run, category=CAT, subcap=cells[0], facet="works", kind="evidence",
           claim="Alkami live since Q3 2024", url=URL, excerpt=EXCERPT,
           source_name="Trade press", tier="T3", published="2025-03-01",
           claim_type="FACT")
    out = M.consolidate(run, CAT)
    assert out["blocked"] == 1 and out["consolidated"] == 0
    text = M.memory_path(run, CAT).read_text()
    assert "[BLOCKED]" in text and "FACT" in text and "T3" in text
