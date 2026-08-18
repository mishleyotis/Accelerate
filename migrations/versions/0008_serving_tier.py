"""Serving tier: 33 tables, one per payload section (Backend Schema §06)

Grain follows the doc's own two patterns: singular sections are one row
per run with sub-lists as JSONB (the overview_scores/pillars pattern);
item-list sections are one row per item with typed columns (the
evidence_age / techstack / cohort_patterns pattern). Item shapes come
from the Surface Specification's per-section contracts — no field is
invented; JSONB is used only where the contract itself nests objects.

Every table carries the universal envelope; producer_version and
promoted_at are NOT NULL ("every promoted row is attributable" — the
invariant that detects a write which bypassed promotion). Every table is
indexed on run_id (§09: the page query's hot path). Everything derivable
is generated: band from the raw score by the §09 four-branch function on
BOTH authorities (hero composite and grid cells — the fixture test
asserts DB ≡ frontend for every score); deltas; grounded_on =
cardinality(e_ids) (invariant 8); H7's age→band→status chain inlined
(PostgreSQL forbids generated-from-generated).

Section-level fields of item-grain sections (why_now.synthesis,
timeline.storyline/arc_shape, opportunity.discarded) are stored on every
row of their section — delete-then-insert promotion keeps them trivially
consistent; the writer registry (stage 2.1) owns that discipline.
heatmap_value_chain and insights_landscape are deliberately minimal:
H9/T2 render from server-derived arrangements and recomputed counts
(invariant 8) — their stored payloads are pinned at stage 6.

heatmap.safeguard_gates stores the caps[] (the §07 assessment_caps shape
— QA B-03: one section, two arrays); gates[] composes from gate_results
at read. alert_actions.alert_id gains its deferred FK here.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-04
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

# The universal envelope (§06). Two NOT NULLs per the invariant.
# ENVELOPE_RUN omits run_id — singular tables carry it as their PK line.
ENVELOPE = """
  run_id           UUID NOT NULL REFERENCES runs(id),
  entity_id        UUID REFERENCES entities(id),
  promoted_at      TIMESTAMPTZ NOT NULL,
  producer_version TEXT NOT NULL,
  provenance       provenance_t,
  e_ids            TEXT[],
  internal_only    TEXT[],
  empty_state      JSONB,
  r_layer          JSONB,
  narrative_thread TEXT,
  produced_at      TIMESTAMPTZ
"""

ENVELOPE_RUN = """
  entity_id        UUID REFERENCES entities(id),
  promoted_at      TIMESTAMPTZ NOT NULL,
  producer_version TEXT NOT NULL,
  provenance       provenance_t,
  e_ids            TEXT[],
  internal_only    TEXT[],
  empty_state      JSONB,
  r_layer          JSONB,
  narrative_thread TEXT,
  produced_at      TIMESTAMPTZ
