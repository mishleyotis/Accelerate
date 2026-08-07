"""H9 · Value-chain view — the server-derived section (Surface Spec H9).

The contract is one sentence: "the same scores arranged along the
institution's value chain rather than the catalogue's taxonomy", and its
payload contract is deliberately `fields: {}` — the producer authors
nothing for this surface. The Backend Schema (§08) says joining
`ccg_value_chains` to `ccg_vc_mapping` "is what lets the heatmap arrange
the same scores along the institution's value chain rather than the
catalogue's taxonomy". This module performs that join at read time; the
promoted `heatmap_value_chain` row contributes only its envelope.

## The tables, and the loader flaw this module must absorb

`ccg_value_chains (chain_id, version, sub_vertical, name, stage_order,
source_stages)` is written by the ccg_loader, which mints `chain_id` PER
STAGE (`VC-RB-01`, `VC-RB-02`, …) — one chain_id names one STAGE, not an
arrangement. Only (sub_vertical, version) identifies an arrangement, so
that pair is what this module selects on; each row's chain_id serves as
the stage id. `ccg_vc_mapping (version, subcap_id, subvertical_code,
value_chain_stages TEXT[], …)` names, per cell, the stage NAMES the cell
belongs to; membership joins mapping stage names to stage rows by name
and is never invented here.

## The arrangement is eight stages, and that is the catalogue's doing

Until 0024 the loader minted one stage per distinct workbook label —
45 to 54 per sub-vertical, of which Baxter served 30 — and the front end
truncated to the five with the deepest coverage. Curating that is
catalogue work, not read-path work: `ccg_loader/value_chains.py` folds
the labels that name the same process into eight client-legible stages
per sub-vertical, so every client of a sub-vertical inherits the same
arrangement and the renderer draws what it is given. Nothing in this
module caps or reorders anything; `stage_order` is still the only
statement of sequence, and `source_stages` records which workbook labels
each stage folds.

## Vocabulary crosswalk (two sub-vertical vocabularies exist)

The serving tier stores the Surface Specification codes (SV1–SV9) or, in
older manifests, a spelled-out label; the catalogue's VC tables key on
the workbook codes (RB · CU · CL · CIB · FC · AM · RIA · IC · IB, per
the loader's SUBVERTICAL_CODES). The pairs are unambiguous — SV1
"Regional Banks" is the workbook's "Retail Banking" (RB), SV7 "Insurance
Brokers" is "Insurance Brokerages" (IB), and so on — and the crosswalk
below is that pairing, nothing more. A value neither vocabulary knows is
NOT guessed at: the section serves its empty state naming exactly what
was searched.

## What is (and is not) in the payload

Stages in the arrangement's stated order, each `{stage_id, id, name,
stage_order, subcaps, not_scored}`. `subcaps` lists only cells the run
actually serves (joined against `serving_subcaps`); a mapped cell the run
does not serve is counted under `not_scored`, never silently dropped, and
never listed as if it were scored. Scores, bands and colours are NOT
copied in: the renderer (ValueChainView → subcapsForStage) resolves each
listed id against the run's served cell register, which is the same rows
the heatmap grid serves — one authority, and no colour in any payload
(invariants 7 and 8). `id` duplicates `stage_id` because the prototype
renderer keys its tiles and selection on `vc.id`.

The catalogue version mirrors `serving_subcaps` (0016): the run's pinned
`ccg_catalog_version`, falling back to the current catalogue when the run
is unpinned.
"""
from __future__ import annotations

import re

from .redaction import redact_section
# One sub-vertical vocabulary for the whole read path: the entity->code
# crosswalk this module needs and the cell->code derivation that keeps a
# foreign variant off the grid are the same fact, so they live together.
from .subverticals import resolve_subvertical, scope_to_entity  # noqa: F401

# Stamped on the envelope when no promoted row supplied one — the derived
# data is the server's work-product, and every served row is attributable.
PRODUCER_VERSION = "svc-api.value-chain-derive@1"
PROVENANCE = "server_derived"

# A stage name that is the workbook annotating rather than naming. Kept in
# step with ccg_loader.value_chains._MARKERS — the loader drops these at
# load, this drops them on read, and the two exist separately because the
# API and the loader are separate deployables that share no code.
#
#   "- (N/A)" · "Not applicable — credit unions follow NCUA framework"
#   "(applicable via CIB pattern)"   another sub-vertical's arrangement
#   "(SV-Specific: P3C1.3.CU1)"      a cell id in the stage column
#   "Indirect: crop insurance brokers overlap with Farm Credit servicing"
_MARKERS = (
    r"^[-–—\s]*(\(?\s*n/?a\s*\)?|not applicable)\b",
    r"^\(applicable via .+\)$",
    r"^\(\s*sv-specific\s*:.*\)$",
    r"^indirect\s*:",
)


