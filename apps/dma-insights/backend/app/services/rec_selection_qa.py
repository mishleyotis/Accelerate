"""Deterministic recommendation selection-quality gate (2026-07-06).

The production review found rec cards that were grammatically clean but
mis-SELECTED: generic recs not aimed at the entity's own lowest-scoring
gaps, "deploy X" recs for platforms the stack already confirms, the same
recommendation persisted twice under two id spellings (``R1`` vs
``REC-01``), and roadmap phases that schedule a rec BEFORE its declared
prerequisite. This module is the pure QA gate the derive chain runs over
every ACTIVE run's rec set:

  * ``targets_no_observed_gap`` — every category the rec's own text/links
    resolve to is already scored at/above the target band: the rec does
    not address an actual gap of THIS entity.
  * ``ungrounded_gap`` — the rec resolves to NO scored category at all
    (nothing connects it to the entity's own assessment).
  * ``no_evidence_link`` — no ``root_cause_e_ids`` and no inline
    ``[E-###]``/``E-###`` citation anywhere in its prose: the rec cannot
    open evidence, so its premise is unverifiable.
  * ``already_deployed_platform`` — a net-new verb frame ("Deploy /
    Implement / Adopt / Migrate to …") on a platform the entity's tech
    stack already CONFIRMS — mis-targeted; the right rec would optimise
    or expand, not introduce.
  * ``duplicate_rec_id:<other>`` — two rows normalise to the same rec id
    (``R1`` ≡ ``REC-01``): the same recommendation ingested twice.
  * ``near_duplicate:<other>`` — title token-set Jaccard ≥ 0.75 against
    an earlier rec: two cards saying the same thing.
  * ``missing_prerequisite:<id>`` — a declared prerequisite that is not
    in the run's rec set.
  * ``phase_before_prerequisite:<id>`` — scheduled in an earlier phase
    than a prerequisite (sequencing contradiction).
  * ``prerequisite_cycle`` — the prerequisite graph loops.

Pure and deterministic: no DB, no LLM, no clock. The derive layer decides
which flags it can remediate deterministically (duplicate-id keep-richest
delete; phase raised to the prerequisite's phase) and which it only
reports — nothing here fabricates content.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_CAT_RE = re.compile(r"\bP[1-4]C\d+\b")
_EID_RE = re.compile(r"\bE-\d{2,4}\b")
# Net-new introduction verbs — "optimize/expand/extend/consolidate" frames
# are legitimate for an already-owned platform and never flag.
_NET_NEW_RE = re.compile(
    r"\b(?:deploy|implement|adopt|introduce|stand\s+up|roll\s+out|"
    r"migrate\s+to|purchase|license|procure|acquire|install)\b",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")
_TITLE_STOP = frozenset({
    "the", "and", "for", "with", "via", "into", "onto", "from", "across",
    "deploy", "implement", "adopt", "enable", "activate", "strengthen",
    "improve", "modernize", "enhance", "cloud", "platform",
})


@dataclass(frozen=True)
class RecQaInput:
    """The selection-relevant slice of one recommendation row."""

    rec_id: str
    title: str | None = None
    description: str | None = None
    phase: int | None = None
    platform_id: str | None = None
    target_subcap_ids: tuple[str, ...] = ()
    root_cause_e_ids: tuple[str, ...] = ()
    prerequisite_rec_ids: tuple[str, ...] = ()
    # Richness rank for duplicate-id resolution (derive fills it from the
    # row's own content; higher wins).
    richness: int = 0
    flags: list[str] = field(default_factory=list, compare=False)


def norm_rec_id(raw: str) -> str:
    """``R1`` / ``REC-01`` / ``Recommendation 1`` → ``REC-01``."""
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    return f"REC-{int(digits):02d}" if digits else str(raw or "").upper()[:16]


def _title_tokens(title: str | None) -> frozenset[str]:
    # Category ids (P2C1) are targeting METADATA, not content — two cards
    # whose titles differ only in the category token say the same thing.
    bare = _CAT_RE.sub(" ", title or "")
    return frozenset(
        t for t in _TOKEN_RE.findall(bare.lower())
        if t not in _TITLE_STOP
    )


def _resolved_categories(rec: RecQaInput) -> set[str]:
    """Every P?C? category the rec's OWN links/prose name (no fallback
    ladder — the gate verifies the rec's own targeting, not the derive
    layer's ability to rescue it)."""
    cats = {s[:4] for s in rec.target_subcap_ids if len(s) >= 4}
    cats.update(
        m[:4] for m in _CAT_RE.findall(f"{rec.title or ''} {rec.description or ''}")
    )
    return cats


