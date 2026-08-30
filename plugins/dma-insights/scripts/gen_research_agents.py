#!/usr/bin/env python3
"""Generate the sixteen per-category research agents from the catalogue.

    python3 plugins/dma-insights/scripts/gen_research_agents.py [--check]

WHY GENERATED. The research tier is clustered by CATEGORY — one agent per
catalogue category, sixteen in all — because a category is the grain the
floors gate closes, the grain the knowledge graph routes, and the grain a
worklist hands out. Sixteen hand-kept manifests would drift sixteen ways;
these are emitted from one template plus the catalogue, the shared protocol
lives ONCE in skills/dma-research/references/RESEARCH-PROTOCOL.md (inside
the skill the researchers load, and outside agents/ so no packaging path
mistakes it for a manifest), and `--check` fails CI
when the files on disk are not what the template produces (the same
freshness discipline as gen_gates_md.py and gen_proto_bands.py).

The category NAMES are declared here rather than scraped from a reference
document: dma-assessment/references/capability_criteria.md carries the same
sixteen, and test_research_agents.py asserts the two agree — a disagreement
is a taxonomy drift finding, not something this generator papers over.

BUDGET, calibrated 2026-08-29 on a live 6-subcap P1C1 slice (real web
research, sonnet): effort stays MEDIUM — the run's quality gates all held
(0 ungrounded figures, 0 accusatory phrasings, honest laddered absences,
everything consolidated), so thoroughness is enforced structurally by the
refusals and the floors gate, not bought with thinking tokens; the depth
work (challenge, consolidation, verification) belongs to the opus tier by
design. maxTurns is 200 because one dispatch covers one search-op-ceiling
window (~7 subcaps at ~31 measured turns/subcap ≈ 217 before the batching
guidance in RESEARCH-PROTOCOL.md § Budget, which exists because turn count
— not search count — was the measured cost driver: 24.5M cached-input
tokens over 188 turns for six subcaps).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
OUT_DIR = PLUGIN / "agents" / "research" / "categories"
PLUGIN_JSON = PLUGIN / ".claude-plugin" / "plugin.json"

sys.path.insert(0, str(PLUGIN / "skills" / "dma-research"))

#: The sixteen category display names (v7.0 — P1C5 is retired and absent).
CATEGORY_NAMES = {
    "P1C1": "Digital Strategy & Vision",
    "P1C2": "Governance & Risk Appetite",
    "P1C3": "Innovation Management & Funding",
    "P1C4": "Culture & Change Enablement",
    "P2C1": "Digital Marketing & Acquisition",
    "P2C2": "Onboarding & Fulfillment",
    "P2C3": "Omnichannel Servicing & Support",
    "P2C4": "Personalization & Proactive Engagement",
    "P3C1": "Core Process Automation",
    "P3C2": "Operational Risk & Fraud Management",
    "P3C3": "Compliance, Supervision & Surveillance",
    "P3C4": "Business Resilience & Third-Party Management",
    "P4C1": "Data Management & Governance",
    "P4C2": "Analytics & AI Enablement",
    "P4C3": "Technology Architecture & Integration",
    "P4C4": "Information Security & Cybersecurity",
}

def _tool_lines() -> tuple[str, str]:
    """The allow/deny pair, derived from the ONE role table
    (scripts/provision_agent_tools.py, DEFAULTS["research"]) so this
    generator can never disagree with the provisioning authority — two
    generators owning one frontmatter line is how the line drifts."""
    sys.path.insert(0, str(PLUGIN.parents[1] / "scripts"))
    import provision_agent_tools as prov  # noqa: PLC0415
    allowed, denied = prov.lists_for(
        "research/categories/research-p1c1-producer.md",
        prov.connector_tools())
    return ", ".join(allowed), ", ".join(denied)

TEMPLATE = """---
name: research-{lower}-producer
description: Researches the {cat} category — {name} — for one DMA run. It \
works the worklist the knowledge graph routes to {cat}, answers each \
subcap's diagnostic questions in the run's declared evidence mode (deferred \
questions ride as discovery, never as silent gaps), notes findings to its \
category memory file as it goes, consolidates them into the scoring \
workbook through the ledger's own refusals, records technographic \
detections, and closes the category against the floors gate. Invoke it \
with a run id and root when {cat}'s worklist is open, when its floors gate \
FAILED, or when a repair names one of its subcaps. It writes only its own \
category; it never scores, never challenges its own synthesis, never \
submits and never promotes.
model: sonnet
effort: medium
maxTurns: 200
skills:
  - dma-research
