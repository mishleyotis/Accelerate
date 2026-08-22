#!/usr/bin/env python3
"""Feedback sitting in a working tree that memory has never seen.

    python scripts/drain_local.py <dir>
    python scripts/drain_local.py <dir> --json > to_record.json

STEP 1 of the loop, second half — `ingest_reviewer_feedback()` is the first.
Anything visible only to this session is not memory yet, and if you triage
before recording it, this run's clustering cannot see it and the store's dedup
cannot count it as a sighting. Record first, triage second.

It emits one `record_finding` payload per candidate, in the shape of
templates/finding.schema.json, filling only what the artefact actually states:

    title, observed      from the failure line
    measurement          BUILT from the artefact — the node and its assertion,
                         the gate and its arithmetic, the URL and its two
                         values. This is the field people drop; each source
                         hands you one for free
    component            derived from the path when the path says so
    severity             from the artefact's own state (FAILED, blocking, FAIL)
    raised_by, kind      the test, gate or auditor that saw it
    defect_class         LEFT BLANK — it is a foreign key from
                         list_defect_classes, and a guess files one defect
                         under a second synonym, which is the rot the key
                         exists to prevent

What it cannot see: the user's own words, and anything said rather than
written. Record those yourself with raised_by_kind=USER, quoting them.

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

COMPONENT_BY_PREFIX = (
    ("apps/mcp", "mcp"), ("apps/api", "api"), ("apps/web", "web"),
    ("apps/worker", "worker"), ("migrations", "migrations"),
    ("infra", "infra"), ("packages", "mcp"),
)
NAMED = ("qa_verdict.json", "issue_register.csv", "check_results.json",
         "audit_summary.json")
SUFFIX = (".json", ".csv", ".md", ".txt", ".log", ".out")
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist",
             ".next", "build"}


def component_of(text):
    for prefix, comp in COMPONENT_BY_PREFIX:
        if prefix in (text or ""):
            return comp
    return ""


def _finding(**kw):
    base = {
        # Required by record_finding. Blank means "you fill it" — never guessed.
        "title": None, "observed": None, "measurement": None,
        "component": "", "defect_class": "", "severity": "MAJOR",
        "raised_by_kind": "TEST", "raised_by": "",
        # Optional, filled where the artefact states them.
        "measured_value": None, "expected": None, "file_path": None,
        "surface": None, "gate_id": None, "fix_hint": None,
        "session_ref": None, "source_ref": None,
    }
    base.update(kw)
    return {k: v for k, v in base.items() if v not in (None,)}


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
        file_part = node.split("::")[0]
        out.append(_finding(
            title=f"{node.split('::')[-1]} fails" if "::" in node else f"{node} fails",
            observed=msg or f"{node} failed",
            measurement=f"pytest {file_part} -> {line.strip()}"[:2000],
            component=component_of(node), severity="BLOCKER",
            raised_by_kind="TEST", raised_by=node,
            gate_id=g.group(1) if g else None,
            file_path=file_part, session_ref=session,
            source_ref=f"{path}:{node}"))
    return out


def from_verdict(doc, path, session):
    """A connector verdict: gate, JSON path, arithmetic."""
    out, reasons = [], []
    if isinstance(doc, dict):
        for key in ("reasons", "blocking", "violations", "issues", "findings"):
            v = doc.get(key)
            if isinstance(v, list):
                reasons += [x for x in v if isinstance(x, dict)]
    for r in reasons:
        gate = str(r.get("gate") or r.get("check") or r.get("id") or "")
        jp = r.get("path") or r.get("json_path") or r.get("field") or ""
        msg = r.get("message") or r.get("reason") or json.dumps(r)[:300]
        out.append(_finding(
            title=f"{gate or 'verdict'} on {jp}" if jp else (msg[:90] or "verdict"),
            observed=msg,
            measurement=(f"submit_page_payload verdict: {gate or 'gate'} at "
                         f"{jp or '(no path)'} — {msg}")[:2000],
            component="mcp", severity="BLOCKER" if r.get("blocking") else "MAJOR",
            raised_by_kind="GATE", raised_by=gate or "connector",
            gate_id=GATE.search(gate).group(1) if GATE.search(gate) else None,
            surface=jp or None, session_ref=session,
            source_ref=f"{path}:{gate}:{jp}"))
    return out


def from_audit(text, path, session):
    out = []
    for m in AUDIT_ROW.finditer(text):
        line = m.group(0).strip()
        if len(line) < 12 or line.startswith("|---"):
            continue
        state = m.group(1)
        jp = JPATH.search(line)
        g = GATE.search(line)
        out.append(_finding(
            title=line.strip("| ").split("|")[0].strip()[:120] or line[:120],
            observed=line[:400],
            measurement=f"deployed-app-auditor row, fetched from production: {line}"[:2000],
            component="api" if state == "FAIL" else "",
            severity="BLOCKER" if state == "FAIL" else "MINOR",
            raised_by_kind="MONITOR", raised_by="deployed-app-auditor",
            gate_id=g.group(1) if g else None,
            surface=jp.group(1) if jp else None,
            fix_hint=("an invariant asserted at submit and not observable at "
                      "serve — the fix is usually a probe, not a repair"
                      if state == "UNVERIFIABLE" else None),
            session_ref=session, source_ref=f"{path}:{line[:60]}"))
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
            if PYTEST_FAIL.search(text) or PYTEST_FAIL_TRAILING.search(text):
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
        need = [k for k in ("defect_class", "component") if not f.get(k)]
        short = (f.get("measurement") or "")[:96]
        print(f"  · [{f['severity']:7s}] {f['title']}")
        print(f"    {short}")
        print(f"    raised_by {f['raised_by']}"
              + (f"   NEEDS: {', '.join(need)}" if need else ""))
    print("\n  Fill defect_class from list_defect_classes — it is a foreign key, and")
    print("  a guess files one defect under a second synonym. Check `measurement`")
    print("  survived: 30 characters minimum, with the denominator. Then record")
    print("  them ALL before you triage, so the dedup counts them as sightings.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
