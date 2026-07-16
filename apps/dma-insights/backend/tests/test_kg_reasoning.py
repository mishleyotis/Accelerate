"""KG reasoning layer — deficiency → L4 features → validated user stories →
platform, with deep-NLP anti-pattern exclusion (2026-07-15)."""
from __future__ import annotations

from app.services import kg_reasoning as kg


def _inputs():
    deficiencies = {
        "P2C1.1.1": 0.60,   # strong gap, has a playbook + platform features
        "P2C1.1.2": 0.30,   # milder gap
        "P3C2.3.4": 0.80,   # HIGH anti-pattern — must be DROPPED
        "P3C3.6.3": 0.50,   # MEDIUM anti-pattern — kept but FLAGGED
        "P9C9.9.9": 0.90,   # no playbook — skipped
    }
    subcap_names = {
        "P2C1.1.1": "Omnichannel Orchestration", "P2C1.1.2": "Next-Best-Action",
        "P3C2.3.4": "Account Takeover Prevention", "P3C3.6.3": "Finding Remediation",
    }
    playbooks = {
        "P2C1.1.1": {"features": ["Journey Builder", "Data Cloud DMO"], "n_stories": 8, "confidence": 0.9},
        "P2C1.1.2": {"features": ["Einstein Discovery"], "n_stories": 3, "confidence": 0.6},
        "P3C2.3.4": {"features": ["Agentforce Builder"], "n_stories": 5, "confidence": 0.5},
        "P3C3.6.3": {"features": ["Agent Actions"], "n_stories": 2, "confidence": 0.4},
    }
    platform_features_by_subcap = {
        "P2C1.1.1": {"salesforce": ["Journey Builder", "Flow"], "databricks": ["Data Cloud DMO"]},
        "P2C1.1.2": {"salesforce": ["Einstein Discovery"]},
        "P3C2.3.4": {"salesforce": ["Agentforce Builder"]},   # excluded upstream
        "P3C3.6.3": {"salesforce": ["Agent Actions"]},
    }
    return deficiencies, subcap_names, playbooks, platform_features_by_subcap


def test_high_anti_pattern_is_dropped_medium_is_flagged():
    kgr = kg.build_kg_reasoning(*_inputs())
    all_subcaps = {s for r in kgr.values() for s in r.addressed_subcap_ids}
    # HIGH-tier P3C2.3.4 never grounds anything
    assert "P3C2.3.4" not in all_subcaps
    # MEDIUM-tier P3C3.6.3 is present but flagged
    assert "P3C3.6.3" in all_subcaps
    sf = kgr["salesforce"]
    assert "P3C3.6.3" in sf.flagged_subcap_ids
    flagged_edge = next(e for e in sf.edges if e.subcap_id == "P3C3.6.3")
    assert flagged_edge.flagged is True


def test_edge_requires_story_validated_feature_intersection():
    kgr = kg.build_kg_reasoning(*_inputs())
    sf = kgr["salesforce"]
    e = next(x for x in sf.edges if x.subcap_id == "P2C1.1.1")
    # only features shared by BOTH the validated playbook AND the platform's
    # catalogue features count ("Flow" is a platform feature but NOT in the
    # story-validated playbook, so it is excluded).
    assert "Journey Builder" in e.validated_features
    assert "Flow" not in e.validated_features
    assert e.n_stories == 8 and e.deficiency == 0.60


def test_grounding_prefers_deeper_deficiency_and_more_stories():
    kgr = kg.build_kg_reasoning(*_inputs())
    # databricks only touches P2C1.1.1 via Data Cloud DMO; salesforce touches
    # more deficient subcaps with more stories → higher grounding.
    assert kgr["salesforce"].grounding_score > kgr["databricks"].grounding_score
    assert kgr["salesforce"].lead_subcap == "P2C1.1.1"   # deepest gap it grounds


def test_no_playbook_subcap_is_skipped():
    kgr = kg.build_kg_reasoning(*_inputs())
    assert all("P9C9.9.9" not in r.addressed_subcap_ids for r in kgr.values())


def test_graceful_empty():
    assert kg.build_kg_reasoning({}, {}, {}, {}) == {}
    # cold playbooks/affinity but live deficiencies → no edges, no raise
    assert kg.build_kg_reasoning({"P1C1.1.1": 0.5}, {}, {}, {}) == {}


def test_registry_shape():
    s = kg.anti_pattern_summary()
    assert set(s["excluded_high"]) == {"P3C2.3.4", "P3C3.6.1"}
    assert "P2C1.2.2" in s["flagged_medium"]
    assert "no fuzzy" in s["method"]
    # excluded ⊂ registry, tiers consistent
    for sid in kg.EXCLUDED_SUBCAP_IDS:
        assert kg.KG_ANTI_PATTERNS[sid]["tier"] == "HIGH"
