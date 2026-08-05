"""The evidence drawer's read path — invariant 4, fail-closed.

Every cited id must resolve, belong to this entity, and carry a verbatim
excerpt. The distinction between an id that does not exist and an id that
belongs to a DIFFERENT entity is the whole point of the gate: the first is a
broken citation, the second is contamination. A response that collapses them
into "missing" cannot tell a reader which one they are looking at.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api.evidence import (INTERNAL_FIELDS, TIERS, distribution,  # noqa: E402
                              fetch, redact_items)

COLS = ("e_id", "origin", "source_name", "source_url", "source_domain",
        "excerpt", "claim_type", "tier", "published_date", "reference_date",
        "age_months", "recency_band", "ers", "specificity", "corroboration",
        "identity_ok", "identity_note")


def _row(e_id, tier="T2", claim="FACT", entity="A", identity_ok=True, ers=4.2,
         linked=()):
    return {"e_id": e_id, "origin": "PUBLIC_WEB", "source_name": "NCUA",
            "source_url": "https://ncua.gov/x", "source_domain": "ncua.gov",
            "excerpt": "a verbatim excerpt of at least fifty characters, as "
                       "the registration gate requires of every item",
            "claim_type": claim, "tier": tier, "published_date": None,
            "reference_date": None, "age_months": 7, "recency_band": "CURRENT",
            "ers": ers, "specificity": 3, "corroboration": 2,
            "identity_ok": identity_ok, "identity_note": None,
            # The cells this item was linked to for this run. Selected by the
            # read path's LEFT JOIN LATERAL over evidence_subcap_links, which is
            # what makes the drawer's "supports:" chips traceable.
            "linked_subcap_ids": list(linked),
            "_entity": entity}


class _Cur:
    """Enough of a cursor to drive fetch(): the entity-scoped select, and the
    second select that decides not_found vs foreign."""

    def __init__(self, rows):
        self.rows, self._out, self.queries = rows, [], []

    def execute(self, sql, params=None):
        self.queries.append(sql)
        if "WHERE e.entity_id" in sql:
            # run_id, when passed, is bound BEFORE entity_id (it sits inside the
            # lateral), so the entity is the last of the leading params.
            has_run = "k.run_id = %s" in sql
            entity = params[1] if has_run else params[0]
            picked = [r for r in self.rows if r["_entity"] == entity]
            if len(params) > (2 if has_run else 1):
                picked = [r for r in picked if r["e_id"] in params[-1]]
            self._out = [tuple(r[c] for c in COLS + ("linked_subcap_ids",))
                         for r in picked]
        elif "WHERE e_id = ANY" in sql:
            wanted = set(params[0])
            self._out = [(r["e_id"],) for r in self.rows if r["e_id"] in wanted]
        else:                                            # pragma: no cover
            raise AssertionError(sql)

    def fetchall(self):
        return self._out


def test_an_id_from_another_entity_is_foreign_not_missing():
    cur = _Cur([_row("E-1", entity="A"), _row("E-9", entity="B")])
    res = fetch(cur, "A", ["E-1", "E-9", "E-404"])
    assert res["found"] == ["E-1"]
    assert res["foreign"] == ["E-9"], "another entity's id is contamination"
    assert res["not_found"] == ["E-404"], "an unknown id is a broken citation"
    assert [i["e_id"] for i in res["items"]] == ["E-1"], "foreign never renders"


def test_unfiltered_read_reports_no_missing_ids():
    """Asked for every id this entity has, none of them can be absent."""
    cur = _Cur([_row("E-1"), _row("E-2")])
    res = fetch(cur, "A")
    assert res["found"] == ["E-1", "E-2"]
    assert res["not_found"] == [] and res["foreign"] == []
    assert all(i["excerpt"] for i in res["items"]), "the excerpt is the point"


def test_distribution_is_computed_and_excludes_failed_identity():
    """identity_ok = FALSE excludes an item from coverage and the tier
    distribution (the schema says so), so a contaminated citation cannot
    inflate how well evidenced a run looks."""
    items = [_row("E-1", tier="T1"), _row("E-2", tier="T3", claim="INFERENCE"),
             _row("E-3", tier="T3"), _row("E-4", tier="T2", identity_ok=False)]
    d = distribution(items)
    assert d["total_items"] == 3 and d["excluded_identity"] == 1
    assert d["tiers"]["T1"] == 1 and d["tiers"]["T3"] == 2
    assert d["tiers"]["T2"] == 0, "the excluded item is not counted"
    assert d["claims"] == {"FACT": 2, "INFERENCE": 1}
    assert list(d["tiers"])[:5] == list(TIERS), "ladder order, not hash order"


def test_customer_audience_never_receives_the_grading():
    items = [_row("E-1")]
    internal = redact_items(items, "internal")
    assert internal[0]["ers"] == 4.2, "the analyst sees the grading"
    customer = redact_items(items, "customer")
    for f in INTERNAL_FIELDS:
        assert f not in customer[0], f"{f} must not reach the customer"
    assert customer[0]["excerpt"] and customer[0]["source_name"], \
        "the excerpt and its source are exactly what the customer DOES get"
    assert items[0]["ers"] == 4.2, "redaction must not mutate the shared row"


def test_the_evidence_route_precedes_the_generic_page_route():
    """FastAPI matches in declaration order; declared after {page}, the
    evidence path would be read as a page name and 404 as unknown_page."""
    import dma_api.main as m
    paths = [r.path for r in m.app.routes if "{display_id}" in getattr(r, "path", "")]
    assert (paths.index("/v1/entities/{display_id}/evidence")
            < paths.index("/v1/entities/{display_id}/{page}"))


def test_linked_cells_reach_the_drawer_and_are_run_scoped():
    """The drawer's traceable cell links.

    `linked_subcap_ids` lives in evidence_subcap_links, not on evidence_index,
    so the read path joins it. It was not selected at all — every item served
    `subcaps: []` and clicking an evidence id opened a drawer with no way back
    to the cells the item supports, which is exactly the reported defect.
    """
    cur = _Cur([_row("E-1", entity="A", linked=["P4C1.3.1", "P2C3.1.1"])])
    res = fetch(cur, "A", ["E-1"], run_id="run-7")
    assert res["found"] == ["E-1"]
    assert res["items"][0]["linked_subcap_ids"] == ["P4C1.3.1", "P2C3.1.1"]
    # Scoped to the run: a prior run's linkage must not answer for this one.
    assert "k.run_id = %s" in cur.queries[0]


def test_an_item_with_no_linkage_still_resolves():
    """A LEFT JOIN, not an inner one: an unlinked item is still evidence.

    An inner join would have dropped it from `found`, turning a real citation
    into not_found — a fail-closed gate reporting a fabrication that isn't one.
    """
    cur = _Cur([_row("E-2", entity="A", linked=[])])
    res = fetch(cur, "A", ["E-2"], run_id="run-7")
    assert res["found"] == ["E-2"]
    assert res["items"][0]["linked_subcap_ids"] == []


def test_the_linkage_survives_customer_redaction():
    """Redaction strips the grading, not the traceability.

    ERS and its inputs are internal; which cells an item supports is the
    argument itself, and a customer reading the dashboard needs it.
    """
    cur = _Cur([_row("E-3", entity="A", linked=["P1C1.1.1"])])
    items = redact_items(fetch(cur, "A", ["E-3"])["items"], "customer")
    assert items[0]["linked_subcap_ids"] == ["P1C1.1.1"]
    assert all(f not in items[0] for f in INTERNAL_FIELDS)
