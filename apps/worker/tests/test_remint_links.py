"""A re-minted evidence row must inherit the links of the row it supersedes.

The measured case: a second ingest of one client's package re-landed 36 rows
under `-R2` ids because their content had changed — a fuller excerpt, a
published date, an ERS the first scan had none of. `_land_evidence` minted the
new id and carried nothing across, so:

  · all 36 copies were linkless under the PROMOTED run, and
  · 30 of them were cited by that run's pages.

Thirty citations, on four surfaces, each opening a drawer that could not name a
single cell the source supports — while the links sat on an id no surface reads.

These tests drive `carry_links_across_remint` with a cursor that records what it
was asked to do, so the guarantees are asserted rather than read: the links move
with their own run_id, they never overwrite one the copy already has, the basis
says where they came from, and NOTHING about the content follows them.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_worker.persist import CARRIED_BASIS, carry_links_across_remint

# Columns that hold what the scan READ. A re-mint exists precisely because
# these changed, so a carry-forward that touched one would be overwriting a
# fresh reading with a stale one.
CONTENT_COLUMNS = ("excerpt", "source_url", "source_name", "tier",
                   "claim_type", "published_date", "reference_date", "ers",
                   "origin", "content_hash")


class _Cur:
    """Records statements and their parameters; reports a row count."""

    def __init__(self, rowcount=0):
        self.calls = []
        self.rowcount = rowcount

    def execute(self, sql, params=None):
        self.calls.append((re.sub(r"\s+", " ", sql).strip(), tuple(params or ())))


def test_links_are_carried_onto_the_reminted_row():
    cur = _Cur(rowcount=7)
    assert carry_links_across_remint(cur, "E-BCU-006", "E-BCU-006-R2") == 7
    insert = cur.calls[0][0]
    assert insert.startswith("INSERT INTO evidence_subcap_links")
    assert cur.calls[0][1] == ("E-BCU-006-R2", "E-BCU-006")
    # the copy is the target, the superseded row is the source
    assert "WHERE k.e_id = %s" in insert


def test_the_carried_link_keeps_the_run_it_was_made_under():
    """Links are run-scoped. Rewriting them onto THIS run would silently
    reassign an earlier assessment's reasoning; carrying `k.run_id` through is
    what makes the promoted run's citation of the new id resolve."""
    cur = _Cur()
    carry_links_across_remint(cur, "E-X-001", "E-X-001-R2")
    insert = cur.calls[0][0]
    assert "k.run_id" in insert, "the link must keep its own run"
    assert "k.subcap_id" in insert


def test_a_carried_link_never_overwrites_one_the_copy_already_has():
    cur = _Cur()
    carry_links_across_remint(cur, "E-X-001", "E-X-001-R2")
    assert "ON CONFLICT DO NOTHING" in cur.calls[0][0]


def test_the_basis_says_the_link_was_carried_not_stated():
    """'package' would claim this scan's package asserted the link. It did
    not — an earlier read of the same source did, and a reader drilling into
    the drawer is owed that difference."""
    cur = _Cur()
    carry_links_across_remint(cur, "E-X-001", "E-X-001-R2")
    assert f"'{CARRIED_BASIS}'" in cur.calls[0][0]
    assert "'package'" not in cur.calls[0][0]


def test_the_carry_is_a_move_not_a_copy():
    """The first version copied the links and left the superseded row's in
    place, so one document read twice reached every one of its subcaps
    twice: E-BCU-012 and its -R2 twin each reached 191 subcaps, and each
    of those cells counted the same source as TWO items toward the <3
    thin-evidence line. The second statement is the move's second half —
    and it deletes only links the mint verifiably holds, so a link that
    failed to carry is never lost."""
    cur = _Cur()
    carry_links_across_remint(cur, "E-X-001", "E-X-001-R2")
    delete = cur.calls[1][0]
    assert delete.startswith("DELETE FROM evidence_subcap_links")
    assert "EXISTS" in delete and "m.subcap_id = k.subcap_id" in delete \
        and "m.run_id = k.run_id" in delete
    assert cur.calls[1][1] == ("E-X-001", "E-X-001-R2"), \
        "delete from the SUPERSEDED row, guarded by the MINT's links"


def test_no_content_follows_the_links():
    """The copy exists BECAUSE the content changed. Only metadata this ingest
    cannot re-derive moves, and only into NULLs."""
    cur = _Cur()
    carry_links_across_remint(cur, "E-X-001", "E-X-001-R2")
    update = cur.calls[2][0]
    assert update.startswith("UPDATE evidence_index")
    for column in CONTENT_COLUMNS:
        assert column not in update, f"{column} is a fresh reading, not metadata"
    for column in ("specificity", "corroboration", "identity_ok", "identity_note"):
        assert f"{column} = COALESCE(fresh.{column}, prior.{column})" in update
    # and only within one entity — an id that merely LOOKS like a re-mint of
    # another institution's row is not one
    assert "fresh.entity_id = prior.entity_id" in update


def test_the_pair_is_matched_by_id_only():
    cur = _Cur()
    carry_links_across_remint(cur, "E-X-001", "E-X-001-R2")
    assert cur.calls[2][1] == ("E-X-001-R2", "E-X-001")


def test_a_row_that_supersedes_nothing_carries_nothing():
    """rowcount 0 is the honest answer, not None and not a guess."""
    cur = _Cur(rowcount=-1)          # DB-API's "not applicable"
    assert carry_links_across_remint(cur, "E-X-009", "E-X-009-R2") == 0
