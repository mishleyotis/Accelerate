#!/usr/bin/env python3
"""Assemble the client DMA folder — the four deliverables, verified.

    python3 -m engine.assemble package --run R [--out DIR] [--push]
    python3 -m engine.assemble verify  --folder "<Entity> - DMA"
    python3 -m engine.assemble contract

THE OUTPUT CONTRACT. A finished engagement ships ONE folder named
'<Entity> - DMA' (the intake tree's own convention — e.g. 'Baxter Credit
Union - DMA') whose root holds exactly the four final outputs:

    DMA_Scoring_Workbook_<entity>_<date>.xlsx      the substrate itself
    Client_Profile_Research_<entity>_<date>.docx   the research report
    DMA_Assessment_Report_<entity>_<date>.docx     the assessment report
    Technographic_Scan_<entity>_<date>.docx        the technographic scan

plus the machine extras the app's ingest reads:

    run_manifest.json                the identity anchor (classifier rank 0)
    01_evidence/evidence_index.json  the URL-bearing evidence copy — gate M
                                     exists because a package shipped 85%
                                     unURLed while this file carried 748
                                     URLs nothing read (AUD-0091)
    technographic_scan.json          the scan, machine-readable

Every filename below is asserted against the app's own classifier patterns
by test (apps/worker/tests), so 'seamless loading onto the web app' is a
tested property, not a hope: `verify` re-checks a built folder and REFUSES
to call a package complete while any deliverable is missing, misnamed, or
fails the workbook contract.
"""
from __future__ import annotations

# Runnable both ways: -m engine.assemble, or by path for --help.
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
import shutil
import subprocess
import sys
from pathlib import Path

from . import contract as C
from . import runstate, techscan, validator
from .workbook import RunWorkbook, _split_ids

#: The four final outputs, as (key, glob pattern, app classifier kind).
#: The patterns are the renderers' own filename contracts; the kinds are
#: what apps/worker/dma_worker/classification.py must return for them —
#: asserted by test on the app side, restated here so the plugin can verify
#: a folder without importing the app.
DELIVERABLES = (
    ("scoring_workbook", "DMA_Scoring_Workbook_*.xlsx", "scoring_workbook"),
    ("research_report", "Client_Profile_Research_*.docx", "client_profile"),
    ("assessment_report", "DMA_Assessment_Report_*.docx", "assessment_report"),
    ("technographic_scan", "Technographic_Scan_*.docx", "technographic_scan"),
)

MACHINE_EXTRAS = (
    ("run_manifest", "run_manifest.json"),
    ("evidence_index", "01_evidence/evidence_index.json"),
    ("techscan_json", "technographic_scan.json"),
)


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def folder_name(entity_name: str) -> str:
    """'<Entity> - DMA', the intake tree's own convention."""
    name = str(entity_name or "").strip()
    return name if name.endswith("- DMA") else f"{name} - DMA"


# ── the evidence index the app reads (AUD-0091's other half) ─────────────

def evidence_index_doc(wb: RunWorkbook) -> dict:
    """The package's evidence_index.json, in the field spellings the app's
    parse_evidence_index already accepts — emitted FROM the workbook, so the
    two cannot disagree."""
    md = wb.metadata()
    items = []
    for r in wb.rows("Evidence_Detail"):
        items.append({
            "evidence_id": r.get("E_ID"),
            "source_name": r.get("Source_Name"),
            "url": r.get("Source_URL"),
            "tier": r.get("Tier"),
            "ers": r.get("ERS"),
            "date_published": r.get("Date_Published"),
            "recency": r.get("Recency"),
            "claim_type": r.get("Claim_Type"),
            "fact_count": r.get("Fact_Count"),
            "subcaps_supported": ", ".join(_split_ids(r.get("SubCap_IDs"))),
            "excerpt": r.get("Excerpt"),
        })
    return {"run_id": md.get("run_id"), "entity_id": md.get("entity_id"),
            "generated_at": _utcnow(), "items": items}


def manifest_doc(wb: RunWorkbook) -> dict:
    md = wb.metadata()
    return {
        "run_id": md.get("run_id"),
        "institution": {"name": md.get("entity_name"),
                        "entity_id": md.get("entity_id"),
                        "sub_vertical": md.get("sub_vertical")},
        "evidence_mode": md.get("evidence_mode"),
        "scope_mode": md.get("scope_mode"),
        "reference_date": md.get("reference_date"),
        "catalogue_version": md.get("catalogue_version"),
        "catalogue_hash": md.get("catalogue_hash"),
        "workbook_contract": md.get("workbook_contract"),
        "engine_version": md.get("engine_version"),
        "assembled_at": _utcnow(),
        "deliverables": [d[1] for d in DELIVERABLES],
    }


# ── assembly ─────────────────────────────────────────────────────────────

