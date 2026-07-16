"""Unit tests for the promoted tech evidence/subcap linker (D1.3).

The linker + catalogue platform-tagger were promoted out of the
post-ingest scripts (`clean_techstack.py`, `apply_catalogue_platforms.py`)
into `persist_package` so `tech_stack_entries.evidence_e_ids` +
`linked_subcap_ids` — and `subcap_scores.platform_tags`, which feeds the
D4 platform-fit scorer — populate AT INGEST instead of ~94%/81%/all
empty across the corpus.

Pure mapping logic is tested directly; the three DB helpers are tested
against an in-memory FakeSession (same approach as
test_package_persist_dedup.py) so they run without a live Postgres. The
end-to-end persist round-trip is covered by the live-DB e2e suite.
"""
from __future__ import annotations

from app.services.parsers.tech_linker import (
    apply_platform_tags_for_run,
    family_for_vendor,
    link_evidence_for_vendor,
    link_subcaps_for_vendor,
    map_l3_to_platform,
)

# ---------------------------------------------------------------------
# Pure mapping units (no session)
# ---------------------------------------------------------------------


def test_family_for_vendor_known_unknown_and_blank() -> None:
    assert family_for_vendor("Salesforce") == "salesforce"
    assert family_for_vendor("nCino") == "ncino"
    assert family_for_vendor("Databricks") == "databricks"
    assert family_for_vendor("Tableau") == "tableau"
    assert family_for_vendor("Twilio") == "twilio"
    # A real vendor with no scored platform family → evidence-only linkage.
    assert family_for_vendor("Fiserv") is None
    assert family_for_vendor("") is None
    assert family_for_vendor(None) is None
    # Surrounding whitespace is tolerated (vendors arrive un-trimmed).
    assert family_for_vendor("  Tableau  ") == "tableau"


def test_family_map_expanded_aliases_resolve_into_the_five() -> None:
    # The map was expanded with aliases — each MUST resolve into one of
    # the five scored families (no other platform is scorable).
    for vendor, expected in [
        ("SFDC", "salesforce"), ("MuleSoft", "salesforce"), ("Slack", "salesforce"),
        ("dbt", "databricks"), ("Looker", "tableau"), ("Qlik", "tableau"),
        ("Segment", "twilio"), ("SendGrid", "twilio"), ("SimpleNexus", "ncino"),
    ]:
        assert family_for_vendor(vendor) == expected


def test_map_l3_to_platform_keyword_family_and_dedup() -> None:
    assert map_l3_to_platform(["nCino"]) == ["ncino"]
    # Salesforce product families all collapse to the single scored id.
    assert map_l3_to_platform(["Sales Cloud", "Service Cloud"]) == ["salesforce"]
    assert map_l3_to_platform(["MuleSoft"]) == ["salesforce"]
    # Distinct platforms preserved, order-stable, de-duplicated.
    assert map_l3_to_platform(["Tableau", "Databricks", "Tableau"]) == ["tableau", "databricks"]
    # Unmapped / empty inputs drop out cleanly.
    assert map_l3_to_platform(["Some Unmapped Vendor"]) == []
    assert map_l3_to_platform([]) == []
    assert map_l3_to_platform(None) == []


# ---------------------------------------------------------------------
# FakeSession — records (sql, params); returns canned rows per table
# ---------------------------------------------------------------------


class _Row:
    def __init__(self, **kw: object) -> None:
        self.__dict__.update(kw)


class _Result:
    def __init__(self, rows: list[_Row] | None = None, rowcount: int = 0) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    def all(self) -> list[_Row]:
        return self._rows


