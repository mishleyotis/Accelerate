"""Evidence dedup primitives.

Per the user mandate: "duplicate material being removed to avoid any
issues". Each evidence row gets a content_hash; the persistence layer
uses this hash to detect re-ingest of identical material across runs
and across entities.

State-transition contract (4 branches):

  1. ``kept`` — content_hash has no existing row anywhere → insert
     fresh; link to current run via evidence_run_links
     (first_seen_in_run=True).
  2. ``dedup_same_entity`` — content_hash exists for the SAME entity
     in a prior run → do NOT insert a new evidence_index row; instead
     add an evidence_run_links row pointing the existing evidence to
     the current run (first_seen_in_run=False). Increments the
     "Seen in N prior runs" chip.
  3. ``cross_entity_kept`` — content_hash exists but is owned by a
     DIFFERENT entity → keep both. Two independent evidence_index
     rows can carry the same content_hash. Same news article
     legitimately evidences different clients.
  4. ``duplicate_within_run`` — same content_hash appears 2+ times in
     the SAME run's incoming CSV/JSON. First copy kept, subsequent
     copies dropped with a warning.

Plus one tier-upgrade special case (folded under ``tier_upgrade``):
incoming row has the same content_hash as an existing row owned by
the same entity, but a STRONGER tier (lower number ⇒ stronger
authority per the analyst's canonical T1..T7 scale; ``None`` means the
source stated no tier and is treated as weakest — a known tier always
upgrades an unknown one). The existing row's tier is upgraded; audit
logs the change.

All entry points are pure functions — they take the existing-row
lookup as a callback so unit tests don't need a database.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Literal

DedupAction = Literal[
    "kept",
    "dedup_same_entity",
    "cross_entity_kept",
    "duplicate_within_run",
    "tier_upgrade",
]


def normalize_excerpt(text: str | None) -> str:
    """Clip → collapse whitespace → lowercase. MUST match the SQL
    backfill in migration 018 verbatim, including the order of steps
    and the (notable) absence of an outer ``trim()``.

    SQL contract (migration 018 lines 60-67):

        lower(regexp_replace(
            COALESCE(LEFT(excerpt, 500), ''),
            '\\s+', ' ', 'g'
        ))

    Translated to Python:
      1. text[:500]            — same as LEFT(excerpt, 500)
      2. re.sub(r"\\s+", " ", …) — same as regexp_replace + 'g'
      3. .lower()              — same as lower()

    Critically: there is NO ``.strip()`` at the end. The earlier
    Python implementation called ``.strip()`` after step 1, which
    produced a hash incompatible with the SQL row — verified by an
    adversarial test on 2026-05-26 (``  Hello  World  `` hashed to
    two different SHA256s on the two sides). Run-time dedup against
    SQL-backfilled rows then never matched, silently breaking the
    cross-entity-kept / dedup_same_entity decisions.
    """
    if not text:
        return ""
    truncated = text[:500]
    collapsed = re.sub(r"\s+", " ", truncated)
    return collapsed.lower()


def compute_content_hash(
    *, source_url: str | None, claim_type: str | None, excerpt: str | None,
) -> str:
    """Deterministic SHA-256 keyed by url + claim + normalized excerpt.

    Matches the SQL backfill in migration 018 byte-for-byte (validated
    by `test_evidence_dedup::test_python_and_sql_content_hash_match`).
    Both sides use `|` as the separator.

    NOTE: ``source_url`` and ``claim_type`` are NOT stripped on the
    Python side because the SQL backfill uses ``COALESCE(... , '')``
    only — no `trim()`. Stripping in Python would re-introduce the
    same drift class as the `normalize_excerpt` bug fixed 2026-05-26.
    """
    payload = "|".join([
        (source_url or ""),
        (claim_type or ""),
        normalize_excerpt(excerpt),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class IncomingEvidence:
    """The minimal projection the dedup engine needs. ``tier=None`` means
    the source stated no canonical tier (honest-absent)."""
    e_id: str
    source_url: str | None
    claim_type: str | None
    excerpt: str
    tier: int | None
    entity_id: str
    run_id: str

    @property
    def content_hash(self) -> str:
        return compute_content_hash(
            source_url=self.source_url,
            claim_type=self.claim_type,
            excerpt=self.excerpt,
        )


@dataclass(slots=True)
class ExistingEvidence:
    evidence_id: str
    entity_id: str
    tier: int | None
    content_hash: str


@dataclass(slots=True)
class DedupDecision:
    """One incoming row → one decision row."""
    action: DedupAction
    incoming_e_id: str
    content_hash: str
    kept_evidence_id: str | None       # the canonical row to LINK to
    upgraded_tier_to: int | None = None
    reason: str = ""


def decide(
    incoming: IncomingEvidence,
    *,
    existing_same_entity: ExistingEvidence | None,
    existing_other_entity: ExistingEvidence | None,
    seen_in_this_run: bool,
) -> DedupDecision:
    """Pure decision function.

    The persistence layer is responsible for:
      - performing the actual lookups (one for same-entity, one for
        any-other-entity with the same content_hash);
      - keeping a per-run in-memory ``seen_hashes`` set to detect
        duplicate-within-run.

    Branch ordering (most-specific first):
      1. seen_in_this_run                → duplicate_within_run
      2. existing_same_entity            → tier_upgrade OR dedup_same_entity
      3. existing_other_entity (and not same-entity) → cross_entity_kept
      4. default                         → kept
    """
    h = incoming.content_hash
    if seen_in_this_run:
        return DedupDecision(
            action="duplicate_within_run",
            incoming_e_id=incoming.e_id,
            content_hash=h,
            kept_evidence_id=None,
            reason="identical content_hash appeared earlier in this run",
        )
    if existing_same_entity is not None:
        # Lower tier number = STRONGER authority; None = unknown (weakest).
        # Upgrade if incoming is stronger — a known tier also upgrades an
        # unknown (None) one. An unknown incoming tier never upgrades.
        if incoming.tier is not None and (
            existing_same_entity.tier is None
            or incoming.tier < existing_same_entity.tier
        ):
            return DedupDecision(
                action="tier_upgrade",
                incoming_e_id=incoming.e_id,
                content_hash=h,
                kept_evidence_id=existing_same_entity.evidence_id,
                upgraded_tier_to=incoming.tier,
                reason=(
                    f"existing row tier={existing_same_entity.tier} "
                    f"→ upgrade to tier={incoming.tier}"
                ),
            )
        return DedupDecision(
            action="dedup_same_entity",
            incoming_e_id=incoming.e_id,
            content_hash=h,
            kept_evidence_id=existing_same_entity.evidence_id,
            reason="content_hash already attached to entity; link to existing row",
        )
    if existing_other_entity is not None:
        return DedupDecision(
            action="cross_entity_kept",
            incoming_e_id=incoming.e_id,
            content_hash=h,
            kept_evidence_id=None,    # caller inserts a NEW row scoped to this entity
            reason=(
                f"same content_hash owned by entity={existing_other_entity.entity_id}; "
                "cross-entity evidence kept as independent row"
            ),
        )
    return DedupDecision(
        action="kept",
        incoming_e_id=incoming.e_id,
        content_hash=h,
        kept_evidence_id=None,
        reason="first sighting",
    )
