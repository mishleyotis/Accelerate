"""Internal documents for a HYBRID or INTERNAL run — landed, listed, checked.

    python3 -m engine.intake add   --root ROOT --file DOC [--title T] [--source-url U]
    python3 -m engine.intake state --root ROOT [--json]

WHY THIS EXISTS. Measured 2026-09-30 on the SWBC run (HYBRID, bound by the
owner). The research protocol says internal evidence is loaded first into
`<run root>/01_intake/`, read by every lane, registered `--origin internal`,
and that a HYBRID run whose documents were never cited must stop. None of it
was code: `01_intake` appeared in SKILL.md and nowhere in the engine, the
scripts, the agents or the command. A HYBRID run was a PUBLIC run with a
different word in Run_Metadata — the lanes were told the mode and never where
the documents were, and nothing measured whether one was read.

So the three halves are here, and each is enforced where it bites:

  * `add` lands a document under `01_intake/` with a hashed manifest entry.
  * `engine.pipeline` PREFLIGHT refuses a HYBRID/INTERNAL run whose intake is
    empty (`missing_for_mode`), and the shared brief every lane opens with
    lists the documents (`for_brief`).
  * HANDOFF refuses a HYBRID/INTERNAL run with no internal-origin evidence
    registered (`handoff_blocker`) — the documents were not read.

The share rule the protocol used to state ("more than half the cells with no
internal citation") is not enforced: one engagement write-up cannot evidence
half of 760 cells, and a rule every honest hybrid run fails is a rule that
gets waived. Zero internal citations is the unambiguous failure, and it is
the one this refuses.
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
import hashlib
import json
import shutil
import sys
from pathlib import Path

INTAKE_DIR = "01_intake"
MANIFEST = "intake_manifest.json"
NEEDS_INTAKE = ("HYBRID", "INTERNAL")


def _dir(root) -> Path:
    return Path(root) / INTAKE_DIR


def docs(root) -> list[dict]:
    """The manifest's rows whose file is still on disk."""
    m = _dir(root) / MANIFEST
    if not m.is_file():
        return []
    try:
        rows = json.loads(m.read_text()).get("documents") or []
    except (OSError, json.JSONDecodeError):
        return []
    return [r for r in rows if (_dir(root) / str(r.get("file") or "")).is_file()]


def add(root, file, *, title: str | None = None,
        source_url: str | None = None) -> dict:
    src = Path(file)
    if not src.is_file():
        raise FileNotFoundError(f"{src} is not a file")
    data = src.read_bytes()
    if not data.strip():
        raise ValueError(f"{src} is empty — an empty document is not evidence")
    d = _dir(root)
    d.mkdir(parents=True, exist_ok=True)
    dest = d / src.name
    if src.resolve() != dest.resolve():
        shutil.copyfile(src, dest)
    sha = hashlib.sha256(data).hexdigest()
    rows = [r for r in docs(root) if r.get("file") != dest.name]
    row = {"file": dest.name, "title": title or src.stem, "sha256": sha,
           "bytes": len(data), "source_url": source_url or "",
           "added_at": _dt.datetime.now(_dt.timezone.utc).isoformat(
               timespec="seconds")}
    rows.append(row)
    (d / MANIFEST).write_text(json.dumps({"documents": rows}, indent=1))
    return row


def missing_for_mode(root, mode: str | None) -> str | None:
    """A refusal line when the mode needs internal documents and none landed."""
    mode = str(mode or "").upper()
    if mode not in NEEDS_INTAKE or docs(root):
        return None
    return (f"evidence_mode is {mode} and {Path(root) / INTAKE_DIR} holds no "
            f"document. Land each internal document first: python3 -m "
            f"engine.intake add --root {root} --file <doc> --title '<title>'")


def for_brief(root, mode: str | None) -> dict | None:
    """What every lane is told about the internal documents, or None."""
    if str(mode or "").upper() not in NEEDS_INTAKE:
        return None
    rows = docs(root)
    return {
        "documents": [{"path": str(_dir(root) / r["file"]),
                       "title": r.get("title"), "sha256": r.get("sha256", "")[:12]}
                      for r in rows],
        "instruction": (
            "Read each document for what it states, implies and omits about "
            "YOUR cells; register every span you rely on with `engine.cli "
            "evidence … --origin internal` and a verbatim excerpt; cross-check "
            "it against public evidence and note contradictions. Internal "
            "T2 outweighs public T3-T5 for the same cell."),
    }


def internal_rows(wb) -> int:
    return sum(1 for r in wb.rows("Evidence_Detail")
               if str(r.get("Origin") or "").strip().lower() == "internal")


