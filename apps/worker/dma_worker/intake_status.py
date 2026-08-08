"""What has NOT been processed — per intake folder, by name.

The routine's step 1 is "is there anything to do?", and until now nothing
in the system could answer it. `import_scans` counts files, `runs` counts
runs, and neither knows the intake tree's folder list: a client folder
that has never produced a run leaves no row anywhere, so 47 of the 170
folders under the intake tree were invisible to every query in the
codebase. The folder list only exists in Drive, so this joins the walked
tree to the ingested tier and names every folder in one of six states:

    no_run                  nothing has ever been ingested from this folder
    run_unparsed            a run exists and scored zero cells
    parsed_unsynthesised    cells landed; no synthesis has claimed the run
    synthesised_unpromoted  claimed/synthesising/staged, never promoted
    promoted_current        promoted and serving
    promoted_superseded     promoted once, replaced by a later run

`reason` names the blocker where the state alone does not: a folder that
ships no scoring workbook, a package quarantined after repeated ingest
failures, a run with no catalogue version pinned, a run already
superseded by a newer ingest of the same entity. A folder that is simply
waiting its turn carries `reason = None` — that is the queue, and
everything else is a fault with a name.

Read-only: SELECTs against the ingested tier and the ingest-ops ledgers,
which is all svc_worker needs and all this is allowed to do.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

NO_RUN = "no_run"
RUN_UNPARSED = "run_unparsed"
PARSED_UNSYNTHESISED = "parsed_unsynthesised"
SYNTHESISED_UNPROMOTED = "synthesised_unpromoted"
PROMOTED_CURRENT = "promoted_current"
PROMOTED_SUPERSEDED = "promoted_superseded"

#: Report order — the pipeline's own order, so the top of the table is
#: always the work that has moved least.
STATES = (NO_RUN, RUN_UNPARSED, PARSED_UNSYNTHESISED, SYNTHESISED_UNPROMOTED,
          PROMOTED_SUPERSEDED, PROMOTED_CURRENT)

#: runs.status values that mean synthesis has begun but not landed.
_IN_FLIGHT = ("CLAIMED", "SYNTHESISING", "STAGED")

PACKAGE_FAILURE_KIND = "package_ingest_failed"


@dataclass(frozen=True)
class FolderState:
    folder: str
    state: str
    reason: str | None = None
    run_id: str | None = None
    run_seq: int | None = None
    run_status: str | None = None
    scored_cells: int = 0
    artefacts: tuple = ()

    @property
    def blocked(self) -> bool:
        """True when this folder is stuck for a nameable reason rather than
        queued. `promoted_current` is never blocked."""
        return self.reason is not None and self.state != PROMOTED_CURRENT


@dataclass
class RunRow:
    """One row of the ingested tier, as this module needs it."""
    run_id: str
    source_folder: str | None
    entity_id: str | None
    run_seq: int | None = None
    status: str | None = None
    is_active: bool = False
    promoted_at: object = None
    catalogue_version: str | None = None
    scored_cells: int = 0
    completed_at: object = None


#: How far along the pipeline each runs.status value sits. SUPERSEDED ranks
#: below PROMOTED but above the pre-promotion states: it means this run once
#: served, which is further than a run that never has.
_STATUS_RANK = {"INGESTED": 1, "CLAIMED": 2, "SYNTHESISING": 3, "STAGED": 4,
                "SUPERSEDED": 5, "PROMOTED": 6}


def _governing(runs: list[RunRow]) -> RunRow:
    """The run a folder is judged by: the serving one if there is one, then
    the furthest along the pipeline, then the highest run_seq. A folder with
    two ingests is described by its newest, not by whichever sorted first."""

    def key(r: RunRow):
        return (1 if r.is_active else 0,
                1 if r.promoted_at else 0,
                _STATUS_RANK.get(r.status or "", 0),
                r.run_seq or 0,
                str(r.completed_at or ""),
                r.run_id)
    return max(runs, key=key)


def classify_folder(folder: str, artefacts: set, runs: list[RunRow],
                    failure: dict | None = None,
                    entity_runs: dict | None = None) -> FolderState:
    """Place one intake folder in the pipeline. Pure — every input is data."""
    arts = tuple(sorted(a for a in (artefacts or ()) if a != "folder"))
    if not runs:
        if failure and failure.get("quarantined"):
            reason = (f"quarantined after {failure['attempts']} ingest attempt(s): "
                      f"{failure.get('error')}")
        elif failure:
            reason = (f"{failure['attempts']} failed ingest attempt(s), retrying: "
                      f"{failure.get('error')}")
        elif "workbook" not in arts:
            reason = ("no scoring workbook artefact in the folder"
                      + (f" (has {', '.join(arts)})" if arts else " (folder is empty"
                         " of recognised artefacts)"))
        else:
            reason = "scoring workbook present, never ingested"
        return FolderState(folder, NO_RUN, reason, artefacts=arts)

    r = _governing(runs)
    common = dict(run_id=r.run_id, run_seq=r.run_seq, run_status=r.status,
                  scored_cells=r.scored_cells, artefacts=arts)

    if r.promoted_at is not None:
        state = PROMOTED_CURRENT if r.is_active else PROMOTED_SUPERSEDED
        reason = None if r.is_active else "a later run for this entity is serving"
        return FolderState(folder, state, reason, **common)
    if r.status in _IN_FLIGHT:
        return FolderState(folder, SYNTHESISED_UNPROMOTED,
                           f"claimed at {r.status}, never promoted", **common)
    if r.scored_cells == 0:
        return FolderState(folder, RUN_UNPARSED,
                           "the workbook parsed to zero scored cells", **common)

    reason = None
    if not r.catalogue_version:
        reason = "no catalogue version pinned — synthesis has nothing to score against"
    elif entity_runs and r.entity_id:
        newer = [o for o in entity_runs.get(r.entity_id, [])
                 if (o.run_seq or 0) > (r.run_seq or 0)]
        if newer:
            reason = (f"superseded by run_seq {max(o.run_seq or 0 for o in newer)} "
                      f"of the same entity")
    return FolderState(folder, PARSED_UNSYNTHESISED, reason, **common)


def folder_states(folders, artefacts: dict, runs: list[RunRow],
                  failures: dict | None = None) -> list[FolderState]:
    """Classify every intake folder, plus any folder that produced a run but
    is no longer in the tree (a renamed or deleted folder is a fault too, and
    dropping it would repeat the hole this query exists to close)."""
    by_folder: dict = {}
    by_entity: dict = {}
    for r in runs:
        if r.source_folder:
            by_folder.setdefault(r.source_folder, []).append(r)
        if r.entity_id:
            by_entity.setdefault(r.entity_id, []).append(r)
    names = list(dict.fromkeys(list(folders) + sorted(by_folder)))
    out = []
    for name in names:
        st = classify_folder(name, set(artefacts.get(name) or ()),
                             by_folder.get(name, []),
                             (failures or {}).get(name), by_entity)
        if name not in folders:
            st = FolderState(st.folder, st.state,
                             ((st.reason + "; ") if st.reason else "")
                             + "folder is no longer in the intake tree",
                             st.run_id, st.run_seq, st.run_status,
                             st.scored_cells, st.artefacts)
        out.append(st)
    return sorted(out, key=lambda s: (STATES.index(s.state), s.folder.lower()))


# ---------------------------------------------------------------- DB reads

def fetch_runs(conn) -> list[RunRow]:
    cur = conn.cursor()
    cur.execute(
        """SELECT r.id, r.source_folder_id, r.entity_id, r.run_seq, r.status::text,
                  COALESCE(r.is_active, FALSE), r.promoted_at, r.ccg_catalog_version,
                  (SELECT count(*) FROM subcap_scores s WHERE s.run_id = r.id),
                  r.completed_at
             FROM runs r""")
    return [RunRow(str(a), b, str(c) if c else None, d, e, bool(f), g, h, int(i or 0), j)
            for a, b, c, d, e, f, g, h, i, j in cur.fetchall()]


def fetch_package_failures(conn) -> dict:
    """Ingest failures recorded per package, newest first, keyed by folder.

    Counts only the attempts made against the artefact's CURRENT checksum:
    a re-uploaded workbook is a new package and starts its retry budget
    over, so a parser fix plus a fresh upload clears a quarantine without
    anybody editing the ledger.
    """
    cur = conn.cursor()
    cur.execute(
        """SELECT o.detail, o.occurred_at, f.checksum
             FROM parser_observations o
             LEFT JOIN import_files f ON f.artefact_id = o.artefact_id
            WHERE o.kind = %s
            ORDER BY o.occurred_at""", (PACKAGE_FAILURE_KIND,))
    out: dict = {}
    for detail, occurred_at, live_checksum in cur.fetchall():
        d = json.loads(detail) if isinstance(detail, (str, bytes)) else (detail or {})
        folder = d.get("folder")
        if not folder:
            continue
        # '' is the requeue marker, not a real checksum: an attempt recorded
        # against it belongs to the package as it stands.
        if live_checksum and d.get("checksum") and live_checksum != d["checksum"]:
            out.pop(folder, None)
            continue
        cur_rec = out.setdefault(folder, {"attempts": 0, "error": None,
                                          "quarantined": False, "last_at": None})
        cur_rec["attempts"] += 1
        cur_rec["error"] = d.get("error")
        cur_rec["quarantined"] = bool(d.get("quarantined")) or cur_rec["quarantined"]
        cur_rec["last_at"] = occurred_at
    return out


def intake_status(conn, folders, artefacts: dict) -> list[FolderState]:
    """The whole answer: tree folders + ingested tier + failure ledger."""
    return folder_states(folders, artefacts, fetch_runs(conn),
                         fetch_package_failures(conn))


# ------------------------------------------------------------------ render

def summary(states: list[FolderState]) -> dict:
    counts = {s: 0 for s in STATES}
    for st in states:
        counts[st.state] = counts.get(st.state, 0) + 1
    return counts


def render(states: list[FolderState], show_all: bool = True) -> str:
    """A flat table plus the counts. Deliberately plain text: this is read
    off a Cloud Run Job log and out of a preflight, not off a dashboard."""
    lines = ["intake status — %d folder(s)" % len(states), ""]
    counts = summary(states)
    for s in STATES:
        lines.append("  %-24s %4d" % (s, counts.get(s, 0)))
    blocked = [st for st in states if st.blocked]
    lines += ["", "  %-24s %4d" % ("blocked (named reason)", len(blocked)),
              "  %-24s %4d" % ("queued (no blocker)",
                               sum(1 for st in states
                                   if st.state == PARSED_UNSYNTHESISED and not st.reason)),
              ""]
    for st in states:
        if not show_all and not st.blocked:
            continue
        lines.append("%-22s %-42s %s" % (st.state, st.folder[:42],
                                         st.reason or ""))
    return "\n".join(lines).rstrip() + "\n"


def as_json(states: list[FolderState]) -> str:
    return json.dumps({
        "counts": summary(states),
        "folders": [{"folder": s.folder, "state": s.state, "reason": s.reason,
                     "run_id": s.run_id, "run_seq": s.run_seq,
                     "run_status": s.run_status, "scored_cells": s.scored_cells,
                     "artefacts": list(s.artefacts)} for s in states],
    }, indent=2, default=str)
