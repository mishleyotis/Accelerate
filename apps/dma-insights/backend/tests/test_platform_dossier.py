"""Pure-logic tests for the platform v3 deterministic dossier + reasoned
finding→platform links + readiness clause. No DB, fixture cards only."""
from __future__ import annotations

import re

from app.services import startup_enrich as se
from app.services.platform_dossier import (
    build_readiness_now,
    compose_dossier,
    story_facts_ok,
)


def _card(**over) -> dict:
    base = {
        "platform_id": "salesforce",
        "display_name": "Salesforce",
        "pillar": "P2",
        "fit_score": 62.0,
        "readiness_index": "red",
        "state": "READY",
        "addressable_subcap_ids": ["P2C1.1.1", "P2C1.2.1", "P2C3.4.2"],
        "sequence_rank": 4,
        "prereq_checks": [
            {"name": "Customer data foundation", "required_subcap_id": "P4C1.1.1",
             "threshold": 3.0, "status": "UNMET", "current_score": 2.0},
            {"name": "Identity & access management", "required_subcap_id": "P1C2.2.1",
             "threshold": 2.5, "status": "MET", "current_score": 2.8},
        ],
        "fit_breakdown": {
            "top_subcaps": [
                {"subcap_id": "P2C1.1.1", "name": "Competitive Analysis",
                 "score": 1.0, "peer_median": 3.0, "opportunity": 0.968,
                 "e_ids": ["E-040", "E-045"], "tier": 2},
                {"subcap_id": "P2C1.2.1", "name": "Industry Trend Monitoring",
                 "score": 1.5, "peer_median": 3.0, "opportunity": 0.8,
                 "e_ids": ["E-046"], "tier": 3},
            ],
            "factors": {"opportunity": {"points": 38.7, "value": 0.64}},
            "absent_families": ["Salesforce"],
            "sequence": {"rank": 4, "after": ["databricks", "tableau"]},
        },
    }
    base.update(over)
    return base


_TECH = [
    {"product_name": "DocuSign", "vendor": "DocuSign", "product": "DocuSign",
     "status": "CONFIRMED", "dma_pillar": "P2", "evidence_e_ids": ["E-127"],
     "peer_coverage": 0.3913},
    {"product_name": "Blue Prism", "vendor": "Blue Prism", "product": "Blue Prism",
     "status": "CONFIRMED", "dma_pillar": "P2", "evidence_e_ids": ["E-153"],
     "peer_coverage": 0.0435},
    {"product_name": "Databricks platform family", "vendor": "Databricks",
     "product": "Databricks", "status": "ABSENT", "dma_pillar": "P4",
     "evidence_e_ids": [], "peer_coverage": 0.4348},
]


# ── story_md floor ───────────────────────────────────────────────────────────

def test_story_never_null_and_scrubbed() -> None:
    out = compose_dossier(_card(), techstack_items=_TECH, entity_name="AAFCU")
    story = out["story_md"]
    assert story is not None and 100 < len(story) <= 1400
    # text_hygiene: no raw taxonomy codes / bare E-IDs leak into prose …
    assert "P2C1" not in story and "P4C1" not in story
    # … but bracketed E-ID citations survive verbatim.
    assert "[E-040" in story or "[E-127" in story
    assert out["story_source"] == "deterministic"


