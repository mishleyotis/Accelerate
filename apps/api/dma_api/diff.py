"""Run-to-run diff — the surface that makes a rerun visible.

  GET /v1/entities/{display_id}/diff?base=<run_id>&target=<run_id>

## Why the surface was refusing to render

The prototype's version diff synthesised its base run from the target:
`base = score - 0.2 - (id.charCodeAt(2) % 5) / 12`. Under a real client that
renders as movement between two assessments that never happened, so the live
build refuses to draw it at all and says the two-run cell read is not wired
up. This is that read.

It could not have been wired up before, because there was no way to ask for
one: every page endpoint resolves exactly ONE run, and `/subcaps` takes a
single `run`. Two calls would have left the front end to decide what "the
previous run" is — the decision that must not be made twice in two places.

## What it refuses to do

Not fabricate a base. `serving_directory` holds only PROMOTED runs; if an
entity has one, there is nothing to compare against and this returns
`comparable: false` with `kind: "no_base_run"` and the count it saw. A
surface renders that sentence. It does not render a diff against a run that
does not exist, and it does not fall back to the peer median, the catalogue,
or last week.

## Across a catalogue bump

Baxter's served run is pinned to v5.0 (HISTORICAL, 17 categories) while v7.0
is current, so the FIRST genuine rerun crosses a version boundary. A cell that
exists in both versions compares directly. A cell that was renamed resolves
through `ccg_aliases` — the bridge the catalogue already carries — and the
row says it was bridged and from what. A cell that exists in only one of the
two versions is `NOT_COMPARABLE`, with the reason, and contributes to NO
count: all 31 of them are P1C5 (ESG), the seventeenth category v7.0 killed,
and scoring their disappearance as "movement" would report a taxonomy change
as a client regression.

## Nothing here is inference

Every number is subtraction over two promoted scores. No ranking, no
weighting, no significance test — a delta and the two values that produced
it, so a reader can check the arithmetic. Cells are ordered by |delta| so the
movement is at the top; ties break on the cell id so the order is stable.
"""
from __future__ import annotations

from .pages import AUDIENCES, ApiError, resolve_run
from .subverticals import scope_to_entity

MAX_CELLS = 2000

#: Why a cell could not be compared. Four values, each of which a surface can
#: state in a sentence — never a silent omission.
NOT_COMPARABLE = (
    "CELL_ABSENT_FROM_BASE_CATALOGUE",
    "CELL_ABSENT_FROM_TARGET_CATALOGUE",
    "SCORE_MISSING_ON_BASE",
    "SCORE_MISSING_ON_TARGET",
)

_COLS = ("subcap_id", "capability_id", "category_id", "pillar_id",
         "subcap_name", "score", "confidence", "linked_evidence_count",
         "is_thin_evidence")


def _cells(cur, run_id: str, sub_vertical: str | None) -> dict:
    cur.execute(
        f"SELECT {', '.join(_COLS)} FROM serving_subcaps "
        "WHERE run_id = %s ORDER BY subcap_id", (run_id,))
    rows = scope_to_entity(cur.fetchall(), sub_vertical,
                           key=_COLS.index("subcap_id"))
    out = {}
    for r in rows:
        d = dict(zip(_COLS, r))
        d["score"] = float(d["score"]) if d["score"] is not None else None
        out[d["subcap_id"]] = d
    return out


def _bridge(cur, from_version: str | None, to_version: str | None) -> dict:
    """The catalogue's own rename map, base version -> target version.

    Read, never inferred: `ccg_aliases` is loaded from the catalogue and its
    `reason` column already says renamed / split / merged / retired.
    """
    if not from_version or not to_version or from_version == to_version:
        return {}
    cur.execute(
        """SELECT from_subcap_id, to_subcap_id, reason FROM ccg_aliases
            WHERE from_version = %s AND to_version = %s
              AND to_subcap_id IS NOT NULL""",
        (from_version, to_version))
    return {f: {"to": t, "reason": reason} for f, t, reason in cur.fetchall()}


def _known_cells(cur, version: str | None) -> set:
    if not version:
        return set()
    cur.execute("SELECT subcap_id FROM ccg_subcaps WHERE version = %s", (version,))
    return {r[0] for r in cur.fetchall()}


