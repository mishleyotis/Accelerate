#!/usr/bin/env python3
"""Assemble the client DMA folder — the four deliverables, verified.

    python3 -m engine.assemble open    --run R [--out DIR] [--no-push]
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
import hashlib
import json
import re
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from . import contract as C
from . import completeness
from . import prelim, runstate, techscan, validator
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
    # No JSON copy of Entity_Timeline. Until 2026-08-30 the tab had a writer,
    # a gate and no reader, and a package extra was added to carry it; the
    # app's parser now reads the TAB itself (workbook_parser maps
    # Entity_Timeline to context.timeline / context.acquisitions) and never
    # read the copy, so the copy was the F-J02-011 shape: written, read by
    # nothing, one more place for the same rows to drift.
)


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def folder_name(entity_name: str) -> str:
    """'<Entity> - DMA', the intake tree's own convention."""
    name = str(entity_name or "").strip()
    return name if name.endswith("- DMA") else f"{name} - DMA"


# ── the timeline the served C1 surface reads ─────────────────────────────

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


#: The manifest's ONE shape. The schema beside this module is the contract
#: every reader keys on; `write_manifest` refuses a document that fails it.
#: Measured 28-09-2026 (QA audit F-N01-019): three incompatible manifests —
#: this module's, a "run_manifest_v2" the assessment skill's governance
#: exporter built from CLI flags, and a flat shape the governance auditor
#: demanded that nothing wrote — so the auditor's IV-02 was CRITICAL on
#: every real run and calibration read "unknown" for every institution.
MANIFEST_SCHEMA_VERSION = "run_manifest_v3"
SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "run_manifest.schema.json"


class ManifestInvalid(ValueError):
    """run_manifest.json would not satisfy its schema; nothing was written."""


@lru_cache(maxsize=1)
def manifest_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_manifest(doc) -> list[str]:
    """Every way `doc` departs from the schema, or [].

    With `jsonschema` installed (plugins/dma-insights/requirements.txt) the
    whole schema is checked. Without it the required keys, the closed key
    set and the schema_version constant are checked — a container that lacks
    the library still cannot write a manifest with a key nobody reads."""
    schema = manifest_schema()
    try:
        import jsonschema                                        # noqa: PLC0415
    except ImportError:
        jsonschema = None
    if jsonschema is not None:
        v = jsonschema.Draft7Validator(schema)
        errs = sorted(v.iter_errors(doc),
                      key=lambda e: [str(p) for p in e.absolute_path])
        return [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: "
                f"{e.message}" for e in errs]
    if not isinstance(doc, dict):
        return ["<root>: not an object"]
    out = [f"<root>: '{k}' is a required property"
           for k in schema["required"] if k not in doc]
    if doc.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        out.append(f"schema_version: {doc.get('schema_version')!r} is not "
                   f"{MANIFEST_SCHEMA_VERSION!r}")
    extra = sorted(set(doc) - set(schema["properties"]))
    if extra:
        out.append(f"<root>: unexpected keys {extra}")
    return out


def write_manifest(path, doc: dict) -> Path:
    """The ONE writer of run_manifest.json: validated first, then written.

    A manifest that fails its schema is not written at all — every reader
    (the app's package scan, the watchdog, gold_standard, the governance
    auditor, calibration) keys on this file being what it says it is, and a
    half-right manifest is the F-N01-019 shape."""
    problems = validate_manifest(doc)
    if problems:
        raise ManifestInvalid("run_manifest.json refused by its schema:\n  "
                              + "\n  ".join(problems))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")
    return path


def _manifest_num(v):
    try:
        return None if v is None or str(v).strip() == "" else float(v)
    except (TypeError, ValueError):
        return None


def _manifest_str(v):
    return None if v is None or str(v).strip() == "" else str(v)


