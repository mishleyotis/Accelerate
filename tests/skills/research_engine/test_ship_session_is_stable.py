"""Every page the driver ships goes under ONE lease holder.

2026-10-01, Cross Insurance: ship_page.py minted a fresh session per
process, so the heatmap claim was refused by the techstack ship's live
lease — the "other session" was the driver itself.
"""
from engine import pipeline as P


def test_shipper_exports_one_session_to_every_ship(monkeypatch, tmp_path):
    seen = []

    class R:
        returncode, stdout, stderr = 0, "", ""

    def fake_run(cmd, **kw):
        seen.append(kw.get("env", {}).get("DMA_AGENT_SESSION"))
        return R()

    monkeypatch.setattr(P.subprocess, "run", fake_run)
    s = P.ShipPageShipper(session="engine-pipeline-r1")
    for page in ("techstack", "heatmap"):
        s.ship("conn-1", page, tmp_path, tmp_path / f"{page}.json")
    assert seen == ["engine-pipeline-r1", "engine-pipeline-r1"]
