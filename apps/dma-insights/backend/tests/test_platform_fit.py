"""Tests for the deterministic platform fit-score computation."""
from __future__ import annotations

from app.services.platform_fit import (
    BREADTH_FULL,
    DEFAULT_TARGET_BAND_SCORE,
    GAP_DENOM,
    SEVERITY_WEIGHTS,
    PlatformFitRow,
    SubcapForFit,
    compute_platform_fit,
)


def _expect(score: float, sev: str | None, n: int = 1) -> float:
    """Mirror the 0-100 fit formula: mean opportunity (gap-to-M5 x severity,
    clamped 0..1) lifted by a bounded breadth bonus."""
    gap = max(0.0, DEFAULT_TARGET_BAND_SCORE - score)
    mult = SEVERITY_WEIGHTS.get(sev, 1.0) if sev else SEVERITY_WEIGHTS["medium"]
    opp = min(1.0, (gap / GAP_DENOM) * mult)
    breadth = min(1.0, n / BREADTH_FULL)
    return round(min(100.0 * opp * (1.0 + 0.20 * breadth), 99.9), 1)


def test_single_critical_gap_dominates() -> None:
    subcaps = [
        SubcapForFit(subcap_id="P2C1.1.1", current_score=2.0,
                     platform_ids=["salesforce"], linked_insight_severities=["critical"])
    ]
    rows = compute_platform_fit(subcaps, ["salesforce", "databricks"])
    by_pid = {r.platform_id: r for r in rows}
    # gap 3.0 to M5 x critical 1.6 → opp clamps to 1.0 → ~max fit
    assert by_pid["salesforce"].fit_score == _expect(2.0, "critical")
    assert by_pid["salesforce"].fit_score >= 95.0  # critical + big gap ≈ ceiling
    assert by_pid["salesforce"].addressable_subcap_ids == ["P2C1.1.1"]
    assert by_pid["databricks"].fit_score == 0.0
    assert by_pid["databricks"].addressable_subcap_ids == []


def test_no_gap_skipped() -> None:
    # At full maturity (M5) there is no runway → not addressable → fit 0.
    subcaps = [
        SubcapForFit(subcap_id="P1C1.1.1", current_score=DEFAULT_TARGET_BAND_SCORE,
                     platform_ids=["salesforce"], linked_insight_severities=["high"])
    ]
    rows = compute_platform_fit(subcaps, ["salesforce"])
    assert rows[0].fit_score == 0.0
    assert rows[0].addressable_subcap_ids == []


def test_severity_uses_max_when_multiple_insights() -> None:
    subcaps = [
        SubcapForFit(subcap_id="P1C1.1.1", current_score=2.0,
                     platform_ids=["salesforce"], linked_insight_severities=["medium", "critical"])
    ]
    rows = compute_platform_fit(subcaps, ["salesforce"])
    assert rows[0].fit_score == _expect(2.0, "critical")


def test_default_severity_when_no_insights_linked() -> None:
    subcaps = [
        SubcapForFit(subcap_id="P1C1.1.1", current_score=3.0,
                     platform_ids=["salesforce"], linked_insight_severities=[])
    ]
    # gap 1.0 to the M4 target x medium 1.0 → opp 1/3 → ~33 (target band
    # unified with the router at M4 per Part 7.1; was M5).
    rows = compute_platform_fit(subcaps, ["salesforce"])
    assert rows[0].fit_score == _expect(3.0, None)
    assert 28.0 <= rows[0].fit_score <= 38.0


def test_subcap_can_address_multiple_platforms() -> None:
    subcaps = [
        SubcapForFit(subcap_id="P4C1.1.1", current_score=2.0,
                     platform_ids=["salesforce", "databricks"], linked_insight_severities=["high"])
    ]
    rows = compute_platform_fit(subcaps, ["salesforce", "databricks"])
    by_pid = {r.platform_id: r for r in rows}
    assert by_pid["salesforce"].fit_score == _expect(2.0, "high")
    assert by_pid["databricks"].fit_score == _expect(2.0, "high")


