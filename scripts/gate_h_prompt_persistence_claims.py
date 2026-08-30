#!/usr/bin/env python3
"""Gate H — the producer prompts may not claim a stored field is unstored.

WHY THIS EXISTS, measured 2026-08-18.

`03-pages/5-context.md` told producers, in bold, that `capped_subcap_ids`
"is validated at submit and has **no column** on `context_issue_register`
— it is dropped at promote", and instructed them to design around the
loss. Migration `0027_promotion_field_gaps` had already given it a JSONB
column and the writer binds it. The paragraph was true when it was
written and had been false ever since, and nothing could tell.

That is a worse failure than a wrong sentence in a document. These
prompts are the producing agent's whole picture of what survives
promotion, so a stale persistence claim does not merely misinform — it
changes what gets written. A producer told a field is dropped stops
sending it, or duplicates its substance into prose, and the surface it
was meant to fill goes empty for a reason nobody can see from the
payload, the gates or the page.

WHAT IS AND IS NOT CHECKED

Only claims about fields the CONTRACT declares and a WRITER binds. The
prompts also warn against invented keys — `theme` on an insight card,
`state` on a cell-evidence item — and those warnings are about keys no
contract names, which have no column precisely because nothing declared
them. Those stay true by construction and this gate does not touch them.

So the rule is narrow and it is exactly the falsifiable half: if a
prompt names a contract field beside a phrase meaning "this does not
survive promotion", and the writer registry binds a column for it, the
prompt is wrong and the gate says so.

Exit 0 clean, 1 on a stale claim.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins" / "dma-insights" / "skills" / "dma-surface-production"
SPEC = ROOT / "apps" / "mcp" / "dma_mcp" / "writer_spec.json"

#: The ways this corpus says "it will not survive promotion". Each is a
#: claim a producer acts on, which is why each is worth checking.
CLAIMS = (
    re.compile(r"\bno column\b", re.I),
    re.compile(r"\bdropped at promot", re.I),
    re.compile(r"\bdiscarded at promot", re.I),
    re.compile(r"\bdoes not persist\b", re.I),
    re.compile(r"\bis not persisted\b", re.I),
    re.compile(r"\bdoes not survive promot", re.I),
)
_BACKTICKED = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")


def bound_by_table() -> dict:
    """table -> the field names that table's writer binds a column for.

    Scoped BY TABLE, and that is the whole precision of this gate. The
    prompts are full of true claims that a field exists on one table and
    not another — `theme` is bound on `overview_findings` and genuinely
    absent from `insight_cards`; `sources_searched` is bound on
    `heatmap_alerts` and genuinely absent from `heatmap_cell_evidence`.
    A name-only check calls all four of those stale and is worse than no
    check, because a gate that cries wolf gets switched off.
    """
    spec = json.loads(SPEC.read_text())
    out = {}
    for page in spec["specs"]:
        for w in page["writers"]:
            table = w.get("table") or w["section"]
            for col in w["columns"]:
                kind, _, name = (col.get("source") or "").partition(":")
                if kind in ("item", "section") and name:
                    out.setdefault(table, set()).add(name)
    return out


def claim_lines(text: str):
    """(line number, line, the two lines around it) for every claim.

    The window is three lines because these documents wrap prose, and the
    field name lands on the line before the phrase about as often as on it.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if any(rx.search(line) for rx in CLAIMS):
            window = " ".join(lines[max(0, i - 1):i + 2])
            yield i + 1, line.strip(), window


def main() -> int:
    bound = bound_by_table()
    if not bound:
        print("gate H: the writer spec bound no columns — refusing to pass "
              "vacuously, since an empty registry would clear every claim")
        return 1
    bad, checked = [], 0
    files = sorted(SKILL.rglob("*.md"))
    for path in files:
        text = path.read_text(encoding="utf-8")
        for lineno, line, window in claim_lines(text):
            names = set(_BACKTICKED.findall(window))
            # An unscoped claim is not checkable: "this field is dropped at
            # promotion" without naming a table could be about any of 34.
            # Skipping it is honest; guessing the table is how a gate starts
            # reporting things that are not true.
            tables = names & set(bound)
            if not tables:
                continue
            checked += 1
            for table in sorted(tables):
                for name in sorted(names - tables):
                    if name in bound[table]:
                        bad.append((path.relative_to(ROOT), lineno,
                                    name, table, line))
    if bad:
        print(f"gate H FAILED: {len(bad)} stale persistence claim(s).\n")
        for path, lineno, name, table, line in bad:
            print(f"  {path}:{lineno}")
            print(f"    claims `{name}` does not survive promotion on `{table}`")
            print(f"    the writer registry binds that column on that table")
            print(f"    > {line[:150]}\n")
        print("A producer reading this stops sending the field, or duplicates "
              "its substance into prose, and the surface goes empty for a "
              "reason nothing downstream can see. Correct the prompt.")
        return 1
    print(f"gate H passed: {len(files)} prompt files, {checked} table-scoped "
          f"persistence claim(s) checked against {len(bound)} writer tables, "
          "none stale.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
