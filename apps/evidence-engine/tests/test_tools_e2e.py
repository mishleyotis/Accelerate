"""End to end, offline: search → fetch → extract → cards → coverage →
verify → expand, over the committed fixture site, a mocked SearXNG, a fake
Parallel client and a mocked Wayback. Also the brief's §6d rate-limit tests
that live in the engine (burst, breaker reroute, EDGAR cap, coalescing +
cache, paid-only refusal)."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

from evidence_engine import contract as C
from evidence_engine import ratelimit as RL
from evidence_engine import search as S
from evidence_engine.fetch import HttpFetcher
from evidence_engine.store import Store
from evidence_engine.textnorm import normalise
from evidence_engine.tools import Engine

SITE = Path(__file__).resolve().parent / "fixtures" / "site"
ENTITY = {"legal_name": "Example Federal Credit Union", "domains": ["example-fcu.test"],
          "aliases": ["Example FCU"], "location": "Anytown, ST", "charter": "12345"}
TODAY = dt.date(2026, 10, 10)

PRESS = (SITE / "news" / "2026-03-03-membership-growth.html").read_text(encoding="utf-8")
# a trade-press copy (syndicated) and a wire copy of the same release
TRADE = PRESS.replace("example-fcu.test", "example-press.test").replace(
    "<title>", "<title>Example Press — ")
WIRE = PRESS.replace("example-fcu.test", "prnewswire.com")
OTHER = """<html><head><title>Example Regulator — Quarterly data</title>
<meta property="article:published_time" content="2026-09-01"></head><body><article>
<p>Example Federal Credit Union reported total assets of $3.1 billion and 212,000 members at June 30, 2026, according to the quarterly call report.</p>
<p>Its net worth ratio stood at 10.8 percent for the period.</p></article></body></html>"""
ARCHIVED = """<html><head><title>Example Federal Credit Union — 2023 annual results</title>
<meta property="article:published_time" content="2024-02-20"></head><body><article>
<p>Example Federal Credit Union said membership grew 4 percent to 180,000 members during 2023, its earlier annual results show.</p>
</article></body></html>"""
CONFLICT = """<html><head><title>Example Herald — Credit union grows</title>
<meta property="article:published_time" content="2026-08-15"></head><body><article>
<p>Example Federal Credit Union now serves 198,000 members across 14 branches, the Anytown lender said on Friday.</p></article></body></html>"""

SEARX_HITS = [
    {"url": "https://www.example-fcu.test/news/2026-03-03-membership-growth.html", "title": "Membership growth", "content": "x", "engine": "mojeek"},
    {"url": "https://example-press.test/2026/03/04/example-fcu-growth?utm_source=rss", "title": "Example FCU growth", "content": "x", "engine": "brave"},
    {"url": "https://www.prnewswire.com/news-releases/example-fcu-growth-301.html", "title": "Example FCU growth (wire)", "content": "x", "engine": "brave"},
    {"url": "https://regulator.example.test/data/2026q2", "title": "Quarterly data", "content": "x", "engine": "mojeek"},
    {"url": "https://herald.example.test/2026/08/15/cu-grows", "title": "Credit union grows", "content": "x", "engine": "qwant"},
    {"url": "https://www.example-fcu.test/dead/page", "title": "Dead page", "content": "x", "engine": "mojeek"},
]


def _site_file(path: str):
    rel = path.lstrip("/") or "index.html"
    p = SITE / rel
    if p.is_dir():
        p = p / "index.html"
    return p if p.exists() else None


class State:
    def __init__(self):
        self.searx_calls = 0
        self.searx_mode = "ok"       # ok | 429
        self.requests = []


def make_transport(st: State):
    def handler(req: httpx.Request) -> httpx.Response:
        u = urlsplit(str(req.url))
        st.requests.append(str(req.url))
        host, path = u.hostname, u.path
        if host == "searx.test":
            st.searx_calls += 1
            if st.searx_mode == "429":
                return httpx.Response(429, headers={"Retry-After": "60"}, text="slow down")
            return httpx.Response(200, json={"results": SEARX_HITS, "unresponsive_engines": []})
        if host == "archive.org":
            orig = req.url.params.get("url", "")
            if "dead" in orig:
                return httpx.Response(200, json={"archived_snapshots": {"closest": {
                    "available": True, "status": "200", "timestamp": "20260101000000",
                    "url": f"http://web.archive.org/web/20260101000000/{orig}"}}})
            return httpx.Response(200, json={"archived_snapshots": {}})
        if host == "web.archive.org":
            return httpx.Response(200, text=ARCHIVED, headers={"content-type": "text/html"})
        if host in ("example-fcu.test", "www.example-fcu.test"):
            if path.startswith("/dead/"):
                return httpx.Response(404)
            f = _site_file(path)
            if f is None:
                return httpx.Response(404)
            ct = "application/pdf" if f.suffix == ".pdf" else ("text/plain" if f.suffix in (".txt", ".xml") else "text/html")
            return httpx.Response(200, content=f.read_bytes(), headers={"content-type": ct})
        if host == "example-press.test":
            if path == "/robots.txt":
                return httpx.Response(404)
            return httpx.Response(200, text=TRADE, headers={"content-type": "text/html"})
        if host == "www.prnewswire.com":
            if path == "/robots.txt":
                return httpx.Response(404)
            return httpx.Response(200, text=WIRE, headers={"content-type": "text/html"})
        if host == "regulator.example.test":
            if path == "/robots.txt":
                return httpx.Response(404)
            return httpx.Response(200, text=OTHER, headers={"content-type": "text/html"})
        if host == "herald.example.test":
            if path == "/robots.txt":
                return httpx.Response(404)
            return httpx.Response(200, text=CONFLICT, headers={"content-type": "text/html"})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


class FakeParallel:
    source = "parallel"

    def __init__(self):
        self.calls = 0
        self.mode = "ok"

    async def search(self, objective, queries, *, run_id, query_id="", facet=""):
        self.calls += 1
        if self.mode == "429":
            raise S.SourceError("429", "parallel", "rate limited")
        from evidence_engine.types import SearchHit
        return [SearchHit(url="https://regulator.example.test/data/2026q2", title="Quarterly data",
                          snippet="x", source="parallel", rank=1, query_id=query_id, facet=facet)]


@pytest.fixture
def engine(tmp_path, monkeypatch):
    RL.reset()
    t = {"now": 0.0}

    async def fake_sleep(s):
        t["now"] += s
    RL.configure(clock=lambda: t["now"], sleep=fake_sleep)
    st = State()
    transport = make_transport(st)
    fetcher = HttpFetcher(transport=transport, clock=lambda: t["now"], sleep=fake_sleep,
                          today=lambda: TODAY, http2=False)
    searx = S.SearxClient("https://searx.test", httpx.AsyncClient(transport=transport))
    par = FakeParallel()
    eng = Engine(fetcher=fetcher, store=Store(tmp_path / "store"), searx=searx, parallel=par, today=TODAY)
    eng._test_state = st            # type: ignore[attr-defined]
    eng._test_parallel = par        # type: ignore[attr-defined]
    yield eng
    RL.reset()


def run(coro):
    return asyncio.run(coro)


def test_research_brief_returns_contract_clean_verified_cards(engine):
    out = run(engine.research_brief(run_id="R-1", entity=ENTITY, facet="value",
                                    questions=["How many members does the credit union serve and how fast is membership growing?"],
                                    max_cards=6, reference_date="2026-10-10"))
    assert "error" not in out and out["cards"], out.get("search")
    for c in out["cards"]:
        assert C.item_problems(c["item"]) == [], c
        assert "content_hash" not in c["provenance"]          # standard projection is lean
        full = engine.store.get_card("R-1", c["card_id"])    # the stored card is complete
        text, meta = engine.store.get_text(full["provenance"]["content_hash"])
        s, e = full["provenance"]["excerpt_offsets"]
        assert text[s:e] == c["item"]["excerpt"]
        assert c["item"]["linked_subcap_ids"] == [] and c["item"]["origin"] == "producer"
        assert c["provenance"]["recency"] in C.RECENCY_WORDS
        assert c["item"]["claim_type"] == C.claim_label_for(c["item"]["tier"])
    assert out["coverage"]["novelty"] == 1.0 and out["coverage"]["saturation"] is False
    assert "news" in out["coverage"]["ladder_searched"]
    assert out["tokens"] > 0


def test_syndicated_copies_collapse_into_one_origin_cluster(engine):
    """Three copies of one release (own site, trade press, wire) are ONE
    origin cluster; the same words are carded once and the other copies are
    reported as drops — syndication is never counted as corroboration."""
    out = run(engine.research_brief(run_id="R-2", entity=ENTITY, questions=["membership grew percent members"],
                                    max_cards=10, token_budget=20000, reference_date="2026-10-10"))
    copy_hosts = ("www.example-fcu.test", "example-press.test", "www.prnewswire.com")
    copies = [c for c in out["cards"] if c["provenance"]["host"] in copy_hosts and c["provenance"]["url_status"] == "live"]
    assert copies, [c["provenance"]["host"] for c in out["cards"]]
    assert len({c["item"]["excerpt"] for c in copies}) == len(copies), "one excerpt, one card"
    assert len({c["provenance"]["origin_cluster"] for c in copies}) == 1
    assert copies[0]["provenance"]["syndication_count"] >= 2
    assert copies[0]["provenance"]["host"] == "www.example-fcu.test", "the entity's own copy outranks the wire's"
    assert any("syndication is not corroboration" in d["reason"] for d in out["search"]["dropped"])
    # the regulator page is its own origin
    reg = [c for c in out["cards"] if c["provenance"]["host"] == "regulator.example.test"]
    assert reg and reg[0]["provenance"]["origin_cluster"] != copies[0]["provenance"]["origin_cluster"]
    assert reg[0]["item"]["tier"] == "T3"      # regulator.example.test is NOT a registered regulator


def test_entity_own_domain_is_never_t1_and_wire_is_t5(engine):
    out = run(engine.research_brief(run_id="R-3", entity=ENTITY, questions=["membership grew members assets"], max_cards=10, token_budget=20000))
    for c in out["cards"]:
        if c["provenance"]["host"].endswith("example-fcu.test"):
            assert c["item"]["tier"] != "T1" and c["provenance"]["entity_match"] == "confirmed"
        if c["provenance"]["host"] == "www.prnewswire.com":
            assert c["item"]["tier"] == "T5"


def test_dead_url_is_archived_or_absent_never_unsourced(engine):
    out = run(engine.research_brief(run_id="R-4", entity=ENTITY, questions=["membership grew members"], max_cards=12, token_budget=20000))
    dead = [engine.store.get_card("R-4", c["card_id"]) for c in out["cards"] if "web.archive.org" in c["item"]["source_url"]]
    assert dead, [c["item"]["source_url"] for c in out["cards"]]
    for c in dead:
        assert c["provenance"]["url_status"] == "archived"
        assert "id_/" in c["item"]["source_url"]
        assert c["provenance"]["archive_timestamp"] == "20260101000000"
        assert c["provenance"]["original_url"].startswith("https://www.example-fcu.test/dead/")
        assert c["provenance"]["host"] == "www.example-fcu.test"
        # classified and named by the page it is a copy OF, never by the archive:
        # the entity's own site, outside a disclosure path ⇒ entity_owned, T5
        assert c["item"]["tier"] == "T5" and c["provenance"]["source_type_hint"] == "entity_owned"
        assert not c["item"]["source_name"].startswith("web.archive.org")
        assert c["provenance"]["entity_match"] == "confirmed"
    for c in out["cards"]:
        assert c["item"]["source_url"].startswith("http")


def test_conflict_candidates_are_flagged_not_resolved(engine):
    out = run(engine.research_brief(run_id="R-5", entity=ENTITY, questions=["how many members does it serve"], max_cards=10, token_budget=20000))
    fields = {k["field"] for k in out["coverage"]["conflict_candidates"]}
    assert "members" in fields
    members = next(k for k in out["coverage"]["conflict_candidates"] if k["field"] == "members")
    assert {v["value"] for v in members["values"]} >= {"212000", "198000"}
    assert "never averages" in members["disposition"]


def test_saturation_after_two_repeat_calls(engine):
    q = ["membership grew members"]
    a = run(engine.research_brief(run_id="R-6", entity=ENTITY, facet="works", questions=q))
    b = run(engine.research_brief(run_id="R-6", entity=ENTITY, facet="works", questions=q))
    c = run(engine.research_brief(run_id="R-6", entity=ENTITY, facet="works", questions=q))
    assert a["coverage"]["saturation"] is False
    assert b["coverage"]["novelty"] == 0.0
    assert c["coverage"]["saturation"] is True


def test_verify_and_expand(engine):
    out = run(engine.research_brief(run_id="R-7", entity=ENTITY, questions=["membership grew members"], max_cards=4))
    ids = [c["card_id"] for c in out["cards"]]
    v = run(engine.verify_cards(run_id="R-7", card_ids=ids + ["EV-nope"]))
    assert v["summary"]["passed"] == len(ids) and v["summary"]["not_found"] == 1
    for r in v["results"]:
        if r["verdict"] == "PASS":
            assert r["checks"]["offsets"] == "ok" and r["checks"]["verbatim_in_connector_text"] == "ok"
    h = out["cards"][0]["provenance"]["context_handle"]          # in every projection
    ctx = run(engine.expand_context(context_handle=h, window=1, run_id="R-7"))
    assert out["cards"][0]["item"]["excerpt"] in ctx["context"]
    assert ctx["offsets"][0] <= ctx["excerpt_offsets"][0]
    rep = run(engine.coverage_report(run_id="R-7"))
    assert rep["cards_total"] == len(ids)


def test_tampered_card_fails_verification(engine):
    out = run(engine.research_brief(run_id="R-8", entity=ENTITY, questions=["membership grew members"], max_cards=2))
    c = engine.store.get_card("R-8", out["cards"][0]["card_id"])
    c["item"]["excerpt"] = c["item"]["excerpt"][:-1] + "!"
    engine.store.put_card("R-8", c)
    v = run(engine.verify_cards(run_id="R-8", card_ids=[c["card_id"]], recheck_liveness=False))
    assert v["results"][0]["verdict"] == "FAIL" and "offsets" in v["results"][0]["failed"]


def test_vendor_name_in_question_is_refused_unless_evidence_led(engine):
    out = run(engine.research_brief(run_id="R-9", entity=ENTITY, questions=["Does it run Symitar for its core banking?"]))
    assert any(v["kind"] == "refused" for v in out["guard_violations"])
    out2 = run(engine.research_brief(run_id="R-9", entity=ENTITY, questions=["Does it run Symitar for its core banking?"],
                                     allow_names_from_cards={"Symitar": ["EV-abc12345"]}))
    assert any(v["kind"] == "exception" and v.get("card_id") == "EV-abc12345" for v in out2["guard_violations"])


# ── §6d ────────────────────────────────────────────────────────────────

def test_6d_coalescing_and_cache_three_agents_one_upstream_call_then_zero(engine):
    st = engine._test_state
    q = ["membership grew members"]
    async def burst():
        return await asyncio.gather(*(engine.research_brief(run_id=f"R-c{i}", entity=ENTITY, questions=q, facet="works") for i in range(3)))
    run(burst())
    searx_after_burst, par_after_burst = st.searx_calls, engine._test_parallel.calls
    n_queries = len({(s.split("q=")[1].split("&")[0]) for s in st.requests if "searx.test" in s})
    assert searx_after_burst == n_queries, (searx_after_burst, n_queries)   # one upstream call per distinct query, not three
    run(engine.research_brief(run_id="R-c9", entity=ENTITY, questions=q, facet="works"))
    assert st.searx_calls == searx_after_burst and engine._test_parallel.calls == par_after_burst   # cache: zero upstream


def test_6d_breaker_reroute_appears_in_provenance(engine):
    engine._test_state.searx_mode = "429"
    out = run(engine.research_brief(run_id="R-b", entity=ENTITY, questions=["membership grew members"], max_cards=4))
    assert out["search"]["per_source"]["searxng"]["error"] == "429"
    assert RL.breakers().get("searxng").state == "open"
    engine._test_state.searx_mode = "ok"
    out2 = run(engine.research_brief(run_id="R-b", entity=ENTITY, questions=["total assets billion net worth"], max_cards=4))
    assert "rerouted_from:searxng" in out2["search"]["rerouted"]
    assert out2["cards"] and all("rerouted_from:searxng" in c["provenance"]["via"] for c in out2["cards"])
    assert out2["search"]["per_source"].get("parallel", {}).get("count", 0) >= 1


def test_6d_paid_only_remainder_returns_needs_spend_approval(engine):
    engine._test_state.searx_mode = "429"
    engine._test_parallel.mode = "429"
    run(engine.research_brief(run_id="R-p", entity=ENTITY, questions=["membership grew members"]))
    out = run(engine.research_brief(run_id="R-p", entity=ENTITY, questions=["membership grew members"]))
    assert out.get("needs_spend_approval") is True and out["cards"] == []
    assert "tavily" in out["paid_options"] and "exa" in out["paid_options"]


def test_6d_burst_nine_agents_fifty_calls_no_lost_queries(engine):
    async def many():
        coros = []
        for i in range(50):
            coros.append(engine.research_brief(run_id=f"R-burst-{i % 9}", entity=ENTITY,
                                               questions=[f"membership grew members variant {i % 5}"], max_cards=2))
        return await asyncio.gather(*coros)
    outs = run(many())
    assert len(outs) == 50 and all("error" not in o for o in outs)
    snap = RL.limits().snapshot()["sources"]["searxng"]
    assert snap["acquired"] <= 9 * 50
    # every answer carries a coverage block; none was dropped on the floor
    assert all("coverage" in o for o in outs)


def test_6d_edgar_global_cap_eight_per_second():
    RL.reset()
    t = {"now": 0.0}
    stamps = []

    async def fake_sleep(s):
        t["now"] += s
    RL.configure(clock=lambda: t["now"], sleep=fake_sleep)

    async def go():
        bucket = RL.limits().source("sec")
        for _ in range(100):
            await bucket.acquire()
            stamps.append(t["now"])
    run(go())
    for a in stamps:
        assert sum(1 for b in stamps if a <= b < a + 1.0) <= 8
    assert stamps[-1] >= 11.5
    RL.reset()


# ── tuning iteration 2 (eval v1, 2026-10-10) ─────────────────────────────

def test_fetch_slice_is_host_diverse_with_back_fill():
    from evidence_engine.tools import PER_HOST_CAP, _host_diverse_order
    hits = [{"url": f"https://one.test/{i}", "url_key": f"one.test/{i}"} for i in range(6)]
    hits += [{"url": "https://two.test/a", "url_key": "two.test/a"},
             {"url": "https://three.test/a", "url_key": "three.test/a"}]
    order = [h["url"] for h in _host_diverse_order(hits)]
    assert order[:PER_HOST_CAP] == [f"https://one.test/{i}" for i in range(PER_HOST_CAP)]
    assert order[PER_HOST_CAP:PER_HOST_CAP + 2] == ["https://two.test/a", "https://three.test/a"]
    assert order[PER_HOST_CAP + 2:] == [f"https://one.test/{i}" for i in range(PER_HOST_CAP, 6)]
    assert len(order) == len(hits)


def test_refused_before_bytes_refunds_its_fetch_slot(engine):
    """Robots, an open breaker and a never-fetch host take no slot: with
    fetch_limit=2 and three such hits in front, both real pages are read."""
    st = engine._test_state
    # every front hit NAMES the entity, so the entity-first ordering keeps
    # them ahead of the trade copy and the refund rule is what is measured
    front = [
        {"url": "https://en.wikipedia.org/wiki/Example_FCU", "title": "Example FCU - Wikipedia", "content": "x", "engine": "mojeek"},
        {"url": "https://example-press.test/blocked/one", "title": "Example FCU blocked", "content": "x", "engine": "brave"},
        {"url": "https://example-press.test/blocked/two", "title": "Example FCU blocked", "content": "x", "engine": "brave"},
    ]
    orig = SEARX_HITS[:]
    SEARX_HITS[:] = front + orig[:2]
    try:
        # example-press.test refuses /blocked/ in robots for this test
        import urllib.robotparser as rp
        parser = rp.RobotFileParser()
        parser.parse("User-agent: *\nDisallow: /blocked/\n".splitlines())
        engine.fetcher._robots["example-press.test"] = (parser, 0.0)
        out = run(engine.research_brief(run_id="R-h", entity=ENTITY, questions=["membership grew members"],
                                        max_cards=4, fetch_limit=2))
    finally:
        SEARX_HITS[:] = orig
    reasons = [f["reason"] for f in out["search"]["fetch_failures"]]
    assert any("never_fetch" in r and "refunded" in r for r in reasons), reasons
    assert out["search"]["fetched"] == 2, (out["search"]["fetched"], reasons)
    assert not any("wikipedia" in u for u in st.requests)


def test_ambiguous_cards_rank_after_probable_ones_when_budget_binds():
    from evidence_engine import pipeline as P_
    from evidence_engine.types import Document, EntityRef
    ent = EntityRef(legal_name="Example Federal Credit Union", domains=["example-fcu.test"], aliases=["Example FCU"])
    amb = "Example Pharmaceuticals reported total assets of $9.1 billion and 2,000 staff at June 30, 2026, the company said."
    prob = "Example Federal Credit Union reported total assets of $3.1 billion and 212,000 members at June 30, 2026."
    docs = [Document(url="https://namesake.test/a", final_url="https://namesake.test/a", title="Namesake", text=amb,
                     verify_text=amb, published="2026-07-01", content_hash="a" * 64),
            Document(url="https://herald.example.test/b", final_url="https://herald.example.test/b", title="Herald", text=prob,
                     verify_text=prob, published="2026-07-01", content_hash="b" * 64)]
    cards, _ = P_.build_cards(docs, question="total assets reported", entity=ent, facet="value",
                              reference=TODAY, today=TODAY, max_cards=1)
    assert len(cards) == 1 and cards[0]["provenance"]["entity_match"] == "probable"


def test_verify_cards_date_check_can_fail(engine):
    out = run(engine.research_brief(run_id="R-d", entity=ENTITY, questions=["membership grew members"], max_cards=1))
    c = engine.store.get_card("R-d", out["cards"][0]["card_id"])
    c["item"]["published_date"] = "2099-01-01"
    engine.store.put_card("R-d", c)
    v = run(engine.verify_cards(run_id="R-d", card_ids=[c["card_id"]], recheck_liveness=False))
    assert v["results"][0]["checks"]["date"].startswith("bad")
    assert v["results"][0]["verdict"] == "FAIL"


def test_fetch_slice_puts_hits_naming_the_entity_first():
    from evidence_engine.tools import _host_diverse_order
    from evidence_engine.types import EntityRef
    ent = EntityRef(legal_name="Example Federal Credit Union", domains=["example-fcu.test"], aliases=["Example FCU"])
    hits = [{"url": "https://namesake-pharma.test/catalog", "url_key": "k1", "title": "Example Pharma catalogue", "snippet": "products"},
            {"url": "https://namesake-pharma.test/jobs", "url_key": "k2", "title": "Careers at Example Pharma", "snippet": ""},
            {"url": "https://trade.test/story", "url_key": "k3", "title": "Example FCU rolls out new app", "snippet": "the credit union said"},
            {"url": "https://www.example-fcu.test/about", "url_key": "k4", "title": "About us", "snippet": ""},
            {"url": "https://other.test/x", "url_key": "k5", "title": "Unrelated", "snippet": "Example Federal Credit Union is cited here"}]
    order = [h["url_key"] for h in _host_diverse_order(hits, ent)]
    assert order[0] == "k4", "the entity's own host first"
    assert order[1:3] == ["k3", "k5"], "then hits naming the entity, in fused order"
    assert order[3:] == ["k1", "k2"], "the namesake last"
