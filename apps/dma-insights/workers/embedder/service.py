"""Pure embedder logic — text recipes, batch grouping, candidate selection.

IO (DB reads, Vertex calls, DB writes) is at the edges in main.py so this
module is unit-testable without any infrastructure.

State-branch contract:
  - `build_embed_text` is the canonical text recipe per artifact kind. If
    you change the recipe, you must re-embed every prior artifact under a
    new model_version label, or cosine distance becomes meaningless across
    versions.
  - `select_candidates` returns only artifacts that DON'T already have an
    embedding row with the current model_version. Re-running the worker
    is therefore safe.
  - `batchify` splits the candidate list into chunks of `batch_size` so
    Vertex's per-call quota is respected (default 32).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ArtifactKind = Literal["evidence", "insight", "recommendation", "section"]

DEFAULT_BATCH_SIZE = 32


@dataclass(frozen=True)
class EmbedCandidate:
    """One item awaiting embedding. `id` is the artifact's UUID; `kind`
    determines which *_embeddings table it lands in."""
    kind: ArtifactKind
    id: str
    text: str


@dataclass
class EmbedBatchResult:
    """One Vertex round-trip's worth of writes ready for DB persistence."""
    kind: ArtifactKind
    ids: list[str] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    vectors: list[list[float]] = field(default_factory=list)
    model_version: str = ""


# ---------- text recipes ----------

def build_evidence_text(*, source_name: str, claim_type: str, excerpt: str) -> str:
    return f"{source_name.strip()} · {claim_type.strip()} · {excerpt.strip()}"


def build_insight_text(
    *,
    title: str,
    what_text: str,
    why_text: str,
    so_what_text: str,
) -> str:
    return " · ".join(
        s.strip() for s in (title, what_text, why_text, so_what_text) if s
    )


def build_recommendation_text(*, title: str, description: str) -> str:
    return f"{title.strip()} · {description.strip()}"


def build_section_text(*, section_kind: str, heading: str, body: str) -> str:
    """Recipe for `document_sections` rows. We prefix with the section
    kind so RAG queries can find e.g. "Pillar 1 deep dive" content
    via lexical+semantic match. The body is the analyst's prose.
    """
    body_trimmed = body.strip()
    # Cap body at ~6k chars; long sections get split downstream when we
    # graduate to chunked embeddings. Today text-embedding-004 accepts
    # up to ~3072 input tokens (~12k chars) so this is comfortable.
    if len(body_trimmed) > 6000:
        body_trimmed = body_trimmed[:6000]
    return f"{section_kind.strip()} · {heading.strip()} · {body_trimmed}"


def build_embed_text(kind: ArtifactKind, row: dict) -> str:
    """Dispatch by kind. Pure — never raises on missing optional fields."""
    if kind == "evidence":
        return build_evidence_text(
            source_name=str(row.get("source_name", "")),
            claim_type=str(row.get("claim_type", "")),
            excerpt=str(row.get("excerpt", "")),
        )
    if kind == "insight":
        return build_insight_text(
            title=str(row.get("title", "")),
            what_text=str(row.get("what_text", "")),
            why_text=str(row.get("why_text", "")),
            so_what_text=str(row.get("so_what_text", "")),
        )
    if kind == "recommendation":
        return build_recommendation_text(
            title=str(row.get("title", "")),
            description=str(row.get("description", "")),
        )
    if kind == "section":
        return build_section_text(
            section_kind=str(row.get("section_kind", "")),
            heading=str(row.get("heading", "")),
            body=str(row.get("body", "")),
        )
    raise ValueError(f"unknown ArtifactKind: {kind!r}")


# ---------- candidate selection ----------

