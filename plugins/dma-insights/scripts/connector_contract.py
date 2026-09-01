#!/usr/bin/env python3
"""Which connectors a firing REQUIRES, as data rather than as prose.

WHY THIS EXISTS. On 2026-08-31 the intake Routine's prompt was given a
connector preflight that named its own list: "Exa, Tavily, Firecrawl, Clay
and Vibe-Prospecting". Firecrawl is in none of the agents' `tools:` lines,
in no role in `scripts/provision_agent_tools.py`, and nowhere in
`docs/CONNECTORS.md` — so a prompt that STOPS on it would have stopped
every firing on a connector the pipeline cannot call and no producer
declares. That is the same defect class as the version floors the plugin
already deleted: a requirement written as prose is never compared to
anything, so it drifts the moment somebody types a name.

So the requirement is derived. `EXTERNAL` in
`scripts/provision_agent_tools.py` is already the one registry of connector
families the agents are provisioned from — one table, one writer. This
module reads THAT, refuses to require a family it does not define, and
hands every caller the same answer: the doctor, `bootstrap_session.sh`, the
Routine prompts and the tests.

WHAT A SCRIPT CANNOT DO, and why the verdict is split. A session's bound
MCP tools live in the model's context, not on this disk. No subprocess can
enumerate them — `claude plugin list` proves the INSTALL, the doctor's
roster proves the SERVER, and neither proves that THIS session can call a
tool (MEM-0112, measured twice). So the split is: this module owns the
declaration and every disk-checkable half, and the caller supplies the one
fact only it can see — the tool names it actually holds. `--check` reads
them; it never guesses them, and it never reports a pass for a list it was
not given.

    connector_contract.py declare [--json]
    connector_contract.py check --tools tools.txt [--strict]
    printenv | ... | connector_contract.py check --tools - --strict

Exit 0 when every REQUIRED family is present, 1 when one is missing, 2 when
the contract itself is unusable (the registry moved, a required family is
not in it) — which is a repo defect and never a session's fault.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

#: The registry lives at the repository root, beside the provisioner that
#: writes every agent manifest from it. Imported by path rather than by
#: package so this runs from a plugin install with no repo on sys.path.
_ROOT = Path(__file__).resolve().parents[3]
_PROVISIONER = _ROOT / "scripts" / "provision_agent_tools.py"

#: Families a RESEARCH or INTAKE firing cannot honestly run without.
#: `docs/CONNECTORS.md` § Preflight is the contract these encode: Exa and
#: Tavily do the open-web reading, and at least one of the firmographic
#: pair answers "who is this entity" — the question a sub-vertical binding
#: turns on. Kept deliberately small: every name here is a STOP, and a stop
#: list that grows by habit is one nobody can satisfy.
REQUIRED: tuple[str, ...] = ("exa", "tavily")

#: At least one of each group must be present. Explorium and Clay both
#: answer firmographics and technographics; requiring both would stop a
#: firing that could do the work.
REQUIRED_ANY: tuple[tuple[str, ...], ...] = (("explorium", "clay"),)

#: Present-if-attached. Their absence is recorded per facet as NOT_RUN with
#: the reason (the enrichment ledger's own vocabulary) and never silently
#: becomes a thin result.
OPTIONAL: tuple[str, ...] = ("indeed", "quartr", "drive")


class ContractBroken(RuntimeError):
    """The contract cannot be evaluated — a repo defect, not a session's."""


def families() -> dict[str, list[str]]:
    """`EXTERNAL` out of the provisioner, without importing its CLI."""
    if not _PROVISIONER.is_file():
        raise ContractBroken(
            f"the connector registry is missing: {_PROVISIONER}. It is the "
            "one table the agents are provisioned from, so nothing can say "
            "which connectors a firing needs without it.")
    ns: dict = {}
    src = _PROVISIONER.read_text()
    # EXTERNAL is a literal dict; exec the module's own assignment rather
    # than re-typing it here, because a second copy is a second answer.
    start = src.find("EXTERNAL = {")
    if start < 0:
        raise ContractBroken(
            f"{_PROVISIONER} no longer defines EXTERNAL. Point this module "
            "at whatever replaced it — do not re-declare the families here.")
    depth, i = 0, src.index("{", start)
    for j in range(i, len(src)):
        depth += (src[j] == "{") - (src[j] == "}")
        if depth == 0:
            exec(f"EXTERNAL = {src[i:j + 1]}", {}, ns)      # noqa: S102
            break
    else:
        raise ContractBroken(f"EXTERNAL in {_PROVISIONER} does not close")
    return ns["EXTERNAL"]


