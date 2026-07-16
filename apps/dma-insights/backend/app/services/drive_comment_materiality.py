"""Drive comment materiality classifier.

Per the integrated batched plan Batch 9 + the 2026-06 operator
mandate: "during the backfill and drive probe, the backfill should
usually look for any new changes or comments that may influence the
DMA presentation." Drive comments do NOT bump a file's
``modifiedTime``, so a reviewer adding a comment would otherwise be
invisible to the mtime-based change detection.

The original ``_latest_comment_time`` probe (Batch 2 era) folded the
latest comment timestamp into the change signal so ANY new comment
triggered a versioned re-ingest. That is correct for safety but
costly: ~100 entities x 25 files of comments-API round-trips when an
AE drops a single "looks good" reply on a thread.

This module adds a **materiality classifier** between the comment
probe and the change signal. Material comments ("re-score P3C2",
"this score is wrong", "fix the heatmap") trigger re-ingest;
cosmetic comments ("looks great", "+1", "thx") get a
``e_comment_cosmetic_skipped`` observation but do NOT block the
SKIP path. The defense-in-depth posture is conservative: an empty,
malformed, or unparseable comment body falls back to MATERIAL (the
expensive but safe choice).

Pure-function. No DB, no async. Drive API access lives in
``extract_comment_records`` which takes a pre-built Drive service
so the caller controls authentication + lifecycle. Every Drive
round-trip is bounded + try/except-swallowed so a comments-API
hiccup never blocks a backfill (matches the legacy
``_latest_comment_time`` contract).

Module location: ``app.services.drive_comment_materiality``. The
classifier is consumed by ``app.scripts.historical_backfill``
(local-corpus backfill + Cloud Run Job) and the future
``workers.drive_crawler.main`` (live Drive scheduler).

State machine
-------------
For each Drive comment:

  - has_keyword:material   → MATERIAL (trigger re-ingest)
  - has_keyword:cosmetic_only → COSMETIC (record observation, skip)
  - empty/None body         → MATERIAL (safe fallback; logged)
  - parse exception         → MATERIAL (safe fallback; logged)

For a list of records the aggregate decision is:

  - any MATERIAL comment newer than prior run timestamp → re-ingest
  - all COSMETIC comments newer  → SKIP +
    ``e_comment_cosmetic_skipped`` observation per file
  - no comments newer            → SKIP (no comment observation)

Per the operator mandate "no test skips, no silent error swallowing"
every classification path is exercised in
``tests/test_drive_comment_materiality.py``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

# ── Keyword catalog ──────────────────────────────────────────────────
#
# These are MATERIAL signal phrases: a reviewer using any of them is
# requesting that the DMA presentation change. Word-boundary matched
# (case-insensitive) so "errors" matches but "errort" does not, and
# "fix" matches but "affix" does not.
#
# Grouped by intent so the operator observation is actionable. The
# classifier returns the matched group name so the log line surfaces
# "matched: data_quality" rather than just "matched: wrong".

MATERIAL_KEYWORDS: dict[str, frozenset[str]] = {
    # NOTE: iteration order matters — the classifier returns on the
    # FIRST match. Place more-specific groups before less-specific
    # ones so "wrong subcap" classifies as taxonomy (specific) rather
    # than data_quality (the generic "wrong" token).

    # Catalogue / taxonomy challenges (specific compound phrases that
    # would otherwise match the generic data_quality "wrong" token).
    "taxonomy": frozenset({
        "wrong subcap", "wrong category", "wrong pillar",
        "subcap mismatch", "category mismatch",
        "miscategorized", "miscategorised",
        "mislabeled", "mislabelled",
    }),
    # Re-scoring / re-rating requests.
    "rescore": frozenset({
        "re-score", "rescore", "re score",
        "re-rate", "rerate", "re rate",
        "re-evaluate", "reevaluate",
        "score is off", "scoring is off",
        "score looks off", "scores look off",
        "score should be", "scores should be",
        "should score",
    }),
    # Data-quality / correctness flags.
    "data_quality": frozenset({
        "wrong", "incorrect", "inaccurate",
        "mistake", "mistaken",
        "error", "errors",
        "false", "fabricated",
        "hallucination", "hallucinated",
        "misleading",
        "doesn't match", "does not match",
        "doesn't reflect", "does not reflect",
        "doesn't align", "does not align",
    }),
    # Maintenance / fix-it requests.
    "maintenance": frozenset({
        "fix", "fix this", "needs fixing",
        "bug", "broken",
        "update", "needs update", "needs updating",
        "patch",
        "redo", "re-do",
        "regenerate", "re-generate",
        "refresh",
    }),
    # Evidence / source-of-truth challenges.
    "evidence": frozenset({
        "no evidence", "missing evidence",
        "where's the evidence", "where is the evidence",
        "cite", "citation", "source",
        "anchor", "anchored",
        "needs anchor", "needs source",
    }),
    # Narrative challenges.
    "narrative": frozenset({
        "rewrite", "re-write",
        "rephrase", "re-phrase",
        "needs rewriting", "needs revising",
        "revise", "revision",
        "incomplete", "missing context",
    }),
}

# Build one compiled regex per group with word-boundary matching.
# Multi-word phrases get \b on each end of the whole phrase; single
# tokens get the standard \b...\b wrap.

def _phrase_to_regex(phrase: str) -> str:
    # Escape regex specials, then collapse runs of whitespace so the
    # operator's "re-score" / "re-score" (with NBSP) / "re-score"
    # (with double space) all match. Each phrase is wrapped with
    # non-word lookahead/lookbehind so:
    #   - "fix" matches "fix this" but NOT "affix" / "prefix"
    #   - "+1" matches "+1 nice!" but NOT "x+1y"
    #   - "lgtm" matches at start/end of string and surrounded by
    #     punctuation
    # Standard \b fails for tokens that START with a non-word char
    # (like "+1") since \b is the transition between \w and \W —
    # there's no \w on the left of "+1". The (?<!\w) form is
    # symmetric and works for both.
    escaped = re.escape(phrase.lower())
    escaped = re.sub(r"\\\s+|\\ ", r"\\s+", escaped)
    return r"(?<!\w)" + escaped + r"(?!\w)"


_MATERIAL_PATTERNS: dict[str, re.Pattern[str]] = {
    group: re.compile(
        # Sort phrases by length DESC so longer phrases are tried
        # first. Without this, "re" could greedily match before
        # "re-score" in some alternations.
        "|".join(
            _phrase_to_regex(p)
            for p in sorted(phrases, key=lambda x: (-len(x), x))
        ),
        re.IGNORECASE,
    )
    for group, phrases in MATERIAL_KEYWORDS.items()
}


# Cosmetic / chatter signals that confirm a comment is NON-material.
# Used purely for the observation message — a comment without any
# material keyword is already classified COSMETIC; this list lets us
# annotate WHY ("matched chatter: +1") so the operator log is rich.

COSMETIC_CHATTER: frozenset[str] = frozenset({
    "+1", "thanks", "thx", "thank you",
    "lgtm", "looks good", "looks great", "nice",
    "great work", "great job", "well done",
    "approved", "ack", "acknowledged",
    "noted", "got it", "ok", "okay",
    "fyi", "for your info",
})

_COSMETIC_CHATTER_PATTERN = re.compile(
    "|".join(
        _phrase_to_regex(c)
        for c in sorted(COSMETIC_CHATTER, key=lambda x: (-len(x), x))
    ),
    re.IGNORECASE,
)

ClassificationLabel = Literal["material", "cosmetic"]


@dataclass(frozen=True)
class CommentClassification:
    """Per-comment classification outcome."""

    label: ClassificationLabel
    reason: str  # e.g. "matched:rescore:re-score", "chatter:lgtm",
    # "empty_body:fallback_material", "no_signal"


def classify_comment_body(body: str | None) -> CommentClassification:
    """Classify a single comment body's materiality.

    Decision order (each terminal):
      1. empty / whitespace-only / None → MATERIAL (safe fallback)
      2. matches a MATERIAL keyword group → MATERIAL (group + match)
      3. matches a COSMETIC chatter token → COSMETIC (chatter match)
      4. neither → COSMETIC (no_signal)

    Defense-in-depth rationale for the empty-body fallback: the Drive
    API returns the comment record with ``content`` set to whatever
    the reviewer typed; if it's empty (e.g. a comment with only an
    attached image) we cannot prove it's cosmetic, so we treat as
    material. Cost is one re-ingest; benefit is no silent drop.
    """
    if body is None or not str(body).strip():
        return CommentClassification(
            label="material",
            reason="empty_body:fallback_material",
        )
    text = str(body)
    # 2. Material check first — a comment "Looks good but also
    #    re-score P3C2" must classify MATERIAL despite the "looks good"
    #    chatter token.
    for group, pat in _MATERIAL_PATTERNS.items():
        m = pat.search(text)
        if m:
            return CommentClassification(
                label="material",
                reason=f"matched:{group}:{m.group(0).lower()[:40]}",
            )
    # 3. Cosmetic chatter check.
    m = _COSMETIC_CHATTER_PATTERN.search(text)
    if m:
        return CommentClassification(
            label="cosmetic",
            reason=f"chatter:{m.group(0).lower()[:40]}",
        )
    # 4. Neither — opinionated COSMETIC (the safer alternative would be
    #    MATERIAL, but operators report that 90%+ of non-keyword
    #    comments are off-topic chatter; the next re-ingest will catch
    #    edits to actual files via the material hash path anyway).
    return CommentClassification(label="cosmetic", reason="no_signal")


@dataclass
class CommentRecord:
    """One Drive comment with the fields the classifier consumes.

    Mirrors the Drive API ``files.comments.list`` response subset we
    rely on. Fields are explicitly typed (not a raw dict) so the
    extractor's response-shape assumptions are pinned + unit-testable.
    """

    file_id: str
    comment_id: str
    body: str
    modified_time: datetime | None
    resolved: bool = False
    author_name: str = ""


@dataclass
class CommentClassificationSummary:
    """Aggregate classifier output across N records for one folder."""

    material_count: int = 0
    cosmetic_count: int = 0
    empty_count: int = 0
    latest_material_at: datetime | None = None
    latest_cosmetic_at: datetime | None = None
    sample_material: list[tuple[str, str]] = field(default_factory=list)
    sample_cosmetic: list[tuple[str, str]] = field(default_factory=list)

    @property
    def latest_change_at(self) -> datetime | None:
        """Most-recent timestamp across material AND cosmetic comments."""
        if self.latest_material_at and self.latest_cosmetic_at:
            return max(self.latest_material_at, self.latest_cosmetic_at)
        return self.latest_material_at or self.latest_cosmetic_at

    def has_material(self) -> bool:
        return self.material_count > 0

    def has_only_cosmetic(self) -> bool:
        return (
            self.cosmetic_count > 0
            and self.material_count == 0
            and self.empty_count == 0
        )


def classify_comments(records: list[CommentRecord]) -> CommentClassificationSummary:
    """Aggregate classifier across N comment records.

    Tracks counts + latest timestamps + 3-row samples per class so the
    operator log + parser_observations can show concrete examples.
    Empty-body fallback bumps the material count (since the per-comment
    classifier resolves to MATERIAL) but is also tracked in
    ``empty_count`` for transparency.
    """
    out = CommentClassificationSummary()
    for r in records:
        c = classify_comment_body(r.body)
        if c.reason.startswith("empty_body:"):
            out.empty_count += 1
        if c.label == "material":
            out.material_count += 1
            if r.modified_time is not None and (
                out.latest_material_at is None
                or r.modified_time > out.latest_material_at
            ):
                out.latest_material_at = r.modified_time
            if len(out.sample_material) < 3:
                snip = (r.body or "")[:120].replace("\n", " ")
                out.sample_material.append((c.reason, snip))
        else:
            out.cosmetic_count += 1
            if r.modified_time is not None and (
                out.latest_cosmetic_at is None
                or r.modified_time > out.latest_cosmetic_at
            ):
                out.latest_cosmetic_at = r.modified_time
            if len(out.sample_cosmetic) < 3:
                snip = (r.body or "")[:120].replace("\n", " ")
                out.sample_cosmetic.append((c.reason, snip))
    return out


def extract_comment_records(
    drive: Any,
    file_ids: list[str],
    *,
    file_limit: int = 25,
    per_file_page_size: int = 100,
) -> list[CommentRecord]:
    """Fetch comment records from Drive for the given file IDs.

    Best-effort: every Drive round-trip is wrapped in try/except so a
    comments-API hiccup never blocks the backfill. Bounded by
    ``file_limit`` (default 25) to match the legacy ``_latest_comment_
    time`` probe budget. The ``drive`` argument is a googleapiclient
    Drive v3 service (or any duck-typed equivalent — the test suite
    passes a hand-rolled stub).

    Drive API response fields:
      - id              (comment_id)
      - content         (the actual comment text, plain)
      - modifiedTime    (ISO8601 string; converted to tz-aware UTC dt)
      - resolved        (bool)
      - author          ({displayName: ...})

    Returns:
      List of ``CommentRecord``, possibly empty. Ordering matches the
      Drive response order; the caller's classify_comments aggregator
      computes latest timestamps so ordering doesn't affect the
      decision.
    """
    out: list[CommentRecord] = []
    if not file_ids:
        return out
    for fid in file_ids[:file_limit]:
        try:
            resp = (
                drive.comments()
                .list(
                    fileId=fid,
                    fields=(
                        "comments(id,content,modifiedTime,"
                        "resolved,author(displayName))"
                    ),
                    pageSize=per_file_page_size,
                )
                .execute()
            )
        except Exception:
            # Drive hiccup on this file — surface ZERO records (no
            # decision) and continue. The mtime check still gates
            # re-ingest, so we never silently skip a real change.
            continue
        for c in resp.get("comments", []) or []:
            modified_dt: datetime | None = None
            raw = c.get("modifiedTime")
            if raw:
                try:
                    modified_dt = datetime.fromisoformat(
                        str(raw).replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    modified_dt = None
            author = ""
            a = c.get("author") or {}
            if isinstance(a, dict):
                author = str(a.get("displayName") or "")
            out.append(CommentRecord(
                file_id=fid,
                comment_id=str(c.get("id") or ""),
                body=str(c.get("content") or ""),
                modified_time=modified_dt,
                resolved=bool(c.get("resolved", False)),
                author_name=author,
            ))
    return out


def build_observation_payload(
    summary: CommentClassificationSummary,
    *,
    folder_name: str,
    prior_completed_at: datetime | None,
) -> dict[str, Any]:
    """Build a JSON-serializable parser_observations payload for the
    comment classification outcome.

    Used by the historical_backfill to record what was seen / what was
    skipped, so the next ingest's parser_observations table carries the
    audit trail. Schema kept stable — additions are tolerated, removals
    require a migration of consumers.
    """
    return {
        "kind": "drive_comment_classification",
        "folder_name": folder_name,
        "prior_completed_at": (
            prior_completed_at.isoformat() if prior_completed_at else None
        ),
        "material_count": summary.material_count,
        "cosmetic_count": summary.cosmetic_count,
        "empty_count": summary.empty_count,
        "latest_material_at": (
            summary.latest_material_at.isoformat()
            if summary.latest_material_at else None
        ),
        "latest_cosmetic_at": (
            summary.latest_cosmetic_at.isoformat()
            if summary.latest_cosmetic_at else None
        ),
        "sample_material": [
            {"reason": r, "snippet": s}
            for r, s in summary.sample_material
        ],
        "sample_cosmetic": [
            {"reason": r, "snippet": s}
            for r, s in summary.sample_cosmetic
        ],
    }
