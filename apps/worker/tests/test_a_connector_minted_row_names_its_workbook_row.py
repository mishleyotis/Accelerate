"""A drawer whose row the connector minted still gets the workbook's URL.

MEASURED 2026-09-04 against production. Teaching `parse_research_workbook`
to read `Evidence_Detail` (commit 80468c7) made every one of Golden 1's 731
ledger rows carry a URL — and would still have left 223 of the 497 URL-less
served rows blank, because `backfill_evidence` reaches a row by the numeric
suffix of its `e_id` and those 223 wear `E-CC-nnn`. `E-CC-569` is the 569th
id the CONNECTOR allocated. It is not the 569th row of anyone's workbook,
and joining it to `E-569` would attach a real URL to the wrong quote.

Those rows do say where they came from, in the only place they can: their
own `source_name`.

    "DFPI Regulated Entity Record — Golden 1 [package evidence id E-5123]"
    "Banking Dive — How Golden 1 used AI … — package id E-055;"

222 of the 223 named a workbook row that way, and every one of the 222
resolved to a ledger row stating a URL. Reading that marker is the package
telling us its own provenance — the join key is IN THE DATA. Guessing from
a number is not, which is why the suffix pass is left exactly as it was and
this is a second pass beside it.

Run with
`pytest apps/worker/tests/test_a_connector_minted_row_names_its_workbook_row.py`.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "worker"))

import job_main


# --------------------------------------------------------------------------
# the marker itself
# --------------------------------------------------------------------------

@pytest.mark.parametrize("source_name,expected", [
    ("DFPI Regulated Entity Record [package evidence id E-5123]", "E-5123"),
    ("Banking Dive — how Golden 1 used AI — package id E-055;", "E-055"),
    ("NCUA Call Report [Package Evidence ID e-001]", "e-001"),
    ("Golden1 DMA Input Brief (2026-08-25) [package evidence id E-ENR-02]",
     "E-ENR-02"),
])
def test_the_row_states_which_workbook_row_it_came_from(source_name, expected):
    assert job_main.stated_package_id(source_name) == expected


@pytest.mark.parametrize("source_name", [
    None,
    "",
    "Fiserv case study — no provenance marker at all",
    "A press release that merely mentions a package",
])
def test_a_row_that_names_nothing_yields_nothing(source_name):
    """Absence of a marker is not a licence to guess one."""
    assert job_main.stated_package_id(source_name) is None


# --------------------------------------------------------------------------
# the pass
# --------------------------------------------------------------------------

class _Cursor:
    """Enough of a cursor to watch which rows the pass decides to touch."""

    def __init__(self, todo, unresolved_rows):
        self._todo, self._unresolved = todo, unresolved_rows
        self._mode = None
        self.suffix_updates, self.named_updates, self.observed = [], [], []
        self.rowcount = 0

    def execute(self, sql, params=None):
        if sql.startswith("SAVEPOINT") or sql.startswith("RELEASE") \
                or sql.startswith("ROLLBACK"):
            return
        if "FROM runs r" in sql:
            self._mode = "todo"
        elif "SELECT e_id, source_name, excerpt" in sql:
            self._mode = "named"
        elif "split_part(e_id, '-', 3)" in sql:
            self.suffix_updates.append(params)
            self.rowcount = 0            # nothing here has a matching suffix
        elif "AND e_id = %s" in sql:
            self.named_updates.append(params)
            self.rowcount = 1
        elif "parser_observations" in sql:
            kind = sql.split("'")[1] if "'" in sql else "?"
            self.observed.append((kind, params))
        else:                                            # pragma: no cover
            raise AssertionError(f"unexpected sql: {sql[:70]}")

    def fetchall(self):
        return self._todo if self._mode == "todo" else self._unresolved


class _Conn:
    def __init__(self, cur):
        self.cur, self.commits = cur, 0

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1

    def rollback(self):                                  # pragma: no cover
        pass


LEDGER = [
    {"e_id": "E-055", "source_name": "Banking Dive",
     "source_url": "https://bankingdive.example/golden1-ai",
     "claim_type": "FACT", "excerpt": "A" * 60},
    {"e_id": "E-5123", "source_name": "Golden1 DMA Input Brief",
     "source_url": "https://drive.example/input-brief",
     "claim_type": "FACT", "excerpt": "B" * 60},
    {"e_id": "E-777", "source_name": "A row nobody cites",
     "source_url": "https://example.test/unused",
     "claim_type": "FACT", "excerpt": "C" * 60},
]


def _stub_workbook(monkeypatch, ledger=LEDGER):
    monkeypatch.setattr(job_main.drive, "download", lambda t, fid: b"bytes")
    monkeypatch.setattr(job_main, "parse_evidence_master", lambda p: ledger)
    monkeypatch.setattr(job_main, "parse_scoring_workbook",
                        lambda p: type("W", (), {"scores": []})())
    monkeypatch.setattr(job_main, "mine_evidence_from_rationales",
                        lambda scores: {})


def _f(folder, name):
    from dma_worker.scan_diff import FileStat
    return FileStat(file_id=f"{folder}/{name}", path_segments=(folder, name),
                    name=name, checksum="abc", size_bytes=10, mime_type="")


def _groups():
    return job_main._package_groups(
        [_f("Golden 1 Credit Union - DMA", "DMA_Scoring_Workbook_G1.xlsx")])


def test_a_connector_minted_row_is_filled_from_the_row_it_names(monkeypatch):
    """The whole point: `E-CC-569` says `[package evidence id E-5123]`, so it
    gets E-5123's URL — the one the workbook states, not one we invented."""
    _stub_workbook(monkeypatch)
    cur = _Cursor(
        todo=[("run-1", "ent-g1", "Golden 1 Credit Union - DMA", 1)],
        unresolved_rows=[
            ("E-CC-569", "DFPI record [package evidence id E-5123]", "B" * 60),
            ("E-CC-564", "Banking Dive — package id E-055;", "A" * 60),
        ])
    conn = _Conn(cur)

    assert job_main.backfill_evidence(conn, "tok", _groups(), forced=True) == 0

    urls = [p[0] for p in cur.named_updates]
    assert urls == ["https://drive.example/input-brief",
                    "https://bankingdive.example/golden1-ai"], \
        "the served row did not receive the URL of the workbook row it names"
    assert [p[4] for p in cur.named_updates] == ["E-CC-569", "E-CC-564"], \
        "the update did not address the row by its own id"


