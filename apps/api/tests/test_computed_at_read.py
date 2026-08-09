"""The eleven contract fields declared COMPUTED and computed nowhere.

`build_page` read columns and returned. Every field below has no serving
column on purpose — invariant 8 says a count with a source of truth is
computed, never stored — and the read path computed none of them, so all
eleven served as absent. Absent on a client surface reads as "the producer
left it empty", which is why the whole O11 evidence-mix panel was diagnosed
as a synthesis gap for two clients running when it was an app gap.

Negative control for the whole file: `dma_api.computed` did not exist. Every
assertion here fails by ImportError against the pre-fix tree, and each
individual field assertion fails against a `build_page` that skips the
`computed_apply` call — which is the state that shipped.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_api import computed


def test_a_share_of_nothing_is_null_not_zero():
    """Invariant 9: derived values are computed or null, never a sentinel
    and never a default that looks like data. 0% undated on a panel with no
    fields is a claim about nothing that renders as a fact."""
    assert computed._pct(0, 0) is None
    assert computed._pct(3, 0) is None
    assert computed._pct(1, 4) == 25.0


def test_a_computed_field_never_silently_replaces_a_producer_figure():
    """Where the producer sent a number the contract calls computed, the
    computed one serves and theirs is kept beside it. If they disagree that
    disagreement is a finding, and dropping one of the two is how it stops
    being one."""
    data = {"undated_pct": 12.0, "fields": [{"as_of": "2026-01-01"},
                                            {"as_of": None},
                                            {"as_of": None},
                                            {"as_of": None}]}
    computed.firmographics(data)
    assert data["undated_pct"] == 75.0
    assert data["undated_pct_stated"] == 12.0

    agree = {"undated_pct": 75.0, "fields": data["fields"]}
    computed.firmographics(agree)
    assert "undated_pct_stated" not in agree, "agreement is not a disagreement"


def test_firmographics_undated_share():
    data = {"fields": [{"field": "aum", "as_of": "2026-03-31"},
                       {"field": "headcount", "as_of": None}]}
    computed.firmographics(data)
    assert data["undated_pct"] == 50.0

    empty = {"fields": []}
    computed.firmographics(empty)
    assert "undated_pct" not in empty, "0% of no fields is not a measurement"


def test_cell_linking_stats_reports_citable_beside_linked():
    """The coverage card said those cells could not be opened; the grid, on
    the same run, rendered them as evidenced. A cell can be LINKED to rows
    that carry no excerpt, and such a row cannot be opened, cited or read.
    Both numbers now serve, so the disclosure is on the surface rather than
    in the difference between two surfaces.

    Thinness itself is deliberately NOT redefined: recomputing it from
    citable rows alone refuses 573 of 706 cells on the reference client,
    and a flag that fires on 81% of a clean run is not a flag."""
    data = {"cells": [
        {"subcap_id": "P1C1.1.1", "e_ids": ["E-1"],
         "items": [{"e_id": "E-1", "excerpt": "x" * 60}]},
        # linked, and every linked row is excerpt-less: openable nowhere
        {"subcap_id": "P1C1.1.2", "e_ids": ["E-2"],
         "items": [{"e_id": "E-2", "excerpt": ""}]},
        {"subcap_id": "P1C1.1.3", "e_ids": [], "items": []},
    ]}
    computed.cell_linking_stats(data)
    assert data["linking_stats"] == {
        "cells_scored": 3, "cells_linked": 2,
        "cells_citable": 1, "rows_unlinkable": 1}


def test_evidence_age_rollups():
    data = {"rows": [
        {"band": "current", "published_or_asof": "2026-01-01"},
        {"band": "stale", "published_or_asof": "2022-01-01"},
        {"band": "archival", "published_or_asof": "2019-01-01"},
        {"band": "undated", "published_or_asof": None},
    ]}
    computed.evidence_age_rollups(data)
    assert data["stale_pct"] == 50.0        # stale + archival
    assert data["undated_pct"] == 25.0


def test_landscape_recomputes_from_the_register_and_says_whether_it_reconciles():
    """Invariant 8, verbatim: the T2 landscape recomputes from the T1
    register. The boolean is the assertion, not a fifth count — two code
    paths producing two numbers is what it exists to make visible."""
    class Cur:
        def execute(self, *_a, **_k):
            pass

        def fetchall(self):
            return [("CONFIRMED", "Anypoint", "MuleSoft", "L1"),
                    ("CONFIRMED", "Service Cloud", "Salesforce", "L2"),
                    ("INFERRED", "Snowflake", None, "L3"),
                    ("CLAIMED", "Data Cloud", "Salesforce", "L4"),
                    ("ABSENT", "Customer data platform", None, None)]

    data = {}
    computed.landscape(Cur(), data, "run")
    tiles = {t["kind"]: t for t in data["tiles"]}
    assert [t["count"] for t in data["tiles"]] == [2, 1, 1, 1]
    assert data["reconciles_to_register"] is True
    # The basis is PRINTED — a bare count invites certainty.
    assert tiles["CONFIRMED"]["basis"] == "2 · L1–L2 evidence"
    assert tiles["GAPS"]["named_items"] == ["Customer data platform"]
    assert tiles["CONFIRMED"]["named_items"] == [], \
        "the register lists what is present; the tile names what is absent"


def test_the_gaps_tile_does_not_say_the_vendor_name_twice():
    """`Salesforce Salesforce Data Cloud`, `Salesforce Salesforce CRM
    Analytics`, `MuleSoft MuleSoft Anypoint Platform` — three strings on the
    live customer-facing D2 GAPS tile, from this module's own blind
    `f"{vendor} {name}"`. The register stores vendor and product separately
    and a producer may put the vendor in either field or both.

    Negative control: the pre-fix expression is `"Salesforce Salesforce Data
    Cloud"` for row one, so this fails against it, and the second assertion
    fails against the naive fix of always dropping the vendor."""
    class Cur:
        def execute(self, *_a, **_k):
            pass

        def fetchall(self):
            return [("ABSENT", "Salesforce Data Cloud", "Salesforce", None),
                    ("ABSENT", "Anypoint Platform", "MuleSoft", None),
                    ("ABSENT", "Customer data platform", None, None),
                    ("ABSENT", None, "Snowflake", None)]

    data = {}
    computed.landscape(Cur(), data, "run")
    named = {t["kind"]: t for t in data["tiles"]}["GAPS"]["named_items"]
    assert named == ["Salesforce Data Cloud", "MuleSoft Anypoint Platform",
                     "Customer data platform", "Snowflake"]


def test_techstack_layers_expected_comes_from_outside_the_register():
    """The frontend computed this rollup from `items` with `expected` set to
    the rows the producer wrote, which is circular: on one client it rendered
    '11 of 12, 92% covered' over a register whose own empty_state said it was
    narrower than the estate, on a page whose narrative_thread called the
    data layer the primary gap. `expected` is now the catalogue's platform
    coverage — a number the register cannot move — or null."""
    class Cur:
        def __init__(self):
            self.n = 0

        def execute(self, *_a, **_k):
            self.n += 1

        def fetchall(self):
            if self.n == 1:
                return [("OPS", "CONFIRMED", False), ("OPS", "ABSENT", False),
                        ("CUST", "INFERRED", True), ("DATA", "CLAIMED", False)]
            return [("P2", 40), ("P3", 55), ("P4", 60)]

    data = {}
    computed.techstack_layers(Cur(), data, "run", "v7.0")
    by = {l["layer"]: l for l in data["layers"]}
    assert [l["layer"] for l in data["layers"]] == ["OPS", "CUST", "DATA", "INFRA"]
    assert by["OPS"]["detected"] == 1 and by["OPS"]["expected"] == 55
    assert by["CUST"]["is_primary_gap"] is True
    # CLAIMED is not detection: the four statuses are CONFIRMED · INFERRED ·
    # CLAIMED · ABSENT and only the first two are evidence of a deployment.
    assert by["DATA"]["detected"] == 0
    # DATA and INFRA both absorb P4, so neither may claim the pillar's count
    # as its own denominator — "6 of 187" and "11 of 187" printed over one
    # 187 is a bigger lie than no denominator. Null, with the reason stated.
    assert by["DATA"]["expected"] is None and by["INFRA"]["expected"] is None
    assert "shared by more than one layer" in by["INFRA"]["expected_basis"]
    assert "v7.0" in by["OPS"]["expected_basis"]


def test_techstack_layers_expected_is_null_when_the_catalogue_says_nothing():
    class Cur:
        def __init__(self):
            self.n = 0

        def execute(self, *_a, **_k):
            self.n += 1

        def fetchall(self):
            return [("OPS", "CONFIRMED", False)] if self.n == 1 else []

    data = {}
    computed.techstack_layers(Cur(), data, "run", "v7.0")
    assert all(l["expected"] is None for l in data["layers"]), \
        "an expected count of 0 renders every layer as fully covered"


def test_safeguard_gates_are_joined_from_gate_results_with_their_plain_label():
    """Invariant 12: a failing SG discloses and still promotes. Nothing
    joined `gate_results`, so the card was empty on every client and a
    failing gate disclosed nothing at all."""
    class Cur:
        def execute(self, *_a, **_k):
            pass

        def fetchall(self):
            return [("SG-01", "No client is named in another client's report",
                     "PASS", "0 of 706 cells", None),
                    ("SG-04", "Every quoted figure resolves to one workbook row",
                     "NOT_RUN", None, None)]

    data = {}
    computed.safeguard_gates(Cur(), data, "run")
    assert data["gates"][0]["result"] == "PASS"
    # A gate reporting PASS because it did not run is worse than one
    # reporting FAIL, so a NOT_RUN with no reason says so rather than blank.
    assert data["gates"][1]["not_run_reason"] == \
        "recorded NOT_RUN with no reason given"


def test_no_evidence_linked_to_the_run_is_a_finding_not_a_zero():
    class Cur:
        def execute(self, *_a, **_k):
            pass

        def fetchall(self):
            return []

    data = {}
    computed.evidence_coverage(Cur(), data, "run", "entity")
    assert data["item_count"] == 0 and data["fact_count"] == 0
    assert "empty_reason" in data, \
        "0 items with no reason reads as a producer who found nothing"


class _CoverageCur:
    """The two statements evidence_coverage runs, in order: the census, then
    the entity's own `origin = 'internal'` domains."""

    def __init__(self, census, internal=()):
        self.census, self.internal, self._out = census, internal, []

    def execute(self, sql, params=None):
        self._out = ([(d,) for d in self.internal] if "origin = 'internal'" in sql
                     else self.census)

    def fetchall(self):
        return self._out