def _scores(wb: RunWorkbook):
    """The scoring stage's own roll-ups, or None before it has written them."""
    pillars = {str(r.get("pillar_id")): _manifest_num(r.get("score"))
               for r in wb.rows("Pillar_Rollup") if r.get("pillar_id")}
    cats = {str(r.get("category_id")): _manifest_num(r.get("score"))
            for r in wb.rows("Category_Rollup") if r.get("category_id")}
    overall = None
    for r in wb.rows("Executive_Summary"):
        if str(r.get("Field") or "").strip() == "Overall Maturity":
            overall = _manifest_num(r.get("Value"))
    if not pillars and not cats and overall is None:
        return None
    return {"overall": overall, "pillars": pillars, "categories": cats}


def _evidence_metrics(wb: RunWorkbook) -> dict:
    dist: dict[str, int] = {t: 0 for t in C.TIERS}
    n = 0
    for r in wb.rows("Evidence_Detail"):
        n += 1
        t = str(r.get("Tier") or "").strip() or "UNTIERED"
        dist[t] = dist.get(t, 0) + 1
    return {"total_items": n, "tier_distribution": dist}


def _enrichment(wb: RunWorkbook) -> dict:
    """The connector's enrichment state as PRELIM seeded it (F-N06-014)."""
    from . import prelim                                         # noqa: PLC0415
    return prelim.enrichment_state(wb)


def _gates(wb: RunWorkbook) -> dict:
    out: dict = {}
    for r in wb.rows("Gate_Log"):
        g = str(r.get("Gate") or "").strip()
        if not g:
            continue
        key = g if not r.get("Scope") else f"{g}:{r.get('Scope')}"
        out[key] = {"verdict": str(r.get("Verdict") or ""),
                    "scope": _manifest_str(r.get("Scope")),
                    "at": _manifest_str(r.get("Timestamp")),
                    "detail": _manifest_str(r.get("Detail"))}
    return out


def _approvals(qa_dir) -> list[dict]:
    if not qa_dir:
        return []
    p = Path(qa_dir) / "approvals.json"
    if not p.is_file():
        return []
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return []
    recs = doc.get("approvals") if isinstance(doc, dict) else doc
    out = []
    for r in recs or []:
        if not isinstance(r, dict) or not r.get("tool"):
            continue
        out.append({"tool": str(r.get("tool")),
                    "cost_line": str(r.get("cost_line") or ""),
                    "approved_by": str(r.get("approved_by") or ""),
                    "at": _manifest_str(r.get("at")),
                    "expires": _manifest_str(r.get("expires"))})
    return out


def _packets(run) -> dict:
    """Every machine packet the run has written, hashed, so a consumer can
    tell the packet this manifest vouches for from a stale or edited one."""
    if run is None:
        return {}
    from . import handoff                                        # noqa: PLC0415
    out: dict = {}
    hp = Path(run.deliverables) / handoff.HANDOFF_NAME
    if hp.is_file():
        try:
            doc = json.loads(hp.read_text(encoding="utf-8"))
            sv = (doc.get("_contract") or {}).get("schema_version")
        except (ValueError, AttributeError):
            sv = None
        out["research_handoff"] = {
            "path": hp.name,
            "sha256": hashlib.sha256(hp.read_bytes()).hexdigest(),
            "schema_version": _manifest_str(sv),
            "verified": not handoff.verify_packet(hp),
        }
    from . import assessment as _A                               # noqa: PLC0415
    sp = Path(run.qa_dir) / _A.SCORING_NAME
    if sp.is_file():
        try:
            sdoc = json.loads(sp.read_text(encoding="utf-8"))
            ssv = (sdoc.get("_contract") or {}).get("schema_version")
        except (ValueError, AttributeError):
            ssv = None
        out["scoring"] = {
            "path": f"07_qa/{sp.name}",
            "sha256": hashlib.sha256(sp.read_bytes()).hexdigest(),
            "schema_version": _manifest_str(ssv),
            "verified": not handoff.verify_packet(
                sp, schema_version=_A.SCORING_SCHEMA_VERSION),
        }
    return out


def _decision_log_ref(run) -> str | None:
    from . import registry                                       # noqa: PLC0415
    try:
        p = registry.registry_path(Path(run.root).parent if run is not None else None)
    except Exception:                                            # noqa: BLE001
        return None
    return str(p) if p.is_file() else None


