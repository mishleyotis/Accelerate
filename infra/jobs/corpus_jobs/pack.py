"""The corpus pack — one measurement per promoted client, in one object.

The TRD gives `pack-exporter` two outputs: "Scorecard PDF via headless
Chromium, and the corpus pack the scanner reads". This module is the second.
The PDF is not built here: it needs headless Chromium in the image and a
rendered page to shoot, both of which belong to the export stage that owns
the scorecard's layout. A Job that shipped an empty PDF beside a real pack
would be worse than one that ships the pack and says the PDF is not built.

## What a pack row is, and what it deliberately is not

Counters, and the denominators that make them rates. Not scores, not prose,
not anything a client would read. Every figure is COUNTED from the serving
tier at export time rather than read from a stored total (invariant 8), and
every one of them has a denominator beside it — a gate that fires on "11
thin cells" fires differently on a 765-cell run and a 100-cell run, and a
ceiling expressed against no denominator is not a rate.

Nothing here judges. The pack states `unknown_assessment_date: 1 of 1`; it is
`gate_scan` that holds that against a ceiling, and only for the gates
`packages/shared/corpus_gates.json` actually configures.

## Why the pack exists at all rather than the scanner reading the database

Because a corpus gate is a claim about the corpus AT A MOMENT. Re-measuring
from live tables at every scan means a regression can appear and vanish
between two runs of the same check with nothing to point at. The pack is
dated, immutable and kept, so a failing gate names an object a person can
open.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

#: The six promoted pages and their per-run serving tables — the same map
#: `dma_api.main._PAGE_TABLES` serves from. A page with no row for a run did
#: not promote, which is the corpus's most consequential defect class.
PAGE_TABLES = {
    "overview": "overview_scores",
    "heatmap": "heatmap_workbook_scores",
    "insights": "insight_cards",
    "platform": "platform_story",
    "context": "context_timeline",
    "techstack": "techstack_items",
}

PACK_SCHEMA = "corpus_pack_v1"


def _one(cur, sql, params=()):
    cur.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row else 0


def measure_run(cur, run_id: str) -> dict:
    """Every counter in the pack, for one promoted run, with denominators.

    One query per counter rather than a wide join: a page that failed to
    promote returns no row, and a join would flatten "absent" and "empty"
    into the same NULL — the distinction this pack exists to carry.
    """
    pages = {}
    for page, table in PAGE_TABLES.items():
        pages[page] = _one(cur, f"SELECT count(*) FROM {table} WHERE run_id = %s",
                           (run_id,))

    cells = _one(cur, "SELECT count(*) FROM serving_subcaps WHERE run_id = %s",
                 (run_id,))
    thin = _one(cur, "SELECT count(*) FROM serving_subcaps "
                     "WHERE run_id = %s AND is_thin_evidence", (run_id,))
    unnamed = _one(cur, "SELECT count(*) FROM serving_subcaps "
                        "WHERE run_id = %s AND subcap_name IS NULL", (run_id,))
    unscored = _one(cur, "SELECT count(*) FROM serving_subcaps "
                         "WHERE run_id = %s AND score IS NULL", (run_id,))
    alerts_open = _one(cur, "SELECT count(*) FROM heatmap_alerts "
                            "WHERE run_id = %s AND status = 'open'", (run_id,))
    gates_not_run = _one(cur, "SELECT count(*) FROM gate_results "
                              "WHERE run_id = %s AND result = 'NOT_RUN'", (run_id,))
    gates_total = _one(cur, "SELECT count(*) FROM gate_results WHERE run_id = %s",
                       (run_id,))
    return {
        "pages_promoted": sum(1 for n in pages.values() if n),
        "pages_expected": len(PAGE_TABLES),
        "page_rows": pages,
        "cells": cells,
        "cells_thin_evidence": thin,
        "cells_without_catalogue_name": unnamed,
        "cells_without_score": unscored,
        "alerts_open": alerts_open,
        "gates_recorded": gates_total,
        "gates_not_run": gates_not_run,
    }


def build_pack(cur, as_of: datetime | None = None) -> dict:
    """The whole corpus, as one dated object.

    Read entirely through `serving_directory` and the serving tables — the
    same window svc_api serves from. A pack that measured the ingested tier
    would report defects no reader can see and miss the ones they can.
    """
    as_of = as_of or datetime.now(timezone.utc)
    cur.execute(
        """SELECT display_id, legal_name, sub_vertical, run_id, request_id,
                  run_seq, composite, scored_cells, catalogue_cells,
                  ccg_catalog_version, promoted_at, assessment_date,
                  assessment_date_basis, refresh_due_date
             FROM serving_directory
            WHERE is_active
            ORDER BY display_id""")
    rows = cur.fetchall()

    clients = []
    for (display_id, name, sub_vertical, run_id, request_id, run_seq, composite,
         scored_cells, catalogue_cells, version, promoted_at, adate, basis,
         due) in rows:
        entry = {
            "display_id": display_id,
            "entity_name": name,
            "sub_vertical": sub_vertical,
            "run_id": str(run_id),
            "request_id": request_id,
            "run_seq": run_seq,
            "composite": float(composite) if composite is not None else None,
            "scored_cells": scored_cells,
            "catalogue_cells": catalogue_cells,
            "ccg_catalog_version": version,
            "promoted_at": promoted_at.isoformat() if promoted_at else None,
            # The cadence, in the pack, because "share of the corpus whose
            # assessment date was reverse-engineered rather than stated" is
            # exactly the shape of thing a ceiling should ratchet down.
            "assessment_date": adate.isoformat() if adate else None,
            "assessment_date_basis": basis,
            "assessment_date_is_stated": basis == "STATED",
            "refresh_due_date": due.isoformat() if due else None,
            "refresh_overdue": (bool(due and due < as_of.date())
                                if due else None),
        }
        entry.update(measure_run(cur, run_id))
        clients.append(entry)

    return {
        "$schema": PACK_SCHEMA,
        "generated_at": as_of.isoformat(),
        "clients": clients,
        "counts": {
            "clients": len(clients),
            # Every corpus figure keeps its denominator: a count with no
            # denominator is not a rate and cannot be ratcheted.
            "cells": sum(c["cells"] for c in clients),
            "pages_promoted": sum(c["pages_promoted"] for c in clients),
            "pages_expected": sum(c["pages_expected"] for c in clients),
        },
        "note": ("Counters only. Nothing here is judged; the ceilings in "
                 "packages/shared/corpus_gates.json are applied by "
                 "corpus-gate-scanner against this object."),
    }


def pack_bytes(pack: dict) -> bytes:
    """Stable bytes: sorted keys, so two packs of an unchanged corpus differ
    only where the corpus differs and a diff is worth reading."""
    return json.dumps(pack, indent=1, sort_keys=True,
                      default=str).encode("utf-8")
