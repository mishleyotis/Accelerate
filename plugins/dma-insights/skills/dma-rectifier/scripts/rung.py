#!/usr/bin/env python3
"""Does the claimed rung resolve to something that exists?

    python scripts/rung.py refinement.json --repo /path/to/Accelerate
    python scripts/rung.py refinement.json            # no repo: reports what it
                                                      # could not check

Shape: templates/refinement.schema.json. A claimed rung that does not resolve is
DOWNGRADED to what it is, not argued about — a refinement recorded as R4 whose
"gate" is a paragraph in a skill file is an R1 wearing a gate's clothes, and the
next run will read the rung, not the paragraph.

What each rung has to resolve to:

  R1  a .md under skills/ or agents/, and check.kind == none
  R2  the same, plus a worked example or measured exemplar in the diff
  R3  an executable check — a test node id or a script entrypoint that exists
  R4  a gate id present in the connector's gate registry
  R5  a migration or a named constraint

And two conditions that are not about the rung at all:

  * `closes` non-empty REQUIRES a negative_control with ran and
    failed_as_expected both true. No third option where you were confident.
  * `reason` is 15-40 words naming what the catch DEPENDS ON.

Exit codes: 0 the claim holds · 1 downgraded or blocked · 2 could not check.
"""
import argparse
import json
import os
import re
import sys

RUNGS = ["R1", "R2", "R3", "R4", "R5"]
GATE_RE = re.compile(r"^(AG|SG|ET|CG)-\d{2}$")


def _exists(repo, rel):
    return bool(repo) and os.path.exists(os.path.join(repo, rel))


def _grep(repo, needle, subdirs, exts):
    """Cheap, deterministic, no dependencies. Returns the first hit's path."""
    if not repo or not needle:
        return None
    for sub in subdirs:
        base = os.path.join(repo, sub)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames
                           if d not in ("__pycache__", "node_modules", ".git")]
            for fn in filenames:
                if exts and not fn.endswith(exts):
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    if needle in open(p, encoding="utf-8", errors="ignore").read():
                        return os.path.relpath(p, repo)
                except OSError:
                    continue
    return None


def check_rung(ref, repo):
    """(verdict, actual_rung, notes[]) — verdict in hold / downgrade / unchecked."""
    claimed = ref.get("rung")
    kind = ((ref.get("check") or {}).get("kind")) or "none"
    cid = ((ref.get("check") or {}).get("id")) or ""
    arte = ref.get("artefacts") or []
    notes, unchecked = [], False

    if claimed not in RUNGS:
        return "downgrade", "R1", [f"rung {claimed!r} is not one of {'/'.join(RUNGS)}"]

    if claimed in ("R1", "R2"):
        if kind != "none":
            notes.append(f"check.kind={kind} on an {claimed} refinement — if a check "
                         f"really landed, the rung is higher than claimed")
        docs = [p for p in arte if p.endswith(".md")]
        if not docs:
            notes.append("no .md artefact — an R1/R2 refinement changes prose")
        if repo:
            missing = [p for p in docs if not _exists(repo, p)]
            if missing:
                notes.append("artefacts do not exist: " + ", ".join(missing))
        else:
            unchecked = True
            notes.append("no --repo: artefact existence not checked")
        return ("hold" if not [n for n in notes if "do not exist" in n] else "downgrade",
                claimed, notes)

    if claimed == "R3":
        if kind not in ("test", "script"):
            return "downgrade", "R2", [f"check.kind={kind} — R3 is an executable check"]
        if not repo:
            return "unchecked", claimed, ["no --repo: cannot resolve the check"]
        node = cid.split("::")[-1].strip()
        hit = _grep(repo, node, ("apps", "packages", "plugins", "scripts", "migrations"),
                    (".py", ".ts", ".tsx", ".js", ".sh"))
        if not hit:
            return "downgrade", "R2", [
                f"check id {cid!r} resolves to no file under the repo — an R3 claim "
                "whose check does not exist is prose"]
        notes.append(f"check resolves: {hit}")
        if ((ref.get("check") or {}).get("result")) != "pass":
            notes.append("check.result is not 'pass' — record the outcome, not a "
                         "description of it")
        return "hold", claimed, notes

    if claimed == "R4":
        if kind != "gate":
            return "downgrade", "R3", [f"check.kind={kind} — R4 is a connector gate"]
        if not GATE_RE.match(cid.strip()):
            notes.append(f"gate id {cid!r} is not of the form AG/SG/ET/CG-nn")
        if not repo:
            return "unchecked", claimed, notes + ["no --repo: gate registry not read"]
        hit = _grep(repo, cid.strip(), ("apps/mcp",), (".py", ".json"))
        if not hit:
            return "downgrade", "R3", notes + [
                f"gate {cid!r} is not in the connector's registry under apps/mcp — a "
                "gate that is not registered refuses nothing"]
        return "hold", claimed, notes + [f"gate resolves: {hit}"]

    # R5
    if kind != "constraint":
        return "downgrade", "R4", [f"check.kind={kind} — R5 is a schema constraint"]
    mig = [p for p in arte if "migrations/" in p]
    if not mig:
        notes.append("no migration in artefacts — a constraint arrives in one")
    if not repo:
        return "unchecked", claimed, notes + ["no --repo: migration not checked"]
    missing = [p for p in mig if not _exists(repo, p)]
    if missing or not mig:
        return "downgrade", "R4", notes + (
            ["migration artefacts do not exist: " + ", ".join(missing)] if missing else [])
    return "hold", claimed, notes + [f"migration present: {mig[0]}"]


