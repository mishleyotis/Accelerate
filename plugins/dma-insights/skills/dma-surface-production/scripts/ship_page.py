#!/usr/bin/env python3
"""Assemble a page from its section files, check it locally, and SUBMIT it —
without a single payload byte passing through the model.

## Why this exists

Production of Golden 1 (2026-09-02) spent roughly 330,000 subagent tokens
moving ONE page's bytes to the connector, twice. The method was: print the
payload in numbered chunks, have an agent retype them into
`append_payload_part`, compare byte receipts, and re-send whatever drifted.
It worked, and it was never necessary — `plugins/dma-insights/scripts/
mcp_raw.py` has spoken JSON-RPC to the connector from disk since 2026-08-20.

Retyping is not merely slow, it is the only step that can INVENT content. On
that run an agent paraphrased `P4C3.5.6.reach_note` ("Both spans establish"
-> "Two spans establishing"); a 2-byte receipt delta was the only thing that
caught it, and the substituted phrasing genuinely exists on a sibling cell,
so a reviewer would have read it as ordinary variation. A file on disk
cannot paraphrase itself. Every byte-receipt mechanism this pipeline used to
need exists to detect a failure mode this script removes.

## What it does

    ship_page.py <run_id> <page> --sections DIR [--promote] [--dry-run]

  1 ASSEMBLE   every `DIR/<page>.<section>.json` into one payload, and merge
                the `<page>.<section>.<shard>.json` shards a big list is
                split across (heatmap's 16 cell_evidence files).
  2 CHECK      the local gate replays that answer without spending a
                submission — a submission SUPERSEDES the staged row, so a
                FAIL on a page that was passing costs that pass and blocks
                the promote for the other five.
  3 SUBMIT     inline under the connector's inline limit, chunked above it,
                reading from disk either way. Parts are planned to a byte
                target and sent in order; the whole is validated
                server-side exactly as an inline payload is.
  4 REPORT     the verdict's STATUS and REASONS. Not the payload, not the
                warnings blob — a passing SG-V4 disclosure list ran to 249
                entries on this run and none of it is actionable.

`--promote` promotes when the page passes AND every other page already
passes; promotion is atomic across all six, so it refuses rather than
half-succeeding.

## What it deliberately does not do

No retries on a FAIL. A gate refusal is a statement about the content, and
the fix belongs in the section file where a human or a producer can see it —
not in a loop that resubmits until the wording happens to pass.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parents[2]
MCP_RAW = PLUGIN / "scripts" / "mcp_raw.py"

PAGES = ("heatmap", "overview", "insights", "platform", "context", "techstack")

#: The one list per section that dominates a page's bytes. A part carrying
#: `items` appends to this path; everything else rides a root `fields` merge.
BIG = {
    "heatmap": [("cell_evidence", "cells"), ("evidence", "evidence"),
                ("evidence_age", "rows"), ("alerts", "alerts")],
    "overview": [("ceilings", "rows"), ("findings", "findings")],
    "platform": [("platform_story", "platforms"),
                 ("recommendations", "recommendations")],
    "context": [("timeline", "events"), ("issue_register", "issues")],
    "techstack": [("techstack", "items")],
    "insights": [("insights", "cards")],
}

INLINE_MAX = 131072          # connector transport.inline_max_bytes
PART_TARGET = 50000          # comfortably under, and small enough to retry


def size(obj) -> int:
    """What the SERVER counts: UTF-8 bytes of its own compact re-encoding."""
    return len(json.dumps(obj, separators=(",", ":"),
                          ensure_ascii=False).encode("utf-8"))


# ---------------------------------------------------------------- assemble

def assemble(sections: Path, page: str) -> dict:
    """Every section file for this page, plus its shards, in one object.

    Shards exist because one section can exceed what a producer writes in a
    single pass (heatmap's `cell_evidence` is 16 files, one per category).
    They are merged in FILENAME order, which is catalogue order, because the
    drawer renders them in the order they arrive.
    """
    payload: dict = {}
    shards: dict[str, list] = {}
    for f in sorted(sections.glob(f"{page}.*.json")):
        rest = f.name[len(page) + 1:-len(".json")]
        parts = rest.split(".")
        body = json.loads(f.read_text(encoding="utf-8"))
        if len(parts) == 1:
            payload.setdefault(parts[0], {}).update(body) \
                if isinstance(body, dict) else payload.__setitem__(parts[0], body)
        else:
            # <section>.<shard> — the shard's own list is concatenated
            shards.setdefault(parts[0], []).append(body)
    for sname, chunks in shards.items():
        key = dict(BIG.get(page, [])).get(sname)
        merged = payload.setdefault(sname, {})
        rows: list = []
        for c in chunks:
            rows.extend(c if isinstance(c, list) else c.get(key or "rows", []))
            if isinstance(c, dict):
                for k, v in c.items():
                    if k != key:
                        merged.setdefault(k, v)
        merged[key or "rows"] = rows
    return payload


# ------------------------------------------------------------------- plan

def plan(payload: dict, page: str, target: int = PART_TARGET) -> list[dict]:
    """Parts, in send order. Root `fields` merges first, then `items`
    appends for each big list, batched to ~`target` bytes.

    The big list is REMOVED from its section's fields part and re-attached by
    the item parts, so no row is sent twice — the connector appends, it does
    not replace.
    """
    big = dict(BIG.get(page, []))
    out: list[dict] = []

    group, acc = {}, 0
    for sname, body in payload.items():
        trimmed = ({k: v for k, v in body.items() if k != big.get(sname)}
                   if isinstance(body, dict) else body)
        s = size(trimmed)
        if group and acc + s > target:
            out.append({"kind": "fields", "path": "", "body": group})
            group, acc = {}, 0
        group[sname] = trimmed
        acc += s
    if group:
        out.append({"kind": "fields", "path": "", "body": group})

    for sname, listkey in BIG.get(page, []):
        rows = (payload.get(sname) or {}).get(listkey) or []
        batch, acc = [], 0
        for row in rows:
            s = size(row)
            if batch and acc + s > target:
                out.append({"kind": "items", "path": f"{sname}.{listkey}",
                            "body": batch})
                batch, acc = [], 0
            batch.append(row)
            acc += s
        if batch:
            out.append({"kind": "items", "path": f"{sname}.{listkey}",
                        "body": batch})
    return out


def expect_of(payload: dict, page: str) -> dict:
    """`expect` for CG-17: the assembled length of every big list.

    Without it a list truncated at a valid element boundary still parses as
    JSON and is invisible — the gate that catches it needs to be told what
    the length should be.
    """
    return {f"{s}.{k}": len((payload.get(s) or {}).get(k) or [])
            for s, k in BIG.get(page, [])
            if (payload.get(s) or {}).get(k) is not None}


# ------------------------------------------------------------------- send

def mcp(tool: str, args: dict) -> dict:
    """One connector call, arguments read from a temp FILE.

    The file is why this pipeline is cheap: `--args-file` means the payload
    never enters a prompt, a transcript, or a model's output.
    """
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as fh:
        json.dump(args, fh, ensure_ascii=False)
        path = fh.name
    try:
        p = subprocess.run(
            [sys.executable, str(MCP_RAW), "call", tool, "--args-file", path],
            capture_output=True, text=True, timeout=1900)  # > mcp_raw SLOW_TOOLS (1800 s for submit)
        raw = (p.stdout or "").strip()
        if not raw:
            return {"_error": (p.stderr or "no output").strip()[:400]}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"_error": raw[:400]}
    finally:
        os.unlink(path)


def verdict_line(res: dict) -> tuple[str, list]:
    v = res.get("verdict") or {}
    return v.get("status", res.get("_error", "?")), (v.get("reasons") or [])


def sg_v4_grounding_fails(res: dict) -> list:
    """The SG-V4 (embedding-grounding) disclosures that FAILED. The connector
    discloses-and-promotes SG results (invariant 12), so these ride in
    `warnings` and never block the connector — measured on the promoted Golden
    1 overview: 249 of them, all ignored. The driver reads them to REVISE
    ungrounded prose before ACCEPTING a page, rather than shipping the claim
    the grounding gate could not support."""
    v = res.get("verdict") or {}
    out = []
    for w in (v.get("warnings") or []):
        if isinstance(w, dict) and w.get("gate_id") == "SG-V4" \
                and str(w.get("result")).upper() == "FAIL":
            out.append({"path": w.get("path"),
                        "similarity": w.get("similarity"),
                        "threshold": w.get("threshold")})
    return out


#: Exit code when the run's lease is held elsewhere. A refused claim is not a
#: failed page: the driver (`engine.pipeline`) waits for the lease to lapse
#: and runs again, and it needs to tell the two apart.
EXIT_CLAIM_REFUSED = 3
#: A lane tried to submit. Measured 2026-10-06 (Arbor Bank): the
#: techstack-surface-producer lane — whose definition says it "returns the
#: assembled page JSON and never submits" — ran `ship_page.py --claim`
#: itself. A lane carries no driver session, so the claim went in under a
#: fresh `ship-page-<uuid>` and its two-hour lease refused the driver's own
#: ship: PAGES_A failed with "another session holds the lease", and that
#: session was the run's own lane. A lane returns section files; the driver
#: ships them. `--dry-run` (assemble and precheck, submit nothing) stays open.
EXIT_LANE_REFUSED = 4


def local_precheck(page: str, payload: dict, *, repo: str | None = None) -> dict:
    """The server's first validation pass, run here before a submission is
    spent on it.

    Measured 28-09-2026 (QA audit F-O07-010): 199 rejections on one page at
    attempts = 2 — two full-page submissions (≈3 MB) for refusals the
    connector's own pass-1 gates would have named locally; replayed over the
    same 102 cells, pass 1 catches 45 of the 46 server refusals (98%),
    CG-15 included. So the pass runs here, through `precheck_gates.py`'s
    loader (the gates are imported, never restated), and a page with a
    blocking reason is not submitted. When the connector package is not
    reachable the result is `not_run`, and the page ships — a check that
    could not run is disclosed, not a refusal to work.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("precheck_gates", HERE / "precheck_gates.py")
    pg = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(pg)
        validation, _v2, _rs, where = pg._load_connector(repo)
    except SystemExit as exc:
        return {"status": "not_run", "why": str(exc)[:200], "reasons": []}
    except Exception as exc:                                     # noqa: BLE001
        return {"status": "not_run", "why": f"{type(exc).__name__}: {exc}"[:200], "reasons": []}
    try:
        reasons = [r for r in validation.validate_pass1(page, payload)
                   if str(r.get("severity", "block")) == "block"
                   and not str(r.get("gate_id", "")).startswith("SG")]
    except Exception as exc:                                     # noqa: BLE001
        return {"status": "not_run", "why": f"validate_pass1 raised {type(exc).__name__}: {exc}"[:200],
                "reasons": []}
    by_gate: dict[str, int] = {}
    for r in reasons:
        by_gate[str(r.get("gate_id") or "?")] = by_gate.get(str(r.get("gate_id") or "?"), 0) + 1
    return {"status": "fail" if reasons else "pass", "gates_from": where,
            "reasons": reasons, "by_gate": by_gate}



def server_order(payload: dict) -> dict:
    """The section order the connector validates in. An inline payload
    arrives as sent; a chunked one is reassembled from JSONB, which returns
    keys shorter-first, then bytewise."""
    if size(payload) <= INLINE_MAX:
        return payload
    return {k: payload[k] for k in sorted(payload, key=lambda k: (len(k), k))}

def sure_to_submit(run_id: str, page: str, payload: dict, *, sections=None,
                   repo: str | None = None) -> dict:
    """Both validation passes, locally, before a submission is spent.

    Owner, 2026-10-07: "You ought to be sure when submitting a page." Pass 1
    (`local_precheck`) needs only the payload; pass 2 (`pass2_replay`) runs
    the server's own `validate_pass2` against a read-only snapshot of the run
    — the half that refused First Tech's heatmap on CG-14, CG-10, CG-48,
    ET-09, AG-01 and AG-03 after pass 1 had passed it clean. A check that
    could not run is `not_run`, and the caller refuses to submit on it: an
    unchecked page is not a page we are sure of.
    """
    pre = local_precheck(page, payload, repo=repo)
    if pre["status"] != "pass":
        return {**pre, "stage": "pass1"}
    import importlib.util
    spec = importlib.util.spec_from_file_location("pass2_replay", HERE / "pass2_replay.py")
    p2 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p2)
    # The server validates a CHUNKED payload as it reassembles it from
    # Postgres JSONB, and JSONB does not keep key order: keys come back
    # shorter-first, then bytewise. Gates that credit a citation to the
    # FIRST section citing it (ET-07's exemption) therefore see a different
    # section than this process's dict order. First Tech platform,
    # 2026-10-07: clean here, refused on ET-07 at roadmap.e_ids.
    payload = server_order(payload)
    r = p2.replay(run_id, page, payload, sections_dir=sections, repo=repo,
                  call=lambda tool, args: mcp(tool, args))
    return {**r, "stage": "pass2"}


