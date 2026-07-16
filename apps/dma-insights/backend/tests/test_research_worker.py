"""Pure-logic tests for the deep-research crawler (research_worker).

No network: the search parser is fed captured DDG-lite HTML shapes and
the sentence extractor is fed a reduced fixture of the real Synchrony
newsroom page that exposed the two precision bugs this worker was
calibrated against (nav-carousel junk outranking the event sentence;
founding dates masquerading as event dates).
"""
from __future__ import annotations

import json

import pytest

from app.scripts import research_worker as rw

# The lite provider's real anchor shape: protocol-relative redirect
# links with the target URL-encoded in ?uddg=.
_LITE_HTML = (
    '<html><body><table>'
    '<a rel="nofollow" href="//duckduckgo.com/l/?uddg='
    'https%3A%2F%2Fwww.synchrony.com%2Fnewsroom%2Fversatile.html'
    '&amp;rut=abc123">Synchrony Acquires <b>Versatile Credit</b></a>'
    '<a rel="nofollow" href="//duckduckgo.com/l/?uddg='
    'https%3A%2F%2Finvestors.synchrony.com%2Fdetail%2F542'
    '&amp;rut=def456">Versatile Credit — Investor News</a>'
    '<a rel="nofollow" href="//duckduckgo.com/l/?uddg='
    'https%3A%2F%2Fwww.synchrony.com%2Fother-page.html'
    '&amp;rut=ghi789">Second hit on the same domain</a>'
    '</table></body></html>'
)

_EVENT_SENT = (
    "— October 1, 2025 – Synchrony (NYSE: SYF), a leading "  # noqa: RUF001 — verbatim from the source page
    "consumer financing company, acquired Versatile Credit, a "
    "consumer-financing software provider connecting merchants."
)
_JUNK_SENT = (
    "More Video 02/11/2015 Synchrony Financial: 2014 Customer "
    "Testimonials Hear what customers have to say about the value "
    "of store credit & financing."
)
_FOUNDING_SENT = (
    "San Francisco-based EarnUp started in 2013 with a mission to "
    "build a financial system that works for everybody."
)


def test_search_parses_protocol_relative_uddg_links(monkeypatch):
    monkeypatch.setattr(rw, "_http_get", lambda url, **kw: _LITE_HTML)
    results = rw._search("synchrony versatile credit")
    urls = [u for u, _ in results]
    assert "https://www.synchrony.com/newsroom/versatile.html" in urls
    assert "https://investors.synchrony.com/detail/542" in urls
    # per-domain dedup: the second www.synchrony.com hit is dropped
    assert len([u for u in urls if "www.synchrony.com" in u]) == 1
    # titles decoded and tag-stripped
    assert results[0][1] == "Synchrony Acquires Versatile Credit"


def test_search_distinguishes_provider_down_from_no_results(monkeypatch):
    monkeypatch.setattr(rw, "_http_get", lambda url, **kw: None)
    assert rw._search("anything") is None
    monkeypatch.setattr(rw, "_http_get",
                        lambda url, **kw: "<html>no anchors</html>")
    assert rw._search("anything") == []


def test_event_sentence_outranks_nav_junk():
    page = f"<p>{_EVENT_SENT}</p><div>{_JUNK_SENT}</div>"
    subject = rw._terms("Acquired Versatile Credit Inc for POS financing")
    entity = rw._terms("synchrony financial") - subject
    got = rw._candidate_sentences(page, subject, entity, want_date=True)
    assert got, "the dated event sentence must be extracted"
    assert "Versatile" in got[0][1]
    if len(got) > 1:
        assert got[0][0] > got[1][0]


def test_rich_subject_requires_two_subject_hits():
    # 'EarnUp' alone + a founding year must NOT qualify as an event
    # date for a ≥4-term subject.
    page = f"<p>{_FOUNDING_SENT}</p>"
    subject = rw._terms("EarnUp AI acquisition undisclosed represents")
    entity = rw._terms("becu") - subject
    assert rw._candidate_sentences(page, subject, entity,
                                   want_date=True) == []


