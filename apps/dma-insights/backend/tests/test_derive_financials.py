"""Unit tests for build_trajectory's series-consistency guard.

2026-07-06 deploy review: Compeer charted total_assets
[29.5, 30.8, 32.1, 0.48, 34.3] — a $480M net-income figure inside a $30B
series. The guard rescues pure unit mistakes (x1000 / /1000) and drops
genuine cross-metric outliers, auditing every intervention in `anomalies`,
while keeping our 50x band so legitimate loss-year net-income swings survive.
"""
from app.scripts.derive_financials import build_trajectory


def _traj(**kw):
    base = {
        "ta_series": None, "ni_series": None, "branches": None,
        "regulator": None, "geography": None, "headcount": None,
        "source": "report_prose",
    }
    base.update(kw)
    return build_trajectory(**base)


def test_drops_cross_metric_outlier_and_audits():
    ta = {2021: 29.5e9, 2022: 30.8e9, 2023: 32.1e9, 2024: 0.48e9, 2025: 34.3e9}
    traj = _traj(ta_series=ta)
    s = traj["series"]["total_assets"]
    assert s[3] is None and s[0] == 29.5 and s[4] == 34.3       # FY2024 dropped
    assert any("FY2024" in a and "dropped" in a for a in traj["anomalies"])


def test_rescues_pure_unit_mistake():
    # FY2023 stored as 32000B (a x1000 slip) rescues to 32.0B via *0.001.
    ta = {2021: 30.0e9, 2022: 31.0e9, 2023: 32000.0e9, 2024: 33.0e9}
    traj = _traj(ta_series=ta)
    assert traj["series"]["total_assets"][2] == 32.0
    assert any("rescaled" in a for a in traj["anomalies"])


def test_keeps_loss_year_net_income_swing():
    # ~12x below median — our 50x band tolerates legitimate loss-year swings.
    ni = {2021: 150e6, 2022: 130e6, 2023: 12e6, 2024: 140e6}
    traj = _traj(ni_series=ni)
    assert None not in traj["series"]["net_income_m"]
    assert traj["anomalies"] == []
