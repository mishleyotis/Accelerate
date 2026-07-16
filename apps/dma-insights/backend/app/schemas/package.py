"""IngestedPackage — typed envelope produced by the package parser.

The Claude project's bot/n8n pipeline emits a `{Entity}_DMA_Complete_Package`
zip with a fixed folder layout (see `app/services/parsers/dma_package.py`).
The package parser walks that layout and produces an `IngestedPackage`
that the persistence stage maps onto our DB schema (entities / runs /
subcap_scores / evidence_index / recommendations / issue_register /
peer_benchmarks / tech_stack_entries / firmographics).

State-branch contract for the envelope:
  - Always populated:    manifest, run_manifest, scoring (categories + pillars
                         + overall), subcap_scores, evidence
  - Often populated:     issue_register, recommendations, peer_set
  - Conditional:         tech_stack (only when Explorium xlsx present),
                         firmographics (only when research_handoff.json present),
                         qa_verdict (only when 07_governance present)
  - Tolerant of missing: anything in `05_narrative_deck/` (deck rarely
                         generated; surface degrades gracefully)
"""
from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PackageManifest(BaseModel):
    """Top-level `MANIFEST.json` contents."""
    engagement: str
    run_id: str
    package_date: date | None = None
    framework: str | None = None
    overall_score: float | None = None
    verdict: str | None = None


class RunManifest(BaseModel):
    """Either `07_governance/run_manifest.json` (ALMA shape) or
    `08_appendices/run_manifest.json` (WSFS shape). Schema is `run_manifest_v2`."""
    model_config = ConfigDict(extra="ignore")

    run_id: str  # canonical assessment id (DMA-ASM-… or REQ-…)
    research_run_id: str | None = None
    institution_name: str
    evidence_mode: str | None = None
    rubric_version: str | None = None
    skill_version: str | None = None
    subvertical_code: str | None = None
    subvertical_name: str | None = None
    pillar_weights: dict[str, float] | None = None
    pillar_scores: dict[str, float] | None = None
    overall_score: float | None = None
    assessment_date: date | None = None


class SubcapScoreRow(BaseModel):
    subcap_id: str
    category_id: str
    score: float
    confidence: str | None = None
    evidence_ceiling: float | None = None
    caps_applied: str | None = None
    rationale: str | None = None
    # Optional human-readable subcap name from the scoring workbook's
    # `SubCap_Name` column. Used by the catalogue auto-bootstrap to seed
    # `ccg_subcaps.name` with real capability names ("Digital Strategy
    # Document", "Audience Segmentation") instead of placeholder
    # f"Subcap {sid}" — keeps the heatmap + drawer copy honest when the
    # operator hasn't run ccg_loader for the package's catalogue version.
    name: str | None = None


class CategoryScoreRow(BaseModel):
    category_id: str
    category_name: str | None = None
    pillar_id: str
    score: float
    peer_median: float | None = None
    peer_p25: float | None = None
    peer_p75: float | None = None


class PillarScoreRow(BaseModel):
    pillar_id: str
    pillar_name: str | None = None
    score: float
    weight: float | None = None


class InsightCardRow(BaseModel):
    """A D2 insight card derived from `section_analysis_#.json` top_findings.
    Maps 1:1 onto the `insight_cards` table (all text columns NOT NULL;
    severity ∈ critical|high|medium|low; UNIQUE(run_id, ic_id))."""
    ic_id: str
    severity: str
    title: str
    what_text: str
    why_text: str = ""
    so_what_text: str = ""
    linked_subcap_id: str
    linked_e_ids: list[str] = Field(default_factory=list)
    # The recommendation this card was DERIVED from (when built by
    # insights_from_recommendations) — the faithful single link for the D2
    # "Linked recommendation" callout. None for section-analysis / category
    # derived cards.
    source_rec_id: str | None = None


class FactItem(BaseModel):
    """One extracted fact from `evidence_index.json` E-ID `facts[]`.
    `text` is tolerant (defaults empty) so a malformed fact never aborts
    the surrounding EvidenceRow construction."""
    model_config = ConfigDict(extra="ignore")

    fact_id: str | None = None
    text: str = ""
    claim_label: str | None = None
    specificity_score: float | None = None


