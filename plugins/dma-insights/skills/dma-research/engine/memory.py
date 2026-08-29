#!/usr/bin/env python3
"""Deep memory: per-category .md files, consolidated into the workbook.

    python3 -m engine.memory note        --run R --category P1C1 --subcap ... --facet ... [--stdin | fields]
    python3 -m engine.memory status      --run R [--category P1C1]
    python3 -m engine.memory consolidate --run R --category P1C1 [--actor NAME]
    python3 -m engine.memory backup      --run R
    python3 -m engine.memory cleanup     --run R [--apply]

WHY .MD FILES AT ALL. A category researcher works in a session that can
compact, die mid-turn or lose its context. The workbook write path is
deliberately strict — every evidence row needs a verbatim 50-500 character
excerpt, a resolvable URL, a tier — and mid-flight a researcher often holds
something REAL but not yet registrable: a promising source, a half-quote, a
hunch about a contradiction. Forcing that through the strict path loses it;
keeping it only in context loses it differently. So each category gets an
append-only markdown file the agent writes AS IT WORKS: cheap, human-
readable, greppable, and durable across context loss.

THE .MD IS A NOTEBOOK, NEVER A RECORD. The workbook remains the substrate
(the AUD-0001 settlement). `consolidate` walks the notebook and pushes every
entry through the SAME ledger refusals the direct path enforces — an entry
that cannot register stays in the notebook marked BLOCKED with the ledger's
own reason, visible, never silently dropped and never laundered into the
workbook around the gate. Nothing downstream ever reads the .md files:
reports, gates and the handoff read sheets.

LIFECYCLE, as the owner specified it: the .md files are LOCAL, they get a
DRIVE BACKUP while the run is in flight (a dead container must not cost the
notebook), and the backup is CLEANED UP once its content is consolidated
into the workbook and the workbook itself is safely off the container.
`cleanup` REFUSES until both facts are verified — deleting the only copy of
unconsolidated notes is the one unrecoverable mistake this module can make,
so it is the one it structurally cannot.
"""
from __future__ import annotations

if __package__ in (None, ""):  # noqa: E402
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import argparse
import datetime as _dt
import json
import re
import subprocess
import sys
from pathlib import Path

from . import contract as C
from . import ledger as L
from . import runstate
from .workbook import RunWorkbook

MEMORY_DIR = "03_memory"

#: One notebook entry. `::` field lines under a stamped heading; the STATUS
#: line is the consolidation state machine: NOTED -> CONSOLIDATED | BLOCKED.
_ENTRY_HEAD = re.compile(r"^## \[(NOTED|CONSOLIDATED|BLOCKED)\] (\S+) · (\S+) · (.+)$")
_FIELD = re.compile(r"^(\w+):: ?(.*)$")

#: What an entry may carry. `kind` decides what consolidation does with it.
KINDS = ("evidence", "lead", "absence", "contradiction", "note")


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def memory_path(run: runstate.Run, category: str) -> Path:
    return run.root / MEMORY_DIR / f"{category}.md"


def note(run: runstate.Run, *, category: str, subcap: str, facet: str,
         kind: str = "evidence", **fields) -> Path:
    """Append one entry. Cheap on purpose: the only validation here is shape
    vocabulary — substance is judged at CONSOLIDATION by the real gates,
    because a notebook that refuses a hunch defeats its reason to exist."""
    if kind not in KINDS:
        raise ValueError(f"kind {kind!r} not in {KINDS}")
    if facet and facet not in C.DQ_FACETS:
        raise ValueError(f"facet {facet!r} not in {C.DQ_FACETS}")
    p = memory_path(run, category)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text(
            f"# {category} — research notebook\n\n"
            f"Append-only. A NOTEBOOK, never a record: nothing downstream\n"
            f"reads this file — `engine.memory consolidate` pushes every\n"
            f"entry through the workbook's own refusals, and an entry that\n"
            f"cannot register is marked BLOCKED with the reason, in place.\n")
    lines = [f"\n## [NOTED] {subcap} · {facet or '-'} · {_utcnow()}",
             f"kind:: {kind}"]
    for k, v in fields.items():
        if v is None:
            continue
        v = str(v).replace("\n", " ⏎ ")
        lines.append(f"{k}:: {v}")
    with p.open("a") as fh:
        fh.write("\n".join(lines) + "\n")
    return p


