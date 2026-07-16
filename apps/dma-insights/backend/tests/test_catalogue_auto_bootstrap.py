"""Tests for the catalogue auto-bootstrap path in package_persist.

Operator mandate (2026-06): "No v5 catalogue will be uploaded. Just use
the scoring toolkits that are there during the backfill. No error
message." When a package references a catalogue version that hasn't
been loaded via `ccg_loader`, `_bootstrap_catalogue_from_workbook`
seeds the four-tier FK chain (pillars → categories → l1 → subcaps)
from the workbook's own taxonomy so the resolver returns
`ResolvedSubcap` on the first pass.

Part 12.4 (2026-07) batching contract: the four per-row upsert loops
collapsed into one executemany per parent level + ONE
jsonb_to_recordset INSERT for ccg_subcaps (single statement so
`rowcount` still reports rows actually inserted). The FakeSession
handles list params (executemany) and unpacks the subcap rows from the
:rows JSONB payload.

Coverage:
  - happy_path           — every parent FK + subcap row written, count
                            returned matches subcap_specs len.
  - idempotent_re_run    — re-invoking with same IDs writes zero new
                            ccg_subcaps rows (ON CONFLICT DO NOTHING →
                            rowcount 0).
  - malformed_id_skipped — non-conforming IDs are skipped silently
                            (no fabricated rows from a bad ID).
  - empty_input          — empty set returns 0 with no SQL writes.
  - rationale_truncated  — long rationales clamp to 512 chars so the
                            ccg_subcaps.description column stays sane.
"""
from __future__ import annotations

import json


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Result:
    def __init__(self, rowcount: int = 1, rows: list[_Row] | None = None):
        self.rowcount = rowcount
        self._rows = rows or []

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class FakeSession:
    """Records each (sql_text, params) execute call.

    Handles BOTH single-dict params and executemany LISTS of dicts
    (the Part-12.4 batched flushes).
    """

    def __init__(self, *, inserted_rowcount: int | None = None):
        self.calls: list[tuple[str, object]] = []
        # For the single jsonb_to_recordset ccg_subcaps INSERT, the DB
        # reports how many rows were ACTUALLY inserted. None → every
        # submitted row inserts (fresh catalogue); 0 → every row
        # conflicts (idempotent re-run).
        self._inserted_rowcount = inserted_rowcount

    async def execute(self, sql, params=None):
        sql_text = str(sql)
        if isinstance(params, list):
            self.calls.append((sql_text, [dict(p) for p in params]))
            return _Result(rowcount=len(params))
        self.calls.append((sql_text, dict(params or {})))
        if "INSERT INTO ccg_subcaps" in sql_text:
            submitted = len(json.loads((params or {}).get("rows", "[]")))
            rc = submitted if self._inserted_rowcount is None \
                else self._inserted_rowcount
            return _Result(rowcount=rc)
        return _Result(rowcount=1)


class _PillarScore:
    def __init__(self, pillar_id: str, pillar_name: str | None = None):
        self.pillar_id = pillar_id
        self.pillar_name = pillar_name


class _CategoryScore:
    def __init__(self, category_id: str, pillar_id: str,
                 category_name: str | None = None):
        self.category_id = category_id
        self.pillar_id = pillar_id
        self.category_name = category_name


class _SubcapScore:
    def __init__(self, subcap_id: str, rationale: str | None = None):
        self.subcap_id = subcap_id
        self.rationale = rationale


class _Pkg:
    def __init__(self, *, pillars=None, categories=None, subcaps=None):
        self.pillar_scores = pillars or []
        self.category_scores = categories or []
        self.subcap_scores = subcaps or []


def _calls_matching(session: FakeSession, fragment: str) -> list[dict]:
    """Flatten executemany lists so assertions see one dict per row."""
    out: list[dict] = []
    for s, p in session.calls:
        if fragment not in s:
            continue
        if isinstance(p, list):
            out.extend(p)
        else:
            out.append(p)
    return out


def _subcap_rows(session: FakeSession) -> list[dict]:
    """The ccg_subcaps rows ride ONE statement as a :rows JSONB payload."""
    out: list[dict] = []
    for p in _calls_matching(session, "INSERT INTO ccg_subcaps"):
        out.extend(json.loads(p["rows"]))
    return out


def _run(coro):
    import asyncio
    return asyncio.run(coro)


from app.services.parsers.package_persist import (  # noqa: E402
    _bootstrap_catalogue_from_workbook,
    _category_from_subcap,
    _l1_from_subcap,
    _pillar_from_subcap,
)


def test_pillar_extractor():
    assert _pillar_from_subcap("P1C1.1.1") == "P1"
    assert _pillar_from_subcap("P4C9.3.2") == "P4"
    assert _pillar_from_subcap("NOT_A_SUBCAP") is None


def test_category_extractor():
    assert _category_from_subcap("P1C1.1.1") == "P1C1"
    assert _category_from_subcap("P2C3.2.4:T2") == "P2C3"
    assert _category_from_subcap("P9C9") is None  # outside 1..4


def test_l1_extractor_strips_tier_suffix():
    assert _l1_from_subcap("P1C1.1.1") == "P1C1.1"
    assert _l1_from_subcap("P2C3.2.4:T2") == "P2C3.2"
    assert _l1_from_subcap("P3C2.5.7T1") == "P3C2.5"


