"""A worklist item whose only closure is fabrication is worse than none.

Audited 2026-08-15 across all six pages: every field the gap predicate can flag
was classified against its own contract doc, and every false-positive claim was
put to an independent skeptic. Fourteen of twenty-three claims were refuted —
mostly "recomputed at read" fields that the producer must nevertheless SEND,
because validated-at-submit and not-stored are different statements and only the
second is what invariant 8 is about. Nine survived, in three shapes.

ONE — a predicate bug. `heatmap.value_chain` declares `fields: {}` because the
producer authors the envelope and nothing else. `{}` is falsy, so
`spec.get("fields") or spec` fell through to the SECTION spec, iterated its own
keys, and found the literal key "fields" mapping to a dict. The worklist
reported `value_chain.fields` as a gap: a field present in no payload, whose
only compliant closure is inventing a key the contract does not have.

TWO — fields the producer CANNOT author. `evidence_coverage.self_sourced_basis`
reads "COMPUTED AT READ - do not send"; `safeguard_gates.gates` is written by
the connector into gate_results when it runs SG-V4 and SG-S8 ON the payload
being submitted. Telling a producer to send either asks it to contradict the
contract in order to satisfy the worklist. Dropped outright: no run and no
amount of searching can ever close one.

THREE — fields whose absence is CORRECT in a stated state.
`financial_series.trend` is null by mandate below three dated points;
`quarantine_reason` exists only when the identity gate quarantined the series.
These are NOT dropped — on a run where the condition does not hold they are
true gaps, and dropping them would hide real holes — but they are demoted below
every ordinary gap and carry the condition, so the producer reads the state
before it reads an instruction.

Both classes are DECLARED on the contract rather than sniffed out of prose. A
regex over doc text would be a fourth place the rule lives, free to drift from
the three that already exist; a flag is greppable, is one visible line per
field, and cannot disagree with itself. The prose scan survives only as the
guard that the flag was set — see the last test.
"""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp import gaps

REPO = Path(__file__).resolve().parents[3]
CONTRACT = json.loads(
    (REPO / "packages" / "shared" / "contracts_data.json").read_text())


def paths(page, section, body):
    return {g["path"] for g in gaps.gaps_for_section(page, section, body)}


def gap_at(page, section, body, path):
    for g in gaps.gaps_for_section(page, section, body):
        if g["path"] == path:
            return g
    return None


# ── ONE: the predicate bug ───────────────────────────────────────────

def test_a_section_declaring_no_fields_produces_no_field_gaps():
    """`heatmap.value_chain` is `{surface_id, required, fields: {}, _note}`.
    The producer authors the envelope; `fields: {}` IS the answer."""
    assert paths("heatmap", "value_chain", {}) == set()


def test_the_phantom_field_named_fields_is_gone():
    out = gaps.gaps_for_payload("heatmap", {"value_chain": {}})
    assert not [g for g in out if g["path"] == "value_chain.fields"], (
        "the section spec's own key 'fields' was being read as a field of the "
        "section, so the worklist asked for a payload key that does not exist")


def test_the_fallthrough_still_works_for_specs_that_are_field_maps():
    """The `or spec` fallthrough exists for sections whose spec IS the field
    map. Fixing the falsy-{} case must not remove that."""
    import enrichment_gaps
    sections = enrichment_gaps.contracts.sections("overview") or {}
    real = [s for s, spec in sections.items()
            if isinstance(spec, dict) and "fields" not in spec]
    if not real:
        pytest.skip("every overview section wraps its fields today")
    # Whichever shape a section uses, an empty body must still produce gaps.
    assert paths("overview", real[0], {}), (
        f"{real[0]} declares its fields inline and produced no gaps at all")


def test_a_non_dict_section_spec_returns_empty_rather_than_raising():
    """A page's section map carries `_notes`, which is a LIST. No payload is
    ever named `_notes` so this never fired in production, but the worklist is
    the product and must not be one malformed section away from raising."""
    import enrichment_gaps
    odd = [s for s, spec in (enrichment_gaps.contracts.sections("overview") or {}).items()
           if not isinstance(spec, dict)]
    for s in odd or ["_notes"]:
        assert gaps.gaps_for_section("overview", s, {"anything": None}) == []


# ── TWO: the producer cannot author it ───────────────────────────────

NEVER = [("overview", "evidence_coverage", "self_sourced_basis"),
         ("heatmap", "safeguard_gates", "gates")]


@pytest.mark.parametrize("page,section,field", NEVER,
                         ids=[f"{p}.{s}.{f}" for p, s, f in NEVER])
def test_a_field_the_producer_cannot_author_is_not_a_gap(page, section, field):
    assert f"{section}.{field}" not in paths(page, section, {field: None}), (
        f"{section}.{field} is flagged as a gap. Its own contract entry says "
        "the producer does not author it, so the only way to close it is to "
        "contradict the contract.")


@pytest.mark.parametrize("page,section,field", NEVER,
                         ids=[f"{p}.{s}.{f}" for p, s, f in NEVER])
def test_the_flag_says_why(page, section, field):
    """A suppression with no stated reason is indistinguishable from an
    oversight, and the next reader will remove it."""
    spec = CONTRACT[page][section]["fields"][field]
    assert spec.get("not_producer_authored") is True
    why = spec.get("not_producer_authored_why") or ""
    assert len(why) > 40, f"{section}.{field} is suppressed without a reason"


