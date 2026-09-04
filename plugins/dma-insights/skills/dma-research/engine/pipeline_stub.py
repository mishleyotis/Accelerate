"""Test doubles for `engine.pipeline` — a driver you can run end to end in a
container with no model, no connector and no Drive.

    python3 -m engine.pipeline run --run <R> --root <ROOT> --dispatcher stub

THREE SEAMS, THREE DOUBLES. The pipeline talks to the world through exactly
three protocols (`Dispatcher`, `ConnectorReads`, `Shipper`); each has a
real implementation and this one. The doubles are honest about what they
are: lanes are played by the test fixtures (the same synthetic evidence,
syntheses, scores and sections every engine test uses) through the ENGINE's
own refusals — so a stub run still meets every gate a real run meets; the
connector "ingests" a version each time it is asked; the shipper "passes"
every page unless a test scripts a verdict. What the stub proves is the
DRIVER: stage order, done-predicates, gate refusals, re-dispatch on FAIL,
retries, timings, resume, idempotence. What it cannot prove is the content,
and it says so.

The fixture module lives in the repository (`tests/skills/research_engine/
fixtures.py`), not in the plugin: a stub run needs the checkout.
"""
from __future__ import annotations

# Runnable both ways: -m engine.<module>, or by path for --help (audit_skills).
if __package__ in (None, ""):  # noqa: E402
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import importlib.util
import json
import sys
import time
from pathlib import Path

from . import contract as C
from . import ledger as L

PLUGIN = Path(__file__).resolve().parents[3]
REPO = PLUGIN.parents[1]
FIXTURES = REPO / "tests" / "skills" / "research_engine" / "fixtures.py"


def fixtures():
    """The repository's engine fixtures, imported by path."""
    if not FIXTURES.is_file():
        raise RuntimeError(
            f"the stub dispatcher plays its lanes with the repository's test fixtures "
            f"and {FIXTURES} is not here — run the stub from a checkout, or use "
            f"--dispatcher agent_run")
    sys.path.insert(0, str(FIXTURES.parent))
    spec = importlib.util.spec_from_file_location("fixtures", FIXTURES)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── the lanes, played by the fixtures ────────────────────────────────────

def _evidence_by_cell(wb) -> dict:
    ev: dict = {}
    sel = set(wb.selected_subcaps())
    for e in wb.rows("Evidence_Detail"):
        for sc in str(e.get("SubCap_IDs") or e.get("SubCaps") or "").replace(";", ",").split(","):
            sc = sc.strip()
            if sc in sel:
                ev.setdefault(sc, []).append(e["E_ID"])
    return ev


def lane_prelim_conductor(agent, prompt_file, ctx):
    F = fixtures()
    from . import prelim
    wb = ctx.run.open()
    if prelim.state(wb)["open"]:
        F.close_prelim(ctx.run, entity=str(wb.metadata().get("entity_name") or "Acme Credit Union"))


def lane_noop(agent, prompt_file, ctx):
    return None


def lane_research(agent, prompt_file, ctx):
    """research-pXcY-producer: work every open cell of the category — five
    evidence rows and a challenged synthesis each; the run's LAST selected
    cell is closed as a declared absence, so the absence path is walked."""
    F = fixtures()
    cat = agent.split("-")[1].upper()          # research-p1c1-producer → P1C1
    wb = ctx.run.open()
    cells = [c for c in wb.selected_subcaps() if c.startswith(cat)]
    last = wb.selected_subcaps()[-1]
    ev = _evidence_by_cell(wb)
    for c in cells:
        row = next((r for r in wb.rows(f"{c[:2]}_Subcap_Scoring") if r.get("SubCap_ID") == c), {})
        if str(row.get("Dominant_Claim") or "").strip() or L.is_declared_absent(row, wb):
            continue
        if c == last and len(cells) > 1:
            F.declare_absent(wb, c, actor=agent)
            continue
        eids = ev.get(c) or F.bank_evidence(wb, c, n=5)
        F.synthesise(wb, c, F.good_synthesis(c, eids), author=agent)
    F.client_facts(wb, wb.selected_subcaps(), _evidence_by_cell(wb))
    F.make_shippable(wb)


