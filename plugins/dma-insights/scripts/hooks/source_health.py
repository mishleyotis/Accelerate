#!/usr/bin/env python3
"""PostToolUse: one line per raw-fallback call into source_health.jsonl,
plus a counts sidecar so a reader never re-scans the log (brief §6a).

Why a sidecar: the log is append-only and grows with every call; the
doctor and the rate gate want "how many 429s from EDGAR in the last hour"
and must not pay O(n) for it. `counts.json` holds per-source totals and a
rolling window of the last 200 outcomes, updated under the same lock as
the append. A reader that needs more than the window tail-scans the log
with `tail(n)`, never `read()`.

Never blocks (PostToolUse); never raises; never logs a payload body or a
token — only the tool, the source, an outcome class and a duration.
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import deque
from pathlib import Path

PREFIX = "mcp__plugin_dma-insights_"
SOURCES = ("evidence", "searxng", "fetch", "edgar", "parallel", "alphaxiv")
LOG_PATH = Path(os.environ.get("DMA_SOURCE_HEALTH_LOG") or "/root/.dma/source_health.jsonl")
WINDOW = 200


def source_of(tool: str) -> str | None:
    if not tool.startswith(PREFIX):
        return None
    server = tool[len(PREFIX):].split("__", 1)[0]
    return server if server in SOURCES else None


def outcome_of(response) -> str:
    """A class, never the body: ok | error:<kind> | empty."""
    text = ""
    if isinstance(response, dict):
        if response.get("isError") or response.get("is_error"):
            text = json.dumps(response)[:400].lower()
            if "429" in text or "too many" in text:
                return "error:429"
            if "403" in text:
                return "error:403"
            if "captcha" in text:
                return "error:captcha"
            if "timeout" in text or "timed out" in text:
                return "error:timeout"
            return "error:other"
        content = response.get("content")
        if content == [] or content is None and not response:
            return "empty"
        return "ok"
    if response in (None, "", [], {}):
        return "empty"
    return "ok"


def record(payload: dict, *, log_path: Path = LOG_PATH, clock=time.time) -> dict | None:
    tool = str(payload.get("tool_name") or "")
    source = source_of(tool)
    if not source:
        return None
    rec = {"ts": round(clock(), 3), "source": source, "tool": tool.split("__")[-1],
           "outcome": outcome_of(payload.get("tool_response")),
           "ms": payload.get("duration_ms") or payload.get("durationMs")}
    try:
        import fcntl
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            fh.write(json.dumps(rec) + "\n")
            counts_path = log_path.with_name("source_health_counts.json")
            try:
                counts = json.loads(counts_path.read_text()) if counts_path.exists() else {}
                if not isinstance(counts, dict):
                    counts = {}
            except (ValueError, OSError):
                counts = {}
            src = counts.setdefault(source, {"total": 0, "by_outcome": {}, "window": []})
            src["total"] += 1
            src["by_outcome"][rec["outcome"]] = src["by_outcome"].get(rec["outcome"], 0) + 1
            win = deque(src.get("window", []), maxlen=WINDOW)
            win.append([rec["ts"], rec["outcome"]])
            src["window"] = list(win)
            tmp = counts_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(counts))
            os.replace(tmp, counts_path)
    except Exception as exc:  # noqa: BLE001
        print(f"dma-insights source_health: not recorded ({type(exc).__name__}: {exc})", file=sys.stderr)
    return rec


def tail(n: int, log_path: Path = LOG_PATH) -> list[dict]:
    """The last n records without reading the whole file."""
    try:
        with open(log_path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            block, data = 4096, b""
            while size > 0 and data.count(b"\n") <= n:
                step = min(block, size)
                size -= step
                fh.seek(size)
                data = fh.read(step) + data
        lines = data.splitlines()[-n:]
        return [json.loads(l) for l in lines if l.strip()]
    except (OSError, ValueError):
        return []


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        return 0
    if not isinstance(payload, dict):
        return 0
    record(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