class TimelineEventCandidate(BaseModel):
    """A D5 Context timeline event derived from an evidence fact. Maps 1:1
    onto the `timeline_events` columns (entity-level, event_date NOT NULL).

    2026-07-02 (Part 8.2 NLP event pipeline): carries the migration-047
    columns — ``signal`` (polarity-classified, native to the claim),
    ``date_precision`` (day|month|quarter|year|publish_fallback),
    ``evidence_e_ids`` (multi-value anchors) and ``subcap_ids`` (capability
    links). All optional/additive so legacy call sites stay valid.
    """
    event_date: date
    kind: str
    title: str
    body: str | None = None
    source_url: str | None = None
    e_id: str | None = None
    signal: str | None = None
    date_precision: str | None = None
    evidence_e_ids: list[str] = Field(default_factory=list)
    subcap_ids: list[str] = Field(default_factory=list)


# ── Canonical evidence source-tier taxonomy ─────────────────────────────
# The research workbooks / research_handoff.json declare the source-tier
# scale the analysts actually use. Across the full fixture corpus two
# variants are declared, and their union is T1..T7:
#   Compeer-style: T1_regulatory, T2_official, T3_thirdparty,
#                  T4_jobpostings, T5_marketing
#   Fulton-style:  T1_primary_regulator_issuer, T2_press_release…,
#                  T3_industry_publication, T6_specialized_data_provider,
#                  T7_other_credible_source (+ T10_internal_synthesis,
#                  which is NOT a source tier)
# Anything outside [1, 7] is a synthesis/QA artefact ("T10-CONTRADICTORY"),
# a confidence word ("HIGH"), or bot noise ("T9") — never a real source
# tier. The 2026-07-06 QA found the previous clamp-to-8 / default-5
# behaviour FABRICATED tiers (the live drawer's "Tier 8" rows all came
# from `or 8` defaults and T10→8 clamps). Honest rule: normalize to the
# canonical set, otherwise None — never invent a tier.
CANONICAL_TIER_MIN = 1
CANONICAL_TIER_MAX = 7

_TIER_NUM_RE = re.compile(r"(?<![\d.])(\d{1,2})(?![\d.])")


def normalize_tier(raw: object) -> int | None:
    """Evidence source tier → canonical int in [1, 7], else None.

    Accepts the analyst vernacular seen in the corpus:
      ``3`` / ``"3"`` / ``"T3"`` / ``"Tier 3"``      → 3
      ``"T7-PROXY"`` / ``"T2-RB"`` (suffixed)         → 7 / 2
      ``"T2, T2"`` (repeated single value)            → 2
      ``"T1, T2, T3"`` (multi-value SET cell)         → None — the cell
        describes the tier mix of a whole evidence set (a per-subcap
        workbook row), so no single tier can honestly be attributed to
        one E-ID; picking the strongest would fabricate authority.
      ``"T10-CONTRADICTORY"`` / ``"T9"`` / ``9``      → None (out of taxonomy)
      ``"HIGH"`` / ``"NO_EVIDENCE"`` / ``""`` / None  → None (no tier stated)

    Year-like tokens ("2024") never match — the digit run is bounded to
    two digits with no adjacent digits/dots.
    """
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int | float):
        try:
            n = int(raw)
        except (ValueError, OverflowError):
            return None
        return n if CANONICAL_TIER_MIN <= n <= CANONICAL_TIER_MAX else None
    s = str(raw).strip()
    if not s:
        return None
    valid = {
        int(m.group(1))
        for m in _TIER_NUM_RE.finditer(s)
        if CANONICAL_TIER_MIN <= int(m.group(1)) <= CANONICAL_TIER_MAX
    }
    # No canonical value ("T10", "T9", "HIGH") or an ambiguous SET of
    # distinct values ("T1, T2, T3") → honest None, never an invented or
    # clamped neighbour.
    return valid.pop() if len(valid) == 1 else None


