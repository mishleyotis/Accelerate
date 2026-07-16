"""Clarification-escalation queue: scripts ASK for research, never guess.

When a composer cannot support a claim from the run's own data — a
topically unrelated excerpt behind a score, a floor finding with no
citable category evidence, a FACT-class signal with no date — the
honest moves are (a) fall back to what IS supportable, and (b) FILE a
clarification so the research tier (deep research / Gemini / Clay in
CI's warm path; an analyst offline) can close the gap. This module is
(b): a durable JSONL queue + a G-ground trigger firing per request,
so every escalation is logged under the Tab-01 enrichment discipline
(G2 verification, G3 corroboration, G9 user-offer).

Dry-run safe: appends are local files; no network. Idempotent per
(entity, surface, subject) via a content key so re-derives don't spam
the queue.

Queue: ``benchmarks/research_queue.jsonl``
Row:   {key, entity, surface, subcap_id, ground, question, context,
        filed_by, status: "open"}
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

from app.services.enrichment_triggers import Trigger, TriggerFiring, log_firing

_HERE = os.path.dirname(__file__)
DEFAULT_QUEUE = os.path.normpath(os.path.join(
    _HERE, "..", "..", "..", "benchmarks", "research_queue.jsonl"))

_GROUNDS = {"G2": Trigger.G2_STALENESS, "G3": Trigger.G3_CORROBORATION,
            "G9": Trigger.G9_PANEL_QUESTION}


def _key(entity: str, surface: str, subject: str) -> str:
    basis = re.sub(r"\W+", " ", f"{entity}|{surface}|{subject}".lower())
    return hashlib.sha256(basis.encode()).hexdigest()[:16]


def file_clarification(*, entity: str, surface: str, question: str,
                       ground: str = "G2", subcap_id: str | None = None,
                       context: str | None = None,
                       filed_by: str = "composer",
                       queue_path: str | None = None) -> str | None:
    """Append one clarification request; returns its key (None on error,
    or when an identical open request already exists). Never raises —
    an escalation must not break the surface it escalates for."""
    try:
        path = queue_path or os.environ.get("DMA_RESEARCH_QUEUE",
                                            DEFAULT_QUEUE)
        key = _key(entity, surface, question[:120])
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        if json.loads(line).get("key") == key:
                            return None
                    except json.JSONDecodeError:
                        continue
        row: dict[str, Any] = {
            "key": key, "entity": entity, "surface": surface,
            "subcap_id": subcap_id, "ground": ground,
            "question": question[:500],
            "context": (context or "")[:500] or None,
            "filed_by": filed_by, "status": "open",
        }
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        trig = _GROUNDS.get(ground, Trigger.G2_STALENESS)
        log_firing(TriggerFiring(
            trigger=trig, query=question[:200], engine="research_queue",
            outcome="queued", entity_id=entity, field=surface))
        return key
    except Exception:
        return None
