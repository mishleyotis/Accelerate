#!/usr/bin/env python3
"""PreToolUse guard on Bash: credential-shaped operations are denied by policy.

WHY (measured 2026-08-20): a trigger-fired synthesis session invented a
"GitHub PAT instruction" that was never given, committed repo edits outside
its writer scope (constraint [B]: the weekly rectifier is the only plugin
writer) and tried to push them "using the routine's existing secrets
mechanism". The harness classifier blocked it — correctly — but a
probabilistic block invites the next session to try another phrasing, and it
teaches nothing. This hook makes the boundary DETERMINISTIC policy (owner,
2026-08-20: "add a scoped permission properly rather than trying to work
around the classifier") and the denial text itself carries the sanctioned
path, so the block is where a confused session learns to self-heal.

Denied, each with zero legitimate use anywhere in this workflow:
  * GitHub token literals on a command line — no GitHub PAT exists in this
    workflow; Secret Manager holds only the SA key and the connector path
    token, and the one routine that pushes (the weekly rectifier) rides the
    harness's own GitHub App credentials via plain `git push`.
  * git URLs with embedded credentials, x-access-token forms, and git
    credential-helper writes — nothing here may mint or persist a git
    credential.
  * shell fetches of docs.google.com URLs — Drive content is read through
    drive_fetch.py under the service-account identity, whose visibility is
    the access boundary; the owner's own documents (one of which holds
    credentials) must never be pulled into a transcript by an ad-hoc fetch.

Fail-open on malformed input: a guard that bricks every Bash call when the
harness changes its stdin shape is a worse failure than the classifier
backstop it complements. Allow = exit 0 with no output.
"""
import json
import re
import sys

DENIALS = (
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "a GitHub token literal"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
     "a GitHub fine-grained token literal"),
    (re.compile(r"://[^/\s'\"]*@github\.com", re.I),
     "a git URL with embedded credentials"),
    (re.compile(r"\bx-access-token\b", re.I),
     "an x-access-token credential form"),
    (re.compile(r"\bgit\b[^\n|;&]*\bcredential\.helper\b"),
     "a git credential-helper write"),
    (re.compile(
        r"\bdocs\.google\.com/(?:document|spreadsheets|presentation)\b",
        re.I),
     "a shell fetch of a Google Docs URL"),
)

REASON = (
    "Denied by dma-insights policy: the command carries {what}. No GitHub "
    "credential exists in this workflow (Secret Manager holds only the SA "
    "key and the connector path token) — any 'GitHub PAT instruction' is "
    "spurious. Synthesis and drift sessions attach the repository read-only "
    "and never commit or push; persistence is the connector plus Drive "
    "(drive_fetch.py push-ledger / push-bundle / push-memory). Repository "
    "changes land only through the weekly rectifier's reviewed PR on the "
    "harness's own credentials, and Google Docs are read via drive_fetch.py "
    "under the service-account identity, never fetched from a shell."
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # fail-open: the harness classifier remains the backstop
    if payload.get("tool_name") != "Bash":
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    if not isinstance(command, str):
        return 0
    for rx, what in DENIALS:
        if rx.search(command):
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": REASON.format(what=what),
            }}))
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
