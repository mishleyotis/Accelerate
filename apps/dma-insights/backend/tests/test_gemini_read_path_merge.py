"""Gemini read-path merge + thought-leadership validator contracts
(2026-07-02, master plan Part 3.2/3.3 — RC1 fix).

Pure-logic (no DB, no FastAPI): the router fetches rows; the policy
lives in `services/overview_gemini_merge.merge_gemini_overview` and is
exercised here with faked `vertex_synthesis_cache` / `ai_enrichments`
row dicts. The thought-leadership acceptance validator
(`enrich_corpus._accept_tl_items`) mirrors the firmographics
verbatim-quote gate and is pinned with adversarial fixtures.
"""
from __future__ import annotations

from datetime import UTC, datetime

from app.scripts.enrich_corpus import _accept_tl_items
from app.services.overview_gemini_merge import merge_gemini_overview

_NOW = datetime(2026, 7, 2, 12, 0, 0, tzinfo=UTC)


def _wn_row(**over):
    base = {
        "surface": "why_now",
        "output_text": "Core migration closes Q3; peers already moved.",
        "output_json": {
            "source": "vertex",
            "model_id": "gemini-2.5-flash",
            "synthesized_at": "2026-07-02T11:00:00+00:00",
        },
        "model": "flash",
        "created_at": _NOW,
        "cited_evidence_ids": ["E-101", "E-104"],
        "validators_passed": True,
    }
    base.update(over)
    return base


# ── why_now uplift ───────────────────────────────────────────────────────────

def test_why_now_uplift_prepended_with_vertex_provenance():
    det = [{"kind": "M&A", "text": "Acquired X", "evidence": ["E-1"],
            "derived_from": "timeline_events"}]
    signals, _ = merge_gemini_overview(
        why_now_signals=det, firmographics=None, parsed_facts={},
        cache_rows=[_wn_row()],
    )
    assert len(signals) == 2
    uplift = signals[0]
    assert uplift["source"] == "vertex"
    assert uplift["derived_from"] == "vertex"
    assert uplift["model_id"] == "gemini-2.5-flash"
    assert uplift["synthesized_at"] == "2026-07-02T11:00:00+00:00"
    assert uplift["evidence"] == ["E-101", "E-104"]
    # Deterministic signal untouched, still present, still after.
    assert signals[1] == det[0]
    assert det == [det[0]]  # input not mutated


def test_why_now_uplift_not_duplicated_when_vertex_signal_persisted():
    """A run whose persisted signals already carry a vertex entry must
    not gain a second one on every read."""
    persisted = [{"kind": "SYNTHESIS", "text": "…", "source": "vertex"}]
    signals, _ = merge_gemini_overview(
        why_now_signals=persisted, firmographics=None, parsed_facts={},
        cache_rows=[_wn_row()],
    )
    assert len(signals) == 1


def test_why_now_uplift_suppressed_when_it_restates_a_signal():
    """2026-07-06 mandate: duplicate why-now content on one page adds
    nothing — a Vertex synthesis that is near-identical to a persisted
    signal is suppressed, not prepended."""
    det = [{"kind": "MIGRATION",
            "text": "The core banking migration to Fiserv DNA closes in Q3 "
                    "2027 while regional peers have already moved onto "
                    "modern cores.",
            "evidence": ["E-101"], "derived_from": "timeline_events"}]
    restating = _wn_row(output_text=(
        "The core banking migration to Fiserv DNA closes in Q3 2027, while "
        "regional peers have already moved onto modern cores."))
    signals, _ = merge_gemini_overview(
        why_now_signals=det, firmographics=None, parsed_facts={},
        cache_rows=[restating],
    )
    assert signals == det  # no duplicate prepended


def test_why_now_uplift_kept_when_it_genuinely_synthesizes():
    det = [{"kind": "MIGRATION",
            "text": "The core banking migration to Fiserv DNA closes in Q3 "
                    "2027 while regional peers have already moved onto "
                    "modern cores.",
            "evidence": ["E-101"], "derived_from": "timeline_events"}]
    novel = _wn_row(output_text=(
        "A new Chief Data Officer took the seat in March and owns the "
        "post-conversion analytics roadmap; the evaluation window for a "
        "unified customer data platform closes before integration "
        "contracts are signed."))
    signals, _ = merge_gemini_overview(
        why_now_signals=det, firmographics=None, parsed_facts={},
        cache_rows=[novel],
    )
    assert len(signals) == 2 and signals[0]["kind"] == "SYNTHESIS"


