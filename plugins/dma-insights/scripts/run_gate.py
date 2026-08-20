#!/usr/bin/env python3
"""The pre-synthesis gate: no run starts unless its grounding chain holds.

Owner instruction, 2026-08-20: "Without this DMA package, and checking that
the client is not served on the web app or does not require a refresh on
the web app, then the scores may be hallucinated. Ensure this is always the
first case. Before any synthesis starts a non-duplicate entity should be
ingested for analysis."

This script IS that first case, mechanical rather than prose. `pick` walks
the learner order and emits exactly one run id a synthesis may claim — or a
refusal naming which gate failed. A routine synthesizes ONLY a run this
gate emitted; anything else is how a hallucinated score happens.

The four gates, per candidate:

  G1 INGESTED SUBSTANCE   an INGESTED run exists, is_latest_for_request,
                          and its PARSED bundle is substantial: scored
                          cells and evidence counted from get_report_bundle
                          — a run row with an empty bundle is a scan
                          failure, not a synthesis input.
  G2 RAW PACKAGE TRACES   the client's folder exists in the Drive intake
                          tree and holds at least one package file — the
                          parsed bundle must trace to a real package.
  G3 NOT ALREADY CURRENT  the client is not already serving six pages on
                          the web app — unless the refresh queue (requested
                          or due) names it, in which case a refresh run is
                          exactly right. Serving-and-current means SKIP to
                          the next client, not re-produce.
  G4 NON-DUPLICATE        no unadjudicated twin: another pending display_id
                          for what is plainly the same entity (shared
                          request family, or a name that is a prefix/
                          suffix of the other). A twin is REFUSED for
                          auto-pick — a human or the worker dedup rules
                          adjudicate first; the gate never guesses which
                          twin is real.

Identity: everything here runs on the dmai-routine service account the
container holds — connector via ID token + path token, serving API via ID
token, Drive via drive_fetch. No value of any token is printed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import drive_fetch  # noqa: E402
import gcp_token  # noqa: E402

MCP = "https://dmai-mcp-dukrne5v4a-uc.a.run.app"
API = "https://dmai-api-dukrne5v4a-uc.a.run.app"
PATHTOK_FILE = Path("/root/.dma/pathtok")
PAGES = ("overview", "heatmap", "insights", "platform", "context", "techstack")
MIN_SCORED_CELLS = 50     # a real workbook scores hundreds; below this the
                          # scan produced a stub, not a package
LEARNERS = ["t-rowe-price-group-inc", "houlihan-lokey-inc",
            "hughes-federal-credit-union", "sl-green-realty-corp-nyse-slg",
            "corporate-america-credit-union"]
STRESS = ["brick-city-capital", "thrivent", "bank-of-utah"]
HELD_OUT = {"bok-financial-corporation", "bok-financial"}


def _idt(audience: str) -> str:
    key, source = gcp_token.load_key("/root/.dma/sa.json")
    if key is None:
        raise SystemExit(f"no service-account identity ({source})")
    tok = gcp_token.exchange(gcp_token.mint_assertion(
        key, {"target_audience": audience})).get("id_token", "")
    if not tok:
        raise SystemExit(f"could not mint an ID token for {audience}")
    return tok


def _pathtok() -> str:
    if PATHTOK_FILE.is_file():
        return PATHTOK_FILE.read_text().strip()
    raise SystemExit(f"no connector path token at {PATHTOK_FILE} — "
                     f"bootstrap_session.sh lands it")


def mcp_call(tool: str, args: dict) -> dict:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": tool, "arguments": args}}).encode()
    req = urllib.request.Request(f"{MCP}/mcp", data=body, method="POST")
    req.add_header("Authorization", f"Bearer {_idt(MCP)}")
    req.add_header("X-DMA-Path-Token", _pathtok())
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read().decode()
    m = re.search(r"data: (\{.*\})", raw)
    d = json.loads(m.group(1) if m else raw)
    content = d.get("result", {}).get("content", [])
    return json.loads(content[0]["text"]) if content else d


def api_get(path: str):
    """(status_code, parsed_or_None)."""
    req = urllib.request.Request(f"{API}{path}")
    req.add_header("Authorization", f"Bearer {_idt(API)}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as e:
        return e.code, None


# ── the gates ─────────────────────────────────────────────────────────────

def g1_ingested(pending: list, display_id: str) -> tuple:
    """(run_id_or_None, detail)."""
    rows = [r for r in pending
            if r.get("display_id") == display_id
            and r.get("is_latest_for_request")
            and r.get("status") == "INGESTED"]
    if not rows:
        return None, "no INGESTED latest-for-request run — the package scan " \
                     "has not produced one; nothing to synthesize"
    row = max(rows, key=lambda r: r.get("run_seq") or 0)
    bundle = mcp_call("get_report_bundle", {"run_id": row["run_id"]})
    cells = bundle.get("scored_cells") or len(bundle.get("scores") or [])
    evidence = len(bundle.get("evidence") or [])
    if not cells or cells < MIN_SCORED_CELLS:
        return None, (f"run {row['run_id'][:8]} parsed to only "
                      f"{cells or 0} scored cells (floor {MIN_SCORED_CELLS})"
                      f" — a stub, not a package; report a scan finding")
    return row["run_id"], (f"run {row['run_id'][:8]}: {cells} scored cells, "
                           f"{evidence} evidence rows, catalogue "
                           f"{bundle.get('ccg_catalog_version')}")


def _tree_files(tok, folder_id: str, depth: int = 0) -> list:
    """Recursive file list (names only), wrapper-transparent. ~30 of 178
    client folders keep the whole package inside one wrapper folder
    (measured 2026-08-20) — a top-level-only count called them EMPTY."""
    if depth > 4:
        return []
    out = []
    for f in drive_fetch._list_children(tok, folder_id):
        if f["mimeType"] == drive_fetch.FOLDER_MIME:
            out += _tree_files(tok, f["id"], depth + 1)
        elif f["name"] != ".DS_Store":
            out.append(f["name"])
    return out


def g2_raw_package(display_id: str) -> tuple:
    """(ok, detail)."""
    try:
        tok = drive_fetch._token()
        folder = drive_fetch._find_client_folder(tok, display_id)
        top = drive_fetch._list_children(tok, folder["id"])
        files = _tree_files(tok, folder["id"])
    except SystemExit as e:
        return False, str(e)
    top_dirs = [f["name"] for f in top
                if f["mimeType"] == drive_fetch.FOLDER_MIME]
    top_files = [f for f in top if f["mimeType"] != drive_fetch.FOLDER_MIME
                 and f["name"] != ".DS_Store"]
    wrapper = (f" (via wrapper {top_dirs[0]!r})"
               if len(top_dirs) == 1 and not top_files else "")
    if not files:
        return False, f"client folder {folder['name']!r} is EMPTY — no raw " \
                      f"package to trace the parsed bundle to"
    workbooks = [n for n in files
                 if n.lower().endswith((".xlsx", ".xlsm"))
                 and re.search(r"scor|assessment.*workbook", n, re.I)]
    if not workbooks:
        sample = ", ".join(sorted(files)[:3])
        return False, (f"{len(files)} files in {folder['name']!r}{wrapper} "
                       f"but NO scoring workbook anywhere in the tree — "
                       f"briefing- or research-only, not a synthesis input "
                       f"(e.g. {sample})")
    return True, (f"{len(files)} package files in {folder['name']!r}"
                  f"{wrapper}, scoring workbook present")


def g3_serving_state(display_id: str) -> tuple:
    """('produce'|'skip', detail)."""
    code, _ = api_get(f"/v1/entities/{display_id}/overview?audience=internal")
    if code == 404:
        return "produce", "not serving — first production"
    if code != 200:
        return "produce", f"serving state unreadable (HTTP {code}) — " \
                          f"treating as not serving"
    served = sum(
        1 for page in PAGES
        if api_get(f"/v1/entities/{display_id}/{page}?audience=internal")[0]
        == 200)
    if served < len(PAGES):
        return "produce", f"serving {served}/6 pages — incomplete, finish it"
    code, queue = api_get("/v1/ops/refresh-queue")
    if code == 200 and queue:
        listed = {e.get("display_id") for lst in ("requested", "due")
                  for e in (queue.get(lst) or [])}
        if display_id in listed:
            return "produce", "serving 6/6 but the refresh queue names it — " \
                              "refresh run"
    return "skip", "already serving 6/6 and no refresh is requested or due " \
                   "— re-producing a current client is not synthesis, skip"


def g4_non_duplicate(pending: list, display_id: str) -> tuple:
    """(ok, detail)."""
    mine = [r for r in pending if r.get("display_id") == display_id]
    requests = {r.get("request_id") for r in mine if r.get("request_id")}
    twins = set()
    for r in pending:
        other = r.get("display_id") or ""
        if other == display_id or other in HELD_OUT:
            continue
        if r.get("request_id") in requests:
            twins.add(other)
        elif other.startswith(display_id) or display_id.startswith(other):
            twins.add(other)
    if twins:
        return False, (f"unadjudicated twin display_id(s): "
                       f"{', '.join(sorted(twins))} — the worker dedup rules "
                       f"or a human adjudicate before any synthesis")
    return True, "no twin display_id in the pending set"


def evaluate(pending: list, display_id: str) -> dict:
    out = {"display_id": display_id}
    run_id, d1 = g1_ingested(pending, display_id)
    out["G1_ingested"] = {"ok": bool(run_id), "detail": d1}
    ok2, d2 = g2_raw_package(display_id)
    out["G2_raw_package"] = {"ok": ok2, "detail": d2}
    verdict3, d3 = g3_serving_state(display_id)
    out["G3_serving"] = {"ok": verdict3 == "produce", "detail": d3,
                         "skip": verdict3 == "skip"}
    ok4, d4 = g4_non_duplicate(pending, display_id)
    out["G4_non_duplicate"] = {"ok": ok4, "detail": d4}
    out["run_id"] = run_id if (run_id and ok2 and ok4
                               and verdict3 == "produce") else None
    return out


def pick(candidates: list) -> int:
    pending = mcp_call("list_pending_runs", {}).get("pending", [])
    for display_id in candidates:
        if display_id in HELD_OUT:
            continue
        v = evaluate(pending, display_id)
        for g in ("G1_ingested", "G2_raw_package", "G3_serving",
                  "G4_non_duplicate"):
            mark = "PASS" if v[g]["ok"] else ("SKIP" if v[g].get("skip")
                                              else "FAIL")
            print(f"  {display_id} {g}: {mark} — {v[g]['detail']}")
        if v["run_id"]:
            print(f"GATE: PRODUCE {display_id} run {v['run_id']}")
            return 0
        if v["G3_serving"].get("skip"):
            continue                     # current client — next candidate
        print(f"GATE: STOP — {display_id} failed above; do not synthesize "
              f"and do not silently advance past a failure that is not a "
              f"clean serving-and-current skip")
        return 1
    print("GATE: STOP — every candidate is serving-and-current or held out; "
          "sequence complete")
    return 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_pick = sub.add_parser("pick", help="walk the learner order, emit one "
                                         "producible run or a refusal")
    p_pick.add_argument("--stress", action="store_true",
                        help="include the stress candidates after learners")
    p_one = sub.add_parser("evaluate", help="all four gates for one client")
    p_one.add_argument("--client", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "pick":
        return pick(LEARNERS + (STRESS if a.stress else []))
    if a.cmd == "evaluate":
        pending = mcp_call("list_pending_runs", {}).get("pending", [])
        print(json.dumps(evaluate(pending, a.client), indent=1))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