def check_closing(ref):
    """The conditions that have nothing to do with the rung. Returns blockers."""
    out = []
    closes = ref.get("closes") or []
    nc = ref.get("negative_control")
    if closes:
        if ((ref.get("check") or {}).get("kind")) == "none":
            out.append("closes findings with check.kind=none — a class fixed with a "
                       "paragraph is not closed, it is untested")
        if not nc:
            out.append("closes findings with no negative_control — you have not shown "
                       "the check would have caught the defect")
        else:
            if not nc.get("ran"):
                out.append("negative_control.ran is false — run it")
            if not nc.get("failed_as_expected"):
                out.append("negative_control.failed_as_expected is false — the check "
                           "passes on the broken state, so it closes nothing")
    words = len((ref.get("reason") or "").split())
    if not 15 <= words <= 40:
        out.append(f"reason is {words} words; the standard is 15-40, naming what the "
                   "catch depends on")
    name = ref.get("cluster_name")
    if name:
        w = len(name.split())
        if not 12 <= w <= 30:
            out.append(f"cluster_name is {w} words; the standard is 12-30 and it must "
                       "state the two points the defect lives between")
    return out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("refinement", nargs="?", default="-",
                    help="refinement JSON, or '-' for stdin")
    ap.add_argument("--repo", default=os.environ.get("DMA_REPO_ROOT"),
                    help="checkout to resolve checks, gates and migrations against "
                         "(default: $DMA_REPO_ROOT). Without it, claims are reported "
                         "as unchecked rather than passed")
    a = ap.parse_args()

    raw = sys.stdin.read() if a.refinement == "-" else open(a.refinement, encoding="utf-8").read()
    doc = json.loads(raw)
    refs = doc if isinstance(doc, list) else [doc]

    rc = 0
    for i, ref in enumerate(refs):
        verdict, actual, notes = check_rung(ref, a.repo)
        blockers = check_closing(ref)
        head = f"  [{i}] claimed {ref.get('rung')}"
        if verdict == "hold":
            print(f"{head} — holds")
        elif verdict == "unchecked":
            print(f"{head} — COULD NOT CHECK (reported as unchecked, never as passed)")
            rc = max(rc, 2)
        else:
            print(f"{head} — DOWNGRADED to {actual}")
            rc = 1
        for n in notes:
            print(f"        · {n}")
        for b in blockers:
            print(f"        ! {b}")
            rc = 1
        if ref.get("rung_not_reached"):
            r = ref["rung_not_reached"]
            print(f"        · rung not reached: {r.get('rung')} — {r.get('reason')}")
            print("          the class stays OPEN; 'we did something' does not close it")
        if ref.get("ceiling"):
            c = ref["ceiling"]
            print(f"        · ceiling {c.get('rung')}: {c.get('reason')}")
    print()
    return rc


if __name__ == "__main__":
    sys.exit(main())
