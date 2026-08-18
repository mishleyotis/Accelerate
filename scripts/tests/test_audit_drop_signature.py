"""The drop check whose arithmetic was backwards.

`check_drop_signature` flags a field null on 100% of its rows, and the
arithmetic IS the finding: a producer short of data leaves a scatter, a perfect
column means something else. That only works if the denominator is the number
of ROWS.

It was the number of null LEAF YIELDS. `walk` descends into a populated list
or dict instead of yielding it, so a row whose value is present never reaches
the counter — and `n == t` became true by construction for every partially
populated column. Measured on the reference client:
`.techstack.data.items[].peer_deployments` is populated on 8 of 51 rows and the
check reported "null on 43/43 rows — every one". "Every one" was true only of a
set selected BY being null.

Counting the last `[i]` instead fails the other way on nested shapes, because
the inner index restarts inside each outer row: `platforms[].gaps[].gap` read
18 nulls against 5 rows. A SET of concrete container paths is the only count
that survives both.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "audit_promoted_client", ROOT / "scripts" / "audit_promoted_client.py")
au = importlib.util.module_from_spec(_spec)
sys.modules["audit_promoted_client"] = au
_spec.loader.exec_module(au)

N = au.DROP_MIN_ROWS


def _paths(findings):
    return {f["path"] for f in findings}


def test_a_wholly_null_column_is_still_flagged():
    body = {"s": {"data": {"rows": [{"a": 1, "b": None} for _ in range(N + 2)]}}}
    out = au.check_drop_signature("p", body)
    assert ".s.data.rows[].b" in _paths(out)


def test_a_PARTIALLY_populated_column_is_not_flagged():
    """The false positive. One populated row is a scatter, not a drop."""
    rows = [{"a": 1, "b": None} for _ in range(N + 2)]
    rows[0]["b"] = "present"
    out = au.check_drop_signature("p", {"s": {"data": {"rows": rows}}})
    assert ".s.data.rows[].b" not in _paths(out)


def test_a_column_populated_with_a_LIST_still_counts_as_populated():
    """The exact production shape: `peer_deployments` is a list of objects on
    8 rows and null on 43. `walk` descends into the list, so those 8 rows were
    invisible and the column read as 100% null."""
    rows = [{"vendor": f"v{i}", "peer_deployments": None} for i in range(43)]
    rows += [{"vendor": f"w{i}", "peer_deployments": [{"peer": "X"}]}
             for i in range(8)]
    out = au.check_drop_signature("p", {"s": {"data": {"items": rows}}})
    assert ".s.data.items[].peer_deployments" not in _paths(out), (
        "a column populated on 8 of 51 rows is not a dropped column")


def test_a_nested_row_counts_against_its_OWN_container():
    """`platforms[].gaps[].gap` — the inner index restarts inside each outer
    row, so an index-derived count under-counts and n > t. Every reported
    finding must satisfy n == t; anything else is a bug in this check rather
    than a finding about the client."""
    platforms = [{"name": f"p{i}",
                  "gaps": [{"gap": None, "id": f"{i}-{j}"} for j in range(4)]}
                 for i in range(5)]
    out = au.check_drop_signature("p", {"s": {"data": {"platforms": platforms}}})
    hit = [f for f in out if f["path"].endswith("gaps[].gap")]
    assert hit, "20 null gaps across 5 platforms is still a perfect column"
    assert hit[0]["rows_null"] == hit[0]["rows_total"] == 20


def test_every_finding_has_a_self_consistent_count():
    rows = [{"a": None, "b": i, "c": {"d": None}} for i in range(N + 3)]
    for f in au.check_drop_signature("p", {"s": {"data": {"rows": rows}}}):
        assert f["rows_null"] == f["rows_total"], f


def test_it_does_not_assert_a_cause_it_cannot_observe():
    """The message used to state the value 'is being lost between the producer
    and the reader'. Attributed against staging, 30 of 32 were producer-side —
    the field was never written. An audit that names the wrong layer sends the
    next person hunting in it."""
    body = {"s": {"data": {"rows": [{"b": None} for _ in range(N + 2)]}}}
    msg = au.check_drop_signature("p", body)[0]["message"]
    assert "is being lost between" not in msg
    assert "SIGNATURE, not the cause" in msg
    assert "get_staged_payload" in msg, (
        "name the tool that settles which half to look in")


def test_a_short_list_is_below_the_floor():
    """Two null rows is not a signature; it is two rows."""
    body = {"s": {"data": {"rows": [{"b": None}, {"b": None}]}}}
    assert au.check_drop_signature("p", body) == []


# ── attributed absence: stated basis downgrades to WARN, never silence ─
def _rows(basis=None, section_basis=None):
    rows = [{"pillar_id": f"P{i}", "score": 1.5, "peer_median": None,
             **({"peer_basis": basis} if basis else {})} for i in range(1, 5)]
    body = {"scores": {"data": {"pillars": rows}}}
    if section_basis:
        body["scores"]["data"]["empty_state"] = {"reason": section_basis}
    return body


def test_a_stated_row_basis_downgrades_the_drop_to_a_warn():
    from audit_promoted_client import check_drop_signature
    out = check_drop_signature("overview", _rows(basis="cannot_estimate"))
    drops = [v for v in out if ".peer_median" in str(v)]
    assert drops and all(d["level"] == "WARN" for d in drops), drops


def test_an_UNATTRIBUTED_perfect_column_still_blocks():
    """The negative control that decides whether the exemption can be
    trusted: with no basis anywhere, the drop signature is what it was."""
    from audit_promoted_client import check_drop_signature
    out = check_drop_signature("overview", _rows())
    drops = [v for v in out if ".peer_median" in str(v)]
    assert drops and all(d["level"] == "BLOCKER" for d in drops), drops


def test_a_section_basis_must_NAME_the_absent_value():
    """'peer' prose does not excuse a null fit_score — a basis that names
    nothing attributes nothing."""
    from audit_promoted_client import check_drop_signature
    body = {"platform_story": {"data": {
        "empty_state": {"reason": "Peer scoring is a pending phase."},
        "platforms": [{"platform": f"X{i}", "fit_score": None}
                      for i in range(4)]}}}
    out = check_drop_signature("platform", body)
    drops = [v for v in out if ".fit_score" in str(v)]
    assert drops and all(d["level"] == "BLOCKER" for d in drops), drops


def test_a_section_basis_that_names_the_value_attributes_it():
    from audit_promoted_client import check_drop_signature
    body = {"platform_story": {"data": {
        "empty_state": {"reason": "The platform fit engine returned no rows "
                                  "for this run, so every fit_score is null "
                                  "rather than estimated."},
        "platforms": [{"platform": f"X{i}", "fit_score": None}
                      for i in range(4)]}}}
    out = check_drop_signature("platform", body)
    drops = [v for v in out if ".fit_score" in str(v)]
    assert drops and all(d["level"] == "WARN" for d in drops), drops


# ── invariant 9: an event that has not happened has a null date ────────
def _issues(status="OPEN", resolved=None):
    return {"issue_register": {"data": {"issues": [
        {"issue_id": f"IR-{i}", "status": status, "severity": "HIGH",
         "resolved_on": resolved} for i in range(3)]}}}


def test_a_null_date_on_open_rows_is_the_event_not_happening():
    from audit_promoted_client import check_drop_signature
    out = check_drop_signature("context", _issues(status="OPEN"))
    drops = [v for v in out if ".resolved_on" in str(v)]
    assert drops and all(d["level"] == "WARN" for d in drops), drops


def test_a_null_date_on_TERMINAL_rows_is_still_a_drop():
    """A RESOLVED issue with no resolved_on is exactly the lost value the
    check exists for — the negative control on the invariant-9 exemption."""
    from audit_promoted_client import check_drop_signature
    out = check_drop_signature("context", _issues(status="RESOLVED"))
    drops = [v for v in out if ".resolved_on" in str(v)]
    assert drops and all(d["level"] == "BLOCKER" for d in drops), drops


# ── the connector's own carrier: r_layer.probes_run names the leaf ─────
def test_probes_run_naming_the_full_leaf_attributes_it():
    from audit_promoted_client import check_drop_signature
    body = {"techstack": {"data": {
        "r_layer": {"probes_run": [
            "peer_coverage and peer_deployments are null on every row: the "
            "peer technographic pass is a recorded pending phase."]},
        "items": [{"product": f"X{i}", "peer_coverage": None}
                  for i in range(4)]}}}
    out = check_drop_signature("techstack", body)
    drops = [v for v in out if ".peer_coverage" in str(v)]
    assert drops and all(d["level"] == "WARN" for d in drops), drops


def test_probes_run_NOT_naming_the_leaf_does_not_attribute():
    from audit_promoted_client import check_drop_signature
    body = {"techstack": {"data": {
        "r_layer": {"probes_run": ["peer work is pending."]},
        "items": [{"product": f"X{i}", "peer_coverage": None}
                  for i in range(4)]}}}
    out = check_drop_signature("techstack", body)
    drops = [v for v in out if ".peer_coverage" in str(v)]
    assert drops and all(d["level"] == "BLOCKER" for d in drops), drops