tools: {tools}
disallowedTools: {denied}
---

You research ONE category of one Digital Maturity Assessment run:
**{cat} — {name}**.

The protocol you work under — the loop, the fusion discipline, the memory
notebook, the budget, every refusal — is
`${{CLAUDE_PLUGIN_ROOT}}/skills/dma-research/references/RESEARCH-PROTOCOL.md`.
Read it before your first tool call. This manifest only binds you to your
category.

## Your category

- Your grain is `{cat}` and nothing else. `engine.cli orient --run <R>
  --root <ROOT> --category {cat}` is your first command; its `do_first`
  list is your instruction, and its work card is your unit of work.
- Your worklist, question counts and deferred questions come from
  `engine.kg route --run <R> --root <ROOT> --category {cat}` — computed
  from the workbook's DQ bank at call time, never assumed.
- Your notebook is `03_memory/{cat}.md` under the run root, written only
  through `engine.memory note --category {cat}`.
- Your synthesis actor name is `research-{lower}-producer` — pass it to
  `--actor` so the challenge's independence is checkable.
- {name} spans this category's capabilities as the catalogue defines them;
  the toolkit's per-subcap source lists on your work cards say where each
  answer lives. Hunt the named artefacts before you fish.

## You are done when

`engine.cli gate --run <R> --root <ROOT> --category {cat}
--require-synthesis` returns PASS, your notebook shows nothing NOTED or
BLOCKED, and your report to the conductor carries the gate verdict, the
deferred-question count, your techscan rows and anything UNTESTED.
"""


def render(cat: str) -> str:
    tools, denied = _tool_lines()
    return TEMPLATE.format(cat=cat, lower=cat.lower(),
                           name=CATEGORY_NAMES[cat], tools=tools,
                           denied=denied)


def agent_paths() -> list[str]:
    return [f"./agents/research/categories/research-{c.lower()}-producer.md"
            for c in sorted(CATEGORY_NAMES)]


def _catalogue_categories() -> list[str]:
    from engine import contract  # noqa: PLC0415
    return list(contract.taxonomy().categories)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if any manifest on disk differs from the "
                         "template, or plugin.json is missing one")
    a = ap.parse_args(argv)

    cats = _catalogue_categories()
    declared = sorted(CATEGORY_NAMES)
    if cats != declared:
        print(f"gen_research_agents: the catalogue holds {cats} and the name "
              f"table holds {declared} — reconcile before generating; a "
              f"category without a researcher is an unworked sixteenth of "
              f"every run")
        return 1

    stale, missing_in_manifest = [], []
    manifest = json.loads(PLUGIN_JSON.read_text())
    listed = set(manifest.get("agents") or [])
    for cat in declared:
        path = OUT_DIR / f"research-{cat.lower()}-producer.md"
        body = render(cat)
        rel = f"./agents/research/categories/{path.name}"
        if rel not in listed:
            missing_in_manifest.append(rel)
        if a.check:
            if not path.is_file() or path.read_text() != body:
                stale.append(path.name)
        else:
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
    conductor = "./agents/research/research-conductor.md"
    if conductor not in listed:
        missing_in_manifest.append(conductor)

    if a.check:
        problems = []
        if stale:
            problems.append(f"{len(stale)} stale manifest(s): {stale[:4]} — "
                            f"run gen_research_agents.py")
        if missing_in_manifest:
            problems.append(f"plugin.json does not list: "
                            f"{missing_in_manifest[:4]}")
        if problems:
            print("gen_research_agents: " + "; ".join(problems))
            return 1
        print(f"gen_research_agents: {len(declared)} category manifests "
              f"current and listed")
        return 0

    if missing_in_manifest:
        manifest["agents"] = sorted(set(manifest.get("agents") or [])
                                    | set(missing_in_manifest)
                                    | set(agent_paths()))
        PLUGIN_JSON.write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"gen_research_agents: plugin.json gained "
              f"{len(missing_in_manifest)} agent path(s)")
    print(f"gen_research_agents: wrote {len(declared)} category manifests "
          f"under {OUT_DIR.relative_to(PLUGIN)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
