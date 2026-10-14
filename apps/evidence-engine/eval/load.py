"""Load harness: a whole DMA run's research volley through the real Engine.

WHY (owner, 2026-10-11): "I want the searches to happen fast. In parallel,
for the over 600 subcaps, batched accordingly. This is the stress-test I
intend to pass." The stress test is IMA: 686 T1_CORE cells, sixteen
categories at once, one batched `research_brief` per capability (~136).

This drives exactly that volley through `Engine.research_brief` — the real
query planner, fan-out, rate limiters, fetch slice, ranking and cards — with
SIMULATED search sources and pages, so the run is repeatable and spends
nothing. Latencies and rates are the production ones divided by `--scale`
(time runs `scale`x faster); every reported duration is multiplied back, so
the numbers read as production seconds for ONE engine instance carrying its
share of the run (`--instances`, default 2: production's max-instances).

    python3 eval/load.py                       # the fixed engine
    python3 eval/load.py --wiring host-bucket  # the pre-2026-10-11 wiring
    python3 eval/load.py --json out.json

What it measures: wall time for the instance's share of the run, per-brief
latency (p50/p95/max, from admission to answer), queries run and cut at the
search-phase budget, questions answered, the achieved search rate. What it
cannot: the live sources' answer quality, CAPTCHAs, or Cloud Run cold starts
— those are the live run's to measure.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CATALOGUE = ROOT.parents[1] / "plugins/dma-insights/skills/dma-research/engine/data/catalogue_v70_names.json"

#: Production latencies (seconds) measured on the live layer, 2026-10-11:
#: a SearXNG query ~1.2 s, a Parallel call ~3 s, a page ~0.8 s.
LAT = {"searxng": 1.2, "parallel": 3.0, "page": 0.8}
#: Production limits (config.py defaults) and the plugin proxy's admission.
RATES = {"EE_SEARXNG_RPS": 4.0, "EE_PARALLEL_RPS": 1.4, "EE_HOST_RPS": 1.0, "EE_ARCHIVE_RPS": 0.5}
BUDGETS = {"EE_SEARCH_PHASE_BUDGET_S": 120.0, "EE_FETCH_PHASE_BUDGET_S": 30.0, "EE_FETCH_TIMEOUT_S": 12.0}
ADMIT_TOTAL = 12              # plugins/dma-insights/scripts/evidence_proxy.py ADMIT_HEAVY
ENTITY = {"legal_name": "IMA Financial Group, Inc.", "domains": ["imacorp.com"],
          "aliases": ["IMA Financial Group"], "location": "Denver, CO"}
#: Hosts a result can land on: the entity's own site (one per-host bucket,
#: the run's hottest) and a spread of press, trade and directory hosts.
HOSTS = ["imacorp.com"] * 6 + [f"press{i}.example.test" for i in range(40)]


def configure_env(scale: float) -> None:
    for k, v in RATES.items():
        os.environ[k] = str(v * scale)
    for k, v in BUDGETS.items():
        os.environ[k] = str(v / scale)


def run_cells() -> dict[str, list[tuple[str, str]]]:
    """capability -> [(cell, name)], the 686 universal T1_CORE cells."""
    names = json.loads(CATALOGUE.read_text())["names"]
    caps: dict[str, list[tuple[str, str]]] = {}
    for cell, name in sorted(names.items()):
        if re.fullmatch(r"P\d+C\d+\.\d+\.\d+", cell):
            caps.setdefault(cell.rsplit(".", 1)[0], []).append((cell, name))
    return caps


def build(scale: float, seed: int):
    """An Engine over simulated sources, built AFTER the env is set."""
    import httpx
    from evidence_engine import search as S
    from evidence_engine.fetch import HttpFetcher
    from evidence_engine.store import Store
    from evidence_engine.tools import Engine
    from evidence_engine.types import SearchHit

    rnd = random.Random(seed)
    counts = {"searxng": 0, "parallel": 0, "pages": 0}

    def hits(source: str, qid: str, facet: str, n: int) -> list:
        out = []
        for r in range(n):
            host = rnd.choice(HOSTS)
            out.append(SearchHit(url=f"https://{host}/{source}/{qid}/{r}", title=f"IMA Financial Group {qid} {r}",
                                 snippet="IMA Financial Group digital insurance brokerage update",
                                 source=source, rank=r + 1, query_id=qid, facet=facet))
        return out

    class Searx:
        source = "searxng"

        async def search(self, text, *, query_id="", facet=""):
            counts["searxng"] += 1
            await asyncio.sleep(LAT["searxng"] / scale)
            return hits("searxng", query_id, facet, 8)

    class Par:
        source = "parallel"

        async def search(self, objective, queries, *, run_id, query_id="", facet=""):
            counts["parallel"] += 1
            await asyncio.sleep(LAT["parallel"] / scale)
            return hits("parallel", query_id, facet, 8)

    page = ("<html><head><title>IMA Financial Group news</title>"
            "<meta property='article:published_time' content='2026-08-18'></head><body><p>"
            + " ".join(["IMA Financial Group, a North American insurance brokerage, said its digital "
                        "strategy and enterprise data platform now support associates and clients across "
                        "risk management, employee benefits and wealth advisory services."] * 6)
            + "</p></body></html>")

    async def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        counts["pages"] += 1
        await asyncio.sleep(LAT["page"] / scale)
        return httpx.Response(200, text=page, headers={"content-type": "text/html"})

    import tempfile
    store = Store(Path(tempfile.mkdtemp(prefix="ee-load-")), gcs_bucket="")
    fetcher = HttpFetcher(transport=httpx.MockTransport(handler), http2=False)
    eng = Engine(fetcher=fetcher, store=store, searx=Searx(), parallel=Par())
    return eng, counts


async def volley(eng, caps: dict, admit: int, scale: float) -> dict:
    gate = asyncio.Semaphore(admit)
    lat, cut, answered, questions, errors = [], 0, 0, 0, 0
    phase = {"search": 0.0, "fetch": 0.0, "rank_and_cards": 0.0}

    async def one(cap: str, cells: list):
        nonlocal cut, answered, questions, errors
        qs = [{"question": f"How does IMA Financial Group approach {name.lower()}?", "subcap_ids": [cell],
               "facet": "primary"} for cell, name in cells]
        t0 = time.monotonic()
        async with gate:
            out = await eng.research_brief(run_id="LOAD-IMA", entity=ENTITY, questions=qs, sub_vertical="IB",
                                           max_cards=2, token_budget=800, provenance="minimal")
        lat.append((time.monotonic() - t0) * scale)
        if out.get("error"):
            errors += 1
            return
        cut += (out.get("search") or {}).get("budget_cut", 0)
        for k in phase:
            phase[k] += (out.get("timing_ms") or {}).get(k, 0) / 1000
        questions += len(out.get("by_question") or [])
        answered += sum(1 for r in out.get("by_question") or [] if r.get("answered"))

    t0, c0 = time.monotonic(), time.process_time()
    await asyncio.gather(*(one(c, cells) for c, cells in caps.items()))
    wall = (time.monotonic() - t0) * scale
    cpu = time.process_time() - c0
    lat.sort()
    return {"wall_s": round(wall, 1), "briefs": len(caps), "errors": errors,
            "latency_s": {"p50": round(statistics.median(lat), 1),
                          "p95": round(lat[int(0.95 * (len(lat) - 1))], 1), "max": round(lat[-1], 1)},
            "queries_cut_at_budget": cut, "questions": questions, "answered": answered,
            # CPU is NOT time-scaled: these are real seconds on this machine.
            # When cpu_s * scale approaches wall_s the harness, not the
            # sources, is the bottleneck — read the projection below instead.
            "cpu_s_unscaled": round(cpu, 1),
            "cpu_share_of_wall": round(cpu * scale / max(wall, 1e-9), 2),
            "phase_sum_s": {k: round(v * scale, 1) for k, v in phase.items()}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scale", type=float, default=20.0)
    ap.add_argument("--instances", type=int, default=2)
    ap.add_argument("--wiring", choices=("source-bucket", "host-bucket"), default="source-bucket")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--admit", type=int, default=ADMIT_TOTAL, help="heavy calls the proxy admits, run-wide")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    configure_env(a.scale)
    sys.path.insert(0, str(ROOT))
    eng, counts = build(a.scale, a.seed)
    if a.wiring == "host-bucket":                 # the pre-2026-10-11 wiring
        eng._source_wait = eng._bucket_wait
    caps = run_cells()
    keys = sorted(caps)
    mine = {k: caps[k] for k in keys[::a.instances]}     # this instance's share
    res = asyncio.run(volley(eng, mine, max(1, a.admit // a.instances), a.scale))
    cells = sum(len(v) for v in mine.values())
    res.update(wiring=a.wiring, scale=a.scale, admit=a.admit, instances=a.instances, cells_this_instance=cells,
               cells_run=sum(len(v) for v in caps.values()), searxng_calls=counts["searxng"],
               parallel_calls=counts["parallel"], pages=counts["pages"],
               searxng_rate_per_s=round(counts["searxng"] / max(res["wall_s"], 1e-9), 2))
    print(json.dumps(res, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
