"""SG-S8 — sentiment resting on one line discloses and still promotes.

A single rating is not a sentiment picture. The common misreading runs the other
way, though: a thin surface read as a finding ABOUT the institution. So this
discloses rather than blocks, and it renders to the client with its plain label.

The measured case: a run promoted one bar (a self-published Member NPS of 79.81)
and the card read "not established" for every other audience, while the public
record actually carried a Glassdoor rating over ~200 reviews and an App Store
rating over 95,000. One line was not the truth; it was an unfinished search.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation2 import _run_s8  # noqa: E402


class _Conn:
    """Enough of a connection to capture the recorded gate row."""

    def __init__(self):
        self.rows = []

    def cursor(self):
        conn = self

        class _Cur:
            def execute(self, sql, params=None):
                conn.rows.append((sql, params))
        return _Cur()

    def commit(self):
        pass


def _run(page, body):
    c = _Conn()
    out = _run_s8(c, "run-1", page, {("sentiment" if page == "overview"
                                     else "context_sentiment"): body})
    return out[0] if out else None, c


def test_one_line_discloses_rather_than_blocking():
    r, conn = _run("overview", {"bars": [
        {"audience": "customer", "source": "Member NPS", "rating": 79.81}]})
    assert r["gate_id"] == "SG-S8" and r["result"] == "FAIL"
    assert r["detail"]["rated_rows"] == 1
    # It is recorded, so the client-visible disclosure has something to render.
    assert any("gate_results" in s for s, _ in conn.rows)


def test_two_independent_sources_pass():
    r, _ = _run("overview", {"bars": [
        {"audience": "employee", "source": "Glassdoor", "rating": 4.0,
         "scale": "0..5", "n": 200, "as_of": "2026-08-05"},
        {"audience": "customer", "source": "Apple App Store", "rating": 4.9,
         "scale": "0..5", "n": 95000, "as_of": "2026-08-05"}]})
    assert r["result"] == "PASS"
    assert r["detail"]["rated_rows"] == 2
    assert r["detail"]["audiences"] == ["customer", "employee"]


def test_self_published_figures_alone_are_thin_whatever_the_count():
    # Two NPS lines are still one voice about itself.
    r, _ = _run("overview", {"bars": [
        {"audience": "customer", "source": "Member NPS 2025", "rating": 79.8},
        {"audience": "customer", "source": "Member NPS 2024", "rating": 74.1}]})
    assert r["result"] == "FAIL"
    assert r["detail"]["self_published_only"] is True


def test_the_count_is_computed_not_read_from_the_payload():
    # A producer that states its own line count is the one thing this gate
    # cannot trust, so a declared displayed_lines must not change the verdict.
    r, _ = _run("overview", {"displayed_lines": 7, "bars": [
        {"audience": "customer", "source": "Member NPS", "rating": 79.81}]})
    assert r["result"] == "FAIL" and r["detail"]["rated_rows"] == 1


def test_a_searched_but_unrated_source_is_not_a_line():
    # A source with no rating belongs in the ladder, not in the count — it is
    # evidence of a search, not a measure.
    r, _ = _run("overview", {"bars": [
        {"audience": "employee", "source": "Glassdoor", "rating": 4.0,
         "scale": "0..5", "n": 200},
        {"audience": "customer", "source": "Trustpilot", "rating": None}]})
    assert r["result"] == "FAIL", "one rated row, whatever else was searched"
    assert r["detail"]["rated_rows"] == 1


def test_c4_tiles_are_counted_the_same_way():
    # O9's bars and C4's tile rows are the same dataset at two depths, so the
    # two pages cannot reach different verdicts about it.
    r, _ = _run("context", {"context_tiles": [
        {"audience": "employee", "rows": [
            {"source": "Glassdoor", "rating": 4.0, "n": 200}]},
        {"audience": "customer", "rows": [
            {"source": "Apple App Store", "rating": 4.9, "n": 95000},
            {"source": "Google Play", "rating": 4.7, "n": 12000}]}]})
    assert r["result"] == "PASS" and r["detail"]["rated_rows"] == 3


def test_no_rated_rows_records_not_run_rather_than_a_failure():
    # Nothing measured is not the same as one thing measured, and a NOT_RUN
    # carries its reason (a failing SG discloses; a NOT_RUN explains).
    r, _ = _run("overview", {"bars": []})
    assert r["result"] == "NOT_RUN" and r["not_run_reason"] == "no rated rows"


def test_a_page_without_a_sentiment_section_is_untouched():
    c = _Conn()
    assert _run_s8(c, "run-1", "heatmap", {"alerts": {"alerts": []}}) == []
    assert c.rows == []
