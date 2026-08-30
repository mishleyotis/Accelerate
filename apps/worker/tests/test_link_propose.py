"""W2 QA — the propose-only evidence→subcap matcher.

The pure core is exercised with injected fake encoders (no torch, no DB):
exact-match short-circuits, the floor and margin route to contention, the
reject line routes to a recorded skip, placeholders never match, and the
whole pipeline is deterministic under input shuffling. The DB half runs
against the migrated local database (skips cleanly without one): accepted
links land with their basis, contentions land as parser_observations,
linked_evidence_count refreshes, re-runs are idempotent, and a dry run
writes nothing at all.
"""
import json
import math
import os
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_worker.link_propose import (BASIS_EMBEDDING, BASIS_STATED_ID,
                                     OBS_CONTENTION, OBS_PASS,
                                     PROPOSAL_FLOOR, REVIEW_FLOOR,
                                     RUNNER_UP_MARGIN, Subcap, persist_result,
                                     propose, run_for_run)

DSN = os.environ.get("LOCAL_DATABASE_URL",
                     "postgresql://postgres:local@localhost:5432/dma_insights")
HOST = DSN.split("@")[1].split(":")[0] if "@" in DSN else "localhost"

LONG = " padded so the excerpt clears the minimum usable length."


class TableEncoder:
    """Returns pre-agreed unit vectors; records every batch it encodes."""
    name = "table-encoder"

    def __init__(self, table):
        self.table = table
        self.batches = []

    def encode(self, texts):
        self.batches.append(list(texts))
        return [list(self.table[t]) for t in texts]


class ExplodingEncoder:
    """Must never be called."""
    name = "exploding-encoder"

    def encode(self, texts):  # pragma: no cover - the point is it never runs
        raise AssertionError(f"encoder invoked on {texts!r}")


def _vec(a, b):
    """Unit vector whose cosine against A=[1,0,0] is exactly a and against
    B=[0,1,0] is exactly b (third axis absorbs the rest)."""
    rest = max(0.0, 1.0 - a * a - b * b)   # clamp float dust like -1e-16
    return (a, b, math.sqrt(rest))


SUB_A = Subcap("P1C1.1.1", "Digital strategy alignment",
               "Digital strategy alignment. Strategy Foundation.")
SUB_B = Subcap("P2C1.1.1", "Customer onboarding journeys",
               "Customer onboarding journeys. Client Lifecycle.")
PLACEHOLDER = Subcap("P1C1.1.2", "Capability dimension 3",
                     "Capability dimension 3")


def _table(evidence_pairs):
    t = {SUB_A.text: _vec(1.0, 0.0), SUB_B.text: _vec(0.0, 1.0),
         PLACEHOLDER.text: _vec(0.0, 0.0)}
    t.update(evidence_pairs)
    return t


# ── pure core ───────────────────────────────────────────────────────────
def test_already_linked_short_circuits_and_never_encodes():
    ev = [("E-1", "An excerpt that is long enough to be usable." + LONG)]
    out = propose(ev, [SUB_A, SUB_B], {("E-1", "P1C1.1.1")}, ExplodingEncoder())
    assert out["accepted"] == [] and out["contentions"] == []
    assert out["skipped"] == [{"e_id": "E-1", "reason": "already_linked"}]


def test_stated_id_in_excerpt_is_exact_match_and_not_encoded():
    text = "Their P2C1.1.1 rollout was described in the 2025 annual report."
    ev = [("E-1", text)]
    out = propose(ev, [SUB_A, SUB_B], set(), ExplodingEncoder())
    assert out["accepted"] == [{"e_id": "E-1", "subcap_id": "P2C1.1.1",
                                "score": None, "basis": BASIS_STATED_ID}]
    # an id NOT in the scored set is never linked on the regex alone
    out2 = propose([("E-2", "P3C9.9.9 appears here but is not a scored cell,"
                            " so nothing may attach on it." + LONG)],
                   [SUB_A, SUB_B], set(),
                   TableEncoder(_table({("P3C9.9.9 appears here but is not a "
                                         "scored cell, so nothing may attach "
                                         "on it." + LONG): _vec(0.0, 0.0)})))
    assert out2["accepted"] == []


