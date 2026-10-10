#!/usr/bin/env python3
"""One entry point for the whole research engine.

    python3 -m engine.cli start   --run R --entity "Acme CU" --sv CU --scope FULL
    python3 -m engine.cli orient  --run R [--category P1C1]
    python3 -m engine.cli search  --run R --subcap P1C1.1.1 --facet works --query '...'
    python3 -m engine.cli fetch   --run R --url U --query '<the DQ text>'
    python3 -m engine.cli evidence --run R --subcap ... --source ... --url ... --excerpt ...
    python3 -m engine.cli attach  --run R --e-id E-007 --subcap P1C1.1.1
    python3 -m engine.cli synthesise --run R --subcap ... --json rec.json
    python3 -m engine.cli gate    --run R --category P1C1 [--require-synthesis]
    python3 -m engine.cli validate --run R
    python3 -m engine.cli handoff --run R
    python3 -m engine.cli report  --run R [--report both]
    python3 -m engine.cli strip   --run R
    python3 -m engine.cli status  [--root ...]
    python3 -m engine.cli counts

Delegated families — each is `engine.cli <family> <args…>`, passed through
verbatim to the module that owns it (its --help lists the subcommands):

    kg …        engine.kg        build / route / show / verify
    fuse …      engine.retrieval fuse / plan   (RRF + BM25 + query variants)
    memory …    engine.memory    note / status / consolidate / backup / cleanup
    techscan …  engine.techscan  record / render / status /
                                 import-explorium / clay-plan
    assemble …  engine.assemble  open / package / verify / contract
    preflight … engine.preflight init / check / record   (the binding basis)
    prelim …    engine.prelim    state / narrate / timeline / peers /
                                 declare / complete   (the PRELIM phase)
    registry …  engine.registry  log / beat / close / list / push / pull
    grains …    engine.grains    show / recompute / recommendations / stage
                                 (the assessment stage's three scored tabs)
    complete …  engine.completeness check   (every tab populated or stated)
    narrative … engine.narrative  state / write / review / contract
                                 (the report sections, as arguments)
    ers …       engine.ers       recompute / show / explain / formula
    cost …      engine.cost      model / estimate / budget / schedule
    template …  engine.template  id / check / bind / binding / report-drift
                                 (the pinned templates, bound INTO the run)
    profile …   engine.profile   firmographic / focus / issue /
                                 enrichment-needed   (the client's own facts)
    assessment … engine.assessment open / score / critique / rollup /
                                 solution / peer-adoption / gate   (SCORING)
    ship …      engine.ship      state   (which app pages are producible now)
    absence     engine.cli absence --run R --subcap X --ladder <json> …
                                 (close a searched cell as a declared absence)

Every subcommand reads and writes the SAME workbook. There is no second
substrate to fall out of step with, which is the whole point (AUD-0001).
"""
from __future__ import annotations

# Runnable both ways. `python3 -m engine.<mod>` is the documented invocation,
# but every audit and every operator reaches for `python3 <path> --help`
# first, and a relative import dies there. Binding __package__ makes the two
# equivalent instead of making one of them a trap.
if __package__ in (None, ""):  # noqa: E402  (must precede the relative imports)
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import argparse
import json
import sys
from pathlib import Path

from . import (assemble, contract, fetch, floors_gate, handoff, ledger,
               orient, preflight, quality, registry, report_spec, reports,
               runstate, strip_working_area, validator, watchdog)


#: family name -> the module whose main() owns it. Dispatched BEFORE
#: argparse so the family's own --help answers, not this wrapper's.
_FAMILIES = ("kg", "fuse", "memory", "techscan", "assemble", "preflight",
             "prelim", "registry", "complete", "narrative", "ers",
             "cost", "template", "grains", "profile", "assessment", "ship",
             "brief", "pipeline", "relay")


def _family_main(name: str):
    if name == "kg":
        from . import kg as m
    elif name == "fuse":
        from . import retrieval as m
    elif name == "memory":
        from . import memory as m
    elif name == "techscan":
        from . import techscan as m
    elif name == "grains":
        from . import grains as m
    elif name == "preflight":
        from . import preflight as m
    elif name == "prelim":
        from . import prelim as m
    elif name == "registry":
        from . import registry as m
    elif name == "complete":
        from . import completeness as m
    elif name == "narrative":
        from . import narrative as m
    elif name == "ers":
        from . import ers as m
    elif name == "cost":
        from . import cost as m
    elif name == "template":
        from . import template as m
    elif name == "profile":
        from . import profile as m
    elif name == "assessment":
        from . import assessment as m
    elif name == "ship":
        from . import ship as m
    elif name == "brief":
        from . import brief as m
    elif name == "pipeline":
        from . import pipeline as m
    elif name == "relay":
        from . import relay as m
    else:
        from . import assemble as m
    return m.main


#: Installed-plugin states on which a run may not START. A checkout, CI or an
#: environment with no install at all (NOT_INSTALLED / MISSING-from-cache,
#: UNREADABLE) proceeds — the engine is running from the tree it was written
#: in; UPDATED_MID_SESSION proceeds — the disk is already fixed.
REFUSING_INSTALL_STATES = ("STALE", "INCOMPLETE", "DIVERGED", "DISABLED",
                           "MANIFEST_SPLIT")


def install_state() -> dict | None:
    """`plugin_version.compare()` when this engine runs from an INSTALLED
    plugin (a `plugins/cache` path, or CLAUDE_PLUGIN_ROOT set); None from a
    repo checkout or when the check cannot run — fail-open, like the hook.

    Owner issue 10 / RC-1 (2026-09-03): this container bound plugin 0.9.12
    while the checkout published 1.16.0 (now 1.17.0), so a run started here ran none of
    the gates the checkout carries, and nothing refused. The session hook
    warns; this is the mechanical half."""
    import os
    here = str(Path(__file__).resolve())
    if "plugins/cache" not in here and not os.environ.get("CLAUDE_PLUGIN_ROOT"):
        return None
    try:
        scripts = Path(__file__).resolve().parents[3] / "scripts"
        sys.path.insert(0, str(scripts))
        import plugin_version                                  # noqa: PLC0415
        v = plugin_version.compare()
        v["_summary"] = plugin_version.summary(v)
        return v
    except Exception:            # noqa: BLE001 — fail OPEN, on purpose
        return None


