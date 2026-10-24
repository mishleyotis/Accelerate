"""Drive the REAL pipeline to its PREFLIGHT gate inside a live session.

Not a test (no `test_` prefix, never collected): a probe for a person to run
from a real Claude Code session, to see what a DMA run's first gate does with
THIS session's own connector roster — no typed baseline, a stub dispatcher,
nothing spent, nothing dispatched to a model, nothing pushed.

    python3 plugins/dma-insights/scripts/tests/preflight_live_probe.py

It prints the PREFLIGHT outcome, whether the baseline was adopted from the
transcript, and the families it found. Before 2026-10-10 a session that had
not typed its tool list read BLOCKED here.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / "plugins/dma-insights/skills/dma-research"))
sys.path.insert(0, str(REPO / "tests/skills/research_engine"))

from engine import pipeline as P, pipeline_stub as S, preflight  # noqa: E402
from fixtures import new_run, preflight_doc  # noqa: E402


def main() -> int:
    if not os.environ.get("CLAUDE_CODE_SESSION_ID"):
        print("run this from inside a Claude Code session", file=sys.stderr)
        return 2
    tmp = Path(tempfile.mkdtemp(prefix="dma-preflight-probe-"))
    run = new_run(tmp, n=6, baseline=None)
    preflight.record(run, preflight_doc())
    log = []
    p = P.Pipeline(run, P.Options(
        dispatcher=S.StubDispatcher(S.default_handlers()), reads=S.StubReads(),
        shipper=S.StubShipper(), push=False, folder_root=tmp / "out",
        ingest_poll_s=0, sleep=lambda s: None, log=log.append,
        until="RESEARCH", max_rounds=1, stall_rounds=0))
    out = p.run_all()
    base = run.root / "connectors_baseline.json"
    rec = json.loads(base.read_text()) if base.is_file() else {}
    print(json.dumps({
        "outcome": out.get("outcome"), "stage": out.get("stage"),
        "blocked_reason": (out.get("reason") or "")[:160]
        if out.get("outcome") == "BLOCKED" else "",
        "baseline_sources": rec.get("sources"),
        "families_present": rec.get("present"),
        "enrichment_degraded": bool(p.state.get("enrichment_degraded")),
        "adoption_log": [l for l in log if "adopted" in l],
    }, indent=1))
    return 1 if out.get("outcome") == "BLOCKED" else 0


if __name__ == "__main__":
    sys.exit(main())
