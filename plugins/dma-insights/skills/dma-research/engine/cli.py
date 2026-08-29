#!/usr/bin/env python3
"""One entry point for the whole research engine.

    python3 -m engine.cli start   --run R --entity "Acme CU" --sv CU --scope FULL
    python3 -m engine.cli orient  --run R [--category P1C1]
    python3 -m engine.cli search  --run R --subcap P1C1.1.1 --facet works --query '...'
    python3 -m engine.cli evidence --run R --subcap ... --source ... --url ... --excerpt ...
    python3 -m engine.cli synthesise --run R --subcap ... --json rec.json
    python3 -m engine.cli gate    --run R --category P1C1 [--require-synthesis]
    python3 -m engine.cli validate --run R
    python3 -m engine.cli handoff --run R
    python3 -m engine.cli report  --run R [--report both]
    python3 -m engine.cli strip   --run R
    python3 -m engine.cli status  [--root ...]
    python3 -m engine.cli counts

Delegated families — each is `engine.cli <family> <args…>`, passed through
verbatim to the module that owns it (its --help lists the subcommands):

    kg …        engine.kg        build / route / show / verify
    fuse …      engine.retrieval fuse / plan   (RRF + BM25 + query variants)
    memory …    engine.memory    note / status / consolidate / backup / cleanup
    techscan …  engine.techscan  record / render / status
    assemble …  engine.assemble  package / verify / contract

Every subcommand reads and writes the SAME workbook. There is no second
substrate to fall out of step with, which is the whole point (AUD-0001).
"""
from __future__ import annotations

# Runnable both ways. `python3 -m engine.<mod>` is the documented invocation,
# but every audit and every operator reaches for `python3 <path> --help`
# first, and a relative import dies there. Binding __package__ makes the two
# equivalent instead of making one of them a trap.
if __package__ in (None, ""):  # noqa: E402  (must precede the relative imports)
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import argparse
import json
import sys
from pathlib import Path

from . import (contract, floors_gate, handoff, ledger, orient, report_spec,
               reports, runstate, strip_working_area, validator, watchdog)


#: family name -> the module whose main() owns it. Dispatched BEFORE
#: argparse so the family's own --help answers, not this wrapper's.
_FAMILIES = ("kg", "fuse", "memory", "techscan", "assemble")


