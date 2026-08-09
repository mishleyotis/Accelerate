"""`resolve_run`'s column list and the view it reads are two copies of one list.

Every API test that resolves a run drives a FAKE cursor returning a
hand-written tuple, and `resolve_run` reads that tuple POSITIONALLY. So a
column added to the SELECT and not to the view — or to the view and not to
the fixtures — is green in twenty unit tests and an IndexError or, worse, a
silent off-by-one in production. Adding `entity_domain` (0045) broke twenty
of those fixtures at once, which was the good outcome; the bad outcome is
the same edit made without a migration, where nothing fails until the
request.

`RULE_HELD_IN_TWO_PLACES_DRIFTS`, in this build's own read path.

Two checks, deliberately of different kinds:

  * statically, against the migration that last rebuilt the view — runs
    everywhere, including CI with no database;
  * against the LIVE local schema — catches a view that exists but was
    never rebuilt, which a file comparison cannot see.

The migration is found by revision number rather than named, so this does
not need editing every time the view is rebuilt.
"""
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api import pages                                    # noqa: E402

MIGRATIONS = ROOT / "migrations" / "versions"


def _select_columns() -> list:
    """The columns resolve_run asks serving_directory for, in order."""
    src = Path(pages.__file__).read_text()
    body = src.split("cur.execute(\"\"\"SELECT ", 1)[1].split("FROM serving_directory", 1)[0]
    body = re.sub(r"--.*", "", body)
    return [c.strip() for c in body.replace("\n", " ").split(",") if c.strip()]


def _view_columns() -> tuple:
    """(revision, aliases) of the latest migration that rebuilds the view."""
    latest, body = None, None
    for path in sorted(MIGRATIONS.glob("*.py")):
        text = path.read_text()
        if "_VIEW_BODY = \"\"\"" not in text or "MATERIALIZED VIEW serving_directory" not in text:
            continue
        rev = path.name.split("_", 1)[0]
        if latest is None or rev > latest:
            latest, body = rev, text.split("_VIEW_BODY = \"\"\"", 1)[1].split('"""', 1)[0]
    assert latest, "no migration defines a serving_directory view body"
    cols = []
    for line in body.split("FROM runs r", 1)[0].split("\n"):
        line = line.strip().rstrip(",")
        if not line or line.upper().startswith("SELECT"):
            line = line[6:].strip() if line.upper().startswith("SELECT") else line
        if not line:
            continue
        m = re.search(r"\bAS\s+([a-z_][a-z0-9_]*)$", line, re.I)
        cols.append(m.group(1) if m else line.split(".")[-1])
    return latest, [c for c in cols if c]


def test_every_column_resolve_run_selects_exists_in_the_view_body():
    revision, view = _view_columns()
    missing = [c for c in _select_columns() if c not in view]
    assert not missing, (
        f"resolve_run selects {missing} and migration {revision}'s "
        "serving_directory does not define them — the read path would 500 on "
        "every page for every client, and no fixture-driven test can see it")


def test_the_positional_read_covers_the_whole_select():
    """`resolve_run` indexes `picked[N]`. The highest index it reads must be
    the last column it asked for: a SELECT longer than the reads means a
    column was added and never consumed, and a read past the end is the
    IndexError this file exists to make impossible to ship."""
    src = Path(pages.__file__).read_text()
    fn = src.split("def resolve_run", 1)[1].split("\ndef ", 1)[0]
    highest = max(int(n) for n in re.findall(r"picked\[(\d+)\]", fn))
    assert highest == len(_select_columns()) - 1, (
        f"resolve_run reads up to picked[{highest}] from a SELECT of "
        f"{len(_select_columns())} columns")


def test_the_live_view_has_the_columns_too():
    """The file check compares two files. This compares the SELECT against a
    view that was actually built — the difference that matters when a
    migration exists and was never applied."""
    import pg8000.dbapi
    dsn = os.environ.get("LOCAL_DATABASE_URL", "")
    host = dsn.split("@")[1].split(":")[0] if "@" in dsn else "localhost"
    try:
        conn = pg8000.dbapi.connect(user="postgres", password="local", host=host,
                                    port=5432, database="dma_insights")
    except Exception:
        pytest.skip("no migrated local database")
    cur = conn.cursor()
    # pg_attribute, NOT information_schema.columns: a MATERIALIZED view has
    # no row there at all, so the obvious query returns empty for a view
    # that exists and this test skipped itself into permanent silence. It
    # was written that way and caught here, which is the whole argument for
    # checking against something built rather than something declared.
    cur.execute("""SELECT a.attname FROM pg_attribute a
                     JOIN pg_class c ON c.oid = a.attrelid
                    WHERE c.relname = 'serving_directory'
                      AND c.relkind = 'm' AND a.attnum > 0
                      AND NOT a.attisdropped""")
    live = {r[0] for r in cur.fetchall()}
    conn.close()
    if not live:
        pytest.skip("serving_directory not built in this database")
    missing = [c for c in _select_columns() if c not in live]
    assert not missing, (
        f"resolve_run selects {missing}; the BUILT serving_directory has "
        "them in no migration that was applied here")