def test_happy_path_writes_full_fk_chain():
    """Every pillar/category/l1/subcap referenced gets seeded."""
    pkg = _Pkg(
        pillars=[_PillarScore("P1", "Strategy"),
                 _PillarScore("P2", "Customer Engagement")],
        categories=[
            _CategoryScore("P1C1", "P1", "Strategic Posture"),
            _CategoryScore("P2C1", "P2", "Channels"),
        ],
        subcaps=[
            _SubcapScore("P1C1.1.1", rationale="strategy clarity"),
            _SubcapScore("P1C1.1.2", rationale="board alignment"),
            _SubcapScore("P2C1.1.1", rationale="channel breadth"),
        ],
    )
    session = FakeSession()
    inserted = _run(_bootstrap_catalogue_from_workbook(
        session,
        catalog_version="v5.5",
        parsed_subcap_ids={"P1C1.1.1", "P1C1.1.2", "P2C1.1.1"},
        pkg=pkg,
        warnings=[],
    ))
    assert inserted == 3

    pillar_inserts = _calls_matching(session, "INSERT INTO ccg_pillars")
    assert len(pillar_inserts) == 2
    pillar_ids = {p["pid"] for p in pillar_inserts}
    assert pillar_ids == {"P1", "P2"}
    pillar_names = {p["pid"]: p["n"] for p in pillar_inserts}
    assert pillar_names["P1"] == "Strategy"
    assert pillar_names["P2"] == "Customer Engagement"

    cat_inserts = _calls_matching(session, "INSERT INTO ccg_categories")
    assert len(cat_inserts) == 2
    cat_ids = {p["cid"] for p in cat_inserts}
    assert cat_ids == {"P1C1", "P2C1"}

    l1_inserts = _calls_matching(session, "INSERT INTO ccg_l1_capabilities")
    assert len(l1_inserts) == 2
    l1_ids = {p["lid"] for p in l1_inserts}
    assert l1_ids == {"P1C1.1", "P2C1.1"}

    sc_rows = _subcap_rows(session)
    assert len(sc_rows) == 3
    sc_ids = {p["sid"] for p in sc_rows}
    assert sc_ids == {"P1C1.1.1", "P1C1.1.2", "P2C1.1.1"}


def test_idempotent_re_run_returns_zero():
    """Second pass with same IDs writes no new ccg_subcaps rows."""
    pkg = _Pkg(
        pillars=[_PillarScore("P1", "Strategy")],
        categories=[_CategoryScore("P1C1", "P1", "Strategic Posture")],
        subcaps=[_SubcapScore("P1C1.1.1", rationale="seeded")],
    )
    # inserted_rowcount=0 → the DB reports every row ON CONFLICT'd.
    session = FakeSession(inserted_rowcount=0)
    inserted = _run(_bootstrap_catalogue_from_workbook(
        session,
        catalog_version="v5.5",
        parsed_subcap_ids={"P1C1.1.1"},
        pkg=pkg,
        warnings=[],
    ))
    assert inserted == 0


def test_malformed_id_skipped_silently():
    """Non-conforming subcap IDs are dropped — never fabricated."""
    pkg = _Pkg(
        pillars=[],
        categories=[],
        subcaps=[_SubcapScore("BAD_ID_FORMAT", rationale="garbage")],
    )
    session = FakeSession()
    inserted = _run(_bootstrap_catalogue_from_workbook(
        session,
        catalog_version="v5.5",
        parsed_subcap_ids={"BAD_ID_FORMAT", "ALSO_BAD"},
        pkg=pkg,
        warnings=[],
    ))
    assert inserted == 0
    # No SQL writes at all when every ID is malformed.
    assert not _calls_matching(session, "INSERT INTO ccg_subcaps")
    assert not _calls_matching(session, "INSERT INTO ccg_pillars")


def test_empty_input_returns_zero():
    session = FakeSession()
    inserted = _run(_bootstrap_catalogue_from_workbook(
        session,
        catalog_version="v5.5",
        parsed_subcap_ids=set(),
        pkg=_Pkg(),
        warnings=[],
    ))
    assert inserted == 0
    assert session.calls == []


def test_long_rationale_truncated_to_512_chars():
    """Description column gets a hard 512-char cap (plus ellipsis)."""
    long_rat = "x" * 1000
    pkg = _Pkg(
        pillars=[_PillarScore("P1", "Strategy")],
        categories=[_CategoryScore("P1C1", "P1")],
        subcaps=[_SubcapScore("P1C1.1.1", rationale=long_rat)],
    )
    session = FakeSession()
    _run(_bootstrap_catalogue_from_workbook(
        session,
        catalog_version="v5.5",
        parsed_subcap_ids={"P1C1.1.1"},
        pkg=pkg,
        warnings=[],
    ))
    sc_rows = _subcap_rows(session)
    assert len(sc_rows) == 1
    desc = sc_rows[0]["d"]
    assert desc.endswith("…")
    assert len(desc) <= 520  # 512 + ellipsis + a few chars of slack


def test_pillar_falls_back_to_canonical_name():
    """Missing pillar_name in pkg falls back to canonical pillar map."""
    pkg = _Pkg(
        pillars=[],  # no pillar_scores supplied
        categories=[],
        subcaps=[_SubcapScore("P3C2.1.1")],
    )
    session = FakeSession()
    _run(_bootstrap_catalogue_from_workbook(
        session,
        catalog_version="v5.5",
        parsed_subcap_ids={"P3C2.1.1"},
        pkg=pkg,
        warnings=[],
    ))
    pillar_inserts = _calls_matching(session, "INSERT INTO ccg_pillars")
    assert len(pillar_inserts) == 1
    assert pillar_inserts[0]["pid"] == "P3"
    # The canonical name dict supplies the friendly name even without
    # package-level pillar_scores.
    assert "Operational" in pillar_inserts[0]["n"]
