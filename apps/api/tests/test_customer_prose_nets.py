"""The customer-body prose nets added 2026-10-02 after the SWBC redaction
audit (c and d — whole-section withholding and dict-valued allowlisting —
are in test_customer_section_shapes.py).

  b. seller vocabulary: "account team" and the executive's spelled-out and
     abbreviated forms;
  f. our pipeline's vocabulary in prose — NOT_RUN, connector credits, the
     enrichment/search tool names, RRF / k=60 / engine v2 / hot band.

Each net is a BACKSTOP: producers are fixing the prose too. Each one is
tested against the words a client legitimately reads, because a net that
fires on ordinary English teaches producers to fight it.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api.redaction import (SELLER_VOCABULARY,  # noqa: E402
                               internal_vocabulary, redact_empty_state,
                               redact_section)


# ── b. seller vocabulary ──────────────────────────────────────────────
@pytest.mark.parametrize("text", [
    "a question for the account team to raise",
    "The Account Team should confirm the renewal date.",
    "shared with the account-team before the review",
    "the account executive's notes",
    "brief the account-executive",
    "the account exec will follow up",
    "two account teams covered the region",
])
def test_seller_phrases_are_caught(text):
    assert SELLER_VOCABULARY.search(text), text


@pytest.mark.parametrize("text", [
    "the institution is accountable for its data lineage",
    "take into account the regulatory timeline",
    "the account opening journey is fully digital",
    "the operations team owns the platform",
    "accountability for model risk sits with the board",
    "team-based account servicing for commercial clients",
])
def test_ordinary_words_do_not_false_positive(text):
    assert not SELLER_VOCABULARY.search(text), text


def test_a_section_field_written_to_the_account_team_is_stripped():
    data = {"platforms": [{"rank": 1, "platform": "Core migration",
                           "story_md": "Worth raising with the account "
                                       "team."}]}
    out, report = redact_section("platform", "platform_story", data, [],
                                 "customer")
    assert "account team" not in json.dumps(out)
    assert report["seller_voice"]


# ── f. pipeline vocabulary in prose ───────────────────────────────────
@pytest.mark.parametrize("text,term", [
    ("The leadership pass was NOT_RUN for budget reasons.", "NOT_RUN"),
    ("Deferred until connector credits are restored.", "connector credit"),
    ("Clay returned no match for the CFO.", "Clay"),
    ("Enriched via Clay.com and the registry.", "Clay"),
    ("Explorium found 2,300 employees.", "Explorium"),
    ("Exa surfaced three press releases.", "Exa"),
    ("A Tavily search found nothing newer.", "Tavily"),
    ("Pages fetched with Firecrawl.", "Firecrawl"),
    ("Ranked by RRF across both retrievers.", "RRF"),
    ("fused at k=60 before review", "k=60"),
    ("scored under engine v2", "engine v2"),
    ("this cell sits in the hot band", "hot band"),
])
def test_pipeline_terms_in_prose_are_caught(text, term):
    assert internal_vocabulary(text) == term


@pytest.mark.parametrize("text", [
    "NOT_RUN",                                   # a bare status token
    "Clay Thompson, Chief Financial Officer",    # a person
    "the clay-tile roofing subsidiary",
    "exactly three examples were found",
    "the exam schedule for licensed producers",
    "the band's upper limit",
    "a hot market for commercial lines",
    "the engine of growth in version two of the plan",
    "k = 6 regional offices",
    "the connector between the two systems",
])
def test_ordinary_text_is_not_caught(text):
    assert internal_vocabulary(text) is None, text


def test_the_field_goes_whole_and_the_receipt_names_the_term():
    data = {"platforms": [{"rank": 1, "platform": "Data platform",
                           "story_md": "Explorium and Clay both returned "
                                       "the headcount."}]}
    out, report = redact_section("platform", "platform_story", data, [],
                                 "customer")
    assert "story_md" not in out["platforms"][0]
    assert out["platforms"][0]["platform"] == "Data platform"
    assert any("(Clay)" in p for p in report["internal_vocabulary"])


def test_a_safeguard_gate_keeps_its_designed_NOT_RUN():
    """Invariant 12: an SG renders to the client with an explicit NOT_RUN
    and its reason. The status token and the reason both stay."""
    data = {"gates": [{"gate_id": "SG-V4", "result": "NOT_RUN",
                       "plain_label": "Grounding check on cited evidence "
                                      "against the run's own centroid",
                       "not_run_reason": "NOT_RUN: the centroid has fewer "
                                         "than five members, so the check "
                                         "abstains."}]}
    out, report = redact_section("heatmap", "safeguard_gates", data, [],
                                 "customer")
    gate = out["gates"][0]
    assert gate["result"] == "NOT_RUN"
    assert gate["not_run_reason"].startswith("NOT_RUN")
    assert not report["internal_vocabulary"]


def test_the_empty_state_runs_the_net_too():
    out, dropped = redact_empty_state(
        {"kind": "held", "reason": "Deferred: connector credits exhausted.",
         "closure_condition": "re-run when budget allows"}, "customer")
    assert "reason" not in out
    assert any("connector credit" in d for d in dropped)


def test_internal_prose_is_untouched_internally():
    data = {"platforms": [{"rank": 1, "story_md": "Ranked by RRF at k=60."}]}
    out, _ = redact_section("platform", "platform_story", data, [],
                            "internal")
    assert out["platforms"][0]["story_md"] == "Ranked by RRF at k=60."
