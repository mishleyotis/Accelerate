#!/usr/bin/env python3
"""Deep memory: per-category .md files, consolidated into the workbook.

    python3 -m engine.memory note        --run R --category P1C1 --subcap CELL [--subcap CELL ...]
                                         [--facet F] [--kind evidence|lead|absence|contradiction|note]
                                         [--actor NAME] [--claim ...] [--excerpt ...] [--url ...]
                                         [--source-name ...] [--tier ...] [--published ...]
                                         [--claim-type ...] [--ladder ...] [--text ...] [--origin ...]
    python3 -m engine.memory note        --run R --category P1C1 --entries-file FILE|-
    python3 -m engine.memory status      --run R [--category P1C1]
    python3 -m engine.memory consolidate --run R --category P1C1 [--actor NAME]
    python3 -m engine.memory backup      --run R
    python3 -m engine.memory restore     --run R
    python3 -m engine.memory cleanup     --run R [--apply]

THE USAGE BLOCK ABOVE IS THE REAL ONE — every flag in it is a flag the
parser has, which a test pins. From the day this module was written until
2026-09-14 it advertised a `stdin` flag that never existed in the parser: a
usage line nobody can run, costing a turn to discover and teaching nothing.
Entries now arrive through `--entries-file` (a JSON list of objects carrying
the same fields the flags take; `-` reads stdin), which is what that phantom
flag was reaching for: a lane writing forty notes paid forty Bash
round-trips, forty turns on the layer whose whole reason to exist is that it
is cheap.

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
notebook), the backup can be RESTORED into a fresh container, and it is
CLEANED UP once its content is consolidated into the workbook and the
workbook itself is safely off the container. The restore half landed
2026-09-14: until then the lifecycle was push-only, so the backup a dead
container's successor needed was a file nothing could fetch.
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
import shutil
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


def note(run: runstate.Run, *, category: str, subcap=None, facet: str = "",
         kind: str = "evidence", actor: str | None = None,
         entries_file=None, **fields):
    """Append one entry — or, with `entries_file`, MANY in one call.

    `entries_file` is a path (or `-` for stdin, or an already-parsed list) to
    a JSON list of objects carrying the same fields the flags take. It
    returns the batch report `{"noted", "failed", "paths", "entries"}`
    instead of a Path; the single-entry call still returns the notebook Path.

    Cheap on purpose: the only validation here is shape
    vocabulary — substance is judged at CONSOLIDATION by the real gates,
    because a notebook that refuses a hunch defeats its reason to exist.

    `subcap` takes a cell or a SEQUENCE of cells. One source routinely bears
    on several cells of a capability — `append_evidence` and `engine.cli
    evidence --subcap` have always accepted a list — and the notebook was the
    one link in the chain that could not say so, so a lane working a
    capability had to register the same find once per cell or drop the
    others. The entry head stores them comma-joined, which the parser's
    `(\\S+)` already accepts.
    """
    if entries_file is not None:
        return note_entries(run, _read_entries(entries_file),
                            category=category, actor=actor)
    if kind not in KINDS:
        raise ValueError(f"kind {kind!r} not in {KINDS}")
    if subcap is None:
        raise ValueError("note needs at least one subcap")
    cells = ([subcap] if isinstance(subcap, str)
             else [str(s).strip() for s in subcap if str(s).strip()])
    if not cells:
        raise ValueError("note needs at least one subcap")
    subcap = ",".join(cells)
    # THE CATEGORY IS A DIRECTORY NAME, and until 2026-09-14 it was free
    # text: `--category P1C1 --subcap P3C2.4.1` wrote a P3 finding into
    # P1C1's notebook, silently, and `--category P9C9` created a notebook
    # for a category that does not exist. Both survive consolidation as
    # findings nobody looks for.
    cat = str(category or "").strip().upper()
    stray = sorted({c for c in cells if not c.upper().startswith(cat + ".")})
    if stray:
        raise ValueError(
            f"this note is filed under {cat} but names {', '.join(stray[:6])}. "
            f"A notebook is read by the lane that owns the category, so a "
            f"cell filed under another one is a finding nobody will look "
            f"for. File it under its own category.")
    from . import scope as _scope
    why = _scope.violation(actor, "note", cells)
    if why:
        raise ValueError(why)
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


#: What an entry object may say instead of `subcap`, and the flag spelling
#: that maps onto each field name. Hyphens become underscores so a JSON
#: entry can be copied straight off a command line.
_SUBCAP_KEYS = ("subcap", "subcaps", "cell", "cells", "subcap_id")


def _read_entries(src) -> list[dict]:
    """The entry list, from a path, from stdin (`-`), or already parsed."""
    if isinstance(src, (list, tuple)):
        raw = list(src)
    else:
        text = (sys.stdin.read() if str(src) == "-"
                else Path(src).read_text(encoding="utf-8"))
        try:
            raw = json.loads(text)
        except ValueError as e:
            raise ValueError(f"--entries-file is not JSON: {e}") from None
    if not isinstance(raw, list):
        raise ValueError(
            "--entries-file carries a JSON LIST of entry objects, one per "
            "note: [{\"subcap\": \"P1C1.1.1\", \"facet\": \"works\", "
            "\"kind\": \"evidence\", ...}, ...]")
    return raw


def note_entries(run: runstate.Run, entries, *, category: str | None = None,
                 actor: str | None = None) -> dict:
    """Many entries, ONE call, in file order.

    ONE BAD ENTRY MUST NOT COST THE OTHER THIRTY-NINE. Each entry is
    validated by `note` itself — same vocabulary, same category-scope and
    actor-scope refusals — and a failure is reported with its INDEX so the
    researcher can find the one line to repair rather than re-deriving which
    of forty notes the refusal was about. Nothing is rolled back: a notebook
    is append-only, and an entry that landed is a finding that survived.
    """
    noted, failed, paths = 0, [], []
    for i, e in enumerate(entries):
        try:
            if not isinstance(e, dict):
                raise ValueError(f"an entry must be a JSON object, not a "
                                 f"{type(e).__name__}")
            f = {str(k).replace("-", "_"): v for k, v in e.items()}
            cat = str(f.pop("category", None) or category or "").strip()
            sub = next((f.pop(k) for k in _SUBCAP_KEYS if k in f), None)
            p = note(run, category=cat, subcap=sub,
                     facet=str(f.pop("facet", "") or ""),
                     kind=str(f.pop("kind", "evidence") or "evidence"),
                     actor=(f.pop("actor", None) or actor), **f)
            noted += 1
            if str(p) not in paths:
                paths.append(str(p))
        except (ValueError, TypeError, OSError) as err:
            failed.append({"index": i, "error": str(err)})
    return {"noted": noted, "failed": failed, "paths": paths,
            "entries": len(entries)}


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
    verbatim excerpt or the URL) and can repair the NOTE, not guess.

    EXCERPTS ARE VERIFIED HERE (2026-09-14). Consolidation passes
    `verify_excerpts=True`, so a note whose page nothing in this run fetched
    is BLOCKED in place with the ledger's own `excerpt_unverified` — the
    notebook is the route a WebFetch-and-quote lane takes, and it was the
    route around the check. The repair is the one the refusal names: run
    `engine.cli fetch --run <R> --url … --query …` and re-note from a window, or, when
    the page genuinely cannot be fetched, register it directly with
    `engine.cli evidence --unverified '<what stopped it>'`, which records the
    reason on the row. There is deliberately no `--unverified` on a NOTE: an
    unverifiable source is a decision, and a decision belongs on the command
    a person or an agent types once, not in a field a batch consolidation
    reads silently.
    """
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
            outcome = _consolidate_one(wb, e, actor, run=run)
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


