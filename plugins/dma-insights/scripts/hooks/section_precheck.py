#!/usr/bin/env python3
"""PostToolUse hook on Write/Edit — a section file is pass-1 checked the
moment it is written.

Arbor Bank (2026-10-06): CG-04 (an undeclared key), CG-46 (a rung that was
prose, not {source, query, outcome}), AG-03 (a tile carrying an empty list)
and AG-01 (a WITHDRAWN verdict) each reached the producer only after
ship_page.py's precheck or the server's verdict — one full page round per
defect. Every one of them is a pass-1 gate, which is pure, needs no
database and runs in well under a second. So it runs HERE, on the file the
producer just wrote, and the reasons for THAT section come back as
additionalContext before the next file is written.

Never blocks: the connector's verdict is the authority and ship_page.py
still replays both passes before a submit. When the connector's gate
modules are not reachable (a container with the plugin and no checkout)
the hook says so and stays out of the way.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parents[1]
PROD_SCRIPTS = PLUGIN / "skills" / "dma-surface-production" / "scripts"
SECTION_FILE = re.compile(r"^(?P<page>[a-z]+)\.(?P<section>[a-z_]+)(?:\.(?P<shard>[^.]+))?\.json$")
PAGES = ("overview", "insights", "heatmap", "platform", "techstack", "context")
MAX_REASONS = 12


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, PROD_SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def section_reasons(path: Path, repo: str | None = None) -> dict | None:
    """{"page", "section", "reasons": [...], "page_total": n} for the
    section file at `path`, or None when the path is not a section file;
    {"not_run": why} when the gates cannot run."""
    m = SECTION_FILE.match(path.name)
    if not m or path.parent.name != "08_sections" or m.group("page") not in PAGES:
        return None
    page, section = m.group("page"), m.group("section")
    try:
        ship = _load("ship_page")
        payload = ship.assemble(path.parent, page)
    except Exception as exc:                                     # noqa: BLE001
        return {"page": page, "section": section, "not_run": f"assemble: {str(exc)[:160]}"}
    try:
        pg = _load("precheck_gates")
        validation, _v2, _rs, _where = pg._load_connector(repo)
    except SystemExit as exc:
        return {"page": page, "section": section, "not_run": str(exc).splitlines()[0][:160]}
    except Exception as exc:                                     # noqa: BLE001
        return {"page": page, "section": section, "not_run": f"{type(exc).__name__}: {str(exc)[:160]}"}
    try:
        reasons = [r for r in validation.validate_pass1(page, payload)
                   if r.get("severity", "block") == "block"]
    except Exception as exc:                                     # noqa: BLE001
        return {"page": page, "section": section, "not_run": f"validate_pass1 raised {type(exc).__name__}"}
    mine = [r for r in reasons if str(r.get("section") or "") == section
            or str(r.get("path") or "").startswith(section)]
    return {"page": page, "section": section, "reasons": mine, "page_total": len(reasons)}


def render(out: dict) -> str:
    if out.get("not_run"):
        return (f"section precheck did not run for {out['page']}.{out['section']}: "
                f"{out['not_run']} — ship_page.py will replay the gates before any submit")
    if not out["reasons"]:
        if out["page_total"]:
            return (f"{out['page']}.{out['section']}: pass-1 clean; {out['page_total']} blocking "
                    f"reason(s) remain on OTHER sections of this page")
        return ""
    lines = [f"PASS-1 REFUSALS on {out['page']}.{out['section']} — fix before the next file "
             f"({len(out['reasons'])} on this section, {out['page_total']} on the page):"]
    for r in out["reasons"][:MAX_REASONS]:
        lines.append(f"  {r.get('gate_id')} {r.get('path')} | {str(r.get('message'))[:220]}")
    if len(out["reasons"]) > MAX_REASONS:
        lines.append(f"  … {len(out['reasons']) - MAX_REASONS} more")
    return "\n".join(lines)


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:                                            # noqa: BLE001
        return 0
    if not isinstance(event, dict):
        return 0
    ti = event.get("tool_input")
    if not isinstance(ti, dict):
        return 0                       # unparsed input is silence, never a traceback
    fp = ti.get("file_path") or ti.get("path") or ""
    if not fp or not str(fp).endswith(".json"):
        return 0
    path = Path(str(fp))
    if not path.is_file():
        return 0
    out = section_reasons(path, os.environ.get("DMA_REPO_ROOT"))
    if not out:
        return 0
    text = render(out)
    if not text:
        return 0
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                             "additionalContext": text}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
