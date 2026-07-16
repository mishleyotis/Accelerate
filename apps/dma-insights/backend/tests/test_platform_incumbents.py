"""Category-incumbent lens + vertical relevance (2026-07-14 skew audit).

The 30-client sample of the live pack measured the failure modes these
contracts pin: nCino top-ranked for 14/28 clients (9 of them ≥70 with 0%
cohort peer coverage; one an asset-manager REIT at 86.8 READY), and 4
Databricks cards ≥70 greenfield over an installed third-party data
platform. Pure-logic, no DB.
"""
from __future__ import annotations

from app.services.platform_fit import (
    FIT_CAP,
    SubcapForFit,
    compute_platform_fit_v2,
    compute_sequence_ranks,
)
from app.services.platform_incumbents import (
    OUT_OF_VERTICAL_RELEVANCE,
    detect_category_incumbents,
    normalize_subvertical,
    stack_lens,
    vertical_relevance,
)
from app.services.platform_signals import (
    INCUMBENT_ABSENT_RESIDUAL,
    SMALL_SCALE_ABSENT_DAMP,
    StackSignal,
    absent_boost_adjustment,
)

# ── incumbent detection ──────────────────────────────────────────────────

def test_incumbents_detected_per_family_category() -> None:
    hay = ("snowflake data cloud warehouse meridianlink loans power bi "
           "reporting hubspot marketing braze journeys").lower()
    inc = detect_category_incumbents(hay)
    assert "Snowflake" in inc["databricks"]
    assert "MeridianLink" in inc["ncino"]
    assert "Power BI" in inc["tableau"]
    assert "HubSpot" in inc["salesforce"]
    assert "Braze" in inc["twilio"]


def test_own_family_products_never_count_as_incumbents() -> None:
    # A stack made ONLY of the scored families' own products has no
    # third-party incumbent anywhere.
    hay = ("salesforce financial services cloud databricks lakehouse "
           "tableau pulse twilio segment ncino").lower()
    inc = detect_category_incumbents(hay)
    assert all(not v for v in inc.values()), inc


def test_empty_stack_has_no_incumbents() -> None:
    assert all(not v for v in detect_category_incumbents("").values())


# ── lens ─────────────────────────────────────────────────────────────────

def test_stack_lens_three_way() -> None:
    assert stack_lens(family_absent=False, incumbents=[], evidence_in_use=False) == "expand"
    assert stack_lens(family_absent=True, incumbents=[], evidence_in_use=True) == "expand"
    assert stack_lens(family_absent=True, incumbents=["Snowflake"],
                      evidence_in_use=False) == "integrate"
    assert stack_lens(family_absent=True, incumbents=[], evidence_in_use=False) == "greenfield"


# ── vertical relevance ───────────────────────────────────────────────────

def test_vertical_relevance_ncino_out_of_vertical() -> None:
    mult, reason = vertical_relevance("ncino", "AM")
    assert mult == OUT_OF_VERTICAL_RELEVANCE
    assert reason and "lending" in reason.lower()


def test_vertical_relevance_in_scope_and_universal() -> None:
    assert vertical_relevance("ncino", "RB") == (1.0, None)
    assert vertical_relevance("ncino", "CU") == (1.0, None)
    # horizontal families are universal
    for pid in ("salesforce", "databricks", "tableau", "twilio"):
        assert vertical_relevance(pid, "AM") == (1.0, None)


def test_vertical_relevance_fails_open_on_unknown() -> None:
    assert vertical_relevance("ncino", None) == (1.0, None)
    assert vertical_relevance("ncino", "???") == (1.0, None)


def test_extended_code_normalization() -> None:
    assert normalize_subvertical("REIT") == "AM"
    assert normalize_subvertical("WEALTH_RIA") == "RIA"
    assert normalize_subvertical("rb") == "RB"
    assert normalize_subvertical("FINTECH_SAAS") is None
    # a REIT-coded entity gets the same nCino cap as an AM one
    assert vertical_relevance("ncino", "REIT")[0] == OUT_OF_VERTICAL_RELEVANCE