def test_sequence_grammar_agrees_with_single_prerequisite_platform() -> None:
    # W7 vet (2026-07-14): a SINGLE prerequisite platform must take singular
    # verbs — "Databricks goes first: it clears", never "Databricks go first:
    # they clear" (the plural weld found on 31 clients).
    # gating branch (an UNMET prereq present in _card):
    g = compose_dossier(_card(**{"fit_breakdown": {
        "top_subcaps": _card()["fit_breakdown"]["top_subcaps"],
        "factors": {"opportunity": {"points": 38.7, "value": 0.64}},
        "sequence": {"rank": 2, "after": ["databricks"]}}}),
        techstack_items=_TECH, entity_name="AAFCU")["story_md"]
    assert "Databricks deliver." not in g and "from them" not in g
    # no-gating branch: single after, all prereqs MET → "goes first: it clears"
    ng = compose_dossier(_card(**{
        "prereq_checks": [{"name": "X", "required_subcap_id": "P4C1.1.1",
                           "threshold": 3.0, "status": "MET", "current_score": 3.2}],
        "fit_breakdown": {
            "top_subcaps": _card()["fit_breakdown"]["top_subcaps"],
            "factors": {"opportunity": {"points": 38.7, "value": 0.64}},
            "prereqs": {"P4C1.1.1": {"name": "X", "threshold": 3.0,
                                     "status": "MET", "current_score": 3.2}},
            "sequence": {"rank": 2, "after": ["databricks"]}}}),
        techstack_items=_TECH, entity_name="AAFCU")["story_md"]
    assert "go first: they clear" not in ng and "which clear its" not in ng


def test_story_names_current_systems_and_facts() -> None:
    out = compose_dossier(_card(), techstack_items=_TECH, entity_name="AAFCU")
    story = out["story_md"]
    assert "DocuSign" in story  # a named CURRENT organizational capability
    assert "Competitive Analysis" in story  # top-opportunity subcap by name
    assert "1.0/5" in story and "3.0" in story  # score + peer, any notation
    assert story_facts_ok(story)  # ≥1 cite + ≥1 concrete fact


def test_story_red_blocked_and_challenges_prereq() -> None:
    out = compose_dossier(_card(), techstack_items=_TECH, entity_name="AAFCU")
    story = out["story_md"]
    assert "blocked on prerequisites" in story
    assert "Customer data foundation" in story
    assert re.search(r"2\.0 (?:versus the|today,|against a) 3\.0", story)


def test_story_green_deployable() -> None:
    card = _card(readiness_index="green", fit_score=78.0, prereq_checks=[
        {"name": "Sales process digitization", "required_subcap_id": "P2C1.1.1",
         "threshold": 2.5, "status": "MET", "current_score": 3.0},
    ])
    out = compose_dossier(card, techstack_items=_TECH, entity_name="AAFCU")
    assert re.search(r"green|clears?\b|ready", out["story_md"])
    assert re.search(r"land now|deployable as-is|ready today", out["story_md"])


def test_capped_prereq_challenge_overrides_stale_met() -> None:
    # A prereq LABELLED MET but whose score is below threshold must be flagged
    # OPEN — "Do not conclude a condition is met before challenging it".
    card = _card(readiness_index="amber", prereq_checks=[
        {"name": "Data foundation", "required_subcap_id": "P4C1.1.1",
         "threshold": 3.0, "status": "MET", "current_score": 2.1},
    ])
    rn = build_readiness_now(card, None)
    assert rn["total_prereqs"] == 1
    assert len(rn["open_prereqs"]) == 1  # challenged: 2.1 < 3.0 → OPEN despite MET
    assert rn["open_prereqs"][0]["current"] == 2.1


def test_open_prereq_always_carries_related_subcaps() -> None:
    # 2026-07 operator report: a prerequisite (the readiness card's "missing
    # issue") must NEVER surface zero related subcaps when it carries a
    # linked_subcap_id (its required_subcap_id). Here P4C1.1.1 is gated but the
    # platform's top_subcaps are all P2C1 — the old prefix-only matcher found
    # nothing; the gate subcap itself is now always related.
    rn = build_readiness_now(_card(), None)
    assert rn["open_prereqs"], "P4C1.1.1 (2.0 < 3.0) is open"
    for p in rn["open_prereqs"]:
        rel = p["related_subcaps"]
        assert rel, f"prereq {p['required_subcap_id']} has zero related subcaps"
        # the gate subcap (the issue's own linked_subcap_id) leads the list
        assert rel[0]["subcap_id"] == p["required_subcap_id"]


