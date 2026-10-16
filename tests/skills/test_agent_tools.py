"""The agents that write and service the sentiment card can call the Indeed
connector's ratings read (SWBC gold audit 2026-10-04, RC-07(b); owner
decision 3).

Measured on SWBC: the Indeed connector's `get_company_data` returned 3.1/5
with a 46/97 recommend split, but no agent on the sentiment path held the
tool — only the technographic scanner held Indeed, and only `search_jobs`.
So the doctrine's "Indeed 403" was the only route anyone could take, and the
card shipped one company-reported bar.

The grant is the role table's (`scripts/provision_agent_tools.py`); these
assert the outcome on the manifests the runtime reads.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "plugins" / "dma-insights" / "agents"
TOOL = "mcp__Indeed__get_company_data"
FM = re.compile(r"^---\n(.*?)\n---\n", re.S)


def _tools(rel: str) -> set:
    text = (AGENTS / rel).read_text(encoding="utf-8")
    fm = FM.match(text).group(1)
    line = next(l for l in fm.split("\n") if l.startswith("tools:"))
    return {t.strip() for t in line[len("tools:"):].split(",") if t.strip()}


def _body(rel: str) -> str:
    text = (AGENTS / rel).read_text(encoding="utf-8")
    return text[FM.match(text).end():]


def test_the_market_producer_holds_the_indeed_ratings_read():
    assert TOOL in _tools("production/overview/overview-market-producer.md")


def test_the_connector_specialist_holds_the_indeed_ratings_read():
    assert TOOL in _tools("enrichment/enrichment-connector-specialist.md")


def test_neither_is_granted_resumes_or_job_postings_by_this():
    """The ratings read is the grant; a named person's resume is never estate
    or sentiment evidence, and job postings stay the scanner's."""
    for rel in ("production/overview/overview-market-producer.md",
                "enrichment/enrichment-connector-specialist.md"):
        t = _tools(rel)
        assert "mcp__Indeed__get_resume" not in t, rel
        assert "mcp__Indeed__search_jobs" not in t, rel


def test_both_bodies_teach_the_connector_origin_registration():
    for rel in ("production/overview/overview-market-producer.md",
                "enrichment/enrichment-connector-specialist.md"):
        body = _body(rel)
        assert "get_company_data" in body, rel
        assert "origin='connector'" in body or 'origin="connector"' in body, rel
