"""engine.pipeline — THE DRIVER. One command runs an assessment from a started
run to a promoted one, gate by gate, dispatching lanes over briefs and
shipping pages to the connector as the work becomes ready.

    python3 -m engine.pipeline run    --run <R> --root <ROOT> [--dispatcher agent_run|stub]
                                      [--until STAGE] [--max-wall-min N] [--max-rounds N]
                                      [--stall-rounds N] [--enrichment-heals N] [--no-relay]
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
    RESEARCH   every category's floors gate PASS                     lanes: 16 researchers → challengers → gates
               (+ verifier, + ENRICHMENT gate, + relay drain)         → relay → gates; rounds
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

ROUNDS ARE A CEILING, NOT A PROXY FOR PROGRESS (owner, 2026-09-07). The
driver refused a category after three rounds while categories were still
gaining ground each round — one hit 100% coverage in round two. `--max-rounds`
now defaults to 10 and every looping stage measures its own progress between
rounds (research: passing categories, evidence rows, searches, syntheses,
declared absences, connector searches; scoring: scored rows, critic passes,
gate terms; reports: READY sections; PRELIM: closed sections). A stage stops
EARLY only when `--stall-rounds` consecutive rounds advanced none of them —
so a big budget cannot spin on a stage that has stopped moving, and a stage
that is moving is not refused for being slow.

CONNECTOR USAGE IS MEASURED, HEALED, THEN DISCLOSED (MEM-0333). After each
research round the driver (1) harvests the `search_requests` every lane
emitted into `07_qa/search_relay.jsonl` (`engine.relay`), (2) dispatches
`enrichment-web-specialist` lanes to run them through the connectors they
hold and reconciles what came back against the Search_Log, and (3) records an
ENRICHMENT gate per category from the Search_Log's Tool column. A category
whose every search ran through bare web_search is re-dispatched as a FRESH
lane instance carrying the measured reason (grants refused / never attempted /
logged as web_search) — up to `--enrichment-heals` times — and after that the
same FAIL is written NON-blocking: disclosed in Gate_Log and the driver
state, never silently passed and never a wall the run cannot get past when
the harness bound no connector to a headless child.

Every stage records `STAGE_<NAME>` in Gate_Log with its verdict and wall
clock, appends to the cost ledger (`engine.cost record`), writes the driver
state to `07_qa/pipeline_state.json` and heartbeats the registry — so a run
that stops says where, and `run` again continues from the first stage whose
DONE predicate is false. Connector WRITES go only through `ship_page.py`;
connector READS go through `mcp_raw.py`; the driver never holds a payload.
"""
from __future__ import annotations

# Runnable both ways: -m engine.<module>, or by path for --help (audit_skills).
if __package__ in (None, ""):  # noqa: E402
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

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
        # Popen + communicate rather than subprocess.run, so that when THIS
        # process is interrupted (SIGINT, the SIGTERM handler in main, any
        # exception) the batch gets SIGTERM — which agent_run turns into a
        # kill of every lane's process group — instead of the SIGKILL
        # subprocess.run sends, which leaves sixteen `claude` children and
        # their grandchildren running with nobody to reap them (owner,
        # 2026-09-07: "50 processes still running, load still climbing").
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, cwd=str(PLUGIN.parents[1]))
        try:
            _out, err = proc.communicate()
        except BaseException:
            _terminate(proc)
            raise
        summary = {}
        if timing.is_file():
            try:
                summary = json.loads(timing.read_text())
            except ValueError:
                summary = {}
        summary.setdefault("rc", proc.returncode)
        summary.setdefault("stderr_tail", (err or "")[-600:])
        return summary


