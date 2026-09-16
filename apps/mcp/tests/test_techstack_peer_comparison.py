"""CG-51 — a run that holds a peer set argues the techstack against it.

Reported on a promoted run: "the tech stack does not enforce peer comparison;
even the narrative itself does not include this." Golden 1 measured the shape —
56 register rows, ZERO carrying peer_deployments, and a techstack
narrative_thread that never compared the estate to a peer, yet the page passed
every gate. The T3 peer fields are declared optional on the register row
(surface-map.md:86), so an estate with a full peer set on the workbook shipped
a peer-blind techstack page and nothing said a word. AG-04 only checks a row
that ALREADY carries peer_coverage, so a peerless row is invisible to it —
present-but-optional-and-ungated, the same shape CG-44 fixed on the overview
strip.

The gate is a CASCADE like CG-44: silent unless the run demonstrably holds a
peer set — a peer with a recorded score, or a row already carrying
peer_deployments. When it does, the page owes both halves the owner named:
STRUCTURED REACH (a row carries peer_deployments) and NARRATIVE REACH (the
story mentions peers at all). The pure core takes payload dicts, so no database
is needed to prove it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dma_mcp.validation2 as V2         # noqa: E402


def find(section, peer_names=(), has_recorded_peers=None):
    """Drive the pure core. `has_recorded_peers` defaults to whether any peer
    name was supplied, which is how the connector wrapper computes it."""
    names = {V2._norm_name(n) for n in peer_names}
    if has_recorded_peers is None:
        has_recorded_peers = bool(names)
    return V2._techstack_peer_findings(section, names, has_recorded_peers)


def ids(out):
    return [r["gate_id"] for r in out]


def paths(out):
    return {r["path"] for r in out}


# A register row carrying a real peer comparison, and one that does not.
def row(product="Salesforce Financial Services Cloud", peers=None):
    r = {"product": product, "vendor": "Salesforce", "status": "CONFIRMED",
         "e_ids": ["ic:1"]}
    if peers is not None:
        r["peer_deployments"] = [{"peer": p, "runs_it": True} for p in peers]
    return r


def section(items, thread=None):
    s = {"items": items}
    if thread is not None:
        s["narrative_thread"] = thread
    return s


# ── the reported defect ───────────────────────────────────────────────

def test_a_held_peer_set_with_no_peer_deployments_anywhere_is_refused():
    """Golden 1's shape: the run holds peers, the register carries none."""
    out = find(section([row(), row("Fiserv DNA")],
                       thread="A broad, modern core estate anchored on "
                               "Salesforce and Fiserv."),
               peer_names=["Suncoast Credit Union", "VyStar"])
    assert ids(out).count("CG-51") >= 1
    assert "techstack.techstack.items[].peer_deployments" in paths(out)
    struct = next(r for r in out
                  if r["path"].endswith("items[].peer_deployments"))
    assert "2 peer(s)" in struct["message"]
    assert struct["severity"] == "block"


def test_a_held_peer_set_with_a_peer_blind_narrative_is_refused():
    """The second half of the owner's sentence: the rows compare, the story
    does not. Structured reach is satisfied here, so ONLY the narrative fires."""
    out = find(section([row(peers=["Suncoast"]), row("Fiserv DNA")],
                       thread="A broad, modern core estate anchored on "
                               "Salesforce and Fiserv, well ahead of the "
                               "sector on customer channels."),
               peer_names=["Suncoast", "VyStar"])
    assert ids(out) == ["CG-51"]
    assert paths(out) == {"techstack.techstack.narrative_thread"}
    assert "never compares the estate to a peer" in out[0]["message"]


def test_both_halves_can_fire_at_once():
    """No structured reach AND no narrative reach is the whole page failing —
    the owner named two things and both are missing on the promoted run."""
    out = find(section([row(), row("Fiserv DNA")],
                       thread="A broad, modern core estate anchored on "
                               "Salesforce and Fiserv."),
               peer_names=["Suncoast"])
    assert ids(out) == ["CG-51", "CG-51"]
    assert paths(out) == {"techstack.techstack.items[].peer_deployments",
                          "techstack.techstack.narrative_thread"}


# ── what clears it ────────────────────────────────────────────────────

def test_peer_deployments_and_a_named_peer_in_the_story_pass():
    out = find(section([row(peers=["Suncoast Credit Union"]), row("Fiserv DNA")],
                       thread="The estate is a generation behind Suncoast "
                               "Credit Union on servicing automation."),
               peer_names=["Suncoast Credit Union", "VyStar"])
    assert out == []


