"""Pattern recognition over embedded artifacts.

The pgvector indexes from migration 010 (ivfflat cosine on evidence /
insight / recommendation 768-dim embeddings) let us answer:

  - For a given insight card, which insight cards in *other* entities are
    closest in narrative space? — Powers D2 "Pattern: 5 peers had the same
    insight" badges.
  - For a given subcap, which evidence items across the cohort are the
    strongest cosine matches? — Powers the IntelligencePanel "borrow
    evidence" lookups for the Claude project.
  - For a given recommendation, which prior recommendations were issued
    against the same gap pattern? — Powers D4 "this rec has shipped on X
    other engagements" affordance.

This module is intentionally pure — it composes a SQL CASE expression
weighted by `ccg_subvertical_adjacency` (from the rag_cohort router) so
cross-vertical matches don't drown out same-vertical ones, but the actual
cosine ordering happens server-side in pgvector.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# pgvector exposes the <=> operator for cosine distance (0 = identical,
# 2 = opposite). similarity = 1 - distance/2 → [0, 1].
COSINE_DISTANCE_OP = "<=>"


@dataclass(frozen=True)
class SimilarInsight:
    insight_card_id: str
    ic_id: str
    entity_name: str
    title: str
    severity: str
    linked_subcap_id: str
    cohort_match: float           # subvertical adjacency weight (0..1)
    text_similarity: float        # 1 - cosine_distance/2 (0..1)
    combined_score: float         # cohort_match * text_similarity


@dataclass(frozen=True)
class SimilarEvidence:
    evidence_id: str
    e_id: str
    entity_name: str
    source_name: str
    excerpt: str
    tier: int
    cohort_match: float
    text_similarity: float
    combined_score: float


@dataclass(frozen=True)
class SimilarRecommendation:
    recommendation_id: str
    rec_id: str
    entity_name: str
    title: str
    platform_id: str | None
    cohort_match: float
    text_similarity: float
    combined_score: float


# ---------- helpers ----------

def _format_vector(vec: list[float]) -> str:
    """pgvector accepts text-formatted vectors: '[0.1, 0.2, ...]'."""
    return "[" + ",".join(f"{v:.8f}" for v in vec) + "]"


def _cohort_case(weights: dict[str, float]) -> tuple[str, dict[str, object]]:
    """Build a CASE expression scoring each row's `subvertical` by adjacency
    weight. Returns (sql_fragment, bind_params)."""
    if not weights:
        return "0::numeric", {}
    parts: list[str] = []
    params: dict[str, object] = {}
    for i, (code, weight) in enumerate(weights.items()):
        if code == "__lob_overlap__":
            continue
        sv_key = f"pcsv_{i}"
        w_key = f"pcw_{i}"
        parts.append(f"WHEN e.subvertical = :{sv_key} THEN :{w_key}::numeric")
        params[sv_key] = code
        params[w_key] = float(weight)
    if not parts:
        return "0.3::numeric", {}
    return "CASE " + " ".join(parts) + " ELSE 0.3::numeric END", params


# ---------- queries ----------

async def find_similar_insights(
    session: AsyncSession,
    *,
    seed_insight_id: str,
    cohort_weights: dict[str, float],
    top_k: int = 8,
    exclude_entity_id: str | None = None,
) -> list[SimilarInsight]:
    """For an existing insight card, return the K closest cards in *other*
    entities, ranked by `cohort_match * text_similarity`.
    """
    seed = (
        await session.execute(
            text(
                "SELECT embedding FROM insight_embeddings "
                "WHERE insight_card_id = CAST(:id AS uuid)"
            ),
            {"id": seed_insight_id},
        )
    ).first()
    if seed is None:
        return []

    case_sql, case_params = _cohort_case(cohort_weights)
    params: dict[str, object] = {
        "seed_emb": seed.embedding,
        "top_k": top_k,
        **case_params,
    }
    where_extra = ""
    if exclude_entity_id is not None:
        where_extra = "AND ic.entity_id <> CAST(:exclude_eid AS uuid)"
        params["exclude_eid"] = exclude_entity_id

    rows = (
        await session.execute(
            text(
                f"""
                SELECT
                  ic.id AS insight_card_id,
                  ic.ic_id,
                  e.name AS entity_name,
                  ic.title,
                  ic.severity,
                  ic.linked_subcap_id,
                  (1 - (ie.embedding {COSINE_DISTANCE_OP} :seed_emb) / 2)
                    AS text_similarity,
                  {case_sql} AS cohort_match
                FROM insight_embeddings ie
                JOIN insight_cards ic ON ic.id = ie.insight_card_id
                JOIN entities e ON e.id = ic.entity_id
                WHERE ic.id <> CAST(:seed_id AS uuid)
                  {where_extra}
                ORDER BY (ie.embedding {COSINE_DISTANCE_OP} :seed_emb) ASC
                LIMIT :top_k
                """
            ),
            {**params, "seed_id": seed_insight_id},
        )
    ).all()
    return [
        SimilarInsight(
            insight_card_id=str(r.insight_card_id),
            ic_id=r.ic_id,
            entity_name=r.entity_name,
            title=r.title,
            severity=r.severity,
            linked_subcap_id=r.linked_subcap_id,
            cohort_match=float(r.cohort_match),
            text_similarity=float(r.text_similarity),
            combined_score=round(float(r.cohort_match) * float(r.text_similarity), 4),
        )
        for r in rows
    ]


async def find_similar_evidence(
    session: AsyncSession,
    *,
    query_embedding: list[float],
    cohort_weights: dict[str, float],
    min_tier: int = 8,
    top_k: int = 12,
    exclude_entity_id: str | None = None,
) -> list[SimilarEvidence]:
    """Cosine-rank evidence across the cohort.

    Caller embeds the query text once (via the RAG /embed endpoint) and
    passes the 768-dim vector here.
    """
    case_sql, case_params = _cohort_case(cohort_weights)
    params: dict[str, object] = {
        "q_emb": _format_vector(query_embedding),
        "top_k": top_k,
        "min_tier": min_tier,
        **case_params,
    }
    where_extra = ""
    if exclude_entity_id is not None:
        where_extra = "AND ev.entity_id <> CAST(:exclude_eid AS uuid)"
        params["exclude_eid"] = exclude_entity_id

    rows = (
        await session.execute(
            text(
                f"""
                SELECT
                  ev.id AS evidence_id,
                  ev.e_id,
                  e.name AS entity_name,
                  ev.source_name,
                  ev.excerpt,
                  ev.tier,
                  (1 - (em.embedding {COSINE_DISTANCE_OP} CAST(:q_emb AS vector)) / 2)
                    AS text_similarity,
                  {case_sql} AS cohort_match
                FROM evidence_embeddings em
                JOIN evidence_index ev ON ev.id = em.evidence_id
                JOIN entities e ON e.id = ev.entity_id
                WHERE ev.tier <= :min_tier
                  {where_extra}
                ORDER BY (em.embedding {COSINE_DISTANCE_OP} CAST(:q_emb AS vector)) ASC
                LIMIT :top_k
                """
            ),
            params,
        )
    ).all()
    return [
        SimilarEvidence(
            evidence_id=str(r.evidence_id),
            e_id=r.e_id,
            entity_name=r.entity_name,
            source_name=r.source_name,
            excerpt=r.excerpt,
            tier=int(r.tier) if r.tier is not None else None,
            cohort_match=float(r.cohort_match),
            text_similarity=float(r.text_similarity),
            combined_score=round(float(r.cohort_match) * float(r.text_similarity), 4),
        )
        for r in rows
    ]


async def find_similar_recommendations(
    session: AsyncSession,
    *,
    seed_rec_id: str,
    cohort_weights: dict[str, float],
    top_k: int = 8,
    exclude_entity_id: str | None = None,
) -> list[SimilarRecommendation]:
    seed = (
        await session.execute(
            text(
                "SELECT embedding FROM recommendation_embeddings "
                "WHERE recommendation_id = CAST(:id AS uuid)"
            ),
            {"id": seed_rec_id},
        )
    ).first()
    if seed is None:
        return []

    case_sql, case_params = _cohort_case(cohort_weights)
    params: dict[str, object] = {
        "seed_emb": seed.embedding,
        "top_k": top_k,
        **case_params,
    }
    where_extra = ""
    if exclude_entity_id is not None:
        where_extra = "AND r.entity_id <> CAST(:exclude_eid AS uuid)"
        params["exclude_eid"] = exclude_entity_id

    rows = (
        await session.execute(
            text(
                f"""
                SELECT
                  r.id AS recommendation_id,
                  r.rec_id,
                  e.name AS entity_name,
                  r.title,
                  r.platform_id,
                  (1 - (re.embedding {COSINE_DISTANCE_OP} :seed_emb) / 2)
                    AS text_similarity,
                  {case_sql} AS cohort_match
                FROM recommendation_embeddings re
                JOIN recommendations r ON r.id = re.recommendation_id
                JOIN entities e ON e.id = r.entity_id
                WHERE r.id <> CAST(:seed_id AS uuid)
                  {where_extra}
                ORDER BY (re.embedding {COSINE_DISTANCE_OP} :seed_emb) ASC
                LIMIT :top_k
                """
            ),
            {**params, "seed_id": seed_rec_id},
        )
    ).all()
    return [
        SimilarRecommendation(
            recommendation_id=str(r.recommendation_id),
            rec_id=r.rec_id,
            entity_name=r.entity_name,
            title=r.title,
            platform_id=r.platform_id,
            cohort_match=float(r.cohort_match),
            text_similarity=float(r.text_similarity),
            combined_score=round(float(r.cohort_match) * float(r.text_similarity), 4),
        )
        for r in rows
    ]
