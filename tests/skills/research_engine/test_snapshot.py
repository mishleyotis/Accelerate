"""engine.snapshot: a run survives a fresh container (measured 2026-09-30:
run state was container-local until PACKAGE)."""
from __future__ import annotations

from pathlib import Path

from engine import snapshot
from fixtures import new_run


def test_a_snapshot_round_trips_the_run_without_transcripts(tmp_path):
    run = new_run(tmp_path, n=3, prelim=False)
    (run.root / "agent_logs").mkdir(exist_ok=True)
    (run.root / "agent_logs" / "lane.jsonl").write_text("x" * 1000)
    blob = snapshot.build(run.root)
    dest = tmp_path / "fresh_container"
    snapshot.unpack(blob, dest)
    assert (dest / run.workbook_path.name).is_file(), "the workbook did not survive"
    assert not (dest / "agent_logs").exists(), "transcripts belong to the container"
    assert not list(dest.rglob("*.lock"))


def test_a_path_outside_the_run_is_refused(tmp_path):
    import io
    import tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        ti = tarfile.TarInfo("../escape.txt"); ti.size = 1
        tf.addfile(ti, io.BytesIO(b"x"))
    try:
        snapshot.unpack(buf.getvalue(), tmp_path / "r")
    except ValueError:
        return
    raise AssertionError("an archive wrote outside the run root")


def test_no_entity_is_not_run_rather_than_a_crash(tmp_path, monkeypatch):
    run = new_run(tmp_path, n=3, prelim=False)
    monkeypatch.setattr(snapshot, "_entity", lambda r: "")
    assert snapshot.push(run)["outcome"] == "NOT_RUN"


# ── session 2 (2026-10-01, SWBC) ──────────────────────────────────────────

def test_session_state_never_rides_in_a_snapshot(tmp_path):
    """I-64: a restore overwrote the resuming session's fresh connector
    baseline with the previous session's, and brought back a dead driver's
    pid and two interrupted saves."""
    run = new_run(tmp_path, n=3, prelim=False)
    (run.root / "pipeline.pid").write_text("12345")
    (run.root / "tmpabc.xlsx.part").write_text("partial")
    assert (run.root / "connectors_baseline.json").is_file()
    dest = tmp_path / "fresh"
    snapshot.unpack(snapshot.build(run.root), dest)
    for gone in ("connectors_baseline.json", "pipeline.pid", "tmpabc.xlsx.part"):
        assert not (dest / gone).exists(), gone
    assert (dest / run.workbook_path.name).is_file()


def test_the_pointer_names_the_current_run_and_its_binding(tmp_path):
    run = new_run(tmp_path, n=3, prelim=False)
    ptr = snapshot.pointer(run)
    assert ptr["run_id"] == run.run_id and ptr["snapshot"] == snapshot.name_for(run.run_id)
    assert ptr["binding"]["sub_vertical"] == "CU"
    assert "superseded" in ptr["note"]


def test_a_superseded_runs_files_are_named_on_restore(tmp_path):
    """I-62: the SWBC backup folder held a 2026-09-16 run's handoff note,
    workbook and notebooks beside the live snapshot; nothing said which was
    current."""
    folder = tmp_path / "backup"
    folder.mkdir()
    rid = "DMA-RES-SWBC-20260930-0001"
    (folder / snapshot.name_for(rid)).write_bytes(b"x")
    (folder / snapshot.POINTER).write_text("{}")
    (folder / "DMA_Scoring_Workbook_swbc_2026-09-30.xlsx").write_bytes(b"x")
    (folder / "DMA_Scoring_Workbook_swbc_2026-09-16.xlsx").write_bytes(b"x")
    (folder / "_RUN_HANDOFF.md").write_text("run_id `9fcee059-1c89-4769-88df-594c2bce20e6`")
    (folder / "P1C1.md").write_text("notes with no run id")
    (folder / "P2C1.md").write_text(f"notes for {rid}")
    got = snapshot._superseded(folder, rid, "DMA_Scoring_Workbook_swbc_2026-09-30.xlsx")
    assert got == ["DMA_Scoring_Workbook_swbc_2026-09-16.xlsx", "_RUN_HANDOFF.md"]


def test_restore_without_a_run_follows_the_pointer(tmp_path, monkeypatch):
    import json
    import subprocess
    run = new_run(tmp_path, n=3, prelim=False)
    blob = snapshot.build(run.root)

    def fake_pull(cmd, **kw):
        dest = Path(cmd[cmd.index("--dest") + 1])
        (dest / snapshot.name_for(run.run_id)).write_bytes(blob)
        (dest / snapshot.POINTER).write_text(json.dumps(snapshot.pointer(run)))
        (dest / "_RUN_HANDOFF.md").write_text("run 9fcee059-1c89-4769-88df-594c2bce20e6")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(snapshot.subprocess, "run", fake_pull)
    out = snapshot.restore(None, tmp_path / "fresh", "Acme Credit Union")
    assert out["outcome"] == "RESOLVED" and out["run_id"] == run.run_id
    assert out["superseded_in_folder"] == ["_RUN_HANDOFF.md"]
