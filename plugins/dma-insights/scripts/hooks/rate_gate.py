#!/usr/bin/env python3
"""PreToolUse backstop on the RAW fallback connectors only (brief §6a).

The evidence engine enforces every upstream limit centrally; this hook is
the plugin-side belt for the four escape hatches an agent may call
directly — SearXNG, Fetch, EDGAR and Parallel through their plugin-scoped
names — so a session that bypasses the engine still cannot burst a source.

  * one token bucket per source, shared across every process on the host
    through a state file under a `fcntl` lock (5s timeout);
  * over budget -> exit 2 with a redirect to `research_brief` (the engine
    path), never a silent wait;
  * FAIL OPEN: a corrupt or unreadable state file, a lock timeout, an
    unparseable payload — the call is allowed and a warning is logged.
    A guard that denies on its own bug stops the research it exists to
    make cheaper.

Buckets (per source, per host): searxng 2/s burst 4; fetch 1/s burst 2;
edgar 4/s burst 4 (half the engine's 8/s, so the two together stay under
SEC's 10/s); parallel 0.5/s burst 2 (anonymous tier, measured ceiling
pending Phase D). Tool names are the plugin-scoped form the manifests use.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

PREFIX = "mcp__plugin_dma-insights_"
SOURCES = {          # server segment -> (rate per second, burst)
    "searxng": (2.0, 4),
    "fetch": (1.0, 2),
    "edgar": (4.0, 4),
    "parallel": (0.5, 2),
}
STATE_PATH = Path(os.environ.get("DMA_RATE_GATE_STATE") or "/root/.dma/rate_gate.json")
LOCK_TIMEOUT_S = 5.0

REDIRECT = (
    "dma-insights rate gate: the {source} fallback is over its budget "
    "({rate}/s, burst {burst}). Use the evidence engine instead — "
    "`research_brief` (search → cards) or `expand_context` / `verify_cards` — "
    "which absorbs rate limits centrally, caches, and coalesces identical "
    "queries. The raw connector is for an engine outage or a disputed card; "
    "retry it after {wait:.1f}s if you must."
)


def source_of(tool: str) -> str | None:
    if not tool.startswith(PREFIX):
        return None
    rest = tool[len(PREFIX):]
    server = rest.split("__", 1)[0]
    return server if server in SOURCES else None


def _lock(fh, timeout: float, now=time.monotonic, sleep=time.sleep) -> bool:
    import fcntl
    deadline = now() + timeout
    while True:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (BlockingIOError, OSError):
            if now() >= deadline:
                return False
            sleep(0.05)


def take(source: str, *, state_path: Path = STATE_PATH, clock=time.time,
         lock=_lock) -> tuple[bool, float, str]:
    """(allowed, wait_seconds, note). Any failure -> allowed (fail open)."""
    rate, burst = SOURCES[source]
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(state_path, "a+") as fh:
            if not lock(fh, LOCK_TIMEOUT_S):
                return True, 0.0, "lock timeout — allowed (fail open)"
            fh.seek(0)
            raw = fh.read()
            try:
                state = json.loads(raw) if raw.strip() else {}
                if not isinstance(state, dict):
                    raise ValueError("state is not an object")
            except (ValueError, TypeError):
                state = {}
                note = "corrupt state file reset — allowed (fail open)"
                fh.seek(0); fh.truncate(); fh.write(json.dumps({}))
                return True, 0.0, note
            b = state.get(source) or {"tokens": float(burst), "at": clock()}
            now = clock()
            tokens = min(float(burst), float(b.get("tokens", burst)) + (now - float(b.get("at", now))) * rate)
            if tokens >= 1.0:
                tokens -= 1.0
                allowed, wait = True, 0.0
            else:
                allowed, wait = False, (1.0 - tokens) / rate
            state[source] = {"tokens": tokens, "at": now}
            fh.seek(0); fh.truncate(); fh.write(json.dumps(state))
            return allowed, wait, ""
    except Exception as exc:  # noqa: BLE001
        return True, 0.0, f"{type(exc).__name__}: {exc} — allowed (fail open)"


def decide(payload: dict, **kw) -> tuple[int, str]:
    """(exit_code, message). 0 = allow silently; 2 = deny with reason."""
    tool = str(payload.get("tool_name") or "")
    source = source_of(tool)
    if not source:
        return 0, ""
    allowed, wait, note = take(source, **kw)
    if allowed:
        if note:
            print(f"dma-insights rate_gate: {note}", file=sys.stderr)
        return 0, ""
    rate, burst = SOURCES[source]
    return 2, REDIRECT.format(source=source, rate=rate, burst=burst, wait=wait)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        return 0                                  # unparseable -> allow
    if not isinstance(payload, dict):
        return 0                                  # a list, a string, null -> allow
    code, msg = decide(payload)
    if code == 2:
        print(msg, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
