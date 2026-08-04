"""The scan pass: tree source → diff → classification/exclusion →
import_scans + import_files rows (stage 1.1, TRD §07 steps 1–3).

The tree source is abstract so the same runner is exercised against
fixture trees in tests and the Drive client in production. Only NEW or
CHANGED files proceed to classification and (later stages) parsing;
every file — including excluded and unrecognised ones — is recorded.
Downstream steps (entity resolution → parse → runs) consume the
new/changed set; on an unchanged tree that set is empty and the scan
creates nothing (runs_created = 0).
"""
from __future__ import annotations

from .classification import classify, detect_test_case
from .scan_diff import FileStat, diff_tree


def run_scan(conn, tree: list[FileStat], scan_started_at) -> dict:
    """Execute one scan pass against an open DB connection (svc_worker).
    Returns the summary counters written to import_scans."""
    cur = conn.cursor()
    cur.execute("SELECT artefact_id, checksum FROM import_files")
    prior = {r[0]: r[1] for r in cur.fetchall()}

    d = diff_tree(tree, prior)
    folders = {f.path_segments[:-1] for f in tree}

    cur.execute(
        "INSERT INTO import_scans (started_at, status, folders_seen, files_seen, files_new, files_changed, runs_created) "
        "VALUES (%s, 'running', %s, %s, %s, %s, 0) RETURNING id",
        (scan_started_at, len(folders), len(tree), len(d.new), len(d.changed)),
    )
    scan_id = cur.fetchone()[0]

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
    cur.execute("UPDATE import_scans SET status='succeeded', finished_at=%s WHERE id=%s",
                (scan_started_at, scan_id))
    conn.commit()
    return summary