def test_addressable_subcap_ids_sorted_deterministic() -> None:
    subcaps = [
        SubcapForFit(subcap_id="P2C3.4.2", current_score=2.0,
                     platform_ids=["salesforce"], linked_insight_severities=["high"]),
        SubcapForFit(subcap_id="P2C1.1.1", current_score=2.0,
                     platform_ids=["salesforce"], linked_insight_severities=["high"]),
    ]
    rows = compute_platform_fit(subcaps, ["salesforce"])
    assert rows[0].addressable_subcap_ids == ["P2C1.1.1", "P2C3.4.2"]


def test_compute_returns_one_row_per_requested_platform_in_order() -> None:
    subcaps = []
    rows = compute_platform_fit(subcaps, ["b", "a", "c"])
    assert [r.platform_id for r in rows] == ["b", "a", "c"]
    assert all(isinstance(r, PlatformFitRow) for r in rows)
    assert all(r.fit_score == 0.0 for r in rows)


# ── Engine v2 (Part 7.1) ────────────────────────────────────────────────

from app.services.platform_fit import (  # noqa: E402
    EVIDENCE_FLOOR,
    FIT_CAP,
    READINESS_MULTIPLIER,
    compute_platform_fit_v2,
    compute_sequence_ranks,
    evidence_strength,
    stack_alignment,
)


def _sc(sid: str, score: float, pids: list[str], **kw) -> SubcapForFit:
    return SubcapForFit(
        subcap_id=sid, current_score=score, platform_ids=pids,
        linked_insight_severities=kw.pop("sev", []), **kw,
    )


def test_v2_red_readiness_gates_below_hot_threshold() -> None:
    """The audit's headline defect: 95/470 cards were fit>=80 while every
    prereq failed. v2 folds readiness IN as a multiplier whose red value
    caps the maximum reachable fit at 100*0.62 = 62 — red AND hot is
    arithmetically impossible."""
    # Construct the WORST case for the gate: max gap, critical severity,
    # full evidence, confirmed-absent family, dense interconnect.
    subcaps = [
        _sc(f"P4C1.{i}.1", 1.0, ["salesforce"], sev=["critical"],
            evidence_strength=1.0, evidence_e_ids=["E-1"], category_id="P4C1")
        for i in range(1, 41)
    ] + [
        # Non-addressable siblings in the same category → interconnect max.
        _sc(f"P4C1.{i}.9", 1.0, [], sev=["critical"], category_id="P4C1")
        for i in range(1, 30)
    ]
    rows = compute_platform_fit_v2(
        subcaps, ["salesforce"],
        readiness_by_platform={"salesforce": "red"},
        absent_families_by_platform={"salesforce": ["Salesforce"]},
    )
    assert rows[0].readiness == "red"
    assert rows[0].fit_score < 80.0, "red readiness must gate below hot"
    assert rows[0].fit_score <= 100.0 * READINESS_MULTIPLIER["red"]
    # Same inputs under green readiness score strictly higher.
    green = compute_platform_fit_v2(
        subcaps, ["salesforce"],
        readiness_by_platform={"salesforce": "green"},
        absent_families_by_platform={"salesforce": ["Salesforce"]},
    )
    assert green[0].fit_score > rows[0].fit_score


def test_v2_breakdown_present_and_traceable() -> None:
    subcaps = [
        _sc("P4C1.1.1", 1.5, ["salesforce"], sev=["high"],
            evidence_strength=0.8, evidence_e_ids=["E-047", "E-141"],
            name="Unified Customer Profile", peer_median=3.0,
            category_id="P4C1"),
    ]
    rows = compute_platform_fit_v2(
        subcaps, ["salesforce"],
        readiness_by_platform={"salesforce": "amber"},
    )
    bd = rows[0].breakdown
    assert bd["engine"] == "v2" and bd["target_band"] == "M4"
    for factor in ("opportunity", "interconnect", "absent_boost", "readiness"):
        assert factor in bd["factors"]
    top = bd["top_subcaps"][0]
    assert top["subcap_id"] == "P4C1.1.1"
    assert top["name"] == "Unified Customer Profile"
    assert top["e_ids"] == ["E-047", "E-141"]
    assert top["peer_median"] == 3.0
    assert rows[0].top_subcap_names == ["Unified Customer Profile"]


