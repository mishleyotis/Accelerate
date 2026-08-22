"""CG-32 — twenty contacts were fetched, paid for, and lost.

The promoted T. Rowe Price run served six leadership seats with every contact
route null. Its own `sources_searched` said exactly why:

    "Clay contact enrichment task mcp-task_0tk3p6ia8ykw5sfVpVR — RAN and
     COMPLETED this session, 20 C-suite contacts resolved; per-contact output
     not delivered to this producer invocation, so 0 of 6"

The enrichment ran and succeeded. Its output never reached the producer.

EVERY GATE PASSED, and each half is individually legal:

  * a null contact route is a permitted absence — CG-28 exists to keep the
    person on the page when the route does not come back, and it correctly
    saw nothing wrong here because nobody was dropped;
  * naming what was searched is precisely what the contract asks for.

Only the COMBINATION is a defect, and nothing was reading both halves of the
sentence. The enrichment ledger was blind as well: `list_enrichment_gaps`
reported `attempted_by_routine: 0` for the run, so the attempt left no trace
anywhere else in the system either.

What this gate must NOT do is refuse honest thinness. A run where the tool was
never attached, or ran and resolved nothing, is a thin assessment result — and
a gate that refused it would push a producer toward inventing contact details,
which is the failure MEM-0082 exists to prevent.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))

from dma_mcp.gates import GATES                                # noqa: E402
from dma_mcp.validation import (                               # noqa: E402
    _check_resolved_contacts_are_served as check)

# The real disclosure from the promoted run, kept verbatim.
TRP_DISCLOSURE = (
    "Clay contact enrichment task mcp-task_0tk3p6ia8ykw5sfVpVR — RAN and "
    "COMPLETED this session, 20 C-suite contacts resolved; per-contact output "
    "not delivered to this producer invocation, so 0 of 6 seats carry a route.")


def _roster(n=6, **contact):
    return [{"name": f"Person {i}", "title": "chief technology officer",
             **contact} for i in range(n)]


def _body(roster, **empty_state):
    return {"roster": roster,
            "empty_state": dict(empty_state) if empty_state else None}


# ── the defect ──


def test_a_resolved_count_with_no_served_route_is_refused():
    out = check("leadership", _body(_roster(), sources_searched=[TRP_DISCLOSURE]))
    assert len(out) == 1, out
    msg = str(out[0])
    assert "20" in msg and "dropped result" in msg
    assert "6" in msg, "the message should name how many seats went unserved"


def test_the_count_is_found_in_the_reason_too():
    """Producers put the account in whichever empty_state key reads best; the
    gate reads every string the section wrote, not one blessed field."""
    out = check("leadership", _body(_roster(), reason=TRP_DISCLOSURE))
    assert len(out) == 1


def test_the_other_phrasings_are_caught():
    for text in ("resolved 14 contacts for the C-suite",
                 "the tool returned 9 contact records",
                 "12 executive contacts were resolved this session"):
        out = check("leadership", _body(_roster(), sources_searched=[text]))
        assert len(out) == 1, f"missed: {text!r}"


# ── what must NOT be refused: honest thinness ──


def test_a_tool_that_was_never_attached_passes():
    out = check("leadership", _body(_roster(), sources_searched=[
        "Clay is not attached to this session; no contact route was attempted. "
        "Recorded as not-run rather than fabricated."]))
    assert out == [], out


def test_resolving_nothing_is_an_honest_absence():
    out = check("leadership", _body(_roster(), sources_searched=[
        "Clay contact enrichment ran and 0 contacts resolved for this entity."]))
    assert out == [], out


def test_one_served_route_is_enough_to_pass():
    """The gate asks whether the resolved values reached the payload at all,
    not whether every seat got one — partial delivery is a real outcome."""
    roster = _roster(6)
    roster[0]["email"] = "someone@example.test"
    out = check("leadership", _body(roster, sources_searched=[TRP_DISCLOSURE]))
    assert out == [], out


def test_a_linkedin_or_phone_route_counts_as_served():
    for field in ("linkedin_url", "phone"):
        roster = _roster(3)
        roster[1][field] = "https://example.test/x" if field == "linkedin_url" else "+1 555 0100"
        assert check("leadership", _body(roster, sources_searched=[TRP_DISCLOSURE])) == []


def test_an_empty_string_route_is_not_a_route():
    roster = _roster(3)
    roster[0]["email"] = "   "
    out = check("leadership", _body(roster, sources_searched=[TRP_DISCLOSURE]))
    assert len(out) == 1, "whitespace is not a contact route"


def test_a_section_with_no_disclosure_is_not_this_gate_s_business():
    """Silence about enrichment is CG-28's and the ledger's problem, not a
    contradiction. This gate fires only on a stated count."""
    assert check("leadership", _body(_roster())) == []


def test_an_empty_roster_is_out_of_scope():
    assert check("leadership", _body([], sources_searched=[TRP_DISCLOSURE])) == []


def test_other_sections_are_untouched():
    assert check("financial_series", _body(_roster(), sources_searched=[TRP_DISCLOSURE])) == []


# ── the gate is registered, so a verdict can explain itself ──


def test_the_gate_is_in_the_registry_and_blocks():
    assert "CG-32" in GATES, "a reason id with no registry entry cannot explain itself"
    entry = GATES["CG-32"]
    assert entry[-1] == "block"
    assert "resolved" in entry[0].lower()


def test_the_check_is_actually_wired_into_the_dispatch():
    """A gate nobody calls is a comment.

    Every test above calls the function directly, so all twelve stay green
    with the check unwired from `validate` — verified by removing the dispatch
    line and watching them pass. The wiring is the half that makes the gate
    real, so it is asserted separately.

    Over the AST, not the text: the function's own `def` and its docstring
    both contain the name, and a substring check would match those and pass on
    an unwired file. A Call node cannot be either of those things.
    """
    import ast
    src = (ROOT / "apps" / "mcp" / "dma_mcp" / "validation.py").read_text(encoding="utf-8")
    calls = [n for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "_check_resolved_contacts_are_served"]
    assert calls, ("CG-32 is defined but never called — validate() will never "
                   "run it, and a dropped enrichment ships again")