class EvidenceRow(BaseModel):
    e_id: str
    source_name: str
    source_url: str | None = None
    tier: int | None = None
    ers: float | None = None
    publish_date: str | None = None
    subcap_mappings: list[str] = Field(default_factory=list)
    excerpt: str
    signal_direction: str | None = None
    internal_source: bool = False
    corroboration_count: int | None = None
    # 2026-06-09: per-E-ID extracted facts (evidence_index.json `facts[]`).
    # Retained for D5 timeline derivation (facts_extractor → timeline_events);
    # not persisted to the evidence_index table.
    facts: list[FactItem] = Field(default_factory=list)

    @field_validator("tier", mode="before")
    @classmethod
    def _normalize_tier(cls, v: object) -> int | None:
        """Normalize to the canonical source-tier taxonomy ([1, 7]) or None.

        This is the *universal* chokepoint: every parser path (CSV, JSON,
        workbook, handoff) constructs an ``EvidenceRow``. The previous
        behaviour clamped out-of-range labels (``T10-CONTRADICTORY`` → 8)
        and defaulted missing tiers to 5 — both FABRICATED tiers that
        polluted the evidence drawer's distribution ("Tier 8" rows,
        2026-07-06 QA). A tier the source doesn't state is now honestly
        None; the DB column is nullable (migration 059).
        """
        return normalize_tier(v)


class IssueRow(BaseModel):
    issue_id: str
    type: str | None = None
    severity: str
    status: str | None = None
    description: str
    evidence_ids: list[str] = Field(default_factory=list)
    cap_formula: str | None = None
    cap_ceiling: float | None = None
    affected_categories: list[str] = Field(default_factory=list)
    # ── DMA-impact attribution (2026-07-06 issue-register fix) ────────
    # `kind` separates the client's REAL business issues ('client' —
    # regulatory orders, breaches, market gaps) from the assessment
    # pipeline's own QA checklist rows ('assessment_qa' — run_manifest
    # missing, sheet-naming checks). Only 'client' rows surface on the
    # AE-facing Context register + heatmap overlay.
    kind: str = "client"
    regulator: str | None = None
    # ISO dates mined from Date / Date_Resolved columns (or from a
    # "Resolved Jan 2025"-style status cell). None when the package
    # carries no date — never fabricated.
    opened_on: str | None = None
    resolved_on: str | None = None
    # Per-capability cap levels mined from Capability_Impact /
    # Ceiling_Impact / Cap_Value cells ("CAPS P1C2 @3.0, P3C3 @2.5",
    # "P1C4 cap 4.0", numeric Cap_Value applied to affected ids).
    caps: dict[str, float] = Field(default_factory=dict)
    # One-line grounded rationale composed from the row's own fields
    # ("Caps P1C2 at M3.0, P3C3 at M2.5 — Regulatory (FDIC), open").
    dma_impact: str | None = None


class PeerScore(BaseModel):
    peer_id: str
    peer_name: str
    ticker: str | None = None
    assets: str | None = None
    rationale: str | None = None
    scores: dict[str, float] = Field(default_factory=dict)


class RecommendationRow(BaseModel):
    """Rich recommendation matching `08_appendices/recommendations_detail.json`."""
    model_config = ConfigDict(extra="allow")

    id: str
    priority: str | None = None
    title: str
    ownership: str | None = None
    technographic_status: str | None = None
    root_cause: dict | None = None
    solution: dict | None = None
    peer_benchmark: dict | None = None
    cross_pillar_unlock: str | None = None
    counter_arguments: list[dict] = Field(default_factory=list)
    expected_outcomes: list[dict] = Field(default_factory=list)
    strategic_objectives: list[str] = Field(default_factory=list)
    # Sibling rec_ids that must ship first, parsed from
    # recommendation_validation.json's `prerequisite` clause and attached by
    # the orchestrator (empty for the vast majority of the corpus).
    prerequisite_rec_ids: list[str] = Field(default_factory=list)


