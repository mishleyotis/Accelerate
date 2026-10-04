"""A multi-line-of-business entity serves the variant cells of every
sub-vertical it is bound to, and no other's.

SWBC (`swbc`, owner-confirmed 2026-09-30): primary IB (insurance brokers),
SUPPLEMENTARY IC, CL and RIA. Its insurance carrier, commercial lending and
wealth lines are real businesses the assessment researched, so their T2
variant cells are SWBC's own. RB (retail banking) and every other
sub-vertical's variants are not, whatever the workbook measured.

Before 0061 `entities` had one sub-vertical column and `serves()` admitted a
variant only when its code was that one value — so the 66 supplementary
cells would have been hidden as "somebody else's". The rule is unchanged for
every entity with no supplementary binding (NULL, which is every entity but
SWBC today), and an unresolved PRIMARY still keeps everything.
"""
import importlib.util
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api import subverticals                               # noqa: E402
from dma_api.pages import resolve_run                          # noqa: E402
from dma_api.subverticals import (resolve_supplementary,       # noqa: E402
                                  scope_sections, scope_to_entity, serves)
from dma_api.value_chain import read_value_chain               # noqa: E402

SUPP = ("IC", "CL", "RIA")
OWN = ["P1C1.4.IB1", "P1C2.9.IB1"]
SUPPLEMENTARY = ["P1C1.3.IC1", "P1C1.3.CL1", "P2C4.6.RIA1"]
UNBOUND = ["P1C1.3.RB1", "P2C2.7.CU1", "P3C2.1.FC1", "P4C1.2.AM1",
           "P2C1.1.CIB3"]
BASE_AND_FAMILY = ["P1C1.1.1", "P2C3.10.4", "P1C2.7.BK1"]
ALL = OWN + SUPPLEMENTARY + UNBOUND + BASE_AND_FAMILY


# ── reading the column ────────────────────────────────────────────────
@pytest.mark.parametrize("raw", [
    ["IC", "CL", "RIA"], ("IC", "CL", "RIA"), "{IC,CL,RIA}", "IC, CL, RIA",
    ["SV8", "Commercial Lending", "RIA / Broker-Dealer"],
])
def test_every_shape_the_column_arrives_in_resolves_to_codes(raw):
    assert resolve_supplementary(raw, "IB") == SUPP


def test_the_primary_repeats_and_unreadable_entries_are_dropped():
    """An unreadable entry is no evidence that another sub-vertical's cells
    belong to this client, so it widens nothing."""
    assert resolve_supplementary(["IB", "IC", "IC", "nonsuch", "", None],
                                 "IB") == ("IC",)
    assert resolve_supplementary(None, "IB") == ()
    assert resolve_supplementary([], "IB") == ()


# ── the rule ──────────────────────────────────────────────────────────
def test_a_supplementary_variant_serves_and_an_unbound_one_does_not():
    for cell in OWN + SUPPLEMENTARY + BASE_AND_FAMILY:
        assert serves(cell, "IB", SUPP), cell
    for cell in UNBOUND:
        assert not serves(cell, "IB", SUPP), cell


def test_no_binding_is_exactly_the_old_rule():
    for cell in ALL:
        assert serves(cell, "IB") == serves(cell, "IB", ()) == \
            serves(cell, "IB", None)
    assert not serves("P1C1.3.IC1", "IB")


def test_scope_to_entity_serves_primary_plus_supplementary():
    served = scope_to_entity(ALL, "IB", supplementary=["IC", "CL", "RIA"])
    assert served == [c for c in ALL if c not in UNBOUND]
    # order preserved, count computed from what is served (invariant 8)
    assert len(served) == len(ALL) - len(UNBOUND)


def test_an_unresolved_primary_still_keeps_everything():
    """Supplementary codes never turn scoping ON — the primary decides
    whether scoping is in force, as before."""
    for raw in (None, "", "Multi-line conglomerate"):
        assert scope_to_entity(ALL, raw, supplementary=SUPP) == ALL


def test_scope_sections_keeps_supplementary_cells_and_drops_unbound_ones():
    data = {"cells": [{"subcap_id": c} for c in ALL],
            "linked_subcap_ids": list(ALL)}
    dropped = scope_sections("SV7", data, ["IC", "CL", "RIA"])
    assert dropped == 2 * len(UNBOUND)
    assert [c["subcap_id"] for c in data["cells"]] == \
        [c for c in ALL if c not in UNBOUND]
    assert data["linked_subcap_ids"] == [c for c in ALL if c not in UNBOUND]


def test_the_scope_tag_moved_because_the_rule_did():
    """`/subcaps` folds SCOPE_TAG into its ETag; a client holding the
    pre-0061 body (66 cells short) would 304 onto it otherwise."""
    assert subverticals.SCOPE_TAG != "sv-scope@2"


# ── the value chain agrees with the grid ─────────────────────────────
class _VcCur:
    def __init__(self):
        self._out = []

    def execute(self, sql, params=None):
        if "FROM ccg_versions" in sql:
            self._out = [("v7.0",)]
        elif "FROM ccg_value_chains" in sql:
            self._out = [("VC-IB-01", "Placement", 1)]
        elif "FROM ccg_vc_mapping" in sql:
            self._out = [(c, ["Placement"]) for c in ALL]
        elif "FROM serving_subcaps" in sql:
            self._out = [(c,) for c in ALL]
        else:                                            # pragma: no cover
            raise AssertionError(sql)

    def fetchall(self):
        return self._out


