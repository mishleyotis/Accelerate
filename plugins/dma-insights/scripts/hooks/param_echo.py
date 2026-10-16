#!/usr/bin/env python3
"""PreCompact: write the run's parameters to disk so PostCompact can echo them.

Measured 28-09-2026 (QA audit F-E10-034): after a compaction the session
brief re-injected the routing rule (911 bytes) and nothing else — no run
id, no root, no stage, no budget. A compacted session had to rediscover
all four from a summary it did not write, or run `engine.cli resume` on a
run id it may not remember. The summariser chooses what to keep; this hook
keeps the parameters regardless.

PreCompact (this script): locate the run the way every guard does
(`_runctx.locate`), read the figures the run itself records, and write
`<run>/07_qa/param_echo.json`. PostCompact (`session_brief.py`): read the
file back and print it beside the compaction brief. Written before the
compaction, read after it, compared by the test — the echo diff is zero.

Fails OPEN: no run, no engine, an unreadable workbook — it writes nothing
and prints nothing, because a PreCompact hook that errors stops the
compaction it exists to survive.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import _runctx  # noqa: E402

ECHO_NAME = "param_echo.json"
ECHO_SCHEMA = "param_echo_v1"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def echo_for(run) -> dict:
    """The parameters a compacted session loses, read from the run."""
    doc = {"schema_version": ECHO_SCHEMA, "written_at": _utcnow(),
           "run_id": run.run_id, "root": str(run.root),
           "workbook": str(run.workbook_path),
           "workbook_stage": None, "entity": None,
           "pipeline": {"done": [], "next": None},
           "budget": None, "rounds": None,
           "search_ops_since_checkpoint": None, "search_op_ceiling": None,
           "resume": (f"python3 -m engine.cli resume --run {run.run_id} "
                      f"--root {run.root}")}
    state = _runctx.pipeline_state(run)
    try:
        doc["budget"] = _runctx.budget(run, state)
        doc["rounds"] = _runctx.rounds(run, state)
    except Exception:                                          # noqa: BLE001
        pass
    try:
        (pipeline,) = _runctx.engine("pipeline")
        stages = state.get("stages") or {}
        done = [s for s in pipeline.STAGES
                if str((stages.get(s) or {}).get("verdict") or "").upper() in ("PASS", "DONE")]
        doc["pipeline"] = {"done": done,
                           "next": next((s for s in pipeline.STAGES if s not in done), None)}
    except Exception:                                          # noqa: BLE001
        pass
    try:
        (contract, ledger) = _runctx.engine("contract", "ledger")
        wb = run.open()
        md = wb.metadata()
        doc["workbook_stage"] = contract.stage_of(md)
        doc["entity"] = str(md.get("entity_name") or "") or None
        st = ledger.stats(wb)
        doc["search_ops_since_checkpoint"] = st.get("search_ops_since_checkpoint")
        doc["search_op_ceiling"] = st.get("search_op_ceiling")
    except Exception:                                          # noqa: BLE001
        pass
    return doc


def write_echo(run) -> Path | None:
    doc = echo_for(run)
    path = Path(run.qa_dir) / ECHO_NAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        return None
    return path


def read_echo(run) -> dict | None:
    """The echo written before the compaction, or None."""
    try:
        path = Path(run.qa_dir) / ECHO_NAME
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or doc.get("run_id") != run.run_id:
        return None
    return doc


def render(doc: dict | None) -> str:
    """One paragraph a compacted session reads before its first tool call."""
    if not doc:
        return (" PARAMETER ECHO: none on disk — no run was located before the "
                "compaction. Recover the run id from `python3 -m engine.cli "
                "resume` before anything else.")
    b = doc.get("budget") or {}
    r = doc.get("rounds") or {}
    p = doc.get("pipeline") or {}
    money = ("budget unknown" if b.get("ceiling") is None else
             f"budget ${b.get('spent') if b.get('spent') is not None else 0:.2f} of "
             f"${b['ceiling']:.2f}" + (" EXHAUSTED" if b.get("exhausted") else ""))
    ops = doc.get("search_ops_since_checkpoint")
    ops_txt = (f"search ops since checkpoint {ops}/{doc.get('search_op_ceiling')}"
               if ops is not None else "search ops unknown")
    return (f" PARAMETER ECHO (written at {doc.get('written_at')}, before the "
            f"compaction): run {doc.get('run_id')}"
            + (f" ({doc['entity']})" if doc.get("entity") else "")
            + f" · root {doc.get('root')}"
            + f" · workbook stage {doc.get('workbook_stage') or 'unknown'}"
            + f" · pipeline next {p.get('next') or 'unknown'}"
            + (f" (done: {', '.join(p['done'])})" if p.get("done") else "")
            + f" · {money} · rounds {r.get('done', '?')}/{r.get('max', '?')}"
            + f" · {ops_txt}. These are the run's own figures, not the summary's;"
            f" `{doc.get('resume')}` re-derives the rest.")


def main() -> int:
    try:
        json.load(sys.stdin)
    except Exception:            # noqa: BLE001 — fail OPEN
        pass
    run = _runctx.locate()
    if run is None:
        return 0
    write_echo(run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