class TechStackRow(BaseModel):
    vendor: str
    product: str | None = None
    category: str | None = None
    layer: str | None = None
    confidence: float | None = None
    source: str | None = None
    # Prototype-aligned fields (2026-06-23). `status` is the deployment-state
    # enum the TechStack page renders as a pill; `l3_id` links the tech to one
    # of the five scored platform areas (D4). Both default to the honest
    # "inferred / unlinked" values when the source carries no signal.
    status: str = "DETECTED"   # DETECTED | CONFIRMED | CONFIRMED_REMOVED
    l3_id: str | None = None


class LeadershipPerson(BaseModel):
    name: str
    title: str | None = None
    tenure: str | None = None
    background: str | None = None


class Firmographics(BaseModel):
    model_config = ConfigDict(extra="allow")

    legal_name: str | None = None
    ticker: str | None = None
    hq: str | None = None
    founded: int | None = None
    total_assets: str | None = None
    employees_approx: str | None = None
    primary_regulator: str | None = None
    cra_rating: str | None = None
    leadership: list[LeadershipPerson] = Field(default_factory=list)
    # D5 Context: multi-year financial series (financials_view) + sentiment
    # grid. Populated from A#_financial_trends.csv / A#_sentiment_data.csv
    # and the client research report; persisted to the firmographics
    # financial_highlights / sentiment JSONB columns.
    financial_highlights: dict = Field(default_factory=dict)
    sentiment: dict = Field(default_factory=dict)
    # F5c (2026-06-07): the firmographics-narrative text extracted from
    # `04_reports/*_Client_Profile_Research_Report.docx` (`Entity Profile`
    # section). 200-1600 chars of analyst prose used by D5 Context page
    # for the "About" panel. Column on `firmographics` table already
    # exists via migration 018; this field threads it through the
    # parser → persistence → API → frontend cascade.
    narrative_md: str | None = None


class QaVerdict(BaseModel):
    model_config = ConfigDict(extra="ignore")

    verdict: str
    recommendation: str | None = None
    verdict_basis: str | None = None
    issue_count_genuine_only: dict[str, int] | None = None
    governance_skill_version: str | None = None


class ReportSectionRow(BaseModel):
    """A single section extracted from `04_reports/*.docx`.

    Populated by `parsers.assessment_report.parse_assessment_report`;
    consumed by `package_persist._persist_document_sections` to write
    `document_sections` + `document_lineage` rows.
    """
    model_config = ConfigDict(extra="forbid")

    kind: str  # SectionKind from assessment_report.SectionKind
    heading: str
    body: str
    ordinal: int
    page_number: int | None = None
    subcap_ids_mentioned: list[str] = Field(default_factory=list)
    e_ids_mentioned: list[str] = Field(default_factory=list)
    source_path: str | None = None


class FocusAreaRow(BaseModel):
    """A single focus area extracted from `04_reports/*Client_Profile*.docx`.

    Populated by `parsers.client_profile.parse_client_profile_path`;
    consumed by `package_persist._persist_focus_areas` to write
    `focus_areas` rows (migration 018 schema, reconciled in 023:
    title, verbatim_quote, source_path, page_number,
    involved_subcap_ids).

    Prior to 2026-05-29 finalization, focus areas were extracted by
    the client_profile parser but only the COUNT was logged — the
    rows were never propagated onto the IngestedPackage envelope,
    so the `focus_areas` table stayed empty in production despite
    every package containing them.
    """
    model_config = ConfigDict(extra="forbid")

    title: str
    verbatim_quote: str
    source_path: str | None = None
    page_number: int | None = None
    involved_subcap_ids: list[str] = Field(default_factory=list)


class ReasoningChainSubcap(BaseModel):
    """C7 (2026-06-07): one subcap's chain-of-thought decision path
    from the bot's `07_governance/reasoning_chain_log.json`.

    Nicola ships 12 subcap chains in the real fixture. Each
    `decision_path` is a 5-step list capturing the bot's actual
    reasoning (Evidence collection -> Tier classification -> M-level
    match -> Caps applied -> Critic review). Surfacing this on the
    D6 Health "Audit" tab gives analysts the BOT's actual rationale
    rather than a Vertex re-synthesis.
    """
    model_config = ConfigDict(extra="allow")
    subcap_id: str
    category: str | None = None
    decision_path: list[str] = Field(default_factory=list)