def test_clear_winner_above_floor_is_accepted_with_score_and_basis():
    text = "Board-approved digital strategy documented across lines." + LONG
    enc = TableEncoder(_table({text: _vec(0.8, 0.1)}))
    out = propose([("E-1", text)], [SUB_A, SUB_B, PLACEHOLDER], set(), enc)
    assert out["accepted"] == [{"e_id": "E-1", "subcap_id": "P1C1.1.1",
                                "score": 0.8, "basis": BASIS_EMBEDDING}]
    assert out["contentions"] == [] and out["skipped"] == []
    assert len(enc.batches) == 1  # one deterministic batch


def test_below_floor_is_contention_with_candidates_and_scores():
    text = "Vague ambitions gesture at strategy without any artefact." + LONG
    enc = TableEncoder(_table({text: _vec(0.55, 0.1)}))
    out = propose([("E-1", text)], [SUB_A, SUB_B], set(), enc)
    assert out["accepted"] == []
    (c,) = out["contentions"]
    assert c["e_id"] == "E-1" and c["reason"] == "below_proposal_floor"
    assert c["candidates"][0] == {"subcap_id": "P1C1.1.1", "score": 0.55}
    assert len(c["candidates"]) == 2
    assert REVIEW_FLOOR <= 0.55 < PROPOSAL_FLOOR  # the branch under test


def test_two_candidates_inside_margin_is_contention():
    text = "Strategy for onboarding is described in equal measure here." + LONG
    enc = TableEncoder(_table({text: _vec(0.70, 0.68)}))
    out = propose([("E-1", text)], [SUB_A, SUB_B], set(), enc)
    assert out["accepted"] == []
    (c,) = out["contentions"]
    assert c["reason"] == "runner_up_within_margin"
    assert [x["subcap_id"] for x in c["candidates"]] == ["P1C1.1.1", "P2C1.1.1"]
    assert 0.70 - 0.68 < RUNNER_UP_MARGIN and 0.70 >= PROPOSAL_FLOOR


def test_below_reject_line_is_skipped_not_contended():
    text = "Cafeteria menus were refreshed quarterly per the newsletter." + LONG
    enc = TableEncoder(_table({text: _vec(0.2, 0.1)}))
    out = propose([("E-1", text)], [SUB_A, SUB_B], set(), enc)
    assert out["contentions"] == []
    (s,) = out["skipped"]
    assert s["reason"] == "no_plausible_candidate"
    assert s["candidates"][0]["score"] == 0.2  # still auditable


def test_short_or_missing_text_is_skipped():
    out = propose([("E-1", None), ("E-2", "too short")],
                  [SUB_A], set(), ExplodingEncoder())
    assert [(s["e_id"], s["reason"]) for s in out["skipped"]] == \
        [("E-1", "no_usable_text"), ("E-2", "no_usable_text")]


def test_placeholder_subcaps_are_excluded_from_the_corpus():
    text = "A perfectly usable excerpt with nothing to match onto." + LONG
    enc = TableEncoder(_table({text: _vec(0.9, 0.0)}))
    out = propose([("E-1", text)], [PLACEHOLDER], set(), enc)
    # corpus is empty -> recorded skip, encoder untouched
    assert out["skipped"] == [{"e_id": "E-1", "reason": "no_matchable_subcaps"}]
    assert enc.batches == []
    assert out["params"]["placeholder_cells_excluded"] == 1


def test_equal_scores_tie_break_is_lexicographic():
    twin_a = Subcap("P1C2.1.1", "Twin cell alpha", "Twin cell alpha.")
    twin_b = Subcap("P1C2.1.2", "Twin cell beta", "Twin cell beta.")
    text = "An excerpt equidistant from two twin cells by construction." + LONG
    enc = TableEncoder({twin_a.text: (1.0, 0.0, 0.0),
                        twin_b.text: (1.0, 0.0, 0.0),
                        text: (1.0, 0.0, 0.0)})
    # margin=0 disables the ambiguity rule so the tie-break itself is visible
    out = propose([("E-1", text)], [twin_a, twin_b], set(), enc, margin=0.0)
    assert out["accepted"][0]["subcap_id"] == "P1C2.1.1"


