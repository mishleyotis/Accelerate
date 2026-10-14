"""A shareable split span serves under its customer attribution only on a run
PROMOTED AT OR AFTER the span was minted (RC-08 / D-10; adversarial review
of fix/serving-redaction-evidence, 2026-10-04).

`evidence_index` is shared by every run of an entity, and the api reads
`customer_attribution` live on every request: in the page's evidence scope,
in the cell drawer's items and in the evidence route. The review measured
what that meant: a producer working on a NEW, unpromoted run could expose a
previously withheld internal row on the LIVE promoted run — and on every
historical run citing it — outside promotion (invariant 3) and under an
unchanged ETag.

The connector now never writes an attribution onto an existing row (apps/mcp
test_split_span_attribution). This is the serving half: the label is BOUND
to the promotion. A run promoted before `customer_attribution_at` keeps
serving exactly what it served — the span withheld like any internal row —
until a payload citing the span is promoted, which moves `promoted_at` and so
the ETag. Missing either instant is not bound: default-deny.

Fixture rows are SHAPED like the measured ones and carry no client text.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api import computed, evidence, pages                    # noqa: E402
from dma_api.redaction import (customer_evidence_items,           # noqa: E402
                               redact_evidence_response, redact_section)

LABEL = "Client statement, discovery conversations, September 2026"
SPAN = ("No single customer profile spans the insurance, mortgage and "
        "wealth lines today.")
MINTED = datetime(2026, 10, 4, 15, 0, tzinfo=timezone.utc)
BEFORE = (MINTED - timedelta(days=2)).isoformat()      # the live promoted run
AFTER = (MINTED + timedelta(hours=1)).isoformat()      # re-promoted, citing it


# ── the rule ───────────────────────────────────────────────────────────────
def test_attribution_binds_forward_only():
    bound = evidence.attribution_bound
    assert bound(MINTED, AFTER) is True
    assert bound(MINTED, MINTED.isoformat()) is True     # same instant
    assert bound(MINTED, BEFORE) is False                # the live run
    assert bound(None, AFTER) is False                   # no mint instant
    assert bound(MINTED, None) is False                  # never promoted
    assert bound(MINTED, "") is False
    assert bound(MINTED, "not a date") is False
    # an ISO string from the DB driver and a naive UTC instant both read
    assert bound(MINTED.isoformat(), AFTER) is True
    assert bound(MINTED.replace(tzinfo=None), AFTER) is True


# ── the customer item filter: default-deny without the binding ───────────
def _item(e_id, bound=None, attribution=LABEL):
    it = {"e_id": e_id, "origin": "internal",
          "source_name": "Discovery notes", "source_url": None,
          "excerpt": SPAN, "claim_type": "FACT", "tier": "T2",
          "customer_attribution": attribution, "split_of": "E-CC-1",
          "customer_attribution_at": MINTED.isoformat()}
    if bound is not None:
        it["attribution_bound"] = bound
    return it


def test_an_attribution_not_bound_to_the_run_does_not_serve():
    kept, withheld = customer_evidence_items(
        [_item("E-CC-2"), _item("E-CC-3", bound=False)])
    assert kept == [] and withheld == {"internal_origin": 2}


def test_a_bound_attribution_serves_under_its_label_and_carries_no_binding():
    kept, _ = customer_evidence_items([_item("E-CC-2", bound=True)])
    assert [i["e_id"] for i in kept] == ["E-CC-2"]
    assert kept[0]["source_name"] == LABEL
    for k in ("customer_attribution", "customer_attribution_at",
              "attribution_bound", "split_of", "origin"):
        assert k not in kept[0], k


# ── the page scope ─────────────────────────────────────────────────────────
class _Cur:
    def __init__(self, rows):
        self.rows, self.sql, self.params = rows, [], []

    def execute(self, sql, params=None):
        self.sql.append(sql)
        self.params.append(params)

    def fetchall(self):
        return self.rows


ROWS = [("E-CC-2", "internal", LABEL, MINTED),
        ("E-CC-3", "internal", None, None),
        ("E-CC-9", "producer", None, None)]


def test_the_live_run_keeps_the_span_withheld():
    scope = pages.evidence_scope(_Cur(ROWS), "ent-1",
                                 {"E-CC-2", "E-CC-3", "E-CC-9"},
                                 promoted_at=BEFORE)
    assert scope == {"withheld": {"E-CC-2", "E-CC-3"}, "attribution": {}}


def test_a_run_promoted_after_the_mint_serves_it():
    scope = pages.evidence_scope(_Cur(ROWS), "ent-1",
                                 {"E-CC-2", "E-CC-3", "E-CC-9"},
                                 promoted_at=AFTER)
    assert scope == {"withheld": {"E-CC-3"}, "attribution": {"E-CC-2": LABEL}}


def test_the_scope_reads_the_mint_instant():
    cur = _Cur(ROWS)
    pages.evidence_scope(cur, "ent-1", {"E-CC-2"}, promoted_at=AFTER)
    assert "customer_attribution_at" in cur.sql[0]


def test_a_page_body_on_the_live_run_is_what_it_was():
    """The whole point: the same promoted body, the same customer bytes,
    before and after a span is minted for a later run."""
    body = {"cards": [{"ic_id": "IC-1", "title": "t",
                       "supporting_e_ids": ["E-CC-2", "E-CC-9"]}]}
    scope = pages.evidence_scope(_Cur(ROWS), "ent-1", {"E-CC-2", "E-CC-9"},
                                 promoted_at=BEFORE)
    out, _ = redact_section("insights", "insights", body, [], "customer",
                            evidence_scope=scope)
    assert out["cards"][0]["supporting_e_ids"] == ["E-CC-9"]


# ── the cell drawer ────────────────────────────────────────────────────────
DRAWER_ROWS = [("E-CC-2", "E-CC-2", "T2", "FACT", "CURRENT", "Discovery notes",
                None, SPAN, None, "internal", LABEL, MINTED)]


def _cell():
    return {"cells": [{"subcap_id": "P4C1.1.1", "synthesis": "s",
                       "e_ids": ["E-CC-2"], "grounded_on": 1}]}


def test_the_drawer_on_the_live_run_withholds_the_span():
    data = _cell()
    computed.cell_items(_Cur(DRAWER_ROWS), data, "ent-1", promoted_at=BEFORE)
    out, _ = redact_section("heatmap", "cell_evidence", data, [], "customer")
    assert out["cells"][0]["items"] == []
    assert out["cells"][0]["e_ids"] == []


def test_the_drawer_on_a_run_promoted_after_serves_it():
    data = _cell()
    computed.cell_items(_Cur(DRAWER_ROWS), data, "ent-1", promoted_at=AFTER)
    out, _ = redact_section("heatmap", "cell_evidence", data, [], "customer")
    items = out["cells"][0]["items"]
    assert [i["e_id"] for i in items] == ["E-CC-2"]
    assert items[0]["source_title"] == LABEL


def test_apply_passes_the_runs_promotion_to_the_drawer():
    data = _cell()
    computed.apply(_Cur(DRAWER_ROWS), "heatmap", "cell_evidence", data,
                   {"run_id": "r", "promoted_at": BEFORE}, "ent-1")
    assert data["cells"][0]["items"][0]["attribution_bound"] is False
    data = _cell()
    computed.apply(_Cur(DRAWER_ROWS), "heatmap", "cell_evidence", data,
                   {"run_id": "r", "promoted_at": AFTER}, "ent-1")
    assert data["cells"][0]["items"][0]["attribution_bound"] is True


# ── the evidence route ─────────────────────────────────────────────────────
def test_the_evidence_route_binds_to_the_run():
    """`fetch` marks each item bound or not for the run it is asked for; the
    customer body then serves only the bound span."""
    cols = evidence._COLUMNS
    assert "customer_attribution_at" in cols
    row = {c: None for c in cols}
    row.update({"e_id": "E-CC-2", "origin": "internal",
                "source_name": "Discovery notes", "excerpt": SPAN,
                "claim_type": "FACT", "tier": "T2",
                "customer_attribution": LABEL, "split_of": "E-CC-1",
                "customer_attribution_at": MINTED})

    class Cur(_Cur):
        def execute(self, sql, params=None):
            super().execute(sql, params)
            self.rows = ([tuple(row[c] for c in cols) + (["P4C1.1.1"],)]
                         if "FROM evidence_index e" in sql else [])

    for promoted, served in ((BEFORE, []), (AFTER, ["E-CC-2"]),
                             (None, [])):
        res = evidence.fetch(Cur([]), "ent-1", ["E-CC-2"], run_id="r",
                             promoted_at=promoted)
        out = redact_evidence_response(res, "customer")
        assert [i["e_id"] for i in out["items"]] == served, promoted
        # the internal reader still sees the label and the mint instant
        assert res["items"][0]["customer_attribution"] == LABEL
        assert res["items"][0]["customer_attribution_at"] == MINTED.isoformat()
