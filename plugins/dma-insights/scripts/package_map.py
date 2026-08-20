#!/usr/bin/env python3
"""Resolve a pulled client package, whatever generation it is.

Owner instruction, 2026-08-20: the workflow assumed every package is
canonical (01..08 folders, evidence only in workbooks). The corpus survey
measured otherwise: 131 of 178 canonical, ~30 wrapper packages (everything
one level down), at least three older numbering generations (02_Evidence /
03_Assessment; 02_peers / 03_issues; workbooks living in 08_appendices),
version stacks (v1/v2/FINAL side by side), INTERIM workbooks misfiled in
research folders, Explorium/internal xlsx noise, and briefing-only folders
with no workbook at all.

This module is the one place that turns that mess into named artefacts:

  map_package(root) -> {
    scoring:   {primary, candidates, set_aside},   # ranked, never guessed
    research:  {primary, candidates, set_aside},
    evidence_tables: [...paths],   # CSVs that define evidence rows
    governance: [...], peers: [...], manifests: [...], reports: [...],
    excluded:  [...],              # slides/decks — never synthesis input
    ambiguities: [...],            # every choice a human may want to check
    source_map: {kind: [paths]},   # "if it is not in the workbook, where?"
  }

Ranking rules (measured, not aspirational):
- FINAL beats vN beats plain beats v1; INTERIM/DRAFT/COPY are set aside and
  become primary only when nothing else exists (recorded as an ambiguity).
- A candidate inside a folder named for its role (scoring/assessment,
  research) outranks one found elsewhere.
- Explorium / techstack-validation / benefit-model / internal-evidence
  workbooks are auxiliary data, never scoring or research candidates.
- A near-tie or a set-aside non-interim candidate is an AMBIGUITY — the
  package-vetter adjudicates; this module never silently guesses.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SLIDES_RE = re.compile(r"(^|/)05[_ ]?narrative|presentation|deck|slides|"
                       r"\.pptx$|\.ppt$", re.I)
AUX_RE = re.compile(r"explorium|techstack[_ ]?validation|benefit model|"
                    r"internal_evidence|attachment|crosswalk|sources[_ ]"
                    r"inventory", re.I)
INTERIM_RE = re.compile(r"interim|draft|copy of|backup|old", re.I)
FINAL_RE = re.compile(r"final", re.I)
VER_RE = re.compile(r"v(\d+)(?:\.\d+)?", re.I)
EVID_HDR_RE = re.compile(r"evidence_id|evidence id", re.I)
EVID_NAME_RE = re.compile(r"evidence|inventory|register", re.I)
GOV_RE = re.compile(r"caps_applied|contradiction|issue", re.I)
PEER_RE = re.compile(r"peer", re.I)


def _version_rank(name: str) -> int:
    if FINAL_RE.search(name):
        return 100
    m = VER_RE.search(name)
    if m:
        return 10 + int(m.group(1))
    return 11        # plain, undecorated — newer than v1, older than v2+


def _rank_workbooks(paths: list, role: str) -> dict:
    """role: 'scoring' | 'research'."""
    role_dirs = ("scoring", "assessment") if role == "scoring" \
        else ("research",)
    scored, set_aside = [], []
    for p in paths:
        name = p.name
        if AUX_RE.search(str(p)):
            continue                       # classified elsewhere
        if INTERIM_RE.search(name):
            set_aside.append({"path": str(p),
                              "reason": "interim/draft naming — never "
                                        "auto-picked over a live workbook"})
            continue
        score = _version_rank(name)
        if any(d in str(p.parent).lower() for d in role_dirs):
            score += 5
        scored.append((score, str(p)))
    scored.sort(reverse=True)
    ambiguities = []
    primary = scored[0][1] if scored else None
    if primary is None and set_aside:
        primary = set_aside[0]["path"]
        ambiguities.append(
            f"{role}: only interim/draft candidates exist — using "
            f"{primary!r} under protest; the vetter must confirm")
    if len(scored) > 1 and scored[0][0] - scored[1][0] <= 1:
        ambiguities.append(
            f"{role}: near-tie between {scored[0][1]!r} and "
            f"{scored[1][1]!r} — ranked by version/location, confirm the pick")
    for s in set_aside:
        if scored:
            ambiguities.append(f"{role}: set aside {s['path']!r} "
                               f"({s['reason']})")
    return {"primary": primary,
            "candidates": [p for _, p in scored],
            "set_aside": set_aside,
            "_ambiguities": ambiguities}


def _json_head_has_eids(path: Path) -> bool:
    """A JSON/JSONL store whose head names evidence_id/fact_id keys is an
    evidence table whatever its filename says (measured: the canonical
    packages keep ledger.jsonl and evidence_index.json in 01_evidence)."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(4096).decode("utf-8", errors="replace")
    except OSError:
        return False
    return bool(re.search(r'"(evidence_id|fact_id|e_id)"', head))


