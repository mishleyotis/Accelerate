#!/usr/bin/env python3
"""Does the claimed rung resolve to something that exists?

    python scripts/rung.py refinement.json --repo /path/to/Accelerate
    python scripts/rung.py refinement.json            # no repo: reports what it
                                                      # could not check

Input is a `record_refinement` payload (or a list of them) — see
templates/refinement.schema.json. The store has no rung column: `target_kind` IS
the rung, and this script asks whether the target it names actually exists.

  DOC · PROCESS   R1   a .md that exists
  SKILL · AGENT   R2   a skill or agent file that exists
  TEST · COMPONENT R3  an executable check — a test node or a script in the repo
  GATE            R4   a gate id present in the connector's registry under apps/mcp
  SCHEMA          R5   a migration or a named constraint that exists

A claimed rung that does not resolve is DOWNGRADED to what it is, not argued
about: a refinement recorded as GATE whose gate is a paragraph in a skill file
is an R1 wearing a gate's clothes, and the next run reads the target_kind.

Three conditions that are not about the rung at all, all blocking:

  * `rationale` opens with `RUNG: R<n> — ` and that rung AGREES with
    target_kind, then 15-40 words naming what the catch depends on.
  * one of `commit_sha` / `change_ref` — a refinement nobody can locate is a
    claim, not a change.
  * `relation: CLOSES` requires a `verification` carrying the NEGATIVE CONTROL
    in both directions: passes on the fixed state, FAILS on the state that
    produced the finding.

Exit codes: 0 the claim holds · 1 downgraded or blocked · 2 could not check.
"""
import argparse
import json
import os
import re
import sys

RUNGS = ["R1", "R2", "R3", "R4", "R5"]
KIND_RUNG = {"DOC": "R1", "PROCESS": "R1", "SKILL": "R2", "AGENT": "R2",
             "TEST": "R3", "COMPONENT": "R3", "GATE": "R4", "SCHEMA": "R5"}
GATE_RE = re.compile(r"\b((?:AG|SG|ET|CG)-\d{2})\b")
RUNG_PREFIX = re.compile(r"^\s*RUNG:\s*(R[1-5])\s*[—:-]\s*(.*)$", re.S)

# Both directions of the negative control, as words that actually appear when it
# was run. Absence of either is reported, never inferred away.
PASSES = re.compile(r"\bpass(?:es|ed|ing)?\b", re.I)
FAILS = re.compile(r"\bfail(?:s|ed|ing|ure)?\b", re.I)


def _walk(repo, subdirs, exts):
    for sub in subdirs:
        base = os.path.join(repo, sub)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames
                           if d not in ("__pycache__", "node_modules", ".git")]
            for fn in filenames:
                if not exts or fn.endswith(exts):
                    yield os.path.join(dirpath, fn)


def _grep(repo, needle, subdirs, exts):
    """Cheap, deterministic, no dependencies. First hit's repo-relative path."""
    if not repo or not needle:
        return None
    for p in _walk(repo, subdirs, exts):
        try:
            if needle in open(p, encoding="utf-8", errors="ignore").read():
                return os.path.relpath(p, repo)
        except OSError:
            continue
    return None


def _target_paths(ref):
    """Repo-relative paths the refinement names, from target and change text."""
    out = []
    t = (ref.get("target") or "").strip()
    if t and "/" in t and not t.startswith(("skill:", "agent:")):
        out.append(t.split("::")[0])
    for m in re.finditer(r"[\w./-]+\.(?:py|md|json|sql|ts|tsx|sh)", ref.get("change") or ""):
        out.append(m.group(0))
    return out