class ContradictionRow(BaseModel):
    """C7 (2026-06-07): one evidence contradiction from
    `07_governance/contradiction_log.csv`.

    Nicola + Odlum both ship the file. Each row describes a
    contradiction between two evidence sources, the resolution rule
    applied, the winner, the justification, and the confidence
    impact. Surfaces the bot's adjudication logic for analyst audit.
    """
    model_config = ConfigDict(extra="allow")
    contradiction_id: str
    subcap_id: str | None = None
    evidence_a_id: str | None = None
    evidence_b_id: str | None = None
    winner: str | None = None
    justification: str | None = None
    contradiction_type: str | None = None


class GovernanceAuditLogs(BaseModel):
    """C7 envelope: per-run bot governance audit logs.

    Currently surfaces:
      - reasoning_chain: list of subcap decision paths
      - contradictions: list of evidence dispute resolutions

    Source files (variable shipment per package):
      - 07_governance/reasoning_chain_log.json (Nicola)
      - 07_governance/contradiction_log.csv    (Nicola, Odlum)

    `None`-when-absent semantics on `IngestedPackage.audit_logs`
    distinguishes "package shipped no audit logs" (analyst tab shows
    empty state) from a query-time loading error.
    """
    model_config = ConfigDict(extra="allow")
    reasoning_chain: list[ReasoningChainSubcap] = Field(default_factory=list)
    contradictions: list[ContradictionRow] = Field(default_factory=list)


class AssumptionRow(BaseModel):
    """C11 (2026-06-07): one row of the analyst's assumptions register.

    2 of 5 real fixtures ship the register:
      - Calprivate `08_appendices/assumptions_register.json` (5 assumptions
        with id, category, assumption, confidence, basis, scoring_impact).
      - Nicola `07_governance/A9_Assumptions_Register.csv` (id, assumption,
        basis, confidence, validation_method, priority, capabilities_affected).

    Common fields land on the typed schema; per-source extras (category,
    scoring_impact, validation_method, priority, capabilities_affected)
    are tolerated via `extra='allow'` and round-trip via
    `model_dump()`. The frontend ClientOverview data-source footer
    renders the assumption + basis text so AE can answer "we assumed X
    because Y" on a sales call.
    """
    model_config = ConfigDict(extra="allow")

    id: str
    assumption: str
    basis: str | None = None
    confidence: str | None = None


class CapsAppliedRow(BaseModel):
    """One row of `07_governance/caps_applied_log.csv`.

    Surfaces "this subcap score is M-N.N because of a cap event" as
    defensible-rationale on D6 Health Gates tab. 4 of 5 real fixtures
    ship the log: Alma (8 caps), Calprivate (115), Nicola (8), Odlum
    (10). WSFS embeds equivalent data in `research_handoff.json`
    instead (its per-subcap `caps_applied` string covers the same
    semantics).
    """
    model_config = ConfigDict(extra="allow")

    log_id: str
    subcap_id: str
    cap_type: str | None = None
    trigger_condition: str | None = None
    cap_ceiling: str | None = None
    trigger_evidence: list[str] = Field(default_factory=list)
    affected_categories: list[str] = Field(default_factory=list)
    severity: str | None = None
    date_applied: str | None = None
    recalc_verified: str | None = None