def test_related_subcaps_pull_same_category_contributors() -> None:
    # A prereq gated on the SAME category the platform contributes in surfaces
    # those contributing subcaps (with names/scores) as related, not just the
    # gate — the "backing subcaps" the readiness card drills into.
    card = _card(prereq_checks=[
        {"name": "Competitive analysis foundation",
         "required_subcap_id": "P2C1.1.1", "threshold": 3.0,
         "status": "UNMET", "current_score": 1.0},
    ])
    rn = build_readiness_now(card, None)
    rel = rn["open_prereqs"][0]["related_subcaps"]
    ids = {r["subcap_id"] for r in rel}
    assert {"P2C1.1.1", "P2C1.2.1"} <= ids  # both P2C1 contributors surfaced
    named = {r["subcap_id"]: r["name"] for r in rel}
    assert named.get("P2C1.2.1") == "Industry Trend Monitoring"


def test_greenfield_vs_expansion() -> None:
    # ABSENT pitched family → greenfield.
    out = compose_dossier(_card(), techstack_items=[
        {"product_name": "Salesforce Sales Cloud", "vendor": "Salesforce",
         "product": "Sales Cloud", "status": "ABSENT", "dma_pillar": "P2",
         "evidence_e_ids": [], "peer_coverage": 0.5}], entity_name="X")
    assert out["dossier"]["readiness_now"]["greenfield"] is True
    assert re.search(r"greenfield|open ground|no incumbent", out["story_md"])
    # CONFIRMED pitched family → expansion, not greenfield.
    out2 = compose_dossier(_card(**{"fit_breakdown": {
        **_card()["fit_breakdown"], "absent_families": []}}), techstack_items=[
        {"product_name": "Salesforce FSC", "vendor": "Salesforce",
         "product": "Financial Services Cloud", "status": "CONFIRMED",
         "dma_pillar": "P2", "evidence_e_ids": ["E-9"], "peer_coverage": 0.7}],
        entity_name="X")
    assert out2["dossier"]["readiness_now"]["greenfield"] is False
    assert re.search(r"expansion|existing foot(?:hold|print)", out2["story_md"])


def test_integrate_lens_names_incumbent_never_greenfield() -> None:
    # 2026-07-14 skew audit: an absent family whose category is occupied by
    # a third-party incumbent must argue integration with the named
    # incumbent — the greenfield frame over an occupied layer was the
    # audit's top narrative defect (4 sampled DBX cards ≥70 over Snowflake).
    base = _card(platform_id="databricks", display_name="Databricks")
    bd = dict(base["fit_breakdown"])
    bd["absent_families"] = ["Databricks"]
    bd["factors"] = {
        **(bd.get("factors") or {}),
        "absent_boost": {
            "points": 2.0, "value": 0.25,
            "stack_lens": {"lens": "integrate",
                           "category_incumbents": ["Snowflake"]},
            "peer_coverage": 0.3,
        },
    }
    out = compose_dossier(
        _card(platform_id="databricks", display_name="Databricks",
              fit_breakdown=bd),
        techstack_items=[
            {"product_name": "Snowflake", "vendor": "Snowflake",
             "product": "Snowflake", "status": "CONFIRMED", "dma_pillar": "P4",
             "evidence_e_ids": [], "peer_coverage": 0.3}],
        entity_name="X")
    rn = out["dossier"]["readiness_now"]
    assert rn["lens"] == "integrate"
    assert rn["category_incumbents"] == ["Snowflake"]
    assert rn["greenfield"] is False
    assert "Snowflake" in out["story_md"]
    assert not re.search(r"greenfield|open ground|no incumbent to unwind",
                         out["story_md"], re.I)


