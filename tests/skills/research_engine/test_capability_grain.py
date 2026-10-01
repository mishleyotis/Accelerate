"""Search at the grain the catalogue already groups the work at.

MEASURED 2026-09-13 against the real catalogue: 686 T1_CORE cells sit under
129 capabilities — 5.32 cells each. Searching per subcap costs 7,546 turns
(37.7 lane-equivalents against the 16 lanes the driver has); one discovery
pass per capability plus per-cell differentiation costs 3,905 (19.5). A 48%
saving at the nine declared facets, 29% at the five askable ones.

And the packet was hiding the fact that makes it possible. On a fresh 47-cell
category, all eight cells in the `work_next` window belong to ONE capability
and each is owed the full five volleys — forty searches for a group a single
pass can seed. The lane could not see the grouping, so it could not exploit
it.

The containment is unchanged and must stay that way: `evidence_smear` blocks
above 50% shared evidence per cell, which is what keeps this capability grain
rather than the category-level searching `deep_search_protocol.md` names as
its #1 failure mode.
"""
from __future__ import annotations

import collections
import tempfile
from pathlib import Path

from engine import brief, contract as C, runstate
from engine.brief import capability_of
import fixtures as F


def _full_run(tmp_path, per_cat=3):
    # Select through `Taxonomy.selected(sv, scope)` — `cells_in` returns every
    # variant, including other sub-verticals', and seeding those is what
    # AUD-0077 refuses.
    tax = C.taxonomy()
    legal = list(tax.selected("CU", "T1_CORE"))
    by_cat: dict[str, list] = {}
    for cell in legal:
        by_cat.setdefault(cell.split(".")[0], []).append(cell)
    sel = [c for cat in sorted(by_cat) for c in by_cat[cat][:per_cat]]
    return runstate.start(
        run_id="R-CAP", entity_name="Acme", entity_id="acme", sub_vertical="CU",
        scope_mode="T1_CORE", reference_date="2026-08-29",
        root=tmp_path / "run", selected=sel)


# ── E1 · the shared block is computed once per batch ────────────────────

def test_a_batch_computes_the_shared_block_once(tmp_path, monkeypatch):
    """It describes the RUN, not the category, and it is identical for every
    lane in a round. Recomputing it per lane walked every category's worklist
    again — measured at 16 categories: 16 `shared()` calls and 272
    `worklist()` calls where 1 and ~17 would do."""
    run = _full_run(tmp_path)
    wb = run.open()
    n = {"shared": 0}
    real = brief.shared
    monkeypatch.setattr(brief, "shared",
                        lambda w, *a, **k: (n.__setitem__("shared", n["shared"] + 1)
                                            or real(w, *a, **k)))
    brief.batch(wb, run=run, out_dir=tmp_path / "b",
                only=sorted(C.taxonomy().categories))
    assert n["shared"] == 1, f"one per batch, not one per lane (got {n['shared']})"


def test_the_shared_block_still_reaches_every_packet(tmp_path):
    """Hoisting changed WHO computes it, never whether the lane gets it —
    `as_markdown`, the packet_chars ceiling and every test reading
    `packet["shared"]` depend on the key being there."""
    run = _full_run(tmp_path)
    wb = run.open()
    out = brief.batch(wb, run=run, out_dir=tmp_path / "b",
                      only=["P1C1", "P1C2", "P1C3"])
    import json
    for row in out["briefs"]:
        packet = json.loads(Path(row["prompt_file"]).with_suffix(".json").read_text())
        assert packet["shared"], f"{row['category']} lost its shared block"
        assert packet["shared"]["entity"] == "Acme"
    assert "## What the run already knows" in Path(
        out["briefs"][0]["prompt_file"]).read_text()


def test_dispatch_still_computes_shared_when_called_alone(tmp_path):
    """The CLI calls `dispatch` directly. The kwarg is optional for it."""
    run = _full_run(tmp_path)
    p = brief.dispatch(run.open(), "P1C1", run=run)
    assert p["shared"] and p["shared"]["entity"] == "Acme"


# ── E2 · the capability rollup ──────────────────────────────────────────

def test_the_packet_names_the_capability_each_open_cell_answers(tmp_path):
    run = _full_run(tmp_path)
    p = brief.dispatch(run.open(), "P1C1", run=run)
    assert p["capabilities"], "the rollup must be present"
    seen = {c["capability"] for c in p["capabilities"]}
    assert seen == {capability_of(d["subcap"]) for d in p["work_next"]}
    for c in p["capabilities"]:
        assert c["cells"] and c["cells_shown"] == len(c["cells"])
        for cell in c["cells"]:
            assert capability_of(cell) == c["capability"]


def test_the_group_carries_the_union_of_volleys_owed(tmp_path):
    """The point of the rollup: fire each owed facet ONCE for the group."""
    run = _full_run(tmp_path)
    p = brief.dispatch(run.open(), "P1C1", run=run)
    by_cell = {d["subcap"]: set(d["volleys_owed"]) for d in p["work_next"]}
    for c in p["capabilities"]:
        union = set().union(*(by_cell[cell] for cell in c["cells"]))
        assert set(c["volleys_owed_across_group"]) == union


def test_work_next_is_untouched(tmp_path):
    """The rollup is ADDITIONAL. `work_next` stays a flat list of per-cell
    dicts, because several tests and the markdown renderer pin that shape."""
    run = _full_run(tmp_path)
    p = brief.dispatch(run.open(), "P1C1", run=run)
    assert isinstance(p["work_next"], list)
    assert len(p["work_next"]) <= brief.CELLS_DETAILED
    for d in p["work_next"]:
        assert {"subcap", "name", "volleys_owed", "volleys_fired", "tools_used",
                "already_registered_for_this_cell",
                "capability_siblings_worth_reading"} <= set(d)


def test_the_lane_is_told_the_grouping_and_its_boundary(tmp_path):
    """A rollup the lane cannot read buys nothing, and one that does not name
    the 50% smear cap invites the failure mode it exists to avoid."""
    run = _full_run(tmp_path)
    md = brief.as_markdown(brief.dispatch(run.open(), "P1C1", run=run))
    assert "### Work next — grouped by capability" in md
    assert "evidence_smear" in md and "at most half" in md
    assert "### Work next" in md, "the per-cell list must still render"


def test_the_packet_stays_under_its_ceiling(tmp_path):
    run = _full_run(tmp_path, per_cat=20)
    p = brief.dispatch(run.open(), "P1C1", run=run)
    assert p["packet_chars"] <= p["packet_ceiling"], (
        "the rollup must not push the packet past the bound that keeps a "
        "lane's opening context payable")


# ── the measurement that justifies the change ───────────────────────────

def test_the_catalogue_really_does_group_five_cells_to_a_capability():
    """If this drifts, the saving the grain change is built on drifts with
    it — and `cost.lane_fit`'s projection stops describing the work."""
    tax = C.taxonomy()
    sel = list(tax.selected(None, "T1_CORE"))
    caps = collections.Counter(capability_of(c) for c in sel)
    assert len(sel) == 686
    assert len(caps) == 129
    assert 5.0 <= len(sel) / len(caps) <= 5.7, len(sel) / len(caps)