def manifest_doc(wb: RunWorkbook, *, status: str = "COMPLETE",
                 opened_at: str | None = None, stage: str = "PACKAGE",
                 run: runstate.Run | None = None) -> dict:
    """The run's identity anchor in its ONE shape (run_manifest_v3).

    Everything here is read from the workbook or computed from the run —
    never typed on a command line. `scores` is None until the scoring stage
    has written its roll-ups; `decision_log_ref` is None unless the registry
    file exists; an approval appears only when the owner wrote one."""
    md = wb.metadata()
    qa_dir = run.qa_dir if run is not None else None
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "status": status,
        "stage": stage,
        "opened_at": _manifest_str(opened_at or md.get("client_folder_opened_at")),
        "checkpointed_at": None,
        "run_id": str(md.get("run_id") or ""),
        "institution": {"name": str(md.get("entity_name") or ""),
                        "entity_id": _manifest_str(md.get("entity_id")),
                        "sub_vertical": _manifest_str(md.get("sub_vertical"))},
        "evidence_mode": _manifest_str(md.get("evidence_mode")),
        "scope_mode": _manifest_str(md.get("scope_mode")),
        "reference_date": _manifest_str(md.get("reference_date")),
        "catalogue_version": _manifest_str(md.get("catalogue_version")),
        "catalogue_hash": _manifest_str(md.get("catalogue_hash")),
        "workbook_contract": _manifest_str(md.get("workbook_contract")),
        "engine_version": _manifest_str(md.get("engine_version")),
        "assembled_at": _utcnow(),
        "deliverables": [d[1] for d in DELIVERABLES],
        "packets": _packets(run),
        "gates": _gates(wb),
        "approvals": _approvals(qa_dir),
        "decision_log_ref": _decision_log_ref(run),
        "scores": _scores(wb),
        "evidence_metrics": _evidence_metrics(wb),
        "enrichment": _enrichment(wb),
    }


# ── the folder exists from the first minute of the run ───────────────────

def default_folder_root(run: runstate.Run) -> Path:
    """Where the client folder lives locally: beside the run tree.

    Beside, not inside: the run tree is working area that `strip` prunes and
    the container discards, and the client folder is the deliverable. A
    folder nested in the thing that gets cleaned up is a folder that gets
    cleaned up."""
    return Path(run.root).parent


#: Where a superseded package is kept, INSIDE the client folder that already
#: exists. Never a second client folder: `runs.source_folder_id` keys on the
#: folder, and renaming or forking it orphans every run that came before.
ARCHIVE_DIR = "_superseded"


