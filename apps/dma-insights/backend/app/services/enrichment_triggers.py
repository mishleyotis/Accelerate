"""Enrichment trigger matrix G1-G10 — the only lawful grounds for enrichment.

Training Specification v2.0 (Tab 01 §1): enrichment never fires because a
model felt like searching. It fires on one of the ten enumerated grounds
below, and every firing is logged (trigger, query, engine, outcome, new
evidence IDs) so the pipeline is auditable and trainable. An enrichment
attempt carrying no valid trigger is a structural defect
(``defect_no_trigger``) — the runner refuses it unless the
``DMA_ENRICH_LEGACY=1`` escape hatch is set.

Dedup discipline (same tab): cosine >= 0.9 on the excerpt embedding means
duplicate — merge instead of insert (lexical fallback threshold 0.85 when the
semantic tier is unavailable; the deciding tier is returned for logging).

The durable ``enrichment_ledger`` table (migration 058) tracks per-gap state
but carries no trigger/engine/outcome columns, so the firing log is an
append-only JSONL ledger (``DMA_ENRICH_LOG`` or
``benchmarks/enrichment_log.jsonl``); ``qa_enrichment_discipline`` audits it.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from enum import Enum

from app.services.nlp import semantic
from app.services.nlp.similarity import LexicalIndex

SEMANTIC_DUP_THRESHOLD = 0.90
LEXICAL_DUP_THRESHOLD = 0.85


class Trigger(str, Enum):
    G1_EMPTY_FIELD = "G1_EMPTY_FIELD"
    G2_STALENESS = "G2_STALENESS"
    G3_CORROBORATION = "G3_CORROBORATION"
    G4_CONTRADICTION = "G4_CONTRADICTION"
    G5_OSS_CHALLENGE = "G5_OSS_CHALLENGE"
    G6_AE_NOTE = "G6_AE_NOTE"
    G7_CADENCE_TIMER = "G7_CADENCE_TIMER"
    G8_NEW_RUN = "G8_NEW_RUN"
    G9_PANEL_QUESTION = "G9_PANEL_QUESTION"
    G10_PEER_REFRESH = "G10_PEER_REFRESH"


@dataclass
class TriggerFiring:
    trigger: Trigger
    query: str
    engine: str            # gemini | clay | crawler | deterministic
    outcome: str           # synthesized | hit | deduped | skipped_cold | ...
    new_evidence_ids: list[str] = field(default_factory=list)
    entity_id: str | None = None
    field: str | None = None
    ts: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["trigger"] = self.trigger.value
        return d


def default_log_path() -> str:
    env = os.environ.get("DMA_ENRICH_LOG")
    if env:
        return env
    backend = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.normpath(os.path.join(
        backend, "..", "benchmarks", "enrichment_log.jsonl"))


def _append_jsonl(path: str, payload: dict) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a") as fh:
            fh.write(json.dumps(payload) + "\n")
    except OSError:
        pass  # the firing log is best-effort; enrichment must never wedge on it


def log_firing(firing: TriggerFiring, *, session=None,
               jsonl_path: str | None = None) -> None:
    """Append the firing to the JSONL ledger. ``session`` is accepted for
    forward-compatibility: the enrichment_ledger table has no
    trigger/engine/outcome columns today (migration 058), so the durable log
    is JSONL-only until a column lands."""
    _append_jsonl(jsonl_path or default_log_path(), firing.to_dict())


def log_defect(key: str, surface: str, *, legacy: bool = False,
               jsonl_path: str | None = None) -> None:
    """Record an enrichment attempt that carried no valid trigger."""
    _append_jsonl(jsonl_path or default_log_path(), {
        "trigger": None, "query": key, "engine": "unknown",
        "outcome": "defect_no_trigger", "new_evidence_ids": [],
        "entity_id": None, "field": surface, "ts": "", "legacy": legacy,
    })


def is_duplicate(excerpt: str, existing: list[str]) -> tuple[bool, float]:
    """Spec dedup rule: cosine >= 0.9 on the excerpt embedding = duplicate."""
    cands = [(i, t) for i, t in enumerate(existing) if (t or "").strip()]
    if not (excerpt or "").strip() or not cands:
        return False, 0.0
    if semantic.model_available():
        idx = semantic.SemanticIndex()
        idx.fit(cands)
        hits = idx.top_k(excerpt, k=1, min_score=0.0)
        best = hits[0][1] if hits else 0.0
        return best >= SEMANTIC_DUP_THRESHOLD, float(best)
    idx = LexicalIndex()
    idx.fit(cands)
    hits = idx.top_k(excerpt, k=1, min_score=0.0)
    best = hits[0][1] if hits else 0.0
    return best >= LEXICAL_DUP_THRESHOLD, float(best)
