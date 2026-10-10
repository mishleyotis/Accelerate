"""The enrichment doctrine names the routes that answer, and the ladder does
not stop at the first refusal (SWBC gold audit 2026-10-04, RC-07; D-22,
D-23; owner decision 3).

What was measured on run 7968492e (SWBC):

- the doctrine said "Glassdoor, Indeed and ZipRecruiter all 403 ... such a
  value is an inference with its route named, or it is omitted" in ten
  files, so the sentiment card shipped one company-reported bar while two
  auditors called the Indeed connector (`get_company_data`, 3.1/5, 46/97
  recommend) and the CFPB complaint API (213 complaints, 96.2% timely) live;
- when Exa/Tavily/Firecrawl credit ran out on 2026-10-01 every rung that
  needed them recorded NOT_RUN — 281 H3 alerts, the I1 contradictory
  probes, the techstack ABSENT search — with no failover tried;
- SWBC Mortgage's HMDA series was public and never back-filled.

A web fetch of indeed.com still 403s. The connector is a different door,
and since owner decision 3 (2026-10-04) its reading is admissible evidence
through `register_evidence(origin='connector', ...)` (migration 0063).
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "dma-insights"
SKILL = PLUGIN / "skills" / "dma-surface-production"
SOURCES = SKILL / "02-inputs" / "enrichment_sources.json"


def _sources() -> dict:
    return json.loads(SOURCES.read_text(encoding="utf-8"))


def _facet(name: str) -> list:
    return _sources()["facets"][name]["sources"]


def test_the_sentiment_facet_lists_the_indeed_connector_route():
    rows = [s for s in _facet("sentiment") if s.get("connector") == "indeed"]
    assert rows, "the sentiment facet names no Indeed connector route"
    r = rows[0]
    assert r.get("tool") == "mcp__Indeed__get_company_data", r
    assert r.get("origin") == "connector", (
        "a connector reading registers as origin='connector' (0063), never as "
        "a URL-less INFERENCE")
    assert r.get("tier_band") == "T3"
    assert "rating" in r["serves"].lower()
    assert r.get("status", "").startswith("wired")


def test_the_sentiment_facet_lists_the_cfpb_api_route():
    rows = [s for s in _facet("sentiment") if s.get("connector") == "cfpb"]
    assert rows, "the sentiment facet names no CFPB complaint API route"
    r = rows[0]
    assert r.get("tier_band") == "T1"
    assert "aggregation" in r["serves"].lower() or "aggs" in json.dumps(r)
    assert "company" in json.dumps(r).lower()


def test_the_firmographics_facet_lists_the_hmda_back_fill():
    rows = [s for s in _facet("firmographics") if s.get("connector") == "hmda"]
    assert rows, "no HMDA back-fill route for a mortgage subsidiary's series"
    assert "unit" in json.dumps(rows[0]).lower(), (
        "a subsidiary's HMDA figure names its entity in unit/basis (owner "
        "decision 2)")


def test_the_search_failover_order_is_declared_and_ends_on_the_builtins():
    sc = _sources()["search_connectors"]
    order = sc.get("_failover")
    assert order and order[:3] == ["exa", "tavily", "firecrawl"], order
    assert order[-1] in ("websearch_webfetch", "WebSearch/WebFetch"), order
    rule = sc.get("_failover_rule", "")
    assert "NOT_RUN" in rule and re.search(r"whole chain|every (rung|provider)", rule), (
        "a rung is NOT_RUN only after the whole chain failed")


#: The words that mean the paragraph is teaching the connector route.
CONNECTOR_WORDS = re.compile(r"connector|get_company_data", re.I)


def _paragraphs(path: Path):
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        def strings(n):
            if isinstance(n, str):
                yield n
            elif isinstance(n, dict):
                for v in n.values():
                    yield from strings(v)
            elif isinstance(n, list):
                for v in n:
                    yield from strings(v)
        # a facet source row is one "paragraph": its strings together
        data = json.loads(text)
        for facet in data.get("facets", {}).values():
            for row in facet.get("sources", []):
                yield " ".join(strings(row))
        return
    yield from re.split(r"\n\s*\n", text)


def _stale(paths) -> list:
    out = []
    for p in paths:
        for para in _paragraphs(p):
            if re.search(r"\bIndeed\b", para) and "403" in para \
                    and not CONNECTOR_WORDS.search(para):
                out.append(f"{p.relative_to(ROOT)}: {para.strip()[:140]!r}")
    return out


def test_no_skill_file_teaches_indeed_403_without_the_connector():
    files = [p for p in SKILL.rglob("*") if p.suffix in (".md", ".json")]
    bad = _stale(files)
    assert not bad, (
        "a paragraph still says Indeed 403s and never names the connector "
        "route (RC-07):\n" + "\n".join(bad))


def test_no_agent_teaches_indeed_403_without_the_connector():
    bad = _stale(sorted((PLUGIN / "agents").rglob("*.md")))
    assert not bad, "\n".join(bad)


def test_the_ladder_does_not_stop_at_the_first_refusal():
    """The absence protocol says a refused provider hands over to the next,
    and names the order, so a NOT_RUN rung reports the chain it exhausted."""
    text = (SKILL / "01-start-here" / "4-absence-protocol.md").read_text(encoding="utf-8")
    assert re.search(r"Exa\W+Tavily\W+Firecrawl\W+WebSearch", text), (
        "the failover order is not stated in the absence protocol")
    assert re.search(r"first refusal", text, re.I)
