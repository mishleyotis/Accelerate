"""engine.snapshot: a run survives a fresh container (measured 2026-09-30:
run state was container-local until PACKAGE)."""
from __future__ import annotations

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
