"""Which run a scheduler hands a producer, and which it must not.

The package scan fills a queue every thirty minutes and nothing drains it:
measured 2026-08-16, 286 runs at INGESTED across 171 entities, none
synthesised. A loop that walks that queue naively does the wrong thing twice
over — 105 of the 171 entities carry MORE THAN ONE pending run, because an
ingest guard keyed on the Drive file id could not tell a re-uploaded workbook
from a new assessment. One entity holds three runs whose request id, composite,
cell count and completed_at are all identical.

Synthesising those is not extra coverage. It spends three producers to make
three copies of one page set and leaves the directory choosing between them.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "synthesis_queue", ROOT / "scripts" / "synthesis_queue.py")
sq = importlib.util.module_from_spec(_spec)
sys.modules["synthesis_queue"] = sq
_spec.loader.exec_module(sq)


def _run(rid, ent, when=None, seq=None, live=None):
    r = {"run_id": rid, "display_id": ent, "completed_at": when,
         "request_id": f"REQ-{ent}", "status": "INGESTED"}
    if seq is not None:
        r["run_seq"] = seq
    if live is not None:
        r["claim"] = {"held_by": "someone", "live": live}
    return r


def test_one_run_per_entity_and_the_rest_are_named_superseded():
    pending = [_run("a", "x", "2026-08-01", 1), _run("b", "x", "2026-08-01", 2),
               _run("c", "x", "2026-08-01", 3), _run("d", "y", "2026-08-02", 1)]
    out = sq.select(pending)
    assert out["counts"]["ready"] == 2
    assert out["counts"]["superseded"] == 2
    assert {s["why"] for s in out["skipped"]} == {sq.SKIP_SUPERSEDED}
    assert [s["run_id"] for s in out["selected"]] == ["d", "c"]


def test_the_highest_run_seq_wins_for_identical_duplicates():
    """The production shape: every field identical except run_seq. Without it
    the choice falls to the run id, which is stable and arbitrary."""
    pending = [_run("aaa", "x", "2026-08-03", 1), _run("zzz", "x", "2026-08-03", 2)]
    out = sq.select(pending)
    assert [s["run_id"] for s in out["selected"]] == ["zzz"], (
        "run_seq 2 is the later ingest and the one to work")


def test_run_seq_beats_the_run_id_even_when_the_id_sorts_the_other_way():
    """Guards the tiebreak order: if run_seq were consulted after the id, this
    would pick 'zzz' and quietly prefer an older ingest."""
    pending = [_run("zzz", "x", "2026-08-03", 1), _run("aaa", "x", "2026-08-03", 5)]
    assert [s["run_id"] for s in sq.select(pending)["selected"]] == ["aaa"]


def test_a_live_claim_is_skipped_and_says_so():
    """Handing out a claimed run means two producers writing the same six
    pages."""
    out = sq.select([_run("a", "x", "2026-08-01", 1, live=True),
                     _run("b", "y", "2026-08-01", 1, live=False)])
    assert [s["run_id"] for s in out["selected"]] == ["b"]
    assert [s["why"] for s in out["skipped"]] == [sq.SKIP_CLAIMED]


def test_a_claim_holds_the_whole_entity_not_just_the_claimed_run():
    """The defect this test was written for, measured on 2026-08-21.

    `t-rowe-price-group-inc` had seq 4 under a live claim and seq 3 — an older
    ingest of a different request — sitting unclaimed. `select` partitioned
    claimed from unclaimed BEFORE deduping, so seq 4 never entered the pool,
    seq 3 won `best`, and the entity was handed out while a producer was
    already working it.

    `test_a_live_claim_is_skipped_and_says_so` cannot see this: it uses two
    DIFFERENT entities with one run each, so the dedup step has nothing to do
    and the ordering bug is invisible. 105 of 171 entities carry more than one
    pending run, so this shape is the common one.
    """
    out = sq.select([_run("seq4", "x", "2026-08-10", 4, live=True),
                     _run("seq3", "x", "2026-08-03", 3)])
    assert out["selected"] == [], (
        "the entity is held; its older run is not a free substitute")
    assert {s["why"] for s in out["skipped"]} == {sq.SKIP_CLAIMED}
    assert out["counts"]["held_entities"] == 1
    assert out["counts"]["claimed"] == 2, (
        "both runs are held back, and the count must say so")


def test_a_claim_on_an_older_run_still_holds_the_entity():
    """The mirror case. Offering the newer run while a producer works the
    older one puts two producers on one entity's six pages; both promote, and
    the directory is left choosing. The claim is a fact about the entity."""
    out = sq.select([_run("seq4", "x", "2026-08-10", 4),
                     _run("seq3", "x", "2026-08-03", 3, live=True)])
    assert out["selected"] == []
    assert {s["why"] for s in out["skipped"]} == {sq.SKIP_CLAIMED}


def test_a_held_entity_does_not_hold_any_other_entity():
    """The guard must be per-entity, not global — one live claim anywhere
    would otherwise empty the whole queue."""
    out = sq.select([_run("a", "x", "2026-08-10", 2, live=True),
                     _run("b", "x", "2026-08-03", 1),
                     _run("c", "y", "2026-08-05", 1),
                     _run("d", "y", "2026-08-06", 2)])
    assert [s["run_id"] for s in out["selected"]] == ["d"]
    assert out["counts"]["claimed"] == 2 and out["counts"]["superseded"] == 1


def test_a_lapsed_claim_is_not_a_claim():
    """`live: false` means the lease expired; staged work survives and the run
    is workable again."""
    out = sq.select([_run("a", "x", "2026-08-01", 1, live=False)])
    assert [s["run_id"] for s in out["selected"]] == ["a"]


def test_newest_assessment_first():
    """The queue is long enough that the order decides what gets done."""
    pending = [_run("old", "a", "2026-03-01", 1), _run("new", "b", "2026-08-13", 1),
               _run("mid", "c", "2026-06-01", 1)]
    assert [s["run_id"] for s in sq.select(pending)["selected"]] == \
        ["new", "mid", "old"]


def test_undated_runs_sort_last_but_are_never_dropped():
    """54 of the ready runs carry no assessment date. Ordering them against
    the dated ones would guess; dropping them would lose the work."""
    pending = [_run("u", "a", None, 1), _run("d", "b", "2026-01-01", 1)]
    out = sq.select(pending)
    assert [s["run_id"] for s in out["selected"]] == ["d", "u"]
    assert out["counts"]["undated"] == 1


def test_the_limit_truncates_the_plan_and_not_the_census():
    """A scheduler taking three per firing must still SEE the whole queue, or
    the backlog is invisible to whoever reads the log."""
    pending = [_run(f"r{i}", f"e{i}", f"2026-08-{i+1:02d}", 1) for i in range(9)]
    out = sq.select(pending, limit=3)
    assert out["counts"]["selected"] == 3 and out["counts"]["ready"] == 9


def test_the_selection_is_stable_across_calls():
    """A scheduler that picks differently each firing cannot be reasoned about
    or resumed."""
    pending = [_run("a", "x", "2026-08-03"), _run("b", "x", "2026-08-03"),
               _run("c", "y", None)]
    first = sq.select(pending)["selected"]
    assert first == sq.select(list(reversed(pending)))["selected"]


def test_an_empty_queue_is_not_an_error():
    out = sq.select([])
    assert out["counts"]["selected"] == 0 and out["selected"] == []


# ── AUD-0072 · a second request is deferred, not absorbed in silence ─────

def test_a_different_request_for_the_same_entity_is_named():
    """The dedupe grain stays the ENTITY — two producers on one entity's six
    pages both promote and the directory picks between them, which is the
    harm this function exists to prevent. What was missing is the
    distinction: an obsolete re-ingest has nobody waiting on it, and a
    second REQUEST has a requester who was never told."""
    from synthesis_queue import SKIP_ABSORBED, select
    pending = [
        {"run_id": "r1", "display_id": "acme", "request_id": "REQ-1",
         "completed_at": "2026-08-01"},
        {"run_id": "r2", "display_id": "acme", "request_id": "REQ-1",
         "completed_at": "2026-07-01"},
        {"run_id": "r3", "display_id": "acme", "request_id": "REQ-2",
         "completed_at": "2026-06-01"},
    ]
    out = select(pending)
    assert out["counts"]["selected"] == 1
    assert out["counts"]["superseded"] == 1     # r2: same request, older run
    assert out["counts"]["absorbed_requests"] == 1  # r3: a different asker
    absorbed = [s for s in out["skipped"] if s["why"] == SKIP_ABSORBED]
    assert [s["run_id"] for s in absorbed] == ["r3"]
    assert absorbed[0]["absorbed_into"] == "r1"
    assert absorbed[0]["absorbed_into_request"] == "REQ-1"


def test_runs_of_one_request_are_still_plain_supersession():
    from synthesis_queue import select
    pending = [
        {"run_id": "r1", "display_id": "acme", "request_id": "REQ-1",
         "completed_at": "2026-08-01"},
        {"run_id": "r2", "display_id": "acme", "request_id": "REQ-1",
         "completed_at": "2026-07-01"},
    ]
    out = select(pending)
    assert out["counts"]["absorbed_requests"] == 0
    assert out["counts"]["superseded"] == 1
