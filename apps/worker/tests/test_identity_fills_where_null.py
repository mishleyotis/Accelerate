"""A package for an entity already on file fills its EMPTY identity, and
never overwrites a value that is set.

SWBC's entity row was created by a package that carried no identity, and
`persist_package` wrote identity only on INSERT — so every later package
that did state the legal name and sub-vertical changed nothing, and the
entity promoted with an empty record. Synthetic entity, no client data.
"""
import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_worker import persist                                   # noqa: E402
from dma_worker.persist import (_institution, _supplementary_codes,  # noqa: E402
                                fill_identity, persist_package)
from dma_worker.workbook_parser import ParsedScore, WorkbookParse  # noqa: E402

DSN = os.environ.get("LOCAL_DATABASE_URL",
                     "postgresql://postgres:local@localhost:5432/dma_insights")
HOST = DSN.split("@")[1].split(":")[0] if "@" in DSN else "localhost"
DISPLAY = "synthetic-identity-fill"


# ── pure: the manifest reading ───────────────────────────────────────
def test_the_binding_and_the_trading_identity_are_read():
    inst = _institution({
        "institution": {"name": "Synthetic Identity Fill",
                        "sub_vertical": "IB"},
        "entity": {"trading_name": "SIF", "domain": "sif.example"},
        "binding": {"supplementary_sub_verticals": ["IC", "CL", "RIA"]},
    })
    assert inst["trading_name"] == "SIF" and inst["domain"] == "sif.example"
    assert inst["supplementary_sub_verticals"] == ["IC", "CL", "RIA"]


def test_supplementary_codes_keep_only_the_vocabulary():
    assert _supplementary_codes("IC, cl,RIA", "IB") == ["IC", "CL", "RIA"]
    assert _supplementary_codes(["SV8", "IB", "IC", "XX"], "IB") == ["IC"]
    assert _supplementary_codes(["IB"], "SV7") is None
    assert _supplementary_codes(None) is None


class _Cur:
    """Records the UPDATE fill_identity issues against a stated row."""

    def __init__(self, row):
        self.row, self.sql, self.params = row, [], []

    def execute(self, sql, params=None):
        self.sql.append(sql)
        self.params.append(params)

    def fetchone(self):
        return self.row


def test_only_null_columns_are_filled():
    current = dict.fromkeys(persist._IDENTITY_COLUMNS)
    current["legal_name"] = "Already Set Ltd"
    cur = _Cur(tuple(current[c] for c in persist._IDENTITY_COLUMNS))
    filled = fill_identity(cur, "e", {"name": "Package Name",
                                      "sub_vertical": "IB",
                                      "trading_name": "PN"})
    assert filled == ["sub_vertical", "trading_name"]
    update = cur.sql[-1]
    assert "legal_name" not in update
    assert "COALESCE(sub_vertical, %s)" in update


def test_nothing_stated_or_nothing_empty_writes_nothing():
    full = tuple("x" for _ in persist._IDENTITY_COLUMNS)
    cur = _Cur(full)
    assert fill_identity(cur, "e", {"name": "N", "sub_vertical": "IB"}) == []
    assert not any(s.startswith("UPDATE") for s in cur.sql)
    cur = _Cur(full)
    assert fill_identity(cur, "e", {}) == []
    assert cur.sql == []


# ── live: through persist_package against the real schema ───────────
def _connect(user):
    import pg8000.dbapi
    return pg8000.dbapi.connect(user=user, password="local", host=HOST,
                                port=5432, database="dma_insights")


@pytest.fixture()
def conns():
    try:
        worker = _connect("dmai-worker@digital-maturity-assessor.iam")
        admin = _connect("dmai-migrate@digital-maturity-assessor.iam")
        cur = admin.cursor()
        cur.execute("SELECT 1 FROM information_schema.columns WHERE "
                    "table_name='entities' AND "
                    "column_name='supplementary_sub_verticals'")
        if cur.fetchone() is None:
            pytest.skip("database not migrated to 0061")
    except pytest.skip.Exception:
        raise
    except Exception:
        pytest.skip("no migrated local database")

    def clean():
        c = admin.cursor()
        c.execute("SELECT id FROM entities WHERE display_id = %s", (DISPLAY,))
        for (eid,) in c.fetchall():
            for t in ("evidence_subcap_links", "parser_observations",
                      "subcap_scores", "peer_scores", "recommendations_raw",
                      "run_manifest"):
                c.execute(f"DELETE FROM {t} WHERE run_id IN "
                          "(SELECT id FROM runs WHERE entity_id = %s)", (eid,))
            c.execute("DELETE FROM runs WHERE entity_id = %s", (eid,))
            c.execute("DELETE FROM evidence_index WHERE entity_id = %s", (eid,))
            c.execute("DELETE FROM entities WHERE id = %s", (eid,))
        admin.commit()

    clean()
    yield worker, admin
    worker.rollback()
    clean()
    worker.close()
    admin.close()


def _workbook():
    s = ParsedScore(subcap_id="P1C1.1.1", pillar_id="P1", category_id="P1C1",
                    capability_id="P1C1.1", name=None, tier=None,
                    score=Decimal("2.4"), source_cell="P1_Subcap_Scoring!D2",
                    evidence_quality=None, confidence="HIGH",
                    evidence_refs=[])
    return WorkbookParse(scores=[s], observations=[], toggled_out=[],
                         scored_cells=1, composite=None)


def test_a_later_package_fills_the_empty_record_and_overwrites_nothing(conns):
    worker, admin = conns
    a = admin.cursor()
    # The entity exists with nothing but a display id and one set value —
    # SWBC's shape, plus a human correction that must survive.
    a.execute("INSERT INTO entities (display_id, size_tier) "
              "VALUES (%s, 'large')", (DISPLAY,))
    admin.commit()
    manifest = {
        "run_id": "DMA-ASM-SIF-20260930-01",
        "institution": {"name": "Synthetic Identity Fill",
                        "sub_vertical": "IB", "size_tier": "mid-size"},
        "entity": {"trading_name": "SIF", "domain": "sif.example"},
        "binding": {"supplementary_sub_verticals": ["IC", "CL", "RIA"]},
        "versions": {"taxonomy": "v7.0"},
    }
    res = persist_package(worker, manifest=manifest, workbook=_workbook(),
                          source_folder_id="synthetic")
    worker.commit()
    a.execute("""SELECT legal_name, trading_name, domain, sub_vertical,
                        supplementary_sub_verticals, size_tier
                   FROM entities WHERE display_id = %s""", (DISPLAY,))
    assert list(a.fetchone()) == ["Synthetic Identity Fill", "SIF",
                                  "sif.example", "IB", ["IC", "CL", "RIA"],
                                  "large"]
    a.execute("""SELECT detail FROM parser_observations
                  WHERE run_id = %s AND kind = 'entity_identity_filled'""",
              (res.run_id,))
    (detail,) = a.fetchone()
    assert "legal_name" in detail["columns"]
    assert "size_tier" not in detail["columns"]