def session_id() -> str:
    """The session token the claim is made under — the harness's when it
    exports one, otherwise a fresh one for this process."""
    for k in ("DMA_AGENT_SESSION", "CLAUDE_SESSION_ID", "CLAUDE_AGENT_ID"):
        v = os.environ.get(k)
        if v:
            return v
    import uuid
    return f"ship-page-{uuid.uuid4().hex[:12]}"


def claim(run_id: str, producer: str) -> dict:
    """Take (or renew) the run's exclusive lease before writing to it.

    `claim_run` is an expiring lease, one session per run; another session's
    live lease refuses. Owner issue 7 (2026-09-03): pages shipped as the work
    proceeds means several processes could touch one run over an afternoon —
    the claim is what makes that safe, and the driver never submits without
    it."""
    res = mcp("claim_run", {"run_id": run_id, "session_id": session_id(),
                            "producer_version": producer})
    ok = bool(res.get("claimed") or res.get("ok") or res.get("lease")
              or (res.get("status") or "").lower() in ("claimed", "renewed", "ok"))
    if res.get("_error") or res.get("refused") or (not ok and res.get("held_by")):
        return {"ok": False, "detail": res}
    return {"ok": ok or not res.get("_error"), "detail": res}


def submit(run_id: str, page: str, payload: dict, producer: str) -> dict:
    exp = expect_of(payload, page)
    if size(payload) <= INLINE_MAX:
        return mcp("submit_page_payload",
                   {"run_id": run_id, "page": page, "payload": payload,
                    "producer_version": producer, "expect": exp})

    opened = mcp("open_payload", {"run_id": run_id, "page": page,
                                  "producer_version": producer})
    upload = opened.get("upload_id")
    if not upload:
        return {"_error": f"open_payload failed: {json.dumps(opened)[:300]}"}
    parts = plan(payload, page)
    print(f"  {len(parts)} part(s), {size(payload):,} bytes", flush=True)
    for i, part in enumerate(parts, 1):
        # The connector takes exactly one body per part: `fields` (merge an
        # object at `path`) or `items` (append to the list at `path`, with
        # `item_count` so a short part is refused at receipt). It refused
        # the older {kind, payload} shape with ONE_BODY.
        args = {"upload_id": upload, "part": i, "parts_total": len(parts),
                "path": part["path"]}
        if part["kind"] == "items":
            args["items"] = part["body"]
            args["item_count"] = len(part["body"])
        else:
            args["fields"] = part["body"]
        ack = mcp("append_payload_part", args)
        if ack.get("_error") or ack.get("ok") is False:
            return {"_error": f"part {i}: {json.dumps(ack)[:300]}"}
        print(f"  part {i}/{len(parts)} ack {ack.get('part_bytes')} bytes",
              flush=True)
    return mcp("submit_page_payload",
               {"run_id": run_id, "page": page, "upload_id": upload,
                "producer_version": producer, "expect": exp})


