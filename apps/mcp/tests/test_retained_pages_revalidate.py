"""A retained PASS is a dated observation, and promote used to treat it as current.

Measured 2026-08-16. A run was re-promoted from retained staging rows after an
unrelated gate was removed. Promotion carried forward payloads dated a week
earlier — none of the owner's reported issues re-synthesised — and the promote
result disclosed EIGHT CG-15 reasons at `"severity": "block"` on
`heatmap.cell_evidence`. It promoted anyway. The content reached the client
surface, and the run's rows said PASS.

The re-validation was already running. It found the reasons, wrote them into
`stale_verdicts`, and nothing refused on them.

    "Disclosed" is only a control if something downstream refuses on it. The
    disclosure landed in a promote result that is read once, by whoever typed
    the call, and a result whose top-level field says `"promoted": true` is
    read as success.

The argument the old behaviour rested on is in the module's history and had
force: a gate that tightened after a page was authored should not strand five
other pages that are fine, and retroactive refusal is how a build stops adding
gates. Retention answers it. The repair is to resubmit the ONE page named and
promote again — invariant 3 exists precisely so that costs one re-synthesis
rather than six.

SG keeps the old behaviour, because the charter states it: a failing safeguard
discloses and still promotes. A failing CG, AG or ET is a correctness reason
and does not.
"""
import inspect
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp import promote as P

SRC = inspect.getsource(P)
#: Adjacent string literals in the source are split across lines, so a phrase
#: that reads as one sentence in the output does not appear contiguously here.
#: Joined before matching, or a test asserting the WORDING silently checks the
#: line wrapping instead.
JOINED = re.sub(r'"\s*\n\s*"', "", SRC)


def _refusal_block() -> str:
    return SRC[SRC.index("if refusing:"):SRC.index("if refusing:") + 1400]


def test_A_BLOCKING_REASON_ON_A_RETAINED_PAGE_REFUSES_THE_PROMOTE():
    """The whole finding. Eight `severity: block` reasons promoted."""
    assert "retained_pages_fail_current_gates" in SRC
    block = _refusal_block()
    assert "conn.rollback()" in block, (
        "the refusal must roll back; a partial promote is worse than either "
        "outcome and invariant 3 says all six pages or none")
    assert '"promoted": False' in block


def test_the_refusal_is_driven_by_severity_not_by_the_reason_merely_existing():
    """Non-blocking reasons must still disclose without refusing, or every
    advisory note becomes a promotion blocker and the gate set ossifies."""
    assert 'r.get("severity") == "block"' in SRC


def test_SAFEGUARDS_STILL_DISCLOSE_AND_PROMOTE():
    """Charter invariant 12, and the one documented exception. An SG that
    fails renders to the client with its reason; it does not strand the run."""
    assert 'startswith("SG")' in SRC
    seg = SRC[SRC.index('r.get("severity") == "block"'):]
    seg = seg[:seg.index("if refusing:")]
    assert "not str(r.get" in seg and 'startswith("SG")' in seg, (
        "the SG exclusion is not applied to the refusal predicate")


def test_A_CRASHED_REVALIDATION_REFUSES_RATHER_THAN_PASSES():
    """CHECK_NEVER_RAN_READS_AS_UNKNOWN. The old code caught the exception
    with `# never block a promote` and continued, so a re-validation that blew
    up on a page was indistinguishable from one that found the page clean —
    and the crashing page promoted."""
    # The except branch ONLY. Reading to `if refusing:` runs past it into the
    # `if now:` branch, which assigns `refusing[page]` too — so the assertion
    # passed no matter what the crash path did. Caught by mutation: deleting
    # the crash branch's assignment killed nothing.
    seg = SRC[SRC.index("except Exception as exc"):]
    seg = seg[:seg.index("continue")]
    assert "refusing[page]" in seg, (
        "a re-validation that raised must refuse; an unknown state is not a "
        "clean state")
    assert "never block a promote" not in seg


def test_the_refusal_names_the_pages_and_only_those():
    """The repair has to be obvious and cheap, or the refusal reads as a wall.
    Naming the pages is what makes resubmit-one-page actionable."""
    block = _refusal_block()
    assert '"pages": sorted(refusing)' in block
    assert '"reasons": refusing' in block
    hint = JOINED[JOINED.index('"hint": ('):JOINED.index('"hint": (') + 700]
    assert "Resubmit each page named" in hint
    assert "only those" in hint, (
        "the hint must say the other pages' retained rows are still good, or "
        "a reader assumes a full re-synthesis")


def test_stale_verdicts_is_still_reported_for_pages_that_do_not_refuse():
    """An SG reason, or a non-blocking one, still has to be visible. Removing
    the disclosure while adding the refusal would trade one blind spot for
    another."""
    assert "stale_verdicts[page] = now[:8]" in SRC
    assert '"stale_verdicts"' in SRC


def test_the_refusal_happens_before_anything_is_written():
    """Ordering matters: the check must precede the serving-table writes, or
    the rollback is doing work that a check could have avoided and any
    non-transactional side effect has already escaped."""
    assert SRC.index("if refusing:") < SRC.index("UPDATE submissions SET promoted_at")
