#!/usr/bin/env python3
"""stdio -> streamable-HTTP bridge for the research-layer services.

Reuses `mcp_proxy.py`'s forward loop unchanged (header refresh, 401 re-mint,
session replay) and swaps only the header minter: `evidence_auth_headers.sh`
with THIS service's audience and secret. The connector's own proxy and its
headers helper are not modified (brief §7.1).

    evidence_proxy.py <base_url> --secret <secret-name> [--segment]

`--segment`: the service's capability is a URL path segment (/mcp-<token>,
the Supergateway backends), so the token the helper returns under the
pseudo-header X-DMA-Path-Segment is placed in the path and never sent as a
header. Without it the token travels as X-DMA-Path-Token (the engine).

Unresolved `${user_config...}` placeholders fall back to the
DMA_<SERVICE>_HOST environment variable, then to the service's production
URL, exactly as mcp_proxy does. No token value is ever printed.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mcp_proxy  # noqa: E402
import research_tool_surface as surface  # noqa: E402

#: Cloud Run URLs in one project share the project's hash suffix; the
#: defaults are what deploy-evidence.sh will produce for each new service.
DEFAULTS = {
    "dmai-evidence-path-token": "https://dmai-evidence-dukrne5v4a-uc.a.run.app",
    "dmai-searxng-path-token": "https://dmai-searxng-dukrne5v4a-uc.a.run.app",
    "dmai-fetch-path-token": "https://dmai-fetch-dukrne5v4a-uc.a.run.app",
    "dmai-edgar-path-token": "https://dmai-edgar-dukrne5v4a-uc.a.run.app",
}

_cfg = {"aud": "", "secret": "", "segment": False, "path_token": None}

#: Where this proxy records whether its service answered `initialize`, one
#: small file per service, read by hooks/search_order.py (the free-chain
#: order steps aside when the engine is down) and by the doctor. Never a
#: token: service, available, reason, ts.
LAYER_STATE_DIR = Path(os.environ.get("DMA_RESEARCH_LAYER_STATE") or "/root/.dma/research_layer")


def mark_available(available: bool, reason: str | None) -> None:
    """Best effort; a marker that cannot be written costs nothing."""
    try:
        service = str(_cfg.get("secret") or "").replace("dmai-", "").replace("-path-token", "") or "unknown"
        LAYER_STATE_DIR.mkdir(parents=True, exist_ok=True)
        path = LAYER_STATE_DIR / f"{service}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"service": service, "available": bool(available),
                                   "reason": (reason or "")[:200] or None, "ts": time.time()}))
        os.replace(tmp, path)
    except Exception:                                           # noqa: BLE001
        pass


def _mint_headers() -> dict:
    """The one function swapped: same shape as mcp_proxy._mint_headers."""
    mode = "segment" if _cfg["segment"] else "header"
    try:
        out = subprocess.run(
            ["bash", str(HERE / "evidence_auth_headers.sh"), _cfg["aud"], _cfg["secret"], mode],
            capture_output=True, text=True, timeout=60)
        hdrs = json.loads(out.stdout.strip() or "{}")
    except Exception as e:  # noqa: BLE001
        print(f"evidence_proxy: header mint failed: {e}", file=sys.stderr)
        hdrs = {}
    seg = hdrs.pop("X-DMA-Path-Segment", None)
    if seg:
        _cfg["path_token"] = seg
    mcp_proxy._state["headers"] = hdrs
    mcp_proxy._state["minted"] = time.time()
    return hdrs


def resolve_base(raw: str, secret: str) -> str:
    raw = (raw or "").strip()
    env_key = "DMA_" + secret.replace("-path-token", "").replace("dmai-", "").upper() + "_HOST"
    if not raw or "${" in raw:
        raw = os.environ.get(env_key, DEFAULTS.get(secret, ""))
    return raw.rstrip("/")


def endpoint(base: str) -> str:
    """The URL to POST to; in segment mode the token is part of it."""
    if _cfg["segment"]:
        if _cfg["path_token"] is None:
            _mint_headers()
        tok = _cfg["path_token"] or "missing"
        return f"{base}/mcp-{tok}"
    return base if base.endswith("/mcp") else base + "/mcp"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("base_url")
    ap.add_argument("--secret", required=True)
    ap.add_argument("--segment", action="store_true")
    a = ap.parse_args(argv)
    base = resolve_base(a.base_url, a.secret)
    _cfg.update(aud=base, secret=a.secret, segment=a.segment)
    mcp_proxy._mint_headers = _mint_headers           # the swap
    _live["emit"] = _write
    # The URL is resolved lazily: in segment mode it needs the capability
    # token, and minting that (gcloud + Secret Manager, up to 60 s) on the
    # main thread before `initialize` was answered is half of what cost the
    # CLI's 30 s connect window.
    url_of = lambda: endpoint(base)                   # noqa: E731
    # One proxy process serves EVERY agent in the session, so a tool call
    # handled inline made each collector wait behind the others' briefs (a
    # brief runs minutes). Each call runs on its own worker; heavy calls pass
    # the admission gate (`admitted`); the handshake, listings and
    # notifications stay in order on this thread.
    mcp_proxy.TIMEOUT_S = CALL_TIMEOUT_S
    slots = threading.BoundedSemaphore(MAX_PENDING_CALLS)

    def run(msg: dict) -> None:
        try:
            for reply in admitted(url_of, msg):
                _write(reply)
        finally:
            slots.release()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("method") == "tools/call" and msg.get("id") is not None:
            slots.acquire()
            threading.Thread(target=run, args=(msg,), daemon=True).start()
            continue
        for reply in serve(url_of, msg):
            _write(reply)
    return 0


# ── BINDING THAT SURVIVES A COLD START (2026-10-11) ───────────────────────
#
# Claude Code gives a stdio server MCP_TIMEOUT (default 30 s) to answer
# `initialize`, and never initializes a server twice. The research services
# run at min-instances 0, so a session that starts on a cold service paid a
# Cloud Run cold start plus an ID-token and capability-token mint — and the
# old proxy either missed the window (server FAILED, no tools) or, on an
# error, answered with an EMPTY tool list "until the next initialize", which
# never comes. Either way the session ran its whole life without the tools
# and the agents fell to WebSearch.
#
# Now: the upstream handshake runs on a worker with INIT_BUDGET_S (under the
# CLI's window). If it misses or errors, the proxy completes the handshake
# itself, advertising `tools.listChanged`, and serves the LAST-KNOWN tool
# list (this session's runtime cache, else the vendored snapshot) so the
# tools are bound from the first turn. A recovery loop keeps trying with
# backoff; when the service answers it replays `notifications/initialized`
# upstream and sends `notifications/tools/list_changed`, and the CLI refreshes
# to the live listing. A tool call made while warming waits up to
# CALL_WAIT_S for recovery before it answers with the recorded reason.

INIT_BUDGET_S = float(os.environ.get("DMA_RESEARCH_INIT_BUDGET_S") or 20)
CALL_WAIT_S = float(os.environ.get("DMA_RESEARCH_CALL_WAIT_S") or 90)
RETRY_WINDOW_S = float(os.environ.get("DMA_RESEARCH_RETRY_WINDOW_S") or 1800)
BACKOFF_S = (5.0, 10.0, 20.0, 40.0, 60.0)
#: Upstream read timeout for one exchange. A batched research_brief runs for
#: minutes (measured 2026-10-11 on IMA P1C1: briefs outlived the cloud
#: environment's 60 s MCP_TOOL_TIMEOUT, finished server-side, and their cards
#: never reached the caller). `.mcp.json` gives these servers a per-server
#: `timeout` above this, so the client waits for the answer.
CALL_TIMEOUT_S = float(os.environ.get("DMA_RESEARCH_CALL_TIMEOUT_S") or 270)

# ── ADMISSION: THE QUEUE LIVES HERE, NOT IN CLOUD RUN (2026-10-11) ────────
#
# The stress test is 686 cells across sixteen categories at once: ~136
# capability briefs of up to 48 queries each against two search sources
# (SearXNG 4/s, Parallel 1.4 calls/s, per engine instance). The work is
# bounded by the sources, not by how many briefs are open — firing all 136
# at the engine only makes each one slower, past Cloud Run's 300 s request
# timeout, and past the instances' concurrency (8): a 429 that the collector
# read as an outage and fell to raw SearXNG for (P3C4, live). So every heavy
# call passes this gate: at most ADMIT_HEAVY in flight (12 keeps both engine
# instances busy — Cloud Run fills one instance to its concurrency before it
# starts the second — and each brief inside ~100 s), the rest wait HERE,
# first come first served, where no server clock runs. `.mcp.json` gives the
# evidence server a 30-minute per-server timeout so a queued call is waited
# for, not abandoned. Light calls (coverage, verify, expand) never queue
# behind heavy ones.
HEAVY_TOOLS = frozenset({"research_brief", "crawl_entity", "filings_evidence"})
ADMIT_HEAVY = int(os.environ.get("DMA_RESEARCH_ADMIT") or 12)
MAX_PENDING_CALLS = int(os.environ.get("DMA_RESEARCH_MAX_PENDING") or 256)
#: A 429 or 503 is Cloud Run saying "no instance free yet" (all at their
#: concurrency, or the second still cold) — the request never reached the
#: engine, so it is safe to send again. Waits between attempts, seconds.
CAPACITY_RETRY_S = (2.0, 4.0, 8.0, 15.0, 30.0, 30.0)
HEARTBEAT_S = 15.0
SNAPSHOT = HERE.parent / "references" / "research_layer_tools.json"

#: Set when the service refused or could not be reached at `initialize`.
#: While set, the proxy serves the last-known tool list and a recovery loop
#: retries; it clears the moment the service answers.
_degraded = {"reason": None}

_live = {"emit": None, "url": None, "init": None, "client_initialized": False,
         "gen": 0}
_up_lock = threading.Lock()          # one HANDSHAKE at a time; calls run concurrently
_out_lock = threading.Lock()         # one stdout line at a time
_recovered = threading.Event()
_kick = threading.Event()


def _mark(available: bool, why: str | None) -> None:
    """Every availability write goes through here, so the per-call tracker
    and the marker on disk can never disagree."""
    _live["marked_down"] = not available
    mark_available(available, why)


def _write(obj: dict) -> None:
    with _out_lock:
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()


def _service() -> str:
    return str(_cfg.get("secret") or "").replace("dmai-", "").replace("-path-token", "") or "unknown"


def _cache_path() -> Path:
    return LAYER_STATE_DIR / f"{_service()}.tools.json"


def remember_tools(tools: list) -> None:
    """Best effort: the live listing, for the next cold start in this container."""
    if not tools:
        return
    try:
        LAYER_STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _cache_path().with_suffix(".tmp")
        tmp.write_text(json.dumps({"service": _service(), "ts": time.time(), "tools": tools}))
        os.replace(tmp, _cache_path())
    except Exception:                                           # noqa: BLE001
        pass


def known_tools() -> list:
    """This container's last live listing, else the vendored snapshot, else []."""
    try:
        tools = json.loads(_cache_path().read_text()).get("tools") or []
        if tools:
            return tools
    except Exception:                                           # noqa: BLE001
        pass
    try:
        return json.loads(SNAPSHOT.read_text()).get(_service()) or []
    except Exception:                                           # noqa: BLE001
        return []