def _archive_existing(dest: Path, wb) -> dict:
    """Move a previous run's package aside before this one is written.

    THE DEFECT THIS CLOSES, measured 2026-08-30. `folder_name()` is a pure
    function of the entity name and `default_folder_root()` is the shared run
    root, so two runs of the same client resolved to ONE directory — and
    nothing noticed. `open_folder` reported `created: false` and overwrote
    `run_manifest.json` with the second run's identity; `package` copied the
    second run's deliverables in beside the first's and overwrote all three
    fixed-name machine extras. The deliverables themselves carry the
    reference date, so a second run on a different date left TWO scoring
    workbooks in one folder, and the app's package scan keeps exactly one
    artefact per kind — chosen by rank and then by iteration order. The
    client folder became a mix of two runs with an arbitrary winner.

    THE SHAPE IS THE ONE THIS SYSTEM ALREADY USES. Server-side, an entity has
    N runs, exactly one active, and promotion demotes its predecessor to
    SUPERSEDED and RETAINS it (the charter's own default). This mirrors that
    on the folder: the CURRENT package is at the folder root, where every
    reader already looks, and each previous one moves whole into
    `_superseded/<run_id>/`. Nothing is deleted, the folder keeps its name
    and its id, and a reader who wants the history knows where it is.
    """
    md = wb.metadata()
    prior = dest / "run_manifest.json"
    if not prior.is_file():
        return {"archived": None, "reason": "no previous package here"}
    try:
        was = json.loads(prior.read_text())
    except ValueError:
        was = {}
    prior_run = str(was.get("run_id") or "").strip()
    if not prior_run or prior_run == str(md.get("run_id") or ""):
        # Same run re-opening its own folder: idempotent, not a supersede.
        return {"archived": None, "reason": "same run"}

    stamp = str(was.get("opened_at") or was.get("generated_at") or "")[:10]
    home = dest / ARCHIVE_DIR / (f"{prior_run}_{stamp}" if stamp else prior_run)
    if home.exists():
        return {"archived": str(home), "reason": "already archived"}
    home.mkdir(parents=True, exist_ok=True)
    moved = []
    for item in sorted(dest.iterdir()):
        if item.name == ARCHIVE_DIR:
            continue
        shutil.move(str(item), str(home / item.name))
        moved.append(item.name)
    (home / "SUPERSEDED.json").write_text(json.dumps({
        "run_id": prior_run,
        "superseded_by": md.get("run_id"),
        "superseded_at": _utcnow(),
        "entity_name": was.get("entity_name"),
        "note": ("This package was the client folder's current one until the "
                 "run named in superseded_by assembled. It is RETAINED, per "
                 "the charter's default for superseded runs, and it is here "
                 "rather than in a second client folder because "
                 "runs.source_folder_id keys on the folder itself."),
    }, indent=2, default=str))
    return {"archived": str(home), "run_id": prior_run, "moved": moved}


def _dest_folder(run: runstate.Run, md: dict, entity: str, out_root) -> Path:
    """Where this run's client folder IS — recorded, not recomputed.

    THE DEFECT THIS CLOSES, found by the stress walk on 2026-08-30.
    `open_folder` writes `client_folder` into the workbook and calls the
    folder "the run's public identity"; `package` then recomputed the same
    path from `out_root or default_folder_root(run)` and never read what was
    recorded. Give the two different roots — which the CLI allows, since
    `--out` is per-command — and the run ends with TWO `<Entity> - DMA`
    directories: the manifest, the evidence and the supersession archive in
    one, the four deliverables in the other. `runs.source_folder_id` keys on
    a folder, so the app scans one of them and the other is orphaned, which
    is AUD-0170 with the halves swapped.

    An EXPLICIT `out_root` still wins: a caller naming a destination means
    it. And the recorded path is honoured only when its parent exists,
    because `client_folder` is an absolute path in the container that wrote
    it — a run resumed on a fresh container must fall back to the default
    root rather than chase a directory that is not there.
    """
    if out_root:
        return Path(out_root) / folder_name(entity)
    recorded = str(md.get("client_folder") or "").strip()
    if recorded and Path(recorded).parent.is_dir():
        return Path(recorded)
    return default_folder_root(run) / folder_name(entity)


def open_folder(run: runstate.Run, out_root=None, *, push: bool = True) -> dict:
    """Create '<Entity> - DMA' NOW, at run start, and say so in the workbook.

    WHY AT START. The Golden 1 calibration finished a category, wrote twenty
    evidence rows and six syntheses, and created no client folder — because
    folder creation lived in `package`, which runs at the END and refuses
    until all four deliverables exist. A run that stops early therefore
    leaves NOTHING an operator can find: no folder in the intake Drive, no
    manifest, no trace that the engagement was ever started. The folder is
    the run's public identity, so it is created with the run and carries
    `status: IN_PROGRESS` until `package` completes it.

    Idempotent: re-opening an existing folder refreshes the manifest and
    reports `created: false`. Pushing is best-effort and HONEST — a Drive
    that could not be reached is reported NOT_RUN with the reason, never
    silently skipped, because a folder that exists only in this container is
    exactly the state this function exists to prevent."""
    wb = run.open()
    md = wb.metadata()
    entity = str(md.get("entity_name") or run.run_id)
    dest = _dest_folder(run, md, entity, out_root)
    created = not dest.exists()
    dest.mkdir(parents=True, exist_ok=True)
    # A SECOND run for this client does not get a second folder — it
    # supersedes the one that is here, and the one that is here is kept.
    superseded = _archive_existing(dest, wb)
    (dest / "01_evidence").mkdir(exist_ok=True)

    opened = str(md.get("client_folder_opened_at") or "").strip() or _utcnow()
    manifest = manifest_doc(wb, status="IN_PROGRESS", opened_at=opened,
                            stage="OPENED", run=run)
    manifest["deliverables_expected"] = [d[1] for d in DELIVERABLES]
    manifest["deliverables_present"] = []
    mpath = write_manifest(dest / "run_manifest.json", manifest)

    wb.set_metadata("client_folder", str(dest))
    wb.set_metadata("client_folder_opened_at", opened)

    out = {"folder": str(dest), "entity": entity, "created": created,
           "status": "IN_PROGRESS", "opened_at": opened,
           "superseded": superseded}
    out["pushed"] = _push_one(mpath, entity, "run_manifest.json") if push \
        else {"outcome": "NOT_RUN", "reason": "push disabled by caller"}
    return out