def test_v2_evidence_floor_yields_insufficient_evidence() -> None:
    """The state the audit found unreachable (470/470 READY)."""
    subcaps = [
        _sc("P1C1.1.1", 2.0, ["twilio"], evidence_strength=0.0),
        _sc("P1C1.1.2", 2.0, ["twilio"], evidence_strength=EVIDENCE_FLOOR / 2),
    ]
    rows = compute_platform_fit_v2(
        subcaps, ["twilio"], readiness_by_platform={"twilio": "green"},
    )
    assert rows[0].state == "INSUFFICIENT_EVIDENCE"
    # Well-evidenced top subcaps → READY.
    ok = compute_platform_fit_v2(
        [_sc("P1C1.1.1", 2.0, ["twilio"], evidence_strength=0.9,
             evidence_e_ids=["E-1"])],
        ["twilio"], readiness_by_platform={"twilio": "green"},
    )
    assert ok[0].state == "READY"
    # Zero addressable subcaps stays INSUFFICIENT_EVIDENCE (fit 0).
    none = compute_platform_fit_v2(
        [], ["twilio"], readiness_by_platform={"twilio": "green"},
    )
    assert none[0].state == "INSUFFICIENT_EVIDENCE"
    assert none[0].fit_score == 0.0


def test_v2_interconnect_uplift_from_category_adjacency() -> None:
    """Closing an addressable subcap lifts sibling gap subcaps in the
    same category → measurable uplift vs an isolated subcap."""
    base = [_sc("P4C1.1.1", 2.0, ["databricks"], evidence_strength=0.8,
                evidence_e_ids=["E-1"], category_id="P4C1")]
    isolated = compute_platform_fit_v2(
        base, ["databricks"], readiness_by_platform={"databricks": "green"},
    )
    with_deps = compute_platform_fit_v2(
        [
            *base,
            _sc("P4C1.2.1", 2.0, [], category_id="P4C1"),
            _sc("P4C1.3.1", 1.5, [], category_id="P4C1"),
        ],
        ["databricks"], readiness_by_platform={"databricks": "green"},
    )
    assert with_deps[0].fit_score > isolated[0].fit_score
    ic = with_deps[0].breakdown["factors"]["interconnect"]
    assert ic["dependent_subcaps"] == 2 and ic["value"] > 0


def test_v2_interconnect_is_a_share_not_saturated(monkeypatch=None) -> None:
    """2026-07-14 W3: interconnect is the SHARE of the non-core gap surface
    adjacent to the core — it must discriminate a broad platform from a
    focused one and must NOT peg at 1.0 on volume (the old
    dependents/(3·n_cats) saturated every broad platform at 1.0 → a flat
    +26 pts). Build a big gap surface where a broad platform touches many
    categories and a focused one touches one."""
    from app.services.platform_fit import _interconnect_value
    # 60 gap subcaps across 6 categories (P1C1..P1C6), 10 each.
    gaps = [
        _sc(f"P1C{c}.{i}.1", 1.5, [], category_id=f"P1C{c}")
        for c in range(1, 7) for i in range(1, 11)
    ]
    broad_core = [g for g in gaps if g.subcap_id.endswith(".1.1")]      # 1 per category → touches all 6
    focused_core = [g for g in gaps if g.category_id == "P1C1"][:1]     # touches 1 category
    broad_ic, broad_dep = _interconnect_value(broad_core, gaps)
    focused_ic, focused_dep = _interconnect_value(focused_core, gaps)
    # broad touches all 6 categories → adjacent to ~all non-core gaps
    assert broad_dep > focused_dep
    # the focused platform is adjacent only to its own category's siblings →
    # a materially SMALLER share; the two are distinguishable (no flat peg).
    assert focused_ic < broad_ic
    # a share is bounded and here well under 1.0 for the focused platform.
    assert 0.0 < focused_ic < 0.3