# ------------------------------------------------------------------- main


def contract_sections(page: str) -> list[str] | None:
    """The sections this page's contract declares, from the connector.

    Asked rather than hard-coded: the contract is the thing that decides
    whether a page is complete, and a copy of it here would be wrong the
    first time a section was added. None when the connector cannot be
    reached — the caller then ships nothing rather than guessing a page is
    ready.
    """
    d = mcp("get_page_contract", {"page": page})
    sections = d.get("sections")
    if not isinstance(sections, dict):
        return None
    # REQUIRED only. The contract marks some sections optional — heatmap's
    # `value_chain` and `cohort_patterns` are `required: False` — and a
    # readiness check that ignored that reported a page as "waiting" on a
    # section it never needed. The heatmap had promoted six times without
    # `value_chain` while this said it was incomplete.
    return sorted(n for n, m in sections.items()
                  if not isinstance(m, dict) or m.get("required", True))


def ready_pages(sections: Path, pages=PAGES) -> tuple[list, list]:
    """(ready, waiting) — which pages have every section their contract
    names, and what the others are still missing.

    THIS IS THE CONCURRENT INGESTION. A run does not have to be finished
    before anything reaches the app: a page whose sections are all written
    is submittable the moment they are, and the connector RETAINS staged
    rows, so five pages can sit staged and passing while the sixth is still
    being produced. Promotion stays atomic across all six — that invariant
    is untouched — but the validation, the gate refusals and the byte cost
    of transport all move earlier, to where a producer can still act on
    them cheaply.

    Submitting late is what made a gate refusal expensive: it arrived after
    every page had been written, when fixing one meant re-running the
    transport for all of them.
    """
    ready, waiting = [], []
    for page in pages:
        have = {f.name[len(page) + 1:-len(".json")].split(".")[0]
                for f in sections.glob(f"{page}.*.json")}
        want = contract_sections(page)
        if want is None:
            waiting.append((page, ["contract unreadable"]))
            continue
        missing = [w for w in want if w not in have]
        (ready if have and not missing else waiting).append(
            (page, missing if have else ["no section file written yet"]))
    return ready, waiting

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_id")
    ap.add_argument("page", choices=PAGES + ("all",))
    ap.add_argument("--sections", required=True, type=Path)
    ap.add_argument("--producer", default="surface-synthesis")
    ap.add_argument("--promote", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="assemble and plan, submit nothing")
    ap.add_argument("--incremental", action="store_true",
                    help="ship every page whose contract sections are all "
                         "written, and report what the rest are waiting on. "
                         "Safe to re-run as production proceeds: a page "
                         "already passing is simply submitted again with the "
                         "same content.")
    ap.add_argument("--claim", action="store_true",
                    help="take the run's lease (claim_run) before submitting; "
                         f"exit {EXIT_CLAIM_REFUSED} if another session holds it")
    ap.add_argument("--verdicts-out", type=Path,
                    help="write {page: {status, reasons}} JSON here — the "
                         "driver reads this rather than the transcript")
    ap.add_argument("--no-precheck", action="store_true",
                    help="submit without running the server's pass-1 and "
                         "pass-2 gates locally first. Without this flag a page "
                         "is sent only when both ran and found nothing.")
    ap.add_argument("--repo", default=None,
                    help="checkout of the DMA Insights repository for the local "
                         "precheck; falls back to $DMA_INSIGHTS_REPO and the cwd")
    a = ap.parse_args(argv)
    verdicts: dict = {}
    if (os.environ.get("DMA_IN_LANE") and not os.environ.get("DMA_SHIP_FROM_DRIVER")
            and not a.dry_run):
        print("REFUSED: ship_page.py submits and claims for the DRIVER only. This is a "
              "lane (DMA_IN_LANE is set): write your section files and return — the "
              "driver ships them under its own lease. Use --dry-run to precheck.",
              file=sys.stderr)
        return EXIT_LANE_REFUSED

    def _write_verdicts():
        if a.verdicts_out:
            a.verdicts_out.parent.mkdir(parents=True, exist_ok=True)
            a.verdicts_out.write_text(json.dumps(verdicts, indent=2, default=str))

    if a.claim and not a.dry_run:
        c = claim(a.run_id, a.producer)
        if not c["ok"]:
            print(f"claim on {a.run_id} REFUSED: {json.dumps(c['detail'])[:300]}",
                  file=sys.stderr)
            verdicts["_claim"] = {"status": "claim_refused", "detail": c["detail"]}
            _write_verdicts()
            return EXIT_CLAIM_REFUSED
        print(f"claimed {a.run_id} as {session_id()}")

    pages = PAGES if a.page == "all" else (a.page,)
    if a.incremental:
        ready, waiting = ready_pages(a.sections, pages)
        for page, why in waiting:
            print(f"{page}: waiting on {', '.join(why[:6])}"
                  + (f" (+{len(why) - 6} more)" if len(why) > 6 else ""))
        pages = [p for p, _ in ready]
        if not pages:
            print("\nno page is complete yet — nothing submitted")
            return 0
        print(f"\nshipping {len(pages)} complete page(s): {', '.join(pages)}\n")
    failed = []
    for page in pages:
        payload = assemble(a.sections, page)
        if not payload:
            print(f"{page}: no section files in {a.sections} — skipped")
            continue
        n = size(payload)
        exp = expect_of(payload, page)
        print(f"{page}: {len(payload)} section(s), {n:,} bytes, "
              f"expect={json.dumps(exp)}")
        if a.dry_run:
            for i, p in enumerate(plan(payload, page), 1):
                print(f"  part {i:2d} {p['kind']:6s} {p['path'] or '(root)':28s}"
                      f" {size(p['body']):,}b")
            # "assemble and precheck, submit nothing" (the flag's own help):
            # until 2026-10-07 the dry run stopped before the precheck, so a
            # repair agent told to verify with it saw a clean run on a page
            # the connector's pass-1 gates refuse (First Tech, CG-15 x40).
            if not a.no_precheck:
                pre = sure_to_submit(a.run_id, page, payload, sections=a.sections, repo=a.repo)
                if pre["status"] == "fail":
                    print(f"{page}: DRY RUN — local {pre['stage']} FAIL, "
                          f"{len(pre['reasons'])} blocking reason(s): "
                          + ", ".join(f"{g} x{n}" for g, n in sorted(pre["by_gate"].items())))
                    for r in pre["reasons"][:40]:
                        print("   ", r.get("gate_id"), r.get("path"), "|",
                              str(r.get("message"))[:160])
                    failed.append(page)
                elif pre["status"] == "not_run":
                    print(f"{page}: DRY RUN — local {pre['stage']} NOT RUN — {pre['why']}")
                    failed.append(page)
                else:
                    print(f"{page}: DRY RUN — local precheck clean (pass 1 + pass 2, "
                          f"{pre['gates_from']})"
                          + (f"; unverified locally: {pre['unverified'][:6]}"
                             if pre.get("unverified") else ""))
            continue
        if not a.no_precheck:
            pre = sure_to_submit(a.run_id, page, payload, sections=a.sections, repo=a.repo)
            if pre["status"] != "pass":
                # Fail closed: a page is submitted only when both passes ran
                # locally and found nothing. NOT RUN is not a pass.
                why = (f"{len(pre['reasons'])} blocking reason(s) from the server's own "
                       f"{pre['stage']} gates, run locally ({pre.get('gates_from')}): "
                       + ", ".join(f"{g} x{n}" for g, n in sorted(pre.get("by_gate", {}).items()))
                       if pre["status"] == "fail" else
                       f"the local {pre['stage']} check could not run — {pre.get('why')}")
                print(f"{page}: NOT SUBMITTED — {why}")
                for r in pre["reasons"][:12]:
                    print("   ", r.get("gate_id"), r.get("path"), "|",
                          str(r.get("message"))[:140])
                verdicts[page] = {"status": "local_precheck_fail" if pre["status"] == "fail"
                                  else "local_precheck_not_run",
                                  "stage": pre["stage"],
                                  "n_reasons": len(pre["reasons"]),
                                  # the FULL list: the driver and a repairing
                                  # producer read this file, and a reason past
                                  # the fortieth is still a reason the page fails
                                  "reasons": pre["reasons"] or [why],
                                  "sg_v4_fails": []}
                _write_verdicts()
                failed.append(page)
                continue
            print(f"{page}: local precheck clean, pass 1 + pass 2 ({pre['gates_from']})"
                  + (f"; unverified locally: {pre['unverified'][:6]}" if pre.get("unverified") else ""))
        res = submit(a.run_id, page, payload, a.producer)
        status, reasons = verdict_line(res)
        verdicts[page] = {"status": status, "reasons": reasons,
                          "n_reasons": len(reasons),
                          "sg_v4_fails": sg_v4_grounding_fails(res)}
        _write_verdicts()
        print(f"{page}: {status.upper()} — {len(reasons)} blocking reason(s)")
        for r in reasons[:20]:
            print("   ", json.dumps(r) if isinstance(r, dict) else r)
        if status != "pass":
            failed.append(page)

    _write_verdicts()
    if failed:
        print(f"\nnot submitted clean: {', '.join(failed)}")
        return 1
    if a.promote and not a.dry_run:
        res = mcp("promote_run", {"run_id": a.run_id})
        if res.get("promoted"):
            stats = res.get("stats") or {}
            print("\npromoted " + res.get("promoted_at", "") + " — "
                  + ", ".join(f"{k} {v.get('rows_written')}"
                              for k, v in stats.items()))
            return 0
        print("\npromote refused: " + json.dumps(res)[:400])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