def lane_scoring(agent, prompt_file, ctx):
    F = fixtures()
    pillar = agent.split("-")[1].upper()       # scoring-p1-producer → P1
    wb = ctx.run.open()
    ev = _evidence_by_cell(wb)
    for i, r in enumerate(wb.rows(f"{pillar}_Subcap_Scoring")):
        c = str(r.get("SubCap_ID") or "")
        if not c or c not in wb.selected_subcaps() or r.get("Score") not in (None, ""):
            continue
        if c in ev:
            F.score_cell(wb, c, ev[c], score=2.0 + 0.25 * (i % 3), actor=agent)
        else:
            F.score_cell(wb, c, [], score=1.5, confidence="LOW", actor=agent)


def lane_solutions(agent, prompt_file, ctx):
    from . import assessment as A, completeness
    wb = ctx.run.open()
    if not [r for r in wb.rows("Solution_Catalogue") if any(r.values())]:
        A.solution(wb, sol_id="SOL-01", name="Digital onboarding and account opening",
                   platform="Alkami", categories=[wb.selected_subcaps()[0][:4]])
    if not [r for r in wb.rows("Platform_Peer_Adoption") if any(r.values())] \
            and "Platform_Peer_Adoption" not in completeness.reasons(wb):
        completeness.declare(wb, "Platform_Peer_Adoption",
                             "no peer institution's deployment of the named products could "
                             "be examined in this stub run, so no adoption verdict is recorded")


def lane_critic(agent, prompt_file, ctx):
    from . import assessment as A
    wb = ctx.run.open()
    st = A.state(wb)
    for pillar in sorted({c[:2] for c in wb.selected_subcaps()}):
        if st["critic_verdicts"].get(pillar) == "PASS":
            continue
        A.critique(wb, pillar=pillar, verdict="PASS", actor="scoring-critic",
                   note="Re-derived 4 of 6 rows across the capabilities; ceilings hold; "
                        "differentiation present; would move nothing.")
    A.rollup(wb, headline="Modern rails, unbuilt member-relationship layer: sits a band "
                          "below digital-leader peers")


def lane_report(agent, prompt_file, ctx):
    F = fixtures()
    from . import narrative as N
    key = "client_research" if agent == "report-research-producer" else "assessment"
    wb = ctx.run.open()
    F.make_shippable(wb)
    st = N.state(wb, key)["reports"][key]
    if st.get("ready"):
        return
    ev = _evidence_by_cell(wb)
    eids = [e for c in wb.selected_subcaps() for e in ev.get(c, [])][:10]
    if not any(s.get("status") not in ("OPEN",) for s in st.get("sections") or []):
        F.write_report(wb, key, eids, run=ctx.run)


def lane_validator(agent, prompt_file, ctx):
    F = fixtures()
    F.sign_off_sections(ctx.run.open())


def lane_page(agent, prompt_file, ctx):
    page = agent.split("-")[0]
    d = ctx.run.root / "08_sections"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{page}.stub.json").write_text(json.dumps(
        {"page": page, "written_by": agent, "at": _utcnow(), "brief": str(prompt_file)}))


def lane_scanner(agent, prompt_file, ctx):
    """technographic-scanner: in PRELIM the tech baseline is already banked
    by the conductor lane (close_prelim); at the assessment stage it carries
    the solutions duty."""
    wb = ctx.run.open()
    if C.stage_of(wb.metadata()) == "assessment":
        lane_solutions(agent, prompt_file, ctx)


def default_handlers() -> dict:
    """agent-name prefix → handler."""
    return {
        "research-conductor": lane_prelim_conductor,
        "technographic-scanner": lane_scanner,
        "enrichment-connector-specialist": lane_noop,
        "research-p": lane_research,
        "finding-challenger": lane_noop,
        "scoring-critic": lane_critic,
        "scoring-p": lane_scoring,
        "report-validator": lane_validator,
        "report-": lane_report,
        "-surface-producer": lane_page,
    }