def _is_error(replies: list, msg: dict) -> str | None:
    for r in replies:
        if isinstance(r, dict) and r.get("id") == msg.get("id") and r.get("error"):
            return str(r["error"].get("message") or "error")
    if msg.get("id") is not None and not any(
            isinstance(r, dict) and r.get("id") == msg.get("id") for r in replies):
        return "no answer"
    return None


def _url(url) -> str:
    return url() if callable(url) else url


def _upstream(url, msg: dict) -> list:
    """One exchange. The handshake is serialised (it resets the session);
    calls run concurrently on the same session."""
    if msg.get("method") == "initialize" or msg.get("id") is None:
        with _up_lock:
            return mcp_proxy.forward(_url(url), msg)
    return mcp_proxy.forward(_url(url), msg)


def _handshake(url, msg: dict) -> str | None:
    """One upstream initialize (+ the client's initialized notification when
    it has already been sent). None on success, else the reason."""
    try:
        replies = _upstream(url, msg)
    except Exception as e:                                      # noqa: BLE001
        return f"unreachable: {e}"
    why = _is_error(replies, msg)
    if why is None and _live["client_initialized"]:
        try:
            _upstream(url, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        except Exception:                                       # noqa: BLE001
            pass
    return why


def _recover(gen: int, first: threading.Thread | None) -> None:
    """Retry the handshake until it answers, the window closes, or a newer
    initialize supersedes this one."""
    if first is not None:
        first.join()
        if _degraded["reason"] is None or gen != _live["gen"]:
            return
    deadline = time.monotonic() + RETRY_WINDOW_S
    i = 0
    while gen == _live["gen"] and time.monotonic() < deadline:
        _kick.wait(BACKOFF_S[min(i, len(BACKOFF_S) - 1)])
        _kick.clear()
        i += 1
        if gen != _live["gen"]:
            return
        why = _handshake(_live["url"], _live["init"])
        if gen != _live["gen"]:
            return
        if why is None:
            _on_recovered(gen)
            return
        _degraded["reason"] = why
        _mark(False, why)


def _on_recovered(gen: int) -> None:
    """Only the CURRENT handshake's worker may clear the degraded state: a
    worker left by a superseded initialize must not mark a newer one up."""
    if gen != _live["gen"]:
        return
    _degraded["reason"] = None
    _mark(True, None)
    _recovered.set()
    print(f"evidence_proxy: {_cfg['secret']}: service answered; tool list refreshed",
          file=sys.stderr)
    emit = _live.get("emit")
    if emit:
        emit({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"})


#: Transport failures, as mcp_proxy words them — not a tool's own refusal.
_TRANSPORT = ("unreachable", "connector HTTP 5", "no answer", "timed out")


def _note_call_outcome(why: str | None) -> None:
    """Keep the availability marker true to the LAST call, not only to the
    handshake: hooks/search_order.py holds WebSearch back while the engine
    is marked up, so an engine that dies mid-session must say so, and one
    that comes back must lift the fallback again (IMA probe, 2026-10-11)."""
    down = bool(why) and any(t in why for t in _TRANSPORT)
    if down == _live.get("marked_down", False):
        return
    _mark(not down, why if down else None)


def _local_handshake(msg: dict, why: str) -> list:
    return [{"jsonrpc": "2.0", "id": msg.get("id"), "result": {
        "protocolVersion": (msg.get("params") or {}).get("protocolVersion", "2025-06-18"),
        "capabilities": {"tools": {"listChanged": True}},
        "serverInfo": {"name": _cfg["secret"].replace("-path-token", ""), "version": "unavailable"},
        "instructions": f"This research-layer service has not answered yet: {why}. Its last-known "
                        f"tools are listed and a call waits for it to come up; run "
                        f"/dma-insights:doctor if it stays down. The connector and the other "
                        f"services are unaffected."}}]


_admit = threading.Semaphore(ADMIT_HEAVY)
_admit_lock = threading.Lock()
_queue_state = {"waiting": 0, "running": 0}


def _progress(msg: dict, note: str, n: int) -> None:
    """notifications/progress for a call that carries a progressToken: the
    client's idle clock is reset while the call waits its turn."""
    token = ((msg.get("params") or {}).get("_meta") or {}).get("progressToken")
    emit = _live.get("emit")
    if token is None or not emit:
        return
    emit({"jsonrpc": "2.0", "method": "notifications/progress",
          "params": {"progressToken": token, "progress": n, "message": note}})


def _heartbeat(msg: dict, what: str, stop: threading.Event) -> None:
    n = 0
    while not stop.wait(HEARTBEAT_S):
        n += 1
        _progress(msg, what(), n)


def _capacity_refused(replies: list, msg: dict) -> bool:
    why = _is_error(replies, msg) or ""
    return "HTTP 429" in why or "HTTP 503" in why


def admitted(url, msg: dict) -> list:
    """serve(), behind the heavy-call gate and the capacity retry."""
    msg = _to_upstream(msg)
    name = (msg.get("params") or {}).get("name") or ""
    heavy = msg.get("method") == "tools/call" and name in HEAVY_TOOLS
    stop = threading.Event()
    with _admit_lock:
        _queue_state["waiting"] += heavy

    def status() -> str:
        return (f"{name}: queued behind {_queue_state['running']} running heavy call(s), "
                f"{_queue_state['waiting']} waiting" if waiting[0] else f"{name}: running")
    waiting = [heavy]
    threading.Thread(target=_heartbeat, args=(msg, status, stop), daemon=True).start()
    try:
        if heavy:
            _admit.acquire()
            with _admit_lock:
                _queue_state["waiting"] -= 1
                _queue_state["running"] += 1
            waiting[0] = False
        replies = serve(url, msg)
        for wait in CAPACITY_RETRY_S:
            if msg.get("method") != "tools/call" or not _capacity_refused(replies, msg):
                break
            time.sleep(wait)
            replies = serve(url, msg)
        return replies
    finally:
        stop.set()
        if heavy:
            with _admit_lock:
                _queue_state["running"] -= 1
            _admit.release()


# ── THE TOOL SURFACE (2026-10-11) ─────────────────────────────────────────
#
# Agents see specific, described tools (scripts/research_tool_surface.py,
# references/research_tool_surface.json): `find_regulator_evidence`, not
# `research_brief`. The listing is rewritten on the way out — live or from
# the snapshot, which stays the UPSTREAM listing — and every call is mapped
# back to the upstream tool with its preset arguments on the way in.

def _present(tools: list) -> list:
    return surface.present(_service(), tools)


def _to_upstream(msg: dict) -> dict:
    if msg.get("method") != "tools/call":
        return msg
    return {**msg, "params": surface.to_upstream(_service(), msg.get("params") or {})}


def _presented(replies: list, msg: dict) -> list:
    out = []
    for r in replies:
        if isinstance(r, dict) and r.get("id") == msg.get("id") and isinstance(r.get("result"), dict) \
                and isinstance(r["result"].get("tools"), list):
            r = {**r, "result": {**r["result"], "tools": _present(r["result"]["tools"])}}
        out.append(r)
    return out


def serve(url, msg: dict) -> list:
    """forward(), answering the handshake itself when the service is cold or down."""
    msg = _to_upstream(msg)
    method = msg.get("method")
    if method == "initialize":
        _live["gen"] += 1
        gen = _live["gen"]
        _live.update(url=url, init=msg, client_initialized=False)
        _degraded["reason"] = None
        _recovered.clear()
        box: dict = {}

        def first() -> None:
            try:
                box["replies"] = _upstream(url, msg)
            except Exception as e:                              # noqa: BLE001
                box["error"] = f"unreachable: {e}"

        t = threading.Thread(target=first, daemon=True)
        t.start()
        t.join(INIT_BUDGET_S)
        if not t.is_alive():
            why = box.get("error") or _is_error(box.get("replies") or [], msg)
            if why is None:
                _mark(True, None)
                _recovered.set()
                return box["replies"]
        else:
            why = f"no answer within {INIT_BUDGET_S:.0f}s (cold start?)"
        _degraded["reason"] = why
        _mark(False, why)
        print(f"evidence_proxy: {_cfg['secret']}: {why}; serving the last-known tool list "
              f"and retrying in the background", file=sys.stderr)

        def late() -> None:
            # the first handshake may still land after the budget
            t.join()
            if gen == _live["gen"] and _degraded["reason"] is not None and "replies" in box \
                    and _is_error(box["replies"], msg) is None:
                if _live["client_initialized"]:
                    try:
                        _upstream(url, {"jsonrpc": "2.0", "method": "notifications/initialized"})
                    except Exception:                           # noqa: BLE001
                        pass
                _on_recovered(gen)
                return
            _recover(gen, None)

        threading.Thread(target=late, daemon=True).start()
        return _local_handshake(msg, why)
    if method == "notifications/initialized":
        _live["client_initialized"] = True
    if _degraded["reason"] is not None:
        if msg.get("id") is None:                       # notifications: replayed on recovery
            return []
        if method == "tools/list":
            return [{"jsonrpc": "2.0", "id": msg.get("id"), "result": {"tools": _present(known_tools())}}]
        if method in ("ping",):
            return [{"jsonrpc": "2.0", "id": msg.get("id"), "result": {}}]
        _kick.set()
        if not _recovered.wait(CALL_WAIT_S) or _degraded["reason"] is not None:
            return [{"jsonrpc": "2.0", "id": msg.get("id"),
                     "error": {"code": -32000,
                               "message": f"service unavailable: {_degraded['reason']}"}}]
    replies = _upstream(url, msg)
    if method == "tools/call":
        _note_call_outcome(_is_error(replies, msg))
    if method == "tools/list":
        for r in replies:
            if isinstance(r, dict) and r.get("id") == msg.get("id"):
                remember_tools(((r.get("result") or {}).get("tools")) or [])
        return _presented(replies, msg)
    return replies


if __name__ == "__main__":
    sys.exit(main())