def package(run: runstate.Run, out_root, *, push: bool = False) -> dict:
    """Build '<Entity> - DMA' from the run's deliverables, then verify it.

    Assembly COPIES, never moves: the run tree stays intact for the audit.
    Missing deliverables refuse the package with the render command that
    would produce each — an unattended session must be able to act on the
    refusal, not just read it."""
    wb = run.open()
    md = wb.metadata()
    entity = str(md.get("entity_name") or run.run_id)
    dest = Path(out_root) / folder_name(entity)

    missing = []
    found: dict[str, Path] = {}
    for key, pattern, _kind in DELIVERABLES:
        hits = sorted(run.deliverables.glob(pattern)) if key != \
            "scoring_workbook" else ([run.workbook_path]
                                     if run.workbook_path.exists() else [])
        if hits:
            found[key] = hits[-1]
        else:
            fix = {
                "research_report": "engine.cli report --report client_research",
                "assessment_report": "engine.cli report --report assessment",
                "technographic_scan": "engine.techscan render",
            }.get(key, "engine.cli start")
            missing.append(f"{key} ({pattern}) — produce it with: {fix}")
    if missing:
        raise SystemExit("REFUSED: the package is not complete —\n  "
                         + "\n  ".join(missing))

    dest.mkdir(parents=True, exist_ok=True)
    (dest / "01_evidence").mkdir(exist_ok=True)
    for key, p in found.items():
        shutil.copy2(p, dest / p.name)
    (dest / "run_manifest.json").write_text(
        json.dumps(manifest_doc(wb), indent=2, default=str))
    (dest / "01_evidence" / "evidence_index.json").write_text(
        json.dumps(evidence_index_doc(wb), indent=2, default=str))
    ts_json = run.deliverables / techscan.JSON_NAME
    if ts_json.exists():
        shutil.copy2(ts_json, dest / techscan.JSON_NAME)

    report = verify(dest)
    out = {"folder": str(dest), "entity": entity,
           "deliverables": {k: str(v.name) for k, v in found.items()},
           "verified": report["complete"], "verification": report}
    if push:
        out["pushed"] = _push(dest, entity)
    return out


def _push(dest: Path, entity: str) -> dict:
    """Every file in the assembled folder to the client's intake folder on
    Drive, through drive_fetch push-package. Honest outcomes per file."""
    df = Path(__file__).resolve().parents[3] / "scripts" / "drive_fetch.py"
    if not df.exists():
        return {"outcome": "NOT_RUN",
                "reason": "drive_fetch.py is not in this install"}
    pushed, failed = [], []
    for p in sorted(dest.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(dest))
        r = subprocess.run(
            [sys.executable, str(df), "push-package", "--client", entity,
             "--file", str(p), "--name", rel],
            capture_output=True, text=True, timeout=600)
        (pushed if r.returncode == 0 else failed).append(
            {"file": rel, "detail": (r.stdout or r.stderr).strip()[-160:]})
    return {"outcome": "RESOLVED" if not failed else "PARTIAL",
            "pushed": pushed, "failed": failed}


# ── verification ─────────────────────────────────────────────────────────

def verify(folder) -> dict:
    """Is this folder a complete, ingestable package? Measured, per rule."""
    folder = Path(folder)
    checks = []

    def check(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    wb_path = None
    for key, pattern, kind in DELIVERABLES:
        hits = sorted(folder.glob(pattern))
        check(f"deliverable:{key}", bool(hits),
              (hits[-1].name if hits else f"nothing matches {pattern}"))
        if key == "scoring_workbook" and hits:
            wb_path = hits[-1]
    for key, rel in MACHINE_EXTRAS:
        p = folder / rel
        ok = p.is_file()
        detail = rel if ok else f"{rel} missing"
        if ok and p.suffix == ".json":
            try:
                json.loads(p.read_text())
            except ValueError as e:
                ok, detail = False, f"{rel} is not valid JSON: {e}"
        check(f"extra:{key}", ok, detail)

    if wb_path is not None:
        fails = validator.validate(wb_path)
        check("workbook_contract", not fails,
              "FAILS=0" if not fails else "; ".join(str(f) for f in fails[:4]))
        ei = folder / "01_evidence" / "evidence_index.json"
        if ei.is_file():
            try:
                items = json.loads(ei.read_text()).get("items") or []
                unurled = sum(1 for i in items if not i.get("url"))
                check("evidence_urls",
                      not items or unurled / len(items) <= 0.15,
                      f"{unurled} of {len(items)} items carry no URL"
                      + ("" if not items else
                         " — over 15% unURLed is the gate-M incident shape"
                         if unurled / len(items) > 0.15 else ""))
            except ValueError:
                pass

    name_ok = folder.name.endswith(" - DMA")
    check("folder_name", name_ok,
          folder.name if name_ok else
          f"{folder.name!r} does not follow '<Entity> - DMA'")

    complete = all(c["ok"] for c in checks)
    return {"folder": str(folder), "complete": complete, "checks": checks}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("package")
    p.add_argument("--run", required=True)
    p.add_argument("--root")
    p.add_argument("--out", help="where the '<Entity> - DMA' folder is "
                                 "created (default: beside the run tree)")
    p.add_argument("--push", action="store_true",
                   help="also push every file to the client's intake folder "
                        "on Drive (creates '<Entity> - DMA' there if new)")
    v = sub.add_parser("verify")
    v.add_argument("--folder", required=True)
    sub.add_parser("contract")
    a = ap.parse_args(argv)
    if a.cmd == "contract":
        print(json.dumps({
            "folder": "<Entity> - DMA",
            "final_outputs": [{"key": k, "pattern": p, "classifier_kind": c}
                              for k, p, c in DELIVERABLES],
            "machine_extras": [{"key": k, "path": p}
                               for k, p in MACHINE_EXTRAS],
        }, indent=2))
        return 0
    if a.cmd == "verify":
        out = verify(a.folder)
        print(json.dumps(out, indent=2))
        return 0 if out["complete"] else 1
    run = runstate.locate(a.run, Path(a.root) if a.root else None)
    out = package(run, Path(a.out) if a.out else run.root.parent, push=a.push)
    print(json.dumps(out, indent=2, default=str))
    return 0 if out["verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