def _pick_runs(cur, display_id: str, base: str | None, target: str | None):
    """Both ends of the comparison, from the one view svc_api resolves runs
    through. The target defaults to the run the pages are serving; the base
    defaults to the promoted run immediately before it."""
    cur.execute(
        """SELECT run_id, request_id, run_seq, is_active, promoted_at,
                  completed_at, ccg_catalog_version, composite, scored_cells,
                  assessment_date, assessment_date_basis, refresh_due_date
             FROM serving_directory
            WHERE display_id = %s
            ORDER BY run_seq DESC, promoted_at DESC""", (display_id,))
    rows = cur.fetchall()
    if not rows:
        raise ApiError(404, "entity_not_found",
                       f"no promoted run for {display_id!r}")

    def meta(r):
        return {"run_id": str(r[0]), "request_id": r[1], "run_seq": r[2],
                "is_active": bool(r[3]),
                "promoted_at": r[4].isoformat() if r[4] else None,
                "completed_at": r[5].isoformat() if r[5] else None,
                "ccg_catalog_version": r[6],
                "composite": float(r[7]) if r[7] is not None else None,
                "scored_cells": r[8],
                "assessment_date": (r[9].isoformat()
                                    if hasattr(r[9], "isoformat") else r[9]),
                "assessment_date_basis": r[10]}

    by_id = {str(r[0]): r for r in rows}
    if target:
        if target not in by_id:
            raise ApiError(404, "entity_not_found",
                           f"run {target} has no promoted rows under {display_id}")
        t = by_id[target]
    else:
        t = next((r for r in rows if r[3]), rows[0])

    b = None
    if base:
        if base not in by_id:
            raise ApiError(404, "entity_not_found",
                           f"run {base} has no promoted rows under {display_id}")
        b = by_id[base]
        if str(b[0]) == str(t[0]):
            raise ApiError(400, "same_run",
                           "base and target name the same run; a diff needs two")
    else:
        later = [r for r in rows if (r[2] or 0) < (t[2] or 0)]
        b = later[0] if later else None

    return ([meta(r) for r in rows], meta(t), meta(b) if b is not None else None)