def parse(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    cur = None
    for i, line in enumerate(path.read_text().splitlines(), 1):
        m = _ENTRY_HEAD.match(line)
        if m:
            cur = {"status": m.group(1), "subcap": m.group(2),
                   "facet": m.group(3), "at": m.group(4), "line": i,
                   "fields": {}}
            out.append(cur)
            continue
        if cur is not None:
            f = _FIELD.match(line)
            if f:
                cur["fields"][f.group(1)] = f.group(2).replace(" ⏎ ", "\n")
    return out


def status(run: runstate.Run, category: str | None = None) -> dict:
    cats = ([category] if category else
            sorted(p.stem for p in (run.root / MEMORY_DIR).glob("*.md"))
            if (run.root / MEMORY_DIR).exists() else [])
    per = {}
    for c in cats:
        entries = parse(memory_path(run, c))
        per[c] = {s: sum(1 for e in entries if e["status"] == s)
                  for s in ("NOTED", "CONSOLIDATED", "BLOCKED")}
        per[c]["entries"] = len(entries)
    return {"run_id": run.run_id, "categories": per,
            "unconsolidated": sum(p["NOTED"] for p in per.values()),
            "blocked": sum(p["BLOCKED"] for p in per.values())}


# ── consolidation: the notebook meets the gates ──────────────────────────

def consolidate(run: runstate.Run, category: str, *,
                actor: str = "research-consolidator") -> dict:
    """Every NOTED entry, through the workbook's own write path.

    Per kind:
      evidence       -> ledger.append_evidence (all invariant-4 refusals)
      lead           -> stays a lead: appended to the scoring row's
                        Discovery_Questions (a lead is not evidence, and
                        registering it as evidence would launder it)
      absence        -> Proxy_Log + Absence_Claimed on the row, so the
                        absence-claim obligations bind at synthesis
      contradiction  -> evidence with claim_type from the note, and the
                        row's Contradiction_Disposition seeded OPEN
      note           -> workbook Provenance detail only

    An entry the ledger refuses is rewritten in place as [BLOCKED] with the
    refusal text — the researcher sees exactly what is missing (usually the
    verbatim excerpt or the URL) and can repair the NOTE, not guess."""
    p = memory_path(run, category)
    entries = parse(p)
    wb = run.open()
    text = p.read_text().splitlines() if p.exists() else []
    done = blocked = 0
    offset = 0            # each _mark inserts one line above later entries
    results = []
    for e in entries:
        if e["status"] != "NOTED":
            continue
        try:
            outcome = _consolidate_one(wb, e, actor)
            _mark(text, e, offset, "CONSOLIDATED", outcome)
            done += 1
            results.append({"subcap": e["subcap"], "outcome": outcome})
        except (L.LedgerRefusal, ValueError) as err:
            _mark(text, e, offset, "BLOCKED", str(err))
            blocked += 1
            results.append({"subcap": e["subcap"], "blocked": str(err)[:200]})
        offset += 1
    if text:
        p.write_text("\n".join(text) + "\n")
    return {"category": category, "consolidated": done, "blocked": blocked,
            "results": results}


def _consolidate_one(wb: RunWorkbook, e: dict, actor: str) -> str:
    f = e["fields"]
    kind = f.get("kind") or "note"
    sub = e["subcap"]
    if kind in ("evidence", "contradiction"):
        eid = L.append_evidence(
            wb, source_name=f.get("source_name") or f.get("source") or "",
            source_url=f.get("url"),
            tier=str(f.get("tier") or "").upper() or "T5",
            excerpt=f.get("excerpt") or "",
            subcaps=[sub],
            published=f.get("published"),
            claim_type=str(f.get("claim_type") or
                           ("INFERENCE" if kind == "contradiction"
                            else "FACT")).upper(),
            origin=f.get("origin") or "public")
        if kind == "contradiction":
            row = wb.scoring_row(sub) or {}
            if not str(row.get("Contradiction_Disposition") or "").strip():
                wb.set_scoring(sub, {"Contradiction_Disposition":
                                     f"OPEN: {f.get('claim', '')[:160]}"})
        L.record_provenance(wb, sub, "enrichment", actor,
                            f"memory consolidation -> {eid}")
        return eid
    if kind == "lead":
        row = wb.scoring_row(sub)
        if row is None:
            raise ValueError(f"{sub} is not in this run's engagement set")
        have = str(row.get("Discovery_Questions") or "").strip()
        lead = f"LEAD: {f.get('claim') or f.get('text') or ''} " \
               f"({f.get('url') or 'no url yet'})"
        wb.set_scoring(sub, {"Discovery_Questions":
                             (have + "\n" if have else "") + lead})
        return "lead -> Discovery_Questions"
    if kind == "absence":
        row = wb.scoring_row(sub)
        if row is None:
            raise ValueError(f"{sub} is not in this run's engagement set")
        ladder = f.get("ladder") or f.get("proxy_log") or ""
        if not ladder.strip():
            raise ValueError(
                "an absence note needs its ladder — what was searched, rung "
                "by rung. Without it the synthesis-time absence obligations "
                "have nothing to bind to.")
        have = str(row.get("Proxy_Log") or "").strip()
        wb.set_scoring(sub, {
            "Proxy_Log": (have + "\n" if have else "") + ladder,
            "Absence_Claimed": "YES"})
        return "absence -> Proxy_Log"
    L.record_provenance(wb, sub, "enrichment", actor,
                        f"note: {(f.get('claim') or f.get('text') or '')[:160]}")
    return "note -> Provenance"


def _mark(text: list[str], e: dict, offset: int, new_status: str,
          detail: str) -> None:
    """Rewrite one entry's status in place, with the reason on the next line.

    `offset` is how many lines earlier _mark calls have already inserted
    above this entry in THIS pass — entries are processed in file order, so
    the caller counts inserts and the parse's line numbers stay honest."""
    i = e["line"] - 1 + offset
    text[i] = text[i].replace(f"[{e['status']}]", f"[{new_status}]", 1)
    text.insert(i + 1, f"consolidation:: {new_status}: "
                       f"{detail.splitlines()[0][:240]} · {_utcnow()}")


# ── the Drive lifecycle ──────────────────────────────────────────────────

def _drive_fetch() -> Path | None:
    p = Path(__file__).resolve().parents[3] / "scripts" / "drive_fetch.py"
    return p if p.exists() else None


def backup(run: runstate.Run) -> dict:
    """Push the notebooks (and the workbook) to Drive. Honest outcomes only:
    a backup that did not run says NOT_RUN and why — a fabricated success
    here costs the notebook on the next dead container."""
    df = _drive_fetch()
    if df is None:
        return {"outcome": "NOT_RUN",
                "reason": "drive_fetch.py is not in this install; the "
                          "notebooks exist only in this container"}
    wb = run.open()
    client = str(wb.metadata().get("entity_name") or run.run_id)
    pushed, failed = [], []
    files = sorted((run.root / MEMORY_DIR).glob("*.md")) + \
        ([run.workbook_path] if run.workbook_path.exists() else [])
    for f in files:
        r = subprocess.run(
            [sys.executable, str(df), "push-backup", "--client", client,
             "--file", str(f)],
            capture_output=True, text=True, timeout=300)
        (pushed if r.returncode == 0 else failed).append(
            {"file": f.name, "detail": (r.stdout or r.stderr).strip()[-160:]})
    return {"outcome": "RESOLVED" if not failed else "PARTIAL",
            "pushed": pushed, "failed": failed}


def cleanup(run: runstate.Run, *, apply: bool = False) -> dict:
    """Remove the Drive backup — REFUSED until it cannot cost anything.

    Three conditions, each verified from the artefacts, none from memory:
      1. no notebook entry anywhere is still NOTED (all consolidated or
         explicitly BLOCKED-and-visible),
      2. no entry is BLOCKED (a blocked entry's only durable copy may be
         the backup),
      3. the WORKBOOK has a copy off this container (persist has run, or
         the backup itself carries it — which is why cleanup verifies the
         workbook was pushed more recently than the last consolidation).
    Without --apply it reports what it WOULD do, which is the safe default."""
    st = status(run)
    reasons = []
    if st["unconsolidated"]:
        reasons.append(f"{st['unconsolidated']} entr(ies) still NOTED — "
                       f"consolidate them first")
    if st["blocked"]:
        reasons.append(f"{st['blocked']} entr(ies) BLOCKED — repair or "
                       f"explicitly resolve them; the backup may hold their "
                       f"only durable copy")
    if reasons:
        return {"outcome": "REFUSED", "reasons": reasons}
    df = _drive_fetch()
    if df is None:
        return {"outcome": "NOT_RUN", "reason": "drive_fetch.py absent"}
    if not apply:
        return {"outcome": "WOULD_DELETE",
                "note": "conditions met; re-run with --apply"}
    wb = run.open()
    client = str(wb.metadata().get("entity_name") or run.run_id)
    # The workbook's durable copy lands OUTSIDE the folder about to be
    # deleted — push-final writes to the client folder's root, which is what
    # makes deleting memory-backup unable to cost anything.
    r = subprocess.run(
        [sys.executable, str(df), "push-final", "--client", client,
         "--file", str(run.workbook_path)],
        capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        return {"outcome": "REFUSED",
                "reasons": ["could not push the final workbook copy before "
                            "deleting the notebook backup: "
                            + (r.stdout or r.stderr).strip()[-200:]]}
    d = subprocess.run(
        [sys.executable, str(df), "cleanup-backup", "--client", client],
        capture_output=True, text=True, timeout=300)
    return {"outcome": "RESOLVED" if d.returncode == 0 else "PARTIAL",
            "detail": (d.stdout or d.stderr).strip()[-400:]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("note", "status", "consolidate", "backup", "cleanup"):
        s = sub.add_parser(name)
        s.add_argument("--run", required=True)
        s.add_argument("--root")
        if name in ("note", "consolidate"):
            s.add_argument("--category", required=True)
        elif name == "status":
            s.add_argument("--category")
        if name == "note":
            s.add_argument("--subcap", required=True)
            s.add_argument("--facet", default="works")
            s.add_argument("--kind", default="evidence", choices=KINDS)
            for f in ("claim", "excerpt", "url", "source-name", "tier",
                      "published", "claim-type", "ladder", "text", "origin"):
                s.add_argument(f"--{f}")
        if name == "consolidate":
            s.add_argument("--actor", default="research-consolidator")
        if name == "cleanup":
            s.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    run = runstate.locate(a.run, Path(a.root) if a.root else None)
    if a.cmd == "note":
        p = note(run, category=a.category, subcap=a.subcap, facet=a.facet,
                 kind=a.kind, claim=a.claim, excerpt=a.excerpt, url=a.url,
                 source_name=getattr(a, "source_name", None), tier=a.tier,
                 published=a.published,
                 claim_type=getattr(a, "claim_type", None),
                 ladder=a.ladder, text=a.text, origin=a.origin)
        print(json.dumps({"noted": str(p)}))
        return 0
    if a.cmd == "status":
        print(json.dumps(status(run, a.category), indent=2))
        return 0
    if a.cmd == "consolidate":
        print(json.dumps(consolidate(run, a.category, actor=a.actor),
                         indent=2))
        return 0
    if a.cmd == "backup":
        print(json.dumps(backup(run), indent=2))
        return 0
    if a.cmd == "cleanup":
        out = cleanup(run, apply=a.apply)
        print(json.dumps(out, indent=2))
        return 0 if out["outcome"] in ("RESOLVED", "WOULD_DELETE") else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