def test_a_row_naming_a_workbook_row_that_does_not_exist_is_recorded(monkeypatch):
    """A blank drawer with no account of why it is blank is the defect this
    whole thread is about. If the marker points nowhere, say so."""
    _stub_workbook(monkeypatch)
    cur = _Cursor(
        todo=[("run-1", "ent-g1", "Golden 1 Credit Union - DMA", 1)],
        unresolved_rows=[("E-CC-901", "Something [package evidence id E-9999]",
                          "Q" * 60)])
    conn = _Conn(cur)

    job_main.backfill_evidence(conn, "tok", _groups(), forced=True)

    assert cur.named_updates == [], "a marker pointing nowhere invented a URL"
    said = [json.loads(params[1]) for kind, params in cur.observed
            if kind == "evidence_stated_id_unresolved"]
    assert said and said[0]["named"] == "1" and said[0]["filled"] == "0", \
        "the unresolvable marker was not recorded"


def test_a_row_that_names_nothing_is_left_alone(monkeypatch):
    """No marker, no fill. The suffix pass is the only route for those rows,
    and silence beats a plausible-looking wrong URL."""
    _stub_workbook(monkeypatch)
    cur = _Cursor(
        todo=[("run-1", "ent-g1", "Golden 1 Credit Union - DMA", 1)],
        unresolved_rows=[("E-CC-570", "A source with no provenance marker",
                          "Q" * 60)])
    conn = _Conn(cur)

    job_main.backfill_evidence(conn, "tok", _groups(), forced=True)

    assert cur.named_updates == []
    assert [k for k, _ in cur.observed
            if k == "evidence_stated_id_unresolved"] == [], \
        "a row that named nothing was reported as an unresolved marker"


def test_the_fill_never_overwrites_a_url_the_package_already_stated(monkeypatch):
    """COALESCE, in the SQL and in the contract. Re-running the pass is
    additive or it is not safe to run every thirty minutes."""
    _stub_workbook(monkeypatch)
    cur = _Cursor(
        todo=[("run-1", "ent-g1", "Golden 1 Credit Union - DMA", 1)],
        unresolved_rows=[("E-CC-569", "DFPI [package evidence id E-5123]",
                          "B" * 60)])
    conn = _Conn(cur)

    job_main.backfill_evidence(conn, "tok", _groups(), forced=True)

    sent = [s for s in _SQL_SEEN if "AND e_id = %s" in s]
    assert sent, "the named pass issued no update"
    assert "COALESCE(source_url" in sent[0], \
        "the named pass can overwrite a URL the package already stated"


_SQL_SEEN: list[str] = []
_orig_execute = _Cursor.execute


def _recording_execute(self, sql, params=None):
    _SQL_SEEN.append(sql)
    return _orig_execute(self, sql, params)


_Cursor.execute = _recording_execute


def test_improving_the_matcher_re_opens_every_run_it_gave_up_on(monkeypatch):
    """The scheduled pass skips a run this reader has already been through.
    A reader that has learnt a second way to reach a row is a DIFFERENT
    reader, and every run stamped by the old one has to re-open by itself —
    with nobody having to remember to bump a number."""
    before = job_main.evidence_reader_fingerprint()
    monkeypatch.setattr(job_main, "stated_package_id",
                        lambda source_name: "E-ANYTHING-ELSE")
    assert job_main.evidence_reader_fingerprint() != before, \
        "changing how a row is matched left the fingerprint unchanged, so " \
        "every already-passed run stays closed to the improvement"


# --------------------------------------------------------------------------
# the excerpt is what corroborates the marker
# --------------------------------------------------------------------------

