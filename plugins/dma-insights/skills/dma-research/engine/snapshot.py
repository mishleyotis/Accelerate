"""A durable copy of a run in flight, so a fresh container resumes it.

Measured 2026-09-30 (a multi-LOB live run): everything a run had researched —
workbook, evidence, QA state, briefs — lived only in the container until
PACKAGE pushed the client folder. A session that resumed on a fresh
container would have lost a day of research and started again at PREFLIGHT.

`push` tars the run (minus the regenerable agent transcripts and lock files)
under the workbook lock, so the copy is one consistent state, and sends it to
the client's Drive `memory-backup` folder with the service account
(drive_fetch push-backup — the same identity and folder the notebook backup
already uses). `restore` pulls it back and unpacks it where the run belongs.
The driver pushes one at every stage boundary; ~2.4 MB for a 760-cell run.

    python3 -m engine.snapshot push    --run R --root ROOT
    python3 -m engine.snapshot restore --run R --root ROOT --client "<Entity>"
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

if __package__ in (None, ""):  # noqa: E402 — runnable as a file, too
    import os as _os
    _sys_path = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    sys.path.insert(0, _sys_path)
    __package__ = "engine"

from . import runstate  # noqa: E402
from .workbook import file_lock  # noqa: E402

EXCLUDE_DIRS = ("agent_logs",)          # transcripts: large and regenerable
EXCLUDE_SUFFIXES = (".lock",)
DRIVE_FETCH = Path(__file__).resolve().parents[3] / "scripts" / "drive_fetch.py"


def name_for(run_id: str) -> str:
    return f"run_snapshot_{run_id}.tar.gz"


def build(root: Path) -> bytes:
    """The run as one gzip'd tar, excluding transcripts and locks."""
    root = Path(root)
    buf = io.BytesIO()

    def keep(ti: tarfile.TarInfo):
        parts = Path(ti.name).parts
        if any(p in EXCLUDE_DIRS for p in parts) or ti.name.endswith(EXCLUDE_SUFFIXES):
            return None
        return ti
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for p in sorted(root.iterdir()):
            tf.add(str(p), arcname=p.name, filter=keep)
    return buf.getvalue()


def unpack(blob: bytes, root: Path) -> int:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    n = 0
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        for m in tf.getmembers():
            dest = (root / m.name).resolve()
            if not str(dest).startswith(str(root.resolve())):
                raise ValueError(f"refusing a path outside the run: {m.name}")
        tf.extractall(root)
        n = len(tf.getmembers())
    return n


def _entity(run) -> str:
    try:
        return str(run.open().metadata().get("entity_name") or "")
    except Exception:
        return ""


def push(run, *, client: str | None = None) -> dict:
    """Snapshot the run to Drive. Never raises: a backup that fails must not
    fail the stage it follows — it is reported, and the next boundary tries
    again."""
    client = client or _entity(run)
    if not client:
        return {"outcome": "NOT_RUN", "reason": "no entity name on the run"}
    if not DRIVE_FETCH.exists():
        return {"outcome": "NOT_RUN", "reason": "drive_fetch.py is not in this install"}
    try:
        with file_lock(Path(str(run.workbook_path) + ".lock"), timeout=300,
                       why="engine.snapshot push"):
            blob = build(run.root)
    except Exception as e:                       # noqa: BLE001 — reported
        return {"outcome": "FAILED", "reason": f"snapshot build: {e}"[:300]}
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / name_for(run.run_id)
        f.write_bytes(blob)
        r = subprocess.run([sys.executable, str(DRIVE_FETCH), "push-backup",
                            "--client", client, "--file", str(f)],
                           capture_output=True, text=True, timeout=600)
    out = {"outcome": "RESOLVED" if r.returncode == 0 else "FAILED",
           "bytes": len(blob), "name": name_for(run.run_id), "client": client}
    if r.returncode:
        out["reason"] = (r.stderr or r.stdout or "").strip()[-300:]
    return out


def restore(run_id: str, root: Path, client: str) -> dict:
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run([sys.executable, str(DRIVE_FETCH), "pull-backup",
                            "--client", client, "--dest", td],
                           capture_output=True, text=True, timeout=600)
        if r.returncode:
            return {"outcome": "FAILED", "reason": (r.stderr or r.stdout)[-300:]}
        f = Path(td) / name_for(run_id)
        if not f.is_file():
            return {"outcome": "NOT_FOUND",
                    "reason": f"no {f.name} in the client's backup folder"}
        n = unpack(f.read_bytes(), root)
    return {"outcome": "RESOLVED", "members": n, "root": str(root)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="engine.snapshot", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("push", "restore"):
        p = sub.add_parser(c)
        p.add_argument("--run", required=True)
        p.add_argument("--root", required=True)
        p.add_argument("--client", required=(c == "restore"))
    a = ap.parse_args(argv)
    if a.cmd == "push":
        out = push(runstate.locate(a.run, Path(a.root)), client=a.client)
    else:
        out = restore(a.run, Path(a.root), a.client)
    print(json.dumps(out, indent=1))
    return 0 if out["outcome"] == "RESOLVED" else 1


if __name__ == "__main__":
    sys.exit(main())
