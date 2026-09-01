"""The canon is only a canon if something compares it to what fires.

THE DEFECT THIS FILE EXISTS FOR, in full, because it is the most expensive
shape of bug in this repo and it defeated every check that was in place.

On 2026-08-31 the intake Routine's STEP 0a was rewritten: run
`doctor.py --heal` rather than stop on a stale plugin. The canon was edited.
Tests were written against the canon — `test_routines_canon.py` grew four of
them, and they asserted exactly the right properties. They passed. The change
was committed, the whole suite ran green, it was pushed to the default
branch. Then the Routine fired and reported:

    STEP 0a check (a) — `doctor.py` — FAILED ... a non-green doctor result
    requires stopping immediately ... STALE: installed 0.9.12 (47 agents)
    vs published 1.14.0 (68 agents)

It ran the BARE doctor, because the prompt that fires lives in the trigger
record and nothing had ever copied the file into it. The canon tests were
measuring a document against itself.

So these tests are about the ONE property no canon test can have: that the
file and the live trigger are the same text, and that when they are not,
something says so out loud.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import routine_sync as rs  # noqa: E402


def test_the_canon_sections_carry_ids_and_prompts():
    secs = rs.sections()
    assert "2g" in secs, "the intake routine is the one that starts a DMA"
    g = secs["2g"]
    assert g["name"] == "dma-assessment-intake"
    assert g["trigger_id"] and g["trigger_id"].startswith("trig_")
    assert g["live"] and g["prompt"] and len(g["prompt"]) > 5000


def test_a_live_routine_that_matches_is_in_sync():
    secs = rs.sections()
    g = secs["2g"]
    assert rs.compare(g["prompt"], g["prompt"])["in_sync"]


def test_the_exact_drift_that_killed_the_firing_is_detected():
    """The live prompt ran the bare doctor; the canon ran `--heal`. That is
    a one-word difference in a 21,000-character prompt, and it decided
    whether the Routine did any work at all."""
    canon = "run `doctor.py --heal` and read the verdict"
    live = "run `doctor.py` and read the verdict"
    c = rs.compare(canon, live)
    assert not c["in_sync"]
    assert c["markers"]["heals the plugin"] == {"canon": True, "live": False}
    assert any("--heal" in ln for ln in c["diff"])


def test_trailing_whitespace_is_not_reported_as_drift():
    """A reconciler that cries wolf over invisible characters is one people
    stop running, and a reconciler nobody runs is the state we just left."""
    assert rs.compare("alpha\nbeta", "alpha  \nbeta\t")["in_sync"]


def test_the_markers_name_the_properties_a_firing_turns_on():
    c = rs.compare("connector_contract.py declare", "Firecrawl is required")
    assert c["markers"]["derives connectors"]["canon"]
    assert not c["markers"]["derives connectors"]["live"]
    assert c["markers"]["requires firecrawl"]["live"]


def test_push_refuses_a_section_with_no_trigger():
    """§2a is declared but NOT CREATED. Pushing it would be a create, not an
    update — a different act, with a schedule nobody chose."""
    secs = rs.sections()
    a = secs.get("2a")
    assert a is not None and not a["trigger_id"]
    with pytest.raises(rs.SyncRefusal) as e:
        rs.push_payload(a)
    assert "does not exist yet" in str(e.value)


def test_push_refuses_to_blank_a_live_routine():
    with pytest.raises(rs.SyncRefusal) as e:
        rs.push_payload({"key": "2x", "name": "x", "trigger_id": "trig_1",
                         "prompt": None, "live": True})
    assert "nothing to push" in str(e.value)


def test_push_renders_exactly_the_update_trigger_arguments():
    secs = rs.sections()
    out = rs.push_payload(secs["2g"])
    assert set(out) == {"trigger_id", "prompt"}, (
        "update_trigger takes these two; anything else would silently "
        "change a schedule or a model nobody asked to change")
    assert out["prompt"] == secs["2g"]["prompt"]


def test_the_live_set_is_read_from_what_list_triggers_returns():
    payload = [{"id": "trig_1", "name": "dma-watchdog", "prompt": "hello"}]
    for shape in (payload, {"triggers": payload}):
        live = rs.load_live_obj(shape) if hasattr(rs, "load_live_obj") else None
        if live is None:
            break
    # the file-based path is the supported one; exercise it end to end
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(payload, f)
        path = f.name
    live = rs.load_live(path)
    assert live["dma-watchdog"] == "hello" and live["trig_1"] == "hello"


def test_the_cli_exits_nonzero_on_drift(tmp_path):
    """A reconciler that reports drift and exits 0 is a reconciler that CI
    and a firing both read as success."""
    live = tmp_path / "live.json"
    secs = rs.sections()
    live.write_text(json.dumps([
        {"name": secs["2g"]["name"], "prompt": "something else entirely"}]))
    r = subprocess.run(
        [sys.executable, str(HERE / "routine_sync.py"), "diff",
         "--routine", "2g", "--live", str(live)],
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 1 and "DRIFTED" in r.stdout


def test_the_cli_exits_zero_when_the_file_is_what_fires(tmp_path):
    secs = rs.sections()
    live = tmp_path / "live.json"
    live.write_text(json.dumps([
        {"name": secs["2g"]["name"], "prompt": secs["2g"]["prompt"]}]))
    r = subprocess.run(
        [sys.executable, str(HERE / "routine_sync.py"), "diff",
         "--routine", "2g", "--live", str(live)],
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "in sync" in r.stdout


def test_a_routine_missing_from_the_live_set_counts_as_drift(tmp_path):
    """Absent is not 'in sync'. A Routine that was deleted, or that the
    caller forgot to include, must never read as reconciled."""
    live = tmp_path / "live.json"
    live.write_text("[]")
    r = subprocess.run(
        [sys.executable, str(HERE / "routine_sync.py"), "diff",
         "--routine", "2g", "--live", str(live)],
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 1 and "NOT IN THE SUPPLIED LIVE SET" in r.stdout


def test_the_canon_no_longer_claims_to_have_no_reconciler():
    """The sentence that made the drift invisible: 'They have no reconciler
    today; this file is their declaration.'"""
    text = rs.CANON.read_text()
    # The ASSERTION, not the history. The canon deliberately quotes the old
    # sentence in lower case as the record of what went wrong, so the test
    # pins the declarative form — the one that would mean it again.
    assert "They have no reconciler" not in text, (
        "the canon still declares itself unreconciled")
    assert "routine_sync.py` is their reconciler" in text
    assert "routine_sync.py" in text, (
        "the canon must name the tool that reconciles it, or the next person "
        "to edit a prompt will again believe the file is the system")
