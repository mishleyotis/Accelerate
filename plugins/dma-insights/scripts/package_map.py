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


#: A folder named for a role is the STRONGER signal, and the corpus is why.
#: Houlihan Lokey ships `02_research_workbook/DMA_Scoring_Workbook_HL.xlsx`:
#: the filename comes off a shared template and says "Scoring" on every
#: workbook in the package, while the folder says which one this is. Reading
#: the name alone left research.primary=None, and the research workbook is
#: the ONLY store that carries verbatim `Excerpt`/`Anchor_Quote` columns —
#: the scoring workbook's Evidence_Master carries a summary or nothing. So a
#: filename-only match does not merely mislabel a file, it silently removes
#: every verbatim excerpt in the package (measured 2026-08-22: 462 of 462
#: HL excerpts were then fabricated downstream to fill the vacuum).
DIR_ROLE_RE = (("research", re.compile(r"research", re.I)),
               ("scoring", re.compile(r"scoring|assessment", re.I)))
NAME_ROLE_RE = (("research", re.compile(r"research", re.I)),
                ("scoring", re.compile(r"scor|assessment.*workbook", re.I)))


def _match_role(text: str, table) -> str | None:
    for role, rx in table:
        if rx.search(text):
            return role
    return None


def role_signals(path: Path, root: Path) -> tuple:
    """(dir_role, name_role) — what the folder says, what the name says.

    The folder is read from every ancestor inside the package, nearest
    first, so a wrapper generation (`DMAI - Client/02_research_workbook/…`)
    reads the same as a canonical one.
    """
    dir_role = None
    try:
        rel_parents = path.relative_to(root).parts[:-1]
    except ValueError:                                     # pragma: no cover
        rel_parents = ()
    for part in reversed(rel_parents):
        dir_role = _match_role(part, DIR_ROLE_RE)
        if dir_role:
            break
    return dir_role, _match_role(path.name, NAME_ROLE_RE)


def role_of(path: Path, root: Path) -> str | None:
    """Which role this workbook fills — RESEARCH is the discriminating word.

    Measured across 141 corpus clients, the two signals disagree in both
    directions and neither one always wins:

      Houlihan Lokey  02_research_workbook/DMA_Scoring_Workbook_HL.xlsx
      ProPartners     04_scoring/DMA_Research_Workbook_ProPartners_…xlsx

    Both are research workbooks. What separates them is not folder-beats-
    name — a rule that reads the folder first recovers Houlihan Lokey and
    loses ProPartners, which is how this was caught. It is that "scoring"
    is the TEMPLATE DEFAULT, stamped on every workbook the generator emits,
    while "research" is only ever written deliberately. So a deliberate
    word anywhere outranks a default word anywhere, and the two roles stay
    mutually exclusive: one file can never serve both.
    """
    signals = role_signals(path, root)
    if "research" in signals:
        return "research"
    if "scoring" in signals:
        return "scoring"
    return None


def _version_rank(name: str) -> int:
    if FINAL_RE.search(name):
        return 100
    m = VER_RE.search(name)
    if m:
        return 10 + int(m.group(1))
    return 11        # plain, undecorated — newer than v1, older than v2+


def _rank_workbooks(paths: list, role: str, root: Path) -> dict:
    """role: 'scoring' | 'research'."""
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
        if role_signals(p, root)[0] == role:
            score += 5                     # the folder confirms the role
        scored.append((score, str(p)))
    scored.sort(reverse=True)
    set_aside.sort(key=lambda s: s["path"])
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


#: A research register is not always a workbook. Measured across the corpus
#: 2026-08-23, counting every file under a research-named path: .json 109,
#: .py 83, .csv 26, .md 19, **.xlsx 19**, .docx 14, .txt 4, .pdf 3 — the
#: spreadsheet is not even the common case, and TEN research-named folders
#: hold files and no .xlsx at all. Owner, same day: "I also thought research
#: workbook may be in multiple formats? Ensure it can detect all mime types."
#:
#: So a research SOURCE is resolved by shape and role, not by extension. The
#: workbook keeps its own slot (`research.primary`) because the tab contract
#: is real where a workbook exists; these are the stores that carry the same
#: content in another container.
RESEARCH_PATH_RE = re.compile(r"research", re.I)