class StubDispatcher:
    """Plays every lane in the batch, sequentially, through a handler.

    `fail_first` scripts retryable failures: {"scoring-p1-producer": 2} makes
    that lane's first two attempts return 125 (an empty verdict) before the
    handler runs — so a test can watch the driver's retry and re-dispatch.
    `broken` names lanes whose handler is never run and whose code is 1 (a
    real failure, never retried)."""

    def __init__(self, handlers: dict | None = None, *, fail_first: dict | None = None,
                 broken: set | None = None):
        self.handlers = handlers or {}
        self.fail_first = dict(fail_first or {})
        self.broken = set(broken or ())
        self.calls: list[dict] = []

    @classmethod
    def fixture_backed(cls, **kw) -> "StubDispatcher":
        """The CLI's stub. Chaos is scripted from the environment so the
        stress walk can run the REAL command line:
          DMA_STUB_FAIL_FIRST="research-p1c1-producer:2,scoring-p1-producer:1"
          DMA_STUB_BROKEN="report-validator"
        """
        import os
        ff = dict(kw.pop("fail_first", None) or {})
        for part in filter(None, os.environ.get("DMA_STUB_FAIL_FIRST", "").split(",")):
            name, _, n = part.partition(":")
            ff[name.strip()] = int(n or 1)
        broken = set(kw.pop("broken", None) or ())
        broken |= {x.strip() for x in os.environ.get("DMA_STUB_BROKEN", "").split(",") if x.strip()}
        return cls(default_handlers(), fail_first=ff, broken=broken, **kw)

    def _handler(self, agent: str):
        for key, fn in self.handlers.items():
            if agent.startswith(key) or (key.startswith("-") and agent.endswith(key)):
                return fn
        return lane_noop

    def dispatch(self, batch_path, *, stage, lanes, retries, ctx):
        rows = json.loads(Path(batch_path).read_text())
        detail, failed = [], []
        t0 = time.monotonic()
        for row in rows:
            agent = row["agent"]
            attempts, codes = 0, []
            code = 1 if agent in self.broken else 125
            while True:
                attempts += 1
                if agent in self.broken:
                    code = 1
                elif self.fail_first.get(agent, 0) > 0:
                    self.fail_first[agent] -= 1
                    code = 125
                else:
                    try:
                        self._handler(agent)(agent, row.get("prompt_file"), ctx)
                        code = 0
                    except Exception as e:           # noqa: BLE001 — a lane that raised is a failed lane
                        code = 1
                        detail.append({"agent": agent, "error": f"{e.__class__.__name__}: {str(e)[:300]}"})
                codes.append(code)
                if code not in (124, 125) or attempts > retries:
                    break
            self.calls.append({"stage": stage, "agent": agent, "codes": codes,
                               "prompt_file": row.get("prompt_file")})
            if code != 0:
                failed.append({"agent": agent, "code": code, "attempts": attempts})
            detail.append({"agent": agent, "code": code, "attempts": attempts,
                           "attempt_codes": codes, "elapsed_s": 0.0,
                           "started_at": _utcnow(), "ended_at": _utcnow()})
        return {"lanes": lanes, "dispatched": len(rows), "ok": len(rows) - len(failed),
                "failed": failed, "lanes_detail": [d for d in detail if "code" in d],
                "errors": [d for d in detail if "error" in d],
                "elapsed_s": round(time.monotonic() - t0, 3), "retries_allowed": retries}


