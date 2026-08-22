"""0023 — three required fields that were validated and then discarded.

All three are the same defect: a REQUIRED contract field with no column, so
whatever a producer sends is checked at submit, promoted into nothing, and gone.
They were found by sweeping every required field against the writer spec rather
than one card at a time, which is now a test (`test_a_required_field_is_either
_stored_or_deliberately_computed`) so the next one surfaces there instead of as
an empty card under a client's name.

  · `techstack.dropped`                 — the taxonomy's rejects (below)
  · `overview.evidence_coverage.mix_implication` — the sentence saying what the
    tier mix MEANS. The histogram beside it is just shape; this is the reading,
    and O11's whole argument ("a ceiling_estimate count of zero usually means
    ceilings were asserted as facts") lives in it.
  · `platform.roadmap.sequencing_basis` — why THIS ordering rather than another.
    The phases were stored and their basis was not, so the roadmap rendered an
    order with no argument for it — and `sequencing_reason` per recommendation
    must agree with a basis the run could not keep.

## The taxonomy's rejects get somewhere to land

`techstack.dropped` is a REQUIRED contract field with no column, so whatever a
producer sends is validated, promoted into nothing, and gone. It is the same
class of defect as `context_sentiment.context_tiles` before 0020 and the
leadership contact route before 0018: a field the contract demands and the
schema cannot hold.

It matters more than its size suggests, because of what the field IS. From the
contract: *"Per dropped candidate: {candidate, reason} — candidates rejected by
the taxonomy, with the reason. dropped[] is reported, not hidden: it is how a
taxonomy gap becomes visible."* A product the scan surfaced and the taxonomy had
no home for is the single best signal that the taxonomy needs a new category —
and discarding it at promotion is precisely how that signal stays invisible
across every client.

## Section-grain on an item-grain table

`techstack_items` is one row per product, and `dropped` belongs to the section.
That is an established shape here rather than a new one: `firmographics` is
item-grain and already carries `sub_vertical_undefined` bound `section:`, which
repeats on every row and is read once. Same pattern, same reader — the serving
projection already reads section columns from the first row.

## Why `layers` deliberately does NOT get a column here

`techstack.layers` is required too, and it is also unstored, and it is being
left that way ON PURPOSE. Every ingredient of the rollup — the layer, the pillar
tag, the status of each row — is already on the item rows, so the detected /
expected counts are COMPUTED at read (`techLayersOf` in the web adapter). Counts
are computed, never stored, where a source of truth exists (invariant 8), and
the register is that source. Adding a column would create a second answer that
could disagree with the rows beneath it, which is the failure this invariant
exists to prevent.

The producer still asserts `layers` at submit and the contract still checks it —
that assertion is what the gate reconciles against — but nothing persists it.
`evidence_coverage.item_count` and `firmographics.undated_pct` work the same
way, and for the same reason.

Nullable, so every already-promoted row stays valid. No GRANT is needed: 0008
grants at table level, which covers columns added afterwards.
"""
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE techstack_items "
               "ADD COLUMN IF NOT EXISTS dropped JSONB")
    op.execute("""
        COMMENT ON COLUMN techstack_items.dropped IS
          'T1 section-grain, repeated per row and read once (same shape as '
          'overview_firmographics.sub_vertical_undefined): [{candidate, '
          'reason}] — products the scan surfaced that the taxonomy had no home '
          'for. Reported, not hidden: it is how a taxonomy gap becomes '
          'visible. Sibling field `layers` is deliberately NOT stored — it is '
          'recomputed from these rows at read (invariant 8).'
    """)

    op.execute("ALTER TABLE overview_evidence_coverage "
               "ADD COLUMN IF NOT EXISTS mix_implication TEXT")
    op.execute("""
        COMMENT ON COLUMN overview_evidence_coverage.mix_implication IS
          'O11 — what the tier and claim mix MEANS for confidence in this '
          'assessment. The histogram beside it is shape; this is the reading. '
          'Required by the contract and previously unstored, so it was '
          'validated at submit and discarded at promotion.'
    """)

    op.execute("ALTER TABLE platform_roadmap "
               "ADD COLUMN IF NOT EXISTS sequencing_basis TEXT")
    op.execute("""
        COMMENT ON COLUMN platform_roadmap.sequencing_basis IS
          'P3 section-grain, repeated per phase row and read once — why THIS '
          'ordering rather than another. The phases were stored and their '
          'basis was not, so the roadmap rendered an order with no argument, '
          'and each recommendation''s sequencing_reason had to agree with '
          'something the run could not keep.'
    """)

    got = op.get_bind().exec_driver_sql("""
        SELECT table_name || '.' || column_name
          FROM information_schema.columns
         WHERE (table_name, column_name) IN
               (('techstack_items', 'dropped'),
                ('overview_evidence_coverage', 'mix_implication'),
                ('platform_roadmap', 'sequencing_basis'))
         ORDER BY 1
    """).fetchall()
    print(f"VERIFY 0023 columns present ({len(got)} of 3): "
          + ", ".join(r[0] for r in got))


def downgrade() -> None:
    op.execute("ALTER TABLE techstack_items DROP COLUMN IF EXISTS dropped")
    op.execute("ALTER TABLE overview_evidence_coverage "
               "DROP COLUMN IF EXISTS mix_implication")
    op.execute("ALTER TABLE platform_roadmap "
               "DROP COLUMN IF EXISTS sequencing_basis")