def test_integrate_lens_fallback_scans_techstack_for_legacy_cards() -> None:
    # A card computed before the lens existed (no stack_lens in the
    # breakdown) still flips to integrate when a category incumbent is
    # CONFIRMED in the techstack items.
    base = _card(platform_id="databricks", display_name="Databricks")
    bd = dict(base["fit_breakdown"])
    bd["absent_families"] = ["Databricks"]
    out = compose_dossier(
        _card(platform_id="databricks", display_name="Databricks",
              fit_breakdown=bd),
        techstack_items=[
            {"product_name": "Snowflake", "vendor": "Snowflake",
             "product": "Snowflake", "status": "CONFIRMED", "dma_pillar": "P4",
             "evidence_e_ids": [], "peer_coverage": 0.3}],
        entity_name="X")
    rn = out["dossier"]["readiness_now"]
    assert rn["lens"] == "integrate"
    assert "Snowflake" in rn["category_incumbents"]


def test_insufficient_evidence_card_still_gets_story() -> None:
    card = _card(state="INSUFFICIENT_EVIDENCE", addressable_subcap_ids=[],
                 fit_breakdown={"top_subcaps": [], "absent_families": []})
    out = compose_dossier(card, techstack_items=_TECH, entity_name="AAFCU")
    assert out["story_md"] is not None  # honest current-state floor, never a hole
    assert "No capability gaps" in out["story_md"]


def test_provenance_audit_chain() -> None:
    out = compose_dossier(_card(), techstack_items=_TECH, entity_name="AAFCU")
    prov = out["narrative_provenance"]
    assert len(prov) >= 3
    kinds = {p["source_kind"] for p in prov}
    assert {"subcap_score", "prereq"} <= kinds
    # the opportunity claim carries the lead subcap's E-IDs
    opp = next(p for p in prov if p["source_kind"] == "subcap_score")
    assert "E-040" in opp["e_ids"]


def test_no_display_name_returns_null() -> None:
    out = compose_dossier({})
    assert out["story_md"] is None and out["dossier"] is None


# ── reasoned finding→platform links ──────────────────────────────────────────

def _cards_for_links() -> list[dict]:
    return [
        {"platform_id": "salesforce", "display_name": "Salesforce", "pillar": "P2",
         "fit_score": 40.0, "readiness_index": "red",
         "addressable_subcap_ids": ["P2C1.1.1", "P2C1.2.1"],
         "fit_breakdown": {"top_subcaps": [
             {"subcap_id": "P2C1.1.1", "opportunity": 0.9, "e_ids": ["E-1"]}]}},
        {"platform_id": "databricks", "display_name": "Databricks", "pillar": "P4",
         "fit_score": 70.0, "readiness_index": "green",
         "addressable_subcap_ids": ["P4C1.1.1", "P4C2.1.1"],
         "fit_breakdown": {"top_subcaps": [
             {"subcap_id": "P4C1.1.1", "opportunity": 0.95, "e_ids": ["E-2"]}]}},
        {"platform_id": "ncino", "display_name": "nCino", "pillar": "P3",
         "fit_score": 55.0, "readiness_index": "amber",
         "addressable_subcap_ids": ["P3C1.1.1"], "fit_breakdown": {"top_subcaps": []}},
    ]


def test_finding_links_prefer_addressing_platform() -> None:
    # A P2 finding: only Salesforce addresses the P2C1 category.
    ids, rationale = se.platforms_for_finding(_cards_for_links(), "P2C1.1.1")
    assert ids[0] == "Salesforce"  # canonical display name
    assert rationale[0]["addresses"] is True
    assert "P2C1.1.1" in rationale[0]["addressed_subcap_ids"]
    assert rationale[0]["e_ids"] == ["E-1"]


def test_finding_links_fallback_flags_non_address() -> None:
    # A P1 finding: NO platform addresses the P1C1 category → fallback, flagged.
    ids, rationale = se.platforms_for_finding(_cards_for_links(), "P1C1.1.1")
    assert ids  # still returns candidates (never empty when cards exist)
    assert all(r["addresses"] is False for r in rationale)


