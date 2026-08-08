"""0028 — the links a re-minted evidence row never inherited.

`persist.py::_land_evidence` mints a run-qualified id (`E-BCU-006-R2`) when a
second scan of the same package re-lands a local id whose CONTENT changed — a
fuller excerpt, a published date, an ERS the first scan had none of. The copy
is the better row and it is the one the surfaces cite. It arrived carrying no
cell links from the row it supersedes, so:

  · a citation of the new id opened a drawer that could not say which cells
    the source supports, and
  · the earlier run's own linkage sat on an id nobody reads any more.

Measured on the production corpus before this ran: for `baxter-credit-union-bcu`
all 36 `-R2` rows were linked under the run that minted them and under NO other,
while the PROMOTED run cited 30 of them — 30 citations resolving to a row with
no cells behind it, on four pages.

The worker no longer does this (the same carry-forward now runs at ingest, after
the scan has written its own links so a stated basis is never overwritten). This
revision is the one-time repair of rows that landed before that fix, and it is
deliberately narrow:

  · A pair is only a supersession when the copy's id is exactly the base id
    plus `-R<digits>`, BOTH rows exist, and both belong to the SAME entity.
    Nothing is matched by content, by domain or by resemblance.
  · Only links are copied, with `link_basis = 'carried_from_superseded'` — the
    basis says where the assertion came from, so a reader is never told a
    package stated something it did not. A link the copy already has wins
    (ON CONFLICT DO NOTHING).
  · Grading (specificity, corroboration, identity_ok, identity_note) is filled
    only where the copy has NULL. A value the re-scan measured is never
    overwritten.
  · No excerpt, url, tier, claim, date or ERS is touched. The content of an
    evidence row is what the scan read; this revision copies nothing anyone
    could mistake for a fresh reading.

Re-running is a no-op: every write is ON CONFLICT DO NOTHING or COALESCE over a
value that is now non-NULL. The VERIFY lines are the production proof.
"""
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

# The id shape persist.py mints: the qualified id, then -R<run_seq>. A pair is
# a supersession only when both rows exist under the same entity.
_PAIRS = """
  SELECT copy.e_id AS copy_id, base.e_id AS base_id
    FROM evidence_index copy
    JOIN evidence_index base
      ON base.e_id = regexp_replace(copy.e_id, '-R[0-9]+$', '')
     AND base.entity_id IS NOT DISTINCT FROM copy.entity_id
   WHERE copy.e_id ~ '-R[0-9]+$'
"""


def upgrade() -> None:
    conn = op.get_bind()

    pairs = conn.exec_driver_sql(f"SELECT count(*) FROM ({_PAIRS}) p").fetchone()[0]
    before = conn.exec_driver_sql(f"""
        SELECT count(*) FILTER (WHERE NOT EXISTS (
                 SELECT 1 FROM evidence_subcap_links k WHERE k.e_id = p.copy_id)),
               count(*)
          FROM ({_PAIRS}) p
    """).fetchone()
    print(f"VERIFY 0028 before: re-mint pairs={pairs} "
          f"copies with no link at all={before[0]} of {before[1]}", flush=True)

    carried = conn.exec_driver_sql(f"""
        INSERT INTO evidence_subcap_links (e_id, subcap_id, run_id, link_basis)
        SELECT p.copy_id, k.subcap_id, k.run_id, 'carried_from_superseded'
          FROM ({_PAIRS}) p
          JOIN evidence_subcap_links k ON k.e_id = p.base_id
        ON CONFLICT DO NOTHING
        RETURNING e_id
    """).fetchall()
    print(f"VERIFY 0028 links carried onto re-minted rows: {len(carried)} "
          f"across {len({r[0] for r in carried})} ids", flush=True)

    graded = conn.exec_driver_sql(f"""
        UPDATE evidence_index fresh
           SET specificity   = COALESCE(fresh.specificity, prior.specificity),
               corroboration = COALESCE(fresh.corroboration, prior.corroboration),
               identity_ok   = COALESCE(fresh.identity_ok, prior.identity_ok),
               identity_note = COALESCE(fresh.identity_note, prior.identity_note)
          FROM ({_PAIRS}) p
          JOIN evidence_index prior ON prior.e_id = p.base_id
         WHERE fresh.e_id = p.copy_id
           AND (fresh.specificity IS NULL OR fresh.corroboration IS NULL
                OR fresh.identity_ok IS NULL OR fresh.identity_note IS NULL)
           AND (prior.specificity IS NOT NULL OR prior.corroboration IS NOT NULL
                OR prior.identity_ok IS NOT NULL OR prior.identity_note IS NOT NULL)
        RETURNING fresh.e_id
    """).fetchall()
    print(f"VERIFY 0028 grading filled from the superseded row: {len(graded)}",
          flush=True)

    # The linked count on subcap_scores is the linker's own arithmetic and is
    # now stale for any cell that gained a carried link. Recomputed for the
    # affected runs only — counts are computed, never stored twice.
    recounted = conn.exec_driver_sql("""
        UPDATE subcap_scores sc
           SET linked_evidence_count =
                 (SELECT count(*) FROM evidence_subcap_links l
                   WHERE l.run_id = sc.run_id AND l.subcap_id = sc.subcap_id)
         WHERE sc.run_id IN (SELECT DISTINCT run_id FROM evidence_subcap_links
                              WHERE link_basis = 'carried_from_superseded')
        RETURNING sc.subcap_id
    """).fetchall()
    print(f"VERIFY 0028 subcap rows recounted: {len(recounted)}", flush=True)

    after = conn.exec_driver_sql(f"""
        SELECT count(*) FILTER (WHERE NOT EXISTS (
                 SELECT 1 FROM evidence_subcap_links k WHERE k.e_id = p.copy_id)),
               count(*)
          FROM ({_PAIRS}) p
    """).fetchone()
    print(f"VERIFY 0028 after: copies with no link at all={after[0]} of {after[1]}",
          flush=True)


def downgrade() -> None:
    # Only the rows this revision wrote — the basis names them.
    op.execute("DELETE FROM evidence_subcap_links "
               "WHERE link_basis = 'carried_from_superseded'")