def arrange(stage_rows, mapping_rows, served_ids) -> dict:
    """The derived section data, from already-fetched join inputs.

    stage_rows   [{stage_id, name, stage_order}] — one ccg_value_chains row
                 per STAGE of one (sub_vertical, version) arrangement.
    mapping_rows [{subcap_id, stages: [stage names]}] — ccg_vc_mapping rows
                 for the same (sub_vertical, version).
    served_ids   the cell ids the run actually serves (serving_subcaps).

    Pure: everything it emits is computed from these inputs, so the join
    result can be injected under test (invariant 8 — counts computed).
    """
    served = set(served_ids)
    # Order is meaning (ccg_value_chains.stage_order); chain_id breaks a tie
    # deterministically but never reorders a stated order.
    ordered = sorted(stage_rows,
                     key=lambda s: (s["stage_order"], s["stage_id"]))

    # stage name -> mapped cell ids, from the mapping ONLY. Sorted by id so
    # two reads of one arrangement serve one list.
    members: dict[str, list[str]] = {}
    for row in sorted(mapping_rows, key=lambda r: r["subcap_id"]):
        for stage_name in row.get("stages") or ():
            members.setdefault(stage_name, []).append(row["subcap_id"])

    chains = []
    unserved: set[str] = set()
    for stage in ordered:
        mapped = members.get(stage["name"], [])
        subcaps = [sid for sid in mapped if sid in served]
        missing = [sid for sid in mapped if sid not in served]
        unserved.update(missing)
        chains.append({
            "stage_id": stage["stage_id"],
            # the prototype renderer keys tiles and selection on `vc.id`
            "id": stage["stage_id"],
            "name": stage["name"],
            "stage_order": stage["stage_order"],
            "subcaps": subcaps,
            # mapped in the catalogue's arrangement, absent from the run's
            # served cell register — counted, never silently dropped
            "not_scored": len(missing),
        })
    return {"chains": chains,
            # distinct across the arrangement: a cell can sit in several
            # stages, so this is not the sum of the per-stage counts and
            # cannot be recomputed from them
            "not_scored_cells": len(unserved)}


def _current_version(cur) -> str | None:
    cur.execute("SELECT version FROM ccg_versions WHERE is_current")
    row = cur.fetchall()
    return row[0][0] if row else None