# ── boost ladder fusion ──────────────────────────────────────────────────

def _sig(polarity: str, e_id: str = "E-1") -> StackSignal:
    return StackSignal(platform_id="databricks", e_id=e_id,
                       polarity=polarity, excerpt="x")


def test_ladder_in_use_still_zeroes_everything() -> None:
    boost, reason, cites = absent_boost_adjustment(
        platform_id="databricks", base_absent=True,
        signals=[_sig("in_use")], scale={"band": "small"},
        category_incumbents=["Snowflake"], graded_base=0.45)
    assert boost == 0.0 and "in use" in (reason or "")
    assert cites == ["E-1"]


def test_ladder_incumbent_rung_returns_residual_with_named_incumbent() -> None:
    boost, reason, _ = absent_boost_adjustment(
        platform_id="databricks", base_absent=True, signals=[],
        scale={"band": "large"}, category_incumbents=["Snowflake"],
        graded_base=1.0)
    assert boost == INCUMBENT_ABSENT_RESIDUAL
    assert "Snowflake" in (reason or "")
    assert "integration" in (reason or "")


def test_ladder_incumbent_rung_beats_small_scale_damp() -> None:
    # incumbent residual (0.25) < small-scale damp (0.5) — the more
    # specific signal wins and stays the smaller value.
    boost, _, _ = absent_boost_adjustment(
        platform_id="databricks", base_absent=True, signals=[],
        scale={"band": "small"}, category_incumbents=["Snowflake"],
        graded_base=1.0)
    assert boost == INCUMBENT_ABSENT_RESIDUAL < SMALL_SCALE_ABSENT_DAMP


def test_ladder_small_scale_takes_min_with_graded_base() -> None:
    lo, _, _ = absent_boost_adjustment(
        platform_id="databricks", base_absent=True, signals=[],
        scale={"band": "small"}, graded_base=0.45)
    assert lo == 0.45  # graded below the damp → graded wins
    hi, _, _ = absent_boost_adjustment(
        platform_id="databricks", base_absent=True, signals=[],
        scale={"band": "small"}, graded_base=0.9)
    assert hi == SMALL_SCALE_ABSENT_DAMP  # damp caps a high graded base


def test_ladder_confirmed_absent_uses_graded_base() -> None:
    for cov_base, expect in ((0.45, 0.45), (0.725, 0.725), (1.0, 1.0)):
        boost, reason, _ = absent_boost_adjustment(
            platform_id="tableau", base_absent=True, signals=[],
            scale={"band": "mid"}, graded_base=cov_base)
        assert boost == expect
        assert "peer coverage" in (reason or "")


def test_ladder_legacy_call_unchanged() -> None:
    # No new kwargs → the exact pre-2026-07-14 values.
    assert absent_boost_adjustment(
        platform_id="tableau", base_absent=True, signals=[],
        scale={"band": "mid"})[0] == 1.0
    assert absent_boost_adjustment(
        platform_id="databricks", base_absent=True, signals=[],
        scale={"band": "small"})[0] == SMALL_SCALE_ABSENT_DAMP
    assert absent_boost_adjustment(
        platform_id="tableau", base_absent=False, signals=[],
        scale=None)[0] == 0.0


# ── engine integration ───────────────────────────────────────────────────

def _sc(sid: str, score: float, pids: list[str]) -> SubcapForFit:
    return SubcapForFit(
        subcap_id=sid, current_score=score, platform_ids=pids,
        linked_insight_severities=["high"], name=f"Cap {sid}",
        evidence_strength=0.8, evidence_e_ids=["E-1"],
    )