def _terminate(proc: "subprocess.Popen", grace_s: float = 30.0) -> None:
    """SIGTERM the batch and give it time to reap its lanes; SIGKILL after."""
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=grace_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    except ProcessLookupError:
        pass


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
                "sg_v4_fails": verdict.get("sg_v4_fails") or [],
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
    # A DOLLAR CEILING, enforced. `cost.BUDGET_PER_PILLAR` x pillars in scope
    # when left None. Measured 2026-09-12: the budget was computed, reported
    # and never enforced — `cost.record` raises only on a missing duration and
    # `cost report`'s verdict is a shell exit code no automated path reads
    # ("reported over budget WITH the figure, and still runs",
    # docs/ROUTINES.md). One research round at the lanes' own 200-turn ceiling
    # is ~$83 against a $20 four-pillar budget, and ten rounds are allowed.
    # Set 0 to disable the ceiling and keep the old reporting-only behaviour.
    max_usd: float | None = None
    # A CEILING on rounds per looping stage. 3 refused categories that were
    # still gaining ground each round (owner, 2026-09-07); 10 is what the
    # owner resumed those runs with. `stall_rounds` is what keeps a large
    # ceiling honest: consecutive rounds that advance nothing end the stage.
    max_rounds: int = 10
    stall_rounds: int = 2
    # How many FRESH lane instances the driver spends on a category whose
    # searches all ran through bare web_search before it discloses the gap
    # instead of working it again (the ENRICHMENT gate). 0 = disclose only.
    enrichment_heals: int = 1
    # Dispatch `enrichment-web-specialist` lanes over the harvested
    # `search_requests` each round. Off = harvest and disclose, never drain.
    relay: bool = True
    lane_retries: int = 1
    page_retries: int = 2
    # SG-V4 (embedding grounding) disclosures the connector promotes anyway
    # (invariant 12); the driver REVISES a page whose FAIL count exceeds this,
    # so ungrounded prose is re-grounded rather than shipped. A small budget
    # tolerates a legitimate paraphrase drifting below threshold; 249 (Golden 1)
    # does not.
    sg_v4_budget: int = 8
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
                        wb=self.wb, **self._spend_kw(cost))
        except Exception as e:                       # noqa: BLE001
            # A swallowed cost failure is how a run spends $96 against a $20
            # budget and leaves a ledger that says nothing. Still non-fatal —
            # accounting must not kill a good stage — but it is now LOUD and
            # it is recorded in the run state.
            self.opts.log(f"  (COST NOT RECORDED — the ledger is now incomplete: "
                          f"{e.__class__.__name__}: {str(e)[:160]})")
            self.state.setdefault("cost_errors", []).append(
                {"stage": stage, "error": f"{e.__class__.__name__}: {str(e)[:200]}"})
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

    def _spend_kw(self, cost) -> dict:
        """The spend to attribute to the stage that just ended — the DELTA
        since the last record, not the run total, so the ledger's rows sum to
        the run instead of each restating it. Silent when the dispatcher
        reported no cost (the stub, or a lane whose status file carried none):
        `cost.record` then falls back to its own estimate, and a zero we made
        up would be worse than an absence."""
        kw = {}
        usd = round(self._spent_usd - self._recorded_usd, 4)
        turns = self._spent_turns - self._recorded_turns
        if usd > 0:
            kw["usd"] = usd
            self._recorded_usd = self._spent_usd
        if turns > 0:
            kw["turns"] = turns
            self._recorded_turns = self._spent_turns
        return kw

    def budget_usd(self) -> float | None:
        """The run's dollar ceiling. `None` disables it."""
        if self.opts.max_usd is not None:
            return None if self.opts.max_usd <= 0 else float(self.opts.max_usd)
        try:
            from . import cost
            pillars = {c[:2] for c in self.wb.selected_subcaps()}
            return cost.BUDGET_PER_PILLAR * max(1, len(pillars))
        except Exception:                            # noqa: BLE001
            return None

    def _over_budget(self) -> bool:
        cap = self.budget_usd()
        return cap is not None and self._spent_usd >= cap

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
            sha = str(md.get("preflight_sha") or "").strip()
            ok = bool(sha) or (bool(sv) and not sv.upper().startswith("UNSTATED"))
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
            if self._over_budget():
                outcome.update(outcome="STOPPED_BUDGET", stage=st,
                               reason=f"spent ${self._spent_usd:.2f} of a "
                                      f"${self.budget_usd():.2f} budget before {st}; "
                                      f"resume: {self.plan()['command']}")
                self.opts.log(f"[{st}] STOPPED — budget ${self._spent_usd:.2f} "
                              f"of ${self.budget_usd():.2f}")
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
                # A stage the BUDGET stopped has not failed its gate — it
                # never got to finish trying. Reporting "still failing the
                # floors gate" there sends the reader to repair research that
                # was simply cut short, which is the wrong repair.
                if self._budget_stopped:
                    msg = (f"stopped by the ${self.budget_usd():.2f} budget after "
                           f"spending ${self._spent_usd:.2f} — the stage was cut "
                           f"short, not refused. Raise --max-usd or narrow scope, "
                           f"then resume; what it had reached when it stopped: {msg}")
                    self._record(st, "FAIL", msg[:600], t0, rounds=self._rounds,
                                 lanes=self._lane_count, attempts=self._attempts)
                    outcome.update(outcome="STOPPED_BUDGET", stage=st, reason=msg[:800],
                                   resume=self.plan()["command"])
                    return outcome
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
    _last_sig: tuple | None = None
    _stalls = 0
    _stalled_at: int | None = None
    #: per-category stall bookkeeping for RESEARCH (see `_research_stalled`)
    _cat_sig: dict = {}
    _cat_stalls: dict = {}
    _cat_stalled: list = []

    #: run-scoped spend — deliberately NOT cleared by `_reset_counters`,
    #: because a ceiling that forgets the previous stage is not a ceiling.
    _spent_usd = 0.0
    _spent_turns = 0
    _recorded_usd = 0.0
    _recorded_turns = 0
    _budget_stopped = False

    def _reset_counters(self):
        self._rounds = self._lane_count = self._attempts = 0
        self._last_sig, self._stalls, self._stalled_at = None, 0, None
        self._cat_sig, self._cat_stalls, self._cat_stalled = {}, {}, []

    # ── progress between rounds ────────────────────────────────────────
    #
    # Each looping stage has a signature: a tuple of counts that can only
    # go up as the stage advances. A round that raises none of them advanced
    # nothing, whatever the lanes reported. The signature is read from the
    # WORKBOOK the lanes write, so it measures the substrate, not the prose.

    def _research_progress(self) -> dict[str, tuple]:
        """Per-category OUTCOME counters for the RESEARCH stage.

        THIS DELIBERATELY EXCLUDES THE RAW `Search_Log` ROW COUNT, and the
        reason is the whole bug. Measured 2026-09-12 against the real
        driver: `len(searches)` sat in the run-level signature and
        `_stalled` clears on `any(c > p ...)`, so ONE extra `web_search`
        row anywhere reset the stall counter for all sixteen categories.
        A lane that logs searches and resolves nothing is the cheapest
        thing a stuck lane does — so the counter meant to STOP the loop was
        the one a stuck loop was guaranteed to raise. Replaying the failing
        run's shape: nine rounds, `stalls=0` every round, never stopped.
        With the row count removed it stops at round 2.

        Two changes, both load-bearing:
          * only OUTCOMES count — a cell closed, a synthesis written, an
            absence declared, a connector actually asked. A search is
            activity, not progress.
          * the counters are PER CATEGORY, so one moving category can no
            longer vouch for fifteen stuck ones.
        """
        from . import brief
        from .workbook import _split_ids
        wb = self.wb
        register = wb.evidence_index()
        declared = L.declared_absences(wb)
        passed = set(brief.categories_needing_dispatch(wb)["passed"])
        acc: dict[str, list] = {}

        def slot(cat: str) -> list:
            return acc.setdefault(cat, [0, 0, 0, 0, 0])

        for r in wb.scoring_rows():
            cell = str(r.get("SubCap_ID") or "").strip()
            if not cell:
                continue
            s = slot(cell.split(".")[0])
            eids = [i.split(":")[0] for i in _split_ids(r.get("Evidence_IDs"))
                    if i and i != C.NO_EVIDENCE]
            if any(e in register for e in eids):
                s[0] += 1                                    # evidenced cells
            if str(r.get("Dominant_Claim") or "").strip():
                s[1] += 1                                    # syntheses
            if cell in declared:
                s[2] += 1                                    # declared absences
        for sr in wb.rows("Search_Log"):
            if str(sr.get("Tool") or "").strip().lower() in C.ENRICHMENT_TOOLS:
                cell = str(sr.get("SubCap_ID") or "").strip()
                if cell:
                    slot(cell.split(".")[0])[3] += 1          # connector asked
        for cat in passed:
            slot(cat)[4] = 1                                  # category closed
        return {c: tuple(v) for c, v in acc.items()}

    def _research_stalled(self, categories: list[str]) -> list[str]:
        """The categories whose OWN outcomes have not moved for
        `stall_rounds` consecutive rounds. Those stop being dispatched; the
        rest carry on. Before this, a stall was an all-or-nothing property
        of the whole stage, so fifteen stuck categories rode along on the
        one that was still moving."""
        if not self.opts.stall_rounds:
            return []
        now = self._research_progress()
        stalled = []
        for cat in categories:
            sig, prev = now.get(cat, ()), self._cat_sig.get(cat)
            if prev is not None and not any(c > p for c, p in zip(sig, prev)):
                self._cat_stalls[cat] = self._cat_stalls.get(cat, 0) + 1
            else:
                self._cat_stalls[cat] = 0
            self._cat_sig[cat] = sig
            if self._cat_stalls.get(cat, 0) >= self.opts.stall_rounds:
                stalled.append(cat)
        return stalled

    def _progress(self, stage: str) -> tuple:
        wb = self.wb
        if stage == "PRELIM":
            from . import prelim
            st = prelim.state(wb)
            return (sum(1 for sec in st.get("sections") or [] if sec.get("status") != "OPEN"),)
        if stage == "RESEARCH":
            # The run-level view is the SUM of the per-category outcome
            # counters, so it stays comparable for the record — but the
            # decision to keep dispatching is made per category, by
            # `_research_stalled`. See `_research_progress` for why the raw
            # Search_Log row count is no longer in here.
            by = self._research_progress()
            return tuple(sum(v[i] for v in by.values()) for i in range(5)) if by else (0,) * 5
        if stage == "SCORING":
            from . import assessment as A
            st = A.state(wb)
            last = st.get("last_scoring_gate") or {}
            blocking = last.get("blocking") or []
            return (sum(1 for r in wb.scoring_rows()
                        if str(r.get("SubCap_ID") or "") in set(wb.selected_subcaps())
                        and r.get("Score") not in (None, "")),
                    sum(1 for v in (st.get("critic_verdicts") or {}).values() if v == "PASS"),
                    -len(blocking) if last else -(10 ** 6))
        if stage == "REPORTS":
            from . import narrative as N
            st = N.state(wb)
            return (sum(1 for x in st["reports"].values()
                        for sec in (x.get("sections") or []) if sec.get("status") == "READY"),
                    sum(1 for x in st["reports"].values() if x.get("ready")))
        return ()

    def _stalled(self, stage: str) -> bool:
        """Record this round's signature; True when `stall_rounds` consecutive
        rounds advanced nothing. The first call seeds and never stalls."""
        sig = self._progress(stage)
        prev, self._last_sig = self._last_sig, sig
        if prev is None:
            self._stalls = 0
            return False
        if any(c > p for c, p in zip(sig, prev)):
            self._stalls = 0
            return False
        self._stalls += 1
        if self.opts.stall_rounds and self._stalls >= self.opts.stall_rounds:
            self._stalled_at = self._rounds
            self.opts.log(f"  [{stage}] no progress for {self._stalls} consecutive round(s) "
                          f"— stopping at round {self._rounds} of {self.opts.max_rounds}")
            return True
        return False

    def _stall_note(self) -> str:
        if self._stalled_at is None:
            return ""
        return (f" — stopped at round {self._stalled_at}: the last {self._stalls} round(s) "
                f"advanced nothing the stage measures, so more rounds would not have helped")

    def _count(self, summary: dict):
        self._lane_count += int(summary.get("dispatched") or 0)
        self._attempts += sum(int(l.get("attempts") or 1)
                              for l in (summary.get("lanes_detail") or []))
        # REAL SPEND, not an estimate. `agent_run.py` already sums each lane's
        # `total_cost_usd` into the batch summary; this used to read
        # `dispatched` and `attempts` out of that dict and drop the one figure
        # that could stop a runaway run.
        usd = summary.get("usd")
        if usd is not None:
            self._spent_usd += float(usd)
        turns = summary.get("turns")
        if turns is not None:
            self._spent_turns += int(turns)

    # ── STAGES ─────────────────────────────────────────────────────────
    def _stage_prelim(self) -> str:
        from . import brief, prelim
        self._reset_counters()
        self._stalled("PRELIM")
        for r in range(self.opts.max_rounds):
            self._rounds = r + 1
            b = brief.prelim_brief(self.wb, run=self.run, out_dir=self._briefs(f"prelim_r{r}"))
            self._count(self._dispatch(b, stage="PRELIM"))
            st = prelim.state(self.wb)
            if not st["open"]:
                if st["recorded_status"] != "COMPLETE":
                    prelim.complete(self.wb)
                return f"PRELIM closed after {r + 1} round(s)"
            if self._stalled("PRELIM"):
                break
        raise StageRefused(f"PRELIM still open after {self._rounds} round(s): "
                           f"{', '.join(prelim.state(self.wb)['open'])}{self._stall_note()}")

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
        self._stalled("RESEARCH")                        # seed the signature
        for r in range(self.opts.max_rounds):
            need = brief.categories_needing_dispatch(self.wb)
            if not need["dispatch"]:
                return self._research_summary(r)
            # A category whose own outcomes have not moved for `stall_rounds`
            # rounds stops being dispatched. The rest carry on — a stall is a
            # property of a category, not of the stage (see
            # `_research_stalled`).
            work = [c for c in need["dispatch"] if c not in self._cat_stalled]
            if not work:
                self._stalled_at = self._rounds
                self.opts.log(f"  [RESEARCH] every open category has stalled "
                              f"({', '.join(sorted(self._cat_stalled))}) — stopping at "
                              f"round {self._rounds} of {self.opts.max_rounds}")
                break
            self._rounds = r + 1               # a round is counted when it dispatches
            b = brief.batch(self.wb, run=self.run, out_dir=self._briefs(f"research_r{r}"),
                            only=work, with_handback=(r > 0))
            self._count(self._dispatch(b, stage="RESEARCH"))
            cb = brief.challenge_batch(self.wb, run=self.run,
                                       out_dir=self._briefs(f"challenge_r{r}"))
            if cb.get("lanes"):
                self._count(self._dispatch(cb, stage="CHALLENGE"))
            for cat in work:
                floors_gate.run(self.wb, cat, require_synthesis=True, qa_dir=self.run.qa_dir)
            self._verify_research(work)
            self._enrich_research(work, r)
            self.reopen()
            newly = self._research_stalled(work)
            for cat in newly:
                if cat not in self._cat_stalled:
                    self._cat_stalled.append(cat)
                    self.opts.log(f"  [RESEARCH] {cat}: no outcome moved for "
                                  f"{self.opts.stall_rounds} round(s) — not dispatching it "
                                  f"again; more rounds would not have helped")
            if self._over_budget():
                # A between-stages-only ceiling cannot stop the stage that
                # spends the money: ten rounds x 16 lanes all happen inside
                # ONE stage. This is the check that actually bites.
                self.opts.log(f"  [RESEARCH] budget ${self._spent_usd:.2f} of "
                              f"${self.budget_usd():.2f} — stopping at round {self._rounds}")
                self._budget_stopped = True
                break
            if self._stalled("RESEARCH"):
                break
        need = brief.categories_needing_dispatch(self.wb)
        if need["dispatch"]:
            # A category held back by the ENRICHMENT gate ALONE is disclosed,
            # not refused: the budget is spent, the floors gate passed it,
            # and a stage that cannot end while the harness binds no connector
            # to a headless child is a wall, not a gate.
            only_enrichment = brief.enrichment_failing_only(self.wb, need["dispatch"])
            if only_enrichment:
                self._disclose_enrichment(only_enrichment, why="round budget spent")
                self.reopen()
                need = brief.categories_needing_dispatch(self.wb)
        if need["dispatch"]:
            raise StageRefused(
                f"{len(need['dispatch'])} category(ies) still failing the floors gate after "
                f"{self._rounds} round(s): "
                + "; ".join(f"{c}: {', '.join(need['reasons'][c][:4])}"
                            for c in need["dispatch"][:4])
                + self._stall_note())
        return self._research_summary(self._rounds)

    def _research_summary(self, rounds: int) -> str:
        """The stage detail names every category whose connector gap was
        disclosed rather than closed — on both exits, so the record never
        reads as a clean pass when it was not one."""
        disclosed = sorted((self.state.get("enrichment_disclosed") or {}).keys())
        return (f"every category PASS after {rounds} round(s)"
                + (f"; ENRICHMENT disclosed (no connector search) for {', '.join(disclosed)}"
                   if disclosed else ""))

    def _enrich_research(self, categories, round_no: int) -> None:
        """The connector half of a research round (MEM-0333; owner 2026-09-07).

        1. HARVEST the `search_requests` this round's lanes emitted into the
           relay queue — a lane that could not run a connector said so; the
           saying must land somewhere.
        2. DRAIN: one `enrichment-web-specialist` lane per category with open
           requests, dispatched with the exact commands that turn a connector
           result into Search_Log and Evidence rows; then RECONCILE the queue
           against the Search_Log the lanes wrote.
        3. GATE: per category, an ENRICHMENT row from the Search_Log's Tool
           column. Zero connector searches → FAIL, BLOCKING while the heal
           budget lasts (the category re-enters the round loop as a FRESH lane
           instance carrying the measured reason — grants / instruction /
           logging / manifest — and the open requests), then FAIL
           NON-BLOCKING: disclosed, recorded, and no longer a re-dispatch.

        FAIL-SAFE BY CONSTRUCTION, like the verifier: an error in the relay
        leaves the category exactly as the floors gate found it, logged."""
        try:
            from . import relay
        except Exception as e:                                  # noqa: BLE001
            self.opts.log(f"[ENRICH] skipped: relay unavailable ({e.__class__.__name__})")
            return
        logs = self.run.root / "agent_logs"
        try:
            h = relay.harvest(self.run, list(categories), logs_dir=logs, round_no=round_no)
            if h["harvested"]:
                self.opts.log(f"[RELAY] harvested {h['harvested']} search request(s): "
                              f"{h['by_category']}")
        except Exception as e:                                  # noqa: BLE001
            self.opts.log(f"[RELAY] harvest skipped ({e.__class__.__name__}: {str(e)[:120]})")
        if self.opts.relay:
            try:
                d = relay.drain_batch(self.run, self.wb, out_dir=self._briefs(f"relay_r{round_no}"),
                                      categories=list(categories))
                if d.get("lanes"):
                    self.opts.log(f"[RELAY] draining {d['requests']} request(s) over "
                                  f"{d['lanes']} specialist lane(s)")
                    self._count(self._dispatch(d, stage="RELAY"))
                    rc = relay.reconcile(self.run, self.wb)
                    self.opts.log(f"[RELAY] reconciled: {rc['closed']}; "
                                  f"still open {rc['still_open']}")
            except Exception as e:                              # noqa: BLE001
                self.opts.log(f"[RELAY] drain skipped ({e.__class__.__name__}: {str(e)[:120]})")
        heals = self.state.setdefault("enrichment_heals", {})
        for cat in categories:
            try:
                plan = relay.heal_plan(self.run, self.wb, cat, logs_dir=logs)
            except Exception as e:                              # noqa: BLE001
                self.opts.log(f"[ENRICH] {cat}: skipped ({e.__class__.__name__})")
                continue
            st = plan["status"]
            try:
                if st["searches"] == 0:
                    L.append_gate(self.wb, gate="ENRICHMENT", scope=cat, verdict="NOT_RUN",
                                  detail=plan["reason"], blocking=False)
                    continue
                if st["enrichment_searches"] > 0:
                    L.append_gate(self.wb, gate="ENRICHMENT", scope=cat, verdict="PASS",
                                  detail=plan["reason"], blocking=False)
                    heals.pop(cat, None)
                    (self.state.get("enrichment_disclosed") or {}).pop(cat, None)
                    continue
                used = int(heals.get(cat) or 0)
                terms = [f"no enrichment connector was asked: {st['searches']} search(es) all "
                         f"through {', '.join(st['tools']) or 'nothing'}",
                         f"heal={plan['heal']}: {plan['reason']}",
                         f"open relay requests {plan['open_requests']}"]
                if used < self.opts.enrichment_heals:
                    heals[cat] = used + 1
                    terms.append(f"fresh lane instance {used + 1} of {self.opts.enrichment_heals}")
                    L.append_gate(self.wb, gate="ENRICHMENT", scope=cat, verdict="FAIL",
                                  detail="; ".join(terms), blocking=True)
                    self.opts.log(f"[ENRICH] {cat}: REVISE — {terms[0][:100]}; heal={plan['heal']}")
                else:
                    self._disclose_enrichment([cat], why=f"heal budget spent ({used})",
                                              plans={cat: plan})
            except Exception as e:                              # noqa: BLE001
                self.opts.log(f"[ENRICH] {cat}: gate write skipped ({e.__class__.__name__})")
        self._save_state()

    def _disclose_enrichment(self, categories, *, why: str, plans: dict | None = None) -> None:
        """Write the ENRICHMENT FAIL for these categories NON-blocking and
        record it in the driver state — a stated gap, never a silent pass."""
        from . import relay
        disclosed = self.state.setdefault("enrichment_disclosed", {})
        for cat in categories:
            plan = (plans or {}).get(cat)
            if plan is None:
                try:
                    plan = relay.heal_plan(self.run, self.wb, cat,
                                           logs_dir=self.run.root / "agent_logs")
                except Exception as e:                          # noqa: BLE001
                    plan = {"heal": "unmeasured", "reason": f"{e.__class__.__name__}",
                            "status": {"searches": None, "tools": []}, "open_requests": None}
            st = plan["status"]
            detail = "; ".join([
                f"DISCLOSED ({why}): no enrichment connector was asked for {cat}",
                f"{st.get('searches')} search(es) all through {', '.join(st.get('tools') or []) or 'nothing'}",
                f"heal={plan['heal']}: {plan['reason']}",
                f"open relay requests {plan.get('open_requests')}"])
            try:
                L.append_gate(self.wb, gate="ENRICHMENT", scope=cat, verdict="FAIL",
                              detail=detail[:900], blocking=False)
            except Exception as e:                              # noqa: BLE001
                self.opts.log(f"[ENRICH] {cat}: disclosure not written ({e.__class__.__name__})")
            disclosed[cat] = {"at": _utcnow(), "why": why, "heal": plan["heal"],
                              "reason": str(plan["reason"])[:300],
                              "searches": st.get("searches"), "tools": st.get("tools"),
                              "open_requests": plan.get("open_requests")}
            self.opts.log(f"[ENRICH] {cat}: DISCLOSED — {detail[:140]}")
        self._save_state()

    def _verify_research(self, categories) -> None:
        """The dispatch verifier for RESEARCH. After the floors gate reads the
        Search_Log a lane wrote, this reads the lane's own transcript and
        REVISEs a category whose logged searches no retrieval could have
        produced — the fabrication the substrate gates structurally cannot
        see. It records a DISPATCH_VERIFY row per category; a FAIL re-enters
        the round loop through categories_needing_dispatch, with the reason in
        the re-dispatch brief. FAIL-SAFE BY CONSTRUCTION: any error leaves the
        category exactly as the floors gate found it, because a verifier that
        cannot read the work must never block a run on a guess."""
        try:
            from . import verify
        except Exception:                                   # noqa: BLE001
            return
        logs = self.run.root / "agent_logs"
        for cat in categories:
            try:
                reasons = verify.research_lane_fabrication(cat, logs)
            except Exception as e:                          # noqa: BLE001
                self.opts.log(f"[VERIFY] {cat}: skipped ({e.__class__.__name__})")
                continue
            try:
                if reasons:
                    L.append_gate(self.wb, gate="DISPATCH_VERIFY", scope=cat,
                                  verdict="FAIL", detail="; ".join(sorted(reasons)),
                                  blocking=True)
                    self.opts.log(f"[VERIFY] {cat}: REVISE — {reasons[0][:120]}")
                else:
                    L.append_gate(self.wb, gate="DISPATCH_VERIFY", scope=cat,
                                  verdict="PASS",
                                  detail="logged searches witnessed by retrieval "
                                         "in the lane transcript", blocking=False)
            except Exception as e:                          # noqa: BLE001
                self.opts.log(f"[VERIFY] {cat}: gate write skipped ({e.__class__.__name__})")

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
        self._stalled("SCORING")
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
            if self._stalled("SCORING"):
                break
        v = A.gate(self.wb, self.run.qa_dir)
        raise StageRefused(f"SCORING gate {v.get('gate')} after {self._rounds} round(s): "
                           + ", ".join((v.get("blocking") or [])[:8])
                           + (f"; {rollup_note}" if rollup_note else "")
                           + self._stall_note())

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
        self._stalled("REPORTS")
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
            if self._stalled("REPORTS"):
                break
        st = N.state(self.wb)
        not_ready = [k for k, x in st["reports"].items() if not x.get("ready")]
        if not_ready:
            raise StageRefused(f"reports not READY after {self._rounds} round(s): "
                               f"{', '.join(not_ready)}; blocking: "
                               + "; ".join(str(b)[:120] for b in (st.get("blocking") or [])[:4])
                               + self._stall_note())
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
                sgv4 = res.get("sg_v4_fails") or []
                if res.get("status") == "pass" and len(sgv4) > self.opts.sg_v4_budget:
                    # The connector discloses-and-promotes SG-V4 (invariant 12);
                    # the driver reads the disclosure and REVISES ungrounded prose
                    # before accepting the page, rather than shipping the claim the
                    # grounding gate could not support (measured on the promoted
                    # Golden 1 overview: 249 SG-V4 FAILs, all ignored).
                    res = {**res, "status": "sg_v4_over_budget",
                           "reasons": [f"SG-V4 grounding FAIL x{len(sgv4)} over "
                                       f"budget {self.opts.sg_v4_budget} — find "
                                       f"grounding or drop the claim"]
                           + [f"{w.get('path')} (sim {w.get('similarity')} < "
                              f"{w.get('threshold')})" for w in sgv4[:6]]}
                rec = self.state["pages"].setdefault(p, {})
                rec.update({"version": version, "status": res.get("status"),
                            "reasons": (res.get("reasons") or [])[:12],
                            "sg_v4_fails": len(sgv4),
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

def _readable(path: Path) -> bool:
    """`Path.is_file()` swallows ENOENT and RE-RAISES everything else — EACCES
    included. Measured 2026-09-04: on a CI runner `/root/.dma/sa.json` is
    unreadable rather than absent, and `env` raised PermissionError instead of
    reporting a missing identity rung. An environment check that crashes on the
    environment it is checking has answered nothing."""
    try:
        return Path(path).is_file()
    except OSError:
        return False


def _is_dir(path) -> bool:
    try:
        return Path(path).is_dir()
    except OSError:
        return False


def _connector_row() -> tuple:
    """(name, ok, detail) for the enrichment-connector baseline."""
    name = "enrichment connectors"
    fix = ("run `python3 $CLAUDE_PLUGIN_ROOT/scripts/connector_contract.py "
           "baseline --tools -` from the session that holds the tools, before "
           "dispatching anything")
    try:
        sys.path.insert(0, str(PLUGIN / "scripts"))
        import connector_contract as cc                       # noqa: PLC0415
        path = cc.baseline_path(os.environ.get("DMA_RUN_ROOT"))
        if not _readable(path):
            return (name, False,
                    f"no connector baseline at {path} — UNVERIFIED, not a pass. {fix}")
        rec = json.loads(Path(path).read_text())
        out = cc.check(rec.get("mcp_tools") or [])
        if out["ok"]:
            return (name, True, f"present: {', '.join(out['present']) or 'none'}")
        return (name, False,
                f"STOP — missing {', '.join(out['missing'])}. Without one of these "
                f"NO cell can be declared absent, so no floors gate can pass and "
                f"the run will re-dispatch until its ceiling. {out['why'][:200]}")
    except Exception as e:                                    # noqa: BLE001
        return (name, False, f"could not be judged: {e.__class__.__name__}: "
                             f"{str(e)[:160]} — UNVERIFIED, not a pass. {fix}")


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
       "on PATH" if shutil.which("claude") else
       "not on PATH: real lanes cannot be dispatched (--dispatcher stub can)")
    for name, p in (("agent_run.py", AGENT_RUN), ("mcp_raw.py", MCP_RAW),
                    ("ship_page.py", SHIP_PAGE),
                    ("drive_fetch.py", PLUGIN / "scripts" / "drive_fetch.py")):
        ck(name, _readable(p), str(p))
    ident = any([shutil.which("gcloud"), _readable(Path("/root/.dma/sa.json")),
                 os.environ.get("DMA_ROUTINE_SA_KEY_B64")])
    ck("connector identity", ident,
       "gcloud / /root/.dma/sa.json / DMA_ROUTINE_SA_KEY_B64" if ident else
       "no identity rung readable here: the connector stages (INGEST_A, "
       "PAGES_*, PROMOTE) will fail; PRELIM..PACKAGE and --dispatcher stub "
       "do not need one")
    # THE ROW THAT WAS NOT HERE. Measured 2026-09-12: a run started with no
    # enrichment connector bound at all. Nothing could then be declared absent
    # (`declare_absence` requires one of C.ENRICHMENT_TOOLS), so no floors gate
    # could pass, so the driver re-dispatched sixteen categories ~18 times for
    # $96.65 and closed nothing. `connector_contract.py` already declares the
    # required set with verdict STOP, is tested, and is wired into the Routine
    # prompts — and was called from nowhere on the `/run-assessment` path: not
    # here, not by the command, not by the conductor.
    #
    # A session's bound MCP tools live in the model's context and no subprocess
    # can enumerate them (MEM-0112), so this reads the BASELINE the command
    # layer writes with `connector_contract.py baseline --tools -`. An absent
    # baseline is reported as UNVERIFIED, never as a pass: "no enrichment
    # connector" and "nobody looked" must not wear the same face.
    ck(*_connector_row())
    tk = os.environ.get("DMA_TOOLKITS_DIR")
    ck("toolkits", bool(tk and _is_dir(tk)),
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
    # A hard failure is one that stops a run HERE. `toolkits` is a stated
    # fallback, and an identity rung is only needed for the connector stages —
    # a checkout with neither still plans, tests and drives the stub.
    # `enrichment connectors` is deliberately NOT in the exempt list: a run
    # without one cannot close a single empty cell, so letting it start is
    # letting it burn. `toolkits` is a stated fallback and an identity rung is
    # only needed for the connector stages.
    hard = [c for c in checks if not c["ok"]
            and c["check"] not in ("toolkits", "connector identity", "claude CLI")]
    return {"ok": not hard, "checks": checks,
            "hard_failures": [c["check"] for c in hard]}


# ── command line ─────────────────────────────────────────────────────────

def _install_terminate_handler() -> None:
    """SIGTERM becomes an exception, so the dispatcher can hand the running
    batch SIGTERM (and it its lanes) before this process exits; the default
    action would end the driver with the lanes still running."""
    import signal

    def _on_term(signum, _frame):
        raise SystemExit(f"terminated by signal {signum}: the running batch was told to stop "
                         f"its lanes; resume with `engine.pipeline run`")
    try:
        signal.signal(signal.SIGTERM, _on_term)
    except (ValueError, OSError):          # not the main thread, or no signals here
        pass


def _build_opts(a) -> Options:
    if a.dispatcher == "stub":
        from . import pipeline_stub as S
        disp, reads, shipper = S.StubDispatcher.fixture_backed(), S.StubReads(), S.StubShipper()
    else:
        disp, reads, shipper = AgentRunDispatcher(timeout=a.lane_timeout), McpReads(), ShipPageShipper()
    return Options(dispatcher=disp, reads=reads, shipper=shipper, until=a.until,
                   max_wall_min=a.max_wall_min, max_usd=getattr(a, 'max_usd', None),
                   max_rounds=a.max_rounds,
                   stall_rounds=a.stall_rounds, enrichment_heals=a.enrichment_heals,
                   relay=not a.no_relay,
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
    r.add_argument("--max-usd", type=float, default=Options.max_usd,
                   help="dollar ceiling for the run; default is "
                        "cost.BUDGET_PER_PILLAR x pillars in scope. "
                        "0 disables it (report-only, the old behaviour).")
    r.add_argument("--max-rounds", type=int, default=Options.max_rounds,
                   help=f"ceiling on rounds per looping stage (default {Options.max_rounds}); "
                        f"a stage stops early only when --stall-rounds rounds advance nothing")
    r.add_argument("--stall-rounds", type=int, default=Options.stall_rounds,
                   help=f"consecutive rounds with no measured progress that end a stage "
                        f"(default {Options.stall_rounds}; 0 disables)")
    r.add_argument("--enrichment-heals", type=int, default=Options.enrichment_heals,
                   help=f"fresh lane instances spent on a category with no connector search "
                        f"before the gap is disclosed instead (default {Options.enrichment_heals})")
    r.add_argument("--no-relay", action="store_true",
                   help="harvest search_requests but do not dispatch specialist lanes over them")
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
    _install_terminate_handler()
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
