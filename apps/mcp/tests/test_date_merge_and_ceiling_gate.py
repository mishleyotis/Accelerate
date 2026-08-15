"""Two defects a producer found by meeting them, 2026-08-15.

1. `register_evidence` dedup merged links and silently dropped the date.

   A producer registered three spans from a client agreement before it had
   established the document's date, then re-registered them with
   `published_date` set. Dedup fired, `linked_subcap_ids` MERGED — a new cell
   was genuinely added to the stored row — and `published_date` stayed null.

   The merge was PARTIAL: one field and not the other. So an item first
   registered undated could never afterwards be dated, sat at UNVERIFIED
   forever, and its rank score stayed suppressed — 3.40 undated against 4.15
   dated, on comparable spans from the same document. Recency is 25% of ERS.

2. The run-level alert ceiling had no gate registry entry.

   `explain_gate` answered `unknown_gate` for the one rule in this system a
   producer could meet and then not look up. Invariant 12 says a verdict
   names the gate; that refusal named none.
"""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))

from dma_mcp import gates                       # noqa: E402
from dma_mcp.register import date_merge         # noqa: E402

D1 = dt.date(2024, 12, 1)
D2 = dt.date(2025, 6, 30)


# ── the partial merge ─────────────────────────────────────────────────
def test_a_date_arriving_after_an_undated_registration_is_taken():
    """The measured case. Unknown becoming known is strictly additive."""
    assert date_merge(None, D1) == "fill"


def test_agreement_changes_nothing():
    assert date_merge(D1, D1) == "keep"


def test_an_undated_re_registration_never_erases_a_stored_date():
    """The reverse of the bug must not become a new one: a later call that
    says nothing about the date must not blank a date already established."""
    assert date_merge(D1, None) == "keep"
    assert date_merge(None, None) == "keep"


def test_two_different_dates_are_a_contradiction_not_a_later_write_winning():
    """Two sources disagreeing about when a document was published is a
    FINDING. Taking the second call's answer resolves it silently in favour
    of whichever happened to be second, which is not a resolution — it is the
    same shape as averaging two disagreeing figures."""
    assert date_merge(D1, D2) == "contradiction"
    assert date_merge(D2, D1) == "contradiction"


def test_the_contradiction_branch_keeps_the_stored_date():
    """Asserted on the code, because the alternative is a silent overwrite
    and no unit test of `date_merge` alone can see which way the caller
    jumps."""
    src = (ROOT / "apps" / "mcp" / "dma_mcp" / "register.py").read_text()
    fill = src.index('verdict == "fill"')
    contra = src.index('verdict == "contradiction"')
    assert src.count("UPDATE evidence_index") == 1, (
        "more than one update path — the contradiction branch may now write")
    assert src.index("UPDATE evidence_index") < contra, (
        "the only UPDATE must sit in the fill branch, above the "
        "contradiction branch which reports and writes nothing")
    assert fill < contra


def test_the_fill_branch_recomputes_the_rank_score():
    """Filling the date without recomputing ERS would leave the row scored as
    though nobody had ever dated it — the defect's own consequence, kept."""
    src = (ROOT / "apps" / "mcp" / "dma_mcp" / "register.py").read_text()
    block = src[src.index('verdict == "fill""'.replace('""', '"')):]
    block = block[:block.index("elif verdict")]
    assert "ers = round(" in block and "_RECENCY_FACTOR[new_band]" in block


# ── the gate that could not be looked up ──────────────────────────────
def test_the_run_level_ceiling_is_in_the_gate_registry():
    assert "SG-AC1" in gates.GATES, (
        "the alert ceiling is the only rule a producer can meet and then not "
        "look up; explain_gate answered unknown_gate")
    name, plain, what, why, on_failure = gates.GATES["SG-AC1"]
    assert on_failure == "block"
    assert plain, "SG gates render to a client and need a plain_label"
    assert 8 <= len(plain.split()) <= 18, (
        f"plain_label is {len(plain.split())} words; the safeguard contract "
        "says 8-18")
    assert "98" in why, "the measurement that motivated it belongs in the why"


def test_the_family_prefix_resolves():
    """`ensure_gate_registry` derives family from the id prefix and would
    KeyError on an unknown one — seeding every gate, not just this one."""
    assert gates._FAMILY[("SG-AC1").split("-")[0]] == "safeguard"


def test_the_refusal_names_its_gate():
    """Invariant 12: a verdict names the gate. It did not."""
    src = (ROOT / "apps" / "mcp" / "dma_mcp" / "promote.py").read_text()
    i = src.index('"error": "alert_ceiling_exceeded"')
    tail = src[i:i + 900]
    assert '"gate_id": "SG-AC1"' in tail
    assert "explain_gate" in tail, "name the tool that answers 'why 15'"