def test_vertical_relevance_caps_fit_and_lands_in_breakdown() -> None:
    subs = [_sc(f"P3C2.{i}.1", 1.2, ["ncino"]) for i in range(6)]
    base = compute_platform_fit_v2(
        subs, ["ncino"], readiness_by_platform={"ncino": "green"},
        absent_families_by_platform={"ncino": ["nCino"]})
    capped = compute_platform_fit_v2(
        subs, ["ncino"], readiness_by_platform={"ncino": "green"},
        absent_families_by_platform={"ncino": ["nCino"]},
        vertical_relevance_by_platform={
            "ncino": (OUT_OF_VERTICAL_RELEVANCE, "out of vertical")})
    assert capped[0].fit_score <= round(FIT_CAP * OUT_OF_VERTICAL_RELEVANCE, 1)
    assert capped[0].fit_score < base[0].fit_score
    vr = capped[0].breakdown["factors"]["vertical_relevance"]
    assert vr["value"] == OUT_OF_VERTICAL_RELEVANCE
    assert vr["penalty_points"] < 0
    assert any(s["factor"] == "vertical_relevance"
               for s in capped[0].breakdown["reasoning"])
    # in-vertical caller sees no such factor entry
    assert "vertical_relevance" not in base[0].breakdown["factors"]


def test_integrate_lens_persisted_in_breakdown() -> None:
    subs = [_sc("P4C1.1.1", 1.5, ["databricks"])]
    rows = compute_platform_fit_v2(
        subs, ["databricks"], readiness_by_platform={"databricks": "green"},
        absent_families_by_platform={"databricks": ["Databricks"]},
        stack_lens_by_platform={"databricks": {
            "lens": "integrate", "incumbents": ["Snowflake"],
            "peer_coverage": 0.4}})
    ab = rows[0].breakdown["factors"]["absent_boost"]
    assert ab["stack_lens"]["lens"] == "integrate"
    assert ab["stack_lens"]["category_incumbents"] == ["Snowflake"]
    assert ab["peer_coverage"] == 0.4


def test_out_of_vertical_never_leads_sequence_on_tie() -> None:
    ranks = compute_sequence_ranks(
        platform_ids=["ncino", "tableau"],
        unmet_prereq_subcaps={},
        addressable_by_platform={"ncino": ["P3C2.1.1"], "tableau": ["P4C2.1.1"]},
        readiness_by_platform={"ncino": "green", "tableau": "green"},
        fit_by_platform={"ncino": 90.0, "tableau": 55.0},
        relevance_by_platform={"ncino": OUT_OF_VERTICAL_RELEVANCE, "tableau": 1.0},
    )
    assert ranks["tableau"] == 1 and ranks["ncino"] == 2


def test_sequence_ranks_without_relevance_unchanged() -> None:
    ranks = compute_sequence_ranks(
        platform_ids=["ncino", "tableau"],
        unmet_prereq_subcaps={},
        addressable_by_platform={"ncino": [], "tableau": []},
        readiness_by_platform={"ncino": "green", "tableau": "green"},
        fit_by_platform={"ncino": 90.0, "tableau": 55.0},
    )
    assert ranks["ncino"] == 1  # legacy behaviour: fit desc on a tie


# ── W1: per-L3 vehicle resolution (2026-07-14 solutioning audit) ──────────
from app.services.platform_affinity import build_l3_affinity, top_l3_for_gaps  # noqa: E402


def _l4_rows():
    # Mirrors the real v7 shape for the Regions data-governance gaps:
    # Data Cloud (CDP) covers deepest, MuleSoft (iPaaS) is the vehicle,
    # Databricks Unity Catalog is the non-integration lakehouse answer.
    R = []
    for sid in ("P1C2.5.3", "P1C2.5.4", "P1C2.5.5"):
        R += [(sid, "Salesforce", "Salesforce Data Cloud", f"DC feat {i}",
               "L3-SF-DATA-CLOUD", "Data Platform / CDP") for i in range(6)]
        R += [(sid, "Salesforce / MuleSoft", "MuleSoft Anypoint Platform", f"MS feat {i}",
               "L3-MS-ANYPOINT", "Integration / iPaaS") for i in range(2)]
        R += [(sid, "Databricks", "Databricks Unity Catalog", f"UC feat {i}",
               "L3-DB-UC", "Governance") for i in range(3)]
    return R