class FakeSession:
    def __init__(
        self,
        *,
        evidence_rows: list[_Row] | None = None,
        subcap_rows: list[_Row] | None = None,
        catalogue_rows: list[_Row] | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._evidence_rows = evidence_rows or []
        self._subcap_rows = subcap_rows or []
        self._catalogue_rows = catalogue_rows or []

    async def execute(self, sql: object, params: dict | None = None) -> _Result:
        s = str(sql)
        self.calls.append((s, dict(params or {})))
        if "FROM evidence_index" in s:
            return _Result(rows=self._evidence_rows)
        if "FROM ccg_subcaps" in s:
            return _Result(rows=self._catalogue_rows)
        if "FROM subcap_scores" in s:
            return _Result(rows=self._subcap_rows)
        if "UPDATE subcap_scores" in s:
            return _Result(rowcount=1)
        return _Result()


def _calls(session: FakeSession, fragment: str) -> list[tuple[str, dict]]:
    return [(s, p) for (s, p) in session.calls if fragment.lower() in s.lower()]


# ---------------------------------------------------------------------
# link_evidence_for_vendor
# ---------------------------------------------------------------------


async def test_link_evidence_returns_matching_eids() -> None:
    sess = FakeSession(evidence_rows=[_Row(e_id="E-001"), _Row(e_id="E-014")])
    out = await link_evidence_for_vendor(sess, entity_id="ent-1", vendor="Salesforce")
    assert out == ["E-001", "E-014"]
    sel = _calls(sess, "FROM evidence_index")
    assert sel, "evidence query was not issued"
    assert "ILIKE" in sel[0][0]
    assert sel[0][1]["v"] == "Salesforce"
    assert sel[0][1]["e"] == "ent-1"


async def test_link_evidence_blank_vendor_short_circuits() -> None:
    sess = FakeSession(evidence_rows=[_Row(e_id="E-001")])
    assert await link_evidence_for_vendor(sess, entity_id="ent-1", vendor="  ") == []
    assert sess.calls == []  # no query for a blank vendor


# ---------------------------------------------------------------------
# link_subcaps_for_vendor
# ---------------------------------------------------------------------


async def test_link_subcaps_uses_platform_family() -> None:
    sess = FakeSession(subcap_rows=[_Row(subcap_id="P2C1.1.1"), _Row(subcap_id="P2C2.1.1")])
    out = await link_subcaps_for_vendor(sess, run_id="run-1", family="salesforce")
    assert out == ["P2C1.1.1", "P2C2.1.1"]
    sel = _calls(sess, "FROM subcap_scores")
    assert sel[0][1]["fam"] == "salesforce"
    assert sel[0][1]["rid"] == "run-1"
    assert "ANY(platform_tags)" in sel[0][0]


async def test_link_subcaps_none_family_short_circuits() -> None:
    sess = FakeSession(subcap_rows=[_Row(subcap_id="P2C1.1.1")])
    assert await link_subcaps_for_vendor(sess, run_id="run-1", family=None) == []
    assert sess.calls == []  # an unmapped vendor never queries


# ---------------------------------------------------------------------
# apply_platform_tags_for_run
# ---------------------------------------------------------------------


async def test_apply_platform_tags_maps_catalogue_and_fills_empty() -> None:
    sess = FakeSession(catalogue_rows=[
        _Row(subcap_id="P2C1.1.1", l3_platforms=["Sales Cloud", "MuleSoft"]),
        _Row(subcap_id="P4C2.1.1", l3_platforms=["Databricks"]),
        _Row(subcap_id="P1C1.1.1", l3_platforms=["Some Unmapped Tool"]),  # → no tag
    ])
    updated = await apply_platform_tags_for_run(
        sess, run_id="run-1", catalog_version="v7.0"
    )

    # The catalogue read is pinned to the run's catalogue version.
    cat = _calls(sess, "FROM ccg_subcaps")
    assert cat[0][1]["cv"] == "v7.0"

    # Only the two mapped subcaps are tagged; the unmapped one is skipped.
    upd = _calls(sess, "UPDATE subcap_scores")
    assert len(upd) == 2
    assert updated == 2
    by_sid = {p["sid"]: p["pids"] for (_s, p) in upd}
    assert by_sid["P2C1.1.1"] == ["salesforce"]   # Sales Cloud + MuleSoft collapse
    assert by_sid["P4C2.1.1"] == ["databricks"]
    assert "P1C1.1.1" not in by_sid

    # Fill-when-empty guard keeps any package-shipped tags authoritative.
    assert "cardinality(platform_tags) = 0" in upd[0][0]
    assert upd[0][1]["rid"] == "run-1"


async def test_apply_platform_tags_no_catalogue_is_noop() -> None:
    sess = FakeSession(catalogue_rows=[])
    assert await apply_platform_tags_for_run(sess, run_id="run-1", catalog_version="v7.0") == 0
    assert _calls(sess, "UPDATE subcap_scores") == []