def refuse_on_stale_install() -> str | None:
    """The refusal text when a run must not start here, else None.

    Two guards, either refuses: the marketplace-cache check (`install_state`,
    a Claude Code checkout) and the zip guard (`template.zip_guard`, an
    install judging itself — the Cowork upload path, owner decision
    2026-09-03: the plugin runs on both)."""
    from . import template as T
    g = T.zip_guard()
    if not g.get("ok"):
        return (f"REFUSED: this install PREDATES its own templates — {g['fix']} "
                f"A run started here would be gated by an engine older than the "
                f"report contract it binds. (`engine.template zip-guard` shows "
                f"this; `--allow-stale-install` records the waiver on the run.)")
    v = install_state()
    if not v or v.get("ok"):
        return None
    if str(v.get("status") or "") not in REFUSING_INSTALL_STATES:
        return None
    return (f"REFUSED: this container's dma-insights install is "
            f"{v.get('_summary') or v.get('status')}. A run started here binds "
            f"stale agents, hooks and gates. Run `python3 "
            f"plugins/dma-insights/scripts/doctor.py --heal`, then start the "
            f"run from a fresh session (or `engine.pipeline run "
            f"--allow-stale-install` to record the waiver on the run).")


def _actor(a):
    """`--actor` if given, else the agent the dispatcher launched.

    A headless lane cannot be identified from inside a hook (the harness
    carries `agent_type` only within a subagent), so `agent_run.py` puts the
    name in the child's environment and the write CLIs read it from there.
    An empty answer is unconstrained, which is what a person at a terminal
    should be.
    """
    from . import scope as _scope
    return (getattr(a, "actor", None) or _scope.actor_from_env()) or None


def _fetch_cmd(run, a) -> int:
    """`engine.cli fetch` — windows and a hash, never the page.

    WHAT THIS PRINTS IS THE WHOLE POINT. A WebFetched page enters the lane's
    context and is re-read on every later turn: 76% of the measured six-cell
    lane bill was cache reads (24.45M tokens, $4.89 of $6.45). So the page
    is read in THIS process, cached on disk under the run, and what crosses
    back into the agent's context is three ~240-character windows and the
    sha256 that ties them to the document. The full text stays on disk,
    where `engine.cli evidence` checks the excerpt against it.
    """
    if a.via_text is not None:
        text = (sys.stdin.read() if a.via_text == "-"
                else Path(a.via_text).read_text(encoding="utf-8",
                                                errors="replace"))
        if not text.strip():
            print("REFUSED: --via-text got no text. Nothing was cached and "
                  "nothing can be verified against it.", file=sys.stderr)
            return 1
        meta = fetch.store_text(run, a.url, text, content_type="via-text")
        got = {"text": text, "sha256": meta["sha256"], "from_cache": False,
               "error": None}
    else:
        got = fetch.fetch_text(run, a.url)
    if got["error"]:
        # WHY it failed, not merely THAT it failed: a 403 means find another
        # source, an NXDOMAIN means the URL is wrong, a timeout means retry.
        print(f"REFUSED: could not read {a.url} — {got['error']}",
              file=sys.stderr)
        return 1
    wins = fetch.windows(got["text"], a.query, window=a.window,
                         max_windows=a.max_windows)
    out = {"url": a.url, "sha256": got["sha256"], "chars": len(got["text"]),
           "from_cache": got["from_cache"], "query": a.query,
           "published": got.get("published"), "published_basis": got.get("published_basis"),
           "windows": wins}
    if a.json:
        print(json.dumps(out, indent=2))
        return 0
    print(f"{a.url}\n  sha256 {got['sha256']}  chars {out['chars']}  "
          f"cached {str(got['from_cache']).lower()}")
    # The date the PAGE states (its publication metadata or its URL path),
    # for `evidence --published` — never the retrieval date (2026-10-09).
    print(f"  published {got.get('published') or 'not stated'}"
          + (f" ({got.get('published_basis')})" if got.get("published") else
             " — the row goes in undated (UNVERIFIED); never pass today's date"))
    if not wins:
        print(f"  NO WINDOW: nothing in this document carries the terms of "
              f"{a.query!r}. That is an answer — do not quote it anyway.")
        return 0
    for i, w in enumerate(wins, 1):
        print(f"  [{i}] chars {w['start']}-{w['end']} · {w['hits']} term(s)")
        print(f"      {w['text']}")
    return 0


#: The credit-spending connector calls the autoapprove hook withholds unless
#: the run carries an approval record. ONE owner: scripts/hooks/
#: autoapprove_connector.py SPEND_SUFFIXES; test_claim_tier-style pinning in
#: scripts/tests/test_autoapprove_connector.py keeps the two equal.
SPEND_TOOLS = frozenset({
    "tavily_research", "tavily_crawl",
    "enrich-business", "enrich-prospects", "match-business", "match-prospects",
})


def _approve_cmd(run, a) -> dict:
    """Append one approval record to <run>/07_qa/approvals.json.

    The record is the owner's decision, so nothing is inferred: the cost
    line is what they typed. A blank cost line is refused because the
    quoted cost is the whole point of the record."""
    from datetime import datetime, timedelta, timezone   # noqa: PLC0415
    cost = str(a.cost or "").strip()
    who = str(a.approved_by or "").strip()
    if not cost or not who:
        raise SystemExit("REFUSED: --cost and --approved-by must both be "
                         "non-empty. An approval without the quoted cost or "
                         "the approver is not an approval.")
    if a.expires_hours <= 0:
        raise SystemExit("REFUSED: --expires-hours must be positive.")
    path = run.qa_dir / "approvals.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"approvals": []}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("approvals"), list):
                doc = loaded
        except ValueError:
            pass
    now = datetime.now(timezone.utc)
    rec = {
        "tool": a.tool,
        "cost_line": cost,
        "approved_by": who,
        "at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "expires": (now + timedelta(hours=a.expires_hours)
                    ).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "max_calls": a.max_calls,
        "run_id": run.run_id,
    }
    doc["approvals"].append(rec)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return {"path": str(path), "record": rec, "count": len(doc["approvals"])}


