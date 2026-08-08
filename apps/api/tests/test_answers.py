"""The grounded answer path (migration 0026 + dma_api/answers.py).

The defect these tests pin is the one the panel shipped with: a question box
that accepts input and does nothing, because the only way anyone had thought
to answer a question was to run a model, and the serving path may not. So the
tests are mostly about what the answer path is NOT allowed to do — invent a
sentence, quote something a producer never wrote, or return a passage that
merely shares a word with the question.

No database. The walker, the registry, the ranking and the assembly are all
pure over promoted page bodies, which is the same discipline as
test_serving_read_path and test_value_chain: drive the real functions with
the exact shapes the read path produces.
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api import answers as A                                # noqa: E402

RUN = {"run_id": "11111111-1111-1111-1111-111111111111",
       "promoted_at": "2026-08-05T04:00:00+00:00"}
ENTITY = {"display_id": "baxter-credit-union-bcu", "entity_name": "Baxter"}

SITUATION = ("A credit union with 370,000 members runs three member-facing "
             "channels on two unreconciled member records.")
COMPLICATION = ("The data layer trails the strategy layer by a full band, so "
                "every channel investment lands on plumbing that cannot "
                "carry it.")
ANSWER = ("Fix the member-data foundation first, then consolidate servicing "
          "on top of it, and hold the agentic work until both are true.")
FRAMING = ("Strategy governance runs ahead of the credit-union peer set "
           "while the data layer trails it, and the gap concentrates in "
           "member identity resolution.")


def page(name, sections):
    return {"entity": ENTITY, "run": RUN, "audience": "internal",
            "page": name, "sections": sections}


def section(data, e_ids=()):
    return {"data": data, "data_source": "producer", "provenance": "producer",
            "produced_at": RUN["promoted_at"], "producer_version": "test@1",
            "e_ids": list(e_ids), "empty_state": None}


def pages_fixture():
    return {
        "overview": page("overview", {
            "exec_summary": section(
                {"situation": SITUATION, "complication": COMPLICATION,
                 "answer": ANSWER, "claim_label": "FACT"},
                ["E-BCU-061", "E-BCU-066"]),
            "scores": section({"framing": FRAMING, "composite": 2.31},
                              ["E-BCU-001"]),
            "findings": section(
                {"findings": [
                    {"statement": ("Member identity is resolved in three "
                                   "systems and reconciled in none of them."),
                     "e_ids": ["E-BCU-070"]}]},
                ["E-BCU-070"]),
        }),
        "heatmap": page("heatmap", {
            "cell_evidence": section(
                {"cells": [
                    {"subcap_id": "P4C1.1.2",
                     "synthesis": ("The unified member profile exists as a "
                                   "reporting view, not as an operational "
                                   "record any channel can write to."),
                     "e_ids": ["E-BCU-088"]}]},
                ["E-BCU-088"]),
        }),
        "insights": page("insights", {}),
        "platform": page("platform", {
            "platform_story": section(
                {"platforms": [
                    {"story_md": ("The integration backbone is the first "
                                  "move because every later capability reads "
                                  "the member record through it."),
                     "gaps": [{"subcap_id": "P4C1.1.2",
                               "peer_note": ("Two comparable credit unions "
                                             "closed this cell within a year "
                                             "of a core migration."),
                               "e_ids": ["E-BCU-091"]}]}]},
                ["E-BCU-090"]),
        }),
    }


class _Cur:
    """Enough cursor to drive the two database touches: the table probe and
    the producer-authored answer read."""

    def __init__(self, tables=(), rows=()):
        self.tables = set(tables)
        self.rows = list(rows)
        self.queries: list = []
        self._out: list = []
        self._one = None

    def execute(self, sql, params=None):
        self.queries.append((" ".join(sql.split()), params))
        if "to_regclass" in sql:
            self._one = (params[0] if params[0] in self.tables else None,)
        elif "FROM serving_answers" in sql:
            self._out = self.rows
        elif "FROM serving_passages" in sql:
            self._out = []
        else:                                            # pragma: no cover
            raise AssertionError(sql)

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._out

    def sql_for(self, fragment):
        for sql, _params in self.queries:
            if fragment in sql:
                return sql
        raise AssertionError(f"no query touched {fragment}")  # pragma: no cover


# ── the passage walker ───────────────────────────────────────────────────
def test_prose_is_recognised_by_length_and_words_not_by_field_name():
    """A curated field list goes stale the moment a section gains a field;
    the rule is a property of the string, so a new promoted paragraph joins
    the corpus without anyone remembering to add it."""
    found = A.walk_passages("overview", "exec_summary",
                            {"situation": SITUATION, "claim_label": "FACT",
                             "composite": 2.31})
    assert [p["text"] for p in found] == [SITUATION]


def test_identifiers_and_dates_never_enter_the_corpus_however_long():
    long_id = "P4C1.1.2 · P4C1.1.3 · P4C1.2.1 · P4C1.2.2 · P4C1.3.1 · P4C1.3.2"
    found = A.walk_passages("heatmap", "cell_evidence",
                            {"subcap_id": long_id, "source_url": long_id,
                             "produced_at": long_id})
    assert found == []


def test_the_producers_own_working_record_is_not_an_answer():
    """`r_layer` is the recorded reasoning behind a ranked claim and
    `sources_searched` is the trail behind an absence. Both are load-bearing
    for audit; neither is what an AE asked for, and cell for cell they
    outnumber the prose that is."""
    data = {"synthesis": SITUATION,
            "r_layer": {"hypothesis": FRAMING, "probes_run": [COMPLICATION]},
            "sources_searched": [COMPLICATION]}
    found = A.walk_passages("heatmap", "cell_evidence", data)
    assert [p["text"] for p in found] == [SITUATION]


def test_a_paragraph_inherits_the_citations_of_the_row_it_came_from():
    """`overview.scores` cites two ids for the whole section and its framing
    paragraph states none of its own. Inheritance is not a guess: the ids are
    the ones promote wrote for the row this text is part of."""
    found = A.walk_passages("overview", "scores", {"framing": FRAMING},
                            ["E-BCU-001", "E-BCU-002"])
    assert found[0]["e_ids"] == ["E-BCU-001", "E-BCU-002"]


def test_an_item_that_states_its_own_citations_keeps_them():
    data = {"cells": [{"subcap_id": "P4C1.1.2", "synthesis": SITUATION,
                       "e_ids": ["E-BCU-088"]}]}
    found = A.walk_passages("heatmap", "cell_evidence", data, ["E-BCU-001"])
    assert found[0]["e_ids"] == ["E-BCU-088"]
    assert (found[0]["anchor_kind"], found[0]["anchor_id"]) == (
        "subcap", "P4C1.1.2")


def test_a_list_of_objects_is_never_mistaken_for_a_citation_list():
    """The adapted entity carries `evidence` as a list of OBJECTS at the top
    level and as a list of ids on a card. Only the second is a citation
    list, and the difference is checked rather than assumed."""
    data = {"evidence": [{"e_id": "E-1", "excerpt": SITUATION}],
            "note": COMPLICATION}
    found = {p["json_path"]: p for p in A.walk_passages("x", "y", data,
                                                        ["E-SEC"])}
    assert found["note"]["e_ids"] == ["E-SEC"]


def test_the_walk_is_stable_so_ties_break_the_same_way_twice():
    data = pages_fixture()["overview"]["sections"]["exec_summary"]["data"]
    once = [p["json_path"] for p in A.walk_passages("overview", "e", data)]
    twice = [p["json_path"] for p in A.walk_passages("overview", "e", data)]
    assert once == twice and len(once) == 3


def test_passages_come_from_the_already_redacted_page():
    """Building the corpus from the page RESPONSE rather than from serving
    rows is what makes audience redaction survive this feature: a path
    deleted for the customer audience is not in the corpus to be retrieved."""
    body = page("overview", {"exec_summary": section({"situation": SITUATION})})
    assert [p["text"] for p in A.passages_from_page(body)] == [SITUATION]
    body["sections"]["exec_summary"]["data"] = None       # withheld
    assert A.passages_from_page(body) == []


# ── the pre-computed answer set ──────────────────────────────────────────
def test_a_starter_question_resolves_to_promoted_prose_with_its_citations():
    cur = _Cur()
    out = A.answers_from_pages(cur, pages_fixture(), "internal")
    got = {a["q_id"]: a for a in out["answers"]}
    thirty = got["Q-ENT-01"]
    assert thirty["provenance"] == "selected"
    assert [p["text"] for p in thirty["parts"]] == [SITUATION, COMPLICATION,
                                                    ANSWER]
    assert thirty["e_ids"] == ["E-BCU-061", "E-BCU-066"]
    assert all(p["page"] == "overview" and p["section"] == "exec_summary"
               for p in thirty["parts"])


def test_every_answered_question_carries_at_least_one_citation():
    """An answer is the surface most likely to be pasted into an email
    without its page around it. Uncited prose under a client's name is the
    failure this application exists to prevent."""
    out = A.answers_from_pages(_Cur(), pages_fixture(), "internal")
    for a in out["answers"]:
        if a["parts"]:
            assert a["e_ids"], a["q_id"]


def test_parts_are_never_joined_into_one_string():
    """Three promoted paragraphs shown one after another are three
    quotations; the same three concatenated are a sentence nobody wrote."""
    out = A.answers_from_pages(_Cur(), pages_fixture(), "internal")
    for a in out["answers"]:
        for part in a["parts"]:
            assert isinstance(part["text"], str)
            assert part["path"] and part["section"]
        assert "answer_text" not in a and "body" not in a


def test_a_question_the_run_cannot_ground_is_returned_as_an_absence():
    """Dropped questions are worse than absent ones: the reader cannot ask
    for the slow path on a question they were never shown."""
    thin = {"overview": page("overview", {"scores": section({"framing": FRAMING},
                                                            ["E-1"])})}
    out = A.answers_from_pages(_Cur(), thin, "internal")
    absent = [a for a in out["answers"] if a["provenance"] == "absent"]
    assert absent, "an unanswerable question must still be listed"
    for a in absent:
        assert a["parts"] == [] and a["absence"]["reason"]


def test_counts_are_computed_from_the_list_that_was_built():
    out = A.answers_from_pages(_Cur(), pages_fixture(), "internal")
    assert out["count"] == len(out["answers"])
    assert out["answered"] == len([a for a in out["answers"] if a["parts"]])


def test_the_producers_own_answer_wins_over_selection():
    """Selection is a fallback for runs that promoted before anyone wrote
    answers. Where a producer answered the question with the whole package in
    view, that answer serves and the selected one is not also emitted."""
    row = ("Q-ENT-01", "entity", None,
           "What is the 30-second version of this assessment?", 1,
           "Two records, three channels, one decision.", None,
           "overview", "exec_summary", "answer", ["E-BCU-061"])
    cur = _Cur(tables=["serving_answers"], rows=[row])
    out = A.answers_from_pages(cur, pages_fixture(), "internal")
    hits = [a for a in out["answers"] if a["q_id"] == "Q-ENT-01"]
    assert len(hits) == 1
    assert hits[0]["provenance"] == "promoted"
    assert hits[0]["parts"][0]["text"] == "Two records, three channels, one decision."


def test_the_customer_audience_never_reads_an_internal_answer_row():
    cur = _Cur(tables=["serving_answers"])
    A.answers_from_pages(cur, pages_fixture(), "customer")
    assert "internal_only = false" in cur.sql_for("FROM serving_answers")


def test_the_customer_never_retrieves_a_withheld_section_or_page():
    """Two different withholdings, and only one is a marked path.
    `internal_only` is the producer's per-path marking; CUSTOMER_WITHHELD and
    CUSTOMER_WITHHELD_PAGES withhold whole sections and whole pages whatever
    the payload said. The passage index stores every section the run
    promoted, so the marking alone would hand a customer exactly the surfaces
    the page endpoint refuses them."""
    cur = _Cur(tables=["serving_passages"])
    A._passages_from_table(cur, RUN["run_id"], "customer", "member data", 5)
    sql = cur.sql_for("FROM serving_passages")
    assert "internal_only = false" in sql
    assert "page <> %s" in sql, "a withheld PAGE must not be retrievable"
    assert "NOT (page = %s AND section = %s)" in sql
    # and the parameters line up with the placeholders, in order
    params = next(p for q, p in cur.queries if "FROM serving_passages" in q)
    assert params[0] == "member data" and params[1] == "member data"
    assert params[2] == RUN["run_id"]
    assert "context" in params, "the customer-withheld page is bound"


def test_the_internal_audience_reads_the_whole_index():
    cur = _Cur(tables=["serving_passages"])
    A._passages_from_table(cur, RUN["run_id"], "internal", "member data", 5)
    sql = cur.sql_for("FROM serving_passages")
    assert "internal_only" not in sql and "page <> " not in sql


def test_the_answer_set_survives_a_missing_table_before_the_migration():
    """Expand–migrate–contract: the endpoint answers before 0026 is applied
    and after, with no deploy order between them."""
    out = A.answers_from_pages(_Cur(tables=[]), pages_fixture(), "internal")
    assert out["answered"] >= 1


# ── deterministic retrieval ──────────────────────────────────────────────
def test_a_passage_that_shares_one_word_is_not_an_answer():
    """Returning it under 'here is what this run states about that' would be
    the same fabrication the frame exists to avoid."""
    corpus = [{"text": "The member record is written by two systems."}]
    assert A.rank_passages("what does the integration backbone unlock for "
                           "agentic servicing", corpus) == []


def test_retrieval_returns_the_run_s_own_sentence_verbatim():
    corpus = A.passages_from_page(pages_fixture()["platform"])
    ranked = A.rank_passages("integration backbone member record", corpus)
    assert ranked, "the run states this"
    score, top = ranked[0]
    assert top["text"] in [p["text"] for p in corpus]
    assert 0 < score <= 1


def test_ranking_is_deterministic_over_the_same_corpus():
    corpus = []
    for body in pages_fixture().values():
        corpus += A.passages_from_page(body)
    a = A.rank_passages("member profile channel", corpus, limit=5)
    b = A.rank_passages("member profile channel", corpus, limit=5)
    assert [p["json_path"] for _s, p in a] == [p["json_path"] for _s, p in b]


def test_a_question_of_only_stopwords_matches_nothing():
    corpus = [{"text": SITUATION}]
    assert A.rank_passages("what is it about", corpus) == []


def test_the_floor_is_a_share_of_the_question_not_a_raw_hit_count():
    corpus = [{"text": "Member identity resolution is unfinished."}]
    assert A.rank_passages("member identity", corpus)
    assert A.rank_passages(
        "member identity governance roadmap funding sequencing", corpus) == []


def test_search_answers_prefers_the_precomputed_set(monkeypatch):
    monkeypatch.setattr(A, "_load_pages",
                        lambda *a, **k: pages_fixture())
    out = A.search_answers(_Cur(), "baxter-credit-union-bcu",
                           "What is the 30-second version of this assessment?")
    assert out["result"] == "answer"
    assert out["answer"]["parts"][0]["text"] == SITUATION


def test_search_answers_falls_through_to_verbatim_passages(monkeypatch):
    monkeypatch.setattr(A, "_load_pages", lambda *a, **k: pages_fixture())
    out = A.search_answers(_Cur(), "baxter-credit-union-bcu",
                           "integration backbone member record")
    assert out["result"] == "passages"
    assert out["frame"] == "here is what this run states about that"
    assert out["count"] == len(out["passages"])
    assert all(p["e_ids"] for p in out["passages"])


def test_search_answers_says_nothing_rather_than_something(monkeypatch):
    monkeypatch.setattr(A, "_load_pages", lambda *a, **k: pages_fixture())
    out = A.search_answers(_Cur(), "baxter-credit-union-bcu",
                           "what is their pricing for commercial deposits")
    assert out["result"] == "no_match"
    assert out["next"]["queue_for_synthesis"]["available"] is False
    assert out["next"]["queue_for_synthesis"]["reason"]


def test_an_empty_question_is_refused_rather_than_answered(monkeypatch):
    monkeypatch.setattr(A, "_load_pages", lambda *a, **k: pages_fixture())
    with pytest.raises(A.ApiError):
        A.search_answers(_Cur(), "baxter-credit-union-bcu", "   ")


# ── the two copies of one registry ───────────────────────────────────────
def test_the_panel_and_the_api_ask_the_same_questions():
    """The panel resolves a starter question without a round trip, so it
    carries the question list too. Two copies of one list is exactly the
    drift this codebase keeps shipping (writer_spec, contracts), so the
    divergence is a test failure rather than a difference of opinion between
    two tiers about what an AE asked."""
    src = (ROOT / "apps" / "web" / "proto" / "drawers.jsx").read_text()
    block = re.search(r"const IP_QUESTIONS = \[(.*?)\n\];", src, re.S)
    assert block, "drawers.jsx no longer declares IP_QUESTIONS"
    panel = set(re.findall(r'q_id:\s*"([^"]+)"', block.group(1)))
    api = {q["q_id"] for q in A.QUESTIONS}
    assert panel == api, (
        f"only in the panel: {sorted(panel - api)} · "
        f"only in the API: {sorted(api - panel)}")
    for q in A.QUESTIONS:
        assert f'question: "{q["question"]}"' in block.group(1), q["q_id"]


def test_every_registry_source_names_a_page_the_answer_set_loads():
    for q in A.QUESTIONS:
        for page_name, _section, _path in q["sources"]:
            assert page_name in A._ANSWER_PAGES, q["q_id"]


def test_wildcards_walk_lists_and_a_dead_path_yields_nothing():
    data = {"recommendations": [{"prerequisites": [{"condition": SITUATION}]},
                                {"prerequisites": []}]}
    assert A._pluck(data, "recommendations[*].prerequisites[*].condition") == [
        SITUATION]
    assert A._pluck(data, "recommendations[*].nope") == []
    assert A._pluck(data, "missing.entirely") == []
