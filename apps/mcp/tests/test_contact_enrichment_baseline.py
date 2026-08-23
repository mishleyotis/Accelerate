"""CG-41 — every roster seat records what the contact search found.

Owner, 2026-08-23, reading a promoted run: "Clay enrichment for Gulf has no
emails. Is the baseline for contact enrichment established?"

It was not, and the gap was exactly shaped: CG-37 makes sure a route that
EXISTS is marked internal_only, and CG-40 sets depth floors for sentiment,
why_now and techstack. Nothing said what contact enrichment owes PER SEAT. So
a roster with no emails because Clay searched and matched nothing, and a
roster with no emails because Clay was never called, were the same payload —
and Gulf was the second (7 of 7 facets never_enriched) and promoted anyway.

THE BASELINE IS THE SEARCH, NOT THE EMAIL. A private company's CFO may have
no reachable address anywhere; that run must still promote. So every test
below that expects a PASS is testing the escape, and the escape is the point:
a gate satisfiable only by data the world may not hold is a gate that teaches
producers to refuse packages, which is the failure this system has already
paid for. What CG-41 refuses is a seat about which nothing at all is said.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation2 import (          # noqa: E402
    CONTACT_BASIS_KEYS, CONTACT_ROUTE_KEYS, _check_contact_enrichment_baseline,
    _seat_contact_state)

BASIS = ("LinkedIn profile https://www.linkedin.com/in/example/ — name AND "
         "title matched the roster entry exactly.")
NEGATIVE = ("The enrichment search returned no profile whose TITLE matched "
            "this person; a name-similar match is an identity failure.")


def payload(roster, **section):
    return {"leadership": {"roster": roster, **section}}


def run(roster, **section):
    return _check_contact_enrichment_baseline("overview", payload(roster, **section))


def ids(out):
    return [r["gate_id"] for r in out]


# ── the three seat states ─────────────────────────────────────────────

def test_a_route_with_a_basis_is_resolved():
    assert _seat_contact_state(
        {"name": "A", "email": "a@example.org", "enrichment_basis": BASIS}
    ) == "resolved"


def test_a_recorded_negative_is_not_a_failure():
    """The seat that carries no address and says why. This is the state the
    gate exists to make expressible — without it the honest answer and the
    unrun tool look identical."""
    assert _seat_contact_state(
        {"name": "B", "enrichment_basis": NEGATIVE}) == "recorded_negative"


def test_a_route_with_no_basis_is_unknown_not_resolved():
    """Measured on Logix: 4 of 7 roster rows carried a linkedin_url with
    enrichment_basis null — a value on the page and no answer to 'from
    where'. That is unattributed, not resolved, and counting it as resolved
    would let the exact shape that prompted this gate through it."""
    assert _seat_contact_state(
        {"name": "C", "linkedin_url": "https://linkedin.com/in/c"}) == "unknown"


def test_a_bare_seat_is_unknown():
    assert _seat_contact_state({"name": "D", "title": "CFO"}) == "unknown"


def test_a_token_is_not_a_basis():
    """'n/a', 'none', 'Clay' — a token cannot distinguish a search that ran
    from one that did not, which is the only question being asked. The
    rulebook says it directly: 'Clay reports it' is not a source."""
    for token in ("n/a", "none", "Clay", "-", "not found", "TBD"):
        assert _seat_contact_state({"name": "E", "enrichment_basis": token}) \
            == "unknown", token


def test_every_documented_basis_key_is_read():
    """The contract's field is `enrichment_basis`; the others are shapes
    promoted runs actually used. Reading them is deliberate — declaring a
    real payload wrong after the fact strands a run that did the work."""
    for k in CONTACT_BASIS_KEYS:
        assert _seat_contact_state({"name": "F", k: NEGATIVE}) \
            == "recorded_negative", k


def test_every_documented_route_key_is_seen():
    """A key this list forgets is a route the gate cannot see while redaction
    still has to strip it — the two vocabularies have to stay one."""
    for k in CONTACT_ROUTE_KEYS:
        assert _seat_contact_state({"name": "G", k: "x@example.org",
                                    "enrichment_basis": BASIS}) == "resolved", k


# ── the gate ──────────────────────────────────────────────────────────

def test_a_fully_resolved_roster_passes():
    assert run([{"name": "A", "email": "a@x.org", "enrichment_basis": BASIS},
                {"name": "B", "linkedin_url": "u", "enrichment_basis": BASIS}]) == []


def test_a_roster_of_recorded_negatives_passes():
    """Zero emails, and it promotes. This is the case the owner asked about
    and the answer the gate gives: no addresses is fine, silence is not."""
    assert run([{"name": "A", "enrichment_basis": NEGATIVE},
                {"name": "B", "enrichment_basis": NEGATIVE},
                {"name": "C", "enrichment_basis": NEGATIVE}]) == []


def test_a_mixed_roster_passes():
    assert run([{"name": "A", "email": "a@x.org", "enrichment_basis": BASIS},
                {"name": "B", "enrichment_basis": NEGATIVE}]) == []


def test_the_gulf_shape_is_refused():
    """No route, no basis, nothing — the state a roster is in when the
    enrichment never ran."""
    out = run([{"name": "A", "title": "CEO"},
               {"name": "B", "title": "CFO"},
               {"name": "C", "title": "CIO"}])
    assert ids(out) == ["CG-41"]
    assert out[0]["severity"] == "block"
    assert "3 of 3" in out[0]["message"]


def test_one_unknown_seat_among_good_ones_is_named_by_index():
    """A producer told only that 'something is unmarked' on a six-seat roster
    has fifteen fields to check by hand — CG-37 learned that and names each
    path. This does the same."""
    out = run([{"name": "A", "email": "a@x.org", "enrichment_basis": BASIS},
               {"name": "B", "enrichment_basis": NEGATIVE},
               {"name": "C", "title": "CIO"}])
    assert ids(out) == ["CG-41"]
    assert "roster[2]" in out[0]["message"]
    assert "roster[0]" not in out[0]["message"]
    assert "1 of 3" in out[0]["message"]


def test_the_counts_are_reported_so_a_producer_can_see_the_shape():
    out = run([{"name": "A", "email": "a@x.org", "enrichment_basis": BASIS},
               {"name": "B", "enrichment_basis": NEGATIVE},
               {"name": "C"}, {"name": "D"}])
    assert "1 resolved with a basis, 1 recorded a negative" in out[0]["message"]


def test_a_long_roster_truncates_the_index_list_but_never_the_count():
    out = run([{"name": f"P{i}"} for i in range(20)])
    assert "20 of 20" in out[0]["message"]
    assert "+8 more" in out[0]["message"]


def test_the_message_names_the_way_out():
    """A producer told only NO cannot act. Every refusal in this build carries
    the route through it."""
    out = run([{"name": "A"}])
    m = out[0]["message"]
    assert "enrichment_basis" in m
    assert "matched nothing" in m
    assert "empty_state" in m or "thin" in m


# ── the section-level escape ──────────────────────────────────────────

def test_a_section_that_says_the_pass_did_not_run_passes():
    """Thinness that discloses is honest. The refusal is silence."""
    assert run([{"name": "A"}, {"name": "B"}],
               thin=True,
               empty_state={"reason": "The contact pass did not run for this "
                                      "entity; no roster seat was searched.",
                            "sources_searched": ["clay", "linkedin"]}) == []


def test_a_bare_thin_boolean_does_not_buy_the_escape():
    """`thin: true` alone is an assertion. The same rule CG-40 already keeps:
    a boolean with nothing travelling beside it is not a disclosure."""
    out = run([{"name": "A"}, {"name": "B"}], thin=True)
    assert ids(out) == ["CG-41"]


def test_a_two_word_empty_state_does_not_buy_the_escape():
    out = run([{"name": "A"}], empty_state="not run")
    assert ids(out) == ["CG-41"]


# ── scope ─────────────────────────────────────────────────────────────

def test_no_other_page_is_touched():
    for page in ("platform", "heatmap", "context", "techstack", "insights"):
        assert _check_contact_enrichment_baseline(
            page, payload([{"name": "A"}])) == []


def test_a_missing_or_empty_roster_is_a_different_finding():
    """An absent leadership section, or one with no people in it, is not this
    gate's business — inventing a contact finding out of no roster would be a
    derived value that is neither computed nor null."""
    assert _check_contact_enrichment_baseline("overview", {}) == []
    assert _check_contact_enrichment_baseline("overview", {"leadership": {}}) == []
    assert run([]) == []


def test_the_nested_data_envelope_is_read():
    """Sections arrive both bare and wrapped in `data`; a gate that reads only
    one shape passes the other by doing nothing."""
    out = _check_contact_enrichment_baseline(
        "overview", {"leadership": {"data": {"roster": [{"name": "A"}]}}})
    assert ids(out) == ["CG-41"]


def test_alternative_roster_container_names_are_read():
    for key in ("roster", "people", "leaders", "rows"):
        out = _check_contact_enrichment_baseline(
            "overview", {"leadership": {key: [{"name": "A"}]}})
        assert ids(out) == ["CG-41"], key


def test_a_non_dict_seat_does_not_crash_the_gate():
    out = run([{"name": "A", "email": "a@x.org", "enrichment_basis": BASIS},
               "a bare string", None, 7])
    assert ids(out) == ["CG-41"]
    assert "3 of 4" in out[0]["message"]


def test_the_gate_is_registered_with_its_family_and_severity():
    from dma_mcp.gates import GATES
    assert "CG-41" in GATES
    assert GATES["CG-41"][-1] == "block"
    why = GATES["CG-41"][3]
    assert "Gulf" in why and "baseline" in why.lower()


def test_the_refusal_quotes_the_container_it_actually_found():
    """Invariant 12: a verdict names the gate, the JSON path and the
    arithmetic. A path that says `roster` on a payload whose container is
    `people` sends the producer to a field that is not there — and the seat
    indices below it are then unreadable too.

    This is a real hazard rather than a hypothetical: `_roster_of` accepts
    four container names on purpose, because promoted payloads have used more
    than one, and the first version of the refusal hard-coded `roster` in both
    the path and every index.
    """
    for key in ("roster", "people", "leaders", "rows"):
        out = _check_contact_enrichment_baseline(
            "overview",
            {"leadership": {key: [{"name": "A", "email": "a@x.org",
                                   "enrichment_basis": BASIS},
                                  {"name": "B"}]}})
        assert ids(out) == ["CG-41"], key
        assert out[0]["path"] == f"overview.leadership.{key}", out[0]["path"]
        assert f"{key}[1]" in out[0]["message"], out[0]["message"]
        # And no other container name leaks into the message.
        for other in ("roster", "people", "leaders", "rows"):
            if other != key:
                assert f"{other}[" not in out[0]["message"], (key, other)