def build_diff(cur, display_id: str, audience: str = "internal",
               base: str | None = None, target: str | None = None,
               role: str | None = None, limit: int = MAX_CELLS) -> dict:
    if audience not in AUDIENCES:
        raise ApiError(400, "unknown_audience",
                       f"audience must be one of {' · '.join(AUDIENCES)}")
    limit = max(1, min(int(limit), MAX_CELLS))

    # Entity identity and the serving run come from the same resolver every
    # page uses, so the diff header names the client the same way the pages do.
    _entity_id, entity, run_meta, _ = resolve_run(cur, display_id, None, True)
    runs, t_meta, b_meta = _pick_runs(cur, display_id, base, target)

    head = {"entity": entity, "audience": audience, "page": "diff",
            "runs": runs, "target": t_meta, "base": b_meta,
            "run": run_meta}

    if b_meta is None:
        # The honest empty state. Not an error: one run is a complete and
        # correct answer to "what changed", it is just not a diff.
        head["comparable"] = False
        head["cells"] = []
        head["summary"] = None
        head["empty_state"] = {
            "kind": "no_base_run",
            "reason": (
                f"{display_id} has {len(runs)} promoted run"
                f"{'' if len(runs) == 1 else 's'}; a diff reads the cell grain "
                "of two runs and reports the movement between them. There is "
                "no earlier promoted run to compare against, and one is never "
                "derived from the other."),
            "promoted_runs": len(runs),
            "sources_searched": ["serving_directory (promoted runs only)"],
        }
        return head

    sub_vertical = entity.get("sub_vertical")
    base_cells = _cells(cur, b_meta["run_id"], sub_vertical)
    target_cells = _cells(cur, t_meta["run_id"], sub_vertical)

    b_ver, t_ver = b_meta["ccg_catalog_version"], t_meta["ccg_catalog_version"]
    bridge = _bridge(cur, b_ver, t_ver)
    b_known = _known_cells(cur, b_ver) if b_ver and b_ver != t_ver else set()
    t_known = _known_cells(cur, t_ver) if b_ver and b_ver != t_ver else set()

    cells, not_comparable = [], []
    seen_targets = set()

    for cell_id, b in sorted(base_cells.items()):
        t_id, bridged = cell_id, None
        if cell_id in bridge:
            t_id = bridge[cell_id]["to"]
            bridged = {"from": cell_id, "to": t_id,
                       "reason": bridge[cell_id]["reason"]}
        t = target_cells.get(t_id)
        if t is None:
            reason = ("CELL_ABSENT_FROM_TARGET_CATALOGUE"
                      if t_known and t_id not in t_known
                      else "SCORE_MISSING_ON_TARGET")
            not_comparable.append({
                "subcap_id": cell_id, "target_subcap_id": t_id,
                "category_id": b["category_id"], "pillar_id": b["pillar_id"],
                "subcap_name": b["subcap_name"], "bridged": bridged,
                "reason": reason,
                "base_score": b["score"], "target_score": None})
            continue
        seen_targets.add(t_id)
        if b["score"] is None or t["score"] is None:
            not_comparable.append({
                "subcap_id": cell_id, "target_subcap_id": t_id,
                "category_id": t["category_id"], "pillar_id": t["pillar_id"],
                "subcap_name": t["subcap_name"] or b["subcap_name"],
                "bridged": bridged,
                "reason": ("SCORE_MISSING_ON_BASE" if b["score"] is None
                           else "SCORE_MISSING_ON_TARGET"),
                "base_score": b["score"], "target_score": t["score"]})
            continue
        cells.append({
            "subcap_id": cell_id, "target_subcap_id": t_id,
            "category_id": t["category_id"], "pillar_id": t["pillar_id"],
            "capability_id": t["capability_id"],
            "subcap_name": t["subcap_name"] or b["subcap_name"],
            "bridged": bridged,
            "base_score": b["score"], "target_score": t["score"],
            # Subtraction over two promoted values, rounded ONCE at the same
            # 2dp the scores are stored at — not re-derived, not weighted.
            "delta": round(t["score"] - b["score"], 2),
            "base_evidence_count": b["linked_evidence_count"],
            "target_evidence_count": t["linked_evidence_count"],
            "base_is_thin_evidence": b["is_thin_evidence"],
            "target_is_thin_evidence": t["is_thin_evidence"],
            "base_confidence": b["confidence"],
            "target_confidence": t["confidence"],
        })

    for cell_id, t in sorted(target_cells.items()):
        if cell_id in seen_targets or cell_id in base_cells:
            continue
        not_comparable.append({
            "subcap_id": cell_id, "target_subcap_id": cell_id,
            "category_id": t["category_id"], "pillar_id": t["pillar_id"],
            "subcap_name": t["subcap_name"], "bridged": None,
            "reason": ("CELL_ABSENT_FROM_BASE_CATALOGUE"
                       if b_known and cell_id not in b_known
                       else "SCORE_MISSING_ON_BASE"),
            "base_score": None, "target_score": t["score"]})

    # Largest movement first; the cell id breaks ties so the order is stable
    # across calls and a cursor over it would not skip rows.
    cells.sort(key=lambda c: (-abs(c["delta"]), c["subcap_id"]))
    not_comparable.sort(key=lambda c: (c["reason"], c["subcap_id"]))

    moved = [c for c in cells if c["delta"] != 0]
    head.update({
        "comparable": True,
        "empty_state": None,
        "cells": cells[:limit],
        "not_comparable": not_comparable,
        "catalogue": {
            "base_version": b_ver, "target_version": t_ver,
            "crossed_a_bump": bool(b_ver and t_ver and b_ver != t_ver),
            "bridged_cells": sum(1 for c in cells if c["bridged"]),
            "aliases_available": len(bridge),
        },
        "summary": {
            "compared": len(cells),
            "returned": len(cells[:limit]),
            "moved": len(moved),
            "improved": sum(1 for c in moved if c["delta"] > 0),
            "declined": sum(1 for c in moved if c["delta"] < 0),
            "unchanged": len(cells) - len(moved),
            "not_comparable": len(not_comparable),
            # The composites are promoted figures, not recomputed from the
            # cells above: a mean of the compared subset is not the run's
            # composite, and printing one beside the other invites the reader
            # to treat them as the same number.
            "base_composite": b_meta["composite"],
            "target_composite": t_meta["composite"],
            "composite_delta": (
                round(t_meta["composite"] - b_meta["composite"], 2)
                if b_meta["composite"] is not None
                and t_meta["composite"] is not None else None),
        },
    })
    return head
