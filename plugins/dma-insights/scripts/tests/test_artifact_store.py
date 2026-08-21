"""Where produced work lives, and why it stopped going missing.

Sections were written to a flat `surfaces/<payload_section>.json`. Two
producers on one section overwrote each other, a challenge report had nowhere
of its own, nothing recorded WHICH agent produced a body, and the only way to
know whether a piece of work already existed was to remember doing it. Work
was redone and work went missing, and neither was detectable — a missing
artifact and an unproduced one look identical.

THE ONE IDEA, and every test here is about it: an artifact's NAME determines
its PATH.

    <run8>__<page>__<section>__<agent>__<kind>__<utc>.json
      -> <NN>_<page>/<section>/<agent>/

The redundancy between name and path IS the check. A file in the wrong folder
can be routed home from its own name, with no index to consult and nothing to
trust — which is what makes audit and heal possible at all.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
STORE = HERE.parent / "artifact_store.py"
HOOK = HERE.parent / "hooks" / "artifact_cadence.py"
RUN = "7a6ad71c-6225-4e0b-80fb-135cfd04b2dd"


def _mod():
    spec = importlib.util.spec_from_file_location("artifact_store", STORE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


A = _mod()


def body(page="overview", section="scores", run=RUN):
    return {"run_id": run, "page": page, "section": section}


# ── the taxonomy comes from the routing authority, not a second copy ──


def test_the_taxonomy_is_read_from_the_surface_map():
    t = A.taxonomy()
    assert set(t) <= set(A.PAGE_ORDER)
    # spot-check ownerships the surface map actually asserts
    assert "overview-hero-producer" in t["overview"]["scores"]
    assert "heatmap-grid-producer" in t["heatmap"]["workbook_scores"]
    assert "insights-cards-producer" in t["insights"]["insights"]


def test_the_taxonomy_is_not_hardcoded_anywhere_in_the_module():
    """A second copy of the page/section/agent map is a second thing to drift,
    and RULE_HELD_IN_TWO_PLACES_DRIFTS is already a top-three open defect
    class here.

    Checked over EXECUTABLE string constants only, never raw source. The
    module's usage examples name a real producer precisely so a reader can see
    the shape of a command, and an earlier version of this test failed on that
    documentation. Third time tonight a source-text assertion matched the prose
    written to explain it — the lesson is to assert over structure.
    """
    import ast
    tree = ast.parse(STORE.read_text())
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            d = ast.get_docstring(node, clean=False)
            if d is not None:
                docstrings.add(d)
    live = [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and n.value not in docstrings]
    for owner in ("overview-hero-producer", "heatmap-grid-producer",
                  "platform-fit-producer", "insights-cards-producer"):
        offenders = [s for s in live if owner in s]
        assert not offenders, (
            f"{owner} is a live string constant in the module; the "
            f"page/section/agent map must come from surface-map.md")


def test_a_taxonomy_that_cannot_be_read_yields_nothing_not_a_guess(tmp_path):
    assert A.taxonomy(tmp_path / "absent.md") == {}


# ── name determines path ──


def test_the_name_determines_the_folder():
    n = A.artifact_name(RUN, "overview", "scores", "overview-hero-producer",
                        "payload", ts="20260821T040000Z")
    assert n.startswith("7a6ad71c__overview__scores__overview-hero-producer__payload__")
    assert A.folder_for_name(n) == "10_overview/scores/overview-hero-producer"


def test_page_level_artifacts_sit_above_the_sections():
    assert A.folder_for("overview", "_page", "page-consolidator") == \
        "10_overview/_page/page-consolidator"


@pytest.mark.parametrize("page,expect", [
    ("run", "00_run"), ("ledger", "99_ledgers"),
])
def test_the_non_page_areas_have_their_own_homes(page, expect):
    assert A.folder_for(page, "x", "some-agent") == expect


def test_qa_and_enrichment_are_filed_by_agent():
    assert A.folder_for("qa", "b", "exclusion-boundary-auditor") == \
        "90_qa/exclusion-boundary-auditor"
    assert A.folder_for("enrichment", "b", "enrichment-planner") == \
        "95_enrichment/enrichment-planner"


def test_page_order_is_pipeline_order_not_alphabetical():
    """A listing should read the way the pipeline runs; alphabetical puts
    context before overview, which reads as nonsense to anyone opening it."""
    assert A.PAGE_DIR["overview"].startswith("10_")
    assert A.PAGE_DIR["techstack"].startswith("60_")


# ── the closed vocabularies ──


def test_an_unknown_kind_is_refused():
    """An open vocabulary means every agent invents its own word for the same
    thing, and `find` stops working."""
    with pytest.raises(A.Refused, match="closed"):
        A.artifact_name(RUN, "overview", "scores", "a-producer", "whatever")


def test_an_unknown_page_is_refused():
    with pytest.raises(A.Refused, match="unknown page"):
        A.folder_for("nonsense", "x", "a-producer")


@pytest.mark.parametrize("bad", ["Overview", "over view", "over/view", ""])
def test_a_non_taxonomy_token_is_refused(bad):
    with pytest.raises(A.Refused):
        A.artifact_name(RUN, bad, "scores", "a-producer", "payload")


def test_a_run_id_that_is_not_eight_hex_is_refused():
    with pytest.raises(A.Refused, match="8 hex"):
        A.artifact_name("nope", "overview", "scores", "a-producer", "payload")


# ── VERIFY BEFORE PLACING ──


def test_a_correct_placement_is_accepted(tmp_path):
    out = A.put(tmp_path, RUN, "overview", "scores",
                "overview-hero-producer", "payload", body())
    assert out.parent.relative_to(tmp_path).as_posix() == \
        "10_overview/scores/overview-hero-producer"


def test_a_body_that_contradicts_its_name_is_refused(tmp_path):
    """THE CASE THE CHECK EXISTS FOR. Writing this anywhere leaves the tree
    lying about what it holds, so it is never resolved by taking two of three."""
    with pytest.raises(A.Refused) as e:
        A.put(tmp_path, RUN, "overview", "scores", "overview-hero-producer",
              "payload", body(page="heatmap", section="alerts"))
    assert "body page" in str(e.value)
    assert not list(tmp_path.rglob("*.json")), "nothing may be written"


def test_a_body_with_a_foreign_run_id_is_refused(tmp_path):
    with pytest.raises(A.Refused, match="run_id"):
        A.put(tmp_path, RUN, "overview", "scores", "overview-hero-producer",
              "payload", body(run="deadbeef-0000-0000-0000-000000000000"))


def test_a_body_that_says_nothing_about_itself_is_allowed(tmp_path):
    """Silence is accepted; only contradiction refuses. Plenty of artifacts
    legitimately carry no envelope."""
    out = A.put(tmp_path, RUN, "overview", "scores",
                "overview-hero-producer", "payload", {"anything": 1})
    assert out.is_file()


def test_a_mismatched_destination_is_refused(tmp_path):
    problems = A.verify_placement(
        tmp_path,
        A.artifact_name(RUN, "overview", "scores", "overview-hero-producer",
                        "payload", ts="20260821T040000Z"),
        "30_heatmap/alerts/heatmap-signals-producer")
    assert problems and "placement says" in problems[0]


# ── recursive retrieval: misplaced work still prevents a redo ──


def test_find_locates_a_misplaced_artifact(tmp_path):
    """A lookup that only reads the correct folder reports misfiled work as
    ABSENT — which is exactly when it gets produced a second time."""
    A.put(tmp_path, RUN, "overview", "scores", "overview-hero-producer",
          "payload", body())
    wrong = tmp_path / "99_ledgers"
    wrong.mkdir(parents=True)
    name = A.artifact_name(RUN, "insights", "landscape",
                           "insights-landscape-producer", "payload",
                           ts="20260821T041100Z")
    (wrong / name).write_text(json.dumps(body("insights", "landscape")))

    hits = A.find(tmp_path, run=RUN, page="insights")
    assert len(hits) == 1
    assert hits[0]["misplaced"] is True
    assert hits[0]["belongs"] == "20_insights/landscape/insights-landscape-producer"


def test_latest_returns_the_newest(tmp_path):
    for ts in ("20260821T040000Z", "20260821T050000Z", "20260821T030000Z"):
        A.put(tmp_path, RUN, "overview", "scores", "overview-hero-producer",
              "payload", body(), ts=ts)
    assert A.latest(tmp_path, run=RUN, section="scores")["ts"] == "20260821T050000Z"


def test_find_on_an_empty_tree_is_empty_not_an_error(tmp_path):
    assert A.find(tmp_path / "nothing-here") == []


# ── heal: move only after verifying ──


def test_a_self_consistent_misplaced_artifact_is_healed(tmp_path):
    (tmp_path / "99_ledgers").mkdir(parents=True)
    name = A.artifact_name(RUN, "insights", "landscape",
                           "insights-landscape-producer", "payload",
                           ts="20260821T041100Z")
    (tmp_path / "99_ledgers" / name).write_text(
        json.dumps(body("insights", "landscape")))
    moves = A.heal(tmp_path, apply=True)
    assert [m for m in moves if m["moved"]]
    assert (tmp_path / "20_insights/landscape/insights-landscape-producer"
            / name).is_file()


def test_heal_refuses_an_artifact_whose_body_contradicts_its_name(tmp_path):
    """A heal that trusted the name alone would turn one misfiled artifact
    into a confidently misfiled one."""
    d = tmp_path / "40_platform/roadmap/platform-roadmap-producer"
    d.mkdir(parents=True)
    name = A.artifact_name(RUN, "context", "timeline",
                           "context-timeline-producer", "payload",
                           ts="20260821T041000Z")
    (d / name).write_text(json.dumps(body("heatmap", "alerts")))
    moves = A.heal(tmp_path, apply=True)
    assert all(not m["moved"] for m in moves)
    assert (d / name).is_file(), "it must be left exactly where it is"
    assert any("body page" in (m["refused"] or "") for m in moves)


def test_heal_never_clobbers_a_correctly_filed_artifact(tmp_path):
    good = A.put(tmp_path, RUN, "overview", "scores",
                 "overview-hero-producer", "payload", body(),
                 ts="20260821T040000Z")
    stray = tmp_path / "99_ledgers"
    stray.mkdir(parents=True)
    (stray / good.name).write_text(json.dumps(body()))
    moves = A.heal(tmp_path, apply=True)
    assert any("already filed correctly" in (m["refused"] or "") for m in moves)
    assert good.is_file()


def test_heal_without_apply_moves_nothing(tmp_path):
    (tmp_path / "99_ledgers").mkdir(parents=True)
    name = A.artifact_name(RUN, "insights", "landscape",
                           "insights-landscape-producer", "payload",
                           ts="20260821T041100Z")
    src = tmp_path / "99_ledgers" / name
    src.write_text(json.dumps(body("insights", "landscape")))
    moves = A.heal(tmp_path, apply=False)
    assert moves and all(not m["moved"] for m in moves)
    assert src.is_file()


def test_audit_ignores_the_older_conventions(tmp_path):
    """state.json and the memory markdown predate this store and are not its
    artifacts; flagging them would make the audit unreadable."""
    (tmp_path / "state.json").write_text("{}")
    (tmp_path / "client — synthesis memory.md").write_text("# notes")
    rep = A.audit(tmp_path)
    assert rep["unnamed"] == []


def test_audit_reports_a_file_with_no_taxonomy_name(tmp_path):
    (tmp_path / "scratch.json").write_text("{}")
    assert "scratch.json" in A.audit(tmp_path)["unnamed"]


# ── the cadence hook ──


def _hook(event, env=None):
    import os
    e = {**os.environ, **(env or {})}
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event),
                       capture_output=True, text=True, env=e)
    return r


def test_the_hook_fires_when_a_producer_returned_with_nothing_filed(tmp_path):
    r = _hook({"tool_name": "Agent",
               "tool_input": {"subagent_type": "dma-insights:overview-whynow-producer"}},
              {"DMA_RUN_ID": RUN, "DMA_ARTIFACT_ROOT": str(tmp_path)})
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert "ARTIFACT CADENCE" in out["additionalContext"]
    assert "overview-whynow-producer" in out["additionalContext"]


def test_the_hook_is_silent_once_the_artifact_is_filed(tmp_path):
    """A hook that speaks on success trains people to ignore it."""
    A.put(tmp_path, RUN, "overview", "why_now", "overview-whynow-producer",
          "payload", body("overview", "why_now"))
    r = _hook({"tool_name": "Agent",
               "tool_input": {"subagent_type": "dma-insights:overview-whynow-producer"}},
              {"DMA_RUN_ID": RUN, "DMA_ARTIFACT_ROOT": str(tmp_path)})
    assert r.stdout.strip() == ""


@pytest.mark.parametrize("agent", ["general-purpose", "Explore", "claude", ""])
def test_the_hook_ignores_non_producers(agent, tmp_path):
    r = _hook({"tool_name": "Agent", "tool_input": {"subagent_type": agent}},
              {"DMA_RUN_ID": RUN, "DMA_ARTIFACT_ROOT": str(tmp_path)})
    assert r.stdout.strip() == ""


def test_the_hook_stays_quiet_when_it_cannot_locate_the_run(tmp_path):
    """An enforcement that fires on a wrong run id is noise, and noise gets
    switched off."""
    r = _hook({"tool_name": "Agent",
               "tool_input": {"subagent_type": "dma-insights:overview-hero-producer"}},
              {"DMA_RUN_ID": "", "DMA_ARTIFACT_ROOT": "",
               "DMA_BUNDLE_CACHE": str(tmp_path / "none")})
    assert r.stdout.strip() == ""


def test_the_hook_never_blocks(tmp_path):
    """A producer's output already exists by the time this runs; refusing the
    tool result would throw away the very work the hook exists to preserve."""
    r = _hook({"tool_name": "Agent",
               "tool_input": {"subagent_type": "dma-insights:heatmap-grid-producer"}},
              {"DMA_RUN_ID": RUN, "DMA_ARTIFACT_ROOT": str(tmp_path)})
    assert r.returncode == 0
    assert "permissionDecision" not in r.stdout
    assert '"decision"' not in r.stdout


def test_malformed_hook_input_neither_crashes_nor_speaks():
    r = subprocess.run([sys.executable, str(HOOK)], input="not json",
                       capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_the_hook_is_registered_on_the_dispatch_tool():
    cfg = json.loads((HERE.parent.parent / "hooks" / "hooks.json").read_text())
    post = cfg["hooks"]["PostToolUse"]
    wired = [e for e in post
             if "artifact_cadence.py" in " ".join(h["command"] for h in e["hooks"])]
    assert wired, "the cadence hook is not wired to PostToolUse"
    assert "Task" in wired[0]["matcher"] or "Agent" in wired[0]["matcher"]
