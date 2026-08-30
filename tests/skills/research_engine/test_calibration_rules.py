"""Rules earned by the 2026-08-29 live calibration (one category, real web
research through the plugin's own category agent).

Three defects the calibration surfaced, each now a refusal:
  1. Six syntheses shipped with Ceiling_Reasoning arguing a ceiling at
     length and Ceiling_Band EMPTY — nothing downstream could read the
     conclusion. Band is now required for positively-evidenced labels.
  2. A FACT could rest entirely on one document cited three times.
     single_source_fact now blocks the floors gate.
  3. NOT_RUN was written over volleys whose searches sat in the log —
     protocol vocabulary now splits NOT_RUN (never fired) from NO_FINDING
     (fired, empty); the ledger accepts both, and this file pins that a
     NO_FINDING answer satisfies the facet-honesty check.
"""
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[2].parent / (
    "plugins/dma-insights/skills/dma-research")
sys.path.insert(0, str(ENGINE))

from engine import contract as C, floors_gate, ledger as L  # noqa: E402
from fixtures import bank_evidence, challenge, good_synthesis, new_run, small_selection  # noqa: E402


def _ready(tmp_path):
    run = new_run(tmp_path)
    wb = run.open()
    sub = small_selection(1)[0]
    return run, wb, sub, bank_evidence(wb, sub)


# ── 1 · the band is the conclusion, stated ────────────────────────────────

def test_a_fact_without_a_band_is_refused(tmp_path):
    _, wb, sub, eids = _ready(tmp_path)
    rec = good_synthesis(sub, eids)
    rec["Ceiling_Band"] = ""
    with pytest.raises(L.LedgerRefusal, match="Ceiling_Band"):
        L.append_synthesis(wb, sub, rec, actor="research-p1c1-producer")


def test_a_fifth_band_word_is_refused(tmp_path):
    _, wb, sub, eids = _ready(tmp_path)
    rec = good_synthesis(sub, eids)
    rec["Ceiling_Band"] = "Transformational"
    with pytest.raises(L.LedgerRefusal, match="Ceiling_Band"):
        L.append_synthesis(wb, sub, rec, actor="research-p1c1-producer")


def test_a_documented_absence_keeps_its_null_band(tmp_path):
    """Invariant 9: null means no score. A HYPOTHESIS absence must not be
    forced to invent a band to satisfy the new rule."""
    _, wb, sub, eids = _ready(tmp_path)
    rec = good_synthesis(sub, eids)
    rec.update({
        "Claim_Label": "HYPOTHESIS", "Ceiling_Band": "",
        "Dominant_Claim": ("No public record names a review cadence for this "
                           "capability; a three-rung search returned nothing."),
        "Absence_Claimed": "YES",
        "Proxy_Log": "direct:: searched X — none | proxy:: searched Y — none",
    })
    out = L.append_synthesis(wb, sub, rec, actor="research-p1c1-producer")
    assert out["subcap"] == sub


# ── 2 · a FACT needs two source identities ────────────────────────────────

def test_a_single_document_fact_blocks_the_gate(tmp_path):
    run, wb, sub, _ = _ready(tmp_path)
    # a second subcap whose three rows are all the SAME host
    sub2 = small_selection(2)[1]
    eids2 = [L.append_evidence(
        wb, source_name=f"Annual Report 2025 p{i}",
        source_url=f"https://acme.example/ar25#x{i}", tier="T2",
        excerpt=("Alkami digital banking went live in Q3 2024 and reached 47 "
                 f"percent member adoption within ninety days, restated at "
                 f"{50+i} percent in the 2025 report."),
        subcaps=[sub2], published="2025-06-01") for i in range(3)]
    L.append_synthesis(wb, sub2, good_synthesis(sub2, eids2),
                       actor="research-p1c1-producer")
    challenge(wb, sub2)
    out = floors_gate.run(wb, "P1C1", qa_dir=run.qa_dir)
    hit = [f for f in out["single_source_fact"] if f["subcap"] == sub2]
    assert hit and "single_source_fact" in out["blocking"], (
        "three pages of one annual report are one source; FACT needs two")


def test_two_source_identities_pass(tmp_path):
    """The fixture path: two hosts (annual report + call report) clears it."""
    run, wb, sub, eids = _ready(tmp_path)
    L.append_synthesis(wb, sub, good_synthesis(sub, eids),
                       actor="research-p1c1-producer")
    challenge(wb, sub)
    out = floors_gate.run(wb, "P1C1", qa_dir=run.qa_dir)
    assert not [f for f in out["single_source_fact"] if f["subcap"] == sub]


# ── 3 · NO_FINDING is an answer, not a gap ────────────────────────────────

def test_no_finding_satisfies_the_facet_honesty_check(tmp_path):
    _, wb, sub, eids = _ready(tmp_path)
    rec = good_synthesis(sub, eids)
    rec["DQ_Fails"] = ("NO_FINDING after 3 logged searches: hunted outage, "
                       "complaint and abandonment artefacts for 2023-2026; "
                       "the volley surfaced only an unrelated employment suit.")
    out = L.append_synthesis(wb, sub, rec, actor="research-p1c1-producer")
    assert out["subcap"] == sub


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
