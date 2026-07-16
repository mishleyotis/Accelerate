"""Per-surface completeness contract (self-healing pipeline, all stages).

The mandate: **no empty state on any page, card, or drilldown for any of the 94
ACTIVE clients on deployment.** This module is the single source of truth for
*what must render* on each surface, consumed by both the data-completeness gate
(`app.scripts.heal_all_stages`) and the render auditor
(`app.scripts.qa_render_validation`), so "complete" is defined once.

The boundary (no fabrication): a surface FAILS the gate only on a **data-absence
empty** the pipeline can fill from the package. A documented **expected-empty
allowlist** is permitted — honest-zero alerts (full evidence coverage is a *good*
signal), RBAC-stripped customer fields, and the genuine firmographics gaps the
healer already reports (e.g. an undisclosed headcount where the panel is still
rich). Each requirement maps to the derive/heal stage that fills it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class SurfaceReq:
    surface: str
    requires: str            # human-readable required-non-empty contract
    filled_by: str           # the derive/heal stage that fills it
    expected_empty: str = ""  # documented allowed-empty conditions


# The contract table (mirrors the approved plan's Part A). Order = render order.
SURFACE_CONTRACTS: tuple[SurfaceReq, ...] = (
    SurfaceReq("directory", "name (not drive-id), subvertical, pillar_scores, overall, top_platform",
               "repark_junk_entities + heal_entities + apply_catalogue_platforms",
               "top_platform only if no platform reaches fit>0"),
    SurfaceReq("overview", "pillar_scores(>=4), overall, firmographics panel, why_now/top_findings, scqa",
               "scores + heal_entities + derive_insights", "narrative_md if no Assessment DOCX"),
    SurfaceReq("insights", ">=1 insight card with WHAT/WHY/SO-WHAT text",
               "derive_insights", "counter_e_ids may be empty"),
    SurfaceReq("heatmap", ">=1 subcap cell with score in [1,5]",
               "ingest scores + broadcast_peer_medians", "peer_median if cohort uncovered"),
    SurfaceReq("platform", ">=1 platform with fit_score>0 + addressable subcaps",
               "apply_catalogue_platforms", "INSUFFICIENT_EVIDENCE if no addressable subcap"),
    SurfaceReq("context", ">=1 timeline event; financials when firmographics ship them",
               "derive_context + heal_entities", "acquisitions/issue_register may be empty"),
    SurfaceReq("techstack", ">=1 tech stack entry",
               "ingest (Explorium/research)", "peer_adoption_count may be 0"),
    SurfaceReq("health", "subcap thin-evidence audit present (alerts may be honest-zero)",
               "ingest + derive_alerts", "zero alerts when evidence coverage is full"),
    SurfaceReq("recommendations", ">=1 recommendation (powers the D4 roadmap drilldown)",
               "ingest + derive_recommendations (grounded gap→platform inference)", ""),
    SurfaceReq("intelligence", "D1 persistent-intelligence profile + summary",
               "intelligence_recompute --all (deterministic rollup when Vertex cold)", ""),
)


@dataclass
class CompletenessReport:
    active: int = 0
    gaps: dict[str, list[str]] = field(default_factory=dict)  # surface -> [display_id]

    @property
    def total_gaps(self) -> int:
        return sum(len(v) for v in self.gaps.values())

    def add(self, surface: str, display_id: str) -> None:
        self.gaps.setdefault(surface, []).append(display_id)


# Each surface's data-absence test: a SQL fragment returning the display_ids of
# ACTIVE entities whose ACTIVE run lacks the required data. Expected-empty
# conditions are encoded directly in the predicates (e.g. health is never a
# gap — honest-zero alerts are allowed; the thin-evidence audit always renders).
_SURFACE_GAP_SQL: dict[str, str] = {
    # name still a drive-id / folder-artifact, or subvertical missing
    "directory": """
        SELECT e.display_id FROM entities e
        WHERE e.status='ACTIVE' AND (
            e.name IS NULL OR e.name = '' OR e.subvertical IS NULL
            OR e.display_id ~ '^[0-9a-f]{16,}' OR e.name ~* 'drive|folder|untitled'
        )""",
    "overview": """
        SELECT e.display_id FROM entities e JOIN runs r ON r.entity_id=e.id AND r.status='ACTIVE'
        WHERE e.status='ACTIVE' AND NOT EXISTS (
            SELECT 1 FROM subcap_scores s WHERE s.run_id=r.id AND s.score IS NOT NULL)""",
    # Firmographics panel: a headline SCALE figure + the regulator. The scale is
    # usually a balance-sheet number (aum_usd), but a balance-sheet-less entity —
    # a member-funded payments utility / clearing house (Payments Canada) has no
    # AUM and no revenue line — is sized by headcount + transaction-volume
    # highlights instead. Accept aum_usd OR revenue_usd OR headcount as the scale;
    # the regulator is always fillable (heal_entities subvertical default).
    "firmographics": """
        SELECT e.display_id FROM entities e
        WHERE e.status='ACTIVE' AND NOT EXISTS (
            SELECT 1 FROM firmographics f WHERE f.entity_id=e.id
              AND COALESCE(f.primary_regulator,'')<>''
              AND (f.aum_usd IS NOT NULL OR f.revenue_usd IS NOT NULL
                   OR f.headcount IS NOT NULL))""",
    "insights": """
        SELECT e.display_id FROM entities e JOIN runs r ON r.entity_id=e.id AND r.status='ACTIVE'
        WHERE e.status='ACTIVE' AND NOT EXISTS (
            SELECT 1 FROM insight_cards ic WHERE ic.run_id=r.id
              AND (COALESCE(ic.what_text,'')<>'' OR COALESCE(ic.title,'')<>''))""",
    "heatmap": """
        SELECT e.display_id FROM entities e JOIN runs r ON r.entity_id=e.id AND r.status='ACTIVE'
        WHERE e.status='ACTIVE' AND NOT EXISTS (
            SELECT 1 FROM subcap_scores s WHERE s.run_id=r.id AND s.score BETWEEN 1 AND 5)""",
    "platform": """
        SELECT e.display_id FROM entities e JOIN runs r ON r.entity_id=e.id AND r.status='ACTIVE'
        WHERE e.status='ACTIVE' AND NOT EXISTS (
            SELECT 1 FROM platform_scores ps WHERE ps.run_id=r.id AND ps.fit_score>0)""",
    "context": """
        SELECT e.display_id FROM entities e
        WHERE e.status='ACTIVE' AND NOT EXISTS (
            SELECT 1 FROM timeline_events te WHERE te.entity_id=e.id)""",
    # D5 Financial-trajectory card must never read "No financials on record":
    # derive_financials mines the report's multi-year table / ratios, and falls
    # back to the already-healed balance-sheet scale (aum_usd) so the card always
    # carries at least the grounded headline figure.
    "financials": """
        SELECT e.display_id FROM entities e
        WHERE e.status='ACTIVE' AND NOT EXISTS (
            SELECT 1 FROM firmographics f WHERE f.entity_id=e.id
              AND f.financial_highlights IS NOT NULL
              AND f.financial_highlights::text NOT IN ('{}', 'null'))""",
    "techstack": """
        SELECT e.display_id FROM entities e
        WHERE e.status='ACTIVE' AND NOT EXISTS (
            SELECT 1 FROM tech_stack_entries ts WHERE ts.entity_id=e.id)""",
    # platform roadmap drilldown — needs >=1 recommendation to sequence
    "recommendations": """
        SELECT e.display_id FROM entities e JOIN runs r ON r.entity_id=e.id AND r.status='ACTIVE'
        WHERE e.status='ACTIVE' AND NOT EXISTS (
            SELECT 1 FROM recommendations rc WHERE rc.run_id=r.id)""",
    # Anti-shallow: the Overview why-now strip must carry DETAILED signals, not
    # category-name one-liners — every active run needs >=3 signals whose
    # longest text is a full sentence (>=60 chars). deepen_narrative fills these.
    "why_now_depth": """
        SELECT e.display_id FROM entities e JOIN runs r ON r.entity_id=e.id AND r.status='ACTIVE'
        WHERE e.status='ACTIVE' AND (
            r.why_now_signals IS NULL
            OR jsonb_array_length(COALESCE(r.why_now_signals,'[]'::jsonb)) < 3
            OR COALESCE((SELECT MAX(length(s->>'text')) FROM jsonb_array_elements(r.why_now_signals) s), 0) < 60
        )""",
    # Anti-shallow prose: no insight card may be a one-/two-liner. The WHAT must
    # be a real paragraph (>=160 chars) AND the WHY must explain business impact
    # (>=100 chars) — deepen_narrative composes both. The Context "About"
    # narrative must be a real paragraph (>=120 chars).
    "insight_depth": """
        SELECT e.display_id FROM entities e JOIN runs r ON r.entity_id=e.id AND r.status='ACTIVE'
        WHERE e.status='ACTIVE' AND EXISTS (
            SELECT 1 FROM insight_cards ic WHERE ic.run_id=r.id
              AND (length(COALESCE(ic.what_text,'')) < 160
                   OR length(COALESCE(ic.why_text,'')) < 100))""",
    # No-jargon: a stakeholder must never see raw taxonomy codes (P2C1.1.1),
    # maturity-band shorthand (M5), or consultant-speak ("priority lever",
    # "peer-cohort", "cross-pillar", "the pillar", "subcap") in any user-facing
    # insight PROSE. deepen_narrative composes plain-business language.
    # Bracketed evidence-anchor citations ("[E-P1C5-003, E-Digital
    # Strategy-012]") are STRUCTURED grounding references — their E-IDs
    # may legitimately embed a taxonomy code (the research workbook keys
    # some evidence by subcap id), they resolve to evidence_index rows by
    # exact string, and rewriting them would sever the grounding chain.
    # The code test therefore runs on the field with anchor spans
    # stripped (2026-07-05: security-finance's code-keyed E-IDs
    # false-flagged 3 entities the heal could not touch without
    # corrupting citations).
    #
    # Belt-and-braces on top of the anchor strip: a RAW code token IS
    # jargon, but an EVIDENCE-ID citation whose id encodes the pillar
    # OUTSIDE a bracketed span ("EV-P2C1-010", "INT-P1C1-002") is still
    # legitimate grounding and MUST NOT be flagged (2026-07-07:
    # first-citizens / security-finance evidence uses the E-P#C#-### id
    # form, protected verbatim by text_hygiene.plain). The
    # `(^|[^-A-Za-z0-9])` guard fires only on a standalone code token —
    # a code inside E-/EV-/INT- is preceded by `-` and skipped.
    "insight_jargon": r"""
        SELECT e.display_id FROM entities e JOIN runs r ON r.entity_id=e.id AND r.status='ACTIVE'
        WHERE e.status='ACTIVE' AND EXISTS (
            SELECT 1 FROM insight_cards ic WHERE ic.run_id=r.id AND (
                regexp_replace(ic.what_text, '\[E-[^\]]*\]', '', 'g') ~ '(^|[^-A-Za-z0-9])P[1-4]C[0-9]'
                OR regexp_replace(COALESCE(ic.why_text,''), '\[E-[^\]]*\]', '', 'g') ~ '(^|[^-A-Za-z0-9])P[1-4]C[0-9]'
                OR regexp_replace(COALESCE(ic.so_what_text,''), '\[E-[^\]]*\]', '', 'g') ~ '(^|[^-A-Za-z0-9])P[1-4]C[0-9]'
                OR ic.title ~ '(^|[^-A-Za-z0-9])P[1-4]C[0-9]'
                OR (ic.what_text || ' ' || COALESCE(ic.why_text,'') || ' '
                    || COALESCE(ic.so_what_text,'')) ~* 'peer[- ]cohort|priority lever|cross[- ]pillar|the pillar|\yM5\y'
                OR ic.title ~* 'sub-?cap'))""",
    "about_narrative": """
        SELECT e.display_id FROM entities e
        WHERE e.status='ACTIVE' AND NOT EXISTS (
            SELECT 1 FROM firmographics f WHERE f.entity_id=e.id
              AND length(COALESCE(f.narrative_md,'')) >= 120)""",
    # D1 persistent-intelligence card — deterministically computed for all 94
    "intelligence": """
        SELECT e.display_id FROM entities e
        WHERE e.status='ACTIVE' AND NOT EXISTS (
            SELECT 1 FROM customer_intelligence_profiles cip
            WHERE cip.entity_id=e.id AND cip.intelligence_summary_md IS NOT NULL)""",
    # health: never a data-absence gap — the thin-evidence audit always renders
    # from subcap_scores (covered by heatmap), and zero alerts is an allowed
    # honest-empty (full evidence coverage). No SQL → no gap by contract.
}


async def audit_completeness(session: AsyncSession) -> CompletenessReport:
    """Run every surface's data-absence test; return per-surface gap display_ids."""
    rep = CompletenessReport()
    rep.active = int((await session.execute(text(
        "SELECT count(*) FROM entities WHERE status='ACTIVE'"))).scalar() or 0)
    for surface, sql in _SURFACE_GAP_SQL.items():
        rows = (await session.execute(text(sql))).all()
        for r in rows:
            rep.add(surface, r.display_id)
    return rep