def test_g3_path_skips_date_gate():
    page = f"<p>{_FOUNDING_SENT}</p>"
    subject = rw._terms("EarnUp financial system")
    entity = rw._terms("becu") - subject
    got = rw._candidate_sentences(page, subject, entity, want_date=False)
    assert got and "EarnUp" in got[0][1]


def test_run_marks_row_and_writes_cited_answer(tmp_path, monkeypatch):
    queue = tmp_path / "q.jsonl"
    answers = tmp_path / "a.jsonl"
    queue.write_text(json.dumps({
        "key": "k1", "entity": "synchrony-financial-0001",
        "surface": "timeline", "ground": "G2", "status": "open",
        "question": ("Real event date needed for timeline event "
                     "'Acquired Versatile Credit Inc for POS financing "
                     "digital…' — no textual date"),
    }) + "\n")
    monkeypatch.setattr(
        rw, "_search",
        lambda q: [("https://www.synchrony.com/newsroom/v.html", "T")])
    monkeypatch.setattr(
        rw, "_http_get", lambda url, **kw: f"<p>{_EVENT_SENT}</p>")
    monkeypatch.setattr(rw.time, "sleep", lambda s: None)
    rep = rw.run(str(queue), str(answers), max_rows=5,
                 grounds={"G2"}, dry_run=False)
    assert rep["answered"] == 1
    row = json.loads(answers.read_text().splitlines()[0])
    assert row["status"] == "pending_review"
    assert row["confidence"] == "candidate"
    src = row["sources"][0]
    assert src["url"].startswith("https://")
    assert "October 1, 2025" in src["excerpt"]
    assert src["retrieved_at"]
    qrow = json.loads(queue.read_text().splitlines()[0])
    assert qrow["status"] == "answered_pending_review"


def test_run_dry_run_touches_nothing(tmp_path, monkeypatch):
    queue = tmp_path / "q.jsonl"
    answers = tmp_path / "a.jsonl"
    queue.write_text(json.dumps({
        "key": "k1", "entity": "synchrony-financial-0001",
        "surface": "timeline", "ground": "G2", "status": "open",
        "question": "Real event date needed for timeline event 'Acquired "
                    "Versatile Credit Inc for POS financing'",
    }) + "\n")
    before = queue.read_text()
    monkeypatch.setattr(
        rw, "_search",
        lambda q: [("https://www.synchrony.com/newsroom/v.html", "T")])
    monkeypatch.setattr(
        rw, "_http_get", lambda url, **kw: f"<p>{_EVENT_SENT}</p>")
    monkeypatch.setattr(rw.time, "sleep", lambda s: None)
    rep = rw.run(str(queue), str(answers), max_rows=5,
                 grounds={"G2"}, dry_run=True)
    assert rep["answered"] == 1
    assert not answers.exists()
    assert queue.read_text() == before


def test_stub_subject_refused_unless_context_fills_it(tmp_path, monkeypatch):
    # 'AssuredPartners (#10) agreed' — one non-entity term; answering
    # would match ANY agreement the entity ever made (observed live:
    # a discovery stipulation in an unrelated lawsuit).
    queue = tmp_path / "q.jsonl"
    row = {"key": "k1", "entity": "assuredpartners-0001",
           "surface": "timeline", "ground": "G2", "status": "open",
           "question": ("Real event date needed for timeline event "
                        "'AssuredPartners (#10) agreed' — no textual date")}
    queue.write_text(json.dumps(row) + "\n")
    searched: list[str] = []
    monkeypatch.setattr(rw, "_search",
                        lambda q: searched.append(q) or [])
    monkeypatch.setattr(rw.time, "sleep", lambda s: None)
    rep = rw.run(str(queue), str(tmp_path / "a.jsonl"), max_rows=5,
                 grounds={"G2"}, dry_run=False)
    assert rep["underspecified"] == 1
    assert searched == []          # no query fired at all
    assert json.loads(queue.read_text())["status"] == "open"
    # the same stub WITH filed context gets researched, with the
    # context terms in the query
    row["context"] = "agreed to acquire Accession Risk Management Group"
    queue.write_text(json.dumps(row) + "\n")
    rep = rw.run(str(queue), str(tmp_path / "a.jsonl"), max_rows=5,
                 grounds={"G2"}, dry_run=False)
    assert rep["underspecified"] == 0
    assert searched and "Accession" in searched[0]


