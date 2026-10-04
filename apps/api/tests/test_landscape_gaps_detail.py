"""T2 GAPS tile: the sentence says how each absence was established.

RC-11 / D-15, gold audit of run 7968492e (2026-10-04). `computed.landscape`
gave the GAPS tile the constant "Searched and not established in this
estate" whatever the rows said. The run's one ABSENT row rested on the
institution's own statement in discovery ("no public source confirms or
contradicts it"). Search credit had run out, so no ABSENT search was run.
The customer's T2 strip therefore claimed a search that never happened.

The detail is now chosen per row, from whether the row's own
`detection_basis` records a search. The server never invents one.

Negative control: against the pre-fix module, the first and third
assertions fail, because the detail is the constant either way.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_api import computed


class _Cur:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, *_a, **_k):
        pass

    def fetchall(self):
        return self.rows


def _gaps(rows):
    data = {}
    computed.landscape(_Cur(rows), data, "run")
    return {t["kind"]: t for t in data["tiles"]}["GAPS"]


STATED = ("The institution said in discovery that it has no customer data "
          "platform; no public source confirms or contradicts it.")
SEARCHED = ("Searched job postings, vendor case studies and the client's "
            "technology pages, 2026-10-01: no deployment found.")


def test_a_stated_absence_is_not_called_searched():
    tile = _gaps([("CONFIRMED", "Snowflake", "Snowflake", "L1", "Named in a case study."),
                  ("ABSENT", "Data Cloud", "Salesforce", "L4", STATED)])
    assert "not yet searched" in tile["detail"], tile["detail"]
    assert not tile["detail"].lower().startswith("searched"), (
        "the tile claims a search the row does not record")


def test_a_recorded_search_is_said_to_be_one():
    tile = _gaps([("ABSENT", "Data Cloud", "Salesforce", "L3", SEARCHED)])
    assert tile["detail"].startswith("Searched and not found"), tile["detail"]


def test_a_mixed_register_says_how_many_of_each():
    tile = _gaps([("ABSENT", "Data Cloud", "Salesforce", "L3", SEARCHED),
                  ("ABSENT", "MDM", "Informatica", "L4", STATED),
                  ("ABSENT", "CDP", None, None, None)])
    assert "1 searched and not found" in tile["detail"], tile["detail"]
    assert "2 stated absent, not yet searched" in tile["detail"], tile["detail"]


def test_no_absent_row_claims_no_search_either():
    tile = _gaps([("CONFIRMED", "Snowflake", "Snowflake", "L1", "x")])
    assert tile["count"] == 0
    assert "searched" not in tile["detail"].lower(), tile["detail"]


def test_a_four_column_cursor_still_reads():
    """The register rows of older fakes, and any caller that has not been
    widened, carry no detection_basis. That is "not recorded", which is
    never a search."""
    tile = _gaps([("ABSENT", "CDP", None, None)])
    assert "not yet searched" in tile["detail"]
