"""Split discovery evidence: the shareable span serves, the internal span
never does (RC-08 / D-10, owner default 2026-10-04).

MEASURED 2026-10-04 on SWBC (gold audit, HM-03, INS-TS-07): all 20 discovery
rows were registered origin='internal' and marked internal_only whole, so the
customer projection held 24 drawers arguing a synthesis over zero items, plus
dangling focus-area, insight and techstack chips. The owner decision is that
the re-attributed client statement in that write-up IS shareable; the seller
and personal remarks are not. The mechanism is a SPLIT at register_evidence
(migration 0063): a shareable span carries `customer_attribution` (the label
a client reads, e.g. "Client statement, discovery conversations, September
2026"), an internal span carries none.

Served here, for the customer audience:
  · an internal-origin item WITH customer_attribution serves, under that
    attribution and never under the internal source name;
  · an internal-origin item without it never serves — not in the drawer, not
    in the evidence route, not as a row of any section, not as a chip;
  · the page builder resolves which cited ids are which in one query per id
    set (`pages.evidence_scope`), entity-scoped.

Fixture rows are SHAPED like the measured ones and carry no client text.
"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api import pages                                         # noqa: E402
from dma_api.redaction import (customer_evidence_items,           # noqa: E402
                               redact_section)

SPAN = ("No single customer profile spans the insurance, mortgage and "
        "wealth lines today.")


def _item(e_id, origin="internal", attribution=None):
    # `attribution_bound` is what the readers stamp when the served run was
    # promoted at or after the span's mint (test_split_span_binding); these
    # fixtures are the bound case.
    return {"e_id": e_id, "origin": origin,
            "source_name": "Internal discovery write-up prepared for a sponsor",
            "source_url": None, "excerpt": SPAN, "claim_type": "FACT",
            "tier": "T2", "linked_subcap_ids": ["P4C1.1.1"],
            "customer_attribution": attribution, "split_of": "E-CC-1",
            "attribution_bound": bool(attribution)}


SHAREABLE = _item("E-CC-2", attribution="Client statement, discovery "
                                        "conversations, September 2026")
INTERNAL_SPAN = _item("E-CC-3")


def test_the_shareable_span_serves_under_its_attribution():
    kept, withheld = customer_evidence_items([SHAREABLE, INTERNAL_SPAN])
    assert [i["e_id"] for i in kept] == ["E-CC-2"]
    assert kept[0]["source_name"].startswith("Client statement")
    for k in ("customer_attribution", "split_of", "origin",
              "attribution_bound"):
        assert k not in kept[0], k
    assert withheld == {"internal_origin": 1}


def test_an_attribution_naming_us_does_not_launder_the_row():
    """The nets run over the attribution like any other string."""
    bad = _item("E-CC-4", attribution="Zennify discovery notes")
    kept, withheld = customer_evidence_items([bad])
    assert kept == [] and withheld == {"vendor_named": 1}


def test_drawer_serves_the_shareable_span_and_keeps_its_chip():
    cell = {"subcap_id": "P4C1.1.1", "synthesis": "In discovery conversations "
            "the client described no single customer profile.",
            "e_ids": ["E-CC-2", "E-CC-3"], "grounded_on": 2, "thin": False,
            "items": [copy.deepcopy(SHAREABLE), copy.deepcopy(INTERNAL_SPAN)]}
    out, _ = redact_section("heatmap", "cell_evidence", {"cells": [cell]}, [],
                            "customer")
    c = out["cells"][0]
    assert c["e_ids"] == ["E-CC-2"]
    assert [i["e_id"] for i in c["items"]] == ["E-CC-2"]
    assert c["grounded_on"] == 1


SCOPE = {"withheld": {"E-CC-3"},
         "attribution": {"E-CC-2": "Client statement, discovery "
                                   "conversations, September 2026"}}


def test_evidence_listing_rows_follow_the_scope():
    body = {"evidence": [
        {"e_id": "E-CC-2", "source_name": "Internal discovery write-up",
         "excerpt": SPAN, "claim_type": "FACT", "url": None},
        {"e_id": "E-CC-3", "source_name": "Internal discovery write-up",
         "excerpt": SPAN, "claim_type": "FACT", "url": None},
        {"e_id": "E-CC-9", "source_name": "Annual report", "excerpt": SPAN,
         "claim_type": "FACT", "url": "https://x.example"}],
        "e_ids": ["E-CC-2", "E-CC-3", "E-CC-9"]}
    out, rep = redact_section("heatmap", "evidence", body, [], "customer",
                              evidence_scope=SCOPE)
    assert [r["e_id"] for r in out["evidence"]] == ["E-CC-2", "E-CC-9"]
    assert out["evidence"][0]["source_name"].startswith("Client statement")
    assert out["e_ids"] == ["E-CC-2", "E-CC-9"]
    assert rep["evidence_scope_withheld"] == 2      # one row + one chip


def test_chips_on_other_sections_drop_the_internal_span():
    body = {"cards": [{"ic_id": "IC-1", "title": "t",
                       "supporting_e_ids": ["E-CC-3", "E-CC-9"]}]}
    out, _ = redact_section("insights", "insights", body, [], "customer",
                            evidence_scope=SCOPE)
    assert out["cards"][0]["supporting_e_ids"] == ["E-CC-9"]


def test_the_internal_audience_ignores_the_scope():
    body = {"evidence": [{"e_id": "E-CC-3", "source_name": "Internal",
                          "excerpt": SPAN}]}
    out, _ = redact_section("heatmap", "evidence", body, [], "internal",
                            evidence_scope=SCOPE)
    assert [r["e_id"] for r in out["evidence"]] == ["E-CC-3"]


class _Cur:
    def __init__(self, rows):
        self.rows, self.sql, self.params = rows, [], []

    def execute(self, sql, params=None):
        self.sql.append(sql)
        self.params.append(params)

    def fetchall(self):
        return self.rows


def test_page_scope_is_one_entity_scoped_query():
    minted = "2026-10-04T15:00:00+00:00"
    cur = _Cur([("E-CC-2", "internal", "Client statement, discovery", minted),
                ("E-CC-3", "internal", None, None),
                ("E-CC-9", "producer", None, None)])
    scope = pages.evidence_scope(cur, "ent-1", {"E-CC-2", "E-CC-3", "E-CC-9"},
                                 promoted_at="2026-10-05T09:00:00+00:00")
    assert scope["withheld"] == {"E-CC-3"}
    assert scope["attribution"] == {"E-CC-2": "Client statement, discovery"}
    joined = " ".join(s for s in cur.sql if "evidence_index" in s)
    assert "entity_id" in joined and "resolve_evidence_id" in joined
    assert sum("evidence_index" in s for s in cur.sql) == 1


def test_no_ids_no_query():
    cur = _Cur([])
    assert pages.evidence_scope(cur, "ent-1", set(),
                                promoted_at=None) == {
        "withheld": set(), "attribution": {}}
    assert cur.sql == []


def test_cited_ids_are_collected_from_every_citation_shape():
    data = {"e_ids": ["E-1"], "rows": [{"e_id": "E-2"},
                                       {"supporting_e_ids": ["E-3"]},
                                       {"evidence_ids": ["E-4"]},
                                       {"nested": {"e_ids": ["E-5"]}}]}
    assert pages.cited_ids(data) == {"E-1", "E-2", "E-3", "E-4", "E-5"}
