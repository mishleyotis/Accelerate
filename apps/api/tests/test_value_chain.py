"""H9 · value-chain view — the server-derived section (stage 6.3).

The section's payload contract is deliberately `fields: {}`: the producer
authors nothing, and the Backend Schema derives the surface by joining
ccg_value_chains to ccg_vc_mapping — "what lets the heatmap arrange the
same scores along the institution's value chain rather than the
catalogue's taxonomy". These tests drive that derivation with injected
join results (no live DB, same discipline as test_serving_read_path):
stated stage order is preserved, membership comes from the mapping only,
a mapped cell the run does not serve is counted rather than dropped, and
the loader's per-stage chain_id minting cannot fracture one arrangement
into many.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api.value_chain import (PRODUCER_VERSION, PROVENANCE, arrange,  # noqa: E402
                                 read_value_chain, resolve_subvertical,
                                 serve_value_chain)

RUN = {"run_id": "11111111-1111-1111-1111-111111111111",
       "ccg_catalog_version": "v7.0",
       "promoted_at": "2026-08-05T04:00:00+00:00"}
ENTITY = {"display_id": "baxter-credit-union-0001", "sub_vertical": "SV2"}


def stage(sid, name, order):
    return {"stage_id": sid, "name": name, "stage_order": order}


def mapped(subcap_id, *stages):
    return {"subcap_id": subcap_id, "stages": list(stages)}


class _Cur:
    """Enough of a cursor to drive read_value_chain: the current-version
    lookup, the two catalogue selects and the run's served-cell register.
    Every query's parameters are recorded so a test can assert WHICH
    arrangement and run were asked for."""

    def __init__(self, stages=(), mapping=(), served=(), current="v7.0"):
        self.stages, self.mapping, self.served = stages, mapping, served
        self.current = current
        self.queries: list[tuple[str, tuple]] = []
        self._out: list = []

    def execute(self, sql, params=None):
        self.queries.append((sql, params))
        if "FROM ccg_versions" in sql:
            self._out = [(self.current,)] if self.current else []
        elif "FROM ccg_value_chains" in sql:
            self._out = [(s["stage_id"], s["name"], s["stage_order"])
                         for s in self.stages]
        elif "FROM ccg_vc_mapping" in sql:
            self._out = [(m["subcap_id"], m["stages"]) for m in self.mapping]
        elif "FROM serving_subcaps" in sql:
            self._out = [(sid,) for sid in self.served]
        else:                                            # pragma: no cover
            raise AssertionError(sql)

    def fetchall(self):
        return self._out

    def params_for(self, fragment):
        for sql, params in self.queries:
            if fragment in sql:
                return params
        raise AssertionError(f"no query touched {fragment}")  # pragma: no cover


# ── the pure derivation ────────────────────────────────────────────────
def test_stage_order_is_the_arrangements_stated_order():
    """`stage_order` is meaning (Backend Schema: 'Order is meaning');
    whatever order the rows arrive in, the chains serve the stated one."""
    rows = [stage("VC-CU-03", "Servicing", 3),
            stage("VC-CU-01", "Origination", 1),
            stage("VC-CU-02", "Onboarding", 2)]
    data = arrange(rows, [mapped("P1C1.1.1", "Origination")], {"P1C1.1.1"})
    assert [c["name"] for c in data["chains"]] == [
        "Origination", "Onboarding", "Servicing"]
    assert [c["stage_order"] for c in data["chains"]] == [1, 2, 3]


def test_membership_comes_from_the_mapping_only():
    """A stage lists exactly the cells ccg_vc_mapping puts in it — a cell
    the run serves but the mapping never mentions is NOT invented into a
    stage, and a stage the mapping leaves empty says so with an empty
    list rather than borrowing cells."""
    rows = [stage("VC-CU-01", "Origination", 1),
            stage("VC-CU-02", "Servicing", 2)]
    mapping = [mapped("P1C1.1.1", "Origination"),
               mapped("P2C3.1.6", "Origination")]
    served = {"P1C1.1.1", "P2C3.1.6", "P4C1.1.2"}  # P4… served, unmapped
    data = arrange(rows, mapping, served)
    origination, servicing = data["chains"]
    assert origination["subcaps"] == ["P1C1.1.1", "P2C3.1.6"]
    assert "P4C1.1.2" not in origination["subcaps"], \
        "a served cell the mapping never named must not be invented in"
    assert servicing["subcaps"] == [] and servicing["not_scored"] == 0


def test_unscored_mapped_cells_are_counted_not_dropped():
    """A mapped cell the run does not serve leaves the membership list but
    not the record: it lands in the per-stage `not_scored` count, and the
    distinct total is counted once even when the cell sits in two stages
    (so it is not recomputable from the per-stage counts)."""
    rows = [stage("VC-CU-01", "Origination", 1),
            stage("VC-CU-02", "Servicing", 2)]
    mapping = [mapped("P1C1.1.1", "Origination"),
               mapped("P9C9.9.9", "Origination", "Servicing"),  # not served
               mapped("P2C3.1.6", "Servicing")]
    data = arrange(rows, mapping, {"P1C1.1.1", "P2C3.1.6"})
    origination, servicing = data["chains"]
    assert origination["subcaps"] == ["P1C1.1.1"]
    assert origination["not_scored"] == 1
    assert servicing["subcaps"] == ["P2C3.1.6"]
    assert servicing["not_scored"] == 1
    assert data["not_scored_cells"] == 1, \
        "one unserved cell in two stages is one cell, not two"
    assert all("P9C9.9.9" not in c["subcaps"] for c in data["chains"])


def test_per_stage_chain_id_flaw_one_arrangement_not_many():
    """The loader mints chain_id PER STAGE (VC-RB-01, VC-RB-02, …): one
    chain_id names one STAGE, and only (sub_vertical, version) names an
    arrangement. Two stage rows with different chain_ids are therefore two
    stages of ONE arrangement — each keeps its own id as stage_id, and the
    arrangement is identified by sub_vertical + version, never by any
    single chain_id."""
    cur = _Cur(stages=[stage("VC-CU-01", "Origination", 1),
                       stage("VC-CU-02", "Servicing", 2)],
               mapping=[mapped("P1C1.1.1", "Origination"),
                        mapped("P2C3.1.6", "Servicing")],
               served=["P1C1.1.1", "P2C3.1.6"])
    data, empty = read_value_chain(cur, ENTITY, RUN)
    assert empty is None
    assert len(data["chains"]) == 2, "two stage rows, one arrangement"
    assert [c["stage_id"] for c in data["chains"]] == ["VC-CU-01", "VC-CU-02"]
    assert data["sub_vertical"] == "CU" and data["version"] == "v7.0"
    # and the selects were keyed on (sub_vertical, version), not chain_id
    assert cur.params_for("ccg_value_chains") == ("v7.0", "CU")
    assert cur.params_for("ccg_vc_mapping") == ("v7.0", "CU")
    assert cur.params_for("serving_subcaps") == (RUN["run_id"],)


def test_empty_state_names_what_was_searched():
    """No arrangement for this sub-vertical/version is an honest absence:
    data None, and the empty state names both tables with the exact keys
    that were searched."""
    cur = _Cur(stages=[], mapping=[], served=["P1C1.1.1"])
    data, empty = read_value_chain(cur, ENTITY, RUN)
    assert data is None
    assert empty["kind"] == "no_value_chain_arrangement"
    assert "CU" in empty["reason"] and "v7.0" in empty["reason"]
    assert empty["sources_searched"] == [
        "ccg_value_chains[version=v7.0 sub_vertical=CU]",
        "ccg_vc_mapping[version=v7.0 subvertical_code=CU]"]


def test_unknown_subvertical_is_named_never_guessed():
    cur = _Cur()
    data, empty = read_value_chain(
        cur, {"sub_vertical": "Intergalactic Banking"}, RUN)
    assert data is None
    assert empty["kind"] == "no_value_chain_arrangement"
    assert "Intergalactic Banking" in empty["reason"]
    # the resolver refused rather than querying with a guess
    assert not any("ccg_value_chains" in sql for sql, _ in cur.queries)


def test_version_falls_back_to_current_mirroring_serving_subcaps():
    """serving_subcaps (0016) joins on COALESCE(r.ccg_catalog_version,
    current); an unpinned run's arrangement must come from the same
    catalogue its cells are named from."""
    cur = _Cur(stages=[stage("VC-CU-01", "Origination", 1)],
               mapping=[mapped("P1C1.1.1", "Origination")],
               served=["P1C1.1.1"], current="v7.0")
    run = dict(RUN, ccg_catalog_version=None)
    data, empty = read_value_chain(cur, ENTITY, run)
    assert empty is None and data["version"] == "v7.0"
    assert any("FROM ccg_versions" in sql for sql, _ in cur.queries)
    # a pinned run never consults the current pointer
    cur2 = _Cur(stages=[stage("VC-CU-01", "Origination", 1)],
                mapping=[], served=[])
    read_value_chain(cur2, ENTITY, RUN)
    assert not any("FROM ccg_versions" in sql for sql, _ in cur2.queries)


def test_subvertical_crosswalk_both_vocabularies():
    """The serving tier speaks Surface-Spec codes/labels; the catalogue's
    VC tables speak the workbook codes. Both resolve; garbage does not."""
    assert resolve_subvertical("SV2") == "CU"
    assert resolve_subvertical("Credit Unions") == "CU"
    assert resolve_subvertical("CU") == "CU"
    assert resolve_subvertical("SV1") == "RB"
    assert resolve_subvertical("Regional Banks") == "RB"
    assert resolve_subvertical("Retail Banking") == "RB"
    assert resolve_subvertical("RIA / Broker-Dealer") == "RIA"
    assert resolve_subvertical("Insurance Brokerages") == "IB"
    assert resolve_subvertical("SV9") == "FC"
    assert resolve_subvertical(None) is None
    assert resolve_subvertical("  ") is None
    assert resolve_subvertical("Hedge Funds") is None


# ── the served section entry ───────────────────────────────────────────
def _built(data=None, env=None, stamps=None):
    """What serving_spec.assemble returns for a promoted envelope-only
    heatmap_value_chain row (SELECT * hands back every column, NULL-valued)."""
    return {"data": {"r_layer": None, "narrative_thread": None,
                     **(data or {})},
            "env": {"e_ids": ["E-BCU-061"], "internal_only": [],
                    "empty_state": None, **(env or {})},
            "stamps": {"provenance": "producer",
                       "promoted_at": datetime(2026, 8, 5, 4, tzinfo=timezone.utc),
                       "producer_version": "dma-surface-production@7",
                       **(stamps or {})}}


def test_promoted_envelope_is_kept_and_null_data_is_replaced():
    """The normal case: the producer promoted only the envelope (H9 has no
    prompt; `fields: {}`). The derived arrangement replaces the null data
    and the promoted stamps keep attributing the row."""
    cur = _Cur(stages=[stage("VC-CU-01", "Origination", 1)],
               mapping=[mapped("P1C1.1.1", "Origination")],
               served=["P1C1.1.1"])
    entry = serve_value_chain(cur, ENTITY, RUN, _built(), "internal")
    assert entry["data_source"] == "server_derived"
    assert entry["data"]["chains"][0]["subcaps"] == ["P1C1.1.1"]
    assert entry["e_ids"] == ["E-BCU-061"], "promoted envelope kept"
    assert entry["produced_at"] == "2026-08-05T04:00:00+00:00"
    assert entry["producer_version"] == "dma-surface-production@7"
    assert entry["provenance"] == "producer"
    assert entry["empty_state"] is None
    # NULL section columns are not data and do not survive the merge
    assert "narrative_thread" not in entry["data"]


def test_section_serves_with_no_promoted_row_under_a_server_stamp():
    cur = _Cur(stages=[stage("VC-CU-01", "Origination", 1)],
               mapping=[mapped("P1C1.1.1", "Origination")],
               served=["P1C1.1.1"])
    entry = serve_value_chain(cur, ENTITY, RUN, None, "internal")
    assert entry["data"]["chains"], "derived data serves without a promote"
    assert entry["producer_version"] == PRODUCER_VERSION
    assert entry["provenance"] == PROVENANCE
    assert entry["produced_at"] == RUN["promoted_at"], \
        "the server stamp is the run's promotion, not an invented time"
    assert entry["e_ids"] == []


def test_no_arrangement_keeps_the_promoted_envelope_and_says_why():
    cur = _Cur(stages=[], mapping=[], served=["P1C1.1.1"])
    entry = serve_value_chain(cur, ENTITY, RUN, _built(), "internal")
    assert entry["data"] is None and entry["data_source"] == "empty"
    assert entry["empty_state"]["kind"] == "no_value_chain_arrangement"
    assert entry["producer_version"] == "dma-surface-production@7"
    assert entry["e_ids"] == ["E-BCU-061"]


def test_redaction_runs_through_the_same_path_as_the_grid():
    """Server-derived score data obeys the same audience rules: a promoted
    internal_only mark strips for the customer and survives for the
    analyst, and the strip is reported."""
    def fresh():
        return _Cur(stages=[stage("VC-CU-01", "Origination", 1)],
                    mapping=[mapped("P1C1.1.1", "Origination")],
                    served=["P1C1.1.1"])
    built = _built(data={"r_layer": {"verdict": "analyst reasoning"}},
                   env={"internal_only": ["r_layer"]})
    internal = serve_value_chain(fresh(), ENTITY, RUN, built, "internal")
    assert internal["data"]["r_layer"] == {"verdict": "analyst reasoning"}
    customer = serve_value_chain(fresh(), ENTITY, RUN, built, "customer")
    assert "r_layer" not in customer["data"]
    assert customer["redacted_paths"] == ["r_layer"]
    assert customer["data"]["chains"], "the arrangement itself still serves"


def test_payload_carries_ids_only_no_scores_no_bands_no_colour():
    """Invariant 7: scores stay on the served cell register the renderer
    already resolves (`subcapsForStage` joins `vc.subcaps` to
    entity.subcaps); the section serves the arrangement, nothing painted."""
    cur = _Cur(stages=[stage("VC-CU-01", "Origination", 1)],
               mapping=[mapped("P1C1.1.1", "Origination")],
               served=["P1C1.1.1"])
    entry = serve_value_chain(cur, ENTITY, RUN, _built(), "internal")
    chain = entry["data"]["chains"][0]
    # exactly what the prototype renderer reads: vc.id, vc.name, vc.subcaps
    assert chain["id"] == chain["stage_id"] == "VC-CU-01"
    assert chain["name"] == "Origination"
    assert chain["subcaps"] == ["P1C1.1.1"]
    forbidden = {"score", "band", "hex", "color", "colour", "peer_median"}
    assert not forbidden & set(chain), "no score, band or colour in the payload"
    assert not forbidden & set(entry["data"])


def test_wired_into_the_heatmap_page_read():
    """pages.py dispatches H9 to the derivation AFTER assembling the
    promoted envelope and BEFORE the section_not_promoted branch — so the
    section serves when only an envelope (or nothing) promoted."""
    src = (ROOT / "apps" / "api" / "dma_api" / "pages.py").read_text()
    assert "from .value_chain import serve_value_chain" in src
    dispatch = src.index('section == "value_chain"')
    assert src.index("built = assemble(page, section, rows)") < dispatch, \
        "the promoted envelope must be assembled first, then kept"
    assert dispatch < src.index('"kind": "section_not_promoted"'), \
        "H9 must never fall through to section_not_promoted"


def test_a_pinned_version_with_no_arrangement_borrows_the_current_one():
    """USER ADJUDICATION 2026-08-07: a v5.0-pinned run whose sub-vertical has
    no v5.0 arrangement borrows the current catalogue's. Membership still
    joins against the run's own served cells, and arrangement_version records
    the borrow so the surface can say so."""
    from dma_api.value_chain import read_value_chain

    class Cur:
        def __init__(self):
            self.calls = []
        def execute(self, sql, params=None):
            self.calls.append((sql, params))
            self._last = (sql, params)
        def fetchall(self):
            sql, params = self._last
            if "FROM ccg_value_chains" in sql:
                # v5.0 has nothing; v7.0 has two stages
                if params and params[0] == "v7.0":
                    return [("VC-CU-01", "Member acquisition", 1),
                            ("VC-CU-02", "Onboarding", 2)]
                return []
            if "FROM ccg_vc_mapping" in sql:
                assert params[0] == "v7.0", "membership reads the BORROWED version"
                return [("P2C1.1.1", ["Member acquisition"]),
                        ("P9C9.9.9", ["Onboarding"])]      # v7-only cell
            if "FROM ccg_versions" in sql:
                return [("v7.0",)]
            if "FROM serving_subcaps" in sql:
                return [("P2C1.1.1",)]
            raise AssertionError(sql)
        def fetchone(self):
            return ("v7.0",)

    data, empty = read_value_chain(
        Cur(), {"sub_vertical": "SV2"},
        {"run_id": "r", "ccg_catalog_version": "v5.0"})
    assert empty is None
    assert data["version"] == "v5.0"
    assert data["arrangement_version"] == "v7.0"
    ids = {c["stage_id"]: c for c in data["chains"]}
    assert ids["VC-CU-01"]["subcaps"] == ["P2C1.1.1"], \
        "only cells the RUN serves appear"
    assert "P9C9.9.9" not in ids["VC-CU-02"]["subcaps"], \
        "a v7-only cell the run never scored is not invented into the view"


def test_every_workbook_marker_shape_is_stripped_and_counted():
    """The `21_VC_Mapping_PerSubcap` column carries the author's own
    annotations as stage labels. Four shapes ship in v7.0, and until the
    catalogue was curated (0024) this read path only recognised two — so
    Baxter's 30 CU stages included a stage headed "(SV-Specific:
    P3C1.3.CU1)" and another headed "Indirect: credit unions also
    cooperative; some governance patterns transfer".

    A catalogue loaded after 0024 carries none of them; a version loaded
    before it still does, and is still served. They are excluded and
    COUNTED — a stage dropped silently is a stage the reader believes
    does not exist.
    """
    markers = [
        "- (N/A)",
        "Not applicable — credit unions follow NCUA framework, not FCA",
        "(applicable via CIB pattern)",
        "(SV-Specific: P3C1.3.CU1)",
        "Indirect: credit unions also cooperative; some governance patterns transfer",
    ]
    stages = [stage(f"VC-CU-{i:02d}", name, i)
              for i, name in enumerate(markers, 1)]
    stages.append(stage("VC-CU-09", "Member onboarding & account opening", 9))
    cur = _Cur(stages=stages,
               mapping=[mapped("P2C1.1.1", "Member onboarding & account opening"),
                        mapped("P1C1.1.1", "- (N/A)")],
               served=["P2C1.1.1", "P1C1.1.1"])
    data, empty = read_value_chain(cur, ENTITY, RUN)
    assert empty is None
    assert [c["name"] for c in data["chains"]] == \
        ["Member onboarding & account opening"]
    assert data["not_applicable_stages"] == len(markers)


def test_a_curated_arrangement_is_served_whole():
    """With the catalogue curated the read path has nothing left to
    filter, and nothing here caps or reorders: eight stages in, eight out,
    in the arrangement's stated order."""
    names = ["Field of membership & market strategy",
             "Member acquisition & marketing",
             "Member onboarding & account opening",
             "Member servicing & digital engagement",
             "Member growth, cross-sell & lending",
             "Payments & card operations",
             "Back office, CUSO & shared services",
             "Risk, fraud & NCUA compliance"]
    cur = _Cur(stages=[stage(f"VC-CU-{i:02d}", n, i)
                       for i, n in enumerate(names, 1)],
               mapping=[mapped(f"P1C1.1.{i}", n) for i, n in enumerate(names, 1)],
               served=[f"P1C1.1.{i}" for i in range(1, len(names) + 1)])
    data, empty = read_value_chain(cur, ENTITY, RUN)
    assert empty is None
    assert [c["name"] for c in data["chains"]] == names
    assert data["not_applicable_stages"] == 0
    assert all(len(c["subcaps"]) == 1 for c in data["chains"])
