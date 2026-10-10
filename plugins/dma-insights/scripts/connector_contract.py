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

WHOSE TOOLS ARE CHECKED (2026-09-14). The caller is the CONDUCTOR's
preflight. Connectors are held and called by the orchestrator tier —
`research-conductor` and the two enrichment specialists — which services
the `search_requests` the research lanes and producers emit; a lane holds
no connector at all. So the tool names this contract judges are the
conductor's session's, written once to the run's baseline before the first
dispatch, and `REQUIRED` here must be a subset of what the conductor's own
manifest grants (a test pins that).

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

EXIT CODES, and the `--strict` trap. 2 means the contract itself is unusable
(the registry moved, a required family is not in it) — a repo defect, never a
session's fault. 1 means a required family is missing — but ONLY under
`--strict`. Without it a STOP still PRINTS and still exits 0, deliberately, so
a caller can quote the verdict without the exit code deciding for it.

That default has a sharp edge and it drew blood (measured 2026-09-12): a
caller that wires this in as a gate and forgets `--strict` gets a silent pass
on a session with no connectors at all, which is the exact condition the gate
exists to catch. **Every caller using this to STOP something must pass
`--strict`.** If you want the verdict rather than the gate, read `--json`.
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
#: becomes a thin result. `drive` left 2026-09-14: the client folder lands
#: through `drive_fetch.py` over Bash and no agent holds a Drive tool, so a
#: session's Drive binding is not a fact this contract can act on.
OPTIONAL: tuple[str, ...] = ("indeed", "quartr")


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


import re as _re

#: A claude.ai connector attached to a session can carry an opaque
#: per-attachment UUID as its server segment instead of its friendly name.
#: Tested AFTER canonicalisation, which has turned its hyphens to underscores.
_OPAQUE_SERVER = _re.compile(
    r"^[0-9a-f]{8}[-_][0-9a-f]{4}[-_][0-9a-f]{4}[-_][0-9a-f]{4}[-_][0-9a-f]{12}$",
    _re.I)


def _split(tool: str):
    """(canonical server, tool segment) of an MCP tool name, or None."""
    parts = tool.split("__", 2)
    if len(parts) != 3 or parts[0] != "mcp":
        return None
    server = parts[1].replace("-", "_")
    if server.startswith("claude_ai_"):
        server = server[len("claude_ai_"):]
    return server, parts[2]


def _present(family: str, fam: dict[str, list[str]], held: set[str]) -> bool:
    """A family answers when ANY of its tools is bound — under its friendly
    server name OR under an opaque one.

    Any rather than all: a connector can expose a subset and still do the
    work, and demanding the full list turns a working session into a stop.

    THE SERVER SEGMENT IS NOT STABLE (verification session for PR #89,
    2026-10-10). A fresh cloud session held Exa as
    `mcp__767c83d5-…__web_search_exa` and Tavily, Clay and Vibe Prospecting
    the same way, and this check — matching `mcp__Exa__web_search_exa`
    exactly — read "present: none" with 302 MCP tools bound. So a name is
    compared on its canonical server (hyphens, the `claude_ai_` prefix), and
    a server whose segment is an opaque UUID counts as a family only when it
    exposes at least two of that family's tool names, or one that carries
    the family's own brand (`web_search_exa`): one shared generic name
    (`search_jobs` is Dice's as well as Indeed's) is not a signature.
    """
    want = [_split(t) for t in fam.get(family, ())]
    want = [w for w in want if w]
    if not want:
        return False
    exact = set(want)
    by_opaque: dict[str, set[str]] = {}
    for t in held:
        sp = _split(t)
        if not sp:
            continue
        if sp in exact:
            return True
        if _OPAQUE_SERVER.match(sp[0]):
            by_opaque.setdefault(sp[0], set()).add(sp[1])
    names = {w[1] for w in want}
    # A name that carries the family's own brand (`web_search_exa`,
    # `tavily_search`) IS a signature on its own; generic names need two.
    branded = {n for n in names if family.lower() in n.lower()}
    need = min(2, len(names))
    return any(segs & branded or len(segs & names) >= need
               for segs in by_opaque.values())


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