def read_value_chain(cur, entity: dict, run_meta: dict):
    """(data, empty_state) — exactly one is None.

    Picks the arrangement for the RUN's pinned catalogue version (falling
    back to current, mirroring serving_subcaps) and the entity's
    sub-vertical, then joins membership against the run's served cells.
    """
    version = run_meta.get("ccg_catalog_version") or _current_version(cur)
    raw_sv = entity.get("sub_vertical")
    code = resolve_subvertical(raw_sv)

    if version is None or code is None:
        unknown = ("no current catalogue version" if version is None else
                   f"sub-vertical {raw_sv!r} matches no known vocabulary "
                   "(Surface Spec SV1-SV9, workbook VC codes, or either's labels)")
        return None, {
            "kind": "no_value_chain_arrangement",
            "reason": f"the value-chain arrangement could not be resolved: {unknown}",
            "sources_searched": [
                f"ccg_value_chains[version={version or '?'} "
                f"sub_vertical={code or raw_sv or '?'}]",
                f"ccg_vc_mapping[version={version or '?'} "
                f"subvertical_code={code or raw_sv or '?'}]",
            ]}

    def _stages(v):
        cur.execute(
            """SELECT chain_id, name, stage_order
                 FROM ccg_value_chains
                WHERE version = %s AND sub_vertical = %s
                ORDER BY stage_order, chain_id""", (v, code))
        return [{"stage_id": r[0], "name": r[1], "stage_order": r[2]}
                for r in cur.fetchall()]

    def _real(stages):
        # The workbook's mapping carries literal not-applicable markers as
        # stage rows — the AUTHOR's way of saying a cell maps nowhere for
        # this sub-vertical, not stages of anyone's value chain. Serving
        # them renders junk columns under a client's heading.
        #
        # A catalogue loaded at v7.0 or later no longer carries them: the
        # loader curates the arrangement (ccg_loader/value_chains.py) and
        # drops markers at load. This filter is for versions loaded BEFORE
        # that, which are still in the database and still served, and it
        # is why it lists every shape rather than the ones that happened to
        # be visible. All four were observed in the shipped v7.0 tabs, and
        # the last two were being served as stages: Baxter's 30 CU stages
        # included "(SV-Specific: P3C1.3.CU1)" and "Indirect: credit unions
        # also cooperative; some governance patterns transfer".
        keep, dropped = [], 0
        for st in stages:
            name = str(st.get("name") or "").strip()
            if not name or any(re.match(p, name, re.IGNORECASE) for p in _MARKERS):
                dropped += 1
                continue
            keep.append(st)
        return keep, dropped

    stage_rows, na_stages = _real(_stages(version))
    searched = [f"ccg_value_chains[version={version} sub_vertical={code}]"]
    # USER ADJUDICATION 2026-08-07: "the value chain arrangement is enriched
    # from v7 to v5." A v5.0-pinned run whose sub-vertical has no v5.0
    # arrangement borrows the CURRENT catalogue's (v7.0's) — the arrangement
    # is business-process taxonomy, not scoring, and 795 of v5.0's 836 cell
    # ids resolve directly in v7.0's mapping. Membership still joins against
    # the run's own served cells, so a v7-only cell simply never appears and
    # a v5-only cell (the killed P1C5) counts under not_scored — nothing is
    # invented on either side. arrangement_version records what was borrowed.
    arrangement_version = version
    if not stage_rows:
        current = _current_version(cur)
        if current and current != version:
            stage_rows, na2 = _real(_stages(current))
            na_stages += na2
            if stage_rows:
                arrangement_version = current
            searched.append(
                f"ccg_value_chains[version={current} sub_vertical={code}]")
    if not stage_rows:
        return None, {
            "kind": "no_value_chain_arrangement",
            "reason": (f"the catalogue has no value-chain arrangement for "
                       f"sub-vertical {code} at version {version}, and none "
                       "at the current version to borrow"),
            "sources_searched": searched + [
                f"ccg_vc_mapping[version={version} subvertical_code={code}]",
            ]}

    cur.execute(
        """SELECT subcap_id, value_chain_stages
             FROM ccg_vc_mapping
            WHERE version = %s AND subvertical_code = %s""",
        (arrangement_version, code))
    mapping_rows = [{"subcap_id": r[0], "stages": list(r[1] or ())}
                    for r in cur.fetchall()]

    # The run's served cell register — the SAME rows the heatmap serves, so
    # a cell listed here resolves in the renderer and nowhere else. Scoped
    # to the entity's sub-vertical by the same rule /subcaps applies, or
    # the two would disagree: a cell excluded from the grid but listed in a
    # stage renders as an unresolvable tile, and `not_scored` would undercount.
    cur.execute("SELECT subcap_id FROM serving_subcaps WHERE run_id = %s",
                (run_meta["run_id"],))
    served_ids = set(scope_to_entity([r[0] for r in cur.fetchall()], raw_sv))

    data = arrange(stage_rows, mapping_rows, served_ids)
    data["sub_vertical"] = code
    data["version"] = version
    data["arrangement_version"] = arrangement_version
    data["not_applicable_stages"] = na_stages
    return data, None


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def serve_value_chain(cur, entity: dict, run_meta: dict, built,
                      audience: str) -> dict:
    """The full section entry for the page response.

    `built` is serving_spec.assemble()'s result for the promoted
    heatmap_value_chain row, or None when no row promoted. Either way the
    derived data is served: the promoted envelope (produced_at, e_ids,
    provenance, producer_version) is KEPT when a row exists, and a server
    stamp fills in when it does not — the normal case is a producer that
    promoted only the envelope, since H9 has no prompt and `fields: {}`.
    """
    env = built["env"] if built else {}
    stamps = built["stamps"] if built else {}
    promoted_data = built["data"] if built else {}

    data, empty = read_value_chain(cur, entity, run_meta)
    if data is None:
        return {
            "data": None, "data_source": "empty",
            "provenance": stamps.get("provenance"),
            "produced_at": _iso(stamps.get("promoted_at")),
            "producer_version": stamps.get("producer_version"),
            "e_ids": env.get("e_ids") or [],
            "empty_state": empty,
        }

    # Promoted section-level fields (r_layer, narrative_thread) survive when
    # the producer set them; NULL columns are not data and do not.
    merged = {k: v for k, v in (promoted_data or {}).items() if v is not None}
    merged.update(data)

    # Same redaction path as every other heatmap section: server-side,
    # default-deny, honouring any internal_only marks on the promoted row.
    redacted, report = redact_section("heatmap", "value_chain", merged,
                                      env.get("internal_only"), audience)
    if redacted is None:                              # pragma: no cover
        return {
            "data": None, "data_source": "withheld", "provenance": None,
            "produced_at": None, "producer_version": None, "e_ids": [],
            "empty_state": {"kind": "withheld_for_audience",
                            "reason": "this surface is not served to the "
                                      "customer audience",
                            "sources_searched": []},
        }

    entry = {
        "data": redacted,
        "data_source": "server_derived",
        "provenance": stamps.get("provenance") or PROVENANCE,
        "produced_at": _iso(stamps.get("promoted_at"))
                       or run_meta.get("promoted_at"),
        "producer_version": stamps.get("producer_version") or PRODUCER_VERSION,
        "e_ids": env.get("e_ids") or [],
        # the derivation succeeded, so no empty state — a producer-submitted
        # one described the producer's absence, which the server just filled
        "empty_state": None,
    }
    if audience == "customer" and report["paths_stripped"]:
        entry["redacted_paths"] = report["paths_stripped"]
    return entry
