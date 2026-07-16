"""The deploy-time Gemini enrichment prompter (services/enrichment_prompter).

Covers the dedicated prompt FORMULATOR (grounded round-1 ask + a follow-up that
names the deficiency), the sufficiency assessment, and the ITERATIVE acquisition
loop — verified with a scripted stub client (no live Vertex): a low-confidence
first answer triggers a targeted re-ask, a sourced high-confidence answer wins, a
model-confirmed absence returns found=False, and an offline/erroring client
resolves to None (the field stays honest-null).
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json

from app.services.enrichment_prompter import (
    FIELD_SPECS,
    EnrichmentGap,
    assess,
    build_unavailability_gaps,
    coerce_value,
    enrich_gap,
    formulate_prompt,
    is_due,
    parse_response,
)


def _gap() -> EnrichmentGap:
    return EnrichmentGap(
        entity_name="Kitsap Credit Union", subvertical="CU", field="headcount",
        surface="firmographics_enrichment",
        want="the total number of employees",
        unit_hint="an integer employee count",
        quality_hints=("COUNT the whole institution's staff, not one branch.",),
        known_context={"aum_usd": 2.5e9, "region": "Western WA", "founded": 1934})


class _ScriptedClient:
    """Async-streaming stand-in: yields a scripted response per round and records
    each prompt it received so the follow-up can be asserted on."""

    def __init__(self, responses: list) -> None:
        self._responses = responses
        self.prompts: list[str] = []
        self.calls = 0

    async def stream(self, call):
        self.prompts.append(call.prompt)
        r = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        if isinstance(r, Exception):
            raise r
        for i in range(0, len(r), 16):    # chunked, like real SSE
            yield r[i:i + 16]


def test_round1_prompt_conditions_model_and_carries_safeguards() -> None:
    p = formulate_prompt(_gap())
    # conditioning: role + correctness-over-completeness stance
    assert "research analyst" in p and "CORRECT over being complete" in p
    # grounded context anchored to disambiguate the entity
    assert "Kitsap Credit Union" in p and "credit union" in p
    assert "WHAT WE ALREADY KNOW" in p and "1934" in p
    # explicit safeguards the user asked for
    assert "RECENCY" in p and "MOST RECENT" in p                # most-recent-info
    assert "NO HALLUCINATION" in p and "never invent" in p      # anti-hallucination
    assert '"found": false' in p and "NEVER guess" in p         # honest-null escape
    assert "VERBATIM" in p and "SOURCE" in p                    # citation required
    # the field-specific quality hint is injected (dynamic per gap-kind)
    assert "not one branch" in p


def test_followup_prompt_names_the_deficiency() -> None:
    prior = [{"found": True, "value": "1200", "confidence": 0.4,
              "_missing": ["a source URL or a verbatim quote", "confidence >= 0.7 (was 0.4)"]}]
    p = formulate_prompt(_gap(), prior)
    assert "INSUFFICIENT" in p
    assert "source URL or a verbatim quote" in p and "confidence >= 0.7" in p
    assert "1200" in p                                            # references the prior answer


def test_assess_flags_missing_source_and_low_confidence() -> None:
    g = _gap()
    assert assess(g, {"found": True, "value": "1200", "confidence": 0.9,
                      "source_url": "https://x"}) == []
    miss = assess(g, {"found": True, "value": "", "confidence": 0.3})
    assert any("value" in m for m in miss)
    assert any("source" in m for m in miss)
    assert any("confidence" in m for m in miss)


def test_iterative_loop_reasks_then_succeeds() -> None:
    weak = json.dumps({"found": True, "value": "1200", "confidence": 0.4})
    strong = json.dumps({
        "found": True, "value": "1,200", "unit": "employees",
        "quote": "Kitsap Credit Union employs approximately 1,200 people.",
        "source_url": "https://www.kitsapcu.org/about", "source_name": "Kitsap CU",
        "published_date": "2025", "confidence": 0.86})
    client = _ScriptedClient([weak, strong])
    out = asyncio.run(enrich_gap(_gap(), client=client, max_rounds=3))
    assert out is not None and out.found and out.rounds == 2
    assert out.value == "1,200" and out.confidence == 0.86
    assert out.source_url.endswith("/about")
    # round 2 was a follow-up that named the missing source
    assert "INSUFFICIENT" in client.prompts[1]


def test_loop_returns_found_false_on_confirmed_absence() -> None:
    client = _ScriptedClient([json.dumps({"found": False})])
    out = asyncio.run(enrich_gap(_gap(), client=client, max_rounds=3))
    assert out is not None and out.found is False and out.rounds == 1


def test_loop_is_offline_safe() -> None:
    assert asyncio.run(enrich_gap(_gap(), client=None)) is None
    # erroring client → None
    assert asyncio.run(enrich_gap(
        _gap(), client=_ScriptedClient([RuntimeError("vertex cold")]))) is None
    # never produces JSON → exhausts → None (never fabricates)
    assert asyncio.run(enrich_gap(
        _gap(), client=_ScriptedClient(["OFFLINE: no creds"]), max_rounds=2)) is None


def test_parse_response_tolerates_fences_and_requires_found() -> None:
    assert parse_response('```json\n{"found": true, "value": "5"}\n```')["value"] == "5"
    assert parse_response('sure: {"found": false} .')["found"] is False
    assert parse_response('{"value": "5"}') is None            # no 'found' key
    assert parse_response("") is None


def test_coerce_value_by_kind() -> None:
    assert coerce_value("approximately 1,200", None, "int") == 1200
    assert coerce_value("999999999", None, "int") is None      # implausible headcount
    assert coerce_value("Poughkeepsie, NY", None, "str") == "Poughkeepsie, NY"
    assert coerce_value("2.5", "B", "usd") == 2.5e9
    assert coerce_value("$3.4B", None, "usd") == 3.4e9
    assert coerce_value("chartered in 1934", None, "year") == 1934
    assert coerce_value("no year here", None, "year") is None


def test_build_gaps_is_registry_driven_and_dynamic() -> None:
    # only aum populated (+ founded in parsed_facts) → the OTHER registry fields
    # are all discovered as gaps (dynamic coverage, nothing hard-coded)
    gaps = build_unavailability_gaps(
        entity_name="Acme CU", subvertical="CU",
        firmographics={"aum_usd": 1e9, "headcount": None, "hq_address": None,
                       "primary_regulator": None,
                       "parsed_facts": {"founded": 1950}})
    fields = {g.field for g in gaps}
    assert fields == {"headcount", "hq_address", "primary_regulator"}
    assert "founded_year" not in fields and "aum_usd" not in fields   # both present
    # a fully-populated entity yields NO gaps
    assert build_unavailability_gaps(
        entity_name="Acme CU", subvertical="CU",
        firmographics={"aum_usd": 1e9, "headcount": 300, "hq_address": "Reno, NV",
                       "primary_regulator": "NCUA",
                       "parsed_facts": {"founded": 1950}}) == []


def test_prompt_varies_by_field_kind() -> None:
    # each registry field produces its OWN tailored ask + quality hint
    aum = FIELD_SPECS["aum_usd"]
    g = EnrichmentGap(entity_name="X Bank", subvertical="RB", field=aum.field,
                      surface=aum.surface, want=aum.want, unit_hint=aum.unit_hint,
                      quality_hints=aum.quality_hints)
    p = formulate_prompt(g)
    assert "total assets" in p and "market-cap" in p           # aum-specific hint
    reg = FIELD_SPECS["primary_regulator"]
    g2 = EnrichmentGap(entity_name="X Bank", subvertical="RB", field=reg.field,
                       surface=reg.surface, want=reg.want, unit_hint=reg.unit_hint,
                       quality_hints=reg.quality_hints)
    p2 = formulate_prompt(g2)
    assert "prudential regulator" in p2 and p2 != p            # distinct, tailored


def test_is_due_reprobe_policy() -> None:
    now = _dt.datetime(2026, 7, 9, tzinfo=_dt.UTC)
    past = now - _dt.timedelta(hours=1)
    future = now + _dt.timedelta(hours=1)
    assert is_due(None, now) is True                            # never-seen → probe
    assert is_due({"status": "pending", "next_probe_after": None}, now) is True
    assert is_due({"status": "deferred", "next_probe_after": past}, now) is True
    assert is_due({"status": "failed", "next_probe_after": future}, now) is False   # backoff
    # resolved gaps are skipped WITHIN the 6-month window...
    recent = now - _dt.timedelta(days=30)
    assert is_due({"status": "enriched", "next_probe_after": None,
                   "last_attempt_at": recent}, now) is False
    assert is_due({"status": "absent", "next_probe_after": None,
                   "last_attempt_at": recent}, now) is False
    # ...and refreshed once 6 months (182d) have elapsed since the last attempt
    stale = now - _dt.timedelta(days=200)
    assert is_due({"status": "enriched", "next_probe_after": None,
                   "last_attempt_at": stale}, now) is True
