"""registry.classify: the tier hint from the source's identity, and the pin
that its lists equal the connector's (apps/mcp/dma_mcp/source_rules.py)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from evidence_engine import registry
from evidence_engine.types import EntityRef

ENTITY = EntityRef(legal_name="Example Federal Credit Union",
                   domains=["example-fcu.test", "www.example-fcu.test"],
                   aliases=["Example FCU"], location="Springfield, Oregon",
                   charter="12345", cik="0001234567", ticker="EXFC")

# url, source_name, source_type, tier, is_wire, is_vendor_collateral, ladder_rung
CASES = [
    # the entity's own domain — never T1
    ("https://www.example-fcu.test/investor-relations/annual-report-2025", None,
     "entity_owned", "T2", False, False, "entity_site"),
    ("https://example-fcu.test/about/leadership", None, "entity_owned", "T5", False, False, "entity_site"),
    ("https://online.example-fcu.test/products/checking", None, "entity_owned", "T5", False, True, "entity_site"),
    ("https://example-fcu.test/news/2026/new-branch-opens", None, "entity_owned", "T2", False, False, "entity_site"),
    ("https://example-fcu.test/governance/board", None, "entity_owned", "T2", False, False, "entity_site"),
    ("https://example-fcu.test/careers/", None, "entity_owned", "T5", False, False, "entity_site"),
    # own press-release path: disclosure in the methodology, capped by the connector
    ("https://example-fcu.test/press-releases/2026/digital-banking", None,
     "entity_owned", "T5", False, True, "entity_site"),
    # a scan name never lifts the own domain to T1
    ("https://example-fcu.test/", "BuiltWith scan of example-fcu.test", "entity_owned", "T5", False, False, "entity_site"),
    # regulators
    ("https://ncua.gov/analysis/cuso-data", None, "regulator", "T1", False, False, "regulator"),
    ("https://www.ncua.gov/newsroom/press-release/2026/example", None, "regulator", "T2", False, False, "regulator"),
    ("https://data.fdic.gov/bank/example", None, "regulator", "T1", False, False, "regulator"),
    ("https://www.fdic.gov/analysis/center-financial-research/example", None, "regulator", "T1", False, False, "regulator"),
    ("https://www.fca.org.uk/firms/example", None, "regulator", "T1", False, False, "regulator"),
    ("https://www.bankofengland.co.uk/prudential-regulation/example", None, "regulator", "T1", False, False, "regulator"),
    ("https://www.osfi-bsif.gc.ca/en/example", None, "regulator", "T1", False, False, "regulator"),
    ("https://www.sec.gov/news/press-release/2026-12", None, "regulator", "T2", False, False, "regulator"),
    ("https://dfpi.ca.gov/licensees/example", None, "regulator", "T1", False, False, "regulator"),
    # lookalike hosts are NOT regulators
    ("https://ncua.gov.example.test/report", None, "other", "T3", False, False, "other"),
    ("https://notfdic.gov.test/x", None, "other", "T3", False, False, "other"),
    # filings
    ("https://www.sec.gov/Archives/edgar/data/1234567/000123456726000001/example-10k.htm", None,
     "filing", "T1", False, False, "filings"),
    ("https://efts.sec.gov/LATEST/search-index?q=example", None, "filing", "T1", False, False, "filings"),
    ("https://data.sec.gov/submissions/CIK0001234567.json", None, "filing", "T1", False, False, "filings"),
    ("https://www.sedarplus.ca/csa-party/records/document.html?id=1", None, "filing", "T1", False, False, "filings"),
    ("https://find-and-update.company-information.service.gov.uk/company/00000001", None,
     "filing", "T1", False, False, "filings"),
    # trade press / news
    ("https://www.americanbanker.com/news/example-credit-union-core", None, "trade_press", "T3", False, False, "trade_press"),
    ("https://www.cutimes.com/2026/01/01/example/", None, "trade_press", "T3", False, False, "trade_press"),
    ("https://www.americascreditunions.org/news/example", None, "trade_press", "T3", False, False, "trade_press"),
    ("https://www.reuters.com/business/finance/example", None, "news", "T3", False, False, "news"),
    ("https://apnews.com/article/example", None, "news", "T3", False, False, "news"),
    # wires: flagged, and a /news-releases/ path is the connector's collateral shape
    ("https://www.prnewswire.com/news-releases/example-fcu-selects-core-301.html", None,
     "vendor", "T5", True, True, "other"),
    ("https://www.businesswire.com/news/home/20260101/en/example", None, "news", "T3", True, False, "news"),
    ("https://www.globenewswire.com/news-release/2026/01/01/example.html", None, "vendor", "T5", True, True, "other"),
    # academic
    ("https://arxiv.org/abs/2401.00001", None, "academic", "T3", False, False, "academic"),
    ("https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1", None, "academic", "T3", False, False, "academic"),
    # job boards
    ("https://www.linkedin.com/jobs/view/123456", None, "job_board", "T3", False, False, "careers"),
    ("https://www.linkedin.com/company/example-fcu", None, "other", "T3", False, False, "other"),
    ("https://example.wd5.myworkdayjobs.com/careers/job/x", None, "job_board", "T3", False, False, "careers"),
    ("https://www.indeed.com/cmp/Example-Federal-Credit-Union/jobs", None, "job_board", "T3", False, False, "careers"),
    # review sites
    ("https://apps.apple.com/us/app/example-fcu-mobile/id123", None, "review_site", "T3", False, False, "other"),
    ("https://www.trustpilot.com/review/example-fcu.test", None, "review_site", "T3", False, False, "other"),
    ("https://www.g2.com/products/example-core/reviews", None, "vendor", "T5", False, True, "other"),
    # vendor collateral on an unknown host
    ("https://vendor-core.test/customers/example-federal-credit-union", None, "vendor", "T5", False, True, "other"),
    ("https://vendor-core.test/case-studies/example", None, "vendor", "T5", False, True, "other"),
    ("https://vendor-core.test/blog/example", None, "vendor", "T5", False, True, "other"),
    # unknown third party
    ("https://springfield-daily.test/2026/01/01/example", None, "other", "T3", False, False, "other"),
    # machine scans: T1 by the producer token in the name or the URL
    ("https://builtwith.com/example-fcu.test", None, "other", "T1", False, False, "other"),
    ("https://app.explorium.ai/report/1", "Explorium technographic scan", "other", "T1", False, False, "other"),
]


@pytest.mark.parametrize("url,source_name,stype,tier,wire,vc,rung", CASES,
                         ids=[c[0].split("://", 1)[1][:60] for c in CASES])
def test_classify_table(url, source_name, stype, tier, wire, vc, rung):
    got = registry.classify(url, ENTITY, source_name=source_name)
    assert (got["source_type"], got["tier"], got["is_wire"], got["is_vendor_collateral"],
            got["ladder_rung"]) == (stype, tier, wire, vc, rung), got
    assert got["tier_basis"]


def test_table_is_large_enough():
    assert len(CASES) >= 25


def test_own_domain_is_never_t1():
    for path in ("/", "/investor", "/annual-report", "/newsroom/x", "/press/x", "/financials/2025"):
        for name in (None, "BuiltWith scan", "Hubbl technographic scan"):
            assert registry.classify(f"https://example-fcu.test{path}", ENTITY, source_name=name)["tier"] != "T1"


def test_scan_basis_names_the_contract():
    got = registry.classify("https://app.explorium.ai/report/1", ENTITY, source_name="Explorium technographic scan")
    assert "contract.SCAN_TIER" in got["tier_basis"]


def test_vendor_basis_names_ceiling_and_corroboration():
    got = registry.classify("https://vendor-core.test/customers/x", ENTITY)
    assert "L2" in got["tier_basis"] and "corroboration required" in got["tier_basis"]


def test_own_press_release_basis_names_the_connector_cap():
    got = registry.classify("https://example-fcu.test/press-releases/2026/x", ENTITY)
    assert "T2" in got["tier_basis"] and "source_rules.tier_violation" in got["tier_basis"]


def test_helpers():
    assert registry.host_of("https://WWW.Example-FCU.test/x?y=1") == "example-fcu.test"
    assert registry.host_of("not a url") == ""
    assert registry.is_own_host("https://online.example-fcu.test/", ENTITY)
    assert not registry.is_own_host("https://example-fcu.test.evil.test/", ENTITY)
    assert not registry.is_own_host("https://example-fcu.test/", None)
    assert registry.regulatory_publisher("https://www.ncua.gov/x")
    assert registry.regulatory_publisher("https://ffiec.gov/x")
    assert not registry.regulatory_publisher("https://ncua.gov.example.test/x")
    assert not registry.regulatory_publisher("https://governance.test/x")
    assert registry.is_wire("https://www.prnewswire.com/x") and registry.is_wire("globenewswire.com")
    assert not registry.is_wire("https://www.reuters.com/x")


def test_unknown_entity_none_classifies_without_entity():
    got = registry.classify("https://example-fcu.test/investor", None)
    assert got["source_type"] == "other" and got["tier"] == "T3"


def test_registry_env_override(tmp_path, monkeypatch):
    p = tmp_path / "r.yaml"
    p.write_text("version: 1\ntiers: {other: T3, vendor: T5, scan: T1, regulator: T1, regulator_press: T2, "
                 "filing: T1, entity_owned_disclosure: T2, entity_owned_other: T5, news: T3}\n"
                 "news: {hosts: [only-news.test]}\n", encoding="utf-8")
    monkeypatch.setenv("EE_REGISTRY", str(p))
    assert registry.registry_path() == p
    got = registry.classify("https://only-news.test/a", None)
    assert got["source_type"] == "news"
    assert registry.classify("https://ncua.gov/a", None)["source_type"] == "other"


# ── pin to the connector's lists ─────────────────────────────────────────

_CONNECTOR = Path(__file__).resolve().parents[3] / "apps" / "mcp" / "dma_mcp" / "source_rules.py"


def _source_rules():
    if not _CONNECTOR.exists():
        pytest.skip("connector checkout not present")
    spec = importlib.util.spec_from_file_location("_dma_source_rules", _CONNECTOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_regulatory_lists_equal_the_connectors():
    sr = _source_rules()
    raw = registry.raw()
    assert tuple(raw["regulators"]["suffixes"]) == tuple(sr._REGULATORY_SUFFIX)
    assert frozenset(raw["regulators"]["hosts"]) == frozenset(sr._REGULATORY_HOST)


def test_vendor_collateral_paths_equal_the_connectors():
    sr = _source_rules()
    ours = [(e["pattern"], e["what"]) for e in registry.raw()["vendor_collateral_paths"]]
    theirs = [(p.pattern, what) for p, what in sr._VENDOR_COLLATERAL]
    assert ours == theirs


def test_scan_producers_equal_the_connectors():
    sr = _source_rules()
    raw = registry.raw()
    assert tuple(raw["scan_producers"]) == tuple(sr._SCAN_PRODUCER)
    assert tuple(raw["scan_phrases"]) == tuple(sr._SCAN_PHRASE)


def test_regulatory_publisher_agrees_with_the_connector_on_every_case():
    sr = _source_rules()
    for url, *_ in CASES:
        assert registry.regulatory_publisher(url) == sr.regulatory_publisher(url), url


def test_no_hint_the_connector_would_refuse_as_too_high():
    """Whatever the registry hints, source_rules.tier_violation must accept it."""
    sr = _source_rules()
    for url, name, *_ in CASES:
        got = registry.classify(url, ENTITY, source_name=name)
        assert sr.tier_violation(url, got["tier"]) is None, (url, got)
        assert sr.scan_tier_violation(name, got["tier"]) is None or registry.is_own_host(url, ENTITY), (url, got)