def test_the_word_peer_alone_carries_the_narrative_half():
    """A story that speaks to peers generically still compares — the gate asks
    for a peer comparison, not a particular peer's name."""
    out = find(section([row(peers=["Suncoast"])],
                       thread="The core estate lags its peers on real-time "
                               "payments by roughly two years."),
               peer_names=["Suncoast"])
    assert out == []


def test_benchmark_language_also_carries_the_narrative_half():
    out = find(section([row(peers=["Suncoast"])],
                       thread="Benchmarked against the cohort, the data "
                               "platform is mid-pack."),
               peer_names=["Suncoast"])
    assert out == []


def test_a_peer_named_only_on_the_row_satisfies_the_narrative_check():
    """The peer names carried inside peer_deployments enrich the narrative
    check, so a story naming a peer the register introduced still passes even
    when that peer was never in the recorded set."""
    out = find(section([row(peers=["Founders Federal"])],
                       thread="Founders Federal is two maturity bands ahead "
                               "on channel orchestration."),
               peer_names=[], has_recorded_peers=False)
    assert out == []


# ── the cascade guard: no peer set, no finding ────────────────────────

def test_a_run_with_no_peer_set_is_never_a_finding():
    """The gate invents nothing. With no recorded peer and no peer_deployments
    on any row, the run has nothing to compare against and stays silent."""
    out = find(section([row(), row("Fiserv DNA")],
                       thread="A broad, modern core estate."),
               peer_names=[], has_recorded_peers=False)
    assert out == []


def test_a_peer_deployment_on_a_row_is_itself_a_peer_set():
    """Even with nothing recorded server-side, a row that carries
    peer_deployments proves the run holds peers — so a peer-blind narrative
    beside it is still refused."""
    out = find(section([row(peers=["Suncoast"]), row("Fiserv DNA")],
                       thread="A broad, modern core estate anchored on "
                               "Salesforce and Fiserv."),
               peer_names=[], has_recorded_peers=False)
    assert ids(out) == ["CG-51"]
    assert paths(out) == {"techstack.techstack.narrative_thread"}


# ── scope and safety ──────────────────────────────────────────────────

def test_a_missing_narrative_is_not_a_second_finding():
    """The narrative half only fires on a thread that EXISTS and ignores peers.
    A section with no narrative_thread at all is the layers-producer's own
    contract to answer, not this gate inventing a second refusal."""
    out = find(section([row()]),      # structured reach missing, no thread
               peer_names=["Suncoast"])
    assert ids(out) == ["CG-51"]
    assert paths(out) == {"techstack.techstack.items[].peer_deployments"}


@pytest.mark.parametrize("bad", [
    None, [], "x", 42, {"items": "no"}, {"items": ["x", None]},
    {"items": [{"peer_deployments": "no"}]},
    {"items": [{"peer_deployments": []}]}])
def test_malformed_shapes_do_not_crash(bad):
    # has_recorded_peers True forces the gate to run its body over the shape
    V2._techstack_peer_findings(bad, {"suncoast"}, True)


def test_only_the_techstack_page_is_touched():
    payload = {"techstack": section([row()], thread="A broad core estate.")}
    for page in ("overview", "heatmap", "platform", "context", "insights"):
        assert V2._check_techstack_peer_comparison(
            None, "run-1", page, payload) == []


def test_the_wrapper_with_no_connection_falls_back_to_payload_peers():
    """No DB in hand, so the recorded set is empty — but a row's own
    peer_deployments still proves the peer set and drives the narrative half."""
    payload = {"techstack": section(
        [row(peers=["Suncoast"]), row("Fiserv DNA")],
        thread="A broad, modern core estate anchored on Salesforce.")}
    out = V2._check_techstack_peer_comparison(None, "run-1", "techstack",
                                              payload)
    assert ids(out) == ["CG-51"]
    assert paths(out) == {"techstack.techstack.narrative_thread"}


# ── it is registered and dispatched ───────────────────────────────────

def test_the_gate_is_registered_with_its_family_and_severity():
    from dma_mcp.gates import GATES
    assert "CG-51" in GATES
    assert GATES["CG-51"][-1] == "block"
    why = " ".join(str(x) for x in GATES["CG-51"]).lower()
    assert "peer" in why and "narrative" in why
    assert "cg-44" in why, "the cascade lineage is named"


def test_it_runs_inside_pass_two():
    import inspect
    src = inspect.getsource(V2.validate_pass2)
    assert "_check_techstack_peer_comparison" in src, \
        "CG-51 is defined but never dispatched"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
