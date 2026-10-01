#!/usr/bin/env python3
"""Routines that still drive a run this client has moved past.

Measured 2026-10-01 (SWBC): an hourly Claude Code Routine written on
2026-09-16 for run 9fcee059 ("relaunch ONE bounded batch now … --lanes 8")
was still ENABLED two weeks after that run was superseded by
DMA-RES-SWBC-20260930-0001, and had fired 39 minutes before the resuming
session looked. Nothing in the plugin could see it: `setup_routines.py`
reconciles Cloud Scheduler jobs, and a Routine is account state no
subprocess can list.

So, like the connector baseline, the SESSION lists them and hands the JSON
here (the `mcp__claude-code-remote__list_triggers` result, verbatim):

    <list_triggers JSON> | python3 stale_run_routines.py --root <ROOT> [--client SWBC]

A routine is STALE when its prompt names a DMA run id that is not the run
at <ROOT> while naming this client (or this run root). It is reported, never
touched here: pausing is `update_trigger(enabled=false)`, a reversible act
the session takes and states. Exit 3 when anything is stale.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

RUN_ID = re.compile(r"\b(DMA-RES-[A-Z0-9]+-\d{8}-\d{4}|[0-9a-f]{8}-[0-9a-f]{4}-"
                    r"[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b")


def current_run_id(root: Path) -> str:
    wbs = sorted(Path(root).glob("DMA_Scoring_Workbook_*.xlsx"))
    if not wbs:
        return ""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "dma-research"))
    from engine.workbook import RunWorkbook                     # noqa: PLC0415
    return str(RunWorkbook(wbs[-1]).metadata().get("run_id") or "")


def _prompt(t: dict) -> str:
    ds = t.get("derived_state") or {}
    return str(ds.get("prompt") or t.get("prompt") or "")


def stale(triggers: list[dict], current: str, *, client: str = "",
          root: str = "") -> list[dict]:
    out = []
    for t in triggers:
        if not t.get("enabled", True):
            continue
        text = _prompt(t)
        ids = set(RUN_ID.findall(text))
        if not ids or current in ids:
            continue
        mine = (client and re.search(rf"\b{re.escape(client)}\b", text, re.I)) or \
               (root and root in text)
        if not mine:
            continue
        out.append({"id": t.get("id"), "name": t.get("name"),
                    "cron": t.get("cron_expression"),
                    "targets": sorted(ids), "current": current,
                    "last_fired_at": t.get("last_fired_at"),
                    "action": "pause it: update_trigger(trigger_id, enabled=false) — "
                              "reversible; say so to the owner"})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", required=True, help="the CURRENT run's root")
    ap.add_argument("--client", default="", help="the client name the prompts use")
    ap.add_argument("--triggers", default="-",
                    help="list_triggers JSON (default: stdin)")
    a = ap.parse_args(argv)
    raw = sys.stdin.read() if a.triggers == "-" else Path(a.triggers).read_text()
    doc = json.loads(raw or "{}")
    triggers = doc.get("data") if isinstance(doc, dict) else doc
    cur = current_run_id(Path(a.root))
    found = stale(triggers or [], cur, client=a.client, root=str(a.root))
    print(json.dumps({"current_run": cur, "stale": found}, indent=1))
    return 3 if found else 0


if __name__ == "__main__":
    sys.exit(main())
