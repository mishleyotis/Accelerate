"""Deterministic platform fit-score computation (engine v2).

Engine v1 (kept for the legacy ingest path) scored fit as
``mean(gap x severity) x breadth`` only. The 2026-06 platform audit
measured the consequences across 94 clients: 95/470 cards were "red but
hot" (fit ≥ 80 while every readiness prerequisite was failing), 42/470
clamped at 99.9 (4 clients with all-5-identical cards), the per-subcap
contributions were computed then thrown away, and INSUFFICIENT_EVIDENCE
was unreachable (state 470/470 READY).

Engine v2 (Part 7.1 of the remediation plan) fixes each measured defect:

  opportunity  = gap x severity x evidence_strength     (per subcap, 0..1)
  interconnect = catalogue-adjacency uplift             (closing an addressable
                                                         subcap lifts sibling
                                                         gap subcaps in the same
                                                         category / value-chain
                                                         stage)
  absent_boost = confirmed-ABSENT platform family       (greenfield opportunity
                                                         from tech_stack_entries)
  readiness    = multiplier from prereq_checks          (folded IN — red gates
                                                         the blend below the hot
                                                         threshold, so
                                                         fit ≥ 80 ∧ red is
                                                         arithmetically
                                                         impossible)

  fit = 100 · (w_opp·opportunity + w_int·interconnect + w_abs·absent_boost)
            · readiness_multiplier

Target band is **M4 (4.0)** — unified with the router / derive_recommendations
target (the v1 engine targeted M5 while the router's gap math targeted M4;
the audit flagged the mismatch). GAP_DENOM normalises the gap over the
M1→M4 runway (3.0).

De-clamping: scores cap at 99.0 and exact within-run ties are separated
deterministically (evidence density, then absent boost, then platform id)
so no client renders five identical cards.

State honesty: ``state_for()`` returns INSUFFICIENT_EVIDENCE when the
platform has no addressable subcaps OR its addressable evidence strength
sits below ``EVIDENCE_FLOOR`` — the branch the audit found unreachable.

Every factor is persisted via ``build_breakdown()`` into
``platform_scores.fit_breakdown`` (migration 053) together with the top
contributing subcaps and their E-IDs — the traceability mandate.

Sequencing: ``compute_sequence_ranks()`` orders the five platforms in a
prerequisite DAG (platform A precedes B when A addresses a failing
prerequisite subcap of B, or when B's recommendations list A's
recommendations as prerequisites) → ``platform_scores.sequence_rank``.

No LLM here. Every function is pure (depends only on input rows).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Severity → priority MULTIPLIER (not a fraction): a critical-linked gap is the
# most valuable to close, a low-linked one the least. Centred on 1.0 (medium) so
# an unlinked subcap scores its raw opportunity.
SEVERITY_WEIGHTS: dict[str, float] = {
    "critical": 1.6,
    "high": 1.3,
    "medium": 1.0,
    "low": 0.85,
    "opportunity": 1.0,
}

# TARGET BAND — M4 ("Differentiating"). Unified with the router's gap math
# and derive_recommendations._TARGET_BAND (both 4.0). v1 targeted M5, which
# meant the engine and the router disagreed about what "the gap" was — the
# audit's target-band mismatch finding. GAP_DENOM = 4.0 - floor(1.0).
DEFAULT_TARGET_BAND_SCORE = 4.0
GAP_DENOM = 3.0
# A platform with this many addressable subcaps gets the full breadth bonus.
BREADTH_FULL = 40.0

# ── v2 calibration ─────────────────────────────────────────────────────
# Factor weights (sum to 1.0). Catalogue-grounded opportunity leads;
# interconnect is secondary; the absent/greenfield term is a small nudge —
# the 2026-07-14 skew audit measured the prior 0.15 blanket absence bonus
# systematically top-ranking whatever families the client happened to lack
# (nCino/Databricks on 20 of 28 sampled clients).
W_OPPORTUNITY = 0.66
W_INTERCONNECT = 0.26
W_ABSENT = 0.08

# Marginal-opportunity multiplier for a gapped subcap the customer's
# installed third-party incumbent already delivers (v7 L4 coverage). Halves
# — not zeroes — the contribution: the Zennify platform can still improve or
# integrate the capability, but it is not net-new ground (2026-07-14).
INCUMBENT_COVERAGE_DISCOUNT = 0.5

# Readiness multiplier — the "fold prereqs IN" gate. Red caps the maximum
# reachable fit at 100·1.0·0.62 = 62 (< the 80 "hot" threshold), so a
# red-readiness platform can never render hot. Amber is a soft penalty.
READINESS_MULTIPLIER: dict[str, float] = {
    "green": 1.00,
    "amber": 0.85,
    "red": 0.62,
}

# Evidence-strength prior for subcaps with a score but no linked evidence
# rows: the score itself came from *some* corpus signal, so we don't zero
# the opportunity — we discount it below fully-evidenced subcaps.
NEUTRAL_EVIDENCE_STRENGTH = 0.55
# Evidence dampening band: strength scales the per-subcap opportunity
# within [ES_DAMP_FLOOR, 1.0] rather than multiplying it away — a real
# gap with thin public evidence is still a gap, just less bankable.
ES_DAMP_FLOOR = 0.6
# Below this mean evidence strength over the TOP contributing subcaps
# (the ones actually driving the score) the card is honest about its
# grounding: INSUFFICIENT_EVIDENCE.
EVIDENCE_FLOOR = 0.10

# Hard ceiling — de-clamped from the v1 ubiquitous 99.9 spike. Ties at or
# near the cap are separated by `separate_ties`.
FIT_CAP = 99.0

# Tier → weight, mirroring the prototype EVIDENCE_TIERS table (T1 primary
# disclosure … T8 social/hypothesis).
TIER_WEIGHTS: dict[int, float] = {
    1: 1.00, 2: 0.92, 3: 0.80, 4: 0.55, 5: 0.50, 6: 0.45, 7: 0.42, 8: 0.25,
}
# Freshness band → multiplier (evidence_staleness bands).
FRESHNESS_WEIGHTS: dict[str, float] = {
    "current": 1.00, "aging": 0.90, "dated": 0.75, "stale": 0.55,
    "undated": 0.70,
}


@dataclass
class SubcapForFit:
    subcap_id: str
    current_score: float                       # 1.0..5.0
    platform_ids: list[str]                    # both per-entity tags and catalogue links
    linked_insight_severities: list[str]       # ['critical', 'high'] etc., dedup'd
    target_band_score: float = DEFAULT_TARGET_BAND_SCORE
    # ── v2 additive inputs (None/empty ⇒ v1-compatible behaviour) ──
    name: str | None = None                    # catalogue display name
    peer_median: float | None = None
    category_id: str | None = None             # e.g. "P4C1" (adjacency)
    vc_stages: list[str] = field(default_factory=list)  # value-chain stages
    evidence_e_ids: list[str] = field(default_factory=list)
    # Precomputed 0..1 strength from tier/recency of the subcap's linked
    # evidence (see `evidence_strength`). None ⇒ neutral prior.
    evidence_strength: float | None = None
    # Best (lowest) evidence tier backing this subcap — the gap table's
    # tier-chip. None when no evidence at any ladder rung.
    evidence_tier: int | None = None


@dataclass
class PlatformFitRow:
    platform_id: str
    fit_score: float
    addressable_subcap_ids: list[str]


@dataclass
class PlatformFitV2Row:
    platform_id: str
    fit_score: float
    state: str                                  # READY | INSUFFICIENT_EVIDENCE
    readiness: str                              # green | amber | red
    addressable_subcap_ids: list[str]
    evidence_strength: float                    # mean over addressable subcaps
    breakdown: dict                             # JSON-ready fit_breakdown
    sequence_rank: int | None = None
    absent_count: int = 0
    top_subcap_names: list[str] = field(default_factory=list)


def evidence_strength(
    tiers: list[int | None],
    freshness_bands: list[str] | None = None,
) -> float:
    """0..1 strength of a subcap's evidence from tier + freshness.

    Best item dominates (a single 10-K beats five tweets); density adds a
    bounded uplift (corroboration matters, hoarding doesn't). Empty ⇒ 0.
    """
    if not tiers:
        return 0.0
    bands = list(freshness_bands or [])
    per_item: list[float] = []
    for i, tier in enumerate(tiers):
        # None = unknown tier (honest-absent) → the same conservative
        # floor weight an unrecognized tier already got.
        tw = TIER_WEIGHTS.get(int(tier), 0.25) if tier is not None else 0.25
        fb = bands[i] if i < len(bands) else "undated"
        per_item.append(tw * FRESHNESS_WEIGHTS.get(fb, 0.70))
    best = max(per_item)
    density = min(1.0, len(per_item) / 4.0)
    return round(min(1.0, best * (0.75 + 0.25 * density)), 4)


def stack_alignment(
    *,
    absent_family: bool,
    absent_count: int = 0,
    peer_coverage: float | None = None,
) -> float:
    """Graded current-stack fit factor 0..1 (platform v3 calibration) — the
    refinement of the binary ``absent_boost`` the audit flagged
    (``platform_fit_data`` fed the confirmed/absent stack in only as a 0/1
    regex, discarding the CONFIRMED/INFERRED rows and peer_coverage).

    A confirmed-ABSENT pitched family is greenfield; the factor grades HOW
    greenfield by the cohort ``peer_coverage`` prior — a family the entity's
    peers broadly deploy but this entity lacks is a higher-conviction
    greenfield than one nobody in the cohort runs. A family already present
    scores 0 (no greenfield boost — matches the binary), so this only ever
    REFINES the confirmed-absent branch.

    2026-07-14 recalibration: the prior base ``0.7 + 0.075*absent_count``
    REWARDED absence breadth (more missing products ⇒ higher alignment) and
    floored peer coverage at 0.9 — both flagged by the skew audit as the
    arithmetic behind 70+ cards sitting next to "0% of cohort peers deploy
    it" notes. ``absent_count`` is now a badge input only; the anchor is
    cohort adoption: cov=0 → 0.45, cov=1 → 1.0, no cohort data → a neutral
    0.70 prior.
    """
    if not absent_family:
        return 0.0
    if peer_coverage is None:
        return 0.70
    cov = max(0.0, min(1.0, float(peer_coverage)))
    return round(0.45 + 0.55 * cov, 4)


def _severity_multiplier(severities: list[str]) -> float:
    if not severities:
        return SEVERITY_WEIGHTS["medium"]
    return max(SEVERITY_WEIGHTS.get(s, 1.0) for s in severities)


def _subcap_opportunity(sc: SubcapForFit) -> float:
    """Per-subcap opportunity 0..1: gap-to-M4 x severity x evidence strength.

    Evidence strength dampens within [ES_DAMP_FLOOR, 1.0]: a fully-
    evidenced gap counts in full; a gap with zero linked evidence still
    counts at the floor (the score row itself is a corpus signal) — the
    honesty branch for truly ungrounded platforms is the state machine
    (EVIDENCE_FLOOR → INSUFFICIENT_EVIDENCE), not silent score erasure.
    """
    gap = max(0.0, sc.target_band_score - sc.current_score)
    if gap == 0.0:
        return 0.0
    es = (
        sc.evidence_strength
        if sc.evidence_strength is not None
        else NEUTRAL_EVIDENCE_STRENGTH
    )
    es = max(0.0, min(1.0, es))
    base = min(1.0, (gap / GAP_DENOM) * _severity_multiplier(sc.linked_insight_severities))
    return base * (ES_DAMP_FLOOR + (1.0 - ES_DAMP_FLOOR) * es)


def compute_platform_fit(
    subcaps: list[SubcapForFit],
    platform_ids: list[str],
) -> list[PlatformFitRow]:
    """Engine v1 — mean addressable opportunity x breadth bonus.

    Kept for the ingest-time persister (`package_persist._persist_platform_
    scores`) and as the router's fallback for runs the v2 recompute has
    not touched. Target band now M4 (see module docstring). New code
    should call :func:`compute_platform_fit_v2`.
    """
    by_platform: dict[str, dict[str, float]] = {pid: {} for pid in platform_ids}
    for sc in subcaps:
        gap = max(0.0, sc.target_band_score - sc.current_score)
        if gap == 0.0:
            continue
        mult = _severity_multiplier(sc.linked_insight_severities)
        opp = min(1.0, (gap / GAP_DENOM) * mult)
        for pid in sc.platform_ids:
            if pid in by_platform:
                by_platform[pid][sc.subcap_id] = opp

    out: list[PlatformFitRow] = []
    for pid in platform_ids:
        contributions = by_platform[pid]
        n = len(contributions)
        if n == 0:
            score = 0.0
        else:
            mean_opp = sum(contributions.values()) / n
            breadth = min(1.0, n / BREADTH_FULL)            # 0..1
            score = round(min(100.0 * mean_opp * (1.0 + 0.20 * breadth), 99.9), 1)
        out.append(
            PlatformFitRow(
                platform_id=pid,
                fit_score=score,
                addressable_subcap_ids=sorted(contributions.keys()),
            )
        )
    return out


def _interconnect_value(
    addressable: list[SubcapForFit],
    all_gap_subcaps: list[SubcapForFit],
) -> tuple[float, int]:
    """Catalogue-adjacency uplift 0..1 (+ raw dependent count).

    For each category (and value-chain stage, when mapped) where the
    platform's DRIVING CORE addresses at least one gap subcap, count the
    other gap subcaps in that category/stage outside the core — the
    dependents that closing the core subcaps lifts. Callers pass the
    top-opportunity core (BREADTH_FULL cap), not the full addressable
    set: with the v7 catalogue a broad platform addresses nearly every
    gap subcap, and measuring "dependents it does NOT address" then
    zeroes interconnect precisely for the platform whose program
    compounds the most (corpus measurement: salesforce interconnect
    10.9 pts vs 25.0 for every narrower platform, purely by set size).
    For cores at or under the cap this is byte-identical to the original
    unaddressed-sibling semantics. Normalised per involved category so a
    platform with 200 tagged subcaps can't saturate on volume alone.
    """
    if not addressable:
        return 0.0, 0
    addr_ids = {sc.subcap_id for sc in addressable}
    addr_cats = {sc.category_id for sc in addressable if sc.category_id}
    addr_stages = {st for sc in addressable for st in sc.vc_stages}
    if not addr_cats and not addr_stages:
        return 0.0, 0
    # Candidate pool = gap subcaps OUTSIDE the core; dependents = the pool
    # members adjacent (same category or value-chain stage) to the core.
    pool = 0
    dependents = 0
    for sc in all_gap_subcaps:
        if sc.subcap_id in addr_ids:
            continue
        pool += 1
        in_cat = sc.category_id in addr_cats if sc.category_id else False
        in_stage = bool(addr_stages.intersection(sc.vc_stages))
        if in_cat or in_stage:
            dependents += 1
    # 2026-07-14 recalibration: interconnect = SHARE of the non-core gap
    # surface adjacent to the core, not dependents/(3*n_cats). The old
    # denominator (3x involved categories) was dwarfed by the dependent
    # count on any broad platform (Regions Databricks: 575 dependents,
    # ~40 categories -> 575/120 -> min(1.0)=1.0), so EVERY broad platform
    # pegged at 1.0 and interconnect added a flat ~26 pts that did not
    # discriminate. A share is bounded in [0,1] by construction, cannot
    # saturate on volume, and separates a focused platform (small adjacent
    # share) from a broad one — the factor now ranks rather than inflates.
    if pool <= 0:
        return 0.0, dependents
    return round(dependents / pool, 4), dependents


def compute_platform_fit_v2(
    subcaps: list[SubcapForFit],
    platform_ids: list[str],
    *,
    readiness_by_platform: dict[str, str],
    absent_families_by_platform: dict[str, list[str]] | None = None,
    absent_count_by_platform: dict[str, int] | None = None,
    stack_alignment_by_platform: dict[str, float] | None = None,
    semantic_fit_by_platform: dict[str, dict[str, float]] | None = None,
    catalogue_fit_by_platform: dict[str, dict[str, dict]] | None = None,
    top_n: int = 12,
    absent_boost_by_platform: dict[str, float] | None = None,
    absent_reason_by_platform: dict[str, tuple[str | None, list[str]]] | None = None,
    stack_signals_by_platform: dict[str, list[dict]] | None = None,
    scale: dict | None = None,
    vertical_relevance_by_platform: dict[str, tuple[float, str | None]] | None = None,
    stack_lens_by_platform: dict[str, dict] | None = None,
    incumbent_covered_by_platform: dict[str, set] | None = None,
) -> list[PlatformFitV2Row]:
    """Engine v2 — the four-factor blend with readiness folded in.

    ``readiness_by_platform``: green/amber/red per platform (from
    `readiness_index.aggregate_readiness` over the prereq checks).
    ``absent_families_by_platform``: confirmed-ABSENT family names per
    platform (empty list ⇒ family detected in the stack ⇒ no boost).
    ``absent_count_by_platform``: count of absent family products for the
    card badge (falls back to len(absent families)).
    ``stack_alignment_by_platform``: OPTIONAL graded [0,1] current-stack
    factor per platform (platform v3 — see :func:`stack_alignment`). When
    present it REPLACES the binary absent_boost in the blend; when absent the
    engine keeps the exact 1.0/0.0 binary behaviour (back-compat).

    2026-07-06 reasoning additions (all optional — legacy callers get
    byte-identical behaviour):
    ``absent_boost_by_platform``: PRE-REASONED boost 0..1 per platform
      from `platform_signals.absent_boost_adjustment` — evidence text
      that names the family in use zeroes it; small-scale entities on
      heavy platforms get the documented dampener. It is the most
      specific stack signal, so it WINS over both the graded
      stack_alignment and the binary absent-family rule when supplied.
    ``absent_reason_by_platform``: {(reason, citing E-IDs)} — the
      auditable why behind each boost value.
    ``stack_signals_by_platform``: verbatim evidence mentions of the
      family (E-ID + polarity + excerpt) → persisted in the breakdown.
    ``scale``: firmographic scale context → persisted in the breakdown.
    ``catalogue_fit_by_platform``: OPTIONAL v7 L4-layer affinity
    ``{platform_id: {subcap_id: {"affinity": float, "features": [...]}}}``
    (see :mod:`app.services.platform_affinity`). Curated subcap→platform
    feature links: a linked subcap is addressable by catalogue design and
    its opportunity weight rides the deeper of (semantic, catalogue)
    confidence; the linked feature names surface in ``top_subcaps`` so fit
    rationale can name the concrete capability the platform ships.

    2026-07-14 skew-audit additions (optional — legacy callers get
    byte-identical behaviour):
    ``vertical_relevance_by_platform``: {(multiplier, reason)} from
      `platform_incumbents.vertical_relevance` — an out-of-vertical family
      (nCino for an asset manager) is capped by the multiplier and the
      reason lands in the breakdown + reasoning record.
    ``stack_lens_by_platform``: {{"lens": greenfield|integrate|expand,
      "incumbents": [...], "peer_coverage": float|None}} — persisted in
      the breakdown so dossier/narrative prose can frame the argument
      (integration with a named incumbent vs greenfield install).
    """
    absent_families_by_platform = absent_families_by_platform or {}
    absent_count_by_platform = absent_count_by_platform or {}
    stack_alignment_by_platform = stack_alignment_by_platform or {}
    semantic_fit_by_platform = semantic_fit_by_platform or {}
    absent_reason_by_platform = absent_reason_by_platform or {}
    stack_signals_by_platform = stack_signals_by_platform or {}
    catalogue_fit_by_platform = catalogue_fit_by_platform or {}
    vertical_relevance_by_platform = vertical_relevance_by_platform or {}
    stack_lens_by_platform = stack_lens_by_platform or {}
    incumbent_covered_by_platform = incumbent_covered_by_platform or {}

    gap_subcaps = [sc for sc in subcaps if sc.target_band_score - sc.current_score > 0]
    rows: list[PlatformFitV2Row] = []
    for pid in platform_ids:
        sem_fit = semantic_fit_by_platform.get(pid, {})
        cat_fit = catalogue_fit_by_platform.get(pid, {})
        # Addressability is gated on the two PRECISE signals: the curated L4
        # catalogue links (addressable by design) and the cross-encoder's
        # confirmation that the platform's capability genuinely SUPPORTS the
        # subcap (>= floor). The legacy keyword tags are ~11% precise on this
        # corpus (94-client stress test: 101,572 tagged pairs, only 11,165
        # CE-confirmed — 9 of 10 mis-attributed), so they remain a LAST
        # fallback only when both precise tiers are cold — the engine then
        # behaves exactly as before (zero regression).
        if sem_fit or cat_fit:
            addressable = [sc for sc in gap_subcaps
                           if sc.subcap_id in sem_fit or sc.subcap_id in cat_fit]
        else:
            addressable = [sc for sc in gap_subcaps if pid in sc.platform_ids]
        n = len(addressable)
        readiness = readiness_by_platform.get(pid, "amber")
        absent_families = list(absent_families_by_platform.get(pid, []))
        # None-safe: a LEFT-JOIN aggregate can surface NULL for a platform
        # with no rows (2026-07-11 prod refresh: int(None) crashed the fit
        # recompute on live data the fixture corpus never produces).
        _ac = absent_count_by_platform.get(pid)
        absent_count = int(_ac if _ac is not None else len(absent_families))
        # Graded current-stack factor (platform v3) when supplied; else the
        # binary 1.0/0.0 the engine has always used.
        sa = stack_alignment_by_platform.get(pid)
        absent_boost = (
            float(sa) if sa is not None
            else (1.0 if absent_families else 0.0)
        )

        signals = list(stack_signals_by_platform.get(pid, []))
        absent_reason, absent_e_ids = absent_reason_by_platform.get(pid, (None, []))
        relevance, relevance_reason = vertical_relevance_by_platform.get(
            pid, (1.0, None))
        lens = stack_lens_by_platform.get(pid)

        if n == 0:
            rows.append(PlatformFitV2Row(
                platform_id=pid, fit_score=0.0, state="INSUFFICIENT_EVIDENCE",
                readiness=readiness, addressable_subcap_ids=[],
                evidence_strength=0.0,
                breakdown=build_breakdown(
                    opportunity=0.0, interconnect=0.0, absent_boost=0.0,
                    readiness=readiness, evidence_strength_mean=0.0,
                    top_subcaps=[], absent_families=absent_families,
                    dependents=0, n_addressable=0,
                    stack_signals=signals, scale=scale,
                    absent_reason=absent_reason, absent_e_ids=absent_e_ids,
                    stack_lens=lens,
                    vertical_relevance=(relevance, relevance_reason),
                ),
                absent_count=absent_count,
            ))
            continue

        # Confidence weight: each subcap's opportunity is scaled by the DEEPER
        # of the two precise signals — cross-encoder support (how strongly the
        # platform's capability descriptor fits the subcap) and catalogue
        # affinity (how many curated L4 features the v7 catalogue links). A
        # subcap neither tier confirms is dampened (0.7); a strong hit on
        # either keeps full weight. Both tiers empty (cold) → weight 1.0 for
        # all → identical to the prior keyword-only score.
        def _conf_w(sid: str, _sf: dict = sem_fit, _cf: dict = cat_fit) -> float:
            # Floor 0.55 (was 0.70, 2026-07-14): pairs NEITHER precise tier
            # confirms ride the ~11%-precise keyword tags — the v7-catalogue
            # mandate says confirmed addressability leads the argument, so
            # unconfirmed pairs are discounted harder.
            if not _sf and not _cf:
                return 1.0
            w = 0.55
            s = _sf.get(sid)
            if s is not None:
                w = max(w, 0.55 + 0.45 * min(1.0, s / 0.60))
            c = _cf.get(sid)
            if c is not None:
                w = max(w, 0.55 + 0.45 * float(c.get("affinity") or 0.0))
            return w

        # Incumbent-coverage discount (2026-07-14): a gap the customer's
        # INSTALLED incumbent (Snowflake, Power BI…) already delivers per the
        # v7 L4 map is a smaller MARGINAL opportunity for the Zennify
        # challenger in that category — the honest pitch is the differentiated
        # ground, not what the incumbent already covers. Empirically abstains
        # where the incumbent doesn't reach (Snowflake covers data-platform
        # subcaps, not the P1C2.5.x governance gaps → no discount there).
        inc_covered = incumbent_covered_by_platform.get(pid) or set()

        def _opp(sc: SubcapForFit, _ic: set = inc_covered) -> float:
            base = _subcap_opportunity(sc) * _conf_w(sc.subcap_id)
            if sc.subcap_id in _ic:
                base *= INCUMBENT_COVERAGE_DISCOUNT
            return base

        opps = {sc.subcap_id: _opp(sc) for sc in addressable}
        n_incumbent_discounted = sum(
            1 for sc in addressable if sc.subcap_id in inc_covered)
        # Opportunity is judged on the platform's BEST addressable subcaps
        # (top BREADTH_FULL=40 — a scoped program's realistic surface), not
        # the mean over the whole set. The all-set mean was calibrated for
        # keyword/CE-gated sets of comparable size (~30-80); the curated L4
        # catalogue makes set sizes differ 5x between platforms (salesforce
        # links 820 subcaps, twilio 154), and a raw mean then punishes the
        # broadest platform with hundreds of small-gap dilutors — measured
        # on the corpus as salesforce ranking last for 93/94 clients purely
        # by set size. Sets at or under 40 keep their exact prior mean.
        top_pool = sorted(opps.values(), reverse=True)[: int(BREADTH_FULL)]
        mean_opp = sum(top_pool) / len(top_pool)
        breadth = min(1.0, n / BREADTH_FULL)
        opportunity = min(1.0, mean_opp * (1.0 + 0.20 * breadth))
        sem_mean = (round(sum(sem_fit[sc.subcap_id] for sc in addressable
                              if sc.subcap_id in sem_fit)
                          / max(1, sum(1 for sc in addressable
                                       if sc.subcap_id in sem_fit)), 4)
                    if sem_fit else None)
        cat_linked = [sc for sc in addressable if sc.subcap_id in cat_fit]
        cat_mean = (round(sum(float(cat_fit[sc.subcap_id].get("affinity") or 0.0)
                              for sc in cat_linked) / len(cat_linked), 4)
                    if cat_linked else None)

        # Driving core = the best BREADTH_FULL addressable subcaps (the same
        # pool the opportunity mean is judged on); interconnect measures the
        # gap mass adjacent to THAT core, so breadth beyond the core counts
        # as compounding, never as a penalty.
        core = sorted(
            addressable, key=lambda sc: (-opps[sc.subcap_id], sc.subcap_id),
        )[: int(BREADTH_FULL)]
        interconnect, dependents = _interconnect_value(core, gap_subcaps)
        # absent_boost (binary or graded stack_alignment) computed above; a
        # PRE-REASONED boost from platform_signals (2026-07-06 — evidence
        # naming the family in use zeroes it, the small-scale dampener is
        # applied) is the most specific signal and wins when supplied.
        if absent_boost_by_platform is not None and pid in absent_boost_by_platform:
            absent_boost = max(0.0, min(1.0, float(absent_boost_by_platform[pid])))

        raw = (
            W_OPPORTUNITY * opportunity
            + W_INTERCONNECT * interconnect
            + W_ABSENT * absent_boost
        )
        mult = READINESS_MULTIPLIER.get(readiness, READINESS_MULTIPLIER["amber"])
        # Vertical relevance caps an out-of-vertical family (0.35 ⇒ ceiling
        # ~34.7) — a lending-origination platform cannot render hot for an
        # entity with no lending operation, however large its gap surface.
        fit = round(min(100.0 * raw * mult * relevance, FIT_CAP), 1)

        top = core[:top_n]
        # Evidence strength is judged on the subcaps DRIVING the score —
        # a platform whose top contributors carry no linked evidence is
        # honestly INSUFFICIENT_EVIDENCE, however many tagged subcaps it
        # nominally addresses.
        es_top = [
            sc.evidence_strength if sc.evidence_strength is not None else 0.0
            for sc in top
        ]
        es_mean = round(sum(es_top) / len(es_top), 4) if es_top else 0.0
        state = "READY" if es_mean >= EVIDENCE_FLOOR else "INSUFFICIENT_EVIDENCE"
        top_subcaps = [
            {
                "subcap_id": sc.subcap_id,
                "name": sc.name,
                "pillar": sc.subcap_id[:2],
                "score": round(sc.current_score, 2),
                "peer_median": (
                    round(sc.peer_median, 2) if sc.peer_median is not None else None
                ),
                "gap": round(max(0.0, sc.target_band_score - sc.current_score), 2),
                "opportunity": round(opps[sc.subcap_id], 4),
                "e_ids": list(sc.evidence_e_ids)[:3],
                "tier": sc.evidence_tier,
                # Concrete L4 features the v7 catalogue maps this platform
                # onto the subcap — the receipts fit rationale / The Play
                # can name instead of a bare platform label.
                "l4_features": list(
                    (cat_fit.get(sc.subcap_id) or {}).get("features") or [])[:3],
            }
            for sc in top
        ]

        _bd = build_breakdown(
                opportunity=opportunity, interconnect=interconnect,
                absent_boost=absent_boost, readiness=readiness,
                evidence_strength_mean=es_mean, top_subcaps=top_subcaps,
                absent_families=absent_families, dependents=dependents,
                n_addressable=n, stack_alignment=sa,
                semantic_fit_mean=sem_mean,
                stack_signals=signals, scale=scale,
                absent_reason=absent_reason, absent_e_ids=absent_e_ids,
                catalogue_fit_mean=cat_mean,
                n_catalogue_linked=len(cat_linked) if cat_fit else None,
                stack_lens=lens,
                vertical_relevance=(relevance, relevance_reason),
            )
        # Incumbent-coverage annotation (additive; the discount already
        # applied inside `opps`): how many addressable gaps the installed
        # incumbent already delivers, so the modal can be honest about
        # where the marginal opportunity was trimmed.
        if n_incumbent_discounted:
            _bd["factors"]["opportunity"]["incumbent_covered_subcaps"] = \
                n_incumbent_discounted
        rows.append(PlatformFitV2Row(
            platform_id=pid,
            fit_score=fit,
            state=state,
            readiness=readiness,
            addressable_subcap_ids=sorted(sc.subcap_id for sc in addressable),
            evidence_strength=es_mean,
            breakdown=_bd,
            absent_count=absent_count,
            top_subcap_names=[
                str(t["name"]) for t in top_subcaps[:2] if t.get("name")
            ],
        ))

    separate_ties(rows)
    return rows


def build_breakdown(
    *,
    opportunity: float,
    interconnect: float,
    absent_boost: float,
    readiness: str,
    evidence_strength_mean: float,
    top_subcaps: list[dict],
    absent_families: list[str],
    dependents: int,
    n_addressable: int,
    stack_alignment: float | None = None,
    semantic_fit_mean: float | None = None,
    stack_signals: list[dict] | None = None,
    scale: dict | None = None,
    absent_reason: str | None = None,
    absent_e_ids: list[str] | None = None,
    catalogue_fit_mean: float | None = None,
    n_catalogue_linked: int | None = None,
    stack_lens: dict | None = None,
    vertical_relevance: tuple[float, str | None] | None = None,
) -> dict:
    """JSON-ready `platform_scores.fit_breakdown` payload — the audit's
    "contributions computed then DISCARDED" fix. Points are the factor's
    share of the pre-readiness 0-100 blend; the readiness entry carries
    the multiplier and the points it removed.

    2026-07-06 reasoning additions: ``stack_signals`` (verbatim evidence
    mentions of the platform family, E-ID-cited), ``scale`` (firmographic
    context), and ``reasoning`` — the step-by-step, E-ID-traceable record
    of what moved the score (built by :func:`build_reasoning`)."""
    mult = READINESS_MULTIPLIER.get(readiness, READINESS_MULTIPLIER["amber"])
    pts_opp = round(100.0 * W_OPPORTUNITY * opportunity, 1)
    pts_int = round(100.0 * W_INTERCONNECT * interconnect, 1)
    pts_abs = round(100.0 * W_ABSENT * absent_boost, 1)
    pre = pts_opp + pts_int + pts_abs
    out = {
        "engine": "v2",
        "target_band": "M4",
        "weights": {
            "opportunity": W_OPPORTUNITY,
            "interconnect": W_INTERCONNECT,
            "absent_boost": W_ABSENT,
        },
        "semantic_fit": (
            {"value": round(semantic_fit_mean, 4),
             "note": "mean cross-encoder platform↔subcap support over the "
                     "addressable set (NLP-graded; weights the opportunity)"}
            if semantic_fit_mean is not None else None
        ),
        "catalogue_fit": (
            {"value": round(catalogue_fit_mean, 4),
             "n_linked": n_catalogue_linked,
             "note": "mean v7 L4-layer affinity (curated subcap→platform "
                     "feature links) over the catalogue-linked addressable "
                     "set; weights the opportunity"}
            if catalogue_fit_mean is not None else None
        ),
        "factors": {
            "opportunity": {"value": round(opportunity, 4), "points": pts_opp},
            "interconnect": {
                "value": round(interconnect, 4), "points": pts_int,
                "dependent_subcaps": dependents,
            },
            "absent_boost": {
                "value": round(absent_boost, 4), "points": pts_abs,
                # platform v3: when the graded current-stack factor drove the
                # value (vs the 1.0/0.0 binary) the modal shows "stack
                # alignment" instead of a bare greenfield flag.
                "graded": stack_alignment is not None,
                "stack_alignment": (
                    round(float(stack_alignment), 4)
                    if stack_alignment is not None else None
                ),
                # 2026-07-14 lens: the frame the argument takes (greenfield |
                # integrate | expand) + the category incumbents behind it +
                # the SAME cohort family share the techstack note renders —
                # card and note can never disagree again.
                **({"stack_lens": {
                    "lens": stack_lens.get("lens"),
                    "category_incumbents": list(
                        stack_lens.get("incumbents") or []),
                }, "peer_coverage": stack_lens.get("peer_coverage")}
                   if stack_lens else {}),
            },
            "readiness": {
                "light": readiness,
                "multiplier": mult,
                "penalty_points": round(-(pre * (1.0 - mult)), 1),
            },
        },
        "evidence_strength": round(evidence_strength_mean, 4),
        "n_addressable": n_addressable,
        "top_subcaps": top_subcaps,
        "absent_families": absent_families,
    }
    rel_value, rel_reason = vertical_relevance or (1.0, None)
    if rel_value < 1.0:
        out["factors"]["vertical_relevance"] = {
            "value": round(float(rel_value), 4),
            "penalty_points": round(-(pre * mult * (1.0 - float(rel_value))), 1),
            "reason": rel_reason,
        }
    if stack_signals:
        out["stack_signals"] = stack_signals
    if scale and scale.get("band"):
        out["scale"] = scale
    out["reasoning"] = build_reasoning(
        pts_opp=pts_opp, pts_int=pts_int, pts_abs=pts_abs,
        readiness=readiness, penalty_points=round(-(pre * (1.0 - mult)), 1),
        top_subcaps=top_subcaps, dependents=dependents,
        n_addressable=n_addressable,
        absent_reason=absent_reason, absent_e_ids=absent_e_ids or [],
        absent_boost=absent_boost, scale=scale,
        vertical_relevance=vertical_relevance,
    )
    return out


def build_reasoning(
    *,
    pts_opp: float,
    pts_int: float,
    pts_abs: float,
    readiness: str,
    penalty_points: float,
    top_subcaps: list[dict],
    dependents: int,
    n_addressable: int,
    absent_reason: str | None,
    absent_e_ids: list[str],
    absent_boost: float,
    scale: dict | None,
    vertical_relevance: tuple[float, str | None] | None = None,
) -> list[dict]:
    """The auditable reasoning record: one step per factor with the
    points it contributed, the driving subcap ids, the citing E-IDs and
    a plain-language detail an admin can verify end-to-end. Pure and
    deterministic — every value is already computed engine state."""
    steps: list[dict] = []
    drivers = [t for t in top_subcaps[:3] if t.get("subcap_id")]
    driver_txt = "; ".join(
        f"{t.get('name') or t['subcap_id']} ({t['subcap_id']}) at "
        f"{t.get('score')} vs M4 target"
        for t in drivers
    )
    steps.append({
        "factor": "opportunity",
        "points": pts_opp,
        "detail": (
            f"{n_addressable} addressable capability gap"
            f"{'s' if n_addressable != 1 else ''}"
            + (f"; largest: {driver_txt}" if driver_txt else "")
        ),
        "subcap_ids": [t["subcap_id"] for t in drivers],
        "e_ids": sorted({
            str(e) for t in drivers for e in (t.get("e_ids") or [])
        })[:6],
    })
    steps.append({
        "factor": "interconnect",
        "points": pts_int,
        "detail": (
            f"closing the addressable gaps lifts {dependents} sibling gap "
            f"subcap{'s' if dependents != 1 else ''} in the same "
            "categories/value-chain stages"
            if dependents else
            "no adjacent gap subcaps ride on this platform's surface"
        ),
        "subcap_ids": [],
        "e_ids": [],
    })
    abs_detail = absent_reason or (
        "family confirmed absent from the detected stack — greenfield entry"
        if absent_boost > 0 else
        "family present in the detected stack — no greenfield boost"
    )
    steps.append({
        "factor": "absent_boost",
        "points": pts_abs,
        "detail": abs_detail,
        "subcap_ids": [],
        "e_ids": list(absent_e_ids)[:6],
    })
    if scale and scale.get("band"):
        steps.append({
            "factor": "scale",
            "points": 0.0,
            "detail": (
                f"firmographic scale: {scale['band']}"
                + (f" ({scale.get('basis')})" if scale.get("basis") else "")
                + " — factored into the greenfield weighting above"
            ),
            "subcap_ids": [],
            "e_ids": [],
        })
    steps.append({
        "factor": "readiness",
        "points": penalty_points,
        "detail": (
            f"readiness {readiness}: multiplier applied to the blend"
            + (" — red caps the card below the hot threshold"
               if readiness == "red" else "")
        ),
        "subcap_ids": [],
        "e_ids": [],
    })
    rel_value, rel_reason = vertical_relevance or (1.0, None)
    if rel_value < 1.0:
        steps.append({
            "factor": "vertical_relevance",
            "points": 0.0,
            "detail": rel_reason or (
                "the platform is built for a different subvertical — "
                "fit capped by the vertical-relevance multiplier"
            ),
            "subcap_ids": [],
            "e_ids": [],
        })
    return steps


def separate_ties(rows: list[PlatformFitV2Row]) -> None:
    """De-clamp: within one run, no two platforms may carry the exact same
    non-zero fit (the audit's 4 all-identical clients). Ties are separated
    by -0.1 steps, keeping the platform with denser evidence (then absent
    boost, then platform id) on top. In-place, deterministic."""
    by_score: dict[float, list[PlatformFitV2Row]] = {}
    for r in rows:
        if r.fit_score > 0:
            by_score.setdefault(r.fit_score, []).append(r)
    for score, tied in by_score.items():
        if len(tied) < 2:
            continue
        tied.sort(key=lambda r: (
            -r.evidence_strength,
            -float(bool(r.breakdown.get("absent_families"))),
            r.platform_id,
        ))
        for i, r in enumerate(tied):
            r.fit_score = round(max(0.0, score - 0.1 * i), 1)


def compute_sequence_ranks(
    *,
    platform_ids: list[str],
    unmet_prereq_subcaps: dict[str, list[str]],
    addressable_by_platform: dict[str, list[str]],
    rec_platform_edges: list[tuple[str, str]] | None = None,
    readiness_by_platform: dict[str, str] | None = None,
    fit_by_platform: dict[str, float] | None = None,
    relevance_by_platform: dict[str, float] | None = None,
    rec_priority_by_platform: dict[str, int] | None = None,
) -> dict[str, int]:
    """Prerequisite-DAG order across the platforms → sequence_rank 1..N.

    Edges (A must precede B):
      - A addresses a failing (UNMET/PARTIAL/MISSING) prerequisite subcap
        of B — closing A's surface unlocks B's readiness.
      - a recommendation on platform B lists a recommendation on platform
        A as prerequisite (``rec_platform_edges`` = [(A, B), ...]).

    Kahn topological sort; deterministic tie-break by vertical relevance
    (in-vertical first — an out-of-vertical platform never leads the
    sequence on a tie), then readiness (green < amber < red), then fit
    desc, then platform id. Cycles are broken by picking the best
    remaining node, so ranks always resolve.
    """
    readiness_by_platform = readiness_by_platform or {}
    fit_by_platform = fit_by_platform or {}
    relevance_by_platform = relevance_by_platform or {}
    rec_priority_by_platform = rec_priority_by_platform or {}
    addr_sets = {p: set(addressable_by_platform.get(p, [])) for p in platform_ids}

    edges: set[tuple[str, str]] = set()
    for b in platform_ids:
        for prereq_sid in unmet_prereq_subcaps.get(b, []):
            for a in platform_ids:
                if a != b and prereq_sid in addr_sets[a]:
                    edges.add((a, b))
    for a, b in rec_platform_edges or []:
        if a in addr_sets and b in addr_sets and a != b:
            edges.add((a, b))

    readiness_order = {"green": 0, "amber": 1, "red": 2}

    def _key(p: str) -> tuple:
        # Analyst recommendation priority leads the sequence (0 = most urgent;
        # a family the assessment did not recommend gets 99 so it never heads
        # the order). Vertical relevance / readiness / fit / id break ties
        # BELOW that, as before.
        return (
            int(rec_priority_by_platform.get(p, 99)),
            0 if float(relevance_by_platform.get(p, 1.0)) >= 1.0 else 1,
            readiness_order.get(readiness_by_platform.get(p, "amber"), 1),
            -float(fit_by_platform.get(p, 0.0)),
            p,
        )

    indeg = dict.fromkeys(platform_ids, 0)
    for _, b in edges:
        indeg[b] += 1
    remaining = set(platform_ids)
    # Analyst-recommended families lead the sequence: while any recommended
    # family is still unplaced, only recommended families are eligible — a family
    # the assessment never recommended must never precede (let alone gate) a
    # recommended one (Sunflower: an unrecommended nCino was a prereq of the
    # recommended Salesforce play and wrongly led rank 1). Prereq order is still
    # honoured WITHIN each partition; when all remaining recommended families are
    # blocked only by non-recommended predecessors, that block is broken so the
    # recommended family still leads. Empty recommendation set → prior behaviour.
    recommended = {p for p in platform_ids if p in rec_priority_by_platform}
    ranks: dict[str, int] = {}
    rank = 1
    while remaining:
        rec_left = recommended & remaining
        if rec_left:
            ready = [p for p in rec_left if indeg[p] == 0]
            pick_from = ready if ready else list(rec_left)
        else:
            ready = [p for p in remaining if indeg[p] == 0]
            # Cycle: no zero-indegree node left — break it at the best node.
            pick_from = ready if ready else list(remaining)
        nxt = min(pick_from, key=_key)
        ranks[nxt] = rank
        rank += 1
        remaining.discard(nxt)
        for a, b in edges:
            if a == nxt and b in remaining:
                indeg[b] -= 1
    return ranks


# ── Recommendation-driven fit (2026-07-15 rework) ────────────────────────────
# Platform fit is a READ of the analyst's own recommendations, NOT a
# deterministic catalogue score. The engine above still computes the
# capability-gap opportunity per family; this layer OVERRIDES the fit for any
# family the assessment recommended with a composite of the analyst's signals,
# and demotes families the assessment did NOT recommend so they can never lead.
#
#   recommended family:
#     fit = 100 · ( 0.35·priority + 0.25·deficiency-depth + 0.15·SO-alignment
#                 + 0.15·L3/L4-coverage + 0.10·evidence ) · effort-multiplier
#   NOT recommended:
#     fit = capability-gap fit · 0.40   (kept low; surfaced, never leading)
#
# This is what fixes the "always Databricks/Tableau/nCino in the exec summary"
# skew: the analyst almost never recommends Databricks, so it drops to the
# residual; the recommended Salesforce-family product the analyst prioritised
# leads, and the card names the SPECIFIC product (lead_product).
from dataclasses import dataclass as _dataclass  # noqa: E402


@_dataclass
class RecSignal:
    """Per-family aggregate of a run's analyst recommendations (built in
    platform_fit_data from the recommendations table's analyst fit fields)."""
    recommended: bool = False
    best_priority: int = 9                    # min priority_rank; 0 = most urgent
    rec_count: int = 0
    lead_product: str | None = None           # display name of the lead product
    lead_product_id: str | None = None
    so_count: int = 0
    evidence_count: int = 0
    effort_band: str = "LOW"                   # LOW | MEDIUM | HIGH
    integration_systems: tuple[str, ...] = ()
    deficient_subcaps: tuple[str, ...] = ()
    lead_rec_title: str | None = None


REC_W_PRIORITY = 0.35
REC_W_DEFICIENCY = 0.25
REC_W_SO = 0.15
REC_W_L3L4 = 0.15
REC_W_EVIDENCE = 0.10
REC_EFFORT_MULT = {"LOW": 1.0, "MEDIUM": 0.93, "HIGH": 0.85}
REC_UNRECOMMENDED_RESIDUAL = 0.40
# When the catalogue L3/L4 tables aren't loaded (offline bake), L3/L4 coverage
# can't be measured — use a neutral prior so the factor neither inflates nor
# zeros the composite. Production (catalogue loaded) passes a real value.
REC_L3L4_NEUTRAL = 0.5


def _deficiency_depth(
    subcap_ids: list[str], subcap_by_id: dict[str, SubcapForFit]
) -> float:
    """Mean normalised gap over the recommendation's target subcaps: how far
    below peer/target the capabilities it addresses actually sit (0..1). Falls
    back to 0.5 when no scored target subcap is resolvable."""
    gaps: list[float] = []
    for sid in subcap_ids:
        s = subcap_by_id.get(sid)
        if not s:
            continue
        target = s.peer_median if s.peer_median else DEFAULT_TARGET_BAND_SCORE
        gap = (float(target) - float(s.current_score)) / GAP_DENOM
        gaps.append(max(0.0, min(1.0, gap)))
    if not gaps:
        return 0.5
    return round(sum(gaps) / len(gaps), 4)


def _l3l4_coverage(
    subcap_ids: list[str],
    platform_id: str,
    l4_subcaps_by_platform: dict[str, set[str]] | None,
) -> float:
    """Fraction of the recommendation's deficient subcaps that the platform's
    catalogue L4 features actually address (the L3/L4→deficiency-alignment
    factor). Neutral prior when the catalogue isn't loaded."""
    if not l4_subcaps_by_platform:
        return REC_L3L4_NEUTRAL
    covered = l4_subcaps_by_platform.get(platform_id) or set()
    if not covered or not subcap_ids:
        return REC_L3L4_NEUTRAL
    hit = sum(1 for sid in subcap_ids if sid in covered)
    return round(hit / len(subcap_ids), 4)


def apply_recommendation_fit(
    rows: list[PlatformFitV2Row],
    rec_signal_by_platform: dict[str, RecSignal] | None,
    subcaps: list[SubcapForFit],
    *,
    l4_subcaps_by_platform: dict[str, set[str]] | None = None,
) -> list[PlatformFitV2Row]:
    """Rewrite each family's fit as a read of the analyst recommendations.
    Pure; mutates + returns the rows. A None/empty signal map leaves the
    capability-gap fit untouched (graceful — behaves like the prior engine)."""
    if not rec_signal_by_platform:
        return rows
    subcap_by_id = {s.subcap_id: s for s in subcaps}
    for r in rows:
        sig = rec_signal_by_platform.get(r.platform_id)
        if sig and sig.recommended:
            prio = (9 - max(0, min(9, sig.best_priority))) / 9.0
            target_subcaps = list(sig.deficient_subcaps) or list(r.addressable_subcap_ids)
            defic = _deficiency_depth(target_subcaps, subcap_by_id)
            so = min(sig.so_count, 3) / 3.0
            l3l4 = _l3l4_coverage(target_subcaps, r.platform_id, l4_subcaps_by_platform)
            ev = min(sig.evidence_count, 6) / 6.0
            composite = (REC_W_PRIORITY * prio + REC_W_DEFICIENCY * defic
                         + REC_W_SO * so + REC_W_L3L4 * l3l4 + REC_W_EVIDENCE * ev)
            mult = REC_EFFORT_MULT.get(sig.effort_band, 1.0)
            r.fit_score = round(min(100.0 * composite * mult, 99.0), 1)
            r.breakdown["recommendation"] = {
                "recommended": True,
                "lead_product": sig.lead_product,
                "lead_product_id": sig.lead_product_id,
                "lead_rec_title": sig.lead_rec_title,
                "analyst_priority": sig.best_priority,
                "rec_count": sig.rec_count,
                "integration_effort": sig.effort_band,
                "integration_systems": list(sig.integration_systems),
                "factors": {
                    "priority": round(prio, 3),
                    "deficiency_depth": defic,
                    "strategic_objective_alignment": round(so, 3),
                    "l3l4_coverage": l3l4,
                    "evidence": round(ev, 3),
                    "effort_multiplier": mult,
                },
            }
        else:
            r.fit_score = round(float(r.fit_score) * REC_UNRECOMMENDED_RESIDUAL, 1)
            r.breakdown["recommendation"] = {
                "recommended": False,
                "note": "not in the assessment's recommendations — residual fit",
            }

    # Structural guarantee (2026-07-15): fit is a READ of the analyst's recs, so
    # a family the assessment never recommended must NEVER out-score one it did —
    # otherwise the exec-summary fit number lands on the wrong platform (Empower:
    # a Tableau residual edged the recommended Salesforce composite). Compress the
    # residual band strictly beneath the lowest recommended fit, preserving the
    # residual families' internal order. No-op when nothing is recommended
    # (graceful — behaves like the prior engine).
    def _is_recommended(row: PlatformFitV2Row) -> bool:
        s = rec_signal_by_platform.get(row.platform_id)
        return bool(s and s.recommended)

    rec_fits = [r.fit_score for r in rows if _is_recommended(r)]
    if rec_fits:
        floor = min(rec_fits)
        residual_rows = [r for r in rows if not _is_recommended(r)]
        hi = max((r.fit_score for r in residual_rows), default=0.0)
        # ceiling sits a hair below the weakest recommended family so ranking
        # by fit_score always places every recommended family above every residual
        ceiling = round(max(floor - 0.1, floor * 0.9), 1)
        if hi > ceiling and hi > 0:
            for r in residual_rows:
                r.fit_score = round(r.fit_score / hi * ceiling, 1)
                r.breakdown.setdefault("recommendation", {})[
                    "compressed_below_recommended"] = True
    return rows
