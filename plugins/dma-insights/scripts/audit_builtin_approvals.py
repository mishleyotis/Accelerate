#!/usr/bin/env python3
"""Which of the pipeline's OWN commands would still prompt — measured by
running the real hook over every command the agents and Routines are told
to run.

    python3 scripts/audit_builtin_approvals.py [--json] [--strict] [--show]

WHY THIS EXISTS. `audit_autoapprove.py` answers the MCP half: every connector
tool a session attaches is approved or refused on the record. It says nothing
about Bash, Write and Edit — and on 2026-09-03 those were the prompts the
owner was still answering, because every agent writes through
`python3 -m engine.…` and no hook ruled on it.

`hooks/autoapprove_builtins.py` now rules on them, by a grammar. A grammar
can be wrong in a way an allowlist cannot: a command the manifests actually
issue may fall outside it, and the only way to know is to feed it the real
commands. So this harvests every fenced or backticked invocation from the
agent manifests, the skill files and the Routine prompts, normalises the
placeholders a prompt uses (`<ROOT>`, `${CLAUDE_PLUGIN_ROOT}`, `$RUN`), and
runs the REAL hook — a subprocess per command, the real PreToolUse event —
then reports which would prompt.

Verdicts per command:

    ALLOWED    the hook approves it — headless
    GUARDED    a deny guard would refuse it (credential shape, bulk read):
               correct, and not a prompt — the session is told why
    PROMPTS    the hook draws no decision; in a scheduled session this is a
               hang. THE FINDING.

`--strict` exits non-zero on any PROMPTS row. A PROMPTS row is either a
command the grammar should learn (a plugin script it does not recognise, a
verb every producer needs) or a manifest telling an agent to do something a
headless session must not (a push, a credential read) — the report says
which, and both are worth a look.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
HOOK = HERE / "hooks" / "autoapprove_builtins.py"
REPO = PLUGIN.parents[1]

sys.path.insert(0, str(HERE / "hooks"))
import autoapprove_builtins as AB  # noqa: E402

#: Where commands are written down for an agent or a Routine to run.
SOURCES = [PLUGIN / "agents", PLUGIN / "skills" / "dma-research",
           PLUGIN / "skills" / "dma-surface-production",
           PLUGIN / "docs" / "ROUTINES.md", PLUGIN / "commands"]

#: A command line as a manifest writes it: fenced or backticked, starting
#: with one of the verbs the pipeline actually uses.
VERBS = r"(?:python3?|bash|git|ls|grep|sed|head|tail|jq|cat|mkdir|cp|find|wc)"
FENCED = re.compile(r"```(?:bash|sh|shell|console)?\n(.*?)```", re.S)
INLINE = re.compile(rf"`({VERBS}\s[^`\n]{{3,400}})`")

#: Placeholders a prompt uses, normalised to the shapes a session would
#: actually type. Values are chosen INSIDE the write roots so a redirection
#: into `<ROOT>` is judged as the real one would be.
PLACEHOLDERS = [
    (re.compile(r"\$\{?CLAUDE_PLUGIN_ROOT\}?"), "plugins/dma-insights"),
    (re.compile(r"<ROOT>|\$ROOT|\$\{ROOT\}"), "/root/.dma/runs/R-1"),
    (re.compile(r"<RUN_ID>|<RUN>|<R>|\$RUN_ID|\$RUN|\$\{RUN\}"), "R-1"),
    (re.compile(r"<[^<>\n]{1,80}>"), "X"),          # <page|all>, <the folder link>
    (re.compile(r"\{[A-Za-z|_-]+\}"), "X"),         # {research|assessment}
    (re.compile(r"\[--[A-Za-z-]+\]"), ""),          # [--promote] — optional flag
    (re.compile(r"\b([a-z_]+)(?:\|[a-z_]+)+\b"), r"\1"),   # payload|challenge|report
    (re.compile(r"\$[A-Z_]{2,}"), "X"),
    (re.compile(r"\.\.\.|…"), ""),
]

#: A backticked "command" whose second word is English is a sentence that
#: happens to start with a verb name (`tail is CG-15's template prose`).
_STOPWORDS = {"is", "are", "the", "a", "an", "of", "with", "to", "and", "or",
              "was", "were", "it", "its", "in", "on", "for", "that", "this"}

#: The Routine canon: only the FENCED prompts under `### 2x` are commands a
#: session runs; the Cloud Scheduler section describes Jobs, whose
#: entrypoints (`python -m dma_worker.enrichment`) no session ever types.
_CANON_HEAD = re.compile(r"^### (2[a-z-]*) · ", re.M)


def _routine_prompts(text: str) -> str:
    heads = list(_CANON_HEAD.finditer(text))
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        fence = re.search(r"```\n(.*?)\n```", text[m.start():end], re.S)
        if fence:
            out.append(fence.group(1))
    return "\n".join(out)


def harvest() -> list[dict]:
    """Every command line the sources tell somebody to run, with its file."""
    out, seen = [], set()
    for src in SOURCES:
        files = [src] if src.is_file() else sorted(src.rglob("*.md"))
        for f in files:
            text = f.read_text(errors="ignore")
            if f.name == "ROUTINES.md":
                text = _routine_prompts(text)
            lines: list[str] = []
            for block in FENCED.findall(text):
                for ln in block.splitlines():
                    ln = ln.strip()
                    if re.match(rf"^(?:\$ )?{VERBS}\s", ln):
                        lines.append(ln.lstrip("$ ").strip())
            lines += [m.strip() for m in INLINE.findall(text)]
            for ln in lines:
                # a prompt's line continuation
                ln = ln.rstrip("\\").strip()
                if not ln or ln in seen:
                    continue
                words = ln.split()
                if len(words) > 1 and words[1].lower() in _STOPWORDS:
                    continue                      # a sentence, not a command
                if "<<" in ln and "\n" not in ln:
                    continue                      # a heredoc MENTIONED, no body
                if re.search(r"-m\s+[A-Za-z_.]*(\.|…|\.\.\.)\s*$", ln) \
                        or re.search(r"-m\s+[A-Za-z_.]*\.(…|\.\.\.)", ln):
                    continue                      # `python3 -m engine.…` — a
                                                  # FAMILY named in prose, not
                                                  # a module a session runs
                seen.add(ln)
                out.append({"file": str(f.relative_to(PLUGIN)), "command": ln})
    return out


def normalise(cmd: str) -> str:
    for rx, rep in PLACEHOLDERS:
        cmd = rx.sub(rep, cmd)
    return cmd.strip()


def ask_the_hook(command: str, cwd: str | None = None) -> str | None:
    """The real hook, with the cwd a session running THIS source would have:
    a skill's SKILL.md is followed from the skill directory, so its relative
    `../../scripts/x.py` resolves from there."""
    event = {"tool_name": "Bash", "hook_event_name": "PreToolUse",
             "tool_input": {"command": command}, "cwd": cwd or str(REPO)}
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event),
                       capture_output=True, text=True, timeout=60, cwd=str(REPO))
    if r.returncode != 0 or not r.stdout.strip():
        return None
    try:
        return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"]
    except (ValueError, KeyError):
        return None


def classify(command: str, cwd: str | None = None) -> str:
    if AB.guards_would_deny(command):
        return "GUARDED"
    return "ALLOWED" if ask_the_hook(command, cwd) == "allow" else "PROMPTS"


def _cwd_for(rel_file: str) -> str:
    """A skill file is followed from its skill directory; everything else
    from the checkout root."""
    parts = Path(rel_file).parts
    if len(parts) >= 2 and parts[0] == "skills":
        return str(PLUGIN / parts[0] / parts[1])
    return str(REPO)


def audit() -> dict:
    rows = []
    for h in harvest():
        cmd = normalise(h["command"])
        rows.append({**h, "normalised": cmd,
                     "verdict": classify(cmd, _cwd_for(h["file"]))})
    by = {}
    for r in rows:
        by.setdefault(r["verdict"], []).append(r)
    return {"total": len(rows), "rows": rows,
            "allowed": by.get("ALLOWED", []), "guarded": by.get("GUARDED", []),
            "prompts": by.get("PROMPTS", [])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when any harvested command would prompt")
    ap.add_argument("--show", action="store_true",
                    help="list the ALLOWED commands too")
    a = ap.parse_args(argv)
    out = audit()
    if a.json:
        print(json.dumps(out, indent=2))
        return 1 if (a.strict and out["prompts"]) else 0
    print(f"{len(out['allowed'])}/{out['total']} harvested command(s) auto-approved · "
          f"{len(out['guarded'])} refused by a guard on purpose · "
          f"{len(out['prompts'])} would PROMPT")
    if a.show:
        for r in out["allowed"]:
            print(f"  ✓ {r['normalised'][:110]}")
    for r in out["guarded"]:
        print(f"  ■ GUARDED  {r['file']}: {r['normalised'][:100]}")
    for r in out["prompts"]:
        print(f"  ✗ PROMPTS  {r['file']}: {r['normalised'][:100]}")
    if out["prompts"]:
        print("\nEach PROMPTS row is a command a scheduled session would hang on. "
              "Either the grammar in hooks/autoapprove_builtins.py should learn "
              "it, or the manifest is telling an agent to do something a "
              "headless session must not.")
        return 1 if a.strict else 0
    print("\nNo command the manifests or Routines issue would prompt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
