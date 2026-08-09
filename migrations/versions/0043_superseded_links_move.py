"""A superseded evidence row that still links is one document voting twice

0028 carried the superseded row's links ONTO the re-mint and left the
originals in place — deliberately cautious at the time, and measurably
wrong since: on the reference client, `E-BCU-012` and its `-R2` twin each
reach 191 subcaps, so every one of those cells counts one document as two
items toward the `<3` thin-evidence line. The excerpt-repair pass that
mints `-R2` rows therefore INFLATES the very counter the thin flag reads,
and the more a package is repaired the less thin its cells look.

`carry_links_across_remint` now moves rather than copies (the code change
lands with this revision). This migration is the same move applied to the
pairs that already exist: for every (base, base-R<n>) pair under one
entity, a base-row link whose (subcap_id, run_id) the re-mint also carries
is deleted. A link ONLY the base row has — which the carry should have
made impossible, but data is data — is kept, on the rule that this
migration removes duplicates and never removes information.

The base rows themselves are retained untouched: an old payload's citation
of the old id still resolves in the drawer. What ends is only the double
vote in the link counts.

Idempotent: re-running deletes nothing the first run did not.

Revision ID: 0043
Revises: 0042
Create Date: 2026-08-09
"""
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

# 0028's own pair derivation, verbatim: the id shape persist.py mints — the
# qualified id, then -R<run_seq> — and a pair is a supersession only when
# both rows exist under the same entity.
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

    before = conn.exec_driver_sql(f"""
        SELECT count(*)
          FROM ({_PAIRS}) p
          JOIN evidence_subcap_links k ON k.e_id = p.base_id
         WHERE EXISTS (SELECT 1 FROM evidence_subcap_links m
                        WHERE m.e_id = p.copy_id
                          AND m.subcap_id = k.subcap_id
                          AND m.run_id = k.run_id)
    """).fetchone()[0]
    print(f"VERIFY 0043 duplicated links (base row + re-mint both linking "
          f"the same cell in the same run): {before}", flush=True)

    removed = conn.exec_driver_sql(f"""
        DELETE FROM evidence_subcap_links k
         USING ({_PAIRS}) p
         WHERE k.e_id = p.base_id
           AND EXISTS (SELECT 1 FROM evidence_subcap_links m
                        WHERE m.e_id = p.copy_id
                          AND m.subcap_id = k.subcap_id
                          AND m.run_id = k.run_id)
    """).rowcount
    print(f"VERIFY 0043 removed {removed} duplicate base-row links; "
          "base rows retained, re-mints keep the linkage", flush=True)

    # The counter those links fed, recomputed for every run a pair touches —
    # counts are computed, never stored where a source of truth exists, and
    # the stored copy exists precisely so it can be recomputed here.
    fixed = conn.exec_driver_sql(f"""
        UPDATE subcap_scores sc
           SET linked_evidence_count =
                 (SELECT count(*) FROM evidence_subcap_links l
                   WHERE l.run_id = sc.run_id AND l.subcap_id = sc.subcap_id)
         WHERE sc.run_id IN (
                 SELECT DISTINCT l.run_id
                   FROM ({_PAIRS}) p
                   JOIN evidence_subcap_links l ON l.e_id = p.copy_id)
    """).rowcount
    print(f"VERIFY 0043 linked_evidence_count recomputed on {fixed} "
          "subcap_scores rows", flush=True)


def downgrade() -> None:
    # The duplicates are not restorable (which links were deleted is not
    # recorded) and restoring a double count is not a state worth returning
    # to. Downgrade is a recorded no-op.
    print("0043 downgrade: no-op — removed duplicate links are not restored")
