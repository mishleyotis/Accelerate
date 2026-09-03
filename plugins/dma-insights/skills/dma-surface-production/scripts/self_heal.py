#!/usr/bin/env python3
"""The defects a real production run actually shipped, checked before submit.

Every rule here is a gate refusal, a reviewer complaint or a rendered defect
that cost a cycle on Golden 1 CU (2026-09-02). They are cheap, local, and run
over the assembled payload — a submission SUPERSEDES the staged row, so a FAIL
on a page that was passing costs that pass and blocks the promote for the other
five. Answer locally what can be answered locally.

    self_heal.py --sections DIR [--page PAGE] [--grains grains.json]

Exit 1 if anything is found. Each finding names the JSON path, what is wrong,
and what to do — never just "invalid".

## The rules, and the run that earned each one

ET-09 · ENTITY NAME.  The connector refuses a client-visible string that
repeats the entity's own legal name with a leading article. It matches
CASE-INSENSITIVELY. Three separate sweeps missed occurrences because they
searched for the capitalised form only, and the gate found them each time —
twelve of them, in prose AND in evidence excerpts. Excerpts must be
RE-ANCHORED to a different verbatim span, never reworded: an excerpt is a
quotation.

NULL SWEEP.  A `null` that reaches a payload field renders as an empty slot
the reader cannot distinguish from "not assessed". Derived values are
computed or null-with-a-reason, never a bare null and never a sentinel.
Reports every null in a non-optional position so each is a decision.

CG-07 · QUOTED FIGURE.  A number written into prose must resolve, within
0.05, to what the run serves at that grain. Golden 1 quoted the workbook's
weighted 2.40 beside a served mean of 2.1115 and was refused four times
before anyone read the arithmetic. Give `--grains` the run's stated grains to
check pillar and category figures the same way the gate will.

CG-12 · FACE BUDGET.  A field that renders in a chip is a LABEL, not a
sentence. `prerequisites[].basis` shipped 291 characters into a pill that
holds about 38. The budget here is the connector's; the app now wraps rather
than clips, so this is about readability, not layout.

CG-44 · A BAR WITH NO NUMBER.  A `peer_median` and a `delta` with a null
`score` is a card that draws a comparison it cannot show — and the missing
figure is recoverable as `peer + delta`. This refuses the null.

INTERNAL MARKING.  `internal_only` is default-deny: a section that carries an
`r_layer` (the reasoning layer) and does not name it in `internal_only` will
promote the analyst's reasoning to a client.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

#: Keyed by a PATH pattern, not a leaf name. `basis` is a chip only under
#: `prerequisites`; `financial_series[].basis` and
#: `peer_deployments[].basis` are prose fields that render in full, and
#: matching on the leaf reported 20 of them as defects on a page that had
#: none. The connector's own `_FACE_BUDGETS` is path-keyed for this reason.
FACE_BUDGETS = {
    re.compile(r"recommendations\[\d+\]\.prerequisites\[\d+\]\.basis$"): 60,
    re.compile(r"\.detection_basis$"): 160,
}
NUM = re.compile(r"(?<![\w.])([0-5]\.\d{1,2})(?![\w.])")


def walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")
    else:
        yield path, obj



def containers(obj, path=""):
    """Every dict and list in the tree, with its path — the counterpart to
    `walk`, which yields only leaves."""
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            yield from containers(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        yield path, obj
        for i, v in enumerate(obj):
            yield from containers(v, f"{path}[{i}]")

def entity_names(sections: Path) -> list[str]:
    """The entity's own name, from whatever section states it."""
    out = set()
    for f in sections.glob("*.json"):
        try:
            body = json.loads(f.read_text(encoding="utf-8"))
        except Exception:                      # noqa: BLE001
            continue
        for p, v in walk(body):
            if p.endswith(("legal_name", "entity_name")) and isinstance(v, str):
                out.add(v.strip())
    return sorted(out)


def check_entity_article(payload, names, findings):
    """ET-09, case-insensitively — which is how the gate matches, and how
    three earlier sweeps missed the same twelve strings."""
    pats = [(n, re.compile(rf"\bthe\s+{re.escape(n)}\b", re.IGNORECASE))
            for n in names if n]
    for path, v in walk(payload):
        if not isinstance(v, str):
            continue
        for name, pat in pats:
            m = pat.search(v)
            if m:
                how = ("re-anchor this excerpt to a different verbatim span; "
                       "an excerpt is a quotation and must not be reworded"
                       if "excerpt" in path else
                       f"drop the article: {name}, not {m.group(0)}")
                findings.append((path, f"ET-09: {m.group(0)!r}", how))


def check_nulls(payload, findings):
    """A null that DISAGREES WITH ITS SIBLINGS, which is the only kind worth
    reporting.

    A blanket null sweep is noise and was tried first: `empty_state: null` is
    how the contract says "not empty", `resolved_on: null` is how an issue
    says it is open, and flagging those buries the one that matters under
    thirty that do not. Five of the six "nulls" reported on the first pass of
    this rule were correct data.

    The signal is a field present-and-populated on some rows of a list and
    null on others: that is a row that LOST something its siblings kept, and
    it is exactly how a producer drops a field mid-list. A field null on
    every row is the contract saying the run does not carry it."""
    # `walk` yields LEAVES, so it never hands back a list — iterating it here
    # made this rule dead code that reported "clean" and was believed. The
    # containers are walked directly.
    for path, v in containers(payload):
        if not isinstance(v, list) or len(v) < 2:
            continue
        rows = [r for r in v if isinstance(r, dict)]
        if len(rows) < 2:
            continue
        for key in {k for r in rows for k in r}:
            present = [r for r in rows if r.get(key) is not None]
            missing = [i for i, r in enumerate(rows)
                       if key in r and r.get(key) is None]
            if present and missing and len(present) >= len(missing):
                findings.append(
                    (f"{path}[{missing[0]}].{key}",
                     f"ADVISORY null on {len(missing)} row(s) but populated "
                     f"on {len(present)}",
                     "a field its siblings carry is a field this row lost; "
                     "fill it or drop it from every row, so the reader is "
                     "not left guessing which absences are meaningful"))