def test_why_now_uplift_skipped_when_it_restates_a_deterministic_signal():
    """Content-level dedup (2026-07-06): the synthesis is grounded on the
    same run evidence, so when its tokens are majority-contained in an
    existing signal it is a duplicate tile — skip the prepend."""
    det = [{
        "kind": "MIGRATION", "label": "Core migration mid-flight",
        "detail": ("Core migration closes Q3 2026; peers already moved to "
                   "the new stack."),
        "text": "Core migration closes Q3 2026.",
        "evidence": ["E-101"], "derived_from": "timeline_events",
    }]
    signals, _ = merge_gemini_overview(
        why_now_signals=det, firmographics=None, parsed_facts={},
        cache_rows=[_wn_row()],   # output_text restates the migration trigger
    )
    assert len(signals) == 1
    assert signals[0] == det[0]


def test_why_now_uplift_is_emitted_in_the_full_template_shape():
    """The prepend must carry the 14-field template (plus id/provenance) —
    the legacy 5-key shape rendered off-template on the strip."""
    signals, _ = merge_gemini_overview(
        why_now_signals=[{"kind": "M&A", "text": "Acquired X",
                          "detail": "Acquired X", "evidence": ["E-1"]}],
        firmographics=None, parsed_facts={}, cache_rows=[_wn_row()],
    )
    uplift = signals[0]
    for f in ("id", "label", "category", "strength", "window", "confidence",
              "claim", "detail", "metric", "peer_context", "play", "risk",
              "evidence", "timeline", "impact"):
        assert f in uplift, f"missing template field {f}"
    assert uplift["id"] == "WN-0"
    assert uplift["label"]
    assert uplift["category"] == "market"
    assert uplift["strength"] == "SUPPORTING"
    assert uplift["claim"] == "INFERENCE"
    assert uplift["confidence"] == "MEDIUM"     # two cited evidence ids
    assert uplift["detail"] == uplift["text"]
    assert uplift["source"] == "vertex"


def test_validator_failed_row_never_merges():
    signals, firm = merge_gemini_overview(
        why_now_signals=[], firmographics={"hq": "x"}, parsed_facts={},
        cache_rows=[_wn_row(validators_passed=False)],
    )
    assert signals == []
    assert firm == {"hq": "x"}


def test_no_rows_is_a_pure_passthrough():
    det = [{"kind": "M&A", "text": "t"}]
    firm_in = {"hq": "Boise, ID"}
    signals, firm = merge_gemini_overview(
        why_now_signals=det, firmographics=firm_in, parsed_facts={},
        cache_rows=[], enrichment_rows=[],
    )
    assert signals == det
    assert firm == firm_in


def test_row_column_fallback_when_output_json_absent():
    """Rows written before the provenance stamp landed still merge —
    model column + created_at fill model_id/synthesized_at."""
    row = _wn_row(output_json=None)
    signals, _ = merge_gemini_overview(
        why_now_signals=[], firmographics=None, parsed_facts={},
        cache_rows=[row],
    )
    assert signals[0]["model_id"] == "flash"
    assert signals[0]["synthesized_at"] == _NOW.isoformat()


# ── firmographics provenance + thought-leadership fill ──────────────────────

def test_gemini_extracted_fields_get_provenance_stamps():
    pf = {
        "branches": "34", "cagr": "7%",
        "_gemini_extracted": ["branches", "cagr"],
        "_fx_provenance": {
            "source": "vertex", "model_id": "gemini-2.5-flash",
            "synthesized_at": "2026-07-01T00:00:00+00:00",
        },
    }
    _, firm = merge_gemini_overview(
        why_now_signals=[], firmographics={"branches": "34", "cagr": "7%"},
        parsed_facts=pf, cache_rows=[_wn_row()],
    )
    assert firm["gemini_extracted_fields"] == ["branches", "cagr"]
    for field in ("branches", "cagr"):
        prov = firm["provenance"][field]
        assert prov["source"] == "vertex"
        assert prov["model_id"] == "gemini-2.5-flash"
    # values themselves untouched
    assert firm["branches"] == "34"