class StubReads:
    """The connector as a queue of versions: every poll after the first
    ingests one more, so INGEST_A sees seq 1 and INGEST_B seq 2. `never`
    makes the ingest time out; `contract` is what get_page_contract returns.
    From the environment (the CLI walk): DMA_STUB_NEVER_INGEST=1."""

    def __init__(self, *, entity_id="acme-cu", entity_name="Acme Credit Union",
                 never: bool | None = None, contract: dict | None = None,
                 polls_before_ingest: int = 0):
        import os
        if never is None:
            never = os.environ.get("DMA_STUB_NEVER_INGEST", "") not in ("", "0")
        self.entity_id, self.entity_name, self.never = entity_id, entity_name, never
        self.contract = contract or {"page": "<page>", "sections": {"stub": {"fields": []}}}
        self.polls, self.seq = 0, 0
        self.polls_before_ingest = polls_before_ingest
        self._pending_since = 0
        # Across PROCESSES (the CLI walk) the fake connector must remember
        # which version it already "ingested", or every invocation starts
        # at version 0 and INGEST_B never sees a newer one. DMA_STUB_STATE
        # names the file; in-process doubles keep memory only.
        self._state_file = Path(os.environ["DMA_STUB_STATE"]) if os.environ.get("DMA_STUB_STATE") else None
        if self._state_file and self._state_file.is_file():
            try:
                self.seq = int(json.loads(self._state_file.read_text()).get("seq") or 0)
            except ValueError:
                self.seq = 0

    def _persist(self):
        if self._state_file:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(json.dumps({"seq": self.seq}))

    def pending_runs(self):
        self.polls += 1
        if self.never:
            return []
        self._pending_since += 1
        if self._pending_since > self.polls_before_ingest:
            self.seq += 1
            self._pending_since = 0
            self._persist()
        return ([{"run_id": f"conn-{self.entity_id}-{self.seq}", "display_id": self.entity_id,
                  "entity_name": self.entity_name, "request_id": "req-1",
                  "status": "INGESTED", "run_seq": self.seq, "scored_cells": 6,
                  "runs_for_request": self.seq, "is_latest_for_request": True}]
                if self.seq else [])

    def page_contract(self, page):
        return {**self.contract, "page": page}


class StubShipper:
    """Every page passes unless `verdicts` scripts otherwise:
    {("heatmap", 1): ("fail", ["CG-14 …"])} fails heatmap's FIRST ship;
    `refuse_claim` names pages whose claim is refused; `refuse_promote`
    makes promote_run return incomplete_run."""

    def __init__(self, *, verdicts: dict | None = None, refuse_claim: set | None = None,
                 refuse_promote: bool | None = None):
        import os
        self.verdicts = dict(verdicts or {})
        # From the environment (the CLI walk): DMA_STUB_PAGE_FAIL="heatmap:1,overview:2"
        # fails that page's Nth ship; DMA_STUB_REFUSE_PROMOTE=1.
        for part in filter(None, os.environ.get("DMA_STUB_PAGE_FAIL", "").split(",")):
            page, _, n = part.partition(":")
            self.verdicts.setdefault((page.strip(), int(n or 1)),
                                     ("fail", [f"CG-99 {page.strip()} scripted FAIL #{n or 1}"]))
        if refuse_promote is None:
            refuse_promote = os.environ.get("DMA_STUB_REFUSE_PROMOTE", "") not in ("", "0")
        self.refuse_claim = set(refuse_claim or ())
        self.refuse_promote = refuse_promote
        self.ships: list[dict] = []
        self.promotions: list[str] = []
        self._attempt: dict = {}

    def ship(self, connector_run, page, sections_dir, verdicts_out):
        n = self._attempt.get(page, 0) + 1
        self._attempt[page] = n
        if page in self.refuse_claim:
            res = {"status": "claim_refused", "reasons": ["another session holds the lease"]}
        else:
            status, reasons = self.verdicts.get((page, n), ("pass", []))
            res = {"status": status, "reasons": list(reasons)}
        self.ships.append({"run": connector_run, "page": page, "attempt": n, **res,
                           "sections_dir": str(sections_dir)})
        Path(verdicts_out).parent.mkdir(parents=True, exist_ok=True)
        Path(verdicts_out).write_text(json.dumps({page: res}))
        return res

    def promote(self, connector_run):
        self.promotions.append(connector_run)
        if self.refuse_promote:
            return {"promoted": False, "incomplete_run": ["context"]}
        return {"promoted": True, "promoted_at": _utcnow(),
                "stats": {p: {"rows_written": 1} for p in
                          ("overview", "insights", "heatmap", "platform", "context", "techstack")}}