def test_v2_absent_boost_and_badge_counts() -> None:
    base = [_sc("P2C1.1.1", 2.0, ["twilio"], evidence_strength=0.8,
                evidence_e_ids=["E-1"])]
    absent = compute_platform_fit_v2(
        base, ["twilio"], readiness_by_platform={"twilio": "green"},
        absent_families_by_platform={"twilio": ["Twilio"]},
        absent_count_by_platform={"twilio": 2},
    )
    present = compute_platform_fit_v2(
        base, ["twilio"], readiness_by_platform={"twilio": "green"},
        absent_families_by_platform={"twilio": []},
    )
    assert absent[0].fit_score > present[0].fit_score
    assert absent[0].absent_count == 2
    assert absent[0].breakdown["absent_families"] == ["Twilio"]


def test_v2_declamp_cap_99_and_tie_separation() -> None:
    """No 99.9 spike; exact within-run ties separate deterministically
    (the audit's 4 all-identical clients)."""
    subcaps = [
        _sc(f"P4C1.{i}.1", 1.0, ["salesforce", "databricks", "tableau"],
            sev=["critical"], evidence_strength=1.0, evidence_e_ids=["E-1"],
            category_id="P4C1")
        for i in range(1, 61)
    ]
    rows = compute_platform_fit_v2(
        subcaps, ["salesforce", "databricks", "tableau"],
        readiness_by_platform={p: "green" for p in ("salesforce", "databricks", "tableau")},
        absent_families_by_platform={p: ["X"] for p in ("salesforce", "databricks", "tableau")},
    )
    scores = [r.fit_score for r in rows]
    assert all(s <= FIT_CAP for s in scores)
    assert len(set(scores)) == len(scores), "within-run ties must separate"


def test_v2_sequence_ranks_prereq_dag() -> None:
    """A addresses B's failing prereq subcap ⇒ A precedes B; rec
    dependency edges add ordering; ties break on readiness then fit."""
    ranks = compute_sequence_ranks(
        platform_ids=["salesforce", "databricks", "tableau"],
        unmet_prereq_subcaps={
            # tableau's governed-reporting prereq is addressable by databricks
            "tableau": ["P4C2.1.1"],
        },
        addressable_by_platform={
            "salesforce": ["P2C1.1.1"],
            "databricks": ["P4C2.1.1", "P4C1.1.2"],
            "tableau": ["P4C3.1.1"],
        },
        rec_platform_edges=[("databricks", "salesforce")],
        readiness_by_platform={
            "salesforce": "amber", "databricks": "green", "tableau": "amber",
        },
        fit_by_platform={"salesforce": 70.0, "databricks": 60.0, "tableau": 50.0},
    )
    assert ranks["databricks"] < ranks["tableau"]
    assert ranks["databricks"] < ranks["salesforce"]
    assert sorted(ranks.values()) == [1, 2, 3]


def test_evidence_strength_tier_and_freshness() -> None:
    # T1 current beats T7 stale; empty is 0; density adds bounded lift.
    strong = evidence_strength([1], ["current"])
    weak = evidence_strength([7], ["stale"])
    assert strong > weak > 0
    assert evidence_strength([], []) == 0.0
    dense = evidence_strength([1, 1, 1, 1], ["current"] * 4)
    assert dense > strong
    assert dense <= 1.0


# ── Platform v3: graded stack_alignment factor + calibration ────────────


def test_stack_alignment_grading() -> None:
    # A present family (not absent) never earns greenfield credit → 0.0.
    assert stack_alignment(absent_family=False, absent_count=3) == 0.0
    # 2026-07-14 recalibration: cohort adoption is the anchor. No cohort
    # data → neutral 0.70 prior; cov=0 → 0.45; cov=1 → full 1.0.
    assert stack_alignment(absent_family=True, absent_count=4) == 0.70
    assert stack_alignment(absent_family=True, absent_count=0, peer_coverage=0.0) == 0.45
    assert stack_alignment(absent_family=True, absent_count=0, peer_coverage=1.0) == 1.0
    # Absence breadth no longer raises alignment (the pre-recalibration
    # formula REWARDED missing products — the 30-sample skew audit's
    # arithmetic behind 70+ cards over 0%-peer-coverage families).
    assert stack_alignment(absent_family=True, absent_count=0) == \
        stack_alignment(absent_family=True, absent_count=5)
    # peer_coverage is bounded and monotone (never lifts above 1.0).
    assert stack_alignment(absent_family=True, absent_count=1, peer_coverage=1.0) <= 1.0
    lo = stack_alignment(absent_family=True, absent_count=1, peer_coverage=0.0)
    mid = stack_alignment(absent_family=True, absent_count=1, peer_coverage=0.5)
    hi = stack_alignment(absent_family=True, absent_count=1, peer_coverage=1.0)
    assert lo < mid < hi