def _push_one(local: Path, entity: str, remote: str) -> dict:
    """One file to the client's intake folder, creating it if new."""
    df = Path(__file__).resolve().parents[3] / "scripts" / "drive_fetch.py"
    if not df.exists():
        return {"outcome": "NOT_RUN",
                "reason": "drive_fetch.py is not in this install"}
    r = subprocess.run(
        [sys.executable, str(df), "push-package", "--client", entity,
         "--file", str(local), "--name", remote],
        capture_output=True, text=True, timeout=600)
    if r.returncode == 0:
        return {"outcome": "RESOLVED", "detail": (r.stdout or "").strip()[-200:]}
    return {"outcome": "FAILED",
            "reason": (r.stderr or r.stdout or "").strip()[-300:]}


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
    dest = _dest_folder(run, md, entity, out_root)

    # A workbook that validates and carries nothing is the Golden 1 shape.
    # The package is where it would reach a client, so it is refused here.
    try:
        completeness.require(wb)
    except completeness.CompletenessRefusal as e:
        raise SystemExit(f"REFUSED: {e}") from None

    # And PRELIM. `prelim.require_complete` described itself as "the gate
    # orient calls" and NOTHING called it — not orient, not handoff, not
    # here — so a package could ship with the institution unprofiled and the
    # client research report written over the hole. The package is the last
    # point where that is still cheap to say.
    try:
        prelim.require_complete(wb)
    except prelim.PrelimRefusal as e:
        raise SystemExit(f"REFUSED: {e}") from None

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
    write_manifest(dest / "run_manifest.json",
                   manifest_doc(wb, status="COMPLETE", stage="PACKAGE", run=run))
    (dest / "01_evidence" / "evidence_index.json").write_text(
        json.dumps(evidence_index_doc(wb), indent=2, default=str))
    ts_json = run.deliverables / techscan.JSON_NAME
    if ts_json.exists():
        shutil.copy2(ts_json, dest / techscan.JSON_NAME)

    report = verify(dest)
    out = {"folder": str(dest), "entity": entity,
           "deliverables": {k: str(v.name) for k, v in found.items()},
           "verified": report["complete"], "verification": report}
    if push and not report["complete"]:
        # The verify step ran and said no; the folder is built and stays on
        # disk for repair, and it does not leave the machine (QA audit
        # F-M08-013, 28-09-2026: the push used to happen regardless).
        out["pushed"] = {"refused": True,
                         "why": "the package did not verify — repair the checks "
                                "named in `verification`, re-package, then push"}
    elif push:
        out["pushed"] = _push(dest, entity)
    return out


