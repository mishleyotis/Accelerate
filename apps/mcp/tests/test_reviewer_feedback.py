"""The consumer: an Accept/Reject verdict becoming memory.

No live DB — a fake connection speaks the module's own SQL and records every
statement, and `record_finding` is captured so the FINDING PAYLOAD can be
asserted rather than the row it would have written.

What is pinned:

  * a REJECT raises a finding carrying the card's own text AND its `r_layer`.
    A verdict with no claim attached teaches nothing, and the r_layer is the
    part the reviewer actually refused.
  * an ACCEPT does not become a defect. It lands as a verdict row, which is
    what makes the reject RATE measurable.
  * a verdict whose body cannot be read is left un-ingested and NAMED. Counting
    it as nothing is the exact class this build kept producing
    (UNRECOGNISED_INPUT_READS_AS_EMPTY), and the consumer must not repeat it.
  * the reject finding's measurement carries the rate with its denominator, not
    the anecdote.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp import feedback as fb                              # noqa: E402
from dma_mcp import memory as mem                               # noqa: E402

T0 = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
RUN = "11111111-1111-1111-1111-111111111111"
ENT = "22222222-2222-2222-2222-222222222222"

CARD = ("Fraud detection buys advocacy and spends it at the till",
        "Members praise the fraud alerts.",
        "The detection model is tuned for recall.",
        "Advocacy earned in one channel is spent in another.",
        "Counter-case: review sites over-represent complaints.",
        "high",
        "A false decline at the point of sale is a lost transaction.",
        "How many declines are reversed within an hour?",
        "INFERENCE", "P2C1.1.1",
        {"counter": "Counter-case: review sites over-represent complaints; "
                    "rejected because the theme repeats across two sites.",
         "probes_run": "two review corpora, one detection vendor page"})


class _Conn:
    def __init__(self, pending, card=CARD, tally=(("ACCEPT", 3), ("REJECT", 1))):
        self.pending, self.card, self.tally = list(pending), card, list(tally)
        self.sql, self.inserts = [], []
        self._rows, self._one = [], None
        self.committed = 0

    # the connector calls conn.cursor() and conn.commit()
    def cursor(self):
        return self

    def commit(self):
        self.committed += 1

    def execute(self, sql, params=()):
        s = " ".join(sql.split())
        self.sql.append((s, params))
        low = s.lower()
        if "from annotations" in low and "memory_reviewer_verdicts v" in low:
            self._rows, self._one = self.pending, None
        elif "from insight_cards" in low:
            self._one = self.card
        elif low.startswith("insert into memory_reviewer_verdicts"):
            self.inserts.append(params)
            self._one = None
        elif "count(*) filter (where action = 'reject')" in low:
            self._one = (1, 4)
        elif low.startswith("select action, count(*)"):
            self._rows, self._one = self.tally, None
        elif low.startswith("insert into memory_finding_sightings"):
            self._one = (99,)
        else:
            self._rows, self._one = [], None

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._rows


def _pending(aid, action, note=None, ic="IC-1", body=None):
    return (aid, ic,
            body if body is not None else json.dumps({"action": action,
                                                      "note": note}),
            T0, RUN, ENT, "analyst@zennify.com", "baxter-credit-union-bcu")


@pytest.fixture()
def captured(monkeypatch):
    seen = []

    def fake(conn, finding, encoder=None):
        seen.append(finding)
        return {"finding_id": f"MEM-{len(seen):04d}", "deduped": False,
                "sighting_id": 1, "sightings": 1, "recurrences": 0,
                "status": "OPEN", "errors": []}
    monkeypatch.setattr(mem, "record_finding", fake)
    return seen


# ── a reject teaches something ──────────────────────────────────────────
def test_a_reject_raises_a_finding_carrying_the_card_and_its_r_layer(captured):
    conn = _Conn([_pending(1, "REJECT", "the mechanism is not shown")])
    out = fb.ingest_reviewer_feedback(conn)
    assert out["ingested"] == 1 and out["skipped"] == 0
    assert out["findings_raised"] == [{"annotation_id": 1, "ic_id": "IC-1",
                                       "finding_id": "MEM-0001"}]
    f = captured[0]
    assert f["defect_class"] == fb.REJECT_CLASS
    assert f["component"] == fb.PRODUCER_COMPONENT, (
        "a rejected claim is a defect in what PRODUCED it, not in the app "
        "that rendered it faithfully")
    assert "Fraud detection buys advocacy" in f["title"]
    # the card's own text
    assert "Members praise the fraud alerts." in f["observed"]
    assert "So what:" in f["observed"]
    # and the reasoning the reviewer refused
    assert "r_layer" in f["observed"]
    assert "review sites over-represent complaints" in f["observed"]
    assert "the mechanism is not shown" in f["observed"]
    assert f["annotation_id"] == 1 and f["source_ref"] == "annotation:1"


def test_the_reject_measurement_carries_the_rate_with_its_denominator(captured):
    conn = _Conn([_pending(1, "REJECT")])
    fb.ingest_reviewer_feedback(conn)
    m = captured[0]["measurement"]
    assert len(m) >= mem.MEASUREMENT_FLOOR
    assert "annotation id 1" in m and "IC-1" in m
    assert "/annotation" in m, "the measurement must name the request that made it"
    assert "2 rejected of 5 annotated cards" in m, (
        "one reject out of one verdict and one out of forty are different "
        "facts about the producer")
    assert captured[0]["measured_value"] == "2/5 rejected on this run"


def test_the_cards_severity_maps_into_the_findings_vocabulary(captured):
    conn = _Conn([_pending(1, "REJECT")])
    fb.ingest_reviewer_feedback(conn)
    assert captured[0]["severity"] in mem.SEVERITIES
    assert captured[0]["severity"] == "MAJOR"     # card severity 'high'
    for card_sev, mapped in fb._SEVERITY.items():
        assert mapped in mem.SEVERITIES, f"{card_sev} maps outside the vocabulary"


# ── an accept is not a defect ───────────────────────────────────────────
def test_an_accept_lands_as_a_verdict_and_raises_no_finding(captured):
    conn = _Conn([_pending(2, "ACCEPT", "reads well")])
    out = fb.ingest_reviewer_feedback(conn)
    assert out["ingested"] == 1 and out["findings_raised"] == []
    assert captured == [], "an accept must not be made into a defect"
    assert conn.inserts, "the verdict itself must still be recorded"
    assert conn.inserts[0][1] == "ACCEPT"


def test_the_verdict_row_carries_the_card_text_and_the_r_layer(captured):
    conn = _Conn([_pending(3, "ACCEPT")])
    fb.ingest_reviewer_feedback(conn)
    params = conn.inserts[0]
    assert params[8] == CARD[0]                       # card_title
    assert "Members praise the fraud alerts." in params[9]   # card_text
    stored = json.loads(params[13])                   # r_layer
    assert "counter" in stored and "probes_run" in stored


# ── an unreadable verdict is named, never counted as nothing ────────────
def test_an_unreadable_body_is_left_un_ingested_and_named(captured):
    conn = _Conn([_pending(4, None, body="{not json")])
    out = fb.ingest_reviewer_feedback(conn)
    assert out["ingested"] == 0 and out["skipped"] == 1
    assert conn.inserts == []
    assert out["problems"][0]["reason"] == "unreadable_action"
    assert "{not json" in out["problems"][0]["detail"]


def test_an_action_outside_the_vocabulary_is_also_named(captured):
    conn = _Conn([_pending(5, "MAYBE")])
    out = fb.ingest_reviewer_feedback(conn)
    assert out["ingested"] == 0 and out["skipped"] == 1
    assert out["problems"][0]["reason"] == "unreadable_action"


def test_a_verdict_on_a_card_that_no_longer_exists_still_lands(captured):
    conn = _Conn([_pending(6, "ACCEPT")], card=None)
    out = fb.ingest_reviewer_feedback(conn)
    assert out["ingested"] == 1
    assert out["problems"][0]["reason"] == "card_not_found"
    assert conn.inserts[0][8] is None                 # card_title


def test_a_refused_finding_leaves_the_reject_un_ingested(monkeypatch):
    monkeypatch.setattr(mem, "record_finding",
                        lambda conn, finding, encoder=None:
                        {"finding_id": None, "errors": ["measurement: too short"]})
    conn = _Conn([_pending(7, "REJECT")])
    out = fb.ingest_reviewer_feedback(conn)
    assert out["ingested"] == 0 and out["skipped"] == 1
    assert conn.inserts == [], (
        "a REJECT stored with no finding is a verdict that went nowhere — the "
        "CHECK in 0034 forbids the row, and this module must not try")
    assert out["problems"][0]["reason"] == "finding_refused"


# ── the tally is computed, never assumed ────────────────────────────────
def test_the_tally_and_reject_rate_are_read_back_from_the_table(captured):
    conn = _Conn([_pending(8, "ACCEPT")], tally=[("ACCEPT", 6), ("REJECT", 2)])
    out = fb.ingest_reviewer_feedback(conn)
    assert out["verdict_tally"] == {"ACCEPT": 6, "REJECT": 2}
    assert out["reject_rate"] == 0.25


# ── the small readers ───────────────────────────────────────────────────
def test_body_parsing_distinguishes_unreadable_from_empty():
    assert fb._body('{"action":"ACCEPT"}') == {"action": "ACCEPT"}
    assert fb._body("[1,2]")["_unparsed"] == "[1,2]"
    assert fb._body("garbage")["_unparsed"] == "garbage"
    assert fb._body(None)["_unparsed"] == "None"


def test_card_text_keeps_the_cards_order_and_drops_blanks():
    text = fb._card_text({"what_text": "w", "so_what_text": "s"})
    assert text == "What: w\nSo what: s"
    assert fb._card_text({}) == ""