class IngestedPackage(BaseModel):
    """Fully-parsed DMA package envelope. Persistence layer consumes this."""
    model_config = ConfigDict(extra="forbid")

    manifest: PackageManifest
    run_manifest: RunManifest
    pillar_weights: dict[str, float] | None = None
    pillar_scores: list[PillarScoreRow] = Field(default_factory=list)
    category_scores: list[CategoryScoreRow] = Field(default_factory=list)
    subcap_scores: list[SubcapScoreRow] = Field(default_factory=list)
    evidence: list[EvidenceRow] = Field(default_factory=list)
    # 2026-06-09: D5 timeline events derived from evidence facts[]
    # (facts_extractor). Entity-level; persisted to `timeline_events`.
    timeline_events: list[TimelineEventCandidate] = Field(default_factory=list)
    # 2026-06-09: D2 insight cards from section_analysis_#.json top_findings
    # (section_analysis parser). Persisted to `insight_cards` per run_id.
    insight_cards: list[InsightCardRow] = Field(default_factory=list)
    issue_register: list[IssueRow] = Field(default_factory=list)
    recommendations: list[RecommendationRow] = Field(default_factory=list)
    peers: list[PeerScore] = Field(default_factory=list)
    tech_stack: list[TechStackRow] = Field(default_factory=list)
    firmographics: Firmographics | None = None
    # `qa_verdict` is the L2 (full review) verdict — the canonical
    # field used since the initial parser. C5 (2026-06-07) keeps it
    # as L2/final and adds the new sibling `qa_verdict_l1`.
    qa_verdict: QaVerdict | None = None
    # C5 (2026-06-07): L1 (first-pass) verdict, distinct from the L2
    # final verdict above. 2 of 5 real fixtures ship both:
    #   Odlum     - 07_governance/L1_qa_verdict.json (verdict=PASS)
    #               + L2_qa_verdict.json (verdict=PASS_WITH_NOTES)
    #   Calprivate- 07_governance/Layer1_qa_verdict.json (PASS)
    #               + GOV_qa_verdict.json (PASS_WITH_NOTES)
    # Alma ships layer1_issue_register.json (issues, not verdict).
    # WSFS / Nicola only ship the L2 verdict.
    # Surfaces "did L1 pass and L2 then flag new issues?" on D6 Gates
    # tab — the 2-stage QA escalation chain that was invisible before.
    qa_verdict_l1: QaVerdict | None = None
    report_sections: list[ReportSectionRow] = Field(default_factory=list)
    focus_areas: list[FocusAreaRow] = Field(default_factory=list)
    # C10 (2026-06-07): cap-event log surfacing why scores were capped.
    # Persisted to `caps_applied_log` table (migration 028); D6 Health
    # Gates tab consumes via `/entities/{id}/health` payload.
    caps_applied_log: list[CapsAppliedRow] = Field(default_factory=list)
    # C11 (2026-06-07): assumptions register. 2 of 5 fixtures ship it
    # (Calprivate JSON + Nicola CSV). Persisted to `runs.assumptions_register`
    # JSONB (migration 030); D1 ClientOverview footer card renders the
    # rows so AE can answer "we assumed X because no public data on Y"
    # on sales calls.
    assumptions_register: list[AssumptionRow] = Field(default_factory=list)
    # C7 (2026-06-07): bot governance audit logs (reasoning chain +
    # contradictions). 2 of 5 fixtures ship at least one component.
    # Persisted to `runs.audit_logs` JSONB (migration 031); D6 Health
    # "Audit" tab (Analyst-only role gate) renders the bot's actual
    # reasoning + adjudication for analyst review and reviewer trust.
    audit_logs: GovernanceAuditLogs | None = None
    parser_warnings: list[str] = Field(default_factory=list)
    # Self-improvement observation log (2026-06 mandate). Parsers
    # populate this with structural surprises (unknown column headers,
    # sheet-name variants, subcap-ID formats outside the known regex).
    # `package_persist.persist_package` flushes these to the
    # `parser_observations` table via `record_parser_observation` so
    # the operator can promote recurring variants into the static
    # ALIASES dicts on the next deploy. Each entry shape:
    #   {"kind": str, "value": str, "canonical_guess": str | None,
    #    "sample_context": dict}
    parser_observations: list[dict[str, object]] = Field(default_factory=list)

    @property
    def expected_subcap_count(self) -> int:
        return len(self.subcap_scores)

    @property
    def evidence_count(self) -> int:
        return len(self.evidence)