def test_finding_links_normalize_casing_and_cap() -> None:
    ids, rationale = se.platforms_for_finding(_cards_for_links(), "P4C1.1.1", top=2)
    assert ids == ["Databricks"] or ids[0] == "Databricks"
    assert len(ids) <= 2
    # display-name casing is canonical (never 'ncino')
    assert "ncino" not in ids


# ── readiness_phrase light strings + numerics ────────────────────────────────

def test_readiness_phrase_accepts_light_strings() -> None:
    assert se.readiness_phrase("green") == "readiness green — deployable now"
    assert "near-ready" in se.readiness_phrase("amber", unmet_count=2)
    assert "2 prerequisites open" in se.readiness_phrase("amber", unmet_count=2)
    assert "blocked on prerequisites" in se.readiness_phrase("red")
    # numerics still work (back-compat)
    assert "deployable now" in se.readiness_phrase(85)
    assert se.readiness_phrase("n/a") is None
    assert se.readiness_phrase(None) is None


def test_opportunity_md_now_renders_readiness_from_light_string() -> None:
    # The dead-code fix: readiness_index is the light string on real cards.
    # Frame pools vary the posture sentence's surface (anti-template 2026-07-13)
    # but the readiness verdict itself is invariant.
    md = se.compose_opportunity_md(_card())
    assert md is not None
    assert re.search(r"red|blocked", md, re.I) and "prerequisite" in md
    # deterministic per (entity, platform): same inputs → same prose
    assert md == se.compose_opportunity_md(_card())
    # different entities draw different frames somewhere in the corpus
    variants = {se.compose_opportunity_md(_card(), entity_key=f"e{i}") for i in range(8)}
    assert len(variants) >= 2


# ── Gemini uplift validator: number-in-grounding ─────────────────────────────

def test_platform_story_validator_blocks_ungrounded_numbers() -> None:
    from app.scripts.enrich_corpus import _accept_platform_story
    ctx = {
        "fit_score": "40/100",
        "top_gaps": "Competitive Analysis: 1.0/5 vs 3.0 peer median",
        "prereq_lines": "Data foundation: 2.0 vs 3.0 threshold",
        "gap_evidence": "[E-040] excerpt",
        "current_stack": "DocuSign",
        "readiness_line": "red", "scqa_situation": "",
    }
    # every number present in the grounding → accepted
    assert _accept_platform_story(
        "DocuSign today. Competitive Analysis 1.0/5 vs 3.0 [E-040]. Data foundation "
        "2.0 vs 3.0. Fit 40/100.", ctx) is True
    # section numbers 1-3 are structural, not claims
    assert _accept_platform_story("1. state 2. why 3. path", ctx) is True
    # a Gemini-invented figure ($4.2M, 12 days, 2025) → blocked
    assert _accept_platform_story(
        "Loan cycle 12 days, $4.2M saved in 2025 [E-040].", ctx) is False


def test_w4_backing_rec_named_in_dossier() -> None:
    card = _card()
    bd = dict(card["fit_breakdown"])
    bd["analyst_backing"] = {"backed": True, "note": None,
        "recs": [{"rec_id": "R2", "title": "Build unified member 360 view", "phase": 1}]}
    out = compose_dossier(_card(fit_breakdown=bd), techstack_items=_TECH, entity_name="X")
    assert "member 360 view" in out["story_md"].lower()


def test_w4_unbacked_hot_card_flagged() -> None:
    bd = {**_card()["fit_breakdown"], "absent_families": ["Salesforce"],
          "analyst_backing": {"backed": False, "recs": [],
                              "note": "engine-derived from the capability data"}}
    out = compose_dossier(_card(fit_score=72.0, fit_breakdown=bd),
                          techstack_items=[], entity_name="X")
    s = out["story_md"].lower()
    assert "engine read" in s or "does not name" in s
