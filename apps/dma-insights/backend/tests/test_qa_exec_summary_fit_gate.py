"""Quality-ratchet gate: the exec summary's cited platform-fit number must
agree with the rank-1 platform card. Pins the 2026-07-15 regression class —
a KEPT synthetic clause froze a stale fit number (Sunflower shipped "22/100"
when the corrected lead fit was 52) — so a redeploy carrying it fails loudly.
"""
from __future__ import annotations

from app.scripts.qa_deploy_review_audit import check_exec_summary


def _ov(fit_txt: str) -> dict:
    return {"narrative": {"scqa_md":
            "The decision is narrow: close Data Lake, at 1.6/5 [E-049, E-068]. "
            f"On platform fit, Service Cloud ranks first ({fit_txt}/100 fit); "
            "the recommended entry point is Data Catalog, sequencing MuleSoft "
            "behind it. The evidence base reads the same way [E-003]."}}


def _platforms(lead_fit: float) -> dict:
    return {"cards": [
        {"platform_id": "salesforce", "fit_score": lead_fit, "sequence_rank": 1},
        {"platform_id": "ncino", "fit_score": 20.0, "sequence_rank": 2},
    ]}


def test_fit_number_matches_lead_card_passes():
    c, bad = check_exec_summary(_ov("52"), available_eids=3,
                                platforms=_platforms(51.8))
    assert c.get("platform_fit_stale", 0) == 0
    assert not any(b.startswith("platform_fit_stale") for b in bad)


def test_stale_fit_number_flagged():
    # exec summary cites 22/100 but the lead card is 52/100 → regression
    c, bad = check_exec_summary(_ov("22"), available_eids=3,
                                platforms=_platforms(51.8))
    assert c.get("platform_fit_stale", 0) == 1
    assert any(b.startswith("platform_fit_stale") for b in bad)


def test_rounding_tolerance_one_point():
    # 48 cited vs 48.4 lead → within tolerance, not flagged
    c, _ = check_exec_summary(_ov("48"), available_eids=3,
                              platforms=_platforms(48.4))
    assert c.get("platform_fit_stale", 0) == 0


def test_no_platforms_is_graceful():
    # no platform pack → the check is skipped, never a false positive
    c, _ = check_exec_summary(_ov("22"), available_eids=3, platforms=None)
    assert c.get("platform_fit_stale", 0) == 0


def test_no_fit_clause_is_graceful():
    ov = {"narrative": {"scqa_md":
          "Close Data Lake, at 1.6/5 [E-049, E-068]. The recommended play is "
          "remediation-first. The evidence base reads the same way [E-003]."}}
    c, _ = check_exec_summary(ov, available_eids=3, platforms=_platforms(51.8))
    assert c.get("platform_fit_stale", 0) == 0