def test_provider_down_leaves_row_open(tmp_path, monkeypatch):
    queue = tmp_path / "q.jsonl"
    queue.write_text(json.dumps({
        "key": "k1", "entity": "e-0001", "surface": "timeline",
        "ground": "G2", "status": "open",
        "question": "Real event date needed for timeline event "
                    "'Zelle instant payments launch'",
    }) + "\n")
    monkeypatch.setattr(rw, "_search", lambda q: None)
    monkeypatch.setattr(rw.time, "sleep", lambda s: None)
    rep = rw.run(str(queue), str(tmp_path / "a.jsonl"), max_rows=5,
                 grounds={"G2"}, dry_run=False)
    assert rep["provider_unavailable"] == 1
    assert json.loads(queue.read_text())["status"] == "open"


def test_nav_debris_gate() -> None:
    assert rw.is_nav_debris("Yes Subscribe to see more Subscribe to see more "
                            "Subscribe to see more Subscribe to see more")
    assert rw.is_nav_debris("Accept all cookies to continue reading this")
    assert rw.is_nav_debris("")
    assert not rw.is_nav_debris(
        "Synchrony completed its acquisition of Ally Lending, the point of "
        "sale financing business, on March 4, 2024.")


def test_router_filed_surfaces_get_query_plans() -> None:
    for surface, ctx, expect in (
        ("firmographics", "founded", "founded"),
        ("firmographics", "hq_address", "headquarters"),
        ("leadership", None, "CEO"),
        ("timeline", "timeline_empty", "announcement"),
        ("tech_stack", "stack_entries=1", "technology"),
        ("focus_kpi", "fa-uuid", "investor"),
    ):
        plan = rw._plan_for(
            {"surface": surface, "context": ctx,
             "filed_by": "route_empty_surfaces",
             "question": "generic census question"},
            "acme credit union", "generic census question")
        assert plan is not None, surface
        assert any(expect.lower() in v.lower() for v in plan["variants"]), surface
    # timeline plans demand a dated sentence; identity facts don't
    assert rw._plan_for({"surface": "timeline", "context": None,
                         "filed_by": "route_empty_surfaces",
                         "question": "q"}, "acme", "q")["want_date"] is True


def test_composer_filed_specific_rows_stay_question_driven() -> None:
    assert rw._plan_for(
        {"surface": "timeline", "filed_by": "deepen_narrative",
         "question": "Real event date needed for timeline event 'X launch'"},
        "acme", "X launch") is None
    assert rw._plan_for(
        {"surface": "finding", "filed_by": "route_empty_surfaces",
         "question": "q"}, "acme", "q") is None
    # focus_area sweeps regardless of filer (the multi-source directive)
    assert rw._plan_for(
        {"surface": "focus_area", "filed_by": "deepen_narrative",
         "question": "q"}, "acme", "q") is not None


def test_promoter_strict_date_parse() -> None:
    import datetime as dt

    from app.scripts.promote_research_answers import parse_strict_date
    assert parse_strict_date(
        "today announced it completed its acquisition on March 4, 2024 in "
        "a deal") == dt.date(2024, 3, 4)
    assert parse_strict_date("dated 4 March 2024 by the parties") == \
        dt.date(2024, 3, 4)
    assert parse_strict_date("effective 2024-03-04 per the filing") == \
        dt.date(2024, 3, 4)
    assert parse_strict_date("Sept. 9, 2025 announcement") == \
        dt.date(2025, 9, 9)
    # bare years / quarters NEVER date evidence
    assert parse_strict_date("founded in 2024") is None
    assert parse_strict_date("in Q3 2024 results") is None
    assert parse_strict_date("1, 2025 /PRNewswire/ -- Synchrony") is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
