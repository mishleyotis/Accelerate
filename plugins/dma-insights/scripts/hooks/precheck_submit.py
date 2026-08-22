#!/usr/bin/env python3
"""PreToolUse hook on submit_page_payload — the five-second refusal.

Catches, BEFORE the network round-trip, only what the connector's gates will
certainly refuse. Blocking here (exit 2) costs nothing and saves a submit
cycle; a check that might false-block does not belong in this file — the
connector's verdict is the authority, this is the doormat.

Checks, deliberately minimal:
  1. Envelope: every section object carries produced_at, producer_version,
     e_ids and internal_only (the contract's four required envelope fields).
  2. Platform cards: fit_score null without the engine's own `state` on the
     card (CG-30 refuses exactly this).
  3. Banned vocabulary: an M5/Transformational band word (invariant 6 — the
     band does not exist), or a colour hex in payload content (invariant 7).
Anything else is the connector's job.
"""
import json
import re
import sys

ENVELOPE = ("produced_at", "producer_version", "e_ids", "internal_only")
HEX = re.compile(r"#[0-9a-fA-F]{6}\b")
M5 = re.compile(r"\b(M5|Transformational)\b")


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0                       # unreadable event: never block blind
    tool_input = event.get("tool_input") or {}
    payload = tool_input.get("payload")
    if not isinstance(payload, dict):
        return 0                       # chunked path: assembled server-side

    problems = []
    for name, body in payload.items():
        if not isinstance(body, dict):
            continue
        missing = [k for k in ENVELOPE if k not in body]
        if missing:
            problems.append(f"{name}: envelope missing {', '.join(missing)}")
        if name == "platform_story":
            for i, card in enumerate(body.get("platforms") or []):
                if isinstance(card, dict) and card.get("fit_score") is None \
                        and not card.get("state"):
                    problems.append(
                        f"platform_story.platforms[{i}]: fit_score is null "
                        "with no engine state on the card — CG-30 refuses "
                        "this; call get_platform_fit and carry its state")
    blob = json.dumps(payload)
    if M5.search(blob):
        problems.append("an M5/Transformational band word is in the payload "
                        "— four bands exist (invariant 6)")
    if HEX.search(blob):
        problems.append("a colour hex is in the payload — no colour in any "
                        "payload (invariant 7); send the flag, not the hex")

    if problems:
        sys.stderr.write(
            "dma-insights precheck refused this submit before the network "
            "round-trip; the connector's gates would refuse it too:\n- "
            + "\n- ".join(problems) + "\n")
        return 2

    # PASSED — and this hook owns the decision for this tool.
    #
    # autoapprove_connector.py deliberately stands aside for submit_page_payload
    # so that exactly one hook decides it. That makes the approval this file's
    # job: without it a scheduled session stops here on a permission prompt no
    # human will ever see (measured 2026-08-21), and the refusal path above
    # would never get the chance to be useful.
    #
    # Approving only on the clean path is the point — the checks above still
    # block, and they block BEFORE the network round-trip, which is the whole
    # reason this file exists.
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "permissionDecisionReason": (
            "dma-insights precheck passed: envelopes complete, no null "
            "fit_score without engine state, no banned band word or colour "
            "hex. The connector's own gates remain the authority."),
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