# ── insight_jargon remedy (owned here, next to its gate) ──────────────
# The `insight_jargon` gap query above is the DETECTOR; this scrubber is
# the matching deterministic REMEDY, applied by heal_all_stages' heal
# mode so the verify-only gate converges to zero without Vertex. The
# render-path `language_rewrite` ruleset does NOT cover these patterns
# (disjoint rulesets — proven 2026-07-05: rendered-language audit green
# while this gate flagged 14 entities), so the fix must live DB-side.
#
# No-fabrication boundary: taxonomy codes are replaced by their real
# catalogue names (caller supplies {code: name} from ccg_subcaps +
# ccg_categories); consultant-speak maps to fixed plain-business
# equivalents; nothing numeric or factual is invented.

_JARGON_CODE_RX = re.compile(r"\bP[1-4]C\d+(?:\.\d+)*")
_JARGON_FALLBACK = "this capability"
# Bracketed evidence-anchor spans are preserved verbatim (see the
# insight_jargon SQL comment above — rewriting an E-ID severs its link
# to evidence_index).
_ANCHOR_SPAN_RX = re.compile(r"\[E-[^\]]*\]")
# A catalogue "name" that is itself a code or contains jargon must never
# be used as a replacement (the v7 workbook carries at least one
# category whose name IS its code — P1C5 — which made the scrub an
# identity no-op on exactly the rows that needed it).
_JARGON_ANY_RX = re.compile(
    r"P[1-4]C\d|\bM5\b|peer[- ]cohort|priority lever|cross[- ]pillar"
    r"|the pillar|sub-?cap",
    re.IGNORECASE,
)
# Plural forms FIRST so "subcaps" never leaves a trailing "s".
_JARGON_PHRASES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsub-?caps\b", re.IGNORECASE), "capability areas"),
    (re.compile(r"\bsub-?cap\b", re.IGNORECASE), "capability area"),
    (re.compile(r"\bpeer[- ]cohorts\b", re.IGNORECASE), "peer groups"),
    (re.compile(r"\bpeer[- ]cohort\b", re.IGNORECASE), "peer group"),
    (re.compile(r"\bpriority levers\b", re.IGNORECASE), "priority initiatives"),
    (re.compile(r"\bpriority lever\b", re.IGNORECASE), "priority initiative"),
    (re.compile(r"\bcross[- ]pillar\b", re.IGNORECASE), "cross-domain"),
    (re.compile(r"\bthe pillars\b", re.IGNORECASE), "the assessment areas"),
    (re.compile(r"\bthe pillar\b", re.IGNORECASE), "the assessment area"),
    (re.compile(r"\bM5\b"), "level 5"),
)