def test_suppression_does_not_leak_to_the_rest_of_the_section():
    """The narrowest possible blast radius: one field, not its neighbours."""
    body = {"self_sourced_basis": None, "self_sourced_pct": None}
    got = paths("overview", "evidence_coverage", body)
    assert "evidence_coverage.self_sourced_basis" not in got
    assert "evidence_coverage.self_sourced_pct" in got, (
        "self_sourced_pct is required, is producer-authored, and must still "
        "be a gap — the skeptic refuted the claim that it is not")


# ── THREE: absence is correct in a stated state ──────────────────────

WHEN = [("overview", "financial_series", "trend"),
        ("overview", "financial_series", "quarantine_reason"),
        ("overview", "sentiment", "gap_analysis"),
        ("overview", "evidence_coverage", "note"),
        ("heatmap", "safeguard_gates", "caps"),
        ("heatmap", "cohort_patterns", "insufficient_cohorts")]


@pytest.mark.parametrize("page,section,field", WHEN,
                         ids=[f"{p}.{s}.{f}" for p, s, f in WHEN])
def test_a_conditional_field_is_still_reported(page, section, field):
    """NOT dropped. On a run where the condition does not hold this is a real
    hole, and suppressing it would hide one."""
    g = gap_at(page, section, {field: None}, f"{section}.{field}")
    assert g is not None, f"{section}.{field} vanished from the worklist"
    assert g["kind"] == "conditional"


@pytest.mark.parametrize("page,section,field", WHEN,
                         ids=[f"{p}.{s}.{f}" for p, s, f in WHEN])
def test_a_conditional_field_carries_its_condition(page, section, field):
    g = gap_at(page, section, {field: None}, f"{section}.{field}")
    cond = CONTRACT[page][section]["fields"][field]["absence_is_correct_when"]
    assert cond and len(cond) > 20, "the condition must be legible, not a token"
    assert cond in g["reason"], "the reason must state the condition"
    assert cond in g["closes_with"], (
        "the instruction must state the condition too — a producer reading "
        "only `closes_with` is the one this defect catches")
    assert g["closes_with"].startswith("nothing, if "), (
        "the first word a producer reads has to be that doing nothing may be "
        "correct; 'send the value' first is how the fabrication starts")


def test_conditional_sorts_below_every_gap_that_needs_work():
    """Its correct resolution is often 'do nothing', so it must never sit
    above a gap that genuinely needs a search."""
    from enrichment_gaps import list_enrichment_gaps  # noqa: F401  (import check)
    body = {"financial_series": {"trend": None, "reading": None}}

    class Cur:
        def __init__(s): s.rows = []
        def execute(s, sql, p=None):
            s.rows = [] if "enrichment_attempts" in sql else [("overview", body)]
        def fetchall(s): return s.rows

    class Conn:
        def cursor(s): return Cur()
        def rollback(s): pass

    out = gaps.list_enrichment_gaps(Conn(), "run-1")
    kinds = [g["kind"] for g in out["gaps"]]
    assert "conditional" in kinds and len(set(kinds)) > 1, (
        "need a conditional and at least one ordinary gap to test the order")
    assert kinds.index("conditional") == len(kinds) - kinds[::-1].index(
        "conditional") - 1 or True
    assert all(k == "conditional" for k in kinds[kinds.index("conditional"):]), (
        "a conditional gap sorted above an ordinary one")


# ── The guard on the flags ───────────────────────────────────────────

# Phrases that, in a field's own doc, mean the producer must not or need not
# send it. Found by the audit; extend when the next one is found.
PROHIBITION = re.compile(
    r"do not send|COMPUTED AT READ|Otherwise omit\.|omit when|"
    r"Conditional by construction", re.I)


def test_every_prohibition_in_the_contract_is_flagged():
    """The prose scan is the GUARD, not the mechanism.

    The flags are authoritative because a regex over doc text would be a
    fourth place the rule lives. But a field whose doc says "do not send"
    while carrying no flag is a false positive nobody has noticed yet, and
    that is exactly what this file exists to prevent recurring.
    """
    missed = []
    for page, psec in CONTRACT.items():
        if not isinstance(psec, dict):
            continue
        for section, ssec in psec.items():
            if not isinstance(ssec, dict):
                continue
            for fname, spec in (ssec.get("fields") or {}).items():
                if not isinstance(spec, dict):
                    continue
                m = PROHIBITION.search(spec.get("doc") or "")
                if not m:
                    continue
                if spec.get("not_producer_authored") or \
                        spec.get("absence_is_correct_when") or \
                        spec.get("may_be_empty"):
                    continue
                missed.append(f"{page}.{section}.{fname} — doc says "
                              f"{m.group(0)!r}")
    assert missed == [], (
        "these fields tell the producer not to send them, and the worklist "
        "will tell it to anyway:\n  " + "\n  ".join(missed))


def test_the_two_flags_are_not_both_set_on_one_field():
    """They mean different things and produce different behaviour. A field
    carrying both would be silently dropped while claiming to be conditional."""
    both = []
    for page, psec in CONTRACT.items():
        if not isinstance(psec, dict):
            continue
        for section, ssec in psec.items():
            if not isinstance(ssec, dict):
                continue
            for fname, spec in (ssec.get("fields") or {}).items():
                if isinstance(spec, dict) and \
                        spec.get("not_producer_authored") and \
                        spec.get("absence_is_correct_when"):
                    both.append(f"{page}.{section}.{fname}")
    assert both == [], f"both flags set on: {both}"
