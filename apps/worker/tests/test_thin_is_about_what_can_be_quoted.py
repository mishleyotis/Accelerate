"""`is_thin_evidence` after migration 0053, against the real generated column.

The old rule was `linked_evidence_count < 3` — a count of LINKS, blind to
whether any of them could be cited. On run d7ed1d90 that gave the reading a
reader objected to: a cell with eight links and nothing quotable read the same
as a cell with none, while three references nobody can open outranked one
verbatim span of congressional testimony.

Owner instruction, 2026-08-19: "As long as a subcap has 1 specific evidence
that speaks on it, it is not thin, especially if it is above T3 level of
evidence."

These cases run against the migrated local database, because the rule IS the
generated column: asserting a Python copy of it would pass while the column
said something else, which is the shape of defect this repo keeps paying for.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_worker.counts import recount_run  # noqa: E402

DSN = os.environ.get("LOCAL_DATABASE_URL",
                     "postgresql://postgres:local@localhost:5432/dma_insights")
HOST = DSN.split("@")[1].split(":")[0] if "@" in DSN else "localhost"

VER = "v7.0-thintest"
SPAN = ("The board approved a documented digital strategy in 2025 covering "
        "every line of business, with a named owner and a three-year horizon.")


def _connect(user):
    import pg8000.dbapi
    return pg8000.dbapi.connect(user=user, password="local", host=HOST,
                                port=5432, database="dma_insights")


@pytest.fixture()
def db():
    try:
        worker = _connect("dmai-worker@digital-maturity-assessor.iam")
        admin = _connect("dmai-migrate@digital-maturity-assessor.iam")
    except Exception:
        pytest.skip("no migrated local database")

    def clean():
        cur = admin.cursor()
        cur.execute("SELECT id FROM entities WHERE display_id = 'thin-rule-test-cu'")
        for (eid,) in cur.fetchall():
            for sql in (
                "DELETE FROM evidence_subcap_links WHERE run_id IN (SELECT id FROM runs WHERE entity_id = %s)",
                "DELETE FROM subcap_scores WHERE run_id IN (SELECT id FROM runs WHERE entity_id = %s)",
                "DELETE FROM runs WHERE entity_id = %s",
                "DELETE FROM evidence_index WHERE entity_id = %s",
                "DELETE FROM entities WHERE id = %s",
            ):
                cur.execute(sql, (eid,))
        cur.execute("DELETE FROM ccg_subcaps WHERE version = %s", (VER,))
        cur.execute("DELETE FROM ccg_versions WHERE version = %s", (VER,))
        admin.commit()

    clean()
    cur = admin.cursor()
    cur.execute("INSERT INTO ccg_versions (version, cell_count, category_count, "
                "is_current) VALUES (%s, 4, 1, FALSE)", (VER,))
    for sid in ("P1C1.1.1", "P1C1.1.2", "P1C1.1.3", "P1C1.1.4"):
        cur.execute("""INSERT INTO ccg_subcaps
                         (subcap_id, version, capability_id, category_id,
                          pillar_id, name)
                       VALUES (%s,%s,'P1C1.1','P1C1','P1','A cell')""", (sid, VER))
    admin.commit()

    w = worker.cursor()
    w.execute("""INSERT INTO entities (display_id, legal_name, status, created_at)
                 VALUES ('thin-rule-test-cu','Thin Rule Test Credit Union',
                         'ACTIVE', now()) RETURNING id""")
    entity_id = w.fetchone()[0]
    w.execute("""INSERT INTO runs (entity_id, request_id, run_seq,
                                   ccg_catalog_version, status, is_active)
                 VALUES (%s,'DMA-ASM-THIN-20260819-0001',1,%s,'INGESTED',TRUE)
                 RETURNING id""", (entity_id, VER))
    run_id = w.fetchone()[0]
    for sid in ("P1C1.1.1", "P1C1.1.2", "P1C1.1.3", "P1C1.1.4"):
        w.execute("""INSERT INTO subcap_scores
                       (run_id, subcap_id, capability_id, category_id,
                        pillar_id, score)
                     VALUES (%s,%s,'P1C1.1','P1C1','P1',2.0)""", (run_id, sid))
    # One quotable span, and three references with none — the exact shape of
    # the corpus that opened this: package rows carrying the links, producer
    # rows carrying the quotes.
    w.execute("""INSERT INTO evidence_index (e_id, entity_id, origin, excerpt,
                                             tier, reference_date)
                 VALUES ('E-THIN-SPAN',%s,'producer',%s,'T2','2026-08-01')""",
              (entity_id, SPAN))
    for e_id, tier in (("E-THIN-REF1", "T2"), ("E-THIN-REF2", "T3"),
                       ("E-THIN-REF3", "T4")):
        w.execute("""INSERT INTO evidence_index (e_id, entity_id, origin,
                                                 excerpt, tier, reference_date)
                     VALUES (%s,%s,'package',NULL,%s,'2026-08-01')""",
                  (e_id, entity_id, tier))
    worker.commit()
    yield worker, str(run_id)
    worker.rollback()
    clean()
    worker.close()
    admin.close()


def _link(cur, run_id, subcap, *e_ids):
    for e in e_ids:
        cur.execute("""INSERT INTO evidence_subcap_links
                         (e_id, subcap_id, run_id, link_basis)
                       VALUES (%s,%s,%s,'package')""", (e, subcap, run_id))


def _flags(cur, run_id, subcap):
    cur.execute("""SELECT linked_evidence_count, citable_evidence_count,
                          is_thin_evidence
                     FROM subcap_scores WHERE run_id = %s AND subcap_id = %s""",
                (run_id, subcap))
    # pg8000 hands back a list; the shape is what matters, not the container.
    return tuple(cur.fetchone())


def test_one_quotable_span_clears_thin(db):
    """THE INSTRUCTION, as the column now reads it. One citable item, one
    link, and the cell is not thin — where the old rule needed three of
    anything."""
    conn, run_id = db
    cur = conn.cursor()
    _link(cur, run_id, "P1C1.1.1", "E-THIN-SPAN")
    recount_run(cur, run_id)
    conn.commit()
    linked, citable, thin = _flags(cur, run_id, "P1C1.1.1")
    assert (linked, citable, thin) == (1, 1, False)


def test_three_references_nobody_can_quote_are_still_thin(db):
    """The inversion the old rule produced, now refused. Three links, three
    rows with no verbatim span, nothing a reader can open.

    This case failed the FIRST draft of migration 0053, which kept the old
    three-link rule as a fallback: `linked = 3` cleared thin over a cell whose
    every citation was unopenable. Invariant 4 settles it — an item with no
    verbatim excerpt cannot be cited — so the fallback went."""
    conn, run_id = db
    cur = conn.cursor()
    _link(cur, run_id, "P1C1.1.2", "E-THIN-REF1", "E-THIN-REF2", "E-THIN-REF3")
    recount_run(cur, run_id)
    conn.commit()
    linked, citable, thin = _flags(cur, run_id, "P1C1.1.2")
    assert (linked, citable) == (3, 0)
    assert thin is True, \
        "three unquotable references cleared thin, which is the reading that " \
        "put a citation with no quote in front of a reader"


def test_a_cell_with_nothing_at_all_is_thin(db):
    conn, run_id = db
    cur = conn.cursor()
    recount_run(cur, run_id)
    conn.commit()
    linked, citable, thin = _flags(cur, run_id, "P1C1.1.3")
    assert (linked, citable, thin) == (0, 0, True)


def test_the_span_still_counts_beside_references(db):
    """The corpus shape: a package reference and a producer span on one cell."""
    conn, run_id = db
    cur = conn.cursor()
    _link(cur, run_id, "P1C1.1.4", "E-THIN-REF1", "E-THIN-SPAN")
    recount_run(cur, run_id)
    conn.commit()
    linked, citable, thin = _flags(cur, run_id, "P1C1.1.4")
    assert (linked, citable, thin) == (2, 1, False)


def test_an_empty_excerpt_is_not_a_span(db):
    """127 rows landed excerpt-less on one ingest and some of them landed as
    an empty string rather than NULL. A zero-length span is not a quote."""
    conn, run_id = db
    cur = conn.cursor()
    cur.execute("""INSERT INTO evidence_index (e_id, entity_id, origin, excerpt,
                                               tier, reference_date)
                   SELECT 'E-THIN-BLANK', entity_id, 'package', '   ', 'T2',
                          '2026-08-01'
                     FROM evidence_index WHERE e_id = 'E-THIN-SPAN'""")
    _link(cur, run_id, "P1C1.1.3", "E-THIN-BLANK")
    recount_run(cur, run_id)
    conn.commit()
    linked, citable, thin = _flags(cur, run_id, "P1C1.1.3")
    assert (linked, citable, thin) == (1, 0, True)


def test_the_counts_are_recomputed_not_incremented(db):
    """A link removed must lower the count. An incremented counter would keep
    the cell non-thin over evidence that is no longer there."""
    conn, run_id = db
    cur = conn.cursor()
    _link(cur, run_id, "P1C1.1.1", "E-THIN-SPAN")
    recount_run(cur, run_id)
    conn.commit()
    assert _flags(cur, run_id, "P1C1.1.1")[2] is False
    cur.execute("DELETE FROM evidence_subcap_links WHERE run_id = %s "
                "AND subcap_id = 'P1C1.1.1'", (run_id,))
    recount_run(cur, run_id)
    conn.commit()
    assert _flags(cur, run_id, "P1C1.1.1") == (0, 0, True)
