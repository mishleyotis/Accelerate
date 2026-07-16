"""Threshold-ladder contract: every classify branch + calibration mapping."""
import itertools

import pytest

from app.services.nlp.thresholds import (
    AUTO_ACCEPT,
    CANDIDATE,
    REVIEW_LOW,
    calibrate,
    classify,
)


@pytest.mark.parametrize("cos", [0.44, 0.0, -0.2])
def test_reject_below_review_low(cos):
    assert classify(cos) == "reject"


@pytest.mark.parametrize("cos", [0.45, 0.61])
def test_review_band(cos):
    assert classify(cos) == "review"


@pytest.mark.parametrize("cos", [0.62, 0.7199])
def test_candidate_band(cos):
    assert classify(cos) == "candidate"


@pytest.mark.parametrize("cos", [0.72, 0.9, 1.0])
def test_auto_accept(cos):
    assert classify(cos) == "auto_accept"


def test_tier_and_recency_demote_to_candidate():
    assert classify(0.8, tier_ok=False) == "candidate"
    assert classify(0.8, recent_ok=False) == "candidate"
    assert classify(0.8, tier_ok=False, recent_ok=False) == "candidate"


def test_margin_forces_review_even_above_auto_accept():
    assert classify(0.80, runner_up=0.76) == "review"     # margin 0.04
    assert classify(0.80, runner_up=0.74) == "auto_accept"  # margin 0.06
    assert classify(0.65, runner_up=0.62) == "review"     # candidate band too
    assert classify(0.80, runner_up=None) == "auto_accept"


def test_margin_does_not_rescue_reject():
    assert classify(0.40, runner_up=0.10) == "reject"


def test_calibrate_monotonic_and_anchored():
    raw = [0.1 + 0.4 * i / 999 for i in range(1000)]   # uniform 0.1-0.5
    cal = calibrate(raw)
    sweep = [cal(x) for x in sorted(raw)]
    assert all(a <= b + 1e-9 for a, b in itertools.pairwise(sweep))
    p25 = raw[249]
    p60 = raw[599]
    p80 = raw[799]
    assert cal(p25) == pytest.approx(REVIEW_LOW, abs=0.02)
    assert cal(p60) == pytest.approx(CANDIDATE, abs=0.02)
    assert cal(p80) == pytest.approx(AUTO_ACCEPT, abs=0.02)
    assert 0.0 <= cal(-5.0) <= 1.0
    assert 0.0 <= cal(5.0) <= 1.0
    assert cal.anchors


def test_calibrate_empty_input_safe():
    cal = calibrate([])
    assert cal(0.5) == pytest.approx(0.5, abs=0.01)
    assert cal(2.0) == 1.0
