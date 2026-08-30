#!/usr/bin/env python3
"""Who owns each artefact — measured, not assumed.

    python3 scripts/audit_coverage.py [--json] [--strict]

WHY THIS EXISTS. "Sixty-four agents" is a count, not a coverage statement.
The 2026-08-30 review asked whether every workbook tab, every report section
and every deliverable actually has an owner, and the honest answer could only
come from measuring the chain rather than reading the roster: the Golden 1
run had sixteen category researchers and still produced no report, because
nothing in the roster was responsible for a report SECTION.

This walks four chains and reports an owner or a HOLE for every link:

  1. workbook tabs      -> the command that fills it -> the agent that runs it
  2. report sections    -> the writer of its Report_Narrative row
  3. deliverables       -> its renderer and its reader
  4. derived fields     -> the code that computes it (ERS is the cautionary
                          tale: a contract column, a standalone calculator,
                          and nothing joining them, so it shipped empty in
                          every run ever produced)

A HOLE is not a style opinion. It is: this artefact is required by a
contract, and no agent and no command writes it.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
SKILL = PLUGIN / "skills" / "dma-research"
sys.path.insert(0, str(SKILL))

from engine import completeness as CP        # noqa: E402
from engine import contract as C             # noqa: E402
from engine import report_spec as RS         # noqa: E402

AGENTS = PLUGIN / "agents"


def _agent_bodies() -> dict[str, str]:
    return {p.stem: p.read_text(errors="replace")
            for p in sorted(AGENTS.rglob("*.md"))}


def _engine_sources() -> dict[str, str]:
    return {p.stem: p.read_text(errors="replace")
            for p in sorted((SKILL / "engine").glob("*.py"))}


#: command fragment -> the agent(s) whose manifest tells someone to run it.
#: Matched as a substring of the agent body, because the manifests write
#: commands the way an operator types them.
def _agents_running(cmd: str, bodies: dict[str, str]) -> list[str]:
    # the distinctive head of the command: 'engine.prelim timeline' etc.
    head = " ".join(cmd.split()[:2]) if cmd else ""
    if not head or head.startswith("the ") or head.startswith("written"):
        return []
    return sorted(n for n, b in bodies.items() if head in b)


#: Tabs the ENGINE writes without anybody asking — at workbook creation, or
#: as a side effect of every append. They have no agent by design, and
#: reporting them as unowned is the audit crying wolf.
ENGINE_WRITTEN = {
    "00_README": "workbook.create -> _write_readme",
    "REF_Method": "workbook.create -> _write_ref_method",
    "Run_Metadata": "workbook.create -> _write_metadata",
    "Handoff_Lock": "workbook.create -> _write_handoff_lock",
    "Provenance": "ledger.record_provenance, on every synthesis",
    "Coverage": "workbook.recompute_coverage, on every synthesis",
}


def audit_tabs(bodies) -> list[dict]:
    out = []
    for sheet in C.SHEETS:
        if sheet in ENGINE_WRITTEN:
            out.append({"artefact": f"tab:{sheet}", "required": True,
                        "filled_by": ENGINE_WRITTEN[sheet], "owners": [],
                        "state": "ENGINE"})
            continue
        if sheet in C.PILLAR_SHEETS:
            cmd = "engine.cli start (seeded at creation)"
            owners = ["research-conductor"]
        else:
            cmd = CP.FILLED_BY.get(sheet, "")
            owners = _agents_running(cmd, bodies)
        never_empty = sheet in CP.NEVER_EMPTY
        # a tab with a filling command but no agent naming it is reachable
        # by hand and by nobody's manifest.
        state = ("OWNED" if owners else
                 "NO_COMMAND" if not cmd else
                 "COMMAND_ONLY")
        out.append({"artefact": f"tab:{sheet}", "required": never_empty,
                    "filled_by": cmd or None, "owners": owners,
                    "state": state})
    return out


def audit_report_sections(bodies) -> list[dict]:
    """Every section of both reports, and who writes its narrative row.

    The renderer READS `Report_Narrative`; it does not author it. So the
    question per section is: which agent is told to write this Section_ID."""
    prelim_src = (SKILL / "engine" / "prelim.py").read_text()
    preflight_src = (SKILL / "engine" / "preflight.py").read_text()
    engine_written = set(re.findall(r'section_id="(PRELIM-[A-Z]+)"', prelim_src))
    engine_written |= set(re.findall(r'"Section_ID": "(PRELIM-[A-Z]+)"',
                                     preflight_src))
    out = []
    for key, spec in RS.SPECS.items():
        for sec in spec.sections:
            sid = str(sec.id)
            # Ownership is declared two ways, and both count: the agent
            # names the report it writes AND lists the section in its
            # section table, or an engine module writes the row directly.
            owners = sorted(
                n for n, b in bodies.items()
                if (f"--report {key}" in b or f"`{key}`" in b)
                and re.search(rf"^\|\s*{re.escape(sid)}\s*\|", b, re.M))
            out.append({
                "artefact": f"report:{key}:§{sid}",
                "required": True,
                "heading": sec.heading, "kind": sec.kind,
                "min_words": sec.min_words,
                "filled_by": None, "owners": owners,
                "state": "OWNED" if owners else "HOLE",
            })
    out.append({"artefact": "report:PRELIM rows (institution profile)",
                "required": True, "filled_by": "engine.prelim / engine.preflight",
                "owners": sorted(engine_written), "state": "OWNED"})
    return out


def audit_deliverables(bodies) -> list[dict]:
    from engine import assemble as A
    out = []
    renderers = {
        "scoring_workbook": "engine.cli start (the substrate itself)",
        "research_report": "engine.cli report --report client_research",
        "assessment_report": "engine.cli report --report assessment",
        "technographic_scan": "engine.techscan render",
    }
    for key, pattern, kind in A.DELIVERABLES:
        cmd = renderers[key]
        owners = _agents_running(cmd, bodies)
        out.append({"artefact": f"deliverable:{key}", "required": True,
                    "pattern": pattern, "app_kind": kind,
                    "filled_by": cmd, "owners": owners,
                    "state": "OWNED" if owners else "HOLE"})
    return out


def audit_derived(bodies, engine) -> list[dict]:
    """Contract fields whose VALUE must be computed by something."""
    checks = [
        ("Evidence_Detail.ERS", "ledger", r"_ers\.recompute\("),
        ("ERS specificity from RRF", "ers", r"def specificity\("),
        ("ERS corroboration by identity", "ers", r"def corroboration\("),
        ("report section argument", "narrative", r"def write\("),
        ("report section independent review", "narrative", r"def review\("),
        ("report accuracy, computed", "narrative", r"def accuracy\("),
        ("Evidence_Detail.Recency", "ledger", r"def recency_band"),
        ("Coverage.*", "workbook", r"def recompute_coverage"),
        ("Handoff_Lock.catalogue_hash", "contract", r"def catalogue_hash"),
        ("Peer_Benchmarks lock", "workbook", r"def lock_peer_set"),
        ("retrieval RRF", "retrieval", r"def rrf\("),
        ("retrieval BM25 rerank", "retrieval", r"def rerank\("),
    ]
    out = []
    for field, mod, pat in checks:
        src = engine.get(mod, "")
        found = bool(re.search(pat, src))
        out.append({"artefact": f"derived:{field}", "required": True,
                    "filled_by": f"engine/{mod}.py" if found else None,
                    "owners": [], "state": "COMPUTED" if found else "HOLE"})
    return out


def audit_connectors(bodies) -> list[dict]:
    """Which enrichment connectors the RESEARCH tier can actually reach.

    The production tier carries Clay and Quartr; the research tier was
    provisioned separately. A connector named in a protocol the tier cannot
    call is a documented capability nobody has."""
    want = {"Clay": "mcp__Clay__", "Exa": "mcp__Exa__",
            "Tavily": "mcp__Tavily__", "Quartr": "mcp__Quartr__",
            "Indeed": "mcp__Indeed__", "Drive": "mcp__Google_Drive__"}
    research = {n: b for n, b in bodies.items()
                if n.startswith("research-")}
    out = []
    for label, prefix in want.items():
        have = sorted(n for n, b in research.items() if prefix in b)
        out.append({"artefact": f"connector:{label} (research tier)",
                    "required": False,
                    "filled_by": prefix, "owners": have,
                    "state": "REACHABLE" if have else "ABSENT"})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if any REQUIRED artefact is a HOLE")
    a = ap.parse_args(argv)

    bodies = _agent_bodies()
    engine = _engine_sources()
    rows = (audit_tabs(bodies) + audit_report_sections(bodies)
            + audit_deliverables(bodies) + audit_derived(bodies, engine)
            + audit_connectors(bodies))
    holes = [r for r in rows if r["state"] in ("HOLE", "NO_COMMAND")
             and r["required"]]

    if a.json:
        print(json.dumps({"agents": len(bodies), "rows": rows,
                          "holes": holes}, indent=2))
    else:
        print(f"{len(bodies)} agents · {len(rows)} artefacts measured\n")
        group = None
        for r in rows:
            g = r["artefact"].split(":")[0]
            if g != group:
                group = g
                print(f"── {g} " + "─" * (60 - len(g)))
            mark = {"OWNED": "✓", "COMPUTED": "✓", "REACHABLE": "✓",
                    "ENGINE": "✓", "COMMAND_ONLY": "~", "ABSENT": "·",
                    "NO_COMMAND": "✗", "HOLE": "✗"}[r["state"]]
            who = ", ".join(r["owners"][:3]) or (r.get("filled_by") or "—")
            if len(r["owners"]) > 3:
                who += f" +{len(r['owners']) - 3}"
            print(f"  {mark} {r['artefact']:<44} {who[:70]}")
        print(f"\n{len(holes)} REQUIRED artefact(s) with no owner:")
        for h in holes:
            print(f"  ✗ {h['artefact']}"
                  + (f" — {h.get('heading')}" if h.get("heading") else ""))
        if not holes:
            print("  (none)")
    return 1 if (a.strict and holes) else 0


if __name__ == "__main__":
    sys.exit(main())
