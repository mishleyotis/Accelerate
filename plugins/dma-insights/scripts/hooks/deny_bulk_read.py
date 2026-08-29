#!/usr/bin/env python3
"""PreToolUse guard on Bash: the never-cat rule, actually enforced.

WHY THIS EXISTS. AUD-0101: R27 forbids `cat` on the knowledge-graph packs,
`engagement_set.json`, `evidence_index.json` and `ledger.jsonl`, and the
audit priced one violation at 116k-592k tokens — a run's whole budget spent
on one command. The rule existed in prose only: the v4.2 archive shipped no
hook mechanism at all, and the live plugin DOES ship a PreToolUse matcher on
Bash that returns a deterministic deny with a written reason
(`deny_credential_ops.py`) — proving the interception works and the team
knows how to build it — but no hook script mentioned any of the four paths.

So the enforcement slot was already there and already used. This points it at
the four paths, and the denial text names the cheap command that answers the
same question, because a block that does not teach the alternative just gets
rephrased.

Fail-open on malformed input, like its sibling: a guard that bricks every
Bash call when the harness changes its stdin shape is worse than the gap it
closes. Allow = exit 0 with no output.
"""
import json
import re
import sys

#: (path pattern, what to run instead). Every one of these files is designed
#: to be QUERIED, and every one has a reader that answers in tens of tokens.
BULK = (
    (re.compile(r"\bledger\.jsonl\b"),
     "ledger.jsonl",
     "`python3 -m engine.cli orient --run R --category C` for the state, or "
     "`... search`/`... evidence` to append. The ledger's readers return the "
     "answer; the file returns the whole run."),
    (re.compile(r"\bevidence_index\.json\b"),
     "evidence_index.json",
     "`python3 -m engine.cli orient` (the register is summarised in the work "
     "card) or the workbook's Evidence_Detail sheet, read row by row."),
    (re.compile(r"\bengagement_set\.json\b"),
     "engagement_set.json",
     "`python3 -m engine.cli orient --run R` — `worklist` is the same "
     "information, counted."),
    (re.compile(r"\bresearch_handoff\.json\b"),
     "research_handoff.json",
     "`python3 -m engine.cli handoff --run R` writes it; read the WORKBOOK "
     "for state, since the handoff is a projection and the workbook is the "
     "authority."),
    (re.compile(r"\bkg[/_][\w./-]*\.(?:json|jsonl)\b"),
     "a knowledge-graph pack",
     "`python3 -m engine.cli orient --run R --category C`, which serves one "
     "bound work card instead of the pack."),
    (re.compile(r"\bkg_pack[\w.-]*\b"),
     "a knowledge-graph pack",
     "`python3 -m engine.cli orient --run R --category C`."),
)

#: Commands that read a whole file into the transcript. `grep`, `head`,
#: `wc`, `jq -r '.x'` and friends are NOT here on purpose — a bounded read
#: is the behaviour this rule wants.
READERS = re.compile(
    r"(?:^|[|;&]\s*)\s*(?:sudo\s+)?(cat|bat|less|more|xxd|od|base64)\b")

REASON = (
    "Denied by dma-insights policy: this command reads {what} whole into the "
    "transcript. R27 forbids it because one such read costs between 116k and "
    "592k tokens — a run's entire budget on a single command, after which the "
    "turn dies mid-category and the resume path has to recover it.\n\n"
    "Run this instead: {instead}\n\n"
    "A BOUNDED read of the same file is allowed and always was — `grep`, "
    "`head -c`, `sed -n '1,40p'`, `jq` with a path, `wc -l`. The rule is "
    "against reading it ALL, not against looking."
)


def decide(command: str):
    if not READERS.search(command or ""):
        return None
    for rx, what, instead in BULK:
        if rx.search(command):
            return REASON.format(what=what, instead=instead)
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:            # noqa: BLE001 — fail open
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    if not isinstance(command, str):
        return 0
    reason = decide(command)
    if reason:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
