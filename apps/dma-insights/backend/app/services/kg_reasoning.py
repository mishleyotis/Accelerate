"""Knowledge-graph reasoning layer — deficiency → L4 features → VALIDATED user
stories → platform / opportunity, grounded in the v7.0 capability catalogue.

The operator mandate (2026-07-15): the models must REASON over a validated
knowledge graph built from the catalogue's L3/L4 features + user stories, not
infer platforms from a deterministic catalogue score alone. Gemini is reserved
for enrichment / challenge-verify; the reasoning here is deterministic and
grounded so it is auditable and cannot hallucinate a platform.

The graph spine (all edges already in the loaded catalogue):

    client subcap deficiency         (subcap_scores: gap vs peer/target)
      → L4 features that address it  (ccg_l4_features: subcap → feature → vendor)
      → user stories that VALIDATE   (ccg_user_stories: subcap → l4_features_used,
        the value                     use_case_ids, match_confidence)
      → the platform/vendor whose validated features dominate

``build_kg_reasoning`` walks that spine per platform family, producing an
auditable KgReasoning record: which of the client's deficient subcaps a platform
addresses, the specific validated L4 features + how many catalogued use-case
stories back each, and a story-weighted confidence. This is the grounding the
fit engine's RecSignal consumes and the composers cite — never a bare score.

ANTI-PATTERN EXCLUSION (the "don't train on wrong data" contract): a small set
of subcap→feature-bundle edges were confirmed WRONG-DOMAIN by the 2026-07-15
deep-NLP validation (MiniLM semantic recall net + LLM challenge reasoning that
steelmans then refutes each match — NO fuzzy string matching). HIGH-tier
mis-maps are DROPPED from the graph so a recommendation is never grounded on a
bundle that serves a foreign domain (e.g. a conversational chat-agent stack
mapped onto real-time fraud DETECTION). MEDIUM-tier are flagged (kept, but
surfaced for catalogue-owner review) so good training data is not discarded.

Pure + framework-free (mirrors platform_affinity / use_case_stories): every
function folds plain inputs; the async DB assembly lives in platform_fit_data.
Never raises — a cold catalogue yields empty reasoning and the engine behaves
exactly as before (zero regression).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ── Deep-NLP anti-pattern registry (2026-07-15) ──────────────────────────────
# Source: MiniLM semantic recall net → 3-shard LLM challenge pass (steelman +
# refute, abstraction-confound corrected) → adversarial verifier. 94.4% of
# candidates cleared; only unambiguous wrong-domain mappings confirmed. Tiers:
#   HIGH   → excluded from KG grounding (bundle serves a foreign domain).
#   MEDIUM → kept but flagged (residual ambiguity; owner review before hard drop).
KG_ANTI_PATTERNS: dict[str, dict[str, str]] = {
    "P3C2.3.4": {"tier": "HIGH", "name": "Account Takeover Prevention",
                 "foreign_domain": "conversational AI / agentic chat-agent tooling",
                 "reason": "bundle is pure conversational-AI primitives with no "
                           "transaction-monitoring / behavioural-analytics / "
                           "device-intelligence detection core"},
    "P3C3.6.1": {"tier": "HIGH", "name": "Exam Preparation",
                 "foreign_domain": "customer service / contact center",
                 "reason": "bundle is a voice/service-agent contact-centre stack; "
                           "the exam-evidence/document/portal core is absent"},
    "P3C3.6.3": {"tier": "MEDIUM", "name": "Finding Remediation",
                 "foreign_domain": "conversational AI / knowledge assistant",
                 "reason": "only generic conversational-agent scaffolding; no "
                           "case/finding-closure/evidence core"},
    "P2C1.2.3": {"tier": "MEDIUM", "name": "Paid Search (SEM)",
                 "foreign_domain": "owned-channel / direct marketing automation",
                 "reason": "email/SMS/journey tooling only; no paid-search / "
                           "ad-platform tooling"},
    "P2C1.2.2": {"tier": "MEDIUM", "name": "Search Engine Optimization (SEO)",
                 "foreign_domain": "outbound email/SMS campaign marketing",
                 "reason": "outbound campaign tooling dominates; no organic-search "
                           "/ SEO tooling"},
}

# HIGH-tier subcaps whose story→feature edges are dropped from KG grounding.
EXCLUDED_SUBCAP_IDS: frozenset[str] = frozenset(
    sid for sid, v in KG_ANTI_PATTERNS.items() if v["tier"] == "HIGH"
)
# MEDIUM-tier subcaps kept but flagged (surfaced, never silently trusted).
FLAGGED_SUBCAP_IDS: frozenset[str] = frozenset(
    sid for sid, v in KG_ANTI_PATTERNS.items() if v["tier"] == "MEDIUM"
)


@dataclass
class KgEdge:
    """One validated deficiency→platform edge: the platform addresses this
    deficient subcap via features PROVEN by N catalogued use-case stories."""
    subcap_id: str
    subcap_name: str
    platform_id: str
    validated_features: list[str]          # L4 features shared by story + affinity
    n_stories: int                         # catalogued use cases validating them
    story_confidence: float                # max match_confidence for the subcap
    deficiency: float                      # gap severity (higher = worse), 0..1
    flagged: bool = False                  # MEDIUM-tier anti-pattern (review)


@dataclass
class KgReasoning:
    """Per-platform reasoning rollup the fit engine + composers consume."""
    platform_id: str
    edges: list[KgEdge] = field(default_factory=list)
    # story-weighted, deficiency-weighted grounding strength (0..1, higher=stronger)
    grounding_score: float = 0.0
    addressed_subcap_ids: list[str] = field(default_factory=list)
    total_stories: int = 0
    lead_subcap: str | None = None         # the deepest deficiency this platform addresses
    flagged_subcap_ids: list[str] = field(default_factory=list)


def _norm_feat(f: str) -> str:
    return " ".join(str(f or "").lower().split())


def build_kg_reasoning(
    deficiencies: dict[str, float],
    subcap_names: dict[str, str],
    playbooks: dict[str, dict],
    platform_features_by_subcap: dict[str, dict[str, list[str]]],
) -> dict[str, KgReasoning]:
    """Walk the validated graph → per-platform reasoning.

    Args:
      deficiencies: subcap_id → gap severity in [0,1] (1 = worst gap). Only
        subcaps the client is actually deficient in are passed.
      subcap_names: subcap_id → display name (for the audit trace).
      playbooks: subcap_id → {"features": [...], "n_stories": n,
        "confidence": c} from ``use_case_stories.build_playbooks`` (the
        VALIDATED use-case corpus — the "training" signal).
      platform_features_by_subcap: subcap_id → {platform_id → [feature names]}
        from the catalogue affinity (which platform delivers which feature for
        the subcap). Restricting to features that ALSO appear in the subcap's
        validated playbook is what makes an edge story-validated, not inferred.

    Returns platform_id → KgReasoning. HIGH-tier anti-pattern subcaps are
    dropped entirely; MEDIUM-tier are included with ``flagged=True``.
    """
    per_platform: dict[str, KgReasoning] = {}
    for subcap_id, sev in deficiencies.items():
        if subcap_id in EXCLUDED_SUBCAP_IDS:
            continue  # HIGH-tier wrong-domain mapping — never ground on it
        pb = playbooks.get(subcap_id)
        if not pb:
            continue  # no validated user-story pattern for this subcap
        validated = {_norm_feat(f) for f in pb.get("features", [])}
        if not validated:
            continue
        plat_feats = platform_features_by_subcap.get(subcap_id) or {}
        flagged = subcap_id in FLAGGED_SUBCAP_IDS
        for platform_id, feats in plat_feats.items():
            # an edge exists only where the platform's catalogue features for
            # this subcap INTERSECT the story-validated feature set
            shared = [f for f in feats if _norm_feat(f) in validated]
            if not shared:
                continue
            r = per_platform.setdefault(platform_id, KgReasoning(platform_id=platform_id))
            r.edges.append(KgEdge(
                subcap_id=subcap_id,
                subcap_name=subcap_names.get(subcap_id, subcap_id),
                platform_id=platform_id,
                validated_features=sorted(dict.fromkeys(shared))[:6],
                n_stories=int(pb.get("n_stories", 0) or 0),
                story_confidence=float(pb.get("confidence", 0.0) or 0.0),
                deficiency=float(sev),
                flagged=flagged,
            ))
    # roll up per platform
    for r in per_platform.values():
        # grounding = sum(deficiency severity * story-evidence weight), normalized.
        # story weight saturates (a subcap validated by many use cases counts,
        # but one mega-subcap can't dominate): 1 - 1/(1+n_stories) in [0,1).
        total = 0.0
        for e in r.edges:
            story_w = 1.0 - 1.0 / (1.0 + max(e.n_stories, 0))
            total += e.deficiency * (0.5 + 0.5 * story_w)  # floor so sev alone counts
        r.total_stories = sum(e.n_stories for e in r.edges)
        r.addressed_subcap_ids = sorted({e.subcap_id for e in r.edges})
        r.flagged_subcap_ids = sorted({e.subcap_id for e in r.edges if e.flagged})
        # normalize by a soft cap so grounding_score is comparable across clients
        r.grounding_score = round(min(1.0, total / 6.0), 4)
        lead = max(r.edges, key=lambda e: (e.deficiency, e.n_stories), default=None)
        r.lead_subcap = lead.subcap_id if lead else None
    return per_platform


def anti_pattern_summary() -> dict[str, object]:
    """The registry the QA gate + admin surface read to show what was excluded."""
    return {
        "excluded_high": sorted(EXCLUDED_SUBCAP_IDS),
        "flagged_medium": sorted(FLAGGED_SUBCAP_IDS),
        "detail": KG_ANTI_PATTERNS,
        "method": "MiniLM semantic recall net + LLM challenge reasoning "
                  "(steelman/refute, abstraction-confound corrected); no fuzzy "
                  "string matching",
    }
