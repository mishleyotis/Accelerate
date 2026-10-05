"""T2 GAPS tile: the sentence asserts nothing the register does not record.

RC-11 / D-15, gold audit of run 7968492e (2026-10-04). `computed.landscape`
served the constant "Searched and not established in this estate" on every
GAPS tile. The run's one ABSENT row rested on the institution's own
statement, and no search had run, so the customer's T2 strip claimed a
search that never happened.

Round 1 replaced the constant with a regex over each row's
`detection_basis` prose: a basis without one of a handful of phrasings
became "stated absent, not yet searched". The round-1 review ran it on real
promoted ABSENT bases, and the inverse false claim appeared at once:

  Baxter  "Two independent negatives: absent from a profile of more than
           two hundred platforms, and from a targeted search that returned
           no BCU deployment."  -> "stated absent, not yet searched"
  G1      "Present in the deployed Marketing Cloud edition, yet the July
           2024 discovery evidences no per-member tuning ..."
                                -> "Stated absent by the institution ..."

and a basis that says outright it was NOT searched matched `searched`.

The register has no structured field for how an absence was established
(techstack_items carries status, evidence_level and detection_basis; there
is no `searched`). So the tile states only what the rows record: how many
were recorded absent, and whether each row carries its own basis, which T3
prints for both audiences. It never classifies the producer's prose.

The detail is computed at read time, so it is a body change under an
unmoved promoted_at. It ships inside serve-rules@12, the single undeployed
bump for every round-1 body change (main serves @10). Round 1's GAPS detail
is already one of the changes that bump covers. The tag pin lives in
test_surface_allowlist, not here.
"""
import sys
from pathlib import Path

import pytest

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


# Real promoted ABSENT detection_basis strings the round-1 review ran.
BAXTER = ("Two independent negatives: absent from a profile of more than two "
          "hundred platforms, and from a targeted search that returned no BCU "
          "deployment.")
GOLDEN1 = ("Present in the deployed Marketing Cloud edition, yet the July 2024 "
           "discovery evidences no per-member tuning or journey "
           "personalisation at this layer.")
# Synthetic: the SWBC shape (a statement, no search), and the two prose forms
# a keyword classifier gets backwards.
STATED = ("The institution said in discovery that it has no customer data "
          "platform; no public source confirms or contradicts it.")
SEARCHED = ("Searched job postings, vendor case studies and the client's "
            "technology pages, 2026-10-01: no deployment found.")
NOT_SEARCHED = ("Not searched: search credit ran out; the institution "
                "stated the absence in discovery.")

# Words that assert HOW an absence was established. The register records
# none of them as a fact, so the server may print none of them.
_OUTCOME = ("searched", "not found", "stated absent", "not established",
            "established by", "by the institution", "by the assessment")


def _asserts_no_outcome(detail: str):
    low = detail.lower()
    hits = [w for w in _OUTCOME if w in low]
    assert not hits, f"tile asserts a search outcome {hits}: {detail!r}"


@pytest.mark.parametrize("basis", [BAXTER, GOLDEN1, STATED, SEARCHED,
                                   NOT_SEARCHED, None, ""],
                         ids=["baxter", "golden1", "stated", "searched",
                              "not_searched", "none", "empty"])
def test_no_basis_is_turned_into_a_search_outcome(basis):
    tile = _gaps([("ABSENT", "CDP", "Vendor", "L3", basis)])
    _asserts_no_outcome(tile["detail"])


def test_baxter_is_not_called_unsearched():
    """Baxter's basis names a targeted search; round 1 said 'not yet
    searched'."""
    tile = _gaps([("ABSENT", "A", None, "L3", SEARCHED),
                  ("ABSENT", "B", None, "L3", SEARCHED),
                  ("ABSENT", "C", None, "L3", BAXTER)])
    assert "not yet searched" not in tile["detail"], tile["detail"]
    assert "stated absent" not in tile["detail"].lower(), tile["detail"]


def test_golden1_is_not_called_stated_by_the_institution():
    tile = _gaps([("ABSENT", "Personalisation", "Salesforce", "L2", GOLDEN1)])
    assert "stated absent" not in tile["detail"].lower(), tile["detail"]
    assert "not yet searched" not in tile["detail"], tile["detail"]


def test_a_basis_saying_not_searched_is_never_called_searched():
    tile = _gaps([("ABSENT", "CDP", None, "L4", NOT_SEARCHED)])
    assert not tile["detail"].lower().startswith("searched"), tile["detail"]
    assert "searched and not found" not in tile["detail"].lower()


def test_the_sentence_does_not_read_the_prose():
    """Two registers with the same rows and different prose serve the same
    sentence: the server reads whether a basis is recorded, never what it
    says."""
    a = _gaps([("ABSENT", "X", None, "L3", BAXTER),
               ("ABSENT", "Y", None, "L3", STATED)])
    b = _gaps([("ABSENT", "X", None, "L3", SEARCHED),
               ("ABSENT", "Y", None, "L3", NOT_SEARCHED)])
    assert a["detail"] == b["detail"]


def test_every_row_with_a_basis_points_at_the_row():
    tile = _gaps([("ABSENT", "X", None, "L3", BAXTER),
                  ("ABSENT", "Y", None, "L4", STATED)])
    assert "each row states how" in tile["detail"].lower(), tile["detail"]


def test_a_row_without_a_basis_is_counted_not_explained():
    """A missing basis is stated as missing; the tile does not fill it in."""
    tile = _gaps([("ABSENT", "X", None, "L3", BAXTER),
                  ("ABSENT", "Y", None, None, None),
                  ("ABSENT", "Z", None, None, "  ")])
    d = tile["detail"]
    assert "1 of 3" in d and "record no basis" in d, d
    _asserts_no_outcome(d)


def test_a_four_column_cursor_still_reads():
    """Older fakes and unwidened callers carry no detection_basis: that is
    'no basis recorded', never a search and never a statement."""
    tile = _gaps([("ABSENT", "CDP", None, None)])
    assert "no row records" in tile["detail"].lower(), tile["detail"]
    _asserts_no_outcome(tile["detail"])


def test_no_absent_row_says_so():
    tile = _gaps([("CONFIRMED", "Snowflake", "Snowflake", "L1", "x")])
    assert tile["count"] == 0
    assert tile["detail"] == "No product is recorded absent in this register."