def scrub_insight_jargon(
    source: str,
    code_names: dict[str, str] | None = None,
    *,
    prefer_fallback: bool = False,
) -> str:
    """Rewrite one user-facing insight field to plain business language.

    Taxonomy codes (P1C1.5.1 / P2C4) resolve through ``code_names`` —
    exact id first, then the category prefix (before the first dot) —
    else the neutral ``this capability``. ``prefer_fallback=True``
    forces the fallback for every code: since the fallback and every
    phrase replacement is at least as long as what it replaces, this
    mode can never shrink the text below the insight_depth floors
    (heal_all_stages re-runs in this mode when a resolved name is
    shorter than its code and the field would dip under the floor).
    Idempotent: output contains none of the detector's patterns.
    """
    names = code_names or {}

    def _resolve(m: re.Match[str]) -> str:
        code = m.group(0)
        if not prefer_fallback:
            name = (names.get(code) or names.get(code.split(".", 1)[0]) or "").strip()
            # Reject identity / jargon-bearing "names" — they would make
            # the scrub a no-op (or re-introduce a flagged pattern).
            if name and not _JARGON_ANY_RX.search(name):
                return name
        return _JARGON_FALLBACK

    def _scrub_prose(chunk: str) -> str:
        out = _JARGON_CODE_RX.sub(_resolve, chunk)
        for rx, replacement in _JARGON_PHRASES:
            out = rx.sub(replacement, out)
        # Tidy artifacts a mid-sentence replacement can leave behind.
        out = re.sub(r"\(\s*\)", "", out)
        out = re.sub(r"\s+([,.;:)])", r"\1", out)
        out = re.sub(r"\(\s+", "(", out)
        out = re.sub(r"[ \t]{2,}", " ", out)
        return out

    # Split out [E-...] anchor spans; scrub only the prose between them.
    pieces: list[str] = []
    last = 0
    for m in _ANCHOR_SPAN_RX.finditer(source):
        pieces.append(_scrub_prose(source[last:m.start()]))
        pieces.append(m.group(0))  # anchor span verbatim
        last = m.end()
    pieces.append(_scrub_prose(source[last:]))
    return "".join(pieces).strip()