def qa_rec_selection(
    recs: list[RecQaInput],
    *,
    cat_scores: dict[str, float],
    target_band: float = 4.0,
    confirmed_platform_ids: frozenset[str] | set[str] = frozenset(),
) -> dict[str, list[str]]:
    """{rec_id → [flag, …]} for one run's rec set (empty list = clean).

    ``cat_scores`` is the run's own category → average score map;
    ``confirmed_platform_ids`` the CONFIRMED rows of its tech stack.
    Deterministic: same inputs, same flags, stable order.
    """
    flags: dict[str, list[str]] = {r.rec_id: [] for r in recs}

    # ── gap grounding + evidence linkage + platform applicability ──────
    for r in recs:
        cats = _resolved_categories(r)
        scored = {c: cat_scores[c] for c in cats if c in cat_scores}
        if not scored:
            flags[r.rec_id].append("ungrounded_gap")
        elif min(scored.values()) >= target_band:
            flags[r.rec_id].append("targets_no_observed_gap")
        if not r.root_cause_e_ids and not _EID_RE.search(
                f"{r.title or ''} {r.description or ''}"):
            flags[r.rec_id].append("no_evidence_link")
        if (
            r.platform_id
            and r.platform_id in confirmed_platform_ids
            and _NET_NEW_RE.search(r.title or "")
        ):
            flags[r.rec_id].append("already_deployed_platform")

    # ── duplicates (id-normalisation collisions + near-identical titles) ─
    seen_norm: dict[str, str] = {}
    seen_titles: list[tuple[str, frozenset[str]]] = []
    for r in recs:
        norm = norm_rec_id(r.rec_id)
        if norm in seen_norm:
            flags[r.rec_id].append(f"duplicate_rec_id:{seen_norm[norm]}")
        else:
            seen_norm[norm] = r.rec_id
            toks = _title_tokens(r.title)
            if len(toks) >= 2:
                for other_id, other_toks in seen_titles:
                    union = toks | other_toks
                    if union and len(toks & other_toks) / len(union) >= 0.75:
                        flags[r.rec_id].append(f"near_duplicate:{other_id}")
                        break
                seen_titles.append((r.rec_id, toks))

    # ── prerequisite sequencing ─────────────────────────────────────────
    by_norm = {norm_rec_id(r.rec_id): r for r in recs}
    graph: dict[str, list[str]] = {}
    for r in recs:
        node = norm_rec_id(r.rec_id)
        edges: list[str] = []
        for p in r.prerequisite_rec_ids:
            pn = norm_rec_id(p)
            if pn == node:
                continue  # self-references carry no ordering information
            pre = by_norm.get(pn)
            if pre is None:
                flags[r.rec_id].append(f"missing_prerequisite:{p}")
                continue
            edges.append(pn)
            if (r.phase is not None and pre.phase is not None
                    and r.phase < pre.phase):
                flags[r.rec_id].append(f"phase_before_prerequisite:{pre.rec_id}")
        graph[node] = edges

    # Cycle detection (iterative DFS, colours) — flag every member node.
    WHITE, GREY, BLACK = 0, 1, 2
    colour = dict.fromkeys(graph, WHITE)
    in_cycle: set[str] = set()

    def _visit(start: str) -> None:
        stack: list[tuple[str, int]] = [(start, 0)]
        path: list[str] = []
        while stack:
            node, idx = stack.pop()
            if idx == 0:
                colour[node] = GREY
                path.append(node)
            edges = graph.get(node, [])
            advanced = False
            for j in range(idx, len(edges)):
                nxt = edges[j]
                if colour.get(nxt, BLACK) == GREY:
                    # cycle: everything from nxt on the current path.
                    if nxt in path:
                        in_cycle.update(path[path.index(nxt):])
                    continue
                if colour.get(nxt, BLACK) == WHITE:
                    stack.append((node, j + 1))
                    stack.append((nxt, 0))
                    advanced = True
                    break
            if not advanced:
                colour[node] = BLACK
                if path and path[-1] == node:
                    path.pop()

    for node in graph:
        if colour[node] == WHITE:
            _visit(node)
    for node in in_cycle:
        rec = by_norm.get(node)
        if rec is not None and "prerequisite_cycle" not in flags[rec.rec_id]:
            flags[rec.rec_id].append("prerequisite_cycle")

    return flags


def resolve_duplicate_ids(
    recs: list[RecQaInput],
) -> list[tuple[str, str]]:
    """[(loser_rec_id, winner_rec_id), …] for duplicate-id collisions —
    the deterministic remediation input: within each normalised-id group
    the RICHEST row wins (richness, then longer description, then the
    earlier id for stability); the rest are safe to delete because they
    are the same recommendation ingested twice."""
    groups: dict[str, list[RecQaInput]] = {}
    for r in recs:
        groups.setdefault(norm_rec_id(r.rec_id), []).append(r)
    out: list[tuple[str, str]] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        winner = max(members, key=lambda r: (
            r.richness, len(r.description or ""), -members.index(r),
        ))
        out.extend(
            (m.rec_id, winner.rec_id) for m in members if m is not winner
        )
    return out


def rec_richness(row: Any) -> int:
    """Content-richness rank for duplicate resolution, computed from the
    row's own fields (each real field = 1 point)."""
    score = 0
    if getattr(row, "description", None):
        score += 1
    if list(getattr(row, "root_cause_e_ids", None) or []):
        score += 1
    if isinstance(getattr(row, "outcomes", None), dict) and row.outcomes.get("metric"):
        score += 1
    if getattr(row, "feature", None):
        score += 1
    if list(getattr(row, "target_subcap_ids", None) or []):
        score += 1
    return score