CLIPPED = ("Golden 1 Credit Union is a California state-chartered, "
           "NCUA-insured credit union headquartered in Sacramento")
FULL = CLIPPED + ", serving members across the state since 1933."


@pytest.mark.parametrize("served,stated,expected", [
    # the same passage, byte for byte
    (FULL, FULL, True),
    # the ingest clips into the 50-500 window, so the served row holds a
    # PREFIX of what Evidence_Master states. Same passage, fewer characters.
    (CLIPPED, FULL, True),
    (FULL, CLIPPED, True),
    # whitespace and case are formatting, not content
    ("  The  Quick   Brown Fox jumps over the lazy dog and keeps on going ",
     "the quick brown fox jumps over the lazy dog and keeps on going", True),
    # a different passage entirely — the marker is pointing somewhere else
    (FULL, "DFPI lists Golden 1 as a regulated entity with total assets of "
           "$21.1bn as at the 2026-Q1 call report", False),
    # nothing to compare: never guessed either way
    (None, FULL, None),
    ("", FULL, None),
    (FULL, None, None),
])
def test_the_quote_decides_whether_the_marker_is_believed(served, stated,
                                                          expected):
    assert job_main.excerpt_agrees(served, stated) is expected


def test_a_marker_whose_quote_contradicts_it_fills_nothing(monkeypatch):
    """THE GUARD. `[package evidence id E-5123]` is text a producer wrote; a
    mistyped digit would hang a real, checkable URL under somebody else's
    quote — worse than the blank drawer it replaced. The excerpt is the
    independent check, and it refuses."""
    _stub_workbook(monkeypatch)
    cur = _Cursor(
        todo=[("run-1", "ent-g1", "Golden 1 Credit Union - DMA", 1)],
        unresolved_rows=[
            ("E-CC-569", "DFPI record [package evidence id E-5123]",
             "A passage about something else entirely, at length, so that "
             "no prefix of it could be mistaken for the ledger's quote.")])
    conn = _Conn(cur)

    job_main.backfill_evidence(conn, "tok", _groups(), forced=True)

    assert cur.named_updates == [], \
        "a URL was attached to a row whose own quote says it is a different " \
        "source"
    said = [json.loads(params[1]) for kind, params in cur.observed
            if kind == "evidence_stated_id_excerpt_conflict"]
    assert said and said[0]["rows"] == "1", \
        "the contradiction was not recorded, so nobody can go and look"


def test_a_clipped_quote_is_still_the_same_quote(monkeypatch):
    """The other half: the guard must not refuse the normal case. The served
    excerpt is routinely a clipped prefix of the Evidence_Master one, and
    every one of Golden 1's 258 marker rows looks like this."""
    ledger = [{"e_id": "E-5123", "source_name": "Golden1 DMA Input Brief",
               "source_url": "https://drive.example/input-brief",
               "claim_type": "FACT", "excerpt": FULL}]
    _stub_workbook(monkeypatch, ledger)
    cur = _Cursor(
        todo=[("run-1", "ent-g1", "Golden 1 Credit Union - DMA", 1)],
        unresolved_rows=[("E-CC-569", "Brief [package evidence id E-5123]",
                          CLIPPED)])
    conn = _Conn(cur)

    job_main.backfill_evidence(conn, "tok", _groups(), forced=True)

    assert [p[0] for p in cur.named_updates] == \
        ["https://drive.example/input-brief"], \
        "the guard refused a clipped prefix of the same passage"
    assert not [k for k, _ in cur.observed
                if k == "evidence_stated_id_excerpt_conflict"]


def test_the_excerpt_is_filled_from_the_same_row_as_the_url(monkeypatch):
    """`Evidence_Master` supplies both. A drawer with a link and no quote is
    still a drawer nobody can check (invariant 4)."""
    _stub_workbook(monkeypatch)
    cur = _Cursor(
        todo=[("run-1", "ent-g1", "Golden 1 Credit Union - DMA", 1)],
        unresolved_rows=[("E-CC-569", "Brief [package evidence id E-5123]",
                          None)])
    conn = _Conn(cur)

    job_main.backfill_evidence(conn, "tok", _groups(), forced=True)

    assert len(cur.named_updates) == 1
    # the trailing three repeat url/excerpt/claim so the statement can match
    # only rows it will actually change (see the WHERE in `backfill_evidence`)
    url, excerpt, claim, _ent, e_id = cur.named_updates[0][:5]
    assert url == "https://drive.example/input-brief"
    assert excerpt == "B" * 60, \
        "the row got a link but no quote to check it against"
    assert claim == "FACT" and e_id == "E-CC-569"


def test_tightening_the_quote_rule_re_opens_every_run(monkeypatch):
    """`_EXCERPT_HEAD` decides which rows are believed, so changing it is a
    different reader and every run stamped by the old one must re-open."""
    before = job_main.evidence_reader_fingerprint()
    monkeypatch.setattr(job_main, "_EXCERPT_HEAD", 200)
    assert job_main.evidence_reader_fingerprint() != before