def cited_documents(wb, root) -> dict:
    """{file: rows} — internal evidence rows per landed document, matched by
    the document's source of record (or its local path, for a register
    written before `ledger._intake_source_of_record`)."""
    out = {}
    rows = [r for r in wb.rows("Evidence_Detail")
            if str(r.get("Origin") or "").strip().lower() == "internal"]
    for d in docs(root):
        keys = [k for k in (str(d.get("source_url") or "").strip().rstrip("/"),
                            d["file"]) if k]
        out[d["file"]] = sum(1 for r in rows if any(
            k in str(r.get("Source_URL") or "") for k in keys))
    return out


def declared(root) -> dict:
    """{file: reason} — documents recorded as READ and deliberately not cited."""
    m = _dir(root) / MANIFEST
    try:
        rows = json.loads(m.read_text()).get("documents") or []
    except (OSError, json.JSONDecodeError):
        return {}
    return {r["file"]: r["read_not_cited"] for r in rows if r.get("read_not_cited")}


def declare_read(root, file: str, *, reason: str, actor: str) -> dict:
    """Record that a landed document was read and why nothing in it is cited.

    R-INTERAC-20261010 (2026-10-12): the largest of seven intake documents —
    a 133 KB Zennify blueprint — had no evidence row and nothing said whether
    it was read. Most of it was a reused proposal for ANOTHER client (49
    Navacord mentions to 14 Interac), so citing it would have been foreign
    evidence; its one Interac slide repeated sources the run already held.
    That is a legitimate outcome, and now a recorded one."""
    reason = str(reason or "").strip()
    if len(reason) < 40:
        raise ValueError("say what the document holds and why none of it is "
                         "cited (>=40 chars)")
    m = _dir(root) / MANIFEST
    doc = json.loads(m.read_text())
    hit = next((r for r in doc.get("documents") or [] if r.get("file") == file), None)
    if hit is None:
        raise FileNotFoundError(f"{file} is not in {INTAKE_DIR}/{MANIFEST}")
    hit["read_not_cited"] = reason
    hit["read_by"] = str(actor or "unattributed")
    hit["read_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    m.write_text(json.dumps(doc, indent=1))
    return hit


def handoff_blocker(wb, root) -> str | None:
    mode = str(wb.metadata().get("evidence_mode") or "").upper()
    if mode not in NEEDS_INTAKE:
        return None
    n = len(docs(root))
    if not internal_rows(wb):
        return (f"evidence_mode is {mode}, {n} internal document(s) landed, and "
                f"not one Evidence_Detail row has Origin=internal — the "
                f"documents were not read. Re-dispatch the categories they bear "
                f"on; do not score a hybrid run as if it were public.")
    # EVERY DOCUMENT, NOT ONE (R-INTERAC-20261010): a run citing one of seven
    # documents passed the check above while the largest went unread and
    # unrecorded. A document is cited, or declared read with the reason.
    silent = [f for f, n_rows in cited_documents(wb, root).items()
              if not n_rows and f not in declared(root)]
    if silent:
        return (f"{len(silent)} of {n} intake document(s) have no evidence row "
                f"and no record of being read: {', '.join(silent)}. Cite what "
                f"they hold, or record why nothing is cited: python3 -m "
                f"engine.intake declare-read --root {root} --file <doc> "
                f"--reason '<what it holds and why none of it is cited>'")
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a_ = sub.add_parser("add")
    a_.add_argument("--root", required=True)
    a_.add_argument("--file", required=True)
    a_.add_argument("--title")
    a_.add_argument("--source-url")
    d_ = sub.add_parser("declare-read", help="record that a landed document was "
                        "read and why nothing in it is cited")
    d_.add_argument("--root", required=True)
    d_.add_argument("--file", required=True)
    d_.add_argument("--reason", required=True)
    d_.add_argument("--actor", default="research-conductor")
    s_ = sub.add_parser("state")
    s_.add_argument("--root", required=True)
    s_.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "add":
        try:
            row = add(a.root, a.file, title=a.title, source_url=a.source_url)
        except (FileNotFoundError, ValueError) as e:
            print(f"REFUSED: {e}", file=sys.stderr)
            return 1
        print(json.dumps(row, indent=1))
        return 0
    if a.cmd == "declare-read":
        try:
            row = declare_read(a.root, a.file, reason=a.reason, actor=a.actor)
        except (FileNotFoundError, ValueError) as e:
            print(f"REFUSED: {e}", file=sys.stderr)
            return 1
        print(json.dumps(row, indent=1))
        return 0
    rows = docs(a.root)
    if a.json:
        print(json.dumps({"documents": rows}, indent=1))
    else:
        print(f"{len(rows)} internal document(s) under {_dir(a.root)}")
        for r in rows:
            print(f"  {r['file']}  {r.get('title')}  {r['bytes']} B  {r['sha256'][:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