def _consolidate_one(wb: RunWorkbook, e: dict, actor: str, run=None) -> str:
    f = e["fields"]
    kind = f.get("kind") or "note"
    # An entry may name several cells (comma-joined by `note`). `sub` stays
    # the FIRST for the single-cell branches below, which are genuinely
    # per-cell decisions; the evidence branch registers against all of them,
    # because one source bearing on four cells of a capability is one
    # registration, not four.
    cells = [c.strip() for c in str(e["subcap"]).split(",") if c.strip()]
    sub = cells[0]
    if kind in ("evidence", "contradiction"):
        eid = L.append_evidence(
            wb, source_name=f.get("source_name") or f.get("source") or "",
            source_url=f.get("url"),
            tier=str(f.get("tier") or "").upper() or "T5",
            excerpt=f.get("excerpt") or "",
            subcaps=cells,
            published=f.get("published"),
            claim_type=str(f.get("claim_type") or
                           ("INFERENCE" if kind == "contradiction"
                            else "FACT")).upper(),
            origin=f.get("origin") or "public",
            run=run, verify_excerpts=True)
        if kind == "contradiction":
            for cell in cells:
                row = wb.scoring_row(cell) or {}
                if not str(row.get("Contradiction_Disposition") or "").strip():
                    wb.set_scoring(cell, {"Contradiction_Disposition":
                                          f"OPEN: {f.get('claim', '')[:160]}"})
        for cell in cells:
            L.record_provenance(wb, cell, "enrichment", actor,
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
        # STAGE, NEVER DECLARE. Measured 2026-09-03: this wrote
        # Absence_Claimed=YES from a notebook line, so a cell with ZERO
        # Search_Log rows read as a searched, declared absence to the
        # worklist, the handoff and the scorer. The ladder text is kept for
        # `engine.cli absence` to bind to; the flag is that command's alone,
        # after its volley, register and enrichment checks.
        wb.set_scoring(sub, {
            "Proxy_Log": (have + "\n" if have else "") + ladder})
        L.record_provenance(
            wb, sub, "enrichment", actor,
            "absence note staged from the notebook into Proxy_Log; NOT "
            "declared — `engine.cli absence` closes the cell")
        return "absence -> Proxy_Log (staged, undeclared)"
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
    # ONE CALL PER FILE, deliberately. `drive_fetch.py push-backup` takes a
    # single `--file` and no list form (read 2026-09-14: `p_bk` declares
    # `--client`, `--file`, `--name`, and `push_backup` uploads exactly one
    # path), so batching here would mean inventing a flag the script does
    # not have. The loop stays until push-backup grows one.
    for f in files:
        r = subprocess.run(
            [sys.executable, str(df), "push-backup", "--client", client,
             "--file", str(f)],
            capture_output=True, text=True, timeout=300)
        (pushed if r.returncode == 0 else failed).append(
            {"file": f.name, "detail": (r.stdout or r.stderr).strip()[-160:]})
    return {"outcome": "RESOLVED" if not failed else "PARTIAL",
            "pushed": pushed, "failed": failed}


#: The drive_fetch verb `restore` needs. It is the mirror of `push-backup`:
#: same client, same `memory-backup` folder, downloading instead of
#: uploading, into `--dest`.
PULL_VERB = "pull-backup"


def restore(run: runstate.Run) -> dict:
    """Pull the Drive backup of the notebooks back into `03_memory/`.

    The mirror of `backup`, and the half the lifecycle was missing: pushing
    a safety copy that nothing can fetch means a dead container still takes
    the notebooks with it. Reports as honestly as `backup` does — a restore
    that did not run says NOT_RUN and why, because a fabricated RESOLVED
    over an empty directory is how a researcher concludes the notes were
    never written.

    A LOCAL NOTEBOOK IS NEVER OVERWRITTEN. The local copy is the live one
    and the backup is older by construction, so a file already on disk is
    reported `kept` and left exactly as it is. Restoring into a running
    container is therefore safe, which is what makes it usable as a repair
    rather than a ceremony.
    """
    df = _drive_fetch()
    if df is None:
        return {"outcome": "NOT_RUN", "restored": [], "kept": [],
                "reason": "drive_fetch.py is not in this install; there is no "
                          "Drive copy to restore from"}
    wb = run.open()
    client = str(wb.metadata().get("entity_name") or run.run_id)
    stage = run.qa_dir / "restore_staging"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(
            [sys.executable, str(df), PULL_VERB, "--client", client,
             "--dest", str(stage)],
            capture_output=True, text=True, timeout=300)
        detail = (r.stdout or r.stderr or "").strip()[-400:]
        if r.returncode != 0:
            if PULL_VERB in (r.stderr or "") and "invalid choice" in (r.stderr or ""):
                return {"outcome": "NOT_RUN", "restored": [], "kept": [],
                        "reason": f"this install's drive_fetch.py has no "
                                  f"`{PULL_VERB}` verb, so the Drive lifecycle "
                                  f"is push-only here and there is nothing to "
                                  f"restore FROM — it is the mirror of "
                                  f"push-backup and has to be added beside it",
                        "detail": detail}
            return {"outcome": "NOT_RUN", "restored": [], "kept": [],
                    "reason": f"drive_fetch.py {PULL_VERB} failed: {detail}"}
        mem = run.root / MEMORY_DIR
        mem.mkdir(parents=True, exist_ok=True)
        restored, kept = [], []
        for f in sorted(stage.glob("*.md")):
            target = mem / f.name
            if target.exists():
                kept.append(f.name)
            else:
                target.write_bytes(f.read_bytes())
                restored.append(f.name)
        if not restored and not kept:
            return {"outcome": "NOT_RUN", "restored": [], "kept": [],
                    "reason": "the Drive backup holds no notebook for this "
                              "client yet", "detail": detail}
        return {"outcome": "RESOLVED", "restored": restored, "kept": kept,
                "detail": detail}
    finally:
        shutil.rmtree(stage, ignore_errors=True)


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
    for name in ("note", "status", "consolidate", "backup", "restore",
                 "cleanup"):
        s = sub.add_parser(name)
        s.add_argument("--run", required=True)
        s.add_argument("--root")
        if name in ("note", "consolidate"):
            s.add_argument("--category", required=True)
        elif name == "status":
            s.add_argument("--category")
        if name == "note":
            s.add_argument("--subcap", action="append",
                           help="the cell this entry bears on. Repeatable: one "
                                "source often bears on several cells of a "
                                "capability, and registering it once against "
                                "all of them is one find, not several. "
                                "Required unless --entries-file is given")
            s.add_argument("--entries-file",
                           help="a JSON LIST of entry objects carrying the same "
                                "fields these flags take — many notes in ONE "
                                "call, validated one by one, each failure "
                                "reported with its index. `-` reads stdin")
            s.add_argument("--facet", default="works")
            s.add_argument("--kind", default="evidence", choices=KINDS)
            s.add_argument("--actor", default=None,
                           help="the agent noting this. Defaults to $DMA_ACTOR; "
                                "a lane notes only its own category")
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
        from . import scope as _scope
        if a.entries_file:
            out = note(run, category=a.category,
                       entries_file=a.entries_file,
                       actor=(a.actor or _scope.actor_from_env() or None))
            print(json.dumps(out, indent=2))
            return 1 if out["failed"] else 0
        if not a.subcap:
            ap.error("note needs --subcap (repeatable) or --entries-file")
        p = note(run, category=a.category, subcap=a.subcap, facet=a.facet,
                 kind=a.kind, actor=(a.actor or _scope.actor_from_env() or None),
                 claim=a.claim, excerpt=a.excerpt, url=a.url,
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
    if a.cmd == "restore":
        out = restore(run)
        print(json.dumps(out, indent=2))
        return 0 if out["outcome"] == "RESOLVED" else 1
    if a.cmd == "cleanup":
        out = cleanup(run, apply=a.apply)
        print(json.dumps(out, indent=2))
        return 0 if out["outcome"] in ("RESOLVED", "WOULD_DELETE") else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