def contract() -> dict:
    """The required set, checked against the registry that defines it."""
    fam = families()
    named = set(REQUIRED) | {n for grp in REQUIRED_ANY for n in grp}
    unknown = sorted(named - set(fam))
    if unknown:
        raise ContractBroken(
            f"required connector famil{'y' if len(unknown) == 1 else 'ies'} "
            f"{', '.join(unknown)} not in EXTERNAL ({', '.join(sorted(fam))}). "
            "A firing cannot be stopped for a connector no agent declares "
            "and no role grants — add it to the registry first, or stop "
            "requiring it here.")
    return {
        "required": list(REQUIRED),
        "required_any": [list(g) for g in REQUIRED_ANY],
        "optional": [f for f in OPTIONAL if f in fam],
        "tools": {f: fam[f] for f in
                  set(REQUIRED) | {n for g in REQUIRED_ANY for n in g}
                  | set(OPTIONAL) if f in fam},
    }


def _present(family: str, fam: dict[str, list[str]], held: set[str]) -> bool:
    """A family answers when ANY of its tools is bound.

    Any rather than all: a connector can expose a subset and still do the
    work, and demanding the full list turns a working session into a stop.
    """
    return any(t in held for t in fam.get(family, ()))


def check(tool_names, *, now_families=None) -> dict:
    """Judge a session's bound tools against the contract.

    `tool_names` is what the CALLER can see and this module cannot.
    """
    fam = now_families or families()
    c = contract()
    held = {t.strip() for t in tool_names if t.strip()}

    missing = [f for f in c["required"] if not _present(f, fam, held)]
    for group in REQUIRED_ANY:
        if not any(_present(f, fam, held) for f in group):
            missing.append(" or ".join(group))

    absent_optional = [f for f in c["optional"] if not _present(f, fam, held)]
    return {
        "ok": not missing,
        "missing": missing,
        "present": sorted(f for f in c["tools"] if _present(f, fam, held)),
        "optional_absent": absent_optional,
        "held_mcp_tools": len([t for t in held if t.startswith("mcp__")]),
        "verdict": "READY" if not missing else "STOP",
        "why": ("every required connector family answers"
                if not missing else
                f"missing: {', '.join(missing)} — attach on this Routine's "
                "own edit screen in the claude.ai routines UI; the connector "
                "browse list's Use buttons enable a connector for the ORG, "
                "not for a Routine"),
        "note_on_absent_optional": (
            "record each as NOT_RUN with that reason in the enrichment "
            "ledger; an unattached connector is an honest absence and never "
            "a thin result" if absent_optional else ""),
    }


#: Where a run's connector baseline lives. Run-scoped on purpose: two runs
#: in one container are two different sessions with two different rosters,
#: and a shared file would have the second overwrite the first's evidence of
#: what it started with.
def baseline_path(root=None) -> Path:
    import os
    base = Path(root) if root else Path(
        os.environ.get("DMA_RUN_ROOT") or ".")
    return base / "connectors_baseline.json"


def write_baseline(tool_names, root=None) -> dict:
    """Record what this session ACTUALLY held when it started producing.

    WHY A BASELINE AND NOT JUST A CHECK (owner, 2026-08-31: "The connectors
    may be lost mid session even after being attached"). A check alone
    cannot tell the two cases apart, and they call for opposite responses:

      never had it   -> a preflight STOP. Nothing has been researched yet,
                        nothing is corrupted, and the fix is a human
                        attaching it before the next firing.
      had it, lost it -> NOT a stop, and not a silent thinning either. Work
                        already done under that connector stays valid; work
                        after the loss must record NOT_RUN with the loss as
                        its reason, so a later firing can close the gap
                        instead of a reader mistaking a dead connector for
                        an absence of evidence about the client.

    The second case is invisible without a record of the first. So the
    orchestrator writes this once, at the boundary where its preflight
    passed, and diffs against it at every stage boundary after.
    """
    import datetime as _dt
    fam = families()
    held = {t.strip() for t in tool_names if t.strip()}
    present = sorted(f for f in fam if _present(f, fam, held))
    rec = {"recorded_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
           "present": present,
           "mcp_tools": sorted(t for t in held if t.startswith("mcp__"))}
    path = baseline_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, indent=2) + "\n")
    rec["path"] = str(path)
    return rec