def checkpoint(run: runstate.Run, out_root, *, push: bool = False,
               stage_reached: str = "") -> dict:
    """Copy the CURRENT workbook and an IN_PROGRESS manifest into the client
    folder — at a stage boundary, not every hour.

    Owner, 2026-09-03 (issue 7): the app should be receiving the assessment
    as it progresses, not in one transport exercise at the end. The package
    scan ingests the folder; every changed workbook it sees is a run version.
    So this is called at TWO boundaries the conductor names — the SCORING gate
    PASS (the app can ingest a scored run and page production can start) and
    both reports READY — and refuses at any other time, because eighteen
    versions with zero scored cells is what an hourly push produced for one
    client. `package` at the end supersedes it with the complete set."""
    wb = run.open()
    md = wb.metadata()
    scoring_pass = any(str(g.get("Gate")) == "SCORING"
                       and str(g.get("Verdict")).upper() == "PASS"
                       for g in wb.rows("Gate_Log"))
    if not scoring_pass:
        raise SystemExit(
            "REFUSED: a checkpoint is pushed only after the SCORING gate has "
            "PASSED — a research-stage workbook in the intake tree is a run "
            "version with zero scored cells, which the scan will ingest and "
            "serve as one. Finish scoring (`engine.assessment gate`) first.")
    entity = str(md.get("entity_name") or run.run_id)
    dest = _dest_folder(run, md, entity, out_root)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(run.workbook_path, dest / run.workbook_path.name)
    doc = manifest_doc(wb, status="IN_PROGRESS",
                       stage=stage_reached or "SCORING_PASS", run=run)
    doc["checkpointed_at"] = _utcnow()
    write_manifest(dest / "run_manifest.json", doc)
    out = {"folder": str(dest), "entity": entity, "stage_reached": doc["stage"],
           "files": [run.workbook_path.name, "run_manifest.json"]}
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

    # THE GOLD GATE, AT VERIFY TIME. Until 2026-09-03 `engine.gold_standard`
    # was an instruction in the agents' manifests — "run it on your own output
    # before you return" — and nothing in the pipeline ran it. A package is
    # complete only when the Golden 1 gate has nothing to say about it; each
    # finding is repaired at its source (the workbook or the section), never
    # in the rendered file.
    from . import gold_standard as GS
    gold = [str(f) for f in GS.package_findings(folder)] if all(
        c["ok"] for c in checks if c["check"].startswith("deliverable:")) else [
        "gold gate not run: a deliverable is missing"]
    check("gold_standard", not gold,
          "PASS — 0 findings" if not gold else
          f"{len(gold)} finding(s); run `python3 -m engine.gold_standard package "
          f"<folder>` and repair each at its source: " + "; ".join(gold[:4]))

    complete = all(c["ok"] for c in checks)
    return {"folder": str(folder), "complete": complete, "checks": checks,
            "gold_findings": gold}


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
    o = sub.add_parser("open", help="create '<Entity> - DMA' NOW, at run "
                                    "start, so a run that stops early is "
                                    "still findable")
    o.add_argument("--run", required=True)
    o.add_argument("--root")
    o.add_argument("--out")
    o.add_argument("--no-push", action="store_true")
    v = sub.add_parser("verify")
    v.add_argument("--folder", required=True)
    ck = sub.add_parser("checkpoint",
                        help="copy the CURRENT workbook + an IN_PROGRESS "
                             "manifest into the client folder at a stage "
                             "boundary (after the SCORING gate PASSes), so the "
                             "scan ingests a scored run while the reports are "
                             "still being written")
    ck.add_argument("--run", required=True)
    ck.add_argument("--root")
    ck.add_argument("--out")
    ck.add_argument("--push", action="store_true")
    ck.add_argument("--stage", default="",
                    help="the boundary reached, e.g. SCORING_PASS or REPORTS_READY")
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
    if a.cmd == "open":
        print(json.dumps(open_folder(run, a.out, push=not a.no_push),
                         indent=2, default=str))
        return 0
    if a.cmd == "checkpoint":
        print(json.dumps(checkpoint(run, Path(a.out) if a.out else None,
                                    push=a.push, stage_reached=a.stage),
                         indent=2, default=str))
        return 0
    out = package(run, Path(a.out) if a.out else None, push=a.push)
    print(json.dumps(out, indent=2, default=str))
    return 0 if out["verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