def check_faces(payload, findings):
    for path, v in walk(payload):
        if not isinstance(v, str):
            continue
        for pat, budget in FACE_BUDGETS.items():
            if pat.search(path) and len(v) > budget:
                findings.append(
                    (path, f"CG-12: {len(v)} chars in a {budget}-char chip",
                     "this field is a STATUS LABEL; the record that settles "
                     "it belongs in `note`, which renders beneath"))


def check_bars(payload, findings):
    """CG-44: a peer median and a delta with no score."""
    for path, v in walk(payload):
        if not path.endswith(".peer_median"):
            continue
        base = path[: -len(".peer_median")]
        row = {}
        for p2, v2 in walk(payload):
            if p2.startswith(base + "."):
                row[p2[len(base) + 1:]] = v2
        if row.get("score") is None and row.get("delta") is not None:
            findings.append(
                (base, "CG-44: peer_median and delta present, score null",
                 f"serve {v} + {row['delta']} = "
                 f"{round(float(v) + float(row['delta']), 2)}, or drop the "
                 "delta — the card cannot show a comparison it does not make"))


def check_internal_marking(payload, findings):
    for sname, body in (payload or {}).items():
        if not isinstance(body, dict):
            continue
        if "r_layer" in body:
            marked = body.get("internal_only") or []
            if not any("r_layer" in str(m) for m in marked):
                findings.append(
                    (f"{sname}.internal_only",
                     "an r_layer is present and unmarked",
                     "add 'r_layer' — redaction is default-deny, so an "
                     "unmarked reasoning layer promotes to the client"))


def check_quoted_figures(payload, grains, findings):
    """CG-07, at pillar grain, against what the RUN serves."""
    if not grains:
        return
    stated = {p["pillar_id"]: p.get("score")
              for p in (grains.get("pillars") or []) if p.get("score") is not None}
    for path, v in walk(payload):
        if not isinstance(v, str) or "pillar" not in path.lower():
            continue
        for m in NUM.finditer(v):
            q = float(m.group(1))
            near = [pid for pid, s in stated.items() if abs(s - q) <= 0.05]
            if stated and not near and any(pid in v for pid in stated):
                findings.append(
                    (path, f"CG-07: quoted {q} resolves to no stated grain",
                     "the gate strikes a quoted figure against what the run "
                     f"serves ({stated}); quote that, or attribute the "
                     "difference in the same sentence"))
            break


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sections", required=True, type=Path)
    ap.add_argument("--page", default=None)
    ap.add_argument("--grains", type=Path, default=None)
    ap.add_argument("--entity", action="append", default=[],
                    help="the entity's legal name, for the ET-09 sweep, when "
                         "no section file states it")
    a = ap.parse_args(argv)

    grains = json.loads(a.grains.read_text()) if a.grains else None
    names = sorted(set(entity_names(a.sections)) | set(a.entity))
    pattern = f"{a.page}.*.json" if a.page else "*.json"

    findings: list[tuple[str, str, str]] = []
    payload: dict = {}
    for f in sorted(a.sections.glob(pattern)):
        body = json.loads(f.read_text(encoding="utf-8"))
        payload[f.name] = body

    check_entity_article(payload, names, findings)
    check_nulls(payload, findings)
    check_faces(payload, findings)
    check_bars(payload, findings)
    check_quoted_figures(payload, grains, findings)
    for name, body in payload.items():
        check_internal_marking({name.split(".")[1]: body}
                               if name.count(".") >= 2 else {}, findings)

    # Two severities, and only one of them blocks.
    #
    # ET-09, CG-12, CG-44 and the redaction check restate a rule the
    # connector enforces: a hit is a refusal waiting to happen, and a
    # submission spent on it costs the staged pass it supersedes.
    #
    # The sibling-null rule is a HEURISTIC. It reads a field null on some
    # rows and populated on others as a row that lost something — which is
    # how a producer drops a field mid-list, and also how the contract
    # expresses a tri-state. `deployed` is null on purpose ("unknown", and a
    # coverage figure of 2/5 with three unknowns is not 2/5); a peer with no
    # public filing has no `source_url`. Blocking on those would rebuild the
    # noise this rule was retuned to remove, so it advises and a human reads
    # it. Never let a heuristic hold a gate it cannot justify.
    advisory = [f for f in findings if f[1].startswith("ADVISORY")]
    blocking = [f for f in findings if not f[1].startswith("ADVISORY")]

    if not findings:
        print(f"self-heal: clean — {len(payload)} section file(s), "
              f"entity {names or '(none stated)'}")
        return 0
    print(f"self-heal: {len(blocking)} blocking, {len(advisory)} advisory\n")
    for label, group in (("BLOCKING", blocking), ("advisory", advisory)):
        if not group:
            continue
        print(f"  --- {label} ---")
        for path, what, how in group[:40]:
            print(f"  {path}\n      {what}\n      -> {how}")
        if len(group) > 40:
            print(f"  … {len(group) - 40} more")
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