def probe(tool_names, root=None) -> dict:
    """Diff this session's connectors against its own recorded baseline.

    Returns a verdict a stage boundary can act on without interpretation:
    STABLE, DEGRADED (something present at baseline no longer answers) or
    RECOVERED. A family lost from the REQUIRED set is what makes DEGRADED
    worth stopping the stage for; an optional one is worth recording and
    continuing.
    """
    path = baseline_path(root)
    if not path.is_file():
        raise ContractBroken(
            f"no connector baseline at {path}. It is written once, when the "
            "preflight passes, and nothing can say what this session LOST "
            "without it — only what it currently lacks, which is a different "
            "question with a different answer.")
    base = json.loads(path.read_text())
    fam = families()
    held = {t.strip() for t in tool_names if t.strip()}
    now = sorted(f for f in fam if _present(f, fam, held))
    was = list(base.get("present") or [])

    lost = [f for f in was if f not in now]
    regained = [f for f in now if f not in was]
    required = set(REQUIRED) | {n for g in REQUIRED_ANY for n in g}
    lost_required = [f for f in lost if f in required]

    verdict = "STABLE"
    if lost:
        verdict = "DEGRADED"
    elif regained:
        verdict = "RECOVERED"
    return {
        "verdict": verdict,
        "ok": not lost_required,
        "baseline_at": base.get("recorded_at"),
        "was": was, "now": now,
        "lost": lost, "lost_required": lost_required, "regained": regained,
        "why": ("every connector this session started with still answers"
                if not lost else
                f"lost since the preflight: {', '.join(lost)}. Work already "
                "done under them stands; from here on record every facet "
                "they would have answered as NOT_RUN with THIS as the "
                "reason, and never as an absence of evidence about the "
                "client — a dead connector and an empty world read "
                "identically in a payload and mean opposite things. "
                "A session cannot re-attach a connector: they bind once at "
                "start, so the close is a later firing, not this one."),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("declare", help="the required set, from the registry")
    d.add_argument("--json", action="store_true")
    k = sub.add_parser("check", help="judge a session's bound tool names")
    k.add_argument("--tools", required=True,
                   help="file of tool names, one per line; - for stdin")
    k.add_argument("--json", action="store_true")
    k.add_argument("--strict", action="store_true",
                   help="exit 1 when a required family is missing")
    b = sub.add_parser("baseline",
                       help="record what this session holds, once, so a "
                            "later loss is distinguishable from never "
                            "having had it")
    b.add_argument("--tools", required=True)
    b.add_argument("--root", default=None,
                   help="the run root (default: $DMA_RUN_ROOT, else cwd)")
    b.add_argument("--json", action="store_true")
    r = sub.add_parser("probe",
                       help="diff this session's connectors against its own "
                            "baseline; run at every stage boundary")
    r.add_argument("--tools", required=True)
    r.add_argument("--root", default=None)
    r.add_argument("--json", action="store_true")
    r.add_argument("--strict", action="store_true",
                   help="exit 1 when a REQUIRED family has been lost")
    a = ap.parse_args(argv)

    try:
        if a.cmd == "declare":
            c = contract()
            if a.json:
                print(json.dumps(c, indent=2))
                return 0
            print("connector contract — required for a research/intake firing")
            print(f"  required      {', '.join(c['required'])}")
            for g in c["required_any"]:
                print(f"  at least one  {' or '.join(g)}")
            print(f"  optional      {', '.join(c['optional'])}")
            print("\nderived from EXTERNAL in scripts/provision_agent_tools.py"
                  " — the same table the agents are provisioned from, so a "
                  "family no agent can call cannot be required here.")
            return 0

        raw = (sys.stdin.read() if a.tools == "-"
               else Path(a.tools).read_text())

        if a.cmd == "baseline":
            rec = write_baseline(raw.splitlines(), a.root)
            if a.json:
                print(json.dumps(rec, indent=2))
            else:
                print(f"baseline recorded at {rec['path']}")
                print(f"  present  {', '.join(rec['present']) or 'none'}")
                print("  a stage boundary compares against this; without it "
                      "a lost connector is indistinguishable from one that "
                      "was never attached")
            return 0

        if a.cmd == "probe":
            out = probe(raw.splitlines(), a.root)
            if a.json:
                print(json.dumps(out, indent=2))
            else:
                print(f"{out['verdict']}: {out['why']}")
                print(f"  baseline {out['baseline_at']}")
                print(f"  was      {', '.join(out['was']) or 'none'}")
                print(f"  now      {', '.join(out['now']) or 'none'}")
                if out["lost_required"]:
                    print(f"  LOST REQUIRED: {', '.join(out['lost_required'])}")
            return 1 if (a.strict and not out["ok"]) else 0

        out = check(raw.splitlines())
        if a.json:
            print(json.dumps(out, indent=2))
        else:
            print(f"{out['verdict']}: {out['why']}")
            print(f"  present  {', '.join(out['present']) or 'none'}")
            if out["optional_absent"]:
                print(f"  absent   {', '.join(out['optional_absent'])} "
                      f"(optional) — {out['note_on_absent_optional']}")
            print(f"  session holds {out['held_mcp_tools']} mcp__ tool(s)")
        return 1 if (a.strict and not out["ok"]) else 0

    except ContractBroken as e:
        print(f"CONTRACT BROKEN: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