def _session_roster(session_id=None) -> dict:
    """This session's MCP roster from its transcript (`session_roster.py`);
    {"found": False} wherever it cannot be read — never a guess."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import session_roster                                 # noqa: PLC0415
        return session_roster.current(session_id)
    except Exception as exc:                                  # noqa: BLE001
        return {"found": False, "tools": [], "mcp_tools": [],
                "workflow_tool": None, "reason": f"{type(exc).__name__}: {exc}"}


def write_baseline(tool_names, root=None, roster=None) -> dict:
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
    import os as _os
    fam = families()
    typed = {t.strip() for t in tool_names if t.strip()}
    # THE TRANSCRIPT IS UNIONED IN (2026-10-10). A typed list is only as good
    # as the typing: Interac's first attempt abbreviated whole families. The
    # session's own roster (`session_roster.py`) is read whenever it exists,
    # so a name the model dropped is still recorded — and a run whose model
    # typed nothing at all still gets a measured baseline.
    roster = roster or {}         # the CLI and ensure_baseline pass it;
    #                               a library call stays exactly what it says
    from_transcript = (set(roster.get("answering_tools")
                           or roster.get("tools") or [])
                       if roster.get("found") else set())
    refused = dict(roster.get("refused_servers") or {})
    if refused:
        # A refusing server's tools are BOUND, but nothing typed can make
        # them answer: drop them from the typed list too.
        typed = {t for t in typed
                 if not (t.startswith("mcp__") and t.split("__", 2)[1] in refused)}
    held = typed | from_transcript
    present = sorted(f for f in fam if _present(f, fam, held))
    sources = [s for s, got in (("typed", typed), ("transcript", from_transcript))
               if got]
    rec = {"recorded_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
           "present": present,
           "mcp_tools": sorted(t for t in held if t.startswith("mcp__")),
           "sources": sources,
           "session_id": (roster.get("session_id")
                          or _os.environ.get("CLAUDE_CODE_SESSION_ID"))}
    if roster.get("found"):
        rec["transcript"] = roster.get("transcript")
    if refused:
        rec["refused_servers"] = refused
    # THE WORKFLOW TOOL IS HELD OR NOT, AND ONLY THE SESSION KNOWS (2026-10-09).
    # A resume or worker restart drops it ("No such tool available: Workflow.
    # Workflow is disabled for this session" — SWBC 10-01, B1 10-08; Cross
    # 10-01 and Arbor 10-06 the same). Recorded only when the list carries
    # built-ins (a list of mcp__ names alone says nothing about Workflow), so
    # an older baseline reads as unknown, never as absent.
    if typed & {"Bash", "Read", "Agent", "Edit"}:
        rec["workflow_tool"] = "Workflow" in typed
    elif roster.get("workflow_tool") is not None:
        # Proven by a Workflow call's own result in the transcript.
        rec["workflow_tool"] = bool(roster["workflow_tool"])
    path = baseline_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, indent=2) + "\n")
    rec["path"] = str(path)
    return rec


def ensure_baseline(root=None, roster=None) -> dict | None:
    """The run's baseline — ADOPTED from this session's transcript when the
    session never wrote one. None only when neither exists.

    WHY (Interac, 2026-10-10, and every run before it): PREFLIGHT, the
    dispatch guard, `engine.pipeline env` and the doctor all refused on a
    missing baseline, and the baseline existed only if the model typed every
    tool it holds — after choosing a run root, which comes later than the
    doctor. The facts were on disk the whole time, in the transcript. So
    every reader calls this first: an existing file is never overwritten (a
    typed baseline carries built-ins the transcript cannot see), and a
    missing one is written from the measured roster with `sources:
    ["transcript"]`. A container with no transcript (a Routine's stub, CI)
    still gets None and still refuses — unverified is still not a pass.
    """
    path = baseline_path(root)
    if path.is_file():
        try:
            rec = json.loads(path.read_text())
        except (OSError, ValueError):
            rec = {}
        rec.update({"path": str(path), "adopted": False})
        return rec
    roster = roster if roster is not None else _session_roster()
    if not roster.get("found") or not roster.get("mcp_tools"):
        return None
    rec = write_baseline([], root, roster=roster)     # answering tools only
    rec["adopted"] = True
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
    k.add_argument("--tools", default=None,
                   help="file of tool names, one per line; - for stdin")
    k.add_argument("--from-session", action="store_true",
                   help="read this session's roster from its transcript "
                        "(unioned with --tools when both are given)")
    k.add_argument("--json", action="store_true")
    k.add_argument("--strict", action="store_true",
                   help="exit 1 when a required family is missing")
    b = sub.add_parser("baseline",
                       help="record what this session holds, once, so a "
                            "later loss is distinguishable from never "
                            "having had it")
    b.add_argument("--tools", default=None,
                   help="optional: the transcript roster is always unioned in")
    b.add_argument("--from-session", action="store_true",
                   help="no typed list: record from the transcript alone")
    b.add_argument("--root", default=None,
                   help="the run root (default: $DMA_RUN_ROOT, else cwd)")
    b.add_argument("--json", action="store_true")
    r = sub.add_parser("probe",
                       help="diff this session's connectors against its own "
                            "baseline; run at every stage boundary")
    r.add_argument("--tools", default=None)
    r.add_argument("--from-session", action="store_true",
                   help="judge NOW from the transcript — it sees a connector "
                        "that dropped mid-session, which a typed list cannot")
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

        if a.tools is None and not a.from_session:
            print("give --tools <file|-> or --from-session", file=sys.stderr)
            return 2
        raw = ("" if a.tools is None else sys.stdin.read() if a.tools == "-"
               else Path(a.tools).read_text())
        roster = _session_roster()
        if a.from_session and not roster.get("found"):
            print(f"NO SESSION ROSTER: {roster.get('reason')} — pass the "
                  "tools with --tools instead", file=sys.stderr)
            if a.tools is None:
                return 2
        names = raw.splitlines()
        if a.cmd in ("check", "probe") and a.from_session and roster.get("found"):
            refused = roster.get("refused_servers") or {}
            names = sorted({n for n in names if not (
                n.startswith("mcp__") and n.split("__", 2)[1] in refused)}
                | set(roster.get("answering_tools") or roster.get("tools") or []))
            for srv, why in refused.items():
                print(f"  BOUND, NOT ANSWERING  {srv}: {why[:120]}",
                      file=sys.stderr)

        if a.cmd == "baseline":
            rec = write_baseline(names, a.root, roster=roster)
            if a.json:
                print(json.dumps(rec, indent=2))
            else:
                print(f"baseline recorded at {rec['path']} "
                      f"(from {' + '.join(rec.get('sources') or ['nothing'])})")
                print(f"  present  {', '.join(rec['present']) or 'none'}")
                print("  a stage boundary compares against this; without it "
                      "a lost connector is indistinguishable from one that "
                      "was never attached")
            return 0

        if a.cmd == "probe":
            out = probe(names, a.root)
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

        out = check(names)
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
