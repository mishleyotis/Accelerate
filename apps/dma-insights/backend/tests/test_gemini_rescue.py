"""The Gemini fallback (nlp/refine.gemini_rescue) — the escalation tier when the
deterministic loop cannot reach the bar. Gemini output is re-graded and returned
ONLY on PASS; a non-JSON / offline / erroring client resolves to None (the caller
keeps the best deterministic draft). Validated with a stub streaming client — no
live Vertex.
"""
from __future__ import annotations

import asyncio
import json
import os

os.environ.setdefault("DMA_DISABLE_SEMANTIC", "1")

from app.services.nlp.composer import compose_card
from app.services.nlp.entity_knowledge import Capability, EntityState
from app.services.nlp.grader import grade
from app.services.nlp.knowledge import EntityKnowledge, Evidence
from app.services.nlp.refine import _parse_gemini, gemini_rescue


def _state() -> EntityState:
    evidence = [
        Evidence("E-mdm", "Master data management is fragmented across 4 core systems, so the same customer is represented differently in each of the bank's platforms.", tier=1, year=2026, owned=True),
        Evidence("E-cx", "The mobile banking experience is a single unified app with modern journeys.", tier=2, year=2026, owned=True),
    ]
    caps = [
        Capability("P4C1.4.1", "Master Data Management", 1.5, 3.0, -1.5, "P4", "P4C1",
                   "Master data management is fragmented across 4 core systems.", "T1", True, ["E-mdm"]),
        Capability("P2C2.1.1", "Digital Servicing Journeys", 3.0, 2.5, 0.5, "P2", "P2C2",
                   "The mobile experience is a unified modern app.", "T1", True, ["E-cx"]),
    ]
    return EntityState(
        run_id="r", entity_id="e", name="Test Bank", subvertical="RB",
        catalog_version="v7.0", capabilities=caps, knowledge=EntityKnowledge(evidence),
        firmographics={}, platforms=[], tech_stack=[], scqa=None, top_findings=[],
        why_now_signals=[{"so_what": "Engage before the 2026 core conversion sets the roadmap."}],
        na_subcap_ids=set(),
        _by_subcap={c.subcap_id: c for c in caps},
        _excerpt_by_eid={e.e_id: e.text for e in evidence},
        _catalogue_names={c.name.lower() for c in caps},
    )


class _StubClient:
    """Minimal async-streaming stand-in for VertexClient."""

    def __init__(self, payload: str = "", *, raise_exc: bool = False) -> None:
        self._payload = payload
        self._raise = raise_exc

    async def stream(self, call):
        if self._raise:
            raise RuntimeError("vertex boom")
        for i in range(0, len(self._payload), 20):   # chunked, like real SSE
            yield self._payload[i:i + 20]


def test_parse_gemini_tolerates_fences_and_prose() -> None:
    assert _parse_gemini('```json\n{"title":"T","what":"W"}\n```') == {
        "title": "T", "what": "W", "why": "", "so_what": ""}
    assert _parse_gemini("here you go: {\"title\":\"T\",\"what\":\"W\"} thanks") is not None
    assert _parse_gemini("OFFLINE FALLBACK: no creds configured") is None
    assert _parse_gemini("") is None
    assert _parse_gemini('{"title":"T"}') is None            # missing 'what'


def test_gemini_rescue_returns_passing_item() -> None:
    st = _state()
    cap = st._by_subcap["P4C1.4.1"]
    draft = compose_card(st, cap, siblings=[st._by_subcap["P2C2.1.1"]])
    assert draft is not None
    # the stub returns a card-quality JSON (mirrors the passing draft's prose)
    payload = json.dumps({"title": draft.title, "what": draft.what,
                          "why": draft.why, "so_what": draft.so_what})
    res = asyncio.run(gemini_rescue(st, cap, draft, grade(draft, st),
                                    client=_StubClient(payload)))
    assert res is not None
    item, g, telem = res
    assert g.passed and telem["path"] == "gemini"
    assert item.e_ids == draft.e_ids            # citations carried from the draft


def test_gemini_rescue_failsafe_on_bad_or_erroring_client() -> None:
    st = _state()
    cap = st._by_subcap["P4C1.4.1"]
    draft = compose_card(st, cap, siblings=[st._by_subcap["P2C2.1.1"]])
    g = grade(draft, st)
    # non-JSON offline string → None
    assert asyncio.run(gemini_rescue(st, cap, draft, g,
                                     client=_StubClient("OFFLINE: no creds"))) is None
    # erroring client → None
    assert asyncio.run(gemini_rescue(st, cap, draft, g,
                                     client=_StubClient(raise_exc=True))) is None


def test_narrate_exec_writes_grounded_summary() -> None:
    import json as _json

    from app.services.nlp.composer import compose_exec, compose_findings
    from app.services.nlp.refine import narrate_exec
    from app.services.nlp.storyline import derive_thesis
    st = _state()
    th = derive_thesis(st)
    findings = compose_findings(st, k=3, thesis=th)
    floor = compose_exec(st, th, findings)          # the grounded floor
    # the LLM returns a natural rewrite mirroring the floor's grounded fields
    payload = _json.dumps({"title": floor.title, "what": floor.what,
                           "why": floor.why, "so_what": floor.so_what})
    item = asyncio.run(narrate_exec(st, th, findings, client=_StubClient(payload)))
    assert item is not None and item.surface == "exec"
    assert grade(item, st).passed
    # fail-safe: offline / erroring client → None (caller keeps compose_exec floor)
    assert asyncio.run(narrate_exec(st, th, findings,
                                    client=_StubClient("OFFLINE: no creds"))) is None
    assert asyncio.run(narrate_exec(st, th, [], client=_StubClient(payload))) is None
