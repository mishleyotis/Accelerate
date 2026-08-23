#!/usr/bin/env python3
"""The pre-synthesis gate: no run starts unless its grounding chain holds.

Owner instruction, 2026-08-20: "Without this DMA package, and checking that
the client is not served on the web app or does not require a refresh on
the web app, then the scores may be hallucinated. Ensure this is always the
first case. Before any synthesis starts a non-duplicate entity should be
ingested for analysis."

This script IS that first case, mechanical rather than prose. `pick` emits
exactly one run id a synthesis may claim — or a refusal naming which gate
failed. A routine synthesizes ONLY a run this gate emitted; anything else is
how a hallucinated score happens.

WHAT `pick` WALKS, changed 2026-08-22 on the owner's instruction. It used to
walk a hardcoded list of eight names and stop. The pending queue holds 286
runs across 172 entities, so 164 vetted, unprocessed clients could never be
reached however long the routine ran, and the sequence reported itself
"complete" having never looked at the overwhelming majority of the corpus.

It now walks the QUEUE: the learner order first, because the learning curve
it measures is only readable if that order holds, and then every other ready
entity the queue offers, newest assessment first. The queue's own selector
decides what "ready" means — one run per entity, nothing whose entity carries
a live claim. No client is named to be admitted; the only name-based rule
left is HELD_OUT, which subtracts.

A failing candidate no longer stops the walk either. Every failure is
printed with its gate and its detail, and the PRODUCE line names what was
walked past — nothing is silent. What is gone is only the blocking, which
protected nothing: a client whose package is broken is not made sound by
refusing to look at the next one.

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
#: A PREFERENCE ORDER, NOT A FENCE. These five were the deliberate learning
#: curriculum (docs/DECISIONS.md D7) and they still go first when they have
#: producible work — the curve they measure is only readable if the order
#: holds. What changed on 2026-08-22, on the owner's instruction, is what
#: happens AFTER them: the walk continues into the whole pending queue instead
#: of stopping.
#:
#: It had to change. The queue holds 286 pending runs across 172 entities and
#: this list named eight, so 164 vetted, unprocessed clients could never be
#: reached however long the routine ran — the sequence reported "sequence
#: complete" while the overwhelming majority of the corpus had never been
#: looked at once.
LEARNERS = ["t-rowe-price-group-inc", "houlihan-lokey-inc",
            "hughes-federal-credit-union", "sl-green-realty-corp-nyse-slg",
            "corporate-america-credit-union"]
STRESS = ["brick-city-capital", "thrivent", "bank-of-utah"]

#: Never produced, by owner decision: the held-out control the learning
#: measurements are read against. This is an EXCLUSION and stays one — it is
#: the only name-based rule left in the walk, and it subtracts rather than
#: admits, which is why widening the queue does not touch it.
HELD_OUT = {"bok-financial-corporation", "bok-financial"}

#: How many candidates one firing will gate before giving up. The gates each
#: cost connector calls, and a firing produces ONE client, so walking hundreds
#: to find it would spend the session on selection. Failures are reported and
#: skipped, so the next firing starts where this one got to.
MAX_CANDIDATES = 40
#: How many spare producible runs to name beyond the ones asked for,
#: so a session whose package fails VETTING has somewhere to go.
RESERVE_DEPTH = 2


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
    """Every route, not just the file. This is the routine's FIRST command:
    a firing that dies here because bootstrap did not land one file has
    ended before it looked at a single client, for a secret the service
    account can read itself (gcp_token.path_token)."""
    return gcp_token.path_token()


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
    exports = [n for n in files
               if n.lower() == "export_scoring_detail.csv"]
    if not workbooks and not exports:
        sample = ", ".join(sorted(files)[:3])
        return False, (f"{len(files)} files in {folder['name']!r}{wrapper} "
                       f"but NO scoring artefact anywhere in the tree (no "
                       f"workbook, no export_scoring_detail.csv) — briefing- "
                       f"or research-only, not a synthesis input "
                       f"(e.g. {sample})")
    kind = ("scoring workbook present" if workbooks else
            "EXPORT-ONLY scoring (flattened exports are the score "
            "authority; workbook absent from Drive — the vetter confirms)")
    return True, (f"{len(files)} package files in {folder['name']!r}"
                  f"{wrapper}, {kind}")


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
    # audience=internal, EXPLICITLY. `refresh_queue` raises 403 for any other
    # audience (apps/api/dma_api/cadence.py) and the endpoint default-denies an
    # omitted parameter to `customer` (invariant 5). Called bare, this returned
    # 403 on every client, the queue was never consulted, and the gate skipped
    # every serving client — including the ones a human had explicitly asked to
    # refresh. A requested refresh that silently never runs is the worst shape
    # of this bug, because the request is recorded and looks answered.
    code, queue = api_get("/v1/ops/refresh-queue?audience=internal")
    if code != 200 or not isinstance(queue, dict):
        # NOT "no refresh is due" — nobody looked. Saying otherwise states a
        # fact this branch did not establish, and that is exactly how the 403
        # stayed invisible. Produce, because an unreadable queue must not be
        # the thing that stops a refresh.
        return "produce", (f"serving 6/6 but the refresh queue is UNREADABLE "
                           f"(HTTP {code}) — cannot show a refresh is not "
                           f"needed, so treating as due")
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


def queue_order(pending: list, prefer: list) -> list:
    """Every entity worth gating, preferred names first, then the whole queue.

    The queue's own selector decides what is READY — one run per entity
    (newest), nothing whose entity carries a live claim, newest assessment
    first. This adds only the ordering the curriculum needs, and never
    invents a candidate the queue did not offer.
    """
    ready = _queue_ready(pending)
    offered = [r.get("display_id") for r in ready if r.get("display_id")]
    available = set(offered)

    # `prefer` REORDERS the queue; it never adds to it. A preferred name with
    # nothing pending is not a candidate — gating it spends connector calls to
    # print "failed G1_ingested" about an entity that has no run to ingest,
    # which reads as a broken client rather than an absent one.
    seen, order = set(), []
    for display_id in prefer:
        if (display_id in HELD_OUT or display_id in seen
                or display_id not in available):
            continue
        seen.add(display_id)
        order.append(display_id)
    for display_id in offered:
        if display_id in seen or display_id in HELD_OUT:
            continue
        seen.add(display_id)
        order.append(display_id)
    return order


def _queue_ready(pending: list) -> list:
    """The ready set, from the queue selector if it is importable.

    The selector lives in the repo (scripts/synthesis_queue.py) and the plugin
    ships without it, so this degrades to the same rule inline rather than
    failing: newest run per entity, entities with a live claim held back,
    newest assessment first. Duplicating the rule is the lesser evil — a pick
    that cannot run at all reaches no clients whatsoever.
    """
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "dma_synthesis_queue",
            Path(__file__).resolve().parents[3] / "scripts" / "synthesis_queue.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # `selected` is the key; an earlier version of this read `plan` — the
        # name of the local variable inside select() rather than the one it
        # returns — and silently produced an empty candidate list, which reads
        # exactly like an empty queue.
        picked = mod.select(pending).get("selected") or []
        if not picked and pending:
            raise RuntimeError("selector returned nothing for a non-empty "
                               "queue; falling back to the inline rule")
        return picked
    except Exception:                                       # noqa: BLE001
        best: dict = {}
        for run in pending:
            key = run.get("display_id") or run.get("run_id")
            cur = best.get(key)
            if cur is None or (run.get("completed_at") or "") > (
                    cur.get("completed_at") or ""):
                best[key] = run
        held = {(r.get("display_id") or r.get("run_id"))
                for r in pending if (r.get("claim") or {}).get("live")}
        ready = [r for k, r in best.items() if k not in held]
        ready.sort(key=lambda r: (r.get("completed_at") or "",
                                  str(r.get("run_id"))), reverse=True)
        return ready


def pick(prefer: list, max_candidates: int = MAX_CANDIDATES,
         count: int = 1) -> int:
    """Emit `count` producible runs, or a refusal that names what it saw.

    COUNT EXISTS SO A FIRING CAN CARRY TWO CLIENTS (owner, 2026-08-23). The
    walk is the same walk; it simply does not stop at the first PRODUCE. Each
    pick names its own run, and a firing that can only find one says so and
    produces one rather than failing — one client synthesised is not a failed
    firing, and refusing to produce it because a second could not be found
    would be the queue-blocking behaviour again in a new place.

    RESERVE, and it is the reason the emitted list runs longer than `count`:
    a package that fails VETTING fails after the gate has passed it, inside
    the producing session, where this script is no longer running. Without a
    named alternative the session's only options are to end the firing or to
    argue with the vetter. So every producible candidate the walk found is
    printed as a RESERVE line, in order, and the session takes the next one.

    A FAILING CANDIDATE NO LONGER STOPS THE QUEUE. It used to: any G1, G2 or
    G4 failure returned immediately, so one client with a stub bundle or an
    unadjudicated twin blocked all 172 ready entities behind it until a human
    noticed. The rule that produced that behaviour — "never silently advance
    past a failure" — is kept in the half that matters: nothing is silent.
    Every failure is printed with its gate and its detail, and the PRODUCE
    line is followed by a summary of what was skipped to reach it, so a reader
    can see the whole walk. What is dropped is only the blocking, which
    protected nothing: a client whose package is broken is not made sound by
    refusing to look at the next one.
    """
    pending = mcp_call("list_pending_runs", {}).get("pending", [])
    order = queue_order(pending, prefer)
    if not order:
        print("GATE: STOP — the pending queue offered no unclaimed entity; "
              "nothing to gate")
        return 1

    skipped: list = []
    produced: list = []
    reserve: list = []
    for display_id in order[:max_candidates]:
        v = evaluate(pending, display_id)
        verbose = len(produced) < count
        for g in ("G1_ingested", "G2_raw_package", "G3_serving",
                  "G4_non_duplicate"):
            mark = "PASS" if v[g]["ok"] else ("SKIP" if v[g].get("skip")
                                              else "FAIL")
            if verbose:
                print(f"  {display_id} {g}: {mark} — {v[g]['detail']}")
        if v["run_id"]:
            if len(produced) < count:
                produced.append((display_id, v["run_id"]))
                print(f"GATE: PRODUCE {display_id} run {v['run_id']}")
            elif len(reserve) < RESERVE_DEPTH:
                reserve.append((display_id, v["run_id"]))
            if len(produced) >= count and len(reserve) >= RESERVE_DEPTH:
                break
            continue
        if v["G3_serving"].get("skip"):
            skipped.append((display_id, "serving and current"))
            continue
        bad = next((g for g in ("G1_ingested", "G2_raw_package",
                                "G4_non_duplicate") if not v[g]["ok"]),
                   "unknown")
        skipped.append((display_id, f"failed {bad}"))

    if produced:
        for display_id, run_id in reserve:
            print(f"GATE: RESERVE {display_id} run {run_id}")
        if len(produced) < count:
            print(f"  (asked for {count}, found {len(produced)} — producing "
                  f"what there is; a firing that synthesises one client is "
                  f"not a failed firing)")
        if skipped:
            print(f"  (walked past {len(skipped)}: "
                  + "; ".join(f"{d} {why}" for d, why in skipped[:8])
                  + ("; …" if len(skipped) > 8 else "") + ")")
        return 0

    print(f"GATE: STOP — gated {len(skipped)} of {len(order)} queued "
          f"entities and none was producible. Not a clean end: every one is "
          f"listed above with the gate it failed, and a package failure is a "
          f"finding to record, not a reason to stop looking.")
    for d, why in skipped:
        print(f"  skipped {d}: {why}")
    return 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_pick = sub.add_parser("pick", help="walk the learners then the whole "
                                         "pending queue, emit one producible "
                                         "run or a refusal")
    p_pick.add_argument("--stress", action="store_true",
                        help="put the stress candidates straight after the "
                             "learners; the rest of the queue follows either "
                             "way")
    p_pick.add_argument("--count", type=int, default=1,
                        help="how many clients this firing will carry (2 runs "
                             "two sessions); fewer are produced when fewer "
                             "are producible, never zero-by-refusal")
    p_pick.add_argument("--max-candidates", type=int, default=MAX_CANDIDATES,
                        help="how many queued entities to gate before giving "
                             "up this firing (default %(default)s)")
    p_one = sub.add_parser("evaluate", help="all four gates for one client")
    p_one.add_argument("--client", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "pick":
        return pick(LEARNERS + (STRESS if a.stress else []),
                    max_candidates=a.max_candidates, count=max(1, a.count))
    if a.cmd == "evaluate":
        pending = mcp_call("list_pending_runs", {}).get("pending", [])
        print(json.dumps(evaluate(pending, a.client), indent=1))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
