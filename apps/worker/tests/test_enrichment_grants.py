"""Every table the enrichment routine reads is granted to the role it runs as.

The charter's rule is "grants in the same revision as the table". 0047 followed
it: it created `enrichment_jobs` and `enrichment_attempts` and granted
svc_worker on both. Then the job died in production with

    permission denied for table submissions

after scanning 287 runs and reporting "0 gap(s)" — a healthy-looking summary
line from a routine that could not read the payloads the gaps are computed
from.

The rule does not cover this case. No table was created, so no revision was
obviously owed a grant; what changed was that an EXISTING table gained a new
CONSUMER. `runs` happened to be granted already and `submissions` happened not
to be, and nothing in the tree could tell the difference until a container
exited 1.

So the assertion is made from the code rather than from a list: every table
name the routine's SQL mentions must appear in a GRANT to svc_worker somewhere
in migrations/. Adding a read to enrichment.py without adding its grant fails
here rather than in production.
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
ROUTINE = REPO / "apps" / "worker" / "dma_worker" / "enrichment.py"
MIGRATIONS = REPO / "migrations" / "versions"

# Not tables: enum_label() and friends read like FROM targets to a regex.
NOT_TABLES = {"dual", "unnest", "generate_series", "jsonb_array_elements"}


def tables_read() -> set:
    """Table names appearing after FROM or JOIN in the routine's SQL."""
    src = ROUTINE.read_text()
    found = set()
    for m in re.finditer(r"\b(?:FROM|JOIN)\s+([a-z_][a-z0-9_]*)", src):
        name = m.group(1)
        if name not in NOT_TABLES:
            found.add(name)
    return found


def tables_written() -> set:
    src = ROUTINE.read_text()
    return {m.group(1) for m in
            re.finditer(r"\b(?:INSERT\s+INTO|UPDATE)\s+([a-z_][a-z0-9_]*)", src)}


def granted(privilege: str) -> set:
    """Tables granted `privilege` to svc_worker anywhere in migrations/."""
    out = set()
    want = privilege.upper()
    for f in MIGRATIONS.glob("*.py"):
        text = f.read_text()
        if "svc_worker" not in text:
            continue
        # `GRANT SELECT ON runs TO svc_worker`, and the 0047 shape where the
        # privilege list is interpolated from a loop variable.
        for m in re.finditer(
                r"GRANT\s+([A-Z, ]+?)\s+ON\s+([a-z_][a-z0-9_]*)\s+TO\s+\{?(\w+)\}?",
                text):
            privs, table, role = m.group(1), m.group(2), m.group(3)
            if role not in ("svc_worker", "role"):
                continue
            if role == "role" and "svc_worker" not in text:
                continue
            if want in privs or "ALL" in privs:
                out.add(table)
        # 0047 interpolates the privilege string: ("svc_worker", "SELECT, ...")
        for m in re.finditer(r"GRANT\s+\{grant\}\s+ON\s+([a-z_][a-z0-9_]*)", text):
            if re.search(r'"svc_worker",\s*"[^"]*' + want, text):
                out.add(m.group(1))
    return out


def test_the_routine_reads_something():
    """A guard on the guard: if the regexes stop matching, the two tests below
    pass over an empty set and report a grant sweep that never happened."""
    reads = tables_read()
    assert "submissions" in reads and "runs" in reads, (
        f"the SQL scan found {sorted(reads)} — enrichment.py's shape changed "
        "and this test is no longer looking at its queries")


@pytest.mark.parametrize("table", sorted(tables_read()))
def test_every_table_the_routine_reads_is_granted(table):
    assert table in granted("SELECT"), (
        f"enrichment.py reads `{table}` and no migration grants SELECT on it "
        "to svc_worker. An existing table with a NEW consumer is owed a grant "
        "that no create-table revision covers — this is how the job scanned "
        "287 runs, reported '0 gap(s)' and exited 1 on `permission denied for "
        "table submissions`.")


@pytest.mark.parametrize("table", sorted(tables_written()))
def test_every_table_the_routine_writes_is_granted(table):
    have = granted("INSERT") & granted("UPDATE")
    assert table in have, (
        f"enrichment.py writes `{table}` without an INSERT+UPDATE grant to "
        "svc_worker.")


def test_the_routine_writes_only_its_own_workflow_tables():
    """Invariant 2 at the grant layer. The routine records that an attempt
    happened; a resolved VALUE still travels the only path content may take —
    registered as evidence and submitted through the connector. A write grant
    on a serving table would be the side door."""
    # refresh_requests joined the sanctioned set on 2026-08-19 with the
    # six-month sweep: it is workflow state, not serving content — 0032
    # built the table with origin='cadence' for exactly this writer, made
    # svc_worker the ONLY role granted INSERT on it, and the API's refresh
    # Job already wrote it as dmai-worker. The rule this test protects is
    # unchanged: no serving-content table gains a worker write.
    assert tables_written() <= {"enrichment_jobs", "enrichment_attempts",
                                "refresh_requests"}, (
        f"the routine writes {sorted(tables_written())}. Anything beyond its "
        "own two workflow tables is content entering outside the connector.")
