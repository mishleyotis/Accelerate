#!/usr/bin/env python3
"""The technographic scan — the fourth deliverable, from the Tech_Register.

    python3 -m engine.techscan record --run R --product ... --vendor ... \
        --layer OPS --status CONFIRMED --method public_document [...]
    python3 -m engine.techscan render --run R [--out DIR]
    python3 -m engine.techscan status --run R

WHAT IT IS. The client package's final outputs are four: the scoring
workbook, the research report, the assessment report, and THIS — the
technographic scan, the register of what technology the client demonstrably
runs, layer by layer, with the basis for every row. The serving-tier
techstack page is produced later by the connector agents; this scan is the
research-stage record they and the assessment draw on, and it ships to the
client folder as its own document.

THE VOCABULARY IS THE CHARTER'S, NOT THE PROTOTYPE'S. Four layers —
OPS · CUST · DATA · INFRA (never L2–L5, which collide with evidence levels)
— and four statuses with CLAIMED present and REQUIRED per row:

    CONFIRMED   independently evidenced (a technographic scan hit AND a
                second source, or a first-party artefact naming it live)
    INFERRED    one indirect signal (a job posting, an integration mention)
    CLAIMED     the client or the vendor says so, nobody else yet
    ABSENT      looked for and established missing — with the search that
                establishes it, because an unsearched estate is not absent
                (the AUD-0115 lesson: 'no register row' and 'confirmed
                absent' are different facts and conflating them over-
                recommended by 28 fit points)

Every row records HOW it was detected (`Detection_Method`), what the
detection rests on (`Detection_Basis`, one clause), and — for CONFIRMED —
the evidence ids that resolve in this run's register. The workbook stays
the substrate: `record` writes the Tech_Register sheet, `render` curates
the .docx and .json FROM it, and the two cannot disagree because there is
only one of them.
"""
from __future__ import annotations

# Runnable both ways: -m engine.techscan, or by path for --help.
if __package__ in (None, ""):  # noqa: E402
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import argparse
import datetime as _dt
import json
import re
import sys
from collections import Counter
from pathlib import Path

from . import contract as C
from . import runstate
from .workbook import RunWorkbook, _split_ids

#: The deliverable's filenames. The .docx is what a person reads; the .json
#: is what the app ingests (both are classified — the docx by name, the json
#: by the app's package_structured registry).
DOCX_NAME = "Technographic_Scan_{entity}_{date}.docx"
JSON_NAME = "technographic_scan.json"


class ScanRefused(SystemExit):
    pass


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", (s or "")).strip("_") or "client"


# ── recording, with the vocabulary enforced at the write ────────────────

def record(wb: RunWorkbook, *, product: str, vendor: str | None, layer: str,
           status: str, method: str, basis: str, subcaps=None,
           evidence_ids=None, source_urls=None,
           as_of: str | None = None) -> str:
    if layer not in C.TECH_LAYERS:
        raise ScanRefused(f"layer {layer!r} not in {C.TECH_LAYERS} — the "
                          f"prototype's L2-L5 keys collide with evidence "
                          f"levels and are refused by charter")
    if status not in C.TECH_STATUS:
        raise ScanRefused(f"status {status!r} not in {C.TECH_STATUS}")
    if method not in C.TECH_METHODS:
        raise ScanRefused(f"method {method!r} not in {C.TECH_METHODS}")
    if not str(product or "").strip():
        raise ScanRefused("a register row names a PRODUCT; a bare vendor or "
                          "a category is the CG-20 defect")
    if len(str(basis or "").strip()) < 15:
        raise ScanRefused("Detection_Basis is one real clause — what was "
                          "seen, where — not a token")
    eids = [e.strip() for e in (evidence_ids or []) if str(e).strip()]
    if status == "CONFIRMED":
        register = wb.evidence_index()
        if not eids:
            raise ScanRefused(
                "CONFIRMED requires evidence ids that resolve in this run — "
                "a confirmation nobody can open is a claim wearing a stronger "
                "word. Register the source first, or record the row as "
                "INFERRED/CLAIMED, which is what it currently is.")
        dead = [e for e in eids if e.split(":")[0] not in register]
        if dead:
            raise ScanRefused(f"CONFIRMED cites {dead}, which do not resolve "
                              f"in Evidence_Detail")
    if status == "ABSENT" and "search" not in str(basis).lower() and \
            "scan" not in str(basis).lower() and "0 hits" not in str(basis):
        raise ScanRefused(
            "ABSENT must state the search that establishes the absence — "
            "'no register row' and 'confirmed absent' are different facts, "
            "and conflating them over-recommends the estate (AUD-0115)")
    n = 1 + sum(1 for r in wb.rows("Tech_Register"))
    ts_id = f"TS-{n:03d}"
    wb.append("Tech_Register", {
        "TS_ID": ts_id, "Product": product.strip(),
        "Vendor": (vendor or "").strip() or None,
        "Layer": layer, "Status": status,
        "Evidence_Level": ("L1" if status == "CONFIRMED" else
                           "L2" if status == "INFERRED" else
                           "L3" if status == "CLAIMED" else "L4"),
        "Detection_Basis": basis.strip(), "Detection_Method": method,
        "SubCap_IDs": ", ".join(subcaps or []) or None,
        "Evidence_IDs": ", ".join(eids) or None,
        "Source_URLs": ", ".join(source_urls or []) or None,
        "As_Of": as_of or _utcnow()[:10],
    })
    return ts_id