"""

BAND_EXPR = """(
  CASE WHEN {col} IS NULL THEN NULL
       WHEN {col} < 2.0   THEN 'Activating'::band_t
       WHEN {col} < 3.0   THEN 'Building'::band_t
       WHEN {col} < 4.0   THEN 'Competing'::band_t
       ELSE 'Differentiating'::band_t END)"""

H7_AGE = """(
  CASE WHEN published_or_asof IS NULL OR reference_date IS NULL THEN NULL
       ELSE (EXTRACT(YEAR  FROM age(reference_date::timestamp, published_or_asof::timestamp))*12
           + EXTRACT(MONTH FROM age(reference_date::timestamp, published_or_asof::timestamp)))::int
  END)"""
H7_BAND = f"""(
  CASE WHEN {H7_AGE} IS NULL THEN 'undated'::age_band_t
       WHEN {H7_AGE} <= 12 THEN 'current'::age_band_t
       WHEN {H7_AGE} <= 24 THEN 'aging'::age_band_t
       WHEN {H7_AGE} <= 36 THEN 'dated'::age_band_t
       ELSE 'stale'::age_band_t END)"""
H7_STATUS = f"""(
  CASE WHEN {H7_BAND} = 'undated'::age_band_t THEN 'UNDATED'::age_status_t
       WHEN {H7_BAND} = 'current'::age_band_t THEN 'FRESH'::age_status_t
       WHEN {H7_BAND} = 'aging'::age_band_t   THEN 'AGING'::age_status_t
       WHEN {H7_BAND} = 'dated'::age_band_t   THEN 'DATED'::age_status_t
       ELSE 'STALE'::age_status_t END)"""

# name -> (body, grain) — grain 'run' means run_id is the PK; 'item' means
# BIGSERIAL id PK + run_id index.
TABLES: dict[str, tuple[str, str]] = {
    # ── Overview ────────────────────────────────────────────────────────
    "overview_scores": (f"""
        run_id       UUID PRIMARY KEY REFERENCES runs(id),   -- the hero is singular
        composite    NUMERIC(4,2),    -- mean of the four PILLAR means, rounded ONCE
        pillars      JSONB,           -- [{{pillar_id, score, peer_median, delta, peer_n, peer_basis, proxy_disclosure}}]
        posture      posture_t,
        posture_basis basis_t,
        framing      TEXT,            -- 18-32 words: states the gap, quantifies it, localises it
        band         band_t GENERATED ALWAYS AS {BAND_EXPR.format(col='composite')} STORED,
        claim_label  claim_t,
        confidence   confidence_t,
        {ENVELOPE_RUN}
    """, "run"),
    "overview_firmographics": (f"""
        id                     BIGSERIAL PRIMARY KEY,
        field                  TEXT,   -- sub-vertical decides WHICH fields (O2 step 0)
        value                  TEXT,
        unit                   TEXT,
        as_of                  DATE,
        recency_band           recency_t,   -- the evidence ladder governs all payload fields
        source_e_id            TEXT,
        confidence             confidence_t,
        quarantined            BOOLEAN,
        quarantine_reason      TEXT,
        sub_vertical_undefined BOOLEAN,     -- Farm Credit: emit and say so
        {ENVELOPE}
    """, "item"),
    "overview_why_now": (f"""
        id                     BIGSERIAL PRIMARY KEY,
        wn_id                  TEXT,
        trigger                TEXT,
        "window"               TEXT,   -- reserved word in PostgreSQL; the contract field name stands
        consequence_of_waiting TEXT,
        cost_of_acting_now     TEXT,   -- required: a signal with only upside is a pitch
        why_this_sequence      TEXT,
        linked_subcap_ids      TEXT[],
        dated_on               DATE,
        claim_label            claim_t,
        confidence             confidence_t,
        synthesis              TEXT,   -- section-level: what the signals TOGETHER say
        thin                   BOOLEAN,
        {ENVELOPE}
    """, "item"),
    "overview_exec_summary": (f"""
        run_id                UUID PRIMARY KEY REFERENCES runs(id),
        situation             TEXT,
        complication          TEXT,   -- the constraint AS A MECHANISM; must contain a causal connective
        question              TEXT,
        answer                TEXT,
        sequencing_rationale  TEXT,   -- the highest-value sentence in the document
        cost_of_delay         TEXT,
        claim_label           claim_t,
        {ENVELOPE_RUN}
    """, "run"),
    "overview_opportunity": (f"""
        id                  BIGSERIAL PRIMARY KEY,
        platform            TEXT,
        composite           NUMERIC(6,2),  -- Σ(priority × gap), normalised 0-100
        factors             JSONB,         -- [{{name, weight, value, contribution}}]; must sum to composite
        addressable_cells   JSONB,         -- [{{subcap_id, name, current, peer, gap, feature_that_addresses_it}}]
        relevance           NUMERIC(3,2),
        their_stack_context TEXT,
        rank                SMALLINT,
        rank_rationale      TEXT,
        discarded           JSONB,         -- section-level: [{{platform, reason, relevance}}]
        {ENVELOPE}
    """, "item"),
    "overview_findings": (f"""
        id                        BIGSERIAL PRIMARY KEY,
        f_id                      TEXT,
        title                     TEXT,   -- <=12 words, a CLAIM
        theme                     TEXT,
        consequence               TEXT,
        body                      TEXT,
        rejected_alternative      TEXT,
        strategic_alignment       TEXT,
        strategic_alignment_score NUMERIC(3,2),   -- the ranking key
        linked_subcap_ids         TEXT[],
        platform_chips            TEXT[],
        source_kind               TEXT,           -- retrieved · derived
        what_text                 TEXT,           -- drilldown: the structural fact
        why_text                  TEXT,           -- drilldown: the mechanism
        so_what_text              TEXT,           -- drilldown: the decision
        ranking_basis             TEXT,           -- alignment · impact_fallback
        claim_label               claim_t,
        confidence                confidence_t,
        {ENVELOPE}
    """, "item"),
    "overview_leadership": (f"""
        id             BIGSERIAL PRIMARY KEY,
        name           TEXT,
        title          TEXT,
        domain         TEXT,     -- data · digital channels · technology · risk
        appointed_on   DATE,
        tenure_months  INTEGER,
        as_of          DATE,     -- blocking: a name with no verification date does not render
        source_e_id    TEXT,
        relevance_note TEXT,     -- a roster without relevance is an org chart
        confidence     confidence_t,
        {ENVELOPE}
    """, "item"),
    "overview_financial_series": (f"""
        run_id          UUID PRIMARY KEY REFERENCES runs(id),   -- serves O8 and C6
        series          JSONB,     -- [{{period, value, unit, as_of, source_e_id, basis}}] oldest first
        basis           TEXT,      -- the metric definition; mixing definitions makes a fake trend
        trend           TEXT,      -- GROWING · STABLE · DECLINING · VOLATILE; NULL under 3 dated points
        cagr            NUMERIC(6,3),
        verified_sparse BOOLEAN,
        reading         TEXT,      -- 35-60 words: what the trajectory means for the assessment
        {ENVELOPE_RUN}
    """, "run"),
    "overview_sentiment": (f"""
        run_id       UUID PRIMARY KEY REFERENCES runs(id),
        ratings      JSONB,   -- [{{audience, source, rating, scale, n, as_of, url, e_id, trend_vs_prior}}]
        themes       JSONB,   -- [{{audience, theme, mapped_subcap_ids, cap_statement}}]
        gap_analysis JSONB,   -- the B2B/B2C and internal/external gaps
        {ENVELOPE_RUN}
    """, "run"),
    "overview_ceilings": (f"""
        id               BIGSERIAL PRIMARY KEY,
        category_id      TEXT,
        category_name    TEXT,
        ceiling          TEXT,           -- M1-M5 rubric level, or NULL: "Cannot reliably estimate"
        uncertainty_band NUMERIC(3,2),   -- base + URF modifiers; over ±0.8 -> ceiling NULL
        rationale        TEXT,           -- both halves: what evidence establishes + the absence that capped
        limiting_absence TEXT,           -- the research backlog for the next run
        urf_modifiers    TEXT[],         -- URF-01..URF-06, every modifier applied named
        claim_label      claim_t,
        confidence       confidence_t,
        {ENVELOPE}
    """, "item"),
    "overview_evidence_coverage": (f"""
        run_id                 UUID PRIMARY KEY REFERENCES runs(id),   -- serves O10 and O11
        overall_pct            NUMERIC(5,1),   -- never rounded across the gate
        per_pillar             JSONB,          -- [{{pillar_id, pillar_name, pct, cells_total, cells_covered, below_gate}}]
        gate_pct               NUMERIC(5,1),   -- 80: a HARD GATE, not a target
        denominator_definition TEXT,           -- REQUIRED and RENDERED
        note                   TEXT,
        tier_distribution      JSONB,          -- O11 census: {{item_count, fact_count, tiers[], claim_classes[], self_sourced_pct, mix_implication}}
        {ENVELOPE_RUN}
    """, "run"),
    "overview_thought_leadership": (f"""
        id                BIGSERIAL PRIMARY KEY,
        kind              TEXT,     -- LINKEDIN POST · CONFERENCE · ARTICLE · PODCAST · EARNINGS CALL · BLOG · PANEL
        published_on      DATE,     -- required; undated is excluded
        headline          TEXT,     -- as published, never rewritten
        quote             TEXT,     -- verbatim, 80-260 chars, never stitched
        author_name       TEXT,
        author_role       TEXT,     -- as stated AT THE TIME
        url               TEXT,
        linked_subcap_ids TEXT[],
        alignment         TEXT,     -- CORROBORATES · CONTRADICTS · EXTENDS (+clause); CONTRADICTS is never filtered
        e_id              TEXT,
        claim_label       claim_t,
        {ENVELOPE}
    """, "item"),
    # ── Insights ────────────────────────────────────────────────────────
    "insight_cards": (f"""
        id                      BIGSERIAL PRIMARY KEY,
        ic_id                   TEXT,
        title                   TEXT,
        pillar_id               TEXT,
        what_text               TEXT,
        why_text                TEXT,   -- the mechanism; no mechanism means observation
        so_what_text            TEXT,
        alternative_explanation TEXT,
        severity                TEXT,   -- critical · high · opportunity · info, justified by consequence
        severity_rationale      TEXT,
        linked_subcap_id        TEXT,   -- a cell THIS run scored; dead anchors are rejected
        affects                 TEXT[],
        linked_rec_id           TEXT,
        validation_question     TEXT,   -- a Discovery Question, never a toolkit diagnostic
        confidence              confidence_t,
        claim_label             claim_t,
        {ENVELOPE}
    """, "item"),
    "insights_landscape": (f"""
        run_id  UUID PRIMARY KEY REFERENCES runs(id),
        summary TEXT,   -- the strip's summary line; the four counts are NEVER
                        -- stored — recomputed from techstack_items at read (invariant 8)
        {ENVELOPE_RUN}
    """, "run"),
    # ── Heatmap ─────────────────────────────────────────────────────────
    "heatmap_workbook_scores": (f"""
        id               BIGSERIAL PRIMARY KEY,
        subcap_id        TEXT,
        name             TEXT,
        capability_id    TEXT,
        category_id      TEXT,
        pillar_id        TEXT,
        score            NUMERIC(4,2),   -- workbook pass-through; authoritative for the grid
        band             band_t GENERATED ALWAYS AS {BAND_EXPR.format(col='score')} STORED,
        peer_median      NUMERIC(4,2),
        delta            NUMERIC(4,2) GENERATED ALWAYS AS (score - peer_median) STORED,
        peer_n           SMALLINT,
        peer_basis       peer_basis_t,
        confidence       confidence_t,
        is_thin_evidence BOOLEAN,        -- semantic flags, never colour (invariant 7)
        below_threshold  BOOLEAN,
        is_primary_gap   BOOLEAN,
        source_cell      TEXT,
        {ENVELOPE}
    """, "item"),
    "heatmap_focus_areas": (f"""
        id               BIGSERIAL PRIMARY KEY,
        fa_id            TEXT,
        name             TEXT,
        verbatim_quote   TEXT,   -- the client's OWN words, 50-400 chars
        source_document  TEXT,
        source_page      INTEGER,   -- provenance triple: document + page + filename
        source_filename  TEXT,
        involved_subcap_ids TEXT[],
        entity_score     NUMERIC(4,2),   -- mean over involved cells, same grain as peer
        peer_score       NUMERIC(4,2),
        delta            NUMERIC(4,2) GENERATED ALWAYS AS (entity_score - peer_score) STORED,
        currency_status  TEXT,   -- CONFIRMED_CURRENT · AGING · SUPERSEDED · UNCONFIRMED
        currency_note    TEXT,
        new_evidence_ids TEXT[],
        {ENVELOPE}
    """, "item"),
    "heatmap_cell_evidence": (f"""
        id          BIGSERIAL PRIMARY KEY,
        subcap_id   TEXT,
        synthesis   TEXT,   -- labelled "on the N items above" in the drawer
        grounded_on INTEGER GENERATED ALWAYS AS (COALESCE(array_length(e_ids, 1), 0)) STORED,
                    -- invariant 8: the count of items reasoned over IS the citation list length
        claim_label claim_t,
        confidence  confidence_t,
        {ENVELOPE}
    """, "item"),
    "heatmap_value_chain": (f"""
        run_id   UUID PRIMARY KEY REFERENCES runs(id),
        chain_id TEXT,    -- which ccg_value_chains arrangement this run uses
        payload  JSONB,   -- server-derived arrangement; pinned at stage 6.3 (H9 has no prompt)
        {ENVELOPE_RUN}
    """, "run"),
    "heatmap_alerts": (f"""
        id                BIGSERIAL PRIMARY KEY,
        subcap_id         TEXT,
        score             NUMERIC(4,2),
        confidence        confidence_t,
        evidence_count    INTEGER,
        state             TEXT,     -- UNWORKED · WORKED_FOUND · WORKED_ABSENT (a count that merges these is useless)
        severity          TEXT,
        status            TEXT,     -- open · resolved · waived — the queue lifecycle alert_actions acts on
        sources_searched  TEXT[],
        queries_run       JSONB,    -- every query logged
        new_evidence_ids  TEXT[],
        justification     TEXT,     -- why the score is defensible on the evidence that DOES exist
        closure_condition TEXT,     -- the specific artefact that would close this alert
        runs_open         INTEGER,  -- 3+ with no queries_run escalates as a PROCESS defect
        created_at        TIMESTAMPTZ,
        {ENVELOPE}
    """, "item"),
    "heatmap_safeguard_gates": (f"""
        id                  BIGSERIAL PRIMARY KEY,
        cap_id              TEXT,          -- from the workbook's own cap log (IR-00N rows)
        kind                cap_kind_t,
        ceiling             TEXT,          -- a served score above its cap is a hard defect
        affected_categories TEXT[],
        rationale           TEXT,          -- the stated reason; never composed to explain a low score
        {ENVELOPE}
    """, "item"),
    "heatmap_evidence_age": (f"""
        id                BIGSERIAL PRIMARY KEY,
        reference_date    DATE NOT NULL,   -- PINNED and RENDERED; age is meaningless without it
        e_id              TEXT REFERENCES evidence_index(e_id),
        title             TEXT,
        source_domain     TEXT,
        published_or_asof DATE,            -- NULL is legal
        age_months        INTEGER GENERATED ALWAYS AS {H7_AGE} STORED,
        band              age_band_t GENERATED ALWAYS AS {H7_BAND} STORED,
        status            age_status_t GENERATED ALWAYS AS {H7_STATUS} STORED,
        identity_ok       BOOLEAN,
        identity_note     TEXT,
        {ENVELOPE}
    """, "item"),
    "heatmap_cohort_patterns": (f"""
        id                     BIGSERIAL PRIMARY KEY,
        sub_vertical           TEXT,
        category_id            TEXT,
        pattern_statement      TEXT,
        affected_count         INTEGER,
        cohort_size            INTEGER CONSTRAINT cohort_min CHECK (cohort_size >= 5),
        share_pct              NUMERIC(5,2) GENERATED ALWAYS AS
                                 (round(100.0 * affected_count / cohort_size, 2)) STORED,
        threshold_pct          NUMERIC(5,2),   -- declared, and enforced
        below_threshold        BOOLEAN GENERATED ALWAYS AS
                                 (round(100.0 * affected_count / cohort_size, 2) < threshold_pct) STORED,
        confidence             confidence_t,   -- derived from cohort size
        structural_explanation TEXT,
        action                 TEXT,
        entity_ids             UUID[],         -- AUDIT ONLY; always in internal_only; stripped from EVERY response
        {ENVELOPE}
    """, "item"),
    # ── Platform ────────────────────────────────────────────────────────
    "platform_story": (f"""
        run_id         UUID PRIMARY KEY REFERENCES runs(id),
        gap_rows       JSONB,   -- [{{subcap_id, name, current_score, peer_score, gap, pillar, l3_area, l4_feature, catalogue_path, e_ids}}]
        discarded      JSONB,   -- [{{platform, reason, relevance}}] — a ranking that cannot discard is a sort
        effort_profile JSONB,   -- ranked effort dimensions, consistent with the timeline's storyline
        story          TEXT,    -- 90-150 words: what it changes, lifts, depends on, does not solve
        {ENVELOPE_RUN}
    """, "run"),
    "platform_recommendations": (f"""
        id                BIGSERIAL PRIMARY KEY,
        rec_id            TEXT,    -- authored by the agent
        title             TEXT,
        l3_area           TEXT,
        l4_feature        TEXT,
        phase             TEXT,
        dma_impact        JSONB,   -- [{{subcap_id, name, current, target, delta}}]; current MUST equal the heatmap
        root_cause        TEXT,    -- cited; "score is low" is not a root cause
        cost_of_inaction  TEXT,    -- grounded, or "no dated trigger established"
        prerequisites     JSONB,   -- cells and minimums
        dependencies      TEXT[],  -- real predecessors only, no inversion
        sequencing_reason TEXT,    -- must agree with roadmap AND stair-step
        effort_band       TEXT,
        kpi_triple        JSONB,   -- {{metric, baseline, target}}; baseline exists in the pack with an as_of
        validation_gate   JSONB,   -- {{cell, threshold, verdict MET/NOT MET, backing_cells[]}}
        claim_label       claim_t,
        {ENVELOPE}
    """, "item"),
    "platform_starters": (f"""
        id                      BIGSERIAL PRIMARY KEY,
        rank                    SMALLINT,
        text                    TEXT,    -- 45-90 words; must pass the say-it-aloud test
        opens_on                TEXT,    -- the opening shape; at most one starter per shape
        named_gap_subcap_id     TEXT,
        peer_reference          TEXT,    -- a NAMED institution and a DATED action, or omitted
        their_system_reference  TEXT,
        followup_question       TEXT,
        {ENVELOPE}
    """, "item"),
    "platform_roadmap": (f"""
        id           BIGSERIAL PRIMARY KEY,
        phase        SMALLINT,   -- order is meaning
        horizon      TEXT,       -- plain terms: next 2 quarters / this year / beyond
        capabilities TEXT[],     -- the rec ids assigned to this phase; ids must resolve
        depends_on   TEXT[],     -- a phase cannot precede a phase it depends on
        rationale    TEXT,
        {ENVELOPE}
    """, "item"),
    "platform_stairstep": (f"""
        id                  BIGSERIAL PRIMARY KEY,
        theme               TEXT,       -- the curve is scoped to a theme
        step_level          SMALLINT,
        label               TEXT,
        covered_subcap_ids  TEXT[],
        current_position    BOOLEAN,    -- computed from the served scores; a measurement, not a judgement
        blocking_findings   TEXT[],     -- f_ids that exist elsewhere in the pack — THE POINT OF THE CARD
        unlocks             TEXT,
        effort_band         TEXT,       -- S · M · L, consistent with the platform effort profile
        entry_condition     TEXT,       -- matches the corresponding recommendation's validation_gate
        {ENVELOPE}
    """, "item"),
    # ── Context ─────────────────────────────────────────────────────────
    "context_timeline": (f"""
        id              BIGSERIAL PRIMARY KEY,
        event_date      DATE,     -- required to at least the month; undated is EXCLUDED, never 'ongoing'
        title           TEXT,
        body            TEXT,
        kind            TEXT,     -- PLATFORM · LEADERSHIP · M&A · REGULATORY · CHANNEL · DATA · SECURITY · STRATEGY
        signal          TEXT,     -- POSITIVE · NEUTRAL · NEGATIVE, with its score effect stated
        capability_ids  TEXT[],   -- an event bearing on none does not belong here
        maturity_effect TEXT,     -- ADVANCED · CONSTRAINED · NEUTRAL, one clause of reasoning
        claim_label     claim_t,
        storyline       TEXT,     -- section-level: how the sequence produced today's position
        arc_shape       TEXT,     -- STEADY_INVESTMENT · STOP_START · POST_EVENT_CATCHUP · LEGACY_ANCHORED · RECENT_ACCELERATION
        verified_sparse BOOLEAN,  -- set when fewer than 3 dated events
        {ENVELOPE}
    """, "item"),
    "context_issue_register": (f"""
        id                BIGSERIAL PRIMARY KEY,
        issue_id          TEXT,
        title             TEXT,
        severity          TEXT NOT NULL,
        status            TEXT NOT NULL,   -- never emit a NULL status
        opened_on         DATE,
        resolved_on       DATE,
        rationale         TEXT,            -- empty is honest; never composed to fill the panel
        linked_subcap_ids TEXT[],          -- the cells this issue caps
        {ENVELOPE}
    """, "item"),
    "context_regulatory_standing": (f"""
        run_id                 UUID PRIMARY KEY REFERENCES runs(id),
        primary_regulator      TEXT,     -- from the regulator's OWN registry; mismatch = identity error
        additional_regulators  TEXT[],
        license_type           TEXT,     -- constrains which capabilities can legitimately be assessed
        jurisdictions          TEXT[],   -- the fastest contamination check in the product
        charter_date           DATE,
        enforcement_actions    JSONB,    -- [{{issue_id, regulator, kind, opened_on, status, summary, capped_subcap_ids, remediation_status, e_id}}]
        absence_of_enforcement JSONB,    -- verified absence records the sources searched
        {ENVELOPE_RUN}
    """, "run"),
    "context_sentiment": (f"""
        run_id       UUID PRIMARY KEY REFERENCES runs(id),   -- O9's prompt at Context depth (C4)
        ratings      JSONB,
        themes       JSONB,
        gap_analysis JSONB,
        {ENVELOPE_RUN}
    """, "run"),
    "context_acquisitions": (f"""
        id                  BIGSERIAL PRIMARY KEY,
        closed_on           DATE,          -- required to the month; ANNOUNCED is a separate row
        target_name         TEXT,
        kind                TEXT,
        status              TEXT NOT NULL, -- ANNOUNCED · INTEGRATING · COMPLETE · ABANDONED
        scale_metrics       TEXT,          -- in the acquirer's own terms
        integration_target  TEXT,
        affected_subcap_ids TEXT[],
        maturity_effect     TEXT,          -- incl. TEMPORARILY_CONSTRAINED — never smoothed to NEUTRAL
        effect_note         TEXT,
        {ENVELOPE}
    """, "item"),
    # ── Tech stack (§06 verbatim) ───────────────────────────────────────
    "techstack_items": (f"""
        id                BIGSERIAL PRIMARY KEY,
        ts_id             TEXT,             -- agent-assigned, unique within the run
        name              TEXT,             -- a PRODUCT, not a service or category
        vendor            TEXT,
        layer             stack_layer_t,    -- OPS · CUST · DATA · INFRA (deliberately not L2-L5)
        pillar_id         TEXT,             -- which pillar absorbs a gap at this layer
        status            stack_status_t NOT NULL,   -- the landscape strip recomputes its counts from this
        evidence_level    evidence_level_t, -- L1-L4; governs the verb the prose may use
        detection_basis   TEXT,             -- PRINTED on the detail page
        linked_subcap_ids TEXT[],
        is_primary_gap    BOOLEAN,
        {ENVELOPE}
    """, "item"),
}


def upgrade() -> None:
    for name, (body, grain) in TABLES.items():
        op.execute(f"CREATE TABLE {name} ({body})")
        if grain == "item":
            op.execute(f"CREATE INDEX {name}_run ON {name} (run_id)")
    # §09: cursor pagination on the corpus-wide alerts queue.
    op.execute(
        "CREATE INDEX heatmap_alerts_queue ON heatmap_alerts (entity_id, status, created_at DESC)"
    )
    op.execute("CREATE UNIQUE INDEX techstack_items_ts_uq ON techstack_items (run_id, ts_id)")
    # Deferred from 0007 — the FK target now exists.
    op.execute(
        """
        ALTER TABLE alert_actions
          ADD CONSTRAINT alert_actions_alert_fk
          FOREIGN KEY (alert_id) REFERENCES heatmap_alerts(id)
        """
    )
    # Grants: the API reads every serving table; the connector is the only
    # writer (invariant 2 / §03).
    for name in TABLES:
        op.execute(f"GRANT SELECT ON {name} TO svc_api")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {name} TO svc_mcp")
    for name, (_, grain) in TABLES.items():
        if grain == "item":
            op.execute(f"GRANT USAGE ON SEQUENCE {name}_id_seq TO svc_mcp")


def downgrade() -> None:
    op.execute("ALTER TABLE alert_actions DROP CONSTRAINT IF EXISTS alert_actions_alert_fk")
    for name in reversed(list(TABLES)):
        op.execute(f"DROP TABLE IF EXISTS {name}")