def test_stack_alignment_binary_backcompat() -> None:
    # Without stack_alignment_by_platform the engine reproduces the binary
    # absent_boost exactly (existing snapshots unaffected).
    subs = [_sc("P2C1.1.1", 2.0, ["twilio"], evidence_strength=0.8, evidence_e_ids=["E-1"])]
    binary = compute_platform_fit_v2(
        subs, ["twilio"], readiness_by_platform={"twilio": "green"},
        absent_families_by_platform={"twilio": ["Twilio"]},
    )
    graded_full = compute_platform_fit_v2(
        subs, ["twilio"], readiness_by_platform={"twilio": "green"},
        absent_families_by_platform={"twilio": ["Twilio"]},
        stack_alignment_by_platform={"twilio": 1.0},
    )
    assert binary[0].fit_score == graded_full[0].fit_score
    # graded value is recorded in the breakdown when supplied.
    fac = graded_full[0].breakdown["factors"]["absent_boost"]
    assert fac["graded"] is True and fac["stack_alignment"] == 1.0
    assert binary[0].breakdown["factors"]["absent_boost"]["graded"] is False


def test_fit_delta_calibration_under_8_on_fixtures() -> None:
    """Calibration mandate: corpus |fit delta| (graded vs binary) stays
    bounded under W_ABSENT — the graded factor grades the ABSENT term only,
    so with W_ABSENT=0.08 the worst-case swing is 8·(1-0.45) < 8 pts. Build
    12 platforms with an absent family and varied cohort peer coverage; the
    graded factor demotes low-adoption greenfields, never lifts above binary."""
    import statistics
    pids = [f"p{i}" for i in range(12)]
    subs = [
        _sc(f"P4C1.{i}.1", 1.5, [pids[i]], sev=["high"],
            evidence_strength=0.8, evidence_e_ids=["E-1"], category_id="P4C1")
        for i in range(12)
    ]
    readiness = {p: "green" for p in pids}
    absent = {p: ["Fam"] for p in pids}
    covs = {pids[i]: (i % 6) / 5.0 for i in range(12)}  # coverage 0..1
    graded_by = {
        pids[i]: stack_alignment(absent_family=True,
                                 peer_coverage=covs[pids[i]])
        for i in range(12)
    }
    binary = {r.platform_id: r.fit_score for r in compute_platform_fit_v2(
        subs, pids, readiness_by_platform=readiness, absent_families_by_platform=absent)}
    graded = {r.platform_id: r.fit_score for r in compute_platform_fit_v2(
        subs, pids, readiness_by_platform=readiness, absent_families_by_platform=absent,
        stack_alignment_by_platform=graded_by)}
    deltas = [abs(binary[p] - graded[p]) for p in pids]
    assert statistics.median(deltas) < 8.0
    assert max(deltas) < 8.0  # bounded: W_ABSENT · (1 - 0.45) · 100 = 4.4
    assert any(d > 0 for d in deltas), "the factor must actually move some scores"
    # Monotone in cohort adoption: broader peer coverage ⇒ graded fit ≥
    # the zero-coverage twin (p5 cov=1.0, p0 cov=0.0).
    assert graded["p5"] >= graded["p0"]
    # The graded factor DEMOTES relative to binary, never lifts above it —
    # modulo separate_ties: the binary run's 12 identical scores are
    # tie-separated downward by up to 0.1·11, so allow that width.
    assert all(graded[p] <= binary[p] + 1.2 for p in pids)