def select_candidates(
    *,
    artifacts: list[dict],
    existing_embedded_ids: set[str],
    kind: ArtifactKind,
) -> list[EmbedCandidate]:
    """Drop artifacts already embedded under the current model_version."""
    out: list[EmbedCandidate] = []
    for art in artifacts:
        raw_id = art.get("id")
        if raw_id is None:
            continue
        art_id = str(raw_id).strip()
        if not art_id or art_id in existing_embedded_ids:
            continue
        text = build_embed_text(kind, art).strip(" ·").strip()
        if not text or len(text) < 2:
            continue  # skip empty / single-char text (separators only)
        out.append(EmbedCandidate(kind=kind, id=art_id, text=text))
    return out


def batchify(
    candidates: list[EmbedCandidate], batch_size: int = DEFAULT_BATCH_SIZE
) -> list[list[EmbedCandidate]]:
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    return [
        candidates[i : i + batch_size]
        for i in range(0, len(candidates), batch_size)
    ]


def coalesce_batches_by_kind(
    candidates: list[EmbedCandidate],
) -> dict[ArtifactKind, list[EmbedCandidate]]:
    """Group candidates by kind so each Vertex call only contains one
    artifact type (lets the worker upsert into a single table per call).

    Every ArtifactKind literal MUST have a bucket here — "section" was
    missing (latent KeyError the moment a section candidate arrived);
    tests/test_embedder_service.py pins the full-kind contract.
    """
    by_kind: dict[ArtifactKind, list[EmbedCandidate]] = {
        "evidence": [], "insight": [], "recommendation": [], "section": [],
    }
    for c in candidates:
        by_kind[c.kind].append(c)
    return by_kind


# ---------- vector sanity checks (anti-corruption guard) ----------

def is_valid_vector(vec: list[float], expected_dim: int = 768) -> bool:
    if len(vec) != expected_dim:
        return False
    if any(v != v for v in vec):  # NaN check
        return False
    # all-zero is rejected — Vertex returns this on quota errors etc.
    return not all(v == 0.0 for v in vec)


def stitch_mixed_batch(
    *,
    batch: list[EmbedCandidate],
    vectors: list[list[float]],
    model_version: str,
) -> list[EmbedBatchResult]:
    """Stitch one Vertex batch that may SPAN artifact kinds.

    live.embed_run batchifies the flat evidence+insight+recommendation
    candidate list, so a single batch can mix kinds — but persistence is
    per-kind (the kind selects the *_embeddings table). Group the pairs
    by kind, then stitch each group. Raises ValueError on a
    candidate/vector length mismatch (same contract as
    stitch_batch_result). One EmbedBatchResult per kind present, in
    first-seen order.
    """
    if len(batch) != len(vectors):
        raise ValueError(
            f"length mismatch: {len(batch)} candidates vs {len(vectors)} vectors"
        )
    grouped: dict[ArtifactKind, tuple[list[EmbedCandidate], list[list[float]]]] = {}
    for cand, vec in zip(batch, vectors, strict=True):
        cands, vecs = grouped.setdefault(cand.kind, ([], []))
        cands.append(cand)
        vecs.append(vec)
    return [
        stitch_batch_result(
            kind=kind, candidates=cands, vectors=vecs, model_version=model_version,
        )
        for kind, (cands, vecs) in grouped.items()
    ]


def stitch_batch_result(
    *,
    kind: ArtifactKind,
    candidates: list[EmbedCandidate],
    vectors: list[list[float]],
    model_version: str,
) -> EmbedBatchResult:
    """Pair up candidates with their resulting vectors. Skips any vector
    that fails `is_valid_vector` (logged as a warning by the caller)."""
    if len(candidates) != len(vectors):
        raise ValueError(
            f"length mismatch: {len(candidates)} candidates vs "
            f"{len(vectors)} vectors"
        )
    result = EmbedBatchResult(kind=kind, model_version=model_version)
    for cand, vec in zip(candidates, vectors, strict=True):
        if not is_valid_vector(vec):
            continue
        result.ids.append(cand.id)
        result.texts.append(cand.text)
        result.vectors.append(list(vec))
    return result