def check_target(ref, repo):
    """(verdict, actual_rung, notes[]) — verdict in hold / downgrade / unchecked."""
    kind = (ref.get("target_kind") or "").upper()
    target = (ref.get("target") or "").strip()
    claimed = KIND_RUNG.get(kind)
    notes = []

    if not claimed:
        return "downgrade", "R1", [
            f"target_kind {kind!r} is not one of {'/'.join(sorted(KIND_RUNG))}"]

    if not repo:
        return "unchecked", claimed, [
            "no --repo: the target was not resolved. Reported as unchecked, "
            "never as passed"]

    if kind in ("DOC", "PROCESS", "SKILL", "AGENT"):
        cand = _target_paths(ref) or []
        if target.startswith(("skill:", "agent:")):
            name = target.split(":", 1)[1]
            hit = _grep(repo, name, ("plugins", "docs", ".claude"), (".md", ".json"))
            if not hit:
                return "downgrade", "R1", [
                    f"{target!r} names no skill or agent under the repo"]
            notes.append(f"target resolves: {hit}")
        missing = [p for p in cand if not os.path.exists(os.path.join(repo, p))]
        if missing:
            return "downgrade", "R1", notes + [
                "artefacts do not exist: " + ", ".join(missing)]
        return "hold", claimed, notes

    if kind in ("TEST", "COMPONENT"):
        node = target.split("::")[-1].strip() or target
        direct = os.path.join(repo, target.split("::")[0])
        if os.path.exists(direct):
            notes.append(f"target file exists: {target.split('::')[0]}")
            if "::" in target and not _grep(repo, node, ("apps", "packages",
                                                         "plugins", "scripts"),
                                            (".py", ".ts", ".tsx", ".js")):
                return "downgrade", "R2", notes + [
                    f"the file exists but {node!r} is not in it — an R3 claim "
                    "whose check does not exist is prose"]
            return "hold", claimed, notes
        hit = _grep(repo, node, ("apps", "packages", "plugins", "scripts",
                                 "migrations"), (".py", ".ts", ".tsx", ".js", ".sh"))
        if not hit:
            return "downgrade", "R2", [
                f"target {target!r} resolves to no file under the repo — an R3 "
                "claim whose check does not exist is prose"]
        return "hold", claimed, [f"check resolves: {hit}"]

    if kind == "GATE":
        gid = (ref.get("gate_added") or target).strip()
        if not GATE_RE.search(gid):
            notes.append(f"gate id {gid!r} is not of the form AG/SG/ET/CG-nn")
        if not ref.get("gate_added"):
            notes.append("gate_added is empty — set it, so the memory holds the "
                         "fix beside the defect")
        hit = _grep(repo, GATE_RE.search(gid).group(1) if GATE_RE.search(gid) else gid,
                    ("apps/mcp",), (".py", ".json"))
        if not hit:
            return "downgrade", "R3", notes + [
                f"gate {gid!r} is not in the connector's registry under apps/mcp — "
                "a gate that is not registered refuses nothing"]
        return "hold", claimed, notes + [f"gate resolves: {hit}"]

    # SCHEMA
    cand = [p for p in ([target] + _target_paths(ref)) if "migrations/" in p]
    if not cand:
        notes.append("no migration named in target or change — a constraint "
                     "arrives in one")
    missing = [p for p in cand if not os.path.exists(os.path.join(repo, p))]
    if missing or not cand:
        return "downgrade", "R4", notes + (
            ["migrations do not exist: " + ", ".join(missing)] if missing else [])
    return "hold", claimed, notes + [f"migration present: {cand[0]}"]


def check_record(ref, actual_rung):
    """The conditions that have nothing to do with the target. Blockers."""
    out = []
    rat = ref.get("rationale") or ""
    m = RUNG_PREFIX.match(rat)
    if not m:
        out.append("rationale does not open with `RUNG: R<n> — ` — the store has "
                   "no rung column, so a rung not written here does not survive "
                   "to the next run")
    else:
        stated, body = m.group(1), m.group(2)
        if actual_rung and stated != actual_rung:
            out.append(f"rationale states {stated} and target_kind is {actual_rung} "
                       "— the target_kind is what landed")
        words = len(body.split())
        if not 15 <= words <= 40:
            out.append(f"rationale reason is {words} words; the standard is 15-40, "
                       "naming what the catch depends on")

    if not (ref.get("commit_sha") or ref.get("change_ref")):
        out.append("neither commit_sha nor change_ref — a refinement nobody can "
                   "locate is a claim, not a change")

    if not (ref.get("finding_ids") or []):
        out.append("no finding_ids — an edit with no finding behind it is a "
                   "preference")

    ver = ref.get("verification") or ""
    if (ref.get("relation") or "").upper() == "CLOSES":
        if not ver:
            out.append("relation=CLOSES with no verification — you have not shown "
                       "the check would have caught the defect")
        else:
            if not PASSES.search(ver):
                out.append("verification does not say the check PASSES on the "
                           "fixed state")
            if not FAILS.search(ver):
                out.append("verification does not say the check FAILS on the state "
                           "that produced the finding — a check that passes on "
                           "both closes nothing and will be believed anyway")
        if actual_rung and RUNGS.index(actual_rung) < 2:
            out.append(f"relation=CLOSES at {actual_rung} — an R1/R2 refinement "
                       "ADDRESSES; a class fixed with a paragraph is untested, "
                       "not closed")
    return out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("refinement", nargs="?", default="-",
                    help="record_refinement payload, or '-' for stdin")
    ap.add_argument("--repo", default=os.environ.get("DMA_REPO_ROOT"),
                    help="checkout to resolve targets, gates and migrations "
                         "against (default: $DMA_REPO_ROOT). Without it, claims "
                         "are reported as unchecked rather than passed")
    a = ap.parse_args()

    raw = sys.stdin.read() if a.refinement == "-" else open(a.refinement, encoding="utf-8").read()
    doc = json.loads(raw)
    refs = doc if isinstance(doc, list) else [doc]

    rc = 0
    for i, ref in enumerate(refs):
        verdict, actual, notes = check_target(ref, a.repo)
        claimed = KIND_RUNG.get((ref.get("target_kind") or "").upper())
        blockers = check_record(ref, actual if verdict != "unchecked" else claimed)
        head = f"  [{i}] {ref.get('target_kind')} → {claimed or '?'}"
        if verdict == "hold":
            print(f"{head} — holds")
        elif verdict == "unchecked":
            print(f"{head} — COULD NOT CHECK (never folded into a pass)")
            rc = max(rc, 2)
        else:
            print(f"{head} — DOWNGRADED to {actual}")
            rc = 1
        for n in notes:
            print(f"        · {n}")
        for b in blockers:
            print(f"        ! {b}")
            rc = 1
    print()
    return rc


if __name__ == "__main__":
    sys.exit(main())