def test_the_self_sourced_share_measures_against_the_entitys_declared_domain():
    """The share of evidence the entity published about ITSELF, which needs
    the entity's own domain — and the previous version could only get it
    from rows carrying `origin = 'internal'`.

    Negative control, measured on production 2026-08-09:
    `evidence_origin_t` HAS an `internal` label and no row in the corpus has
    ever carried one (25,385 package, 152 producer, 0 internal). So without
    the declared column this returns an empty set for every client, the
    numerator is always 0, and `self_sourced_pct` has never rendered for
    anyone. Drop `entity_domain` here and the first assertion fails."""
    census = [("T1", "FACT", "bcu.org", 4),
              ("T3", "FACT", "creditunions.com", 2),
              ("T3", "FACT", "ncua.gov", 1),
              ("T1", "FACT", "www.bcu.org", 3)]

    data = {}
    computed.evidence_coverage(_CoverageCur(census), data, "run", "entity",
                               "https://WWW.BCU.org/")
    assert data["self_sourced_pct"] == 50.0, "2 of 4 items are the entity's own"
    assert "bcu.org" in data["self_sourced_basis"]

    # The old route still works where a run actually marks its own rows.
    other = {}
    computed.evidence_coverage(_CoverageCur(census, internal=("bcu.org",)),
                               other, "run", "entity", None)
    assert other["self_sourced_pct"] == 50.0


