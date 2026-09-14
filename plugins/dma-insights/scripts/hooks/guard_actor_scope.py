#!/usr/bin/env python3
"""PreToolUse guard on Bash: an agent writes its own work, or the turn stops.

WHY (measured 2026-09-14, MEM-0514): no write path in the engine checked
cell ownership. `append_evidence` and `append_search` took no actor at all;
`append_synthesis`, `declare_absence`, `record_challenge` and
`assessment.score` took one and used it only for attribution and
independence. The only cell-scope refusal anywhere was run-membership,
which is a different question. So `research-p1c1-producer` could write
every P3 cell in the run — sixteen lanes writing one workbook in parallel,
under a lock that serialises rows and says nothing about which rows — and
the containment was three sentences of prose: the SessionStart brief's
"Work only your own category", the manifest's description, and the
conductor's "what you never do".

The engine now refuses these writes itself (`ledger.assert_actor_scope`).
This hook is the seam in front of it, and it exists for one reason the
engine cannot serve: a refusal that arrives after the command has run has
already cost the turn, and a lane that has spent its turns is re-dispatched
— which is the shape that turned a $20 budget into $96.65. Denying at the
call keeps the lane's remaining turns.

ONE TABLE, TWO ENFORCERS. The rules are read from `engine/scope.py`, never
restated here: a guard with its own copy of the rule is the drift this
repository keeps removing. If the engine cannot be imported the hook is
silent — the ledger still refuses, so the boundary holds either way.

WHO IS ASKING. A headless lane cannot be identified from inside a hook: the
harness carries `agent_type` only within a subagent. `agent_run.py` puts the
name in the child's environment as DMA_ACTOR and every engine write CLI
defaults `--actor` to it, so this hook reads, in order: the command's own
`--actor`, the subagent's `agent_type`, then $DMA_ACTOR. An actor none of
those name is unconstrained, which is what a person at a terminal should be.

Fail-open on anything unparsable: a guard that bricks every Bash call when a
command shape changes is a worse failure than the refusal it duplicates.
"""
import json
import os
import re
import shlex
import sys
from pathlib import Path

#: `engine.cli <verb>` / `engine.memory note` -> the scope op. `synthesise`
#: and `challenge` are the two whose CLI verb differs from the ledger op.
_VERB_OP = {"search": "search", "evidence": "evidence", "attach": "attach",
            "synthesise": "synthesis", "absence": "absence",
            "challenge": "challenge", "note": "note"}

_CMD = re.compile(r"(?:python3?|py)\s+-m\s+engine\.(cli|memory)\s+(\w[\w-]*)")


def _engine_scope():
    """`engine.scope`, imported from the plugin this hook ships in."""
    root = Path(os.environ.get("CLAUDE_PLUGIN_ROOT")
                or Path(__file__).resolve().parents[2])
    sys.path.insert(0, str(root / "skills" / "dma-research"))
    from engine import scope                                    # noqa: PLC0415
    return scope


def _flags(argv, name):
    """Every value of a repeatable flag, in `--x v` and `--x=v` form."""
    out, want = [], f"--{name}"
    for i, tok in enumerate(argv):
        if tok == want and i + 1 < len(argv):
            out.append(argv[i + 1])
        elif tok.startswith(want + "="):
            out.append(tok.split("=", 1)[1])
    return [v for v in out if v and not v.startswith("-")]


def decide(command: str, actor_hint: str = "") -> str:
    """The reason to deny, or "" to stay silent."""
    m = _CMD.search(command or "")
    if not m:
        return ""
    op = _VERB_OP.get(m.group(2))
    if not op:
        return ""
    try:
        argv = shlex.split(command)
    except ValueError:
        return ""                      # an unclosed quote is not our business
    actor = (_flags(argv, "actor") or [""])[0] or actor_hint \
        or os.environ.get("DMA_ACTOR", "")
    cells = _flags(argv, "subcap")
    if op == "note":
        # The notebook's own category is the scope; the cells are checked
        # against it by the writer.
        cells = cells or _flags(argv, "category")
    try:
        scope = _engine_scope()
    except Exception:                                           # noqa: BLE001
        return ""                      # the ledger still refuses
    return scope.violation(actor, op, cells)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:                                           # noqa: BLE001
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    if not isinstance(command, str):
        return 0
    try:
        why = decide(command, str(payload.get("agent_type") or "").split(":")[-1])
    except Exception:                                           # noqa: BLE001
        return 0
    if not why:
        return 0
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": (
            f"{why}\n\nThe engine refuses this write too — this is the same "
            f"rule (engine/scope.py), stopped at the call so the refusal "
            f"does not cost you a turn."),
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