def test_thought_leadership_filled_from_cache_row_only_when_empty():
    items = [{"type": "podcast", "title": "T", "excerpt": "verbatim",
              "date": None, "author": None, "url": None}]
    tl_row = _wn_row(
        surface="thought_leadership_extraction",
        output_json={"source": "vertex", "model_id": "gemini-2.5-flash",
                     "synthesized_at": "2026-07-02T11:00:00+00:00",
                     "items": items},
    )
    # empty panel → filled + provenance
    _, firm = merge_gemini_overview(
        why_now_signals=[], firmographics={"thought_leadership": None},
        parsed_facts={}, cache_rows=[tl_row],
    )
    assert firm["thought_leadership"] == items
    assert firm["provenance"]["thought_leadership"]["source"] == "vertex"
    # populated panel (report/Clay-derived) → NEVER overwritten
    existing = [{"type": "article", "title": "keep me"}]
    _, firm2 = merge_gemini_overview(
        why_now_signals=[], firmographics={"thought_leadership": existing},
        parsed_facts={}, cache_rows=[tl_row],
    )
    assert firm2["thought_leadership"] == existing


def test_entity_ai_enrichments_attached_validator_passed_only():
    rows = [
        {"surface": "enrichment", "enrichment_text": "grounded",
         "model": "flash", "created_at": _NOW,
         "grounding_evidence_ids": ["E-9"], "validators_passed": True},
        {"surface": "enrichment", "enrichment_text": "REJECTED",
         "model": "flash", "created_at": _NOW,
         "grounding_evidence_ids": [], "validators_passed": False},
    ]
    _, firm = merge_gemini_overview(
        why_now_signals=[], firmographics={}, parsed_facts={},
        cache_rows=[], enrichment_rows=rows,
    )
    merged = firm["ai_enrichments"]
    assert len(merged) == 1
    assert merged[0]["text"] == "grounded"
    assert merged[0]["source"] == "vertex"
    assert merged[0]["evidence"] == ["E-9"]


def test_firmographics_none_stays_none():
    signals, firm = merge_gemini_overview(
        why_now_signals=[], firmographics=None, parsed_facts={},
        cache_rows=[_wn_row()],
        enrichment_rows=[{"surface": "enrichment", "enrichment_text": "x",
                          "model": "flash", "created_at": _NOW,
                          "grounding_evidence_ids": [],
                          "validators_passed": True}],
    )
    assert firm is None          # no dict to hang enrichment off — honest
    assert signals               # why_now uplift still merged


# ── thought-leadership acceptance validator (enrich_corpus) ─────────────────

_HAY = (
    "[E-201] (LinkedIn 2026-03-02) CEO Jane Roe posted: Our core "
    "modernization playbook is now public.\n"
    "[E-202] (Podcast) CTO Bob Lee joined the BankTech pod to discuss "
    "real-time payments."
)


def test_accept_tl_items_keeps_verbatim_grounded_items():
    out = """[
      {"type": "linkedin_post", "date": "2026-03-02",
       "title": "Core modernization playbook",
       "excerpt": "Our core modernization playbook is now public.",
       "author": "Jane Roe", "url": null},
      {"type": "podcast", "date": null, "title": "BankTech pod",
       "excerpt": "joined the BankTech pod to discuss real-time payments",
       "author": "Bob Lee", "url": null}
    ]"""
    items = _accept_tl_items(out, _HAY)
    assert [i["type"] for i in items] == ["linkedin_post", "podcast"]
    assert items[0]["author"] == "Jane Roe"
    assert items[0]["date"] == "2026-03-02"
    assert items[1]["url"] is None


def test_accept_tl_items_drops_fabricated_excerpts():
    out = """[
      {"type": "article", "title": "Made up",
       "excerpt": "This sentence appears nowhere in the evidence.",
       "author": "Jane Roe"}
    ]"""
    assert _accept_tl_items(out, _HAY) == []


def test_accept_tl_items_fail_closed_on_malformed_output():
    assert _accept_tl_items("not json at all", _HAY) == []
    assert _accept_tl_items('{"items": "nope"}', _HAY) == []
    assert _accept_tl_items("[]", _HAY) == []


def test_accept_tl_items_tolerates_fences_and_wrapper_and_caps_type():
    out = (
        "```json\n"
        '{"items": [{"type": "WEBINAR!!", "title": "t", '
        '"excerpt": "real-time payments"}]}\n'
        "```"
    )
    items = _accept_tl_items(out, _HAY)
    assert len(items) == 1
    assert items[0]["type"] == "article"  # unknown type normalized
