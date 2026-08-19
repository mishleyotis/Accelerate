#!/usr/bin/env python3
"""Gate K — a refused payload cannot be undetectable.

THE DEFECT. A submission that fails validation supersedes the passing row for
its page and then sits there. Nothing listed refusals across the corpus, so a
producer session that ended left no trace anything was outstanding, and all
three refusals measured on this build were found by a person reading a
verdict rather than by the system saying so.

Migration 0052 and `dma_mcp.rejections` close it. This gate asserts the wiring
is still there — a ledger nobody writes to is a comment, and the failure mode
is silent by construction: everything keeps working, the queue is simply
always empty.

Four claims, all read from source, no database:

  1. `submit_page_payload` records EVERY verdict, pass and fail. A pass is
     what closes the tickets a failure opened; recording only failures leaves
     a queue that never empties.
  2. The submit reply carries the identifiers back, so a producer can act on
     them without a second call.
  3. A corpus-wide read exists as an MCP tool — the read that did not exist.
  4. Safeguard results are excluded, per invariant 12.

Stdlib only, like the gates beside it.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    p = ROOT / rel
    if not p.exists():
        print(f"Gate K: {rel} is missing — the return path is gone entirely.")
        raise SystemExit(1)
    return p.read_text()


def main() -> int:
    fails = []

    submit = _read("apps/mcp/dma_mcp/submit.py")
    if "rejections.record_verdict" not in submit:
        fails.append(
            "submit_page_payload does not record verdicts in the rejection "
            "ledger. Every refusal it issues from now on is invisible the "
            "moment the session ends.")
    else:
        # It must run on EVERY submit. A call guarded by a failure test would
        # never close anything, and the queue would only grow.
        call = submit[submit.index("rejections.record_verdict"):]
        before = submit[:submit.index("rejections.record_verdict")]
        tail = before.rsplit("\n", 12)[-1] if "\n" in before else before
        window = before[-600:]
        if re.search(r'if\s+status\s*==\s*[\'"]FAIL[\'"]\s*:', window):
            fails.append(
                "the ledger is written only when the verdict FAILS. A pass is "
                "what CLOSES the tickets a failure opened; guarded like this "
                "the queue never empties.")
        del call, tail

    if '"rejections": rejection_report' not in submit:
        fails.append(
            "the submit reply does not return the rejection identifiers, so a "
            "producer has to make a second call to learn what its own "
            "submission opened or closed.")

    server = _read("apps/mcp/server.py")
    if "def list_open_rejections" not in server:
        fails.append(
            "no MCP tool lists open rejections across the corpus. That is the "
            "read that did not exist: a session must be able to ask whether "
            "anything is outstanding WITHOUT already knowing which run to ask "
            "about, because not knowing is why refusals went unnoticed.")

    rej = _read("apps/mcp/dma_mcp/rejections.py")
    if 'startswith("SG")' not in rej:
        fails.append(
            "safeguard results are no longer excluded from the queue. The "
            "charter says a failing SG discloses and still promotes, so it is "
            "not an outstanding repair — queueing them makes the queue "
            "permanently non-empty and trains everyone to ignore it.")
    if "attempts" not in rej:
        fails.append(
            "the ledger no longer counts attempts. A count past two is how "
            "'this is the fourth try at the same reason' becomes visible "
            "instead of being rediscovered each session.")

    mig = ROOT / "migrations" / "versions" / "0052_rejection_ledger.py"
    if not mig.exists():
        fails.append("migration 0052 is gone; the ledger has no table.")
    else:
        m = mig.read_text()
        if "ON DELETE SET NULL" not in m:
            fails.append(
                "the ledger's foreign keys onto `submissions` no longer SET "
                "NULL, which makes this table a veto on deleting a "
                "submission — the same shape that made a run undeletable one "
                "migration earlier.")
        if "CREATE OR REPLACE VIEW open_rejections" not in m:
            fails.append("the open_rejections view is gone; the corpus-wide "
                         "read has nothing to read.")

    if fails:
        print(f"Gate K: {len(fails)} break(s) in the refused-payload return path:")
        for f in fails:
            print(f"  · {f}")
        return 1
    print("Gate K: refusals are named, queued, returned to the caller and "
          "closable by evidence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
