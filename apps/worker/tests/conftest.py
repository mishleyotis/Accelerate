"""A fake DB-API connection that understands the worker's statements.

The scan's honesty is a property of what it WRITES, so testing it needs a
connection that remembers writes — not a mock that swallows them. The
local Postgres these suites prefer is not always up (the DB-backed tests
skip when it is down), and "the scan lied about its status" must never be
a skipped test again. This fake keeps `import_scans`, `import_files` and
`parser_observations` as dicts and answers the handful of statements the
worker actually issues; anything unrecognised raises, so a query that
changes shape fails loudly instead of silently passing.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import pytest


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


class FakeCursor:
    def __init__(self, db: "FakeDB"):
        self.db = db
        self._rows: list = []
        self.rowcount = 0

    # ------------------------------------------------------------------
    def execute(self, sql, params=None):
        s = _norm(sql)
        p = params or ()
        self.db.statements.append(s)
        self._rows = []
        self.rowcount = 0
        if self.db.failed_transaction and not s.startswith("ROLLBACK"):
            raise RuntimeError("current transaction is aborted")

        if s.startswith("SELECT pg_try_advisory_lock"):
            self._rows = [(self.db.lock_available,)]
        elif s.startswith("SELECT artefact_id, checksum FROM import_files"):
            self._rows = [(k, v["checksum"]) for k, v in self.db.import_files.items()]
        elif s.startswith("INSERT INTO import_scans"):
            self.db.scan_seq += 1
            sid = self.db.scan_seq
            self.db.import_scans[sid] = {
                "id": sid, "started_at": p[0], "status": p[1], "error": None,
                "folders_seen": 0, "files_seen": 0, "files_new": 0,
                "files_changed": 0, "runs_created": 0, "finished_at": None}
            self._rows = [(sid,)]
        elif s.startswith("UPDATE import_scans SET folders_seen"):
            row = self.db.import_scans[p[4]]
            row.update(folders_seen=p[0], files_seen=p[1], files_new=p[2],
                       files_changed=p[3])
        elif s.startswith("UPDATE import_scans SET status='succeeded'"):
            # The pre-repair statement, kept so a revert fails the honesty
            # tests with an assertion about status rather than an IndexError.
            row = self.db.import_scans[p[1]]
            row.update(status="succeeded", finished_at=p[0])
            self.db.closes.append("succeeded")
        elif s.startswith("UPDATE import_scans SET status"):
            row = self.db.import_scans[p[4]]
            row.update(status=p[0], error=p[1], runs_created=p[2], finished_at=p[3])
            self.db.closes.append(p[0])
        elif s.startswith("INSERT INTO import_files"):
            self.db.import_files[p[0]] = {
                "artefact_id": p[0], "scan_id": p[1], "name": p[3],
                "checksum": p[5], "classified_kind": p[7], "excluded": p[9],
                "exclusion_rule": p[10]}
        elif s.startswith("UPDATE import_files SET last_seen_at"):
            self.rowcount = 1 if p[1] in self.db.import_files else 0
        elif s.startswith("UPDATE import_files SET checksum = ''"):
            if len(p) == 1 and p[0] in self.db.import_files:
                self.db.import_files[p[0]]["checksum"] = ""
                self.rowcount = 1
        elif s.startswith("SELECT detail FROM parser_observations"):
            self._rows = [(json.dumps(o["detail"]),) for o in self.db.observations
                          if o["artefact_id"] == p[0] and o["kind"] == p[1]]
        elif s.startswith("INSERT INTO parser_observations"):
            self.db.observations.append(
                {"artefact_id": p[0], "kind": p[1],
                 "detail": json.loads(p[2]) if isinstance(p[2], str) else p[2],
                 "occurred_at": datetime.now(timezone.utc)})
        elif s.startswith("SELECT o.detail, o.occurred_at, f.checksum"):
            self._rows = [
                (json.dumps(o["detail"]), o["occurred_at"],
                 (self.db.import_files.get(o["artefact_id"]) or {}).get("checksum"))
                for o in self.db.observations if o["kind"] == p[0]]
        elif s.startswith("SELECT r.id, r.source_folder_id"):
            self._rows = [
                (r["id"], r.get("source_folder_id"), r.get("entity_id"),
                 r.get("run_seq"), r.get("status"), bool(r.get("is_active")),
                 r.get("promoted_at"), r.get("ccg_catalog_version"),
                 r.get("scored_cells", 0), r.get("completed_at"))
                for r in self.db.runs]
        else:                                       # pragma: no cover
            raise AssertionError(f"FakeCursor does not know: {s[:90]}")

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class FakeDB:
    """Connection + the tables the worker touches."""

    def __init__(self, import_files=None, runs=None, lock_available=True):
        self.import_files = dict(import_files or {})
        self.import_scans: dict = {}
        self.observations: list = []
        self.runs = list(runs or [])
        self.scan_seq = 0
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.statements: list = []
        self.closes: list = []          # every status written to a scan row
        self.lock_available = lock_available
        self.failed_transaction = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1
        self.failed_transaction = False

    def close(self):
        self.closed = True

    # ---------------------------------------------------------- helpers
    @property
    def scan(self) -> dict:
        """The one (or latest) scan row."""
        assert self.import_scans, "no scan row was ever opened"
        return self.import_scans[max(self.import_scans)]

    def files(self, *stats):
        for f in stats:
            self.import_files[f.file_id] = {
                "artefact_id": f.file_id, "name": f.name,
                "checksum": f.checksum, "classified_kind": None,
                "excluded": False, "exclusion_rule": None}
        return self


@pytest.fixture()
def fakedb():
    return FakeDB()
