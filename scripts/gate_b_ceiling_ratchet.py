#!/usr/bin/env python3
"""CI Gate B — the ceiling ratchet (Implementation Plan S.3).

The build fails if any corpus gate ceiling in
packages/shared/corpus_gates.json is HIGHER than in the base commit, and
names the gate. Ceilings only ratchet down: the pressure to raise one
arrives exactly when everyone is busy shipping, so the check lives at the
moment of the commit.

Usage: gate_b_ceiling_ratchet.py [BASE_GIT_REF]
BASE_GIT_REF defaults to HEAD~1; CI passes the PR base SHA.
"""
import json
import subprocess
import sys
from pathlib import Path

GATES_PATH = "packages/shared/corpus_gates.json"
ROOT = Path(__file__).resolve().parent.parent


def load_at(ref: str):
    try:
        blob = subprocess.run(
            ["git", "show", f"{ref}:{GATES_PATH}"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout
    except subprocess.CalledProcessError:
        return None  # file absent at base — nothing to ratchet against
    return json.loads(blob)


def main() -> int:
    base_ref = sys.argv[1] if len(sys.argv) > 1 else "HEAD~1"
    current = json.loads((ROOT / GATES_PATH).read_text(encoding="utf-8"))
    base = load_at(base_ref)
    if base is None:
        print(f"Gate B passed: {GATES_PATH} absent at {base_ref}; all gates are new.")
        return 0
    failures = []
    for name, gate in current.get("gates", {}).items():
        prev = base.get("gates", {}).get(name)
        if prev is None:
            continue  # new gate — allowed at any measured level
        if float(gate["ceiling"]) > float(prev["ceiling"]):
            failures.append(
                f"gate '{name}': ceiling raised {prev['ceiling']} -> {gate['ceiling']}"
            )
    if failures:
        print(f"GATE B FAILED — corpus ceilings only ratchet down (base {base_ref}):")
        print("\n".join(failures))
        return 1
    print(f"Gate B passed: no ceiling raised relative to {base_ref}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
