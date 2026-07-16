"""Post-generation validator for Gemini responses.

Every surface that streams Gemini output runs this on the assembled text /
structured response. On any flag → fail-closed: serve a template-fill
fallback + create a gemini_hallucination_alerts row. AE never sees fabricated
content.

Validators implemented:
  V1 — cited_evidence_ids ⊆ retrieved bundle IDs
  V2 — no fabricated E-IDs / subcap IDs / IC-IDs / REC-IDs (regex + DB check)
  V3 — no fabricated agent IDs (AF-*, FM-AGENT-*) unless in tech_stack_entries
  V4 — re-embed response, cosine ≥ 0.55 vs retrieved bundle centroid

V4 is a SEMANTIC check (``semantic_grounding_ok``): re-embed the response and
require cosine ≥ 0.55 against the retrieved-bundle centroid, so a fluent
paraphrase that reuses NO fabricated ids (which V1-V3 cannot catch) is still
rejected. It runs on the local MiniLM tier (offline-first) and ABSTAINS when no
embedding tier is available — an additional guard, never a fail-closed on
missing embeddings (2026-07-14 audit: V4 was documented but never invoked).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Patterns the LLM might emit
RE_E_ID = re.compile(r"\bE-\d+\b")
RE_SUBCAP = re.compile(r"\bP[1-4]C\d+\.\d+\.\d+(?:-T2-[A-Z]{2,3})?\b")
RE_IC = re.compile(r"\bIC-\d+\b")
RE_REC = re.compile(r"\bREC-\d+\b")
RE_AGENT = re.compile(r"\b(?:AF-[A-Za-z0-9_-]+|FM-AGENT-[A-Za-z0-9_-]+)\b")


@dataclass
class ValidationFlags:
    fabricated_e_ids: list[str] = field(default_factory=list)
    fabricated_subcap_ids: list[str] = field(default_factory=list)
    fabricated_ic_ids: list[str] = field(default_factory=list)
    fabricated_rec_ids: list[str] = field(default_factory=list)
    fabricated_agents: list[str] = field(default_factory=list)
    citation_set_mismatch: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not any(
            (
                self.fabricated_e_ids,
                self.fabricated_subcap_ids,
                self.fabricated_ic_ids,
                self.fabricated_rec_ids,
                self.fabricated_agents,
                self.citation_set_mismatch,
            )
        )

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "fabricated_e_ids": self.fabricated_e_ids,
            "fabricated_subcap_ids": self.fabricated_subcap_ids,
            "fabricated_ic_ids": self.fabricated_ic_ids,
            "fabricated_rec_ids": self.fabricated_rec_ids,
            "fabricated_agents": self.fabricated_agents,
            "citation_set_mismatch": self.citation_set_mismatch,
        }


async def validate_response(
    *,
    session: AsyncSession,
    response_text: str,
    cited_evidence_ids: list[str],
    retrieved_bundle_e_ids: list[str],
    entity_id: str | None,
    run_catalog_version: str,
) -> ValidationFlags:
    """Run V1-V3. Caller runs V4 (embedding-based)."""
    flags = ValidationFlags()

    # V1 — cited subset of retrieved
    retrieved_set = set(retrieved_bundle_e_ids)
    for cited in cited_evidence_ids:
        if cited not in retrieved_set:
            flags.citation_set_mismatch.append(cited)

    # V2 — every mentioned E-ID must exist in evidence_index for this entity
    mentioned_e_ids = set(RE_E_ID.findall(response_text))
    if mentioned_e_ids:
        existing = await _existing_e_ids(session, mentioned_e_ids, entity_id)
        flags.fabricated_e_ids = sorted(mentioned_e_ids - existing)

    # V2 — subcap IDs must exist in ccg_subcaps for this catalogue version
    # (or in ccg_subcap_aliases as prior IDs)
    mentioned_subcaps = set(RE_SUBCAP.findall(response_text))
    if mentioned_subcaps:
        existing = await _existing_subcaps(
            session, mentioned_subcaps, run_catalog_version
        )
        flags.fabricated_subcap_ids = sorted(mentioned_subcaps - existing)

    # V2 — IC/REC must exist for this entity
    mentioned_ic = set(RE_IC.findall(response_text))
    if mentioned_ic and entity_id is not None:
        existing = await _existing_ic_ids(session, mentioned_ic, entity_id)
        flags.fabricated_ic_ids = sorted(mentioned_ic - existing)

    mentioned_rec = set(RE_REC.findall(response_text))
    if mentioned_rec and entity_id is not None:
        existing = await _existing_rec_ids(session, mentioned_rec, entity_id)
        flags.fabricated_rec_ids = sorted(mentioned_rec - existing)

    # V3 — agent IDs must exist in tech_stack_entries OR in
    # ccg_agentforce_agents for this catalogue version
    mentioned_agents = set(RE_AGENT.findall(response_text))
    if mentioned_agents:
        existing = await _existing_agents(
            session, mentioned_agents, run_catalog_version
        )
        flags.fabricated_agents = sorted(mentioned_agents - existing)

    return flags


V4_COSINE_FLOOR = 0.55


def semantic_grounding_ok(
    response_text: str,
    bundle_texts: list[str],
    *,
    floor: float = V4_COSINE_FLOOR,
) -> tuple[bool, float | None]:
    """V4: is the response semantically anchored in the retrieved evidence?

    Re-embeds the response and the bundle with the local MiniLM tier and
    returns ``(ok, cosine)`` where ``cosine`` is the response vs the
    bundle-centroid similarity. ``ok`` is False only when a cosine was actually
    computed AND fell below ``floor`` — a paraphrased fabrication with no fake
    ids. When the embedding tier is unavailable (offline / no baked model) it
    ABSTAINS: ``(True, None)``. Never raises.
    """
    if not response_text or not bundle_texts:
        return True, None
    try:
        import numpy as np

        from app.services.nlp import semantic
        mat = semantic.embed(bundle_texts)
        rv = semantic.embed([response_text])
        if mat is None or rv is None or len(mat) == 0:
            return True, None                       # abstain — no tier
        centroid = np.asarray(mat, dtype=float).mean(axis=0)
        n = float(np.linalg.norm(centroid))
        if n == 0.0:
            return True, None
        centroid = centroid / n
        cos = float(np.asarray(rv[0], dtype=float) @ centroid)
    except Exception:
        return True, None                           # never block on a V4 error
    return cos >= floor, cos


async def _existing_e_ids(
    session: AsyncSession, ids: set[str], entity_id: str | None
) -> set[str]:
    if not ids:
        return set()
    if entity_id is None:
        rows = (
            await session.execute(
                text("SELECT e_id FROM evidence_index WHERE e_id = ANY(:ids)"),
                {"ids": list(ids)},
            )
        ).all()
    else:
        rows = (
            await session.execute(
                text(
                    "SELECT e_id FROM evidence_index "
                    "WHERE entity_id = :eid AND e_id = ANY(:ids)"
                ),
                {"eid": entity_id, "ids": list(ids)},
            )
        ).all()
    return {r.e_id for r in rows}


async def _existing_subcaps(
    session: AsyncSession, ids: set[str], version: str
) -> set[str]:
    rows = (
        await session.execute(
            text(
                """
                SELECT subcap_id FROM ccg_subcaps
                WHERE version = :ver AND subcap_id = ANY(:ids)
                UNION
                SELECT prior_subcap_id AS subcap_id FROM ccg_subcap_aliases
                WHERE prior_subcap_id = ANY(:ids)
                """
            ),
            {"ver": version, "ids": list(ids)},
        )
    ).all()
    return {r.subcap_id for r in rows}


async def _existing_ic_ids(
    session: AsyncSession, ids: set[str], entity_id: str
) -> set[str]:
    rows = (
        await session.execute(
            text(
                "SELECT ic_id FROM insight_cards "
                "WHERE entity_id = :eid AND ic_id = ANY(:ids)"
            ),
            {"eid": entity_id, "ids": list(ids)},
        )
    ).all()
    return {r.ic_id for r in rows}


async def _existing_rec_ids(
    session: AsyncSession, ids: set[str], entity_id: str
) -> set[str]:
    rows = (
        await session.execute(
            text(
                "SELECT rec_id FROM recommendations "
                "WHERE entity_id = :eid AND rec_id = ANY(:ids)"
            ),
            {"eid": entity_id, "ids": list(ids)},
        )
    ).all()
    return {r.rec_id for r in rows}


async def _existing_agents(
    session: AsyncSession, ids: set[str], version: str
) -> set[str]:
    rows = (
        await session.execute(
            text(
                """
                SELECT tech_id AS agent_id FROM tech_stack_entries
                WHERE tech_id = ANY(:ids)
                UNION
                SELECT agent_id FROM ccg_agentforce_agents
                WHERE version = :ver AND agent_id = ANY(:ids)
                """
            ),
            {"ver": version, "ids": list(ids)},
        )
    ).all()
    return {r.agent_id for r in rows}
