"""G1-G10 trigger matrix contract tests (enum, log roundtrip, dedup, gating)."""
import asyncio
import json
import os

os.environ.setdefault("DMA_DISABLE_SEMANTIC", "1")

from app.services.enrichment_runner import (
    BudgetedEnrichmentRunner,
    EnrichItem,
    VertexGateway,
)
from app.services.enrichment_triggers import (
    Trigger,
    TriggerFiring,
    is_duplicate,
    log_firing,
)


def test_enum_has_all_ten_grounds():
    names = [t.name for t in Trigger]
    assert names == [
        "G1_EMPTY_FIELD", "G2_STALENESS", "G3_CORROBORATION",
        "G4_CONTRADICTION", "G5_OSS_CHALLENGE", "G6_AE_NOTE",
        "G7_CADENCE_TIMER", "G8_NEW_RUN", "G9_PANEL_QUESTION",
        "G10_PEER_REFRESH",
    ]


def test_log_firing_jsonl_roundtrip(tmp_path):
    log = tmp_path / "firings.jsonl"
    firing = TriggerFiring(
        trigger=Trigger.G3_CORROBORATION, query="second source for E-089",
        engine="crawler", outcome="synthesized",
        new_evidence_ids=["ENR-031"], entity_id="e-1", field="cdp_vendor",
        ts="2026-07-11T00:00:00Z")
    log_firing(firing, jsonl_path=str(log))
    row = json.loads(log.read_text().strip())
    assert row["trigger"] == "G3_CORROBORATION"
    assert row["new_evidence_ids"] == ["ENR-031"]
    assert row["engine"] == "crawler"


def test_is_duplicate_thresholds():
    text = "The institution retained three production cores through acquisitions."
    dup, score = is_duplicate(text, [text])
    assert dup and score >= 0.85
    distinct, low = is_duplicate(
        text, ["Mobile app sentiment improved by half a star this quarter."])
    assert not distinct and low < 0.85
    empty, zero = is_duplicate("", [text])
    assert not empty and zero == 0.0


class _FakeSessionMaker:
    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _run(items, monkeypatch, tmp_path, legacy=False):
    monkeypatch.setenv("DMA_ENRICH_LOG", str(tmp_path / "log.jsonl"))
    if legacy:
        monkeypatch.setenv("DMA_ENRICH_LEGACY", "1")
    else:
        monkeypatch.delenv("DMA_ENRICH_LEGACY", raising=False)
    runner = BudgetedEnrichmentRunner(
        session_maker=_FakeSessionMaker(),
        gateway=VertexGateway(vertex_client=None),
        budget_sec=30, concurrency=1)
    return asyncio.run(runner.run(items))


def test_runner_rejects_untriggered_item(monkeypatch, tmp_path):
    ran = []

    async def _proc(session, gateway):
        ran.append(1)
        return "synthesized"

    result = _run([EnrichItem(key="k", surface="s", process=_proc)],
                  monkeypatch, tmp_path)
    assert result.counts.get("defect_no_trigger") == 1
    assert not ran
    log = (tmp_path / "log.jsonl").read_text()
    assert "defect_no_trigger" in log


def test_legacy_escape_hatch_runs_item(monkeypatch, tmp_path):
    ran = []

    async def _proc(session, gateway):
        ran.append(1)
        return "synthesized"

    result = _run([EnrichItem(key="k", surface="s", process=_proc)],
                  monkeypatch, tmp_path, legacy=True)
    assert ran
    assert result.counts.get("synthesized") == 1
    assert '"legacy": true' in (tmp_path / "log.jsonl").read_text()


def test_triggered_item_runs(monkeypatch, tmp_path):
    ran = []

    async def _proc(session, gateway):
        ran.append(1)
        return "synthesized"

    result = _run([EnrichItem(key="k", surface="s", process=_proc,
                              trigger=Trigger.G8_NEW_RUN)],
                  monkeypatch, tmp_path)
    assert ran
    assert result.counts.get("synthesized") == 1
    assert result.counts.get("defect_no_trigger") is None
