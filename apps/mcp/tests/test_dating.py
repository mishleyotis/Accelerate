"""CG-10 — a date that could not be established says so.

The defective shape is verbatim from a promoted run: three rows of the
context issue register carrying `opened_on: null` and nothing else. The
register orders on that date and the Gantt draws its bar from it, so the
row rendered with an empty date slot beside four populated ones — which
reads as undated when nobody looked and as undated when somebody looked
and found nothing. Those are different facts (invariant 9), so the
payload has to distinguish them.

The correct shapes are here too, because the gate would be wrong to
refuse them: a firmographic with `as_of: null` and `recency_band:
UNVERIFIED` is the absence stated properly, and a SECOND date on the same
item — `resolved_on` on an ACTIVE matter, `closed_on` on an ANNOUNCED
merger — is null because the event has not happened.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation import _check_date_absence, validate_pass1
from dma_mcp.validation2 import _check_evidence_dating

# verbatim from the promoted run
ISS_002 = {"issue_id": "ISS-002", "title": "Fraud False Positives",
           "severity": "low", "status": "ACTIVE", "opened_on": None,
           "resolved_on": None,
           "rationale": "Trustpilot false positive fraud blocks on legitimate "
                        "transactions. Cap effect: NONE.",
           "linked_subcap_ids": [], "e_ids": ["E-BCU-053"]}


def test_the_promoted_bare_null_is_refused_and_the_path_names_the_row():
    out = _check_date_absence("context", "issue_register",
                              {"issues": [ISS_002]})
    assert len(out) == 1
    r = out[0]
    assert r["gate_id"] == "CG-10" and r["severity"] == "block"
    assert r["path"] == "issue_register.issues[0].opened_on"
    assert "bare null" in r["message"] and "orders on opened_on" in r["message"]


def test_the_second_date_on_the_same_row_is_untouched():
    """`resolved_on` is null because the matter is ACTIVE. Refusing that
    would be refusing the truth — only the item's OWN dating field is
    registered."""
    assert all(r["path"].endswith("opened_on")
               for r in _check_date_absence("context", "issue_register",
                                            {"issues": [ISS_002]}))


def test_stating_the_date_clears_it():
    fixed = {**ISS_002, "opened_on": "2025-11-01"}
    assert _check_date_absence("context", "issue_register",
                               {"issues": [fixed]}) == []


def test_the_ladder_clears_it_without_inventing_a_date():
    """The other honest repair: say what was searched. An absence with a
    record is a finding; an absence with none is a hole."""
    recorded = {**ISS_002,
                "sources_searched": ["the review corpus, all 340 items",
                                     "the credit union's own newsroom"]}
    assert _check_date_absence("context", "issue_register",
                               {"issues": [recorded]}) == []


def test_the_firmographic_rung_already_in_the_run_passes():
    """Verbatim from the same run: three financial fields with no as_of,
    each carrying recency_band UNVERIFIED. That IS the absence rung —
    undated evidence is UNVERIFIED, never current."""
    body = {"fields": [
        {"field": "shares", "value": None, "unit": None, "as_of": None,
         "recency_band": "UNVERIFIED", "source_e_id": None,
         "confidence": None, "quarantined": False, "quarantine_reason": None},
        {"field": "assets", "value": 6.5e9, "as_of": "2026-06-30",
         "recency_band": "CURRENT"},
    ]}
    assert _check_date_absence("overview", "firmographics", body) == []
    # and strip the rung and it is refused
    body["fields"][0].pop("recency_band")
    assert len(_check_date_absence("overview", "firmographics", body)) == 1


def test_a_quarantined_row_states_its_own_reason():
    body = {"fields": [{"field": "roa", "value": None, "as_of": None,
                        "quarantined": True,
                        "quarantine_reason": "the figure resolved to a "
                                             "name-similar institution"}]}
    assert _check_date_absence("overview", "firmographics", body) == []


def test_the_evidence_half_refuses_a_freshness_computed_from_no_date():
    """Invariant 9 on the store side: a row with no published_date whose
    band says CURRENT is a freshness reading drawn from nothing, and the
    drawer's freshness dot is drawn from that band."""
    row = {"e_id": "E-BCU-070", "stored_id": "E-BCU-070", "excerpt": "x" * 80,
           "published_date": None, "recency_band": "CURRENT"}
    out = _check_evidence_dating([row], {"E-BCU-070": "cell_evidence"})
    assert len(out) == 1 and out[0]["gate_id"] == "CG-10"
    assert "UNVERIFIED, never current" in out[0]["message"]
    row["recency_band"] = "UNVERIFIED"
    assert _check_evidence_dating([row], {"E-BCU-070": "cell_evidence"}) == []


def test_the_gate_reaches_the_verdict_through_pass_one():
    payload = {"issue_register": {
        "produced_at": "2026-08-07T00:00:00Z", "producer_version": "test@1",
        "e_ids": [], "internal_only": [], "issues": [ISS_002]}}
    gates = {r["gate_id"] for r in validate_pass1("context", payload)}
    assert "CG-10" in gates