BATCH_OPS = ("search", "evidence", "attach", "synthesise", "absence",
             "challenge", "fetch")


def _batch(a) -> int:
    """Many writes, one workbook transaction.

    Measured 2026-09-30 (a multi-LOB live run): one `engine.cli` write took
    ~10 s — interpreter start, a 740 KB workbook load, the exclusive lock,
    a full save — and every writer in the run shares that one lock. A batch
    agent made 27 writes (4.5 of its 12 minutes); 76 batches would have held
    the lock ~5.7 hours end to end, so concurrency past a few agents only
    queued them. Here every command runs against ONE loaded workbook inside
    ONE transaction: one load, one lock acquisition, one save. Each command
    still goes through its own parser and the ledger's refusals; a refused
    command is reported and the rest still apply."""
    import contextlib
    import io
    import shlex
    root = Path(a.root) if a.root else None
    run = runstate.locate(a.run, root)
    wb = run.open()
    wb.autosave = False
    lines = [l.strip() for l in Path(a.file).read_text().splitlines()]
    ops = [l for l in lines if l and not l.startswith("#")]
    results, ok = [], 0
    real_open = runstate.Run.open
    runstate.Run.open = lambda self: wb if self.run_id == run.run_id else real_open(self)
    try:
        with wb.transaction(why=f"engine.cli batch ({len(ops)} ops)"):
            for i, line in enumerate(ops, 1):
                argv = shlex.split(line)
                if argv[:3] == ["python3", "-m", "engine.cli"]:
                    argv = argv[3:]
                if not argv or argv[0] not in BATCH_OPS:
                    results.append({"op": i, "ok": False,
                                    "error": f"not a batchable write: {argv[:1]} "
                                             f"(allowed: {', '.join(BATCH_OPS)})"})
                    continue
                # --run/--root copied from a command sheet are fine when they
                # name THIS run; another run's write in this batch is refused.
                named, clean, j = {}, [], 0
                while j < len(argv):
                    if argv[j] in ("--run", "--root") and j + 1 < len(argv):
                        named[argv[j]] = argv[j + 1]; j += 2; continue
                    clean.append(argv[j]); j += 1
                if (named.get("--run", a.run) != a.run or
                        ("--root" in named and a.root and
                         Path(named["--root"]).resolve() != Path(a.root).resolve())):
                    results.append({"op": i, "ok": False,
                                    "error": f"names another run ({named}); a batch "
                                             f"writes only {a.run}"})
                    continue
                argv = clean
                out = io.StringIO()
                try:
                    with contextlib.redirect_stdout(out):
                        rc = main(argv + ["--run", a.run] +
                                  (["--root", a.root] if a.root else []))
                    good = rc in (0, None)
                    results.append({"op": i, "cmd": argv[0], "ok": good,
                                    "out": out.getvalue().strip()[-300:]})
                    ok += good
                except BaseException as e:          # a refusal is data, not a crash
                    if isinstance(e, KeyboardInterrupt):
                        raise
                    results.append({"op": i, "cmd": argv[0], "ok": False,
                                    "error": (str(e) or e.__class__.__name__)[:600]})
            wb._dirty = True
    finally:
        runstate.Run.open = real_open
    print(json.dumps({"applied": ok, "refused": len(ops) - ok, "results": results},
                     indent=1))
    return 0 if ok == len(ops) else 1


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in _FAMILIES:
        rest = args[1:]
        if args[0] == "fuse" and (not rest or rest[0].startswith("-")):
            # `engine.cli fuse …` is retrieval's own `fuse` subcommand
            # unless the caller already named one (fuse/plan).
            rest = ["fuse"] + rest
        return _family_main(args[0])(rest)

    ap = argparse.ArgumentParser(prog="engine", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for fam in _FAMILIES:
        sub.add_parser(fam, help=f"delegated to engine.{fam if fam != 'fuse' else 'retrieval'} — "
                                 f"run `engine.cli {fam} --help`")

    def common(p):
        p.add_argument("--run", required=True)
        p.add_argument("--root")
        return p

    s = common(sub.add_parser("start"))
    s.add_argument("--entity", required=True)
    s.add_argument("--entity-id", required=True)
    s.add_argument("--scope", default=None, choices=contract.SCOPE_MODES,
                   help="optional: must agree with the preflight's binding")
    s.add_argument("--reference-date", required=True)
    s.add_argument("--preflight", required=True,
                   help="the binding basis: a preflight-v1 document carrying "
                        "the financial-statement review, the LOB census and "
                        "the AskUserQuestion exchange that CONFIRMED the "
                        "sub-vertical and the evidence mode. Build it with "
                        "`engine.preflight init`, fill it, check it with "
                        "`engine.preflight check`. sub-vertical, mode, "
                        "sv_basis, mode_basis and lob_census are all DERIVED "
                        "from it — free-text bases were how a run bound "
                        "itself on a fluent sentence nobody had checked")
    s.add_argument("--allow-stale-install", action="store_true",
                   help="start even though this container's installed plugin "
                        "is stale/incomplete; the waiver is a decision, and "
                        "`doctor.py --heal` is the fix")
    s.add_argument("--no-folder", action="store_true",
                   help="do not open the '<Entity> - DMA' client folder. "
                        "For tests and dry runs only: a real engagement that "
                        "stops early with no folder leaves an operator "
                        "nothing to find")
    s.add_argument("--folder-root", default=None,
                   help="where the client folder is created locally "
                        "(default: beside the run tree)")
    s.add_argument("--no-push", action="store_true",
                   help="do not push the opened folder to the intake Drive")
    # WHERE THE REQUEST CAME FROM. The firing that starts a run is not the
    # firing that finishes it — often days and certainly containers apart —
    # so the thread to answer travels in the workbook or it is lost. The
    # automated intake passes all three; the manual path passes none, and
    # empty means "no thread to answer", which is a state and not a gap.
    s.add_argument("--slack-channel", default="",
                   help="the channel the request was posted in")
    s.add_argument("--slack-thread-ts", default="",
                   help="the request message's ts — the thread the completion "
                        "reply goes back to. Take it from `slack_intake.py "
                        "triage`; a ts typed by hand answers a thread nobody "
                        "asked in")
    s.add_argument("--requested-by", default="",
                   help="the Slack user id that submitted the request")

    o = common(sub.add_parser("orient")); o.add_argument("--category")
    q = common(sub.add_parser("search"))
    q.add_argument("--subcap", action="append", default=[],
                   help="the cell(s) this search bears on. Repeatable: one "
                        "query for a capability genuinely answers its cells, "
                        "and `volley_status` matches SubCap_ID exactly — a "
                        "sibling with no row of its own reads as never "
                        "searched. The search-op ceiling is charged once")
    q.add_argument("--facet", choices=contract.DQ_FACETS + contract.PRELIM_SHEET_FACETS,
                   help="the volley for a cell; with --prelim, the connector-owned "
                        "tab the search was for (focus_areas, issues, "
                        "peer_deployments) — engine.prelim counts these before "
                        "it accepts that tab as legitimately empty")
    q.add_argument("--query", required=True)
    q.add_argument("--actor", default=None,
                   help="the agent logging this search. Defaults to $DMA_ACTOR, "
                        "which the dispatcher sets to the agent it launched. "
                        "A lane may log only its own category's cells "
                        "(engine/scope.py); the servicing tier logs any cell "
                        "in the run, which is how one lane's find reaches "
                        "another lane's")
    q.add_argument("--tool", default="web_search", choices=contract.SEARCH_TOOLS,
                   help="which tool ran — closed vocabulary so the gate can "
                        "count the enrichment effort behind an empty cell")
    q.add_argument("--hits", type=int, default=0); q.add_argument("--kept", type=int, default=0)
    q.add_argument("--outcome", default="")
    q.add_argument("--prelim", action="store_true",
                   help="institution-profile retrieval that belongs to no cell; "
                        "without it --subcap and --facet are required")

    e = common(sub.add_parser("evidence"))
    e.add_argument("--subcap", action="append", default=[],
                   help="the cell(s) this evidence supports. Required unless "
                        "--profile: evidence that reaches no cell supports "
                        "nothing the assessment can read, and banking it "
                        "unmapped is how a register fills with sources no "
                        "drawer can open")
    e.add_argument("--profile", action="store_true",
                   help="this source supports the INSTITUTION PROFILE rather "
                        "than a capability cell — the financial statement, "
                        "the officer schedule, the firmographic record that "
                        "PRELIM's narrative sections cite. Explicit because "
                        "the default must stay 'evidence reaches a cell'")
    e.add_argument("--source", required=True); e.add_argument("--url")
    e.add_argument("--tier", required=True); e.add_argument("--excerpt", required=True)
    e.add_argument("--published",
                   help="when the source was published: YYYY-MM-DD, YYYY-MM, "
                        "YYYY-Qn or YYYY (a quarter IS a date and bands from its "
                        "end — engine/dates.py, the app's own rule). Omitted, the "
                        "row bands UNVERIFIED, never current")
    e.add_argument("--claim-type", default=None, choices=contract.CLAIM_LABELS,
                   help="FACT | INFERENCE | HYPOTHESIS | CEILING_ESTIMATE. "
                        "Omitted, the ledger derives it from --tier (T1/T2 "
                        "-> FACT, weaker -> INFERENCE); a stated FACT on "
                        "T3 or weaker is refused (contract.FACT_TIERS)")
    e.add_argument("--origin", default="public")
    e.add_argument("--unverified", default=None, metavar="REASON",
                   help="register this span WITHOUT a fetched copy of the "
                        "page to check it against, and record why. The CLI "
                        "verifies every public URL against the run's fetch "
                        "cache (`engine.cli fetch`); a URL nothing could "
                        "fetch is refused unless this says what stopped it "
                        "(a 403 WAF, a paywall, a connector's own extract). "
                        "The reason lands on the row's Access_Status as "
                        "`UNVERIFIED: <reason>` — recorded, never silent. It "
                        "does NOT excuse a span a fetched page contradicts")
    e.add_argument("--actor", default=None,
                   help="the agent registering this source. Defaults to "
                        "$DMA_ACTOR. A lane may register only against its own "
                        "category's cells (engine/scope.py); the servicing "
                        "tier registers against any cell in the run")

    gl = common(sub.add_parser(
        "gate-log", help="record one Gate_Log row (non-blocking by default) — the "
                         "way a hand-driven step states a PASS, FAIL or NOT_RUN "
                         "with its reason where a reader of the run looks"))
    gl.add_argument("--gate", required=True)
    gl.add_argument("--scope", default="run")
    gl.add_argument("--verdict", required=True, choices=["PASS", "FAIL", "NOT_RUN"])
    gl.add_argument("--detail", default="")
    gl.add_argument("--blocking", action="store_true")

    rt = common(sub.add_parser(
        "retier", help="move one registered row to another tier, with the "
                       "cascade the tier carries (claim label re-derived, ERS "
                       "recomputed, Provenance and Gate_Log rows written). "
                       "The entity's own domain is never T1."))
    rt.add_argument("--e-id", required=True)
    rt.add_argument("--tier", required=True, choices=[t for t in contract.TIERS
                                                      if t != contract.NO_EVIDENCE])
    rt.add_argument("--reason", required=True,
                    help="why the tier changes (>=20 chars): the ladder rung the "
                         "source actually sits on, and what was mis-filed")
    rt.add_argument("--actor", default=None)

    at = common(sub.add_parser(
        "attach",
        help="cite an evidence row the run ALREADY holds from one of your "
             "own cells, without minting a duplicate. This is how a lead or "
             "a proposal in your dispatch packet becomes a citation."))
    at.add_argument("--e-id", required=True,
                    help="the registered row to cite (E-007). It must already "
                         "exist — `attach` never creates a row; "
                         "`engine.cli evidence` does that")
    at.add_argument("--subcap", action="append", default=[], required=True,
                    help="the cell(s) of YOUR category this row bears on. "
                         "Repeatable. A lane may attach only to its own "
                         "category's cells (engine/scope.py)")
    at.add_argument("--actor", default=None,
                    help="the agent attaching. Defaults to $DMA_ACTOR")
    at.add_argument("--decline", action="store_true",
                    help="the opposite outcome, recorded: you READ the "
                         "proposal and it does not bear on this cell. Needs "
                         "--why. Without this record, 'offered and judged "
                         "irrelevant' and 'offered and never looked at' are "
                         "the same state, and the floors gate's advisory "
                         "`reuse_ignored` cannot tell them apart")
    at.add_argument("--why", default=None,
                    help="with --decline: what the row is actually about and "
                         "why it does not answer this cell")

    ck = sub.add_parser("checkpoint", help="open a fresh search window for one "
                        "category (a new conversation — a workflow agent starting work)")
    ck.add_argument("--run", required=True); ck.add_argument("--root")
    ck.add_argument("--category", required=True)
    ck.add_argument("--position", default="workflow dispatch")
    sub.add_parser("synthesis-template",
                   help="the synthesis record `synthesise --json` takes: every "
                        "field, its floor and its vocabulary, from the ledger")
    y = common(sub.add_parser("synthesise"))
    y.add_argument("--subcap", required=True); y.add_argument("--json", required=True)
    y.add_argument("--actor", required=True,
                   help="the agent name writing this synthesis — recorded to "
                        "Provenance so record_challenge can refuse a "
                        "self-challenge. Required on the CLI because an "
                        "unattributed synthesis makes challenge independence "
                        "unverifiable (AUD-0018/AUD-0024)")

    g = common(sub.add_parser("gate"))
    g.add_argument("--category", required=True)
    g.add_argument("--require-synthesis", action="store_true")
    g.add_argument("--summary", action="store_true",
                   help="print only the verdict, blocking term -> cells and the "
                        "advisory term names (the full document is still "
                        "written to 07_qa/floors_<cat>.json)")

    ab = common(sub.add_parser(
        "absence",
        help="close a subcap with NO evidence as a DECLARED absence: every "
             "askable volley logged, a ladder whose rungs name fired queries, "
             "a proxy log, and what was hunted. The only sanctioned way a "
             "cell ends a run empty."))
    ab.add_argument("--subcap", required=True)
    ab.add_argument("--actor", required=True)
    ab.add_argument("--ladder", required=True,
                    help="JSON list of {rung: direct|proxy|peer|regulatory, "
                         "query: <the query as logged>}")
    ab.add_argument("--proxy-log", required=True,
                    help="which proxy class was hunted and what came back")
    ab.add_argument("--hunted", required=True,
                    help="what was looked for, where, and what came back instead")
    ab.add_argument("--inferable", default=None,
                    help="what the absence still lets you INFER (>= 30 chars); "
                         "comes with --validation-question, labelled INFERENCE "
                         "on the surface and routed to the client conversation")
    ab.add_argument("--validation-question", default=None,
                    help="the question a client answer would settle the "
                         "inference with (>= 15 chars, ends in ?)")
    ab.add_argument("--not-determinable", default=None,
                    help="why no public source can decide this cell (>= 30 "
                         "chars): the triage routes it internal_only instead "
                         "of to another proxy round")
    ab.add_argument("--enrichment-unavailable", action="store_true",
                    help="this container had NO enrichment connector bound, so "
                         "the connector rung could not be climbed. VERIFIED, "
                         "not taken on trust: the run's own recorded connector "
                         "baseline must prove it, and the absence is then "
                         "written with REDUCED rigour and the reason. Without "
                         "a baseline, or with a connector bound and unused, "
                         "the refusal stands")

    vc = common(sub.add_parser(
        "verify-claim",
        help="is this sentence IN the excerpts it cites? Lexical, offline, "
             "deterministic: every figure, name and quoted phrase must be in "
             "the cited excerpts, and the content words mostly so. "
             "entailed / partial / not_supported / frame, with the span and "
             "the missing words. Run it before a synthesis is written "
             "(QA audit F-D04-005, 28-09-2026)"))
    vc.add_argument("--claim", required=True, help="the sentence(s) to verify")
    vc.add_argument("--e-id", action="append", default=[],
                    help="evidence id(s) whose excerpts ground the claim; "
                         "repeatable. Default: every row on --subcap")
    vc.add_argument("--subcap", default=None,
                    help="the cell whose registered rows ground the claim")

    fe = common(sub.add_parser(
        "fetch",
        help="read a page and print only the spans that answer the query — "
             "never the page. A WebFetched page sits in the lane's context "
             # `%%` because argparse %-expands help strings and a bare
             # `%` reads as a format spec — `76% o` died as `%o`, which
             # took `engine/cli.py --help` down entirely (audit_skills).
             "and is re-read on every later turn (76%% of a measured lane's "
             "bill was cache reads); three windows are read once. The "
             "extracted text is cached under the run, which is what lets "
             "`engine.cli evidence` check the excerpt is verbatim"))
    fe.add_argument("--url", required=True)
    fe.add_argument("--query", required=True,
                    help="what you are looking for — the diagnostic "
                         "question's own text works best; the windows are "
                         "ranked on its distinct terms")
    fe.add_argument("--window", type=int, default=fetch.DEFAULT_WINDOW,
                    help=f"characters per window (default "
                         f"{fetch.DEFAULT_WINDOW}: twice the 50-character "
                         f"excerpt floor, half the 500 ceiling)")
    fe.add_argument("--max", type=int, default=fetch.DEFAULT_MAX_WINDOWS,
                    dest="max_windows", help="how many windows")
    fe.add_argument("--via-text", default=None, metavar="PATH",
                    help="do not fetch: read ALREADY-EXTRACTED text from this "
                         "file ('-' for stdin) and cache it under --url. The "
                         "seam for a connector's own extract (Tavily), so a "
                         "span taken from it verifies exactly as a fetched "
                         "one does and no second fetch is bought")
    fe.add_argument("--json", action="store_true")
    # Accepted and ignored: the command sheet says "pass --actor on every
    # write", and a batch line that carries it failed here (R-IMA-20261009,
    # three fetch lines refused; the evidence lines behind them then had no
    # cache to verify against). A fetch is a read; the flag is harmless.
    fe.add_argument("--actor", default=None, help=argparse.SUPPRESS)

    common(sub.add_parser("validate"))
    ch = common(sub.add_parser(
        "challenge", help="record an INDEPENDENT challenge verdict on a synthesis "
                          "(refuses the synthesis's own author / session)"))
    ch.add_argument("--subcap", required=True)
    ch.add_argument("--verdict", required=True, choices=contract.CHALLENGE_VERDICTS)
    ch.add_argument("--actor", required=True)
    ch.add_argument("--rationale", required=True)
    ch.add_argument("--dimension", action="append", default=[],
                    metavar="NAME=PASS|FAIL|NOT_RUN",
                    help="one per dimension; all seven are required: "
                         + ", ".join(contract.CHALLENGE_DIMENSIONS))
    ch.add_argument("--all", choices=("PASS", "NOT_RUN"),
                    help="set every dimension not given by --dimension to this")
    ch.add_argument("--ceiling-band-delta", default="")
    ch.add_argument("--session", default="")
    common(sub.add_parser("handoff"))
    r = common(sub.add_parser("report"))
    r.add_argument("--report", default="both",
                   choices=["client_research", "assessment", "both"])
    r.add_argument("--force", action="store_true")
    common(sub.add_parser("strip")).add_argument("--force", action="store_true")
    common(sub.add_parser("resume"))
    p = common(sub.add_parser("persist")); p.add_argument("--dest")
    st = sub.add_parser("status"); st.add_argument("--root")
    sub.add_parser("counts")
    sub.add_parser("columns", help="the pillar sheets' columns, from the contract "
                                    "(the one owner of the workbook's shape)")
    apv = common(sub.add_parser(
        "approve",
        help="record the owner's approval of ONE credit-spending connector "
             "call for this run, with the cost the owner quoted. The "
             "autoapprove hook opens tavily_research, tavily_crawl and the "
             "Explorium enrich-*/match-* calls only against this record "
             "(07_qa/approvals.json); without it a scheduled firing prompts "
             "and stops (QA audit F-K01-003, 28-09-2026)"))
    apv.add_argument("--tool", required=True, choices=sorted(SPEND_TOOLS),
                     help="the connector tool suffix being approved")
    apv.add_argument("--cost", required=True, metavar="LINE",
                     help="the cost line the owner is approving, verbatim "
                          "(e.g. '2 credits/row x 400 rows = 800 credits'). "
                          "Stated by the owner, never priced here")
    apv.add_argument("--approved-by", required=True,
                     help="who approved it (an email or a name)")
    apv.add_argument("--expires-hours", type=float, default=24.0,
                     help="how long the record stays valid (default 24h)")
    apv.add_argument("--max-calls", type=int, default=None,
                     help="an optional call ceiling, recorded for the audit "
                          "trail; the hook does not count calls")

    cd_ = sub.add_parser("card", help="the capability card: every open cell of one "
                         "capability, the volleys each owes, and batched log lines")
    cd_.add_argument("--run", required=True); cd_.add_argument("--root")
    cd_.add_argument("--capability", required=True)
    bt = common(sub.add_parser(
        "batch", help="apply many write commands (search, evidence, attach, "
                      "synthesise, absence, challenge, fetch) in ONE process, "
                      "ONE workbook load, ONE lock and ONE save"))
    bt.add_argument("--file", required=True,
                    help="one command per line, shell-quoted; the `python3 -m "
                         "engine.cli` prefix and --run/--root are optional (the "
                         "batch supplies them, and refuses another run's); '#' "
                         "lines are skipped")
    a = ap.parse_args(argv)
    if a.cmd == "batch":
        return _batch(a)
    if a.cmd == "synthesis-template":
        # Measured 2026-09-30 (SWBC, P2C3): a lane spent ~20 turns grepping the
        # ledger to learn what this record needs. It is printed from the same
        # constants the refusals read, so it cannot drift from them.
        tpl = {f: f"<at least {n} chars, specific to this cell and its evidence>"
               for f, n in ledger.SYNTHESIS_REQUIRED.items()}
        tpl.update({f: "<the answer this facet's searches gave, or 'NOT_RUN: <reason>'>"
                    for f in ledger.DQ_FIELDS})
        tpl["Claim_Label"] = "|".join(contract.CLAIM_LABELS)
        tpl["Ceiling_Band"] = "<optional: the band the evidence caps the cell at>"
        tpl["_notes"] = ("write to a file, then `engine.cli synthesise --run R "
                         "--root ROOT --subcap X --json <file> --actor <you>`; a "
                         "cell with NO evidence closes only via `engine.cli absence`")
        print(json.dumps(tpl, indent=1)); return 0
    if a.cmd == "counts":
        print(json.dumps(contract.counts(), indent=2)); return 0
    if a.cmd == "columns":
        for i, col in enumerate(contract.PILLAR_COLUMNS):
            n, letters = i + 1, ""
            while n:
                n, r = divmod(n - 1, 26); letters = chr(65 + r) + letters
            print(f"{letters}\t{col}")
        return 0
    if a.cmd == "status":
        return watchdog.main(["--root", a.root or str(runstate.RUN_ROOT), "--json"])

    root = Path(a.root) if a.root else None
    if a.cmd == "start":
        stale = refuse_on_stale_install()
        if stale and not getattr(a, "allow_stale_install", False):
            print(stale, file=sys.stderr)
            return 1
        try:
            pf = preflight.require(a.preflight)
        except preflight.PreflightRefusal as e:
            print(f"REFUSED: {e}", file=sys.stderr)
            return 1
        b = preflight.bases(pf["doc"], pf["report"])
        scope = a.scope or b["scope_mode"]
        if a.scope and a.scope != b["scope_mode"]:
            print(f"REFUSED: --scope {a.scope} disagrees with the preflight's "
                  f"binding.scope_mode {b['scope_mode']}. The preflight is "
                  f"the binding; change it there, or drop the flag.",
                  file=sys.stderr)
            return 1
        run = runstate.start(run_id=a.run, entity_name=a.entity,
                             entity_id=a.entity_id,
                             sub_vertical=b["sub_vertical"],
                             scope_mode=scope, reference_date=a.reference_date,
                             root=root, evidence_mode=b["evidence_mode"],
                             sv_basis=b["sv_basis"],
                             mode_basis=b["mode_basis"],
                             lob_census=b["lob_census"],
                             supplementary=b.get("supplementary", ()))
        # Recorded before anything else touches the workbook: a run that
        # dies in preflight.record still knows which thread was waiting.
        wb = run.open()
        for key, val in (("slack_channel", a.slack_channel),
                         ("slack_thread_ts", a.slack_thread_ts),
                         ("requested_by", a.requested_by)):
            if val:
                wb.set_metadata(key, val)
        recorded = preflight.record(run, pf["doc"], pf["report"])
        out = {"run": run.run_id, "workbook": str(run.workbook_path),
               "selected": len(run.open().selected_subcaps()),
               "evidence_mode": b["evidence_mode"],
               "binding": {"sv": b["sub_vertical"], "scope": scope,
                           "supplementary": list(b.get("supplementary", ())),
                           "sv_basis": b["sv_basis"],
                           "mode_basis": b["mode_basis"],
                           "lob_census": b["lob_census"],
                           "preflight_sha": b["preflight_sha"]},
               "preflight": {"revenue_lines": recorded["revenue_lines"],
                             "evidence_banked": recorded["evidence_banked"]},
               "request": {"slack_channel": a.slack_channel,
                           "slack_thread_ts": a.slack_thread_ts,
                           "requested_by": a.requested_by}}
        if a.no_folder:
            out["client_folder"] = {
                "outcome": "NOT_RUN",
                "reason": "--no-folder was passed; this run has no findable "
                          "client folder and must not be treated as a real "
                          "engagement"}
        else:
            out["client_folder"] = assemble.open_folder(
                run, a.folder_root, push=not a.no_push)
        out["registry"] = registry.log(run, event="STARTED",
                                       detail="run started")
        print(json.dumps(out, indent=2, default=str))
        return 0

    run = runstate.locate(a.run, root)
    if a.cmd == "approve":
        print(json.dumps(_approve_cmd(run, a), indent=2)); return 0
    if a.cmd == "resume":
        try:
            _, state = runstate.resume(a.run, root)
        except runstate.RunDrift as e:
            print(f"REFUSED: {e}", file=sys.stderr); return 1
        print(json.dumps(state, indent=2)); return 0
    if a.cmd == "persist":
        print(json.dumps(runstate.persist(run, a.dest), indent=2)); return 0
    if a.cmd == "fetch":
        return _fetch_cmd(run, a)

    wb = run.open()
    if a.cmd == "checkpoint":
        runstate.checkpoint(wb, a.position, scope=[a.category])
        print(json.dumps({"checkpoint": a.category, "window_remaining":
                          ledger.stats(wb, a.category)["window_remaining"]})); return 0
    if a.cmd == "card":
        print(json.dumps(orient.capability_card(wb, a.capability, run=run),
                         indent=1)); return 0
    if a.cmd == "orient":
        print(json.dumps(orient.orient(wb, a.category, qa_dir=run.qa_dir),
                         indent=2, sort_keys=True)); return 0
    if a.cmd == "search":
        if a.facet in contract.PRELIM_SHEET_FACETS and not a.prelim:
            print(f"REFUSED: --facet {a.facet} names a PRELIM tab; pass --prelim "
                  f"(it belongs to no cell)", file=sys.stderr)
            return 1
        try:
            n = ledger.append_search(wb, subcap=list(a.subcap or []), facet=a.facet,
                                     query=a.query, tool=a.tool, hits=a.hits,
                                     kept=a.kept, outcome=a.outcome,
                                     prelim=a.prelim, actor=_actor(a))
        except ledger.LedgerRefusal as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1
        # The budget line for THIS conversation's window (its category, or
        # PRELIM) — the run-wide count read as "checkpoint_required: true"
        # to every relay subagent once the run passed 60 searches (2026-09-30).
        cells = list(a.subcap or [])
        cat = None if a.prelim or not cells else str(cells[0]).split(".")[0]
        st = ledger.stats(wb, cat)
        if a.prelim or not cells:
            since = ledger._ops_since_checkpoint(wb, "PRELIM")
            st.update(search_ops_since_checkpoint=since,
                      checkpoint_required=since >= ledger.SEARCH_OP_CEILING)
        cap = None if a.prelim else ledger._collector_scope(_actor(a), cells)
        if cap:
            # a collector lane reads ITS window, the one the wall measures
            # (2026-10-09: lanes read the category's and reported a false
            # "checkpoint needed" up to the orchestrator)
            since = ledger._ops_since_checkpoint(wb, cap)
            ceiling = ledger.collector_ceiling(wb, cap)
            st.update(search_ops_since_checkpoint=since,
                      window=ceiling,
                      window_remaining=max(0, ceiling - since),
                      checkpoint_required=since >= ceiling)
        print(json.dumps({"seq": n, "window": cap or cat or "PRELIM", **st}, indent=2)); return 0
    if a.cmd == "evidence":
        cells = [c for c in (a.subcap or []) if str(c).strip()]
        if not cells and not a.profile:
            print("REFUSED: no --subcap. Name the cell(s) this evidence "
                  "supports, or pass --profile if it supports the "
                  "institution profile (a financial statement, an officer "
                  "schedule) rather than a capability.", file=sys.stderr)
            return 1
        if cells and a.profile:
            print("REFUSED: --profile and --subcap together. Profile evidence "
                  "supports the institution; cell evidence supports a "
                  "capability. A row cannot be filed as both.", file=sys.stderr)
            return 1
        try:
            eid = ledger.append_evidence(
                wb, source_name=a.source, source_url=a.url, tier=a.tier,
                excerpt=a.excerpt, subcaps=cells, published=a.published,
                claim_type=a.claim_type, origin=a.origin, actor=_actor(a),
                run=run,
                # ON at the CLI and OFF in the library: this is the path a
                # lane's writes actually take, and every in-process caller
                # (fixtures, stub, handoff) registers against URLs nothing
                # fetched. Flipping the default would rewrite what those
                # mean rather than add a check where it bites.
                verify_excerpts=True, unverified_reason=a.unverified)
        except ledger.LedgerRefusal as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1
        print(json.dumps({"e_id": eid, "profile": bool(a.profile)}, indent=2))
        return 0
    if a.cmd == "gate-log":
        try:
            ledger.append_gate(wb, gate=a.gate, scope=a.scope, verdict=a.verdict,
                               detail=a.detail, blocking=a.blocking)
        except ledger.LedgerRefusal as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1
        print(json.dumps({"gate": a.gate, "scope": a.scope, "verdict": a.verdict}))
        return 0
    if a.cmd == "retier":
        try:
            out = ledger.retier_evidence(wb, a.e_id, a.tier, reason=a.reason,
                                         run=run, actor=_actor(a))
        except ledger.LedgerRefusal as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(out, indent=2))
        return 0
    if a.cmd == "attach":
        cells = [c for c in (a.subcap or []) if str(c).strip()]
        try:
            if a.decline:
                if len(cells) != 1:
                    print("REFUSED: --decline judges ONE proposal on ONE "
                          "cell. Pass a single --subcap.", file=sys.stderr)
                    return 1
                out = ledger.decline_evidence(wb, a.e_id, cells[0],
                                              why=a.why or "",
                                              actor=_actor(a))
            elif a.why:
                print("REFUSED: --why belongs to --decline. An attach needs "
                      "no argument — the citation is the claim, and the "
                      "reasoning belongs in the synthesis that uses it.",
                      file=sys.stderr)
                return 1
            else:
                out = ledger.attach_evidence(wb, a.e_id, cells,
                                             actor=_actor(a))
        except ledger.LedgerRefusal as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(out, indent=2))
        return 0
    if a.cmd == "synthesise":
        rec = json.loads(Path(a.json).read_text())
        print(json.dumps(ledger.append_synthesis(wb, a.subcap, rec,
                                                 actor=a.actor), indent=2))
        return 0
    if a.cmd == "absence":
        lad = json.loads(a.ladder)
        if isinstance(lad, dict):
            lad = [lad]
        print(json.dumps(ledger.declare_absence(
            wb, a.subcap, actor=a.actor, ladder=lad, proxy_log=a.proxy_log,
            what_was_hunted=a.hunted,
            enrichment_unavailable=a.enrichment_unavailable,
            inferable=a.inferable, validation_question=a.validation_question,
            not_determinable=a.not_determinable, run=run), indent=2))
        return 0
    if a.cmd == "verify-claim":
        index = wb.evidence_index()
        # Rows cite fact-level ids (E-003:F1); the register is keyed by row.
        ids = [str(i).strip().split(":")[0] for i in (a.e_id or []) if str(i).strip()]
        if not ids and a.subcap:
            row = wb.scoring_row(a.subcap) or {}
            ids = [i.split(":")[0] for i in ledger._split_ids(row.get("Evidence_IDs"))
                   if i and i != contract.NO_EVIDENCE]
            ids += [e for e, r in index.items()
                    if a.subcap in str(r.get("SubCap_IDs") or "") and e not in ids]
        ids = list(dict.fromkeys(ids))
        if not ids:
            print("REFUSED: name the evidence the claim rests on (--e-id, "
                  "repeatable) or a --subcap with registered rows. A claim "
                  "verified against nothing is not verified.", file=sys.stderr)
            return 1
        unknown = [i for i in ids if i not in index]
        if unknown:
            print(f"REFUSED: evidence id(s) not in this run's register: "
                  f"{unknown}", file=sys.stderr)
            return 1
        excerpts = []
        for i in ids:
            r = index[i]
            excerpts.append(str(r.get("Excerpt") or ""))
            if r.get("Anchor_Quote"):
                excerpts.append(str(r.get("Anchor_Quote") or ""))
        out = quality.verify_claim(a.claim, excerpts,
                                   entity=wb.metadata().get("entity_name"))
        out["e_ids"] = ids
        print(json.dumps(out, indent=2))
        return 1 if out["verdict"] == "not_supported" else 0
    if a.cmd == "gate":
        out = floors_gate.run(wb, a.category,
                              require_synthesis=a.require_synthesis,
                              qa_dir=run.qa_dir)
        print(json.dumps(floors_gate.summary(out) if a.summary else out,
                         indent=2, sort_keys=True))
        return 0 if out["gate"] == "PASS" else 1
    if a.cmd == "validate":
        return validator.main(["--workbook", str(run.workbook_path),
                               "--run-id", a.run])
    if a.cmd == "challenge":
        dims = {}
        for d in a.dimension:
            if "=" not in d:
                print(f"REFUSED: --dimension {d!r} is not NAME=VERDICT", file=sys.stderr)
                return 1
            k, v = d.split("=", 1)
            dims[k.strip()] = v.strip().upper()
        if a.all:
            for k in contract.CHALLENGE_DIMENSIONS:
                dims.setdefault(k, a.all)
        try:
            out = ledger.record_challenge(
                wb, a.subcap, verdict=a.verdict, actor=a.actor, dimensions=dims,
                rationale=a.rationale, ceiling_band_delta=a.ceiling_band_delta,
                session=a.session)
        except ledger.LedgerRefusal as e:
            print(f"REFUSED: {e}", file=sys.stderr)
            return 1
        print(json.dumps(out, indent=2, default=str))
        return 0
    if a.cmd == "handoff":
        return handoff.main(["--run", a.run] + (["--root", str(root)] if root else []))
    if a.cmd == "report":
        args = ["--run", a.run, "--report", a.report]
        if root: args += ["--root", str(root)]
        if a.force: args += ["--force"]
        return reports.main(args)
    if a.cmd == "strip":
        hp = run.deliverables / handoff.HANDOFF_NAME
        print(json.dumps(strip_working_area.strip(
            run.workbook_path, handoff=hp if hp.exists() else None,
            force=a.force), indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