def _csv_header(path: Path) -> str:
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
            return fh.readline()
    except OSError:
        return ""


def map_package(root) -> dict:
    root = Path(root)
    entries = [p for p in root.rglob("*") if p.is_file()]
    tops = list(root.iterdir()) if root.is_dir() else []
    top_dirs = [p for p in tops if p.is_dir()]
    top_files = [p for p in tops if p.is_file() and p.name != ".DS_Store"]
    wrapper = (top_dirs[0].name
               if len(top_dirs) == 1 and not top_files else None)

    excluded, xlsx, evidence_tables, governance = [], [], [], []
    peers, manifests, reports, other = [], [], [], []
    for p in entries:
        rel = str(p.relative_to(root))
        low = rel.lower()
        if SLIDES_RE.search(low):
            excluded.append(rel)
        elif low.endswith((".xlsx", ".xlsm")):
            xlsx.append(p)
        elif low.endswith(".csv"):
            if EVID_NAME_RE.search(low) or EVID_HDR_RE.search(_csv_header(p)):
                evidence_tables.append(rel)
            elif GOV_RE.search(low):
                governance.append(rel)
            elif PEER_RE.search(low):
                peers.append(rel)
            else:
                other.append(rel)
        elif low.endswith((".json", ".jsonl")) and (
                re.search(r"evidence|ledger|register", low)
                or _json_head_has_eids(p)):
            evidence_tables.append(rel)
        elif low.endswith(".json") and "manifest" in low:
            manifests.append(rel)
        elif low.endswith((".docx", ".pdf")):
            reports.append(rel)
        else:
            other.append(rel)

    # "DMA_Scoring_Workbook_X" and "DMA_Assessment_Workbook_X" are the
    # same artefact under two naming generations (measured: CoBank,
    # Achieve, Brick City use the assessment spelling)
    SCORING_NAME = re.compile(r"scor|assessment.*workbook", re.I)
    scoring_cand = [p for p in xlsx if SCORING_NAME.search(p.name)]
    research_cand = [p for p in xlsx if re.search(r"research", p.name, re.I)
                     and not SCORING_NAME.search(p.name)]
    aux = [str(p.relative_to(root)) for p in xlsx if AUX_RE.search(str(p))]
    unclassified_xlsx = [str(p.relative_to(root)) for p in xlsx
                         if p not in scoring_cand and p not in research_cand
                         and str(p.relative_to(root)) not in aux]

    scoring = _rank_workbooks(scoring_cand, "scoring")
    research = _rank_workbooks(research_cand, "research")
    ambiguities = scoring.pop("_ambiguities") + research.pop("_ambiguities")
    if scoring["primary"] is None and unclassified_xlsx:
        ambiguities.append(
            f"no workbook named 'scoring' — unclassified xlsx exist: "
            f"{unclassified_xlsx[:3]}; the vetter decides whether one is the "
            f"scoring workbook")
    if scoring["primary"] is None and not xlsx:
        ambiguities.append("BRIEFING-ONLY package: no workbook anywhere in "
                           "the tree — not a synthesis input")

    src = {
        "scores": [scoring["primary"]] if scoring["primary"] else [],
        "evidence": evidence_tables + ([research["primary"]]
                                       if research["primary"] else []),
        "governance": governance,
        "peers": peers,
        "identity": manifests + [r for r in reports
                                 if "profile" in r.lower()][:2],
        "narrative_claims": reports,
    }
    return {"root": str(root), "wrapper": wrapper,
            "scoring": scoring, "research": research,
            "evidence_tables": evidence_tables, "governance": governance,
            "peers": peers, "manifests": manifests, "reports": reports,
            "auxiliary_xlsx": aux, "unclassified_xlsx": unclassified_xlsx,
            "excluded": excluded, "other": other[:50],
            "ambiguities": ambiguities, "source_map": src}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("package_dir")
    a = ap.parse_args(argv)
    root = Path(a.package_dir)
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    m = map_package(root)
    print(json.dumps(m, indent=1))
    if m["ambiguities"]:
        print("\nAMBIGUITIES (the vetter adjudicates, never this script):",
              file=sys.stderr)
        for x in m["ambiguities"]:
            print(f"  - {x}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
