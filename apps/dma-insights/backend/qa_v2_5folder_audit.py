"""v2 QA — parse_package audit across the 5 real-sample folders.

Runs `parse_package` against each of the 5 in-repo packages
and prints a per-folder matrix of:
  - subcap_count / evidence_count / recommendations_count /
    peer_count / focus_area_count / leadership_count / warnings
  - firmographics fields populated
  - parser_warnings detail (top 5)

The goal is to quantify the under-leveraged information per folder
(versus what's PRESENT in the folder per the inventory in
qa_ingestion_under_leveraged.md). Output is written verbatim to
docs/qa/qa_evidence_snippets.txt.
"""
from __future__ import annotations
import json
import sys
import traceback
from pathlib import Path


def audit_one(folder: Path) -> dict:
    from app.services.parsers.dma_package import parse_package

    name = folder.name
    out: dict = {"folder": name, "status": "ok", "err": None}
    try:
        pkg = parse_package(folder)
    except Exception as exc:  # parser top-level failure
        out["status"] = "parse_failed"
        out["err"] = f"{type(exc).__name__}: {exc}"
        out["trace"] = traceback.format_exc(limit=4)
        return out

    out["request_id"] = getattr(pkg, "request_id", None) or getattr(
        pkg.run_manifest if pkg.run_manifest else None, "request_id", None
    )

    # Count what parse_package extracted.
    # IngestedPackage shape per dma_package.py docstring + CLAUDE.md.
    rm = pkg.run_manifest
    out["run_manifest_present"] = rm is not None
    if rm:
        # `run_manifest` is a dataclass or dict; introspect either way.
        if hasattr(rm, "__dataclass_fields__"):
            out["run_manifest"] = {
                k: getattr(rm, k) for k in rm.__dataclass_fields__
            }
        elif isinstance(rm, dict):
            out["run_manifest"] = rm

    fg = pkg.firmographics
    out["firmographics_present"] = fg is not None
    if fg:
        # firmographics dataclass per Batch 6 baseline; check populated fields
        fg_dict = (
            {k: getattr(fg, k) for k in fg.__dataclass_fields__}
            if hasattr(fg, "__dataclass_fields__")
            else dict(fg) if isinstance(fg, dict) else {}
        )
        populated = {k: v for k, v in fg_dict.items() if v not in (None, "", [], {})}
        out["firmographics_populated_fields"] = sorted(populated.keys())
        out["firmographics_count"] = len(populated)
        # Leadership specifically — often the failure point.
        leadership = fg_dict.get("leadership") or fg_dict.get("leaders") or []
        out["leadership_count"] = (
            len(leadership) if isinstance(leadership, (list, tuple)) else 0
        )
        parsed_facts = fg_dict.get("parsed_facts") or {}
        out["parsed_facts_keys"] = sorted(parsed_facts.keys()) if parsed_facts else []

    def _count(attr: str) -> int:
        val = getattr(pkg, attr, None)
        if val is None:
            return -1  # attribute not present on dataclass
        try:
            return len(val)
        except TypeError:
            return 0

    out["evidence_count"] = _count("evidence")
    out["subcap_scores_count"] = _count("subcap_scores")
    out["focus_areas_count"] = _count("focus_areas")
    out["recommendations_count"] = _count("recommendations")
    out["peer_scores_count"] = _count("peer_scores")
    out["report_sections_count"] = _count("report_sections")
    out["parser_warnings_count"] = _count("parser_warnings")
    pw = getattr(pkg, "parser_warnings", None)
    out["parser_warnings_top5"] = pw[:5] if pw else []
    out["parser_observations_count"] = _count("parser_observations")

    # Dump ALL attributes of pkg for visibility — helps catch attribute
    # naming drift (focus_areas may live elsewhere).
    out["package_attrs"] = sorted(
        a for a in dir(pkg) if not a.startswith("_") and not callable(getattr(pkg, a, None))
    )

    qa = getattr(pkg, "qa_verdict", None)
    out["qa_verdict_present"] = qa is not None
    if qa:
        out["qa_verdict_fields"] = (
            sorted(qa.keys())
            if isinstance(qa, dict)
            else list(getattr(qa, "__dataclass_fields__", {}))
            if hasattr(qa, "__dataclass_fields__")
            else []
        )

    ts = getattr(pkg, "tech_stack", None) or []
    out["tech_stack_count"] = len(ts) if ts else 0

    return out


def main() -> int:
    root = Path("tests/fixtures/dma_packages_real_samples")
    folders = sorted(root.iterdir())
    folders = [f for f in folders if f.is_dir()]

    results = []
    for f in folders:
        print(f"=== auditing {f.name} ===", flush=True)
        r = audit_one(f)
        results.append(r)
        # Print human-readable snippet immediately so we see progress.
        print(json.dumps(r, indent=2, default=str)[:4000])
        print()

    # Aggregate matrix.
    print()
    print("=" * 80)
    print("SUMMARY MATRIX (extracted counts per folder)")
    print("=" * 80)
    headers = [
        "folder",
        "evidence",
        "subcaps",
        "focus_areas",
        "recs",
        "peers",
        "sections",
        "leadership",
        "warnings",
        "fg_fields",
        "status",
    ]
    print("  ".join(f"{h:>14}" for h in headers))
    for r in results:
        row = [
            r["folder"][:14],
            r.get("evidence_count", "-"),
            r.get("subcap_scores_count", "-"),
            r.get("focus_areas_count", "-"),
            r.get("recommendations_count", "-"),
            r.get("peer_scores_count", "-"),
            r.get("report_sections_count", "-"),
            r.get("leadership_count", "-"),
            r.get("parser_warnings_count", "-"),
            r.get("firmographics_count", "-"),
            r["status"],
        ]
        print("  ".join(f"{str(c):>14}" for c in row))

    # Write the JSON for downstream consumers.
    out_json = Path("../docs/qa/qa_5folder_parse_audit.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nwrote {out_json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