def test_determinism_under_input_shuffle():
    rng = random.Random(7)
    subcaps, table = [], {}
    for i in range(12):
        s = Subcap(f"P1C1.{i}.1", f"Cell number {i}", f"Cell number {i} text.")
        a = (i % 5) / 5.0
        b = ((i * 3) % 7) / 10.0
        subcaps.append(s)
        table[s.text] = _vec(a, b)
    evidence = []
    for i in range(25):
        t = f"Evidence excerpt number {i} with enough words to be usable" + LONG
        evidence.append((f"E-{i:03d}", t))
        table[t] = _vec(((i * 7) % 9) / 9.0, ((i * 5) % 8) / 12.0)
    links = {("E-003", "P1C1.0.1")}

    out1 = propose(list(evidence), list(subcaps), set(links),
                   TableEncoder(table))
    shuffled_e, shuffled_s = list(evidence), list(subcaps)
    rng.shuffle(shuffled_e)
    rng.shuffle(shuffled_s)
    out2 = propose(shuffled_e, shuffled_s, set(links), TableEncoder(table))
    assert out1 == out2
    out3 = propose(list(evidence), list(subcaps), set(links),
                   TableEncoder(table))
    assert out1 == out3


def test_dry_run_persist_never_touches_the_connection():
    result = {"accepted": [{"e_id": "E-1", "subcap_id": "P1C1.1.1",
                            "score": 0.9, "basis": BASIS_EMBEDDING}],
              "contentions": [], "skipped": [], "params": {}}
    stats = persist_result(None, "any-run", result, dry_run=True)
    assert stats == {"dry_run": True, "links_written": 0, "accepted": 1,
                     "contentions": 0, "skipped": 0}


# ── DB half ─────────────────────────────────────────────────────────────
class KeywordEncoder:
    """Deterministic vectors keyed on marker words, so the DB test controls
    every cosine exactly through the texts it seeds."""
    name = "kw-test-encoder"

    def __init__(self):
        self.batches = []

    def encode(self, texts):
        self.batches.append(list(texts))
        out = []
        for t in texts:
            low = t.lower()
            s, o = "strategy" in low, "onboarding" in low
            if s and o:
                v = _vec(0.70, 0.68)      # ambiguous: margin 0.02
            elif s and "roughly" in low:
                v = _vec(0.55, 0.0)       # plausible but below the floor
            elif s:
                v = _vec(1.0, 0.0)
            elif o:
                v = _vec(0.0, 1.0)
            else:
                v = _vec(0.0, 0.0)        # noise: below the reject line
            out.append(list(v))
        return out


def _connect(user):
    import pg8000.dbapi
    return pg8000.dbapi.connect(user=user, password="local", host=HOST,
                                port=5432, database="dma_insights")


VER = "v7.0-w2test"
EXCERPTS = {
    "E-W2-STRAT": "The board approved a documented digital strategy in 2025 "
                  "covering every line of business.",
    "E-W2-AMBIG": "The digital strategy chapter also narrates the customer "
                  "onboarding overhaul in equal depth.",
    "E-W2-WEAK": "Roughly stated ambitions hint at a strategy but nothing "
                 "is documented anywhere yet.",
    "E-W2-NOISE": "Cafeteria menus were refreshed quarterly according to "
                  "the facilities newsletter.",
    "E-W2-LINKED": "The board approved a documented digital strategy in "
                   "2024; this row is already linked by the package.",
    "E-W2-STATED": "Their P2C1.1.1 rollout was documented at length in the "
                   "2025 annual report appendix.",
}


