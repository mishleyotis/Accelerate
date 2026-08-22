#!/usr/bin/env python3
"""Where every produced artifact lives, and how it is found again.

    artifact_store.py plan   --run R --page overview --section scores --agent overview-hero-producer --kind payload
    artifact_store.py put    --run R --page ... --agent ... --kind payload --file body.json --root DIR
    artifact_store.py find   --root DIR [--run R] [--page P] [--section S] [--agent A] [--kind K]
    artifact_store.py audit  --root DIR
    artifact_store.py heal   --root DIR [--apply]
    artifact_store.py taxonomy

WHY THIS EXISTS. Producing an artifact and being able to find it again are
different problems, and only the first was solved. Sections were written to a
flat `surfaces/<payload_section>.json`, so two producers on the same section
overwrote each other, a challenge report had nowhere of its own, nothing
recorded WHICH agent produced a body, and the only way to know whether a piece
of work already existed was to remember doing it. Work was redone; work went
missing; neither was detectable.

THE ONE IDEA. An artifact's NAME determines its PATH:

    <run8>__<page>__<section>__<agent>__<kind>__<utc>.json
      |
      └─> <NN>_<page>/<section>/<agent>/

So a file found in the wrong folder can be routed home from its own name, with
no index to consult and nothing to trust. That is what makes `audit` and `heal`
possible at all, and it is why the name is redundant with the path on purpose —
the redundancy IS the check.

VERIFY BEFORE PLACING, always. `put` refuses unless three things agree: the
name's derived path, the requested path, and the artifact's own body (its
run_id / page / section). Two agreeing and one dissenting is a refusal, never a
majority vote — a body that disagrees with its name is the case where writing
it anywhere makes the tree lie.

The taxonomy is READ FROM the routing authority (05-lifecycle/surface-map.md),
never restated here. A second copy of the page/section/agent mapping is a
second thing to drift, and `RULE_HELD_IN_TWO_PLACES_DRIFTS` is already the
third most common open defect class in this system.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SURFACE_MAP = (HERE.parent / "skills" / "dma-surface-production" /
               "05-lifecycle" / "surface-map.md")

# Page order fixes the folder prefix so a listing sorts the way the pipeline
# runs, rather than alphabetically (context before overview reads as nonsense
# to anyone opening the folder).
PAGE_ORDER = ["overview", "insights", "heatmap", "platform", "context",
              "techstack"]
PAGE_DIR = {p: f"{(i + 1) * 10:02d}_{p}" for i, p in enumerate(PAGE_ORDER)}

RUN_DIR = "00_run"          # gate verdicts, claims, manifests
PAGE_LEVEL = "_page"        # consolidator / surface-producer, above sections
QA_DIR = "90_qa"            # checkers and auditors that span sections
ENRICH_DIR = "95_enrichment"
LEDGER_DIR = "99_ledgers"

# Artifact kinds. Deliberately closed: an open vocabulary means every agent
# invents its own word for the same thing and `find` stops working.
KINDS = ("payload", "challenge", "consolidated", "evidence", "verdict",
         "plan", "report", "audit", "memory", "manifest", "gate", "ledger")

SEP = "__"
NAME_RE = re.compile(
    r"^(?P<run>[0-9a-f]{8})" + SEP +
    r"(?P<page>[a-z_]+)" + SEP +
    r"(?P<section>[a-z0-9_]+)" + SEP +
    r"(?P<agent>[a-z0-9-]+)" + SEP +
    r"(?P<kind>[a-z]+)" + SEP +
    r"(?P<ts>\d{8}T\d{6}Z)"
    r"(?P<ext>\.[a-z]+)$")


class Refused(Exception):
    """A placement that would make the tree lie."""


# ── the taxonomy, read from the routing authority ────────────────────────


def taxonomy(path: Path = SURFACE_MAP) -> dict:
    """{page: {section: [agents]}} parsed from surface-map.md.

    Read rather than restated. If a surface changes owner in the routing
    authority, this follows on the next call; a hardcoded copy would not, and
    would be believed.
    """
    out: dict = {}
    if not path.is_file():
        return out
    for line in path.read_text().splitlines():
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 7:
            continue
        sid, _name, _dash, _parent, agent, _anchor, section = cells[:7]
        if not re.match(r"^[A-Z]+\d", sid):
            continue
        agent = agent.split("(")[0].split("—")[0].strip()
        if not agent or agent.startswith("server-computed"):
            continue
        for page, sec in re.findall(r"([a-z_]+)\.([a-z_]+)", section):
            if page not in PAGE_DIR:
                continue
            out.setdefault(page, {}).setdefault(sec, [])
            if agent not in out[page][sec]:
                out[page][sec].append(agent)
    return out


# ── names and paths ──────────────────────────────────────────────────────


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def artifact_name(run_id: str, page: str, section: str, agent: str,
                  kind: str, ts: str | None = None, ext: str = ".json") -> str:
    if kind not in KINDS:
        raise Refused(f"unknown kind {kind!r}; the vocabulary is closed: "
                      f"{', '.join(KINDS)}")
    run8 = (run_id or "").replace("-", "")[:8].lower()
    if len(run8) != 8:
        raise Refused(f"run id {run_id!r} does not yield 8 hex characters")
    for label, value in (("page", page), ("section", section)):
        if not re.fullmatch(r"[a-z0-9_]+", value or ""):
            raise Refused(f"{label} {value!r} is not a taxonomy token "
                          f"(lowercase, digits and underscore only)")
    if not re.fullmatch(r"[a-z0-9-]+", agent or ""):
        raise Refused(f"agent {agent!r} is not a taxonomy token")
    return SEP.join([run8, page, section, agent, kind,
                     ts or _stamp()]) + ext


def parse_name(name: str) -> dict | None:
    m = NAME_RE.match(name)
    return m.groupdict() if m else None


def folder_for(page: str, section: str, agent: str) -> str:
    """The ONE correct folder for this artifact, as a relative path."""
    if page == "run":
        return RUN_DIR
    if page == "qa":
        return f"{QA_DIR}/{agent}"
    if page == "enrichment":
        return f"{ENRICH_DIR}/{agent}"
    if page == "ledger":
        return LEDGER_DIR
    if page not in PAGE_DIR:
        raise Refused(f"unknown page {page!r}; known: "
                      f"{', '.join(PAGE_ORDER)} (plus run/qa/enrichment/ledger)")
    if section == "_page":
        return f"{PAGE_DIR[page]}/{PAGE_LEVEL}/{agent}"
    return f"{PAGE_DIR[page]}/{section}/{agent}"


def folder_for_name(name: str) -> str | None:
    p = parse_name(name)
    return None if p is None else folder_for(p["page"], p["section"], p["agent"])


# ── verify before placing ────────────────────────────────────────────────


def verify_placement(root: Path, name: str, dest_rel: str,
                     body: dict | None = None) -> list:
    """Every reason this artifact must not be written here. Empty means write.

    Three sources have to agree — the name, the requested folder, and the
    body. Any dissent refuses. A body that disagrees with its own name is
    exactly the case where writing it anywhere leaves the tree lying about
    what it holds, so it is never resolved by taking two-out-of-three.
    """
    problems = []
    parsed = parse_name(name)
    if parsed is None:
        return [f"{name!r} is not a taxonomy name "
                f"(<run8>{SEP}<page>{SEP}<section>{SEP}<agent>{SEP}<kind>"
                f"{SEP}<utc>.ext)"]
    try:
        derived = folder_for(parsed["page"], parsed["section"], parsed["agent"])
    except Refused as e:
        return [str(e)]
    if dest_rel.strip("/") != derived:
        problems.append(f"name says {derived!r}, placement says "
                        f"{dest_rel.strip('/')!r}")
    if body is not None and isinstance(body, dict):
        # The body's own account of itself, where it gives one. Silence is
        # accepted — many artefacts legitimately carry no envelope — but a
        # CONTRADICTION never is.
        rid = str(body.get("run_id") or "").replace("-", "").lower()
        if rid and not rid.startswith(parsed["run"]):
            problems.append(f"body run_id {body.get('run_id')!r} is not the "
                            f"name's run {parsed['run']!r}")
        for key, want in (("page", parsed["page"]), ("section", parsed["section"])):
            got = body.get(key)
            if isinstance(got, str) and got and got != want and want != "_page":
                problems.append(f"body {key} {got!r} is not the name's {want!r}")
    return problems


def put(root: Path, run_id: str, page: str, section: str, agent: str,
        kind: str, payload, ts: str | None = None) -> Path:
    """Write one artifact to its one correct place, or refuse."""
    name = artifact_name(run_id, page, section, agent, kind, ts)
    dest_rel = folder_for(page, section, agent)
    body = payload if isinstance(payload, dict) else None
    problems = verify_placement(root, name, dest_rel, body)
    if problems:
        raise Refused("; ".join(problems))
    dest = root / dest_rel
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / name
    out.write_text(payload if isinstance(payload, str)
                   else json.dumps(payload, indent=1, default=str))
    return out


# ── retrieval: recursive, so misplaced work is still found ───────────────


def find(root: Path, run: str | None = None, page: str | None = None,
         section: str | None = None, agent: str | None = None,
         kind: str | None = None) -> list:
    """Every matching artifact anywhere under root, newest first.

    RECURSIVE ON PURPOSE. A lookup that only reads the correct folder cannot
    find work that was filed wrongly, and reports it as absent — which is the
    exact condition under which it gets produced a second time. Searching the
    whole tree means a misplaced artefact still prevents the redo, and `audit`
    can put it right afterwards.
    """
    run8 = (run or "").replace("-", "")[:8].lower() or None
    hits = []
    if not root.is_dir():
        return hits
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        parsed = parse_name(p.name)
        if parsed is None:
            continue
        if run8 and parsed["run"] != run8:
            continue
        if page and parsed["page"] != page:
            continue
        if section and parsed["section"] != section:
            continue
        if agent and parsed["agent"] != agent:
            continue
        if kind and parsed["kind"] != kind:
            continue
        rel = p.relative_to(root).parent.as_posix()
        hits.append({
            "path": p, "rel": p.relative_to(root).as_posix(),
            **parsed,
            "misplaced": rel != folder_for(parsed["page"], parsed["section"],
                                           parsed["agent"]),
            "belongs": folder_for(parsed["page"], parsed["section"],
                                  parsed["agent"]),
        })
    hits.sort(key=lambda h: h["ts"], reverse=True)
    return hits


def latest(root: Path, **kw):
    hits = find(root, **kw)
    return hits[0] if hits else None


# ── misplacement: detect, then move only after verifying ─────────────────


def audit(root: Path) -> dict:
    """What is filed wrongly, and what carries no taxonomy name at all."""
    misplaced, unnamed = [], []
    for p in root.rglob("*"):
        if not p.is_file() or p.name.startswith("."):
            continue
        parsed = parse_name(p.name)
        if parsed is None:
            # state.json, the memory file and the ledgers are named by their
            # own older conventions and are not artefacts of this store.
            if p.name in ("state.json",) or p.suffix in (".md",):
                continue
            unnamed.append(p.relative_to(root).as_posix())
            continue
        rel = p.relative_to(root).parent.as_posix()
        belongs = folder_for(parsed["page"], parsed["section"], parsed["agent"])
        if rel != belongs:
            misplaced.append({"rel": p.relative_to(root).as_posix(),
                              "belongs": belongs, "name": p.name})
    return {"misplaced": misplaced, "unnamed": unnamed}


def heal(root: Path, apply: bool = False) -> list:
    """Move misplaced artifacts home — verifying each one BEFORE it moves.

    A heal that trusted the name alone would happily relocate a file whose
    body contradicts it, turning one misfiled artefact into a confidently
    misfiled one. Each move is re-verified against the body it actually
    carries, and a refusal leaves the file exactly where it is with the reason
    recorded.
    """
    moves = []
    for row in audit(root)["misplaced"]:
        src = root / row["rel"]
        body = None
        if src.suffix == ".json":
            try:
                body = json.loads(src.read_text())
            except Exception:                                # noqa: BLE001
                body = None
        problems = verify_placement(root, row["name"], row["belongs"],
                                    body if isinstance(body, dict) else None)
        if problems:
            moves.append({**row, "moved": False,
                          "refused": "; ".join(problems)})
            continue
        dest = root / row["belongs"] / row["name"]
        if apply:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                moves.append({**row, "moved": False,
                              "refused": "an artifact of that exact name is "
                                         "already filed correctly"})
                continue
            shutil.move(str(src), str(dest))
        moves.append({**row, "moved": bool(apply), "refused": None})
    return moves


# ── cli ──────────────────────────────────────────────────────────────────


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="artifact_store", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, root=True):
        if root:
            p.add_argument("--root", required=True, type=Path)
        p.add_argument("--run"); p.add_argument("--page")
        p.add_argument("--section"); p.add_argument("--agent")
        p.add_argument("--kind")

    p_plan = sub.add_parser("plan", help="where would this artifact go?")
    common(p_plan, root=False)

    p_put = sub.add_parser("put", help="write one artifact, verified")
    common(p_put)
    p_put.add_argument("--file", required=True, type=Path)

    common(sub.add_parser("find", help="recursive search"))
    sub.add_parser("audit", help="what is misfiled").add_argument(
        "--root", required=True, type=Path)
    p_heal = sub.add_parser("heal", help="move misfiled artifacts home")
    p_heal.add_argument("--root", required=True, type=Path)
    p_heal.add_argument("--apply", action="store_true",
                        help="actually move (default: report only)")
    sub.add_parser("taxonomy", help="the page/section/agent map in use")

    a = ap.parse_args(argv)
    try:
        if a.cmd == "taxonomy":
            t = taxonomy()
            for page in PAGE_ORDER:
                secs = t.get(page, {})
                print(f"{PAGE_DIR[page]}/  ({len(secs)} sections)")
                for sec, agents in sorted(secs.items()):
                    for ag in agents:
                        print(f"   {sec}/{ag}/")
            print(f"\n{RUN_DIR}/  {QA_DIR}/<agent>/  {ENRICH_DIR}/<agent>/  "
                  f"{LEDGER_DIR}/")
            return 0

        if a.cmd == "plan":
            name = artifact_name(a.run, a.page, a.section, a.agent, a.kind)
            print(f"{folder_for(a.page, a.section, a.agent)}/{name}")
            return 0

        if a.cmd == "put":
            body = json.loads(a.file.read_text()) if a.file.suffix == ".json" \
                else a.file.read_text()
            out = put(a.root, a.run, a.page, a.section, a.agent, a.kind, body)
            print(out.relative_to(a.root).as_posix())
            return 0

        if a.cmd == "find":
            hits = find(a.root, a.run, a.page, a.section, a.agent, a.kind)
            for h in hits:
                flag = "  MISPLACED -> " + h["belongs"] if h["misplaced"] else ""
                print(f"{h['rel']}{flag}")
            print(f"\n{len(hits)} artifact(s)", file=sys.stderr)
            return 0

        if a.cmd == "audit":
            rep = audit(a.root)
            for m in rep["misplaced"]:
                print(f"MISPLACED  {m['rel']}  -> {m['belongs']}")
            for u in rep["unnamed"]:
                print(f"UNNAMED    {u}")
            n = len(rep["misplaced"]) + len(rep["unnamed"])
            print(f"\n{len(rep['misplaced'])} misplaced, "
                  f"{len(rep['unnamed'])} unnamed", file=sys.stderr)
            return 1 if n else 0

        if a.cmd == "heal":
            for m in heal(a.root, a.apply):
                if m["refused"]:
                    print(f"REFUSED    {m['rel']}: {m['refused']}")
                else:
                    verb = "MOVED" if m["moved"] else "WOULD MOVE"
                    print(f"{verb:10} {m['rel']} -> {m['belongs']}")
            return 0
    except Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
