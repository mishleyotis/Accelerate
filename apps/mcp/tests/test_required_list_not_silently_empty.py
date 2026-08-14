"""CG-17 — `required: true` was satisfied by an empty list.

The second root cause behind "changes do not get promoted", and the larger of
the two. `val = []` is not None, so CG-02's branch never ran; a list
type-checks fine; promotion then wrote zero rows; and the read path omits a
key with no rows. The surface DISAPPEARED from the served page with no
`empty_state` to explain it, and every gate was green.

Measured 2026-08-14 across both promoted clients, over every required list
field that is not an envelope field: exactly one content field each is empty
or absent without an empty state.

  reference client   techstack.dropped        empty  — nothing was dropped
  second client      platform.starters.starters absent — the conversation
                                                starters the build owner
                                                reported as "disappeared"

That measurement is what makes this safe to BLOCK: it fires on the real
defect and on one benign case, and the benign case is what `may_be_empty`
exists for. The tests below pin both sides.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.contracts import ENVELOPE, sections
from dma_mcp.validation import validate_pass1


def _reasons(page, payload):
    out = validate_pass1(page, payload)
    return [r for r in out if r["gate_id"] == "CG-17"]


def _platform(starters):
    """A platform payload complete enough that only `starters` is in question."""
    page = sections("platform")
    body = {}
    for sec, spec in page.items():
        s = {"produced_at": "2026-08-14T00:00:00Z", "producer_version": "t",
             "e_ids": [], "internal_only": []}
        for f, fs in (spec.get("fields") or {}).items():
            if f in ENVELOPE:
                continue
            if fs["type"] == "list":
                s[f] = [{}] if fs.get("item_type") == "object" else ["x"]
            elif fs["type"] == "object":
                s[f] = {}
            elif fs["type"] == "number":
                s[f] = 1
            elif fs["type"] == "boolean":
                s[f] = False
            else:
                s[f] = "x"
        body[sec] = s
    body["starters"]["starters"] = starters
    return body


def test_an_empty_required_list_is_refused():
    """The shape that shipped: not None, type-checks, writes nothing."""
    out = _reasons("platform", _platform([]))
    assert len(out) == 1
    r = out[0]
    assert r["severity"] == "block"
    assert r["path"] == "starters.starters"
    assert "vanishes" in r["message"] and "empty state" in r["message"]


def test_a_populated_list_passes():
    assert _reasons("platform", _platform([{"id": "S1"}])) == []


def test_an_empty_list_WITH_a_section_empty_state_passes():
    """The honest route: say there are none, and say what established it."""
    body = _platform([])
    body["starters"]["empty_state"] = {
        "kind": "verified_absent",
        "reason": "no starter could be grounded in a cited capability",
        "sources_searched": ["the run's own cited cells"]}
    assert _reasons("platform", body) == []


def test_may_be_empty_exempts_the_field_the_measurement_found():
    """`techstack.dropped` empty means nothing was dropped — the ordinary
    case, not a finding. It is the ONE field in the registry marked so, and
    that number is asserted below to keep the exemption from spreading."""
    spec = sections("techstack")["techstack"]["fields"]["dropped"]
    assert spec.get("may_be_empty") is True


def test_the_may_be_empty_exemption_has_not_spread():
    """An exemption is only as good as how rarely it is granted. If this
    count rises, the reviewer should be made to look at why."""
    n = sum(1
            for p in ("overview", "insights", "platform", "techstack",
                      "context", "heatmap")
            for s in sections(p).values()
            for f in (s.get("fields") or {}).values()
            if f.get("may_be_empty"))
    assert n == 1, f"{n} fields now claim may_be_empty; justify each"


def test_envelope_lists_are_governed_by_CG_05_not_this_gate():
    """`e_ids` and `internal_only` are legitimately empty on most sections —
    they were 48 of the 51 hits in the raw measurement, and blocking on them
    would refuse every correct payload in the corpus."""
    body = _platform([{"id": "S1"}])
    for sec in body:
        body[sec]["e_ids"] = []
        body[sec]["internal_only"] = []
    assert _reasons("platform", body) == []


def test_an_absent_required_list_is_still_CG_02_not_CG_17():
    """Absent and empty need different diagnoses because they need different
    repairs, and CG-02 already owns absent."""
    body = _platform([{"id": "S1"}])
    del body["starters"]["starters"]
    out = validate_pass1("platform", body)
    gates = {r["gate_id"] for r in out if r["path"] == "starters.starters"}
    assert gates == {"CG-02"}
