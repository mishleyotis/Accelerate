"""engine.pipeline — THE DRIVER. One command runs an assessment from a started
run to a promoted one, gate by gate, dispatching lanes over briefs and
shipping pages to the connector as the work becomes ready.

    python3 -m engine.pipeline run    --run <R> --root <ROOT> [--dispatcher agent_run|stub]
                                      [--until STAGE] [--max-wall-min N] [--max-rounds N]
                                      [--lane-retries N] [--page-retries N]
                                      [--ingest-poll-s S --ingest-timeout-s S]
                                      [--folder-root DIR] [--no-push] [--allow-stale-install]
    python3 -m engine.pipeline plan   --run <R> --root <ROOT>      # done / next / blockers; dispatches nothing
    python3 -m engine.pipeline status --run <R> --root <ROOT> [--watch]
    python3 -m engine.pipeline env                                 # every hard dependency, measured
    python3 -m engine.pipeline stages                              # the stage table

WHY (owner, 2026-09-03, issues 6–9): the conductor NARRATED ten stages and
dispatched most of them "with the run id and the root"; the scorers, the
critic, the report producers and the page producers had no brief; the
handback was computed and never fed back; nothing recorded where six hours
went; ship-as-you-go stopped at a Cloud Scheduler hop nobody drove. This
module is the mechanism the prose described.

THE STAGE TABLE (in order; each stage has a DONE predicate read from the
workbook and the run tree, WORK that dispatches lanes over `engine.brief`
packets and runs engine commands, and a GATE that must PASS before the next
stage starts):

    PREFLIGHT  the binding is recorded (preflight answered)          — checked, never done here
    START      the run exists and is bound to the pinned templates   — checked, never done here
    PRELIM     the institution before its capabilities               lanes: conductor (PRELIM-only), scanner, connectors
    KG         DQ_Bank seeded from the toolkits (fallback stated)     engine.kg build
    RESEARCH   every category's floors gate PASS                     lanes: 16 researchers → challengers → gates; rounds
    HANDOFF    research_handoff.json, research_ready == []           engine.handoff
    SCORING    SCORING gate PASS                                     lanes: 4 scorers, solutions, critic → rollup → gate
    INGEST_A   checkpoint pushed; connector ingested version A       engine.assemble checkpoint → poll list_pending_runs
    REPORTS    both reports READY and rendered                        lanes: 2 producers → validator; rounds
    PAGES_A    techstack + heatmap shipped to version A               lanes: page producers → ship_page --claim
    PACKAGE    '<Entity> - DMA' verified (gold gate clean), pushed    engine.techscan render, engine.assemble package
    INGEST_B   connector ingested version B                           poll list_pending_runs
    PAGES_B    A pages restaged from disk; overview, insights,        lanes → ship_page
               platform, then context (after overview) shipped to B
    PROMOTE    promote_run — the final connector call                 ship_page / mcp_raw

Exactly TWO ingests (a scored checkpoint and the package), so a run gets two
versions rather than eighteen; the early pages ship to version A while the
reports are written, are restaged from disk to version B, and `promote_run`
is the last call the pipeline makes.

Every stage records `STAGE_<NAME>` in Gate_Log with its verdict and wall
clock, appends to the cost ledger (`engine.cost record`), writes the driver
state to `07_qa/pipeline_state.json` and heartbeats the registry — so a run
that stops says where, and `run` again continues from the first stage whose
DONE predicate is false. Connector WRITES go only through `ship_page.py`;
connector READS go through `mcp_raw.py`; the driver never holds a payload.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from . import contract as C
from . import ledger as L
from . import runstate
from .workbook import RunWorkbook

PIPELINE_VERSION = "1.0"
STATE_NAME = "pipeline_state.json"
SECTIONS_DIR = "08_sections"
BRIEFS_DIR = "briefs"

STAGES = ("PREFLIGHT", "START", "PRELIM", "KG", "RESEARCH", "HANDOFF", "SCORING",
          "INGEST_A", "REPORTS", "PAGES_A", "PACKAGE", "INGEST_B", "PAGES_B",
          "PROMOTE")

#: Which pages ship at which version. `ship.PAGE_NEEDS` decides: techstack
#: and heatmap need the scored workbook and no report; overview, insights and
#: platform read a READY report; context renders after overview (O9 before
#: C4, `ship.PAGE_AFTER`). So the early pages are the two the scan can serve
#: from a scored checkpoint, and the rest wait for the package.
PAGES_A = ("techstack", "heatmap")
PAGES_B = (("overview", "insights", "platform"), ("context",))

PLUGIN = Path(__file__).resolve().parents[3]
AGENT_RUN = PLUGIN / "scripts" / "agent_run.py"
MCP_RAW = PLUGIN / "scripts" / "mcp_raw.py"
SHIP_PAGE = PLUGIN / "skills" / "dma-surface-production" / "scripts" / "ship_page.py"


def _utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class StageRefused(Exception):
    """A stage could not complete; the message names the blocker."""


# ── the three seams the driver talks through ─────────────────────────────

class Dispatcher(Protocol):
    def dispatch(self, batch_path: Path, *, stage: str, lanes: int, retries: int,
                 ctx: "Pipeline") -> dict: ...


class ConnectorReads(Protocol):
    def pending_runs(self) -> list[dict]: ...
    def page_contract(self, page: str) -> dict: ...


class Shipper(Protocol):
    def ship(self, connector_run: str, page: str, sections_dir: Path,
             verdicts_out: Path) -> dict: ...
    def promote(self, connector_run: str) -> dict: ...


class AgentRunDispatcher:
    """Real lanes: `agent_run.py --batch` as a child process, with retries,
    timings and the cost record the batch itself writes."""

    def __init__(self, timeout: int = 2400, stream: bool = True):
        self.timeout, self.stream = timeout, stream

    def dispatch(self, batch_path, *, stage, lanes, retries, ctx):
        timing = ctx.run.qa_dir / f"lanes_{stage}_{int(time.time())}.json"
        cmd = [sys.executable, str(AGENT_RUN), "--batch", str(batch_path),
               "--lanes", str(lanes), "--retries", str(retries),
               "--timeout", str(self.timeout), "--timing-out", str(timing),
               "--record-run", ctx.run.run_id, "--record-root", str(ctx.run.root),
               "--record-stage", stage]
        if self.stream:
            cmd += ["--stream", "--log-dir", str(ctx.run.root / "agent_logs")]
        r = subprocess.run(cmd, capture_output=True, text=True,
                           cwd=str(PLUGIN.parents[1]))
        summary = {}
        if timing.is_file():
            try:
                summary = json.loads(timing.read_text())
            except ValueError:
                summary = {}
        summary.setdefault("rc", r.returncode)
        summary.setdefault("stderr_tail", (r.stderr or "")[-600:])
        return summary


class McpReads:
    """Connector READS over `mcp_raw.py call` — no payload ever in a prompt."""

    def _call(self, tool: str, args: dict | None = None) -> dict:
        r = subprocess.run([sys.executable, str(MCP_RAW), "call", tool,
                            "--args", json.dumps(args or {})],
                           capture_output=True, text=True, timeout=600)
        raw = (r.stdout or "").strip()
        try:
            return json.loads(raw) if raw else {"_error": (r.stderr or "no output")[:300]}
        except ValueError:
            return {"_error": raw[:300]}

    def pending_runs(self) -> list[dict]:
        out = self._call("list_pending_runs")
        if isinstance(out, dict):
            return list(out.get("pending") or out.get("runs") or [])
        return list(out or [])

    def page_contract(self, page: str) -> dict:
        return self._call("get_page_contract", {"page": page})


class ShipPageShipper:
    """Connector WRITES only through ship_page.py (claim, submit) and, for
    the final call, promote_run through mcp_raw — the two audited paths."""

    def __init__(self, producer: str = "engine.pipeline"):
        self.producer = producer

    def ship(self, connector_run, page, sections_dir, verdicts_out):
        r = subprocess.run(
            [sys.executable, str(SHIP_PAGE), connector_run, page,
             "--sections", str(sections_dir), "--producer", self.producer,
             "--claim", "--verdicts-out", str(verdicts_out)],
            capture_output=True, text=True, timeout=1800)
        verdict = {}
        if Path(verdicts_out).is_file():
            try:
                verdict = json.loads(Path(verdicts_out).read_text()).get(page) or {}
            except ValueError:
                verdict = {}
        status = verdict.get("status") or ("pass" if r.returncode == 0 else
                                           "claim_refused" if r.returncode == 3 else "fail")
        return {"status": status, "reasons": verdict.get("reasons") or
                ([(r.stderr or r.stdout)[-400:]] if r.returncode else []),
                "rc": r.returncode}

    def promote(self, connector_run):
        r = subprocess.run([sys.executable, str(MCP_RAW), "call", "promote_run",
                            "--args", json.dumps({"run_id": connector_run})],
                           capture_output=True, text=True, timeout=600)
        try:
            return json.loads((r.stdout or "").strip() or "{}")
        except ValueError:
            return {"_error": (r.stdout or r.stderr)[-300:]}


# ── options and state ────────────────────────────────────────────────────

@dataclass
class Options:
    dispatcher: Dispatcher
    reads: ConnectorReads
    shipper: Shipper
    until: str | None = None
    max_wall_min: float | None = None
    max_rounds: int = 3
    lane_retries: int = 1
    page_retries: int = 2
    ingest_poll_s: float = 60.0
    ingest_timeout_s: float = 3600.0
    folder_root: Path | None = None
    push: bool = True
    allow_stale_install: bool = False
    lanes: int | None = None
    toolkit_dir: Path | None = None
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    log: Callable[[str], None] = field(default=lambda s: print(s, flush=True))


def _load_state(path: Path) -> dict:
    if path.is_file():
        try:
            return json.loads(path.read_text())
        except ValueError:
            pass
    return {"pipeline_version": PIPELINE_VERSION, "stages": {}, "pages": {},
            "connector": {}, "package": {}, "invocations": []}


class Pipeline:
    def __init__(self, run: runstate.Run, opts: Options):
        self.run, self.opts = run, opts
        self.wb = run.open()
        self.state_path = run.qa_dir / STATE_NAME
        self.state = _load_state(self.state_path)
        self.t_start = opts.clock()
        self.dispatched: list[dict] = []

    # ── plumbing ───────────────────────────────────────────────────────
    def reopen(self) -> RunWorkbook:
        """Lanes write the FILE; the driver re-reads it after every batch."""
        self.wb = self.run.open()
        return self.wb

    def _save_state(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.state, indent=2, default=str))

    def _md(self) -> dict:
        return self.wb.metadata()

    def _set_md(self, key: str, value):
        self.wb.set_metadata(key, value)

    def _lanes(self) -> int:
        from . import cost
        return int(self.opts.lanes or cost.PARALLEL_LANES)

    def _dispatch(self, batch: dict, *, stage: str) -> dict:
        if not batch.get("batch") or not batch.get("lanes"):
            return {"dispatched": 0, "ok": 0, "failed": []}
        summary = self.opts.dispatcher.dispatch(
            Path(batch["batch"]), stage=stage, lanes=self._lanes(),
            retries=self.opts.lane_retries, ctx=self)
        self.dispatched.append({"stage": stage, "batch": batch["batch"],
                                "lanes": batch["lanes"],
                                "failed": summary.get("failed") or []})
        self.reopen()
        return summary

    def _briefs(self, name: str) -> Path:
        return self.run.root / BRIEFS_DIR / name

    def _record(self, stage: str, verdict: str, detail: str, t0: float,
                *, rounds: int = 0, lanes: int = 0, attempts: int = 0):
        elapsed = round(self.opts.clock() - t0, 1)
        try:
            L.append_gate(self.wb, gate=f"STAGE_{stage}", scope="run",
                          verdict=verdict,
                          detail=f"{detail} [elapsed {elapsed}s; rounds {rounds}]"[:900],
                          blocking=True)
        except Exception as e:                       # noqa: BLE001
            self.opts.log(f"  (gate log not written: {str(e)[:120]})")
        try:
            from . import cost
            cost.record(self.run, stage=stage, elapsed_s=elapsed, lanes=lanes or None,
                        attempts=attempts or None, note=f"pipeline {verdict}: {detail[:200]}",
                        wb=self.wb)
        except Exception as e:                       # noqa: BLE001
            self.opts.log(f"  (cost not recorded: {str(e)[:120]})")
        st = self.state["stages"].setdefault(stage, {})
        st.update({"verdict": verdict, "detail": detail[:600], "elapsed_s": elapsed,
                   "ended_at": _utcnow(), "rounds": rounds})
        st["runs"] = int(st.get("runs") or 0) + 1
        self._save_state()
        try:
            from . import registry
            registry.log(self.run, event="STAGE", position=f"{stage}:{verdict}",
                         detail=detail[:200])
        except Exception:                            # noqa: BLE001
            pass
        self.opts.log(f"[{stage}] {verdict} — {detail[:160]} ({elapsed}s)")

    def _over_wall(self) -> bool:
        if self.opts.max_wall_min is None:
            return False
        return (self.opts.clock() - self.t_start) / 60.0 >= self.opts.max_wall_min

    # ── DONE predicates ────────────────────────────────────────────────
    def done(self, stage: str) -> tuple[bool, str]:
        md = self._md()
        wb = self.wb
        if stage == "PREFLIGHT":
            # An API start records `UNSTATED — …` as its basis; that is the
            # absence of a binding, not one. The recorded preflight file is
            # the other proof (`preflight.record`, which `engine.cli start`
            # and the binding preflight both write).
            sv = str(md.get("sv_basis") or "").strip()
            ok = (bool(sv) and not sv.upper().startswith("UNSTATED")) or \
                (self.run.root / "00_entity_profile" / "preflight.json").is_file()
            return ok, ("binding recorded" if ok else
                        "no binding basis on the run: start it with `engine.cli start "
                        "--preflight <answered preflight.json>`")
        if stage == "START":
            from . import template as T
            b = T.binding_state(wb)
            return bool(b["bound"]), ("bound to the pinned templates" if b["bound"]
                                      else f"unbound: {b['fix']}")
        if stage == "PRELIM":
            from . import prelim
            st = prelim.state(wb)
            ok = st["prelim_status"] == "COMPLETE"
            return ok, ("PRELIM complete" if ok else f"PRELIM open: {', '.join(st['open'])}")
        if stage == "KG":
            from . import completeness
            n = len([r for r in wb.rows("DQ_Bank") if any(r.values())])
            ok = n > 0 or "DQ_Bank" in completeness.reasons(wb)
            return ok, (f"DQ_Bank {n} rows" if ok else "DQ_Bank empty")
        if stage == "RESEARCH":
            from . import brief
            need = brief.categories_needing_dispatch(wb)
            ok = not need["dispatch"]
            return ok, ("every category gate PASS" if ok else
                        f"categories not passing: {', '.join(need['dispatch'])}")
        if stage == "HANDOFF":
            from . import assessment as A
            from . import handoff
            hp = self.run.deliverables / handoff.HANDOFF_NAME
            pre = A.research_ready(wb, self.run.qa_dir)
            ok = hp.is_file() and not pre
            return ok, ("handoff written; research ready" if ok else
                        (f"{len(pre)} research-ready blocker(s): {pre[0][:160]}" if pre
                         else "research_handoff.json missing"))
        if stage == "SCORING":
            from . import assessment as A
            last = (A.state(wb).get("last_scoring_gate") or {})
            ok = str(last.get("verdict") or "") == "PASS"
            return ok, ("SCORING gate PASS" if ok else
                        f"SCORING gate {last.get('verdict') or 'NOT_RUN'}")
        if stage == "INGEST_A":
            ok = bool(str(md.get("connector_run_id") or "").strip())
            return ok, (f"connector run {md.get('connector_run_id')}" if ok
                        else "no connector run id: checkpoint not ingested")
        if stage == "REPORTS":
            from . import narrative as N
            st = N.state(wb)
            ready = all(v.get("ready") for v in st["reports"].values())
            files = [sorted(self.run.deliverables.glob(p)) for p in
                     ("Client_Profile_Research_*.docx", "DMA_Assessment_Report_*.docx")]
            recs = [r for r in wb.rows("Recommendations") if any(r.values())]
            ok = ready and all(files) and bool(recs)
            return ok, ("both reports READY and rendered; recommendations projected" if ok else
                        ("reports not READY: " + ", ".join(
                            k for k, v in st["reports"].items() if not v.get("ready"))
                         if not ready else
                         "reports READY but not rendered" if not all(files) else
                         "Recommendations not projected from the report's REC cards"))
        if stage == "PAGES_A":
            ok = self._pages_passed(PAGES_A, "A")
            return ok, ("techstack, heatmap shipped to version A" if ok else
                        f"pending: {', '.join(p for p in PAGES_A if not self._page_ok(p, 'A'))}")
        if stage == "PACKAGE":
            pk = self.state.get("package") or {}
            ok = bool(pk.get("verified")) and Path(str(pk.get("folder") or "/nonexistent")).is_dir()
            return ok, (f"package verified at {pk.get('folder')}" if ok else "no verified package")
        if stage == "INGEST_B":
            prev, cur = md.get("connector_run_id_prev"), md.get("connector_run_id")
            ok = bool(str(prev or "").strip()) and str(cur) != str(prev)
            return ok, (f"version B ingested as {cur} (A was {prev})" if ok
                        else "package not yet ingested as a new version")
        if stage == "PAGES_B":
            allp = PAGES_A + tuple(p for g in PAGES_B for p in g)
            ok = self._pages_passed(allp, "B")
            return ok, ("all six pages PASS on version B" if ok else
                        f"pending: {', '.join(p for p in allp if not self._page_ok(p, 'B'))}")
        if stage == "PROMOTE":
            ok = bool(str(md.get("promoted_at") or "").strip())
            return ok, (f"promoted at {md.get('promoted_at')}" if ok else "not promoted")
        raise KeyError(stage)

    def _page_ok(self, page: str, version: str) -> bool:
        p = (self.state.get("pages") or {}).get(page) or {}
        return (p.get("versions") or {}).get(version) == "pass"

    def _pages_passed(self, pages, version) -> bool:
        return all(self._page_ok(p, version) for p in pages)

    # ── PLAN ───────────────────────────────────────────────────────────
    def plan(self) -> dict:
        rows, nxt = [], None
        for st in STAGES:
            try:
                ok, why = self.done(st)
            except Exception as e:                   # noqa: BLE001
                ok, why = False, f"could not evaluate: {str(e)[:160]}"
            rows.append({"stage": st, "done": ok, "detail": why,
                         "recorded": (self.state.get("stages") or {}).get(st)})
            if nxt is None and not ok:
                nxt = st
        return {"run_id": self.run.run_id, "root": str(self.run.root),
                "stages": rows, "next": nxt,
                "complete": nxt is None,
                "blockers": [r["detail"] for r in rows if not r["done"]][:3],
                "command": (f"python3 -m engine.pipeline run --run {self.run.run_id} "
                            f"--root {self.run.root}" if nxt else None)}

    # ── RUN ────────────────────────────────────────────────────────────
    def run_all(self) -> dict:
        from . import cli as _cli
        stale = _cli.refuse_on_stale_install()
        if stale and not self.opts.allow_stale_install:
            return {"outcome": "REFUSED", "reason": stale, "stage": None}
        if stale:
            self.state.setdefault("waivers", []).append(
                {"at": _utcnow(), "stale_install": stale[:300]})
        self._set_md("pipeline_version", PIPELINE_VERSION)
        self.state["invocations"].append({"at": _utcnow(), "until": self.opts.until})
        self._save_state()
        outcome = {"outcome": "COMPLETE", "stage": None, "stages_run": [],
                   "dispatched": self.dispatched}
        for st in STAGES:
            ok, why = self.done(st)
            if ok:
                self.state["stages"].setdefault(st, {}).setdefault("verdict", "PASS")
                self.state["stages"][st]["done_detail"] = why
                self._save_state()
                self.opts.log(f"[{st}] done — {why[:140]}")
                if self.opts.until == st:
                    outcome.update(outcome="STOPPED_AT_UNTIL", stage=st)
                    return outcome
                continue
            if st in ("PREFLIGHT", "START"):
                self._record(st, "FAIL", why, self.opts.clock())
                outcome.update(outcome="BLOCKED", stage=st, reason=why)
                return outcome
            if self._over_wall():
                outcome.update(outcome="STOPPED_WALL_CLOCK", stage=st,
                               reason=f"--max-wall-min {self.opts.max_wall_min} reached "
                                      f"before {st}; resume: {self.plan()['command']}")
                return outcome
            t0 = self.opts.clock()
            try:
                detail = getattr(self, f"_stage_{st.lower()}")()
                ok2, why2 = self.done(st)
                if not ok2:
                    raise StageRefused(f"stage ran but is not done: {why2}")
                self._record(st, "PASS", detail, t0, rounds=self._rounds,
                             lanes=self._lane_count, attempts=self._attempts)
                outcome["stages_run"].append(st)
            except (StageRefused, SystemExit, L.LedgerRefusal, ValueError,
                    KeyError, RuntimeError) as e:
                msg = str(e).strip() or e.__class__.__name__
                self._record(st, "FAIL", msg[:600], t0, rounds=self._rounds,
                             lanes=self._lane_count, attempts=self._attempts)
                outcome.update(outcome="FAILED", stage=st, reason=msg[:800],
                               resume=self.plan()["command"])
                return outcome
            if self.opts.until == st:
                outcome.update(outcome="STOPPED_AT_UNTIL", stage=st)
                return outcome
        return outcome

    # per-stage bookkeeping the record reads
    _rounds = 0
    _lane_count = 0
    _attempts = 0

    def _reset_counters(self):
        self._rounds = self._lane_count = self._attempts = 0

    def _count(self, summary: dict):
        self._lane_count += int(summary.get("dispatched") or 0)
        self._attempts += sum(int(l.get("attempts") or 1)
                              for l in (summary.get("lanes_detail") or []))

    # ── STAGES ─────────────────────────────────────────────────────────
    def _stage_prelim(self) -> str:
        from . import brief, prelim
        self._reset_counters()
        for r in range(self.opts.max_rounds):
            self._rounds = r + 1
            b = brief.prelim_brief(self.wb, run=self.run, out_dir=self._briefs(f"prelim_r{r}"))
            self._count(self._dispatch(b, stage="PRELIM"))
            st = prelim.state(self.wb)
            if not st["open"]:
                if st["recorded_status"] != "COMPLETE":
                    prelim.complete(self.wb)
                return f"PRELIM closed after {r + 1} round(s)"
        raise StageRefused(f"PRELIM still open after {self.opts.max_rounds} round(s): "
                           f"{', '.join(prelim.state(self.wb)['open'])}")

    def _stage_kg(self) -> str:
        from . import kg
        self._reset_counters()
        tk = self.opts.toolkit_dir or (Path(os.environ["DMA_TOOLKITS_DIR"])
                                       if os.environ.get("DMA_TOOLKITS_DIR") else None)
        out = kg.build(self.wb, toolkit_dir=tk)
        self.reopen()
        n = len([r for r in self.wb.rows("DQ_Bank") if any(r.values())])
        probs = out.get("problems") if isinstance(out, dict) else None
        return (f"DQ_Bank seeded: {n} rows" + (f"; {len(probs)} problem(s) stated: "
                                                  f"{probs[0][:120]}" if probs else ""))

    def _stage_research(self) -> str:
        from . import brief, floors_gate
        self._reset_counters()
        for r in range(self.opts.max_rounds):
            self._rounds = r + 1
            need = brief.categories_needing_dispatch(self.wb)
            if not need["dispatch"]:
                return f"every category PASS after {r} round(s)"
            b = brief.batch(self.wb, run=self.run, out_dir=self._briefs(f"research_r{r}"),
                            only=need["dispatch"], with_handback=(r > 0))
            self._count(self._dispatch(b, stage="RESEARCH"))
            cb = brief.challenge_batch(self.wb, run=self.run,
                                       out_dir=self._briefs(f"challenge_r{r}"))
            if cb.get("lanes"):
                self._count(self._dispatch(cb, stage="CHALLENGE"))
            for cat in need["dispatch"]:
                floors_gate.run(self.wb, cat, require_synthesis=True, qa_dir=self.run.qa_dir)
            self.reopen()
        need = brief.categories_needing_dispatch(self.wb)
        if need["dispatch"]:
            raise StageRefused(
                f"{len(need['dispatch'])} category(ies) still failing the floors gate after "
                f"{self.opts.max_rounds} round(s): "
                + "; ".join(f"{c}: {', '.join(need['reasons'][c][:4])}"
                            for c in need["dispatch"][:4]))
        return f"every category PASS after {self.opts.max_rounds} round(s)"

    def _stage_handoff(self) -> str:
        from . import assessment as A
        from . import handoff
        self._reset_counters()
        pre = A.research_ready(self.wb, self.run.qa_dir)
        if pre:
            raise StageRefused("research is not ready to score:\n  - " + "\n  - ".join(pre))
        doc = handoff.build(self.wb, qa_dir=self.run.qa_dir, strict=True)
        out = self.run.deliverables / handoff.HANDOFF_NAME
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, indent=2, default=str))
        self.reopen()
        return f"handoff written: {len(doc.get('subcap_records') or [])} records"

    def _stage_scoring(self) -> str:
        from . import assessment as A
        from . import brief
        self._reset_counters()
        if C.stage_of(self._md()) != "assessment":
            A.open_stage(self.wb, self.run.qa_dir)
            self.reopen()
        for r in range(self.opts.max_rounds):
            self._rounds = r + 1
            b = brief.scoring_batch(self.wb, run=self.run, out_dir=self._briefs(f"scoring_r{r}"))
            self._count(self._dispatch(b, stage="SCORING"))
            if r == 0:
                s = brief.scoring_batch(self.wb, run=self.run,
                                        out_dir=self._briefs("scoring_solutions"), solutions=True)
                self._count(self._dispatch(s, stage="SCORING"))
            c = brief.scoring_batch(self.wb, run=self.run,
                                    out_dir=self._briefs(f"scoring_critic_r{r}"), critic=True)
            self._count(self._dispatch(c, stage="SCORING"))
            rollup_note = ""
            try:
                A.rollup(self.wb)
            except A.ScoringRefusal as e:
                rollup_note = str(e)[:200]
                if "headline" in rollup_note.lower():
                    rollup_note = ("the rollup has no headline — the scoring-critic lane "
                                   "records it (`engine.assessment rollup --headline '<one "
                                   "institution-specific line, 40+ chars>'`) after its verdicts")
                self.opts.log(f"  rollup refused: {rollup_note}")
            v = A.gate(self.wb, self.run.qa_dir)
            self.reopen()
            if v.get("gate") == "PASS":
                return f"SCORING gate PASS after {r + 1} round(s)"
            self.opts.log(f"  SCORING gate {v.get('gate')}: {', '.join((v.get('blocking') or [])[:6])}")
        v = A.gate(self.wb, self.run.qa_dir)
        raise StageRefused(f"SCORING gate {v.get('gate')} after {self.opts.max_rounds} round(s): "
                           + ", ".join((v.get("blocking") or [])[:8])
                           + (f"; {rollup_note}" if rollup_note else ""))

    def _ingest(self, label: str, *, after_seq: int | None) -> dict:
        """Poll list_pending_runs until the entity's newest run is newer than
        `after_seq`. Returns the row. Refuses on timeout — loudly."""
        md = self._md()
        ent_id = str(md.get("entity_id") or "").strip().lower()
        ent_name = str(md.get("entity_name") or "").strip().lower()
        deadline = self.opts.clock() + self.opts.ingest_timeout_s
        polls = 0
        while True:
            polls += 1
            rows = self.opts.reads.pending_runs()
            mine = [r for r in rows
                    if str(r.get("display_id") or "").strip().lower() == ent_id
                    or str(r.get("entity_name") or "").strip().lower() == ent_name]
            fresh = [r for r in mine
                     if after_seq is None or int(r.get("run_seq") or 0) > int(after_seq)]
            if fresh:
                fresh.sort(key=lambda r: int(r.get("run_seq") or 0))
                row = fresh[-1]
                self.state["connector"][label] = {"row": row, "polls": polls, "at": _utcnow()}
                self._save_state()
                return row
            if self.opts.clock() >= deadline:
                raise StageRefused(
                    f"{label}: the connector did not ingest a new version for "
                    f"{md.get('entity_name')} within {self.opts.ingest_timeout_s:.0f}s "
                    f"({polls} poll(s)); the package scan runs every 30 minutes — "
                    f"check the intake push, then run the pipeline again")
            self.opts.sleep(self.opts.ingest_poll_s)

    def _stage_ingest_a(self) -> str:
        from . import assemble
        self._reset_counters()
        ck = assemble.checkpoint(self.run, self.opts.folder_root, push=self.opts.push,
                                 stage_reached="SCORING_PASS")
        self.state["connector"]["checkpoint_a"] = {"folder": ck.get("folder"),
                                                   "pushed": ck.get("pushed"), "at": _utcnow()}
        self._save_state()
        row = self._ingest("ingest_a", after_seq=None)
        self._set_md("connector_run_id", row["run_id"])
        self._set_md("connector_ingest_after_seq", row.get("run_seq"))
        return f"version A ingested as {row['run_id']} (seq {row.get('run_seq')})"

    def _stage_reports(self) -> str:
        from . import brief, narrative as N, report_spec as RS, reports
        self._reset_counters()
        for r in range(self.opts.max_rounds):
            self._rounds = r + 1
            b = brief.report_batch(self.wb, run=self.run, out_dir=self._briefs(f"reports_r{r}"))
            self._count(self._dispatch(b, stage="REPORTS"))
            v = brief.report_batch(self.wb, run=self.run,
                                   out_dir=self._briefs(f"reports_validator_r{r}"), validator=True)
            self._count(self._dispatch(v, stage="REPORTS"))
            st = N.state(self.wb)
            if all(x.get("ready") for x in st["reports"].values()):
                break
            self.opts.log("  reports not READY: " + "; ".join(
                f"{k}: {len([s for s in x.get('sections') or [] if s.get('status') != 'READY'])} "
                f"section(s) open" for k, x in st["reports"].items() if not x.get("ready")))
        st = N.state(self.wb)
        not_ready = [k for k, x in st["reports"].items() if not x.get("ready")]
        if not_ready:
            raise StageRefused(f"reports not READY after {self.opts.max_rounds} round(s): "
                               f"{', '.join(not_ready)}; blocking: "
                               + "; ".join(str(b)[:120] for b in (st.get("blocking") or [])[:4]))
        # The Recommendations tab is PROJECTED from the assessment report's
        # REC cards (the pinned Doc's §8), never authored — an engine step,
        # so the driver runs it, not a lane.
        from . import grains
        grains.recommendations(self.wb)
        out = []
        for key, spec in RS.SPECS.items():
            res = reports.render(self.wb, spec, self.run.deliverables, qa_dir=self.run.qa_dir)
            out.append(Path(res["path"]).name)
        self.reopen()
        return "rendered: " + ", ".join(out)

    def _sections_dir(self) -> Path:
        d = self.run.root / SECTIONS_DIR
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _contract_file(self, page: str) -> Path:
        d = self._sections_dir() / "contracts"
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{page}.json"
        if not f.is_file():
            f.write_text(json.dumps(self.opts.reads.page_contract(page), indent=2, default=str))
        return f

    def _ship_pages(self, pages: tuple, version: str, *, produce: bool) -> list[str]:
        """Produce (lanes) and ship each page until it passes or the retries
        are spent. A FAIL re-dispatches ONLY that page, with the verdict's
        reasons in its brief."""
        from . import brief
        connector_run = str(self._md().get("connector_run_id") or "")
        if not connector_run:
            raise StageRefused("no connector run id — the checkpoint was never ingested")
        verdicts_file = self.run.qa_dir / f"verdicts_{version}.json"
        verdicts = {}
        if verdicts_file.is_file():
            try:
                verdicts = json.loads(verdicts_file.read_text())
            except ValueError:
                verdicts = {}
        todo = [p for p in pages if not self._page_ok(p, version)]
        shipped = []
        for attempt in range(self.opts.page_retries + 1):
            if not todo:
                break
            if produce:
                for p in todo:
                    self._contract_file(p)
                b = brief.page_batch(self.wb, run=self.run,
                                     out_dir=self._briefs(f"pages_{version}_{attempt}"),
                                     connector_run=connector_run,
                                     contract_file=self._sections_dir() / "contracts",   # a dir: <page>.json each
                                     verdicts_file=verdicts_file if verdicts else None,
                                     pages=list(todo))
                self._count(self._dispatch(b, stage=f"PAGES_{version}"))
            still = []
            for p in todo:
                res = self.opts.shipper.ship(connector_run, p, self._sections_dir(),
                                             self.run.qa_dir / f"verdict_{p}_{version}.json")
                rec = self.state["pages"].setdefault(p, {})
                rec.update({"version": version, "status": res.get("status"),
                            "reasons": (res.get("reasons") or [])[:12],
                            "attempts": int(rec.get("attempts") or 0) + 1,
                            "connector_run": connector_run, "at": _utcnow()})
                rec.setdefault("versions", {})[version] = res.get("status")
                if res.get("status") == "claim_refused":
                    self._save_state()
                    raise StageRefused(
                        f"claim on {connector_run} refused while shipping {p}: another "
                        f"session holds the lease; wait for it to lapse, then run again")
                if res.get("status") == "pass":
                    shipped.append(p)
                else:
                    still.append(p)
                    verdicts[p] = (res.get("reasons") or [])[:12]
            self._save_state()
            verdicts_file.write_text(json.dumps(verdicts, indent=2, default=str))
            todo = still
            if todo and not produce:
                break                     # a restage from disk is not retried by lanes
        if todo:
            raise StageRefused(
                f"page(s) not passing on version {version} after "
                f"{self.opts.page_retries + 1} attempt(s): "
                + "; ".join(f"{p}: {', '.join(str(x)[:100] for x in verdicts.get(p, [])[:2])}"
                            for p in todo))
        return shipped

    def _stage_pages_a(self) -> str:
        self._reset_counters()
        shipped = self._ship_pages(PAGES_A, "A", produce=True)
        return f"shipped to version A: {', '.join(shipped)}"

    def _stage_package(self) -> str:
        from . import assemble, grains, techscan
        self._reset_counters()
        if not [r for r in self.wb.rows("Recommendations") if any(r.values())]:
            grains.recommendations(self.wb)
        if not list(self.run.deliverables.glob("Technographic_Scan_*.docx")):
            techscan.render(self.wb, self.run.deliverables)
        pkg = assemble.package(self.run, self.opts.folder_root, push=self.opts.push)
        self.state["package"] = {"folder": pkg["folder"], "verified": pkg["verified"],
                                 "gold_findings": pkg["verification"].get("gold_findings"),
                                 "pushed": pkg.get("pushed"), "at": _utcnow()}
        self._save_state()
        if not pkg["verified"]:
            bad = [c for c in pkg["verification"]["checks"] if not c["ok"]]
            raise StageRefused("package did not verify: " + "; ".join(
                f"{c['check']}: {c['detail'][:120]}" for c in bad[:4]))
        self.reopen()
        return f"package verified at {pkg['folder']}" + (" and pushed" if self.opts.push else "")

    def _stage_ingest_b(self) -> str:
        self._reset_counters()
        md = self._md()
        prev = str(md.get("connector_run_id") or "")
        after = md.get("connector_ingest_after_seq")
        row = self._ingest("ingest_b", after_seq=int(after) if str(after or "").strip() else None)
        if str(row["run_id"]) == prev:
            raise StageRefused("the connector returned the same run as version A")
        self._set_md("connector_run_id_prev", prev)
        self._set_md("connector_run_id", row["run_id"])
        self._set_md("connector_ingest_after_seq", row.get("run_seq"))
        return f"version B ingested as {row['run_id']} (seq {row.get('run_seq')}; A was {prev})"

    def _stage_pages_b(self) -> str:
        self._reset_counters()
        restaged = self._ship_pages(PAGES_A, "B", produce=False)   # from disk, no lanes
        shipped = []
        for group in PAGES_B:
            shipped += self._ship_pages(group, "B", produce=True)
        return f"restaged {', '.join(restaged)}; shipped {', '.join(shipped)} to version B"

    def _stage_promote(self) -> str:
        self._reset_counters()
        connector_run = str(self._md().get("connector_run_id") or "")
        res = self.opts.shipper.promote(connector_run)
        if not res.get("promoted"):
            raise StageRefused(f"promote_run refused: {json.dumps(res)[:400]}")
        when = res.get("promoted_at") or _utcnow()
        self._set_md("promoted_at", when)
        self.state["connector"]["promoted"] = {"run_id": connector_run, "at": when,
                                               "stats": res.get("stats")}
        self._save_state()
        return f"promoted {connector_run} at {when}"


# ── env: every hard dependency, measured ─────────────────────────────────

def env_check() -> dict:
    checks = []

    def ck(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    for mod in ("openpyxl", "docx"):
        try:
            __import__(mod)
            ck(f"python:{mod}", True, "importable")
        except ImportError:
            ck(f"python:{mod}", False, f"pip install {'python-docx' if mod == 'docx' else mod}")
    ck("claude CLI", shutil.which("claude") is not None,
       "on PATH" if shutil.which("claude") else "not on PATH — lanes cannot be dispatched")
    for name, p in (("agent_run.py", AGENT_RUN), ("mcp_raw.py", MCP_RAW),
                    ("ship_page.py", SHIP_PAGE),
                    ("drive_fetch.py", PLUGIN / "scripts" / "drive_fetch.py")):
        ck(name, p.is_file(), str(p))
    ident = any([shutil.which("gcloud"), Path("/root/.dma/sa.json").is_file(),
                 os.environ.get("DMA_ROUTINE_SA_KEY_B64")])
    ck("connector identity", ident,
       "gcloud / /root/.dma/sa.json / DMA_ROUTINE_SA_KEY_B64" if ident else
       "no identity rung: connector reads and ship_page will fail")
    tk = os.environ.get("DMA_TOOLKITS_DIR")
    ck("toolkits", bool(tk and Path(tk).is_dir()),
       tk or "DMA_TOOLKITS_DIR unset — kg build falls back to the 71 category questions and says so")
    from . import template as T
    g = T.zip_guard()
    ck("templates vs manifest", g["ok"], g.get("fix") or f"{g['status']} ({g.get('installed')})")
    try:
        from . import cli as _cli
        stale = _cli.refuse_on_stale_install()
        ck("install", not stale, stale[:200] if stale else "not judged stale")
    except Exception as e:                           # noqa: BLE001
        ck("install", True, f"not judged: {str(e)[:100]}")
    hard = [c for c in checks if not c["ok"] and c["check"] not in ("toolkits",)]
    return {"ok": not hard, "checks": checks,
            "hard_failures": [c["check"] for c in hard]}


# ── command line ─────────────────────────────────────────────────────────

def _build_opts(a) -> Options:
    if a.dispatcher == "stub":
        from . import pipeline_stub as S
        disp, reads, shipper = S.StubDispatcher.fixture_backed(), S.StubReads(), S.StubShipper()
    else:
        disp, reads, shipper = AgentRunDispatcher(timeout=a.lane_timeout), McpReads(), ShipPageShipper()
    return Options(dispatcher=disp, reads=reads, shipper=shipper, until=a.until,
                   max_wall_min=a.max_wall_min, max_rounds=a.max_rounds,
                   lane_retries=a.lane_retries, page_retries=a.page_retries,
                   ingest_poll_s=(0 if a.dispatcher == "stub" else a.ingest_poll_s),
                   ingest_timeout_s=a.ingest_timeout_s,
                   folder_root=Path(a.folder_root) if a.folder_root else None,
                   push=(not a.no_push) and a.dispatcher != "stub",
                   allow_stale_install=a.allow_stale_install, lanes=a.lanes,
                   toolkit_dir=Path(a.toolkits) if a.toolkits else None)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="engine.pipeline", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--run", required=True)
        p.add_argument("--root")
        return p

    r = common(sub.add_parser("run", help="drive the run to PROMOTE, gate by gate"))
    r.add_argument("--dispatcher", choices=("agent_run", "stub"), default="agent_run")
    r.add_argument("--until", choices=STAGES, help="stop after this stage")
    r.add_argument("--max-wall-min", type=float)
    r.add_argument("--max-rounds", type=int, default=3)
    r.add_argument("--lane-retries", type=int, default=1)
    r.add_argument("--page-retries", type=int, default=2)
    r.add_argument("--lane-timeout", type=int, default=2400)
    r.add_argument("--lanes", type=int)
    r.add_argument("--ingest-poll-s", type=float, default=60.0)
    r.add_argument("--ingest-timeout-s", type=float, default=3600.0)
    r.add_argument("--folder-root")
    r.add_argument("--no-push", action="store_true")
    r.add_argument("--toolkits")
    r.add_argument("--allow-stale-install", action="store_true")
    r.add_argument("--json", action="store_true")
    common(sub.add_parser("plan", help="done / next / blockers — dispatches nothing"))
    st = common(sub.add_parser("status"))
    st.add_argument("--watch", action="store_true")
    st.add_argument("--interval", type=float, default=15.0)
    sub.add_parser("env", help="every hard dependency, measured")
    sub.add_parser("stages", help="the stage table")

    a = ap.parse_args(argv)
    if a.cmd == "stages":
        print(__doc__.split("THE STAGE TABLE")[1].split("Exactly TWO")[0])
        return 0
    if a.cmd == "env":
        out = env_check()
        print(json.dumps(out, indent=2))
        return 0 if out["ok"] else 1
    run = runstate.locate(a.run, Path(a.root) if a.root else None)
    if a.cmd == "plan":
        opts = Options(dispatcher=None, reads=None, shipper=None)  # type: ignore[arg-type]
        print(json.dumps(Pipeline(run, opts).plan(), indent=2, default=str))
        return 0
    if a.cmd == "status":
        while True:
            p = Pipeline(run, Options(dispatcher=None, reads=None, shipper=None))  # type: ignore[arg-type]
            plan = p.plan()
            print(f"{_utcnow()}  run {run.run_id}  next: {plan['next'] or 'COMPLETE'}")
            for s in plan["stages"]:
                rec = s.get("recorded") or {}
                print(f"  {'✓' if s['done'] else '·'} {s['stage']:<10} {s['detail'][:90]}"
                      + (f"  [{rec.get('elapsed_s')}s]" if rec.get("elapsed_s") else ""))
            if not a.watch or plan["complete"]:
                return 0
            time.sleep(a.interval)
    opts = _build_opts(a)
    out = Pipeline(run, opts).run_all()
    if a.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print(f"\n{out['outcome']}" + (f" at {out['stage']}" if out.get("stage") else "")
              + (f": {out['reason']}" if out.get("reason") else ""))
    # A clean stop (--until, --max-wall-min) is exit 0: the run is resumable
    # and nothing failed. FAILED / BLOCKED / REFUSED are exit 1.
    return 0 if out["outcome"] in ("COMPLETE", "STOPPED_AT_UNTIL",
                                   "STOPPED_WALL_CLOCK") else 1


if __name__ == "__main__":
    sys.exit(main())