#: Formats a register can be READ from. A .docx or .pdf under a research
#: path is a report, not a table — named, never parsed as one.
TABULAR_EXT = (".csv", ".tsv", ".json", ".jsonl", ".xlsx", ".xlsm")
NARRATIVE_EXT = (".docx", ".pdf", ".md", ".txt", ".rtf")


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
        elif low.endswith((".csv", ".tsv")):
            # A research-path table is an evidence source whatever it is
            # called: the name test alone missed registers living under
            # `08_appendices/research/` and `… Background Research/`.
            if (EVID_NAME_RE.search(low) or EVID_HDR_RE.search(_csv_header(p))
                    or (RESEARCH_PATH_RE.search(low)
                        and EVID_HDR_RE.search(_csv_header(p)))):
                evidence_tables.append(rel)
            elif GOV_RE.search(low):
                governance.append(rel)
            elif PEER_RE.search(low):
                peers.append(rel)
            else:
                other.append(rel)
        elif low.endswith((".json", ".jsonl")) and (
                re.search(r"evidence|ledger|register", low)
                or _json_head_has_eids(p)
                or (RESEARCH_PATH_RE.search(low) and _json_head_has_eids(p))):
            evidence_tables.append(rel)
        elif low.endswith(".json") and "manifest" in low:
            manifests.append(rel)
        elif low.endswith((".docx", ".pdf")):
            reports.append(rel)
        else:
            other.append(rel)

    # "DMA_Scoring_Workbook_X" and "DMA_Assessment_Workbook_X" are the same
    # artefact under two naming generations (measured: CoBank, Achieve,
    # Brick City use the assessment spelling) — so the NAME cannot separate
    # the two roles on its own. The FOLDER can, and does whenever it speaks:
    # a file under a role-named folder belongs to that role however the
    # shared template named it. The name decides only where the folder is
    # silent (`08_appendices/Foo_Research_Workbook.xlsx`, top-level files).
    roles = {p: role_of(p, root) for p in xlsx}
    scoring_cand = [p for p in xlsx if roles[p] == "scoring"]
    research_cand = [p for p in xlsx if roles[p] == "research"]
    aux = [str(p.relative_to(root)) for p in xlsx if AUX_RE.search(str(p))]
    unclassified_xlsx = [str(p.relative_to(root)) for p in xlsx
                         if p not in scoring_cand and p not in research_cand
                         and str(p.relative_to(root)) not in aux]

    scoring = _rank_workbooks(scoring_cand, "scoring", root)
    research = _rank_workbooks(research_cand, "research", root)
    ambiguities = scoring.pop("_ambiguities") + research.pop("_ambiguities")
    if scoring["primary"] is None and unclassified_xlsx:
        ambiguities.append(
            f"no workbook named 'scoring' — unclassified xlsx exist: "
            f"{unclassified_xlsx[:3]}; the vetter decides whether one is the "
            f"scoring workbook")
    if scoring["primary"] is None and research["primary"]:
        ambiguities.append(
            f"no scoring workbook — the only role-named workbook is the "
            f"research one ({research['primary']}); scores must come from "
            f"the exports or the vetter refuses. It is NOT re-used as the "
            f"scoring workbook: one file never serves both roles")
    if research["primary"] is None and scoring["primary"]:
        ambiguities.append(
            f"NO RESEARCH WORKBOOK anywhere in the tree. Verbatim excerpts "
            f"live in its register tab and nowhere else — the scoring "
            f"workbook's Evidence_Master carries a summary column at best. "
            f"Expect an evidence pass with excerpts missing, NOT excerpts "
            f"invented to fill the gap; the vetter decides whether the "
            f"package can be produced from at all")
    score_exports = sorted(
        str(q.relative_to(root)) for q in entries
        if q.name.lower().startswith("export_")
        and "scor" in q.name.lower())
    if scoring["primary"] is None and score_exports:
        ambiguities.append(
            f"EXPORT-ONLY scoring: no workbook, but flattened exports exist "
            f"({score_exports[0]}) — measured on ~2 dozen corpus clients; "
            f"the exports are the score authority here, vetter confirms")
    if scoring["primary"] is None and not xlsx and not score_exports:
        ambiguities.append("BRIEFING-ONLY package: no workbook anywhere in "
                           "the tree — not a synthesis input")

    src = {
        "scores": ([scoring["primary"]] if scoring["primary"]
                   else score_exports),
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
