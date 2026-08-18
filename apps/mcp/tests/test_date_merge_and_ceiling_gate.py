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

   RETIRED 2026-08-16: the ceiling itself was removed, so there is no longer
   a rule here to look up. A second client owed 621 alerts against it — the
   count measures the assessment's evidence mode, not the run's quality. The
   registry assertions below became assertions about ABSENCE, because a
   registry that keeps answering for a removed gate is worse than one that
   says `unknown_gate`: it reads as a live constraint. What the ceiling was,
   why it went, and where the count survives are in
   `apps/mcp/tests/test_alert_ceiling.py`.
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


# ── the gate that was removed ─────────────────────────────────────────
def test_the_removed_ceiling_is_not_in_the_gate_registry():
    """Removed means removed. A `"disabled"` entry left behind would let
    `explain_gate("SG-AC1")` keep returning a definition for a rule nothing
    enforces, and a producer would repair against a constraint that cannot
    fire."""
    assert "SG-AC1" not in gates.GATES


def test_the_family_prefix_still_resolves_for_the_gates_that_remain():
    """`ensure_gate_registry` derives family from the id prefix and would
    KeyError on an unknown one — seeding every gate, so the prefix table has
    to cover every id still in the registry, not just the ones anyone
    remembers."""
    for gate_id in gates.GATES:
        prefix = gate_id.split("-")[0]
        assert prefix in gates._FAMILY, (
            f"{gate_id} has prefix {prefix!r}, which _FAMILY does not map; "
            "seeding the registry would KeyError on it")


def test_promote_no_longer_refuses_on_the_alert_count():
    src = (ROOT / "apps" / "mcp" / "dma_mcp" / "promote.py").read_text()
    assert '"error": "alert_ceiling_exceeded"' not in src
