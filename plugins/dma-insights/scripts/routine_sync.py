#!/usr/bin/env python3
"""Reconcile the routines canon against the Routines that actually fire.

WHY THIS EXISTS, and it is the defect it was born from. `docs/ROUTINES.md`
says of the Claude-session routines: "They have no reconciler today; this
file is their declaration." That sentence was the whole bug. On 2026-08-31
the intake Routine's STEP 0a was rewritten to run `doctor.py --heal` instead
of stopping on a stale plugin — the canon was edited, tests were written
against the canon, the tests passed, the change was committed and pushed to
the default branch, and then the Routine fired and stopped on a stale plugin
exactly as before, because THE PROMPT THAT FIRES LIVES IN THE TRIGGER RECORD
and nothing had ever copied the file into it.

Every one of those steps looked like progress. None of them touched
production. A declaration with no reconciler is a document that describes a
system it does not control, and the more carefully it is maintained the more
convincing the illusion gets: the app-side Cloud Scheduler routines in the
same file have had `setup_routines.py` since the beginning, so half the file
was enforced and half was fiction, with nothing in the shape of either half
to say which was which.

    routine_sync.py diff                 # canon vs live, per routine
    routine_sync.py diff --routine 2g
    routine_sync.py push --routine 2g    # write the canon prompt to the trigger
    routine_sync.py push --all --yes

WHAT IT CANNOT DO, stated so nobody builds on a false floor. This script has
no credentials of its own: it reads the canon, and it renders the exact
payload a caller passes to the `update_trigger` MCP tool. A session with
that tool applies it. So `push` PRINTS the call rather than making it, and
`diff` needs the live prompts supplied — `--live <file>` — because a
subprocess cannot reach the Routines API. That split is deliberate: a
reconciler that silently could not reach production is the failure this file
exists to end, so this one says which half it did.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

CANON = Path(__file__).resolve().parents[1] / "docs" / "ROUTINES.md"

#: A canon heading: `### 2g · dma-assessment-intake — \`cron\` · STATE (...)`
_HEAD = re.compile(r"^### (2[a-z-]*) · ([a-z0-9-]+) — .*$", re.M)
#: The trigger id, where the heading carries one. A section with no id is a
#: routine that does not exist yet (2a), and pushing one is a create, not an
#: update — a different act with a different tool, so it is refused here.
_TRIG = re.compile(r"(trig_[A-Za-z0-9]+)")


class SyncRefusal(RuntimeError):
    """The canon and the request disagree about something structural."""


def sections(canon: Path = CANON) -> dict[str, dict]:
    """Every canon routine section: key -> {name, trigger_id, prompt}."""
    text = canon.read_text()
    heads = list(_HEAD.finditer(text))
    out = {}
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        block = text[m.start():end]
        fence = re.search(r"```\n(.*?)\n```", block, re.S)
        tid = _TRIG.search(m.group(0))
        out[m.group(1)] = {
            "key": m.group(1),
            "name": m.group(2),
            "trigger_id": tid.group(1) if tid else None,
            "live": "LIVE" in m.group(0),
            "prompt": fence.group(1) if fence else None,
            "heading": m.group(0).strip(),
        }
    return out


def _norm(s: str) -> list[str]:
    """Trailing whitespace is not drift; anything else is."""
    return [ln.rstrip() for ln in (s or "").splitlines()]


def compare(canon_prompt: str, live_prompt: str) -> dict:
    a, b = _norm(live_prompt), _norm(canon_prompt)
    same = a == b
    diff = [] if same else list(difflib.unified_diff(
        a, b, fromfile="live (what fires)", tofile="canon (what is written)",
        lineterm="", n=1))
    # The properties worth naming even when the whole diff is long, because
    # these are the ones a firing's behaviour actually turns on.
    marks = {}
    for label, needle in (("heals the plugin", "doctor.py --heal"),
                          ("derives connectors", "connector_contract"),
                          ("requires firecrawl", "Firecrawl")):
        marks[label] = {"canon": needle in (canon_prompt or ""),
                        "live": needle in (live_prompt or "")}
    return {"in_sync": same, "diff": diff, "markers": marks,
            "canon_chars": len(canon_prompt or ""),
            "live_chars": len(live_prompt or "")}


def load_live(path: str) -> dict[str, str]:
    """`{name_or_trigger_id: prompt}` as supplied by the caller.

    Accepts the shape `list_triggers` returns (a list of objects, or an
    object with a `triggers` list), or a plain name->prompt mapping.
    """
    raw = json.loads(sys.stdin.read() if path == "-"
                     else Path(path).read_text())
    # The API's envelope. Measured 2026-09-03: `list_triggers` returns
    # `{"data": [...]}`, and each record carries the prompt that fires under
    # `derived_state.prompt` (or, older, as the first user event's message),
    # NOT a top-level `prompt`. Read as `prompt` only, this reported every
    # live Routine as NOT IN THE SUPPLIED LIVE SET — a reconciler blind to
    # the shape it reconciles, which is the defect this file exists to end.
    if isinstance(raw, dict):
        for key in ("triggers", "data", "items", "results"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
    if isinstance(raw, dict):
        return {k: v for k, v in raw.items() if isinstance(v, str)}
    out = {}
    for t in raw or []:
        if not isinstance(t, dict):
            continue
        for key in (t.get("name"), t.get("id")):
            if key:
                out[key] = live_prompt(t)
    return out


def live_prompt(t: dict) -> str:
    """The prompt a trigger record actually fires, wherever the API put it."""
    if isinstance(t.get("prompt"), str) and t["prompt"]:
        return t["prompt"]
    ds = t.get("derived_state") or {}
    if isinstance(ds, dict) and isinstance(ds.get("prompt"), str) and ds["prompt"]:
        return ds["prompt"]
    try:
        for ev in (t.get("session_request") or {}).get("events") or []:
            msg = ((ev.get("payload") or {}).get("internal_anthropic_catchall")
                   or {}).get("message") or {}
            content = msg.get("content")
            if isinstance(content, str) and content:
                return content
            if isinstance(content, list):
                text = "".join(b.get("text", "") for b in content
                               if isinstance(b, dict))
                if text:
                    return text
    except AttributeError:
        pass
    return ""


def push_payload(sec: dict) -> dict:
    """The exact `update_trigger` arguments for one canon section."""
    if not sec["prompt"]:
        raise SyncRefusal(
            f"§{sec['key']} ({sec['name']}) carries no fenced prompt — there "
            f"is nothing to push, and pushing an empty prompt would blank a "
            f"live Routine")
    if not sec["trigger_id"]:
        raise SyncRefusal(
            f"§{sec['key']} ({sec['name']}) names no trigger id, so it does "
            f"not exist yet. Creating a Routine is a different act from "
            f"updating one — use create_trigger deliberately rather than "
            f"having a sync script conjure a schedule nobody chose")
    return {"trigger_id": sec["trigger_id"], "prompt": sec["prompt"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("diff", help="canon vs live, per routine")
    d.add_argument("--routine", help="one section key, e.g. 2g")
    d.add_argument("--live", required=True,
                   help="JSON of live triggers (list_triggers output); "
                        "- for stdin")
    d.add_argument("--json", action="store_true")
    d.add_argument("--full", action="store_true",
                   help="print the whole unified diff, not just the markers")
    p = sub.add_parser("push", help="render the update_trigger call(s)")
    p.add_argument("--routine")
    p.add_argument("--all", action="store_true")
    p.add_argument("--canon", default=None)
    d.add_argument("--canon", default=None)
    a = ap.parse_args(argv)

    canon = Path(a.canon) if getattr(a, "canon", None) else CANON
    secs = sections(canon)

    try:
        if a.cmd == "push":
            keys = ([a.routine] if a.routine
                    else [k for k, s in secs.items() if s["live"]]
                    if a.all else [])
            if not keys:
                print("name a --routine or pass --all", file=sys.stderr)
                return 2
            print(json.dumps([push_payload(secs[k]) for k in keys
                              if k in secs], indent=2))
            print("\n# Apply each of these with the update_trigger MCP tool. "
                  "This script holds no credentials and made no call.",
                  file=sys.stderr)
            return 0

        live = load_live(a.live)
        keys = [a.routine] if a.routine else sorted(secs)
        drift, rows = [], []
        for k in keys:
            s = secs.get(k)
            if not s:
                raise SyncRefusal(f"no §{k} in {canon}")
            if not s["live"]:
                rows.append({"routine": k, "name": s["name"],
                             "state": "NOT LIVE — nothing to reconcile"})
                continue
            lp = live.get(s["name"]) or live.get(s["trigger_id"] or "")
            if lp is None:
                rows.append({"routine": k, "name": s["name"],
                             "state": "NOT IN THE SUPPLIED LIVE SET"})
                drift.append(k)
                continue
            c = compare(s["prompt"] or "", lp)
            rows.append({"routine": k, "name": s["name"],
                         "state": "in sync" if c["in_sync"] else "DRIFTED",
                         **c})
            if not c["in_sync"]:
                drift.append(k)

        if a.json:
            print(json.dumps({"drifted": drift, "routines": rows}, indent=2))
        else:
            for r in rows:
                print(f"{r['routine']:>3} {r['name']:<28} {r['state']}")
                for label, m in (r.get("markers") or {}).items():
                    if m["canon"] != m["live"]:
                        print(f"      {label}: canon={m['canon']} "
                              f"live={m['live']}")
                if a.full:
                    for ln in r.get("diff") or []:
                        print(f"      {ln}")
            if drift:
                print(f"\nDRIFTED: {', '.join(drift)} — the file is not what "
                      f"fires. `routine_sync.py push --routine <key>` renders "
                      f"the update_trigger call that closes it.")
        return 1 if drift else 0

    except SyncRefusal as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
