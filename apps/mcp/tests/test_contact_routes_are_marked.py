"""CG-37 — a way to reach a named person is marked, or it reaches the client.

Invariant 5 says audience redaction is server-side and default-deny. The
default-deny part is true of SECTIONS (`CUSTOMER_WITHHELD`); it is not true of
FIELDS. `redaction.py` strips the paths a section lists in `internal_only` and
serves the paths it does not, so at field grain the default is PUBLISH. The
contract has always said so — "Marking is the producer's duty: a path you do
not mark reaches the client" — and has only ever required the field to exist,
never checked what is in it.

Harmless while every contact column was null. On 2026-08-22 a re-polled Clay
task put five named executives' work addresses and LinkedIn profiles onto a
promoted roster, and the distance between that and publishing them became one
forgotten list entry.

Scoped to a route BESIDE A NAME. A published switchboard number on a
firmographics card is a company's contact detail; the same column next to
"Rob Sharps" is a person's.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))

from dma_mcp.gates import GATES                                     # noqa: E402
from dma_mcp.validation import (_CONTACT_ROUTE_FIELDS,              # noqa: E402
                                _check_contact_routes_are_marked as marked)

FIELDS = ("email", "linkedin_url", "phone", "enriched_at", "enrichment_basis")


def _roster(n, *, mark=True, **over):
    seats, marks = [], []
    for i in range(n):
        seats.append({"name": f"Person {i}", "title": "Chief Something",
                      "email": f"p{i}@example.test",
                      "linkedin_url": f"https://www.linkedin.com/in/p{i}/",
                      "phone": None, **over})
        if mark:
            marks += [f"roster[{i}].{f}" for f in FIELDS]
    return {"roster": seats, "internal_only": marks}


# ── the leak ──


def test_an_unmarked_route_is_refused():
    body = _roster(1, mark=False)
    out = marked("leadership", body)
    assert len(out) == 1
    assert out[0]["path"] == "leadership.internal_only"
    assert "roster[0].email" in out[0]["message"]
    assert "roster[0].linkedin_url" in out[0]["message"]


def test_one_forgotten_seat_among_six_is_caught():
    """The realistic shape: a roster gains a seat and nobody re-checks the
    marks. Five seats marked, one not."""
    body = _roster(6)
    body["internal_only"] = [p for p in body["internal_only"]
                             if not p.startswith("roster[4]")]
    out = marked("leadership", body)
    assert len(out) == 1
    assert "roster[4].email (Person 4)" in out[0]["message"]
    assert "roster[3]" not in out[0]["message"], "the marked seats are not flagged"


def test_a_partially_marked_seat_is_caught():
    """Marking the email and forgetting the profile is the likeliest slip of
    all, and the profile is the more identifying of the two."""
    body = _roster(1)
    body["internal_only"] = ["roster[0].email"]
    out = marked("leadership", body)
    assert "roster[0].linkedin_url" in out[0]["message"]
    assert "roster[0].email" not in out[0]["message"]


def test_every_unmarked_path_is_named_not_just_the_first():
    body = _roster(3, mark=False)
    msg = marked("leadership", body)[0]["message"]
    assert "6 contact routes" in msg
    for i in range(3):
        assert f"roster[{i}].email" in msg


def test_a_long_list_says_how_many_it_did_not_show():
    body = _roster(8, mark=False)
    msg = marked("leadership", body)[0]["message"]
    assert "16 contact routes" in msg
    assert "and 10 more" in msg


# ── what must NOT be refused ──


def test_a_fully_marked_roster_passes():
    assert marked("leadership", _roster(6)) == []


def test_a_roster_with_no_routes_passes():
    """The state every client was in until this week. CG-28 keeps the person
    on the page without a route; this gate must not argue with that."""
    body = {"roster": [{"name": "Person 0", "title": "Chief Something",
                        "email": None, "linkedin_url": None, "phone": None}],
            "internal_only": []}
    assert marked("leadership", body) == []


def test_a_company_phone_with_no_person_beside_it_is_out_of_scope():
    """A published switchboard on a firmographics card is the company's own
    contact detail, not personal data."""
    assert marked("firmographics", {
        "fields": {"phone": "+1 410 345 2000", "hq": "Baltimore, MD"},
        "internal_only": []}) == []


def test_a_gap_seat_carrying_no_name_is_out_of_scope():
    """A gap row names the ROLE that is missing and has no person to protect."""
    assert marked("leadership", {
        "roster": [{"name": "-", "title": "Chief Information Security Officer",
                    "email": None}],
        "internal_only": []}) == []


def test_blank_values_are_not_routes():
    body = {"roster": [{"name": "Person 0", "email": "   ", "phone": ""}],
            "internal_only": []}
    assert marked("leadership", body) == []


def test_non_dict_bodies_are_ignored():
    assert marked("leadership", None) == [] and marked("leadership", []) == []


# ── the field list is the one redaction and CG-32 use ──


def test_it_covers_exactly_the_route_fields_migration_0018_binds():
    assert _CONTACT_ROUTE_FIELDS == ("email", "linkedin_url", "phone")


def test_it_works_at_any_depth():
    """Keyed off "a dict with a name and a route", not off the roster's shape,
    so a nested contact block is covered too."""
    out = marked("insights", {"cards": [{"owner": {
        "name": "Person X", "email": "x@example.test"}}],
        "internal_only": []})
    assert len(out) == 1
    assert "cards[0].owner.email" in out[0]["message"]


# ── registered and wired ──


def test_the_gate_is_registered_and_blocks():
    assert "CG-37" in GATES
    assert GATES["CG-37"][-1] == "block"


def test_the_check_is_wired_into_the_dispatch():
    """Every test above calls the check directly and would stay green with it
    unwired. Asserted over the AST — the name appears in its own def and
    docstring, so a substring check would pass on an unwired file."""
    import ast
    src = (ROOT / "apps" / "mcp" / "dma_mcp" / "validation.py").read_text(encoding="utf-8")
    called = {getattr(n.func, "id", None) for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.Call)}
    assert "_check_contact_routes_are_marked" in called