@pytest.fixture()
def seeded_run():
    try:
        worker = _connect("dmai-worker@digital-maturity-assessor.iam")
        admin = _connect("dmai-migrate@digital-maturity-assessor.iam")
    except Exception:
        pytest.skip("no migrated local database")

    def clean():
        cur = admin.cursor()
        cur.execute("SELECT id FROM entities WHERE display_id = 'w2-link-test-bank'")
        for (eid,) in cur.fetchall():
            for sql in (
                "DELETE FROM evidence_subcap_links WHERE run_id IN (SELECT id FROM runs WHERE entity_id = %s)",
                "DELETE FROM parser_observations WHERE run_id IN (SELECT id FROM runs WHERE entity_id = %s)",
                "DELETE FROM subcap_scores WHERE run_id IN (SELECT id FROM runs WHERE entity_id = %s)",
                "DELETE FROM runs WHERE entity_id = %s",
                "DELETE FROM evidence_index WHERE entity_id = %s",
                "DELETE FROM entities WHERE id = %s",
            ):
                cur.execute(sql, (eid,))
        cur.execute("DELETE FROM ccg_maturity_descriptors WHERE version = %s", (VER,))
        cur.execute("DELETE FROM ccg_categories WHERE version = %s", (VER,))
        cur.execute("DELETE FROM ccg_subcaps WHERE version = %s", (VER,))
        cur.execute("DELETE FROM ccg_versions WHERE version = %s", (VER,))
        admin.commit()

    clean()
    cur = admin.cursor()
    cur.execute("INSERT INTO ccg_versions (version, cell_count, category_count, is_current) "
                "VALUES (%s, 3, 2, FALSE)", (VER,))
    for sid, cap, cat, pil, name in (
        ("P1C1.1.1", "P1C1.1", "P1C1", "P1", "Digital strategy alignment"),
        ("P1C1.1.2", "P1C1.1", "P1C1", "P1", "Capability dimension 3"),
        ("P2C1.1.1", "P2C1.1", "P2C1", "P2", "Customer onboarding journeys"),
    ):
        cur.execute("""INSERT INTO ccg_subcaps
                         (subcap_id, version, capability_id, category_id, pillar_id, name)
                       VALUES (%s,%s,%s,%s,%s,%s)""", (sid, VER, cap, cat, pil, name))
    cur.execute("""INSERT INTO ccg_maturity_descriptors (version, subcap_id, band, narrative)
                   VALUES (%s,'P1C1.1.1','M3','Board-level strategy articulation cadence.')""",
                (VER,))
    admin.commit()

    wcur = worker.cursor()
    wcur.execute("""INSERT INTO entities (display_id, legal_name, status, created_at)
                    VALUES ('w2-link-test-bank','W2 Link Test Bank','ACTIVE', now())
                    RETURNING id""")
    entity_id = wcur.fetchone()[0]
    wcur.execute("""INSERT INTO runs (entity_id, request_id, run_seq,
                                      ccg_catalog_version, status, is_active)
                    VALUES (%s,'DMA-ASM-W2T-20260806-0001',1,%s,'INGESTED',TRUE)
                    RETURNING id""", (entity_id, VER))
    run_id = wcur.fetchone()[0]
    for sid, cap, cat, pil in (("P1C1.1.1", "P1C1.1", "P1C1", "P1"),
                               ("P1C1.1.2", "P1C1.1", "P1C1", "P1"),
                               ("P2C1.1.1", "P2C1.1", "P2C1", "P2")):
        wcur.execute("""INSERT INTO subcap_scores
                          (run_id, subcap_id, capability_id, category_id, pillar_id, score)
                        VALUES (%s,%s,%s,%s,%s, 2.5)""", (run_id, sid, cap, cat, pil))
    for e_id, excerpt in EXCERPTS.items():
        wcur.execute("""INSERT INTO evidence_index (e_id, entity_id, origin, excerpt,
                                                    reference_date)
                        VALUES (%s,%s,'package',%s,'2026-08-01')""",
                     (e_id, entity_id, excerpt))
    wcur.execute("""INSERT INTO evidence_subcap_links (e_id, subcap_id, run_id, link_basis)
                    VALUES ('E-W2-LINKED','P1C1.1.1',%s,'package')""", (run_id,))
    worker.commit()

    yield worker, str(run_id)
    worker.rollback()
    clean()
    worker.close()
    admin.close()


