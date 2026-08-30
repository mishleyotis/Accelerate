#!/usr/bin/env python3
"""Every hand-off from intake to a served surface — owner, gate, reader.

    python3 scripts/audit_chain.py [--json] [--strict]

WHY THIS EXISTS. `audit_coverage.py` walks four chains INSIDE a run — tabs,
report sections, deliverables, derived fields — and asks who writes each. It
cannot see the chain BETWEEN the pieces: intake to run, run to enrichment,
workbook to reports, package to vetting, vetting to synthesis, synthesis to
promotion, promotion to a served surface. That chain is where this product
has failed most expensively, and always the same way: a link whose two halves
both work and are not joined.

  · `classification.py` classified the Client Research Profile, the scanner
    wrote the kind into `import_files`, and `_classify_artefact` dropped it.
    Both halves had tests. (AUD-0169/0171)
  · `open_folder` recorded the client folder and `package` recomputed it, so
    one run could end with two folders and the app scanned one. (AUD-0183)
  · Entity_Timeline had a writer, a gate and no reader anywhere. (AUD-0165)
  · The three scored tabs had a reader, two live gates, and no writer at all.
    (AUD-0166/0173)

So each LINK is asserted to have three things, and a missing one is a HOLE:

    OWNER   the agent, Routine or command that performs it
    GATE    the refusal that stops the chain when the link did not happen
    READER  the thing downstream that consumes what the link produced

A HOLE is not a style opinion: it is a link the product depends on where one
of the three does not exist in this repository. Existence is what a script
can check honestly — that a named file, command or declaration is THERE. It
does not prove the link runs correctly in production; `stress_stage_and_
supersede.py` and `stress_run_lifecycle.py` walk that, and the routines'
own health is `routine_health.py`. This answers the question those cannot:
is any link of the chain simply not built?
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(PLUGIN))


def _exists(rel: str) -> bool:
    return os.path.exists(os.path.join(REPO, rel))


def _agent(name: str) -> bool:
    for root, _dirs, files in os.walk(os.path.join(PLUGIN, "agents")):
        if f"{name}.md" in files:
            return True
    return False


def _grep(rel: str, needle: str) -> bool:
    path = os.path.join(REPO, rel)
    if not os.path.isfile(path):
        return False
    with open(path, errors="ignore") as fh:
        return needle in fh.read()


def _cmd(module: str, sub: str | None = None) -> bool:
    """A command answers --help. `--help` is the cheapest proof that a
    documented command is not a fiction, and this project has shipped two
    that were (AUD-0011)."""
    skill = os.path.join(PLUGIN, "skills", "dma-research")
    argv = [sys.executable, "-m", module] + ([sub] if sub else []) + ["--help"]
    try:
        r = subprocess.run(argv, cwd=skill, capture_output=True, text=True,
                           timeout=60)
    except Exception:                                        # noqa: BLE001
        return False
    return r.returncode == 0


def _routine(name: str) -> bool:
    """An app-side Cloud Scheduler routine, declared where setup_routines.py
    reconciles it — a routine that exists only in prose is one nobody can
    reconcile."""
    path = os.path.join(PLUGIN, "routines.json")
    try:
        doc = json.load(open(path))
    except Exception:                                        # noqa: BLE001
        return False
    return any(r.get("name") == name for r in doc.get("routines", []))


def _claude_routine(name: str) -> bool:
    """A Claude-session Routine. These have no reconciler, so ROUTINES.md IS
    their declaration and the prompt is kept there verbatim."""
    return _grep("plugins/dma-insights/docs/ROUTINES.md", name)


#: (link, owner-check, gate-check, reader-check). Each value is a
#: (description, predicate) pair so a HOLE can name what is missing rather
#: than reporting a boolean.
LINKS = [
    ("intake → a run exists",
     ("dma-assessment-intake scans the tree; run_gate.py pick chooses",
      lambda: _claude_routine("dma-assessment-intake")
      and _exists("plugins/dma-insights/scripts/run_gate.py")),
     ("dmai-package-scan is how runs come to exist (charter, mandatory)",
      lambda: _routine("dmai-package-scan")),
     ("the app's scanner reads the tree and records classified_kind",
      lambda: _grep("apps/worker/job_main.py", "_classify_artefact"))),

    ("run → deep research, routed by category",
     ("research-conductor dispatches the sixteen category producers",
      lambda: _agent("research-conductor")
      and all(_agent(f"research-p{p}c{c}-producer")
              for p in (1, 2, 3, 4) for c in (1, 2, 3, 4))),
     ("the floors gate closes a category; orient withholds cards until "
      "PRELIM is closed",
      lambda: _cmd("engine.cli", "gate") and _cmd("engine.cli", "orient")),
     ("the workbook is the record every later stage reads",
      lambda: _cmd("engine.cli", "status"))),

    ("research → enrichment, on a cadence",
     ("the enrichment planner and the two specialists",
      lambda: _agent("enrichment-planner")
      and _agent("enrichment-connector-specialist")
      and _agent("enrichment-web-specialist")),
     ("the ledger auditor refuses an enrichment that never ran",
      lambda: _agent("enrichment-ledger-auditor")),
     ("dmai-enrich-loop raises the cadence rows hourly; the daily drift "
      "review reads what it left",
      lambda: _routine("dmai-enrich-loop")
      and _claude_routine("dma-refresh-drift-daily"))),

    ("enrichment → workbook population",
     ("every write goes through the ledger's own refusals",
      lambda: _exists("plugins/dma-insights/skills/dma-research/engine/"
                      "ledger.py")),
     ("the completeness gate blocks a package whose tabs are empty and "
      "undeclared, and an ILLEGAL_DECLARATION blocks harder",
      lambda: _cmd("engine.completeness", "check")
      and _grep("plugins/dma-insights/skills/dma-research/engine/"
                "completeness.py", "ILLEGAL_DECLARATION")),
     ("the app's workbook parser reads every tab it depends on",
      lambda: _grep("apps/worker/dma_worker/workbook_parser.py",
                    "parse_grain_summaries"))),

    ("workbook → report finalization",
     ("two report producers, one section at a time, through engine.narrative",
      lambda: _agent("report-research-producer")
      and _agent("report-assessment-producer")),
     ("the renderer refuses an unreviewed section, and the validator is a "
      "different actor from the author",
      lambda: _agent("report-validator")
      and _grep("plugins/dma-insights/skills/dma-research/engine/"
                "narrative.py", "requires_citation")),
     ("the app parses both reports into document_sections, each naming its "
      "own artefact",
      lambda: _grep("apps/worker/dma_worker/report_parser.py",
                    "artefact_id")
      and _grep("apps/worker/job_main.py", "PROFILE_KIND_PREFIX"))),

    ("reports → the client package",
     ("assemble.package copies the four deliverables into '<Entity> - DMA'",
      lambda: _cmd("engine.assemble", "package")),
     ("verify refuses an incomplete folder; a second run supersedes rather "
      "than merges",
      lambda: _cmd("engine.assemble", "verify")
      and _grep("plugins/dma-insights/skills/dma-research/engine/"
                "assemble.py", "ARCHIVE_DIR")),
     ("the app's package scan reads the folder and skips the archive",
      lambda: _grep("apps/worker/job_main.py", "ARCHIVE_SEGMENT"))),

    ("package → vetting",
     ("package-vetter decides whether a package may enter the system",
      lambda: _agent("package-vetter")),
     ("it vets BEFORE anything is parsed — workbook shape, headers, "
      "evidence register, sub-vertical scope, catalogue pinning",
      lambda: _exists("plugins/dma-insights/scripts/vet_workbooks.py")
      or _exists("plugins/dma-insights/scripts/vet_corpus.py")),
     ("run_gate.py pick will only choose a vetted package",
      lambda: _grep("plugins/dma-insights/scripts/run_gate.py", "pick"))),

    ("vetted package → synthesis",
     ("two synthesis Routines, each choosing its client from the gate",
      lambda: _claude_routine("dma-synthesis-sequence-a")
      and _claude_routine("dma-synthesis-sequence-b")),
     ("claim_run leases the run so two lanes cannot take one client",
      lambda: _grep("plugins/dma-insights/docs/MCP-TOOLS.md", "claim_run")),
     ("the watchdog revives a run whose container is gone",
      lambda: _claude_routine("dma-watchdog"))),

    ("synthesis → promotion",
     ("the surface-producer is the only agent permitted to submit or promote",
      lambda: _agent("surface-producer")),
     ("submit and promote each carry their own PreToolUse precheck, and "
      "promotion is atomic across all six pages",
      lambda: _exists("plugins/dma-insights/scripts/hooks/"
                      "precheck_submit.py")
      and _exists("plugins/dma-insights/scripts/hooks/"
                  "precheck_promote.py")),
     ("the connector's promote_run is the only writer of serving content",
      lambda: _grep("plugins/dma-insights/docs/MCP-TOOLS.md", "promote_run"))),

    ("promotion → the served web app",
     ("the app serves from the serving tables; no model runs at request time",
      lambda: os.path.isdir(os.path.join(REPO, "apps", "web"))
      and os.path.isdir(os.path.join(REPO, "apps", "api"))),
     ("audience redaction is server-side and default-deny",
      lambda: _agent("exclusion-boundary-auditor")),
     ("the deployed-app auditor reads what PRODUCTION serves, not what an "
      "agent said it produced",
      lambda: _agent("deployed-app-auditor"))),

    ("served surface → vetting the result",
     ("the adversarial verifier attacks a run that already passed every gate",
      lambda: _agent("adversarial-verifier")),
     ("evidence integrity halts on a foreign id; numeric reconciliation "
      "recomputes every figure rendered twice",
      lambda: _agent("evidence-integrity-checker")
      and _agent("numeric-reconciliation-checker")),
     ("the qa-overseer writes what was learned into the findings memory, and "
      "the rectifier works it",
      lambda: _agent("qa-overseer") and _agent("rectifier"))),
]

ROLES = ("owner", "gate", "reader")


def audit() -> dict:
    rows = []
    for link, *roles in LINKS:
        got = {}
        for role, (desc, pred) in zip(ROLES, roles):
            try:
                ok = bool(pred())
            except Exception as e:                           # noqa: BLE001
                ok = False
                desc = f"{desc} [check raised {type(e).__name__}]"
            got[role] = {"what": desc, "present": ok}
        holes = [r for r in ROLES if not got[r]["present"]]
        rows.append({"link": link, **got, "holes": holes})
    return {"links": rows,
            "holes": [{"link": r["link"], "missing": r["holes"],
                       "what": [r[m]["what"] for m in r["holes"]]}
                      for r in rows if r["holes"]]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when any link is missing an owner, a gate "
                         "or a reader")
    a = ap.parse_args(argv)
    out = audit()
    rc = 1 if (a.strict and out["holes"]) else 0
    if a.json:
        print(json.dumps(out, indent=2))
        return rc

    whole = len(out["links"]) - len(out["holes"])
    print(f"{whole}/{len(out['links'])} link(s) have an owner, a gate and a "
          f"reader\n")
    for r in out["links"]:
        mark = "✓" if not r["holes"] else "✗"
        print(f"  {mark} {r['link']}")
        for role in ROLES:
            tick = " " if r[role]["present"] else "!"
            print(f"      {tick} {role:7s} {r[role]['what']}")
    if out["holes"]:
        print(f"\n{len(out['holes'])} link(s) with a HOLE. A hole is a link "
              f"this product depends on where one of the three does not "
              f"exist — not a style opinion.")
    else:
        print("\nNo link of the chain is missing an owner, a gate or a "
              "reader. That is existence, not behaviour: the walks "
              "(stress_stage_and_supersede.py, stress_run_lifecycle.py) "
              "prove the behaviour, and routine_health.py proves the "
              "Routines are firing.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