def test_the_value_chain_lists_supplementary_cells_too():
    data, empty = read_value_chain(
        _VcCur(), {"sub_vertical": "IB",
                   "supplementary_sub_verticals": list(SUPP)},
        {"run_id": "r", "ccg_catalog_version": "v7.0"})
    assert empty is None
    listed = set(data["chains"][0]["subcaps"])
    assert set(SUPPLEMENTARY) <= listed
    assert not set(UNBOUND) & listed
    assert data["sub_vertical"] == "IB"            # the label is the primary's


# ── the read path threads the binding through ────────────────────────
ENTITY = "53d062c3-e309-4033-9438-297b2b8505aa"
RUN = "7968492e-ba03-47fd-93c3-93f5867f1d43"


def _dir_row(legal="Southwest Business Corporation", trading="SWBC",
             supp=("IC", "CL", "RIA")):
    """resolve_run's twenty-three columns, 0061's two appended."""
    return (ENTITY, "swbc", legal, "IB", None, RUN, "DMA-SWBC-1", 2, True,
            "PROMOTED", 2.01, 760, 851, "v7.0",
            datetime(2026, 9, 30, tzinfo=timezone.utc),
            datetime(2026, 10, 1, tzinfo=timezone.utc),
            date(2026, 9, 30), "STATED", "manifest.completed_at",
            date(2027, 3, 30), "swbc.com", trading,
            list(supp) if supp is not None else None)


class _DirCur:
    def __init__(self, row, cells=()):
        self.row, self.cells, self._out = row, list(cells), []
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append(sql)
        if "FROM serving_directory" in sql:
            self._out = [self.row]
        elif "FROM serving_subcaps" in sql:
            self._out = list(self.cells)
        else:
            self._out = []

    def fetchall(self):
        return self._out

    def fetchone(self):
        return self._out[0] if self._out else None

    def cursor(self):
        return self

    def close(self):
        pass


def test_resolve_run_carries_the_binding_and_the_trading_name():
    _eid, entity, _run, _p = resolve_run(_DirCur(_dir_row()), "swbc", None,
                                         False)
    assert entity["supplementary_sub_verticals"] == ["IC", "CL", "RIA"]
    assert entity["trading_name"] == "SWBC"
    assert entity["sub_vertical"] == "IB"


def test_resolve_run_with_no_binding_carries_an_empty_list():
    _eid, entity, _run, _p = resolve_run(
        _DirCur(_dir_row(legal=None, trading=None, supp=None)), "swbc", None,
        False)
    assert entity["supplementary_sub_verticals"] == []
    assert entity["entity_name"] is None and entity["trading_name"] is None


def test_the_subcaps_route_serves_supplementary_variants(monkeypatch):
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from dma_api import main

    cols = main._SUBCAP_COLS
    cells = []
    for c in ALL:
        row = dict.fromkeys(cols)
        row.update(subcap_id=c, score=2.5)
        cells.append(tuple(row[k] for k in cols))
    conn = _DirCur(_dir_row(), cells)
    monkeypatch.setattr(main, "_connect", lambda: conn)
    body = TestClient(main.app).get(
        "/v1/entities/swbc/subcaps?audience=internal").json()
    served = [r["subcap_id"] for r in body["subcaps"]]
    assert served == [c for c in ALL if c not in UNBOUND]
    assert body["count"] == len(served)


# ── migration 0061 ────────────────────────────────────────────────────
MIGRATIONS = ROOT / "migrations" / "versions"


def _load(name):
    path = next(MIGRATIONS.glob(f"{name}_*.py"))
    spec = importlib.util.spec_from_file_location(f"_m{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, path.read_text()


def test_0061_follows_0060_and_its_downgrade_is_0060s_view_exactly():
    m61, _ = _load("0061")
    m60, _ = _load("0060")
    assert m61.down_revision == "0060"
    assert m61._PRE_0061 == m60._VIEW_BODY, \
        "downgrade must rebuild 0060's view byte for byte"
    for col in ("e.trading_name", "e.supplementary_sub_verticals"):
        assert col in m61._VIEW_BODY and col not in m61._PRE_0061


def test_0061_checks_the_same_vocabulary_the_rule_uses():
    m61, _ = _load("0061")
    assert tuple(m61.SUBVERTICAL_CODES) == tuple(subverticals.SUBVERTICAL_CODES)


def test_0061_rebuild_carries_every_grant():
    _, src = _load("0061")
    assert "GRANT SELECT ON serving_directory TO svc_api" in src
    assert "TO svc_mcp" in src and "TO svc_worker" in src


def _db():
    import pg8000.dbapi
    dsn = os.environ.get("LOCAL_DATABASE_URL", "")
    host = dsn.split("@")[1].split(":")[0] if "@" in dsn else "localhost"
    try:
        return pg8000.dbapi.connect(user="postgres", password="local",
                                    host=host, port=5432,
                                    database="dma_insights")
    except Exception:
        pytest.skip("no migrated local database")


def test_the_live_column_refuses_a_code_outside_the_vocabulary():
    conn = _db()
    cur = conn.cursor()
    try:
        cur.execute("""SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'entities'
                          AND column_name = 'supplementary_sub_verticals'""")
        if cur.fetchone() is None:
            pytest.skip("database not migrated to 0061")
        cur.execute("INSERT INTO entities (display_id, "
                    "supplementary_sub_verticals) VALUES "
                    "('t-0061-ok', ARRAY['IC','RIA'])")
        with pytest.raises(Exception, match="entities_supplementary_sv_known"):
            cur.execute("INSERT INTO entities (display_id, "
                        "supplementary_sub_verticals) VALUES "
                        "('t-0061-bad', ARRAY['IC','XX'])")
    finally:
        conn.rollback()
        conn.close()
