#!/usr/bin/env python3
"""Feedback sitting in a working tree that memory has never seen.

    python scripts/drain_local.py <dir>
    python scripts/drain_local.py <dir> --json > to_record.json

STEP 1 of the loop. Anything visible only to this session is not memory yet, and
if you triage before recording it, this run's clustering cannot see it and the
store's dedup cannot count it as a sighting. So: record first, triage second.

It emits one `record_finding` payload per candidate, in the shape of
templates/finding.schema.json, with the fields it can establish filled and the
fields that need judgement left null:

    invariant   from a gate id in the text where one appears, else UNKNOWN
    path        the JSON path / file:symbol the artefact names
    verb, locus BLANK where the artefact does not state them — you fill these,
                and until you do the finding cannot be fingerprinted, which
                triage.py will tell you loudly rather than dropping it

What it cannot see: the user's own words, and anything that was said rather than
written. Record those yourself with source=user, quoting them.

Exit codes: 0 always (an empty sweep is a result, not a failure).
"""
import argparse
import json
import os
import re
import sys

GATE = re.compile(r"\b((?:AG|SG|ET|CG)-\d{2})\b")
JPATH = re.compile(r"\b([a-z_]+(?:\.[a-z_]+){1,4}(?:\[\])?(?:\.[a-z_]+)?)\b")
# Two pytest dialects: the short summary (`FAILED node - msg`) and the verbose
# progress line (`node FAILED`). Both appear in one log, so nodes are deduped —
# the summary carries the message and wins.
PYTEST_FAIL = re.compile(r"^(?:FAILED|ERROR)\s+(\S+?)(?:\s+-\s+(.*))?$", re.M)
PYTEST_FAIL_TRAILING = re.compile(r"^(\S+::\S+)\s+(?:FAILED|ERROR)\s*$", re.M)
AUDIT_ROW = re.compile(r"^.*\b(FAIL|UNVERIFIABLE)\b.*$", re.M)

# filename -> (source, severity hint)
NAMED = {
    "qa_verdict.json": ("dma-governance", "material"),
    "issue_register.csv": ("dma-governance", "material"),
    "check_results.json": ("dma-governance", "material"),
    "audit_summary.json": ("dma-governance", "noted"),
}
SUFFIX = (".json", ".csv", ".md", ".txt", ".log", ".out")
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist",
             ".next", "build"}


def _finding(**kw):
    base = {
        "invariant": "UNKNOWN", "path": None, "locus": None, "verb": None,
        "observed": None, "source": "ci", "session_ref": None, "surface": None,
        "severity": "material", "client_reach": None, "excerpt": None,
        "artefact_ref": None, "would_have_caught_it": None, "internal_only": [],
    }
    base.update(kw)
    return base


def from_pytest(text, path, session):
    out, seen = [], set()
    hits = [(m.group(1), (m.group(2) or "").strip(), m.group(0))
            for m in PYTEST_FAIL.finditer(text)]
    hits += [(m.group(1), "", m.group(0)) for m in PYTEST_FAIL_TRAILING.finditer(text)]
    for node, msg, line in hits:
        if node in seen:
            continue
        seen.add(node)
        g = GATE.search(msg) or GATE.search(node)
        out.append(_finding(
            invariant=g.group(1) if g else "UNKNOWN",
            path=node, source="ci", session_ref=session,
            observed=msg or f"{node} failed",
            excerpt=line.strip()[:500], artefact_ref=path,
            severity="blocking", client_reach="caught_before_submit",
            would_have_caught_it="the check exists and fired — this is a defect "
                                 "sighting, not a check gap"))
    return out


def from_verdict(doc, path, session):
    """A connector verdict: gate, JSON path, arithmetic."""
    out = []
    reasons = []
    if isinstance(doc, dict):
        for key in ("reasons", "blocking", "violations", "issues", "findings"):
            v = doc.get(key)
            if isinstance(v, list):
                reasons += [x for x in v if isinstance(x, dict)]
    for r in reasons:
        gate = r.get("gate") or r.get("check") or r.get("id") or ""
        out.append(_finding(
            invariant=gate if GATE.match(str(gate)) else "UNKNOWN",
            path=r.get("path") or r.get("json_path") or r.get("field"),
            source="surface-producer", session_ref=session,
            observed=r.get("message") or r.get("reason") or json.dumps(r)[:300],
            excerpt=json.dumps(r)[:500], artefact_ref=path,
            severity="blocking" if r.get("blocking") else "material",
            client_reach="caught_before_submit"))
    return out


def from_audit(text, path, session):
    out = []
    for m in AUDIT_ROW.finditer(text):
        line = m.group(0).strip()
        if len(line) < 12 or line.startswith("|---"):
            continue
        state = m.group(1)
        jp = JPATH.search(line)
        out.append(_finding(
            invariant=(GATE.search(line).group(1) if GATE.search(line) else "UNKNOWN"),
            path=jp.group(1) if jp else None,
            source="deployed-app-auditor", session_ref=session,
            observed=line[:300], excerpt=line[:500], artefact_ref=path,
            severity="blocking" if state == "FAIL" else "noted",
            client_reach="rendered" if state == "FAIL" else None,
            verb="unreachable" if state == "UNVERIFIABLE" else None,
            locus="serve" if state == "FAIL" else None,
            would_have_caught_it=(
                "an invariant asserted at submit and not observable at serve"
                if state == "UNVERIFIABLE" else None)))
    return out


def sweep(root, session, limit):
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in sorted(filenames):
            if not fn.endswith(SUFFIX):
                continue
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, root)
            try:
                if os.path.getsize(p) > 4_000_000:
                    continue
                text = open(p, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue

            if fn in NAMED or "verdict" in fn:
                try:
                    found += from_verdict(json.loads(text), rel, session)
                    continue
                except (ValueError, TypeError):
                    pass
            if PYTEST_FAIL.search(text):
                found += from_pytest(text, rel, session)
            elif fn.endswith(".md") and AUDIT_ROW.search(text):
                found += from_audit(text, rel, session)
            if len(found) >= limit:
                return found[:limit]
    return found


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", nargs="?", default=".", help="directory to sweep")
    ap.add_argument("--session", default=os.environ.get("CLAUDE_SESSION_ID", "unknown"),
                    help="session_ref stamped on every emitted finding")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--json", action="store_true", help="payloads only, for piping")
    a = ap.parse_args()

    found = sweep(a.dir, a.session, a.limit)

    if a.json:
        print(json.dumps(found, indent=1))
        return 0

    if not found:
        print("\n  local channel empty — nothing in this tree that memory has not "
              "seen.\n  Say so and continue. An empty sweep that ran is a different "
              "fact\n  from a sweep that was skipped, and only one belongs in a "
              "report.\n")
        return 0

    print(f"\n  {len(found)} candidate findings, none of them recorded yet.\n")
    for f in found:
        need = [k for k in ("verb", "locus") if not f.get(k)]
        print(f"  · {f['invariant']:9s} {f.get('path') or '(no path)'}")
        print(f"    {(f.get('observed') or '')[:100]}")
        print(f"    from {f['artefact_ref']}"
              + (f"   NEEDS: {', '.join(need)}" if need else ""))
    print("\n  Fill verb and locus — a finding without them cannot be fingerprinted,")
    print("  and triage.py fails loudly rather than dropping it. Then record them")
    print("  ALL before you triage, so the dedup counts them as sightings.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