def test_build_l3_affinity_keeps_subproduct_grain():
    agg = build_l3_affinity(_l4_rows())
    # MuleSoft folds into the salesforce family but keeps its own L3 identity
    assert "L3-MS-ANYPOINT" in agg["salesforce"]
    assert "L3-SF-DATA-CLOUD" in agg["salesforce"]
    assert agg["salesforce"]["L3-MS-ANYPOINT"]["is_integration"] is True
    assert agg["salesforce"]["L3-SF-DATA-CLOUD"]["is_integration"] is True  # CDP
    assert agg["databricks"]["L3-DB-UC"]["is_integration"] is False


def test_top_l3_picks_data_cloud_over_the_family_label():
    agg = build_l3_affinity(_l4_rows())
    gaps = ["P1C2.5.3", "P1C2.5.4", "P1C2.5.5"]
    sf = top_l3_for_gaps(agg["salesforce"], gaps, limit=3)
    # Data Cloud (6 feats/gap) leads MuleSoft (2) within the family
    assert sf[0]["platform_name"] == "Salesforce Data Cloud"
    assert sf[0]["gaps_covered"] == 3
    # the integration vehicle is discoverable for the integrate-lens play
    veh = next(v for v in sf if v["is_integration"] and "MuleSoft" in v["platform_name"])
    assert veh["gaps_covered"] == 3


def test_top_l3_empty_when_no_gap_overlap():
    agg = build_l3_affinity(_l4_rows())
    assert top_l3_for_gaps(agg["salesforce"], ["P9C9.9.9"]) == []
    assert top_l3_for_gaps({}, ["P1C2.5.3"]) == []


# ── W2: incumbent-coverage discount (2026-07-14) ──────────────────────────
from app.services.platform_affinity import incumbent_covered_subcaps  # noqa: E402
from app.services.platform_fit import (  # noqa: E402
    INCUMBENT_COVERAGE_DISCOUNT,
)


def test_incumbent_covered_subcaps_matches_vendor_substring():
    cov = {"snowflake inc.": {"P4C1.3.1", "P4C1.3.2"}, "collibra": {"P1C2.5.3"}}
    # display name "Snowflake" matches the L4 vendor "Snowflake Inc."
    assert incumbent_covered_subcaps(["Snowflake"], cov) == {"P4C1.3.1", "P4C1.3.2"}
    assert incumbent_covered_subcaps(["Collibra", "Snowflake"], cov) == \
        {"P1C2.5.3", "P4C1.3.1", "P4C1.3.2"}
    assert incumbent_covered_subcaps(["Databricks"], cov) == set()


def test_incumbent_discount_lowers_fit_only_on_covered_gaps():
    # DBX addresses two data-platform gaps the incumbent (Snowflake) covers.
    subs = [_sc("P4C1.3.1", 1.5, ["databricks"]), _sc("P4C1.3.2", 1.5, ["databricks"])]
    base = compute_platform_fit_v2(
        subs, ["databricks"], readiness_by_platform={"databricks": "green"})
    discounted = compute_platform_fit_v2(
        subs, ["databricks"], readiness_by_platform={"databricks": "green"},
        incumbent_covered_by_platform={"databricks": {"P4C1.3.1", "P4C1.3.2"}})
    assert discounted[0].fit_score < base[0].fit_score
    assert discounted[0].breakdown["factors"]["opportunity"][
        "incumbent_covered_subcaps"] == 2


def test_incumbent_discount_abstains_off_covered_gaps():
    # DBX addresses GOVERNANCE gaps; the incumbent covers only data-platform
    # subcaps → no overlap → no discount (the Regions case).
    subs = [_sc("P1C2.5.3", 1.0, ["databricks"]), _sc("P1C2.5.4", 1.0, ["databricks"])]
    base = compute_platform_fit_v2(
        subs, ["databricks"], readiness_by_platform={"databricks": "green"})
    same = compute_platform_fit_v2(
        subs, ["databricks"], readiness_by_platform={"databricks": "green"},
        incumbent_covered_by_platform={"databricks": {"P4C1.3.1", "P4C1.3.2"}})
    assert same[0].fit_score == base[0].fit_score  # abstains
    assert INCUMBENT_COVERAGE_DISCOUNT == 0.5
