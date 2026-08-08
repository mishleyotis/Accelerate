"""The scan pass: tree source → diff → classification/exclusion →
import_scans + import_files rows (stage 1.1, TRD §07 steps 1–3).

The tree source is abstract so the same runner is exercised against
fixture trees in tests and the Drive client in production. Only NEW or
CHANGED files proceed to classification and (later stages) parsing;
every file — including excluded and unrecognised ones — is recorded.
Downstream steps (entity resolution → parse → runs) consume the
new/changed set; on an unchanged tree that set is empty and the scan
creates nothing (runs_created = 0).

**The scan row is not a receipt for the diff — it is a receipt for the
execution.** It opens BEFORE the tree walk (so a walk that dies is still
recorded), stays `running` through ingestion, and is closed exactly once
by `finish_scan` with the outcome the execution actually had. Writing
`succeeded` at the end of the diff — as this module did for 150 firings
— records success for work that had not started yet: every one of those
rows said `succeeded`, `runs_created = 0`, and `finished_at =
started_at`, while the job exited 1 and 130 runs existed.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .classification import classify, detect_test_case
from .scan_diff import FileStat, diff_tree

#: The three values `import_scans.status` may ever hold.
SCAN_RUNNING = "running"
SCAN_SUCCEEDED = "succeeded"
SCAN_FAILED = "failed"


class EmptyTreeError(RuntimeError):
    """The walk returned nothing while the previous scan recorded files.

    An empty listing is indistinguishable from a healthy scan of an empty
    tree by counters alone — both write `files_seen = 0` — so the only
    thing that separates them is what the last scan saw. When the tree is
    known non-empty, zero files means the walk failed (revoked scope,
    throttled listing, a 5xx swallowed mid-recursion) and the scan must
    record a failure with that reason rather than a successful traversal
    of a tree that has apparently vanished.
    """


def open_scan(conn, scan_started_at) -> int:
    """Insert the `running` scan row and commit it, BEFORE the tree walk.

    Committed on its own so the row survives the execution: an exception
    in the walk or in ingestion rolls back its own work, and the scan
    ledger still shows a firing that started. `finish_scan` closes it.
    """
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO import_scans (started_at, status, folders_seen, files_seen, "
        "files_new, files_changed, runs_created) "
        "VALUES (%s, %s, 0, 0, 0, 0, 0) RETURNING id",
        (scan_started_at, SCAN_RUNNING),
    )
    scan_id = cur.fetchone()[0]
    conn.commit()
    return scan_id


def finish_scan(conn, scan_id: int, *, status: str, error: str | None = None,
                runs_created: int = 0, finished_at=None) -> None:
    """Close a scan row exactly once, with the outcome it actually had.

    `succeeded` is legal only when the traversal completed AND nothing in
    the execution failed; every other ending carries `error` naming the
    cause. Rolls back first: the caller reaches here from an exception
    path where the connection may be sitting in a failed transaction, and
    a status write that cannot commit is another silent success.
    """
    if status not in (SCAN_SUCCEEDED, SCAN_FAILED):
        raise ValueError(f"a scan closes as succeeded or failed, not {status!r}")
    if status == SCAN_FAILED and not error:
        raise ValueError("a failed scan records the reason it failed")
    if scan_id is None:
        return
    try:
        conn.rollback()
    except Exception:                       # noqa: BLE001 — best effort
        pass
    cur = conn.cursor()
    cur.execute(
        "UPDATE import_scans SET status = %s, error = %s, runs_created = %s, "
        "finished_at = %s WHERE id = %s",
        (status, (error or None), runs_created,
         finished_at or datetime.now(timezone.utc), scan_id),
    )
    conn.commit()


def run_scan(conn, tree: list[FileStat], scan_started_at, scan_id: int | None = None) -> dict:
    """Execute one scan pass against an open DB connection (svc_worker).

    Records the diff against the open scan row and returns the summary.
    It does NOT close the row: ingestion has not run yet, and the outcome
    of this execution is not known until it has. The caller owns
    `finish_scan`.
    """
    cur = conn.cursor()
    cur.execute("SELECT artefact_id, checksum FROM import_files")
    prior = {r[0]: r[1] for r in cur.fetchall()}

    if scan_id is None:
        scan_id = open_scan(conn, scan_started_at)

    # Fail-closed on an empty walk. Nothing is written for missing files, so
    # raising here leaves import_files untouched and the row `running` for
    # the caller to close as failed with this reason.
    if not tree and prior:
        raise EmptyTreeError(
            f"walked 0 files and 0 folders, but the last scan recorded "
            f"{len(prior)} artefact(s) — the intake tree is known non-empty, "
            f"so this is a failed walk, not an empty tree")

    d = diff_tree(tree, prior)
    folders = {f.path_segments[:-1] for f in tree}

    cur.execute(
        "UPDATE import_scans SET folders_seen = %s, files_seen = %s, "
        "files_new = %s, files_changed = %s WHERE id = %s",
        (len(folders), len(tree), len(d.new), len(d.changed), scan_id),
    )

    for f in d.new + d.changed:
        rule = detect_test_case(list(f.path_segments))
        c = classify(f.name)
        cur.execute(
            """INSERT INTO import_files
                 (artefact_id, scan_id, drive_file_id, name, mime_type, checksum,
                  size_bytes, classified_kind, source_priority, excluded,
                  exclusion_rule, first_seen_at, last_seen_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (artefact_id) DO UPDATE SET
                 scan_id = EXCLUDED.scan_id,
                 checksum = EXCLUDED.checksum,
                 classified_kind = EXCLUDED.classified_kind,
                 source_priority = EXCLUDED.source_priority,
                 excluded = EXCLUDED.excluded,
                 exclusion_rule = EXCLUDED.exclusion_rule,
                 last_seen_at = EXCLUDED.last_seen_at""",
            (f.file_id, scan_id, f.file_id, f.name, f.mime_type, f.checksum,
             f.size_bytes, c.kind if c else None, c.priority if c else None,
             rule is not None, rule, scan_started_at, scan_started_at),
        )
    # Unchanged files: refresh last_seen_at only — the row itself is stable.
    for f in d.unchanged:
        cur.execute("UPDATE import_files SET last_seen_at = %s WHERE artefact_id = %s",
                    (scan_started_at, f.file_id))

    summary = {
        "scan_id": scan_id, "folders_seen": len(folders), "files_seen": len(tree),
        "files_new": len(d.new), "files_changed": len(d.changed),
        "missing": d.missing, "to_process": d.new + d.changed,
    }
    conn.commit()
    return summary