def test_end_to_end_persist_links_contentions_counts_idempotency(seeded_run, capsys):
    worker, run_id = seeded_run
    out = run_for_run(worker, run_id, KeywordEncoder())
    cur = worker.cursor()

    # accepted: the clear embedding winner and the stated-id row, each with
    # its own basis; the stated link is untouched.
    cur.execute("""SELECT e_id, subcap_id, link_basis FROM evidence_subcap_links
                    WHERE run_id = %s ORDER BY e_id""", (run_id,))
    links = cur.fetchall()
    assert [tuple(r) for r in links] == [
        ("E-W2-LINKED", "P1C1.1.1", "package"),
        ("E-W2-STATED", "P2C1.1.1", BASIS_STATED_ID),
        ("E-W2-STRAT", "P1C1.1.1", BASIS_EMBEDDING),
    ]

    # contentions: the ambiguous row and the below-floor row, with reasons,
    # candidates and scores; the noise row is a recorded skip, not a contention.
    cur.execute("""SELECT detail FROM parser_observations
                    WHERE run_id = %s AND kind = %s ORDER BY id""",
                (run_id, OBS_CONTENTION))
    cont = [json.loads(r[0]) if isinstance(r[0], str) else r[0]
            for r in cur.fetchall()]
    by_id = {c["e_id"]: c for c in cont}
    assert set(by_id) == {"E-W2-AMBIG", "E-W2-WEAK"}
    assert by_id["E-W2-AMBIG"]["reason"] == "runner_up_within_margin"
    assert [c["subcap_id"] for c in by_id["E-W2-AMBIG"]["candidates"]] == \
        ["P1C1.1.1", "P2C1.1.1"]
    assert by_id["E-W2-WEAK"]["reason"] == "below_proposal_floor"
    assert by_id["E-W2-WEAK"]["candidates"][0]["score"] == 0.55

    # the pass summary carries params, counts, skip reasons and every
    # accepted link with its score — the audit trail.
    cur.execute("""SELECT detail FROM parser_observations
                    WHERE run_id = %s AND kind = %s""", (run_id, OBS_PASS))
    (raw,) = cur.fetchone()
    summary = json.loads(raw) if isinstance(raw, str) else raw
    assert summary["params"]["floor"] == PROPOSAL_FLOOR
    assert summary["params"]["encoder"] == "kw-test-encoder"
    assert summary["counts"]["links_written"] == 2
    assert summary["skip_reasons"] == {"already_linked": 1,
                                       "no_plausible_candidate": 1}
    scores = {a["e_id"]: a["score"] for a in summary["accepted"]}
    assert scores == {"E-W2-STRAT": 1.0, "E-W2-STATED": None}

    # linked_evidence_count refreshed from the links table
    cur.execute("""SELECT subcap_id, linked_evidence_count FROM subcap_scores
                    WHERE run_id = %s ORDER BY subcap_id""", (run_id,))
    assert [tuple(r) for r in cur.fetchall()] == [
        ("P1C1.1.1", 2), ("P1C1.1.2", 0), ("P2C1.1.1", 1)]

    # the placeholder never matched anything
    assert not any(a["subcap_id"] == "P1C1.1.2"
                   for a in out["result"]["accepted"])
    assert "coverage 1/3 -> 2/3" in capsys.readouterr().out

    # idempotent re-run: accepted rows now short-circuit as already_linked,
    # links do not duplicate, observations are replaced not accumulated.
    out2 = run_for_run(worker, run_id, KeywordEncoder())
    assert out2["stats"]["links_written"] == 0
    cur.execute("SELECT count(*) FROM evidence_subcap_links WHERE run_id = %s",
                (run_id,))
    assert cur.fetchone()[0] == 3
    cur.execute("""SELECT kind, count(*) FROM parser_observations
                    WHERE run_id = %s AND kind IN (%s,%s) GROUP BY kind""",
                (run_id, OBS_CONTENTION, OBS_PASS))
    assert dict(cur.fetchall()) == {OBS_CONTENTION: 2, OBS_PASS: 1}


def test_dry_run_writes_nothing(seeded_run):
    worker, run_id = seeded_run
    out = run_for_run(worker, run_id, KeywordEncoder(), dry_run=True)
    assert out["stats"]["dry_run"] is True
    assert out["stats"]["accepted"] == 2       # it still reports what it found
    cur = worker.cursor()
    cur.execute("SELECT count(*) FROM evidence_subcap_links WHERE run_id = %s",
                (run_id,))
    assert cur.fetchone()[0] == 1              # the seeded stated link only
    cur.execute("""SELECT count(*) FROM parser_observations
                    WHERE run_id = %s AND kind IN (%s,%s)""",
                (run_id, OBS_CONTENTION, OBS_PASS))
    assert cur.fetchone()[0] == 0
    cur.execute("""SELECT count(*) FROM subcap_scores
                    WHERE run_id = %s AND linked_evidence_count IS NOT NULL""",
                (run_id,))
    assert cur.fetchone()[0] == 0              # counts stay NULL: linker never wrote


def test_unpinned_run_refuses_loudly(seeded_run):
    worker, run_id = seeded_run
    cur = worker.cursor()
    cur.execute("UPDATE runs SET ccg_catalog_version = NULL WHERE id = %s",
                (run_id,))
    worker.commit()
    with pytest.raises(ValueError, match="no pinned catalogue version"):
        run_for_run(worker, run_id, KeywordEncoder(), dry_run=True)