def test_an_uncomputable_share_says_so_instead_of_vanishing():
    """An absent field reads as "the producer left it empty" — the exact
    misreading this module exists to end. `entities.domain` is NULL on all
    166 rows and nothing writes it, so this is what every client gets
    today, and it now names what would close it."""
    census = [("T3", "FACT", "ncua.gov", 1)]
    data = {}
    computed.evidence_coverage(_CoverageCur(census), data, "run", "entity", None)
    assert "self_sourced_pct" not in data, "a share of an unknown is not 0%"
    assert "publication domain" in data["self_sourced_basis"]
    assert "ingest" in data["self_sourced_basis"], "names what closes it"


def test_a_failed_computation_names_itself_rather_than_taking_the_page_down():
    """The fields are additive. A page that renders without its census is
    worse than one that renders with it and better than one that 500s — but
    a swallowed failure is how an app gap gets diagnosed as a producer gap,
    so the section says which computation broke."""
    class Boom:
        def execute(self, *_a, **_k):
            raise RuntimeError("permission denied for table gate_results")

    data = {}
    computed.apply(Boom(), "heatmap", "safeguard_gates", data,
                   {"run_id": "r"}, "e")
    assert data["computed_error"] == "heatmap.safeguard_gates: RuntimeError"


def test_every_computed_at_read_field_has_a_function_that_writes_it():
    """The list in test_serving_read_path's field census is the contract's
    own record of which required fields have no column. Each entry there is
    an assertion that something else computes it; this is the something
    else, checked by name so the two lists cannot drift apart silently."""
    covered = {
        ("overview", "firmographics"): ("undated_pct",),
        ("overview", "evidence_coverage"): ("item_count", "fact_count",
                                            "tiers", "claim_classes",
                                            "self_sourced_pct"),
        ("insights", "landscape"): ("tiles", "reconciles_to_register"),
        ("techstack", "techstack"): ("layers",),
        ("heatmap", "cell_evidence"): ("linking_stats",),
        ("heatmap", "evidence_age"): ("stale_pct", "undated_pct"),
        ("heatmap", "safeguard_gates"): ("gates",),
    }
    assert sum(len(v) for v in covered.values()) == 13
    src = (Path(__file__).resolve().parents[1] / "dma_api" / "computed.py").read_text()
    for (page, section), fields in covered.items():
        for f in fields:
            assert f'"{f}"' in src, f"{page}.{section}.{f} is computed by nothing"