def _family_main(name: str):
    if name == "kg":
        from . import kg as m
    elif name == "fuse":
        from . import retrieval as m
    elif name == "memory":
        from . import memory as m
    elif name == "techscan":
        from . import techscan as m
    else:
        from . import assemble as m
    return m.main


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in _FAMILIES:
        rest = args[1:]
        if args[0] == "fuse" and (not rest or rest[0].startswith("-")):
            # `engine.cli fuse …` is retrieval's own `fuse` subcommand
            # unless the caller already named one (fuse/plan).
            rest = ["fuse"] + rest
        return _family_main(args[0])(rest)

    ap = argparse.ArgumentParser(prog="engine", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for fam in _FAMILIES:
        sub.add_parser(fam, help=f"delegated to engine.{fam if fam != 'fuse' else 'retrieval'} — "
                                 f"run `engine.cli {fam} --help`")

    def common(p):
        p.add_argument("--run", required=True)
        p.add_argument("--root")
        return p

    s = common(sub.add_parser("start"))
    s.add_argument("--entity", required=True)
    s.add_argument("--entity-id", required=True)
    s.add_argument("--sv")
    s.add_argument("--scope", default="FULL", choices=contract.SCOPE_MODES)
    s.add_argument("--reference-date", required=True)
    s.add_argument("--mode", default="PUBLIC",
                   choices=contract.ASSESSMENT_MODES,
                   help="evidence mode — decides which diagnostic questions "
                        "are answerable and which are deferred to discovery")
    s.add_argument("--sv-basis", required=True,
                   help="WHY this sub-vertical: the charter type, regulator "
                        "or LOB census the binding rests on. Refused when it "
                        "reads as filler; an entity with several plausible "
                        "sub-verticals is a question for the engagement "
                        "owner, never a guess")
    s.add_argument("--mode-basis", required=True,
                   help="WHY this evidence mode: the engagement terms that "
                        "granted (or withheld) internal access")
    s.add_argument("--lob-census", default=None,
                   help="optional: the lines of business found during "
                        "preflight and the sub-vertical candidates "
                        "considered/rejected — the disambiguation record")

    o = common(sub.add_parser("orient")); o.add_argument("--category")
    q = common(sub.add_parser("search"))
    q.add_argument("--subcap"); q.add_argument("--facet")
    q.add_argument("--query", required=True); q.add_argument("--tool", default="web_search")
    q.add_argument("--hits", type=int, default=0); q.add_argument("--kept", type=int, default=0)
    q.add_argument("--outcome", default="")

    e = common(sub.add_parser("evidence"))
    e.add_argument("--subcap", required=True, action="append")
    e.add_argument("--source", required=True); e.add_argument("--url")
    e.add_argument("--tier", required=True); e.add_argument("--excerpt", required=True)
    e.add_argument("--published"); e.add_argument("--claim-type", default="FACT")
    e.add_argument("--origin", default="public")

    y = common(sub.add_parser("synthesise"))
    y.add_argument("--subcap", required=True); y.add_argument("--json", required=True)
    y.add_argument("--actor", required=True,
                   help="the agent name writing this synthesis — recorded to "
                        "Provenance so record_challenge can refuse a "
                        "self-challenge. Required on the CLI because an "
                        "unattributed synthesis makes challenge independence "
                        "unverifiable (AUD-0018/AUD-0024)")

    g = common(sub.add_parser("gate"))
    g.add_argument("--category", required=True)
    g.add_argument("--require-synthesis", action="store_true")

    common(sub.add_parser("validate"))
    common(sub.add_parser("handoff"))
    r = common(sub.add_parser("report"))
    r.add_argument("--report", default="both",
                   choices=["client_research", "assessment", "both"])
    r.add_argument("--force", action="store_true")
    common(sub.add_parser("strip")).add_argument("--force", action="store_true")
    common(sub.add_parser("resume"))
    p = common(sub.add_parser("persist")); p.add_argument("--dest")
    st = sub.add_parser("status"); st.add_argument("--root")
    sub.add_parser("counts")

    a = ap.parse_args(argv)
    if a.cmd == "counts":
        print(json.dumps(contract.counts(), indent=2)); return 0
    if a.cmd == "status":
        return watchdog.main(["--root", a.root or str(runstate.RUN_ROOT), "--json"])

    root = Path(a.root) if a.root else None
    if a.cmd == "start":
        run = runstate.start(run_id=a.run, entity_name=a.entity,
                             entity_id=a.entity_id, sub_vertical=a.sv,
                             scope_mode=a.scope, reference_date=a.reference_date,
                             root=root, evidence_mode=a.mode,
                             sv_basis=a.sv_basis, mode_basis=a.mode_basis,
                             lob_census=a.lob_census)
        print(json.dumps({"run": run.run_id, "workbook": str(run.workbook_path),
                          "selected": len(run.open().selected_subcaps()),
                          "evidence_mode": a.mode,
                          "binding": {"sv": a.sv, "sv_basis": a.sv_basis,
                                      "mode_basis": a.mode_basis,
                                      "lob_census": a.lob_census}},
                         indent=2))
        return 0

    run = runstate.locate(a.run, root)
    if a.cmd == "resume":
        _, state = runstate.resume(a.run, root)
        print(json.dumps(state, indent=2)); return 0
    if a.cmd == "persist":
        print(json.dumps(runstate.persist(run, a.dest), indent=2)); return 0

    wb = run.open()
    if a.cmd == "orient":
        print(json.dumps(orient.orient(wb, a.category, qa_dir=run.qa_dir),
                         indent=2, sort_keys=True)); return 0
    if a.cmd == "search":
        n = ledger.append_search(wb, subcap=a.subcap, facet=a.facet,
                                 query=a.query, tool=a.tool, hits=a.hits,
                                 kept=a.kept, outcome=a.outcome)
        print(json.dumps({"seq": n, **ledger.stats(wb)}, indent=2)); return 0
    if a.cmd == "evidence":
        eid = ledger.append_evidence(
            wb, source_name=a.source, source_url=a.url, tier=a.tier,
            excerpt=a.excerpt, subcaps=a.subcap, published=a.published,
            claim_type=a.claim_type, origin=a.origin)
        print(json.dumps({"e_id": eid}, indent=2)); return 0
    if a.cmd == "synthesise":
        rec = json.loads(Path(a.json).read_text())
        print(json.dumps(ledger.append_synthesis(wb, a.subcap, rec,
                                                 actor=a.actor), indent=2))
        return 0
    if a.cmd == "gate":
        out = floors_gate.run(wb, a.category,
                              require_synthesis=a.require_synthesis,
                              qa_dir=run.qa_dir)
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0 if out["gate"] == "PASS" else 1
    if a.cmd == "validate":
        return validator.main(["--workbook", str(run.workbook_path),
                               "--run-id", a.run])
    if a.cmd == "handoff":
        return handoff.main(["--run", a.run] + (["--root", str(root)] if root else []))
    if a.cmd == "report":
        args = ["--run", a.run, "--report", a.report]
        if root: args += ["--root", str(root)]
        if a.force: args += ["--force"]
        return reports.main(args)
    if a.cmd == "strip":
        hp = run.deliverables / handoff.HANDOFF_NAME
        print(json.dumps(strip_working_area.strip(
            run.workbook_path, handoff=hp if hp.exists() else None,
            force=a.force), indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