def scan_state(wb: RunWorkbook) -> dict:
    rows = wb.rows("Tech_Register")
    by_layer = Counter(str(r["Layer"]) for r in rows)
    by_status = Counter(str(r["Status"]) for r in rows)
    return {
        "rows": len(rows),
        "by_layer": {l: by_layer.get(l, 0) for l in C.TECH_LAYERS},
        "by_status": {s: by_status.get(s, 0) for s in C.TECH_STATUS},
        "layers_never_looked_at": [l for l in C.TECH_LAYERS
                                   if by_layer.get(l, 0) == 0],
    }


# ── rendering: docx for people, json for the app ─────────────────────────

def render(wb: RunWorkbook, out_dir, *, force: bool = False) -> dict:
    md = wb.metadata()
    rows = wb.rows("Tech_Register")
    state = scan_state(wb)
    if not rows and not force:
        raise ScanRefused(
            "REFUSED: the Tech_Register is empty. A scan that ran and found "
            "nothing is renderable — record ABSENT rows with the searches "
            "that establish them, or pass --force to render the empty state "
            "as an explicit NOT_RUN document. A blank scan that looks like a "
            "clean scan is the defect.")
    entity = str(md.get("entity_name") or "client")
    date = str(md.get("reference_date"))[:10]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # the machine copy first — it is the one the app reads
    doc = {
        "artefact": "technographic_scan",
        "run_id": md.get("run_id"),
        "entity_name": entity,
        "entity_id": md.get("entity_id"),
        "reference_date": md.get("reference_date"),
        "generated_at": _utcnow(),
        "engine_version": md.get("engine_version"),
        "vocabulary": {"layers": list(C.TECH_LAYERS),
                       "statuses": list(C.TECH_STATUS)},
        "counts": state,
        "detections": [
            {"ts_id": r["TS_ID"], "product": r["Product"],
             "vendor": r["Vendor"], "layer": r["Layer"],
             "status": r["Status"], "evidence_level": r["Evidence_Level"],
             "detection_basis": r["Detection_Basis"],
             "detection_method": r["Detection_Method"],
             "subcap_ids": _split_ids(r.get("SubCap_IDs")),
             "evidence_ids": _split_ids(r.get("Evidence_IDs")),
             "source_urls": _split_ids(r.get("Source_URLs")),
             "as_of": r["As_Of"]} for r in rows],
        "not_run": (None if rows else
                    "the scan produced no register rows; this document "
                    "records that it RAN EMPTY, which is different from a "
                    "clean estate"),
    }
    json_path = out_dir / JSON_NAME
    json_path.write_text(json.dumps(doc, indent=2, default=str))

    from docx import Document
    from docx.shared import Pt, RGBColor
    d = Document()
    d.styles["Normal"].font.name = "Calibri"
    d.styles["Normal"].font.size = Pt(10.5)
    d.add_heading("Technographic Scan", level=0)
    d.add_paragraph(entity)
    d.add_paragraph(
        f"Run {md.get('run_id')} · reference date {date} · generated "
        f"{doc['generated_at']} · engine {md.get('engine_version')}")
    d.add_paragraph(
        "Every row below is read from the run's Tech_Register at render "
        "time. Four layers (OPS · CUST · DATA · INFRA), four statuses — and "
        "CLAIMED is a status, not a confirmation: a row says how it was "
        "detected and what that detection rests on, so a reader can weigh "
        "it rather than trust it.")
    d.add_heading("Coverage", level=1)
    t = d.add_table(rows=1, cols=3)
    t.style = "Light Grid Accent 1"
    for i, c in enumerate(("Layer", "Detections", "Statuses")):
        t.rows[0].cells[i].text = c
    for layer in C.TECH_LAYERS:
        cells = t.add_row().cells
        mine = [r for r in rows if str(r["Layer"]) == layer]
        cells[0].text = layer
        cells[1].text = str(len(mine))
        cells[2].text = ", ".join(
            f"{s}×{sum(1 for r in mine if str(r['Status']) == s)}"
            for s in C.TECH_STATUS
            if any(str(r["Status"]) == s for r in mine)) or "—"
    never = state["layers_never_looked_at"]
    if never:
        p = d.add_paragraph()
        r = p.add_run(
            f"NOT SCANNED: {', '.join(never)} — no detection was attempted "
            f"for these layers. That is a gap in the scan, not a clean "
            f"estate; nothing here may be read as ABSENT.")
        r.bold = True
        r.font.color.rgb = RGBColor(0xB0, 0x00, 0x20)
    d.add_heading("Register", level=1)
    if rows:
        t = d.add_table(rows=1, cols=7)
        t.style = "Light Grid Accent 1"
        for i, c in enumerate(("ID", "Product", "Vendor", "Layer", "Status",
                               "Basis", "As of")):
            t.rows[0].cells[i].text = c
        for r in rows:
            cells = t.add_row().cells
            for i, v in enumerate((r["TS_ID"], r["Product"], r["Vendor"],
                                   r["Layer"], r["Status"],
                                   r["Detection_Basis"], r["As_Of"])):
                cells[i].text = "" if v is None else str(v)
    else:
        p = d.add_paragraph()
        r = p.add_run("NOT RUN — the register is empty and this render was "
                      "forced. No detection, no absence, no estate claim.")
        r.bold = True
        r.font.color.rgb = RGBColor(0xB0, 0x00, 0x20)
    docx_path = out_dir / DOCX_NAME.format(entity=_slug(entity), date=date)
    d.save(docx_path)
    return {"docx": str(docx_path), "json": str(json_path),
            "detections": len(rows), "counts": state, "forced": not rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("record", "render", "status"):
        s = sub.add_parser(name)
        s.add_argument("--run", required=True)
        s.add_argument("--root")
        if name == "record":
            s.add_argument("--product", required=True)
            s.add_argument("--vendor")
            s.add_argument("--layer", required=True, choices=C.TECH_LAYERS)
            s.add_argument("--status", required=True, choices=C.TECH_STATUS)
            s.add_argument("--method", required=True, choices=C.TECH_METHODS)
            s.add_argument("--basis", required=True)
            s.add_argument("--subcap", action="append", default=[])
            s.add_argument("--evidence-id", action="append", default=[])
            s.add_argument("--url", action="append", default=[])
            s.add_argument("--as-of")
        if name == "render":
            s.add_argument("--out")
            s.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    run = runstate.locate(a.run, Path(a.root) if a.root else None)
    wb = run.open()
    if a.cmd == "record":
        ts = record(wb, product=a.product, vendor=a.vendor, layer=a.layer,
                    status=a.status, method=a.method, basis=a.basis,
                    subcaps=a.subcap, evidence_ids=a.evidence_id,
                    source_urls=a.url, as_of=a.as_of)
        print(json.dumps({"ts_id": ts, **scan_state(wb)}, indent=2))
        return 0
    if a.cmd == "render":
        out = render(wb, Path(a.out) if a.out else run.deliverables,
                     force=a.force)
        print(json.dumps(out, indent=2))
        return 0
    if a.cmd == "status":
        print(json.dumps(scan_state(wb), indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
