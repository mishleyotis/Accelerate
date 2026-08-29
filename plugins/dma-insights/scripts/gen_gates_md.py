#!/usr/bin/env python3
"""Regenerate the complete gate census inside 1-gates.md, from the registry.

    gen_gates_md.py [--check]

WHY THIS EXISTS. AUD-0053: `05-lifecycle/1-gates.md` is the file SKILL.md maps
as "Reading a verdict" and that eight checker and producer manifests list as a
required read. It documented 32 of the 69 (CG|AG|SG|ET)-NN ids the deployed
connector emits. The audit's own worked example, CG-30, had zero occurrences
in it while `gates.py` defines it and `validation2.py` emits it. An unattended
repairer sent there for 37 of 69 gates learns nothing about what it violated
and repairs by guessing at the rule.

The hand-written sections above the generated block are the valuable part and
are left alone: they explain the gates that block most often, at length. What
this adds is the CENSUS — every gate id, with the sentence the registry itself
carries — so no id is undocumented, and a gate added to the registry without a
line here fails CI (AUD-0131: one generated-artefact freshness check across
thirty CI steps; this is the second).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TARGET = (ROOT / "plugins/dma-insights/skills/dma-surface-production"
          / "05-lifecycle/1-gates.md")
BEGIN = "<!-- generated:gate-census BEGIN — edit gen_gates_md.py, not this -->"
END = "<!-- generated:gate-census END -->"

FAMILY = {"AG": "Analytical", "SG": "Safeguard", "ET": "Enrichment trigger",
          "CG": "Corpus / contract"}


def _load_gates() -> dict:
    sys.path.insert(0, str(ROOT / "apps" / "mcp"))
    from dma_mcp.gates import GATES        # noqa: PLC0415
    return GATES


def _emitted_ids() -> set:
    """Every gate id the connector's modules actually name."""
    out = set()
    base = ROOT / "apps" / "mcp" / "dma_mcp"
    for p in list(base.glob("*.py")) + list(base.glob("*.json")):
        out |= set(re.findall(r"\b(?:CG|AG|SG|ET)-[0-9]+\b", p.read_text(
            errors="ignore")))
    return out


def render() -> str:
    gates = _load_gates()
    emitted = _emitted_ids()
    lines = [BEGIN, "",
             "## Every gate, by id",
             "",
             f"The registry holds **{len(gates)}** gates. This census is "
             f"generated from `apps/mcp/dma_mcp/gates.py` by "
             f"`plugins/dma-insights/scripts/gen_gates_md.py`, so a gate "
             f"cannot exist in the connector and be absent here. The sections "
             f"above go deeper on the ones that block most often; this table "
             f"is what you read when a verdict names an id you have not seen.",
             "",
             "When the row below is not enough, the connector will explain "
             "itself: `explain_gate(gate_id)` returns the registry's own "
             "wording plus the threshold history. A verdict also carries the "
             "JSON path it fired on, so the repair routes from the path "
             "through `05-lifecycle/routing.md` to the owning per-surface "
             "producer without needing this file at all.",
             ""]
    for fam in ("CG", "AG", "SG", "ET"):
        ids = sorted((g for g in gates if g.split("-")[0] == fam),
                     key=lambda g: (len(g), g))
        if not ids:
            continue
        lines += [f"### {fam} · {FAMILY[fam]} ({len(ids)})", "",
                  "| Gate | What it asserts | On failure |", "|---|---|---|"]
        for gid in ids:
            name, plain, what, _why, on_fail = gates[gid]
            what = " ".join(str(what).split())
            if len(what) > 240:
                what = what[:237].rsplit(" ", 1)[0] + "…"
            note = "" if gid in emitted else " *(registry-only: no module "\
                                             "emits this id today)*"
            lines.append(f"| `{gid}` | **{name}.** {what}{note} | {on_fail} |")
        lines.append("")
    missing = sorted(emitted - set(gates))
    if missing:
        lines += ["> **Emitted but not in the registry:** "
                  + ", ".join(f"`{m}`" for m in missing)
                  + ". A verdict can name these and `explain_gate` cannot "
                    "answer for them.", ""]
    lines.append(END)
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the file is stale, and print the diff")
    a = ap.parse_args(argv)
    body = render()
    text = TARGET.read_text()
    if BEGIN in text and END in text:
        head, rest = text.split(BEGIN, 1)
        _, tail = rest.split(END, 1)
        new = head + body + tail
    else:
        new = text.rstrip("\n") + "\n\n---\n\n" + body + "\n"
    if a.check:
        if new != text:
            print("gen_gates_md: 1-gates.md is STALE — run "
                  "plugins/dma-insights/scripts/gen_gates_md.py")
            return 1
        print("gen_gates_md: 1-gates.md is current")
        return 0
    TARGET.write_text(new)
    n = len(_load_gates())
    print(f"gen_gates_md: wrote the census of {n} gates into "
          f"{TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
