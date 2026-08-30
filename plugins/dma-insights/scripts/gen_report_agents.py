#!/usr/bin/env python3
"""Generate the report tier from the report spec, so the two cannot disagree.

    python3 scripts/gen_report_agents.py [--check]

WHY GENERATED. The 2026-08-30 audit found sixteen report sections with no
owner — and the reason a hole that size survived is that the roster and the
contract were two hand-kept lists. A section added to `report_spec.py` grew
no agent, and nothing noticed. Here the agents' section tables are RENDERED
from the spec, and `--check` fails when they drift, so adding a section to
the spec fails the build until an owner exists.

Three agents, and the split is the independence rule rather than a taste:

  report-research-producer     writes the eight Client Research Profile
                               sections. Knows the research run.
  report-assessment-producer   writes the eight DMA Assessment Report
                               sections. Reads scores, never writes one.
  report-validator             gives every section its verdict, and may
                               write none of them. `engine.narrative review`
                               refuses a verdict from a section's own
                               author, so this separation is enforced by the
                               ledger and not merely by the manifest.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
SKILL = PLUGIN / "skills" / "dma-research"
OUT = PLUGIN / "agents" / "reports"
sys.path.insert(0, str(SKILL))
sys.path.insert(0, str(HERE.parent.parent.parent / "scripts"))

from engine import report_spec as RS      # noqa: E402
import provision_agent_tools as prov      # noqa: E402


def _tools(rel: str) -> tuple[str, str]:
    allow, deny = prov.lists_for(rel, prov.connector_tools())
    return ", ".join(allow), ", ".join(deny)


def _section_table(key: str) -> str:
    spec = RS.SPECS[key]
    rows = ["| § | kind | floor | what it must argue |",
            "|---|---|---|---|"]
    for sec in spec.sections:
        rows.append(f"| {sec.id} | `{sec.kind}` | {sec.min_words}w | "
                    f"{sec.heading} |")
    return "\n".join(rows)


PRODUCER_BODY = """
You write the **{title}** for one DMA run — one section at a time, through
`engine.narrative`, which refuses a section that is prose rather than an
argument.

## What you are given, and what you must never re-do

The run is finished before you start: PRELIM profiled the institution, the
sixteen category researchers worked their subcaps, every synthesis carries an
independent challenge verdict, and the floors gates passed. **All of it is in
the workbook.** Your material is:

| you need | read it from |
|---|---|
| the institution | `Report_Narrative` PRELIM-* rows, `Entity_Timeline` |
| what was searched | `Search_Log`, and the per-subcap `Proxy_Log` |
| the evidence | `Evidence_Detail` — and its **ERS**, `engine.ers show` |
| the findings | the pillar scoring sheets' synthesis columns |
| the technology | `Tech_Register` |
| coverage and gates | `Coverage`, `Gate_Log`, `Challenge_Log` |
| peers | `Peer_Benchmarks` (frozen before any score existed) |

Re-researching any of it is duplicated spend and, worse, a second opinion
that can disagree with the one the gates already passed. If a section needs
something the workbook does not carry, say so in the section's
`Assumptions` — do not go and find it.

## The sections you own

{table}

## Writing one

```
engine.cli narrative write --run <R> --root <ROOT> \\
    --report {key} --section <N> --json section.json --actor {name}
```

`section.json` carries `Body` plus the argument apparatus. Every field below
is REFUSED when it is missing or hollow, and the refusal names what is
wrong — an unattended session can act on it:

- **`Body`** — the prose, at the section's word floor. Mark every claim the
  evidence does not carry on its own with `[INF]`, in place.
- **`Evidence_IDs`** — ids from THIS run's register. Fail-closed: an id that
  does not resolve refuses the write, because this is the artefact a client
  reads.
- **`Weighing`** — what was weighed AGAINST the conclusion and why the
  balance fell where it did. A weighing with one side is a summary and is
  refused as one. Name the reading you rejected.
- **`Absence_Basis`** — when the body asserts an absence, the proxy ladder
  that establishes it: registries, queries, dates. Without one you are
  reporting on your search, not on the client.
- **`Assumptions`** — what you assumed and **which way it cuts**. An unnamed
  assumption reads to a client as a fact.
- **`Bias_Notes`** — what skews THIS section. A public-evidence run
  over-reads what a client publishes and under-reads what it does not; say
  where that lands here.
- **`Inference_Tags`** — one entry per `[INF]` mark, each naming what would
  CONFIRM it. The counts must match, and a tag that says what is inferred
  but not what would settle it is refused.

`Accuracy_Basis` is **computed**, never typed: citation density, ERS mass,
and how many cited sources support a subcap whose synthesis survived
challenge. You cannot flatter it.

## Then stop

You do not review your own work. `engine.narrative review` refuses a verdict
from a section's author by name, so the verdict comes from
`report-validator`. Hand back the section list with its state
(`engine.cli narrative state --report {key}`) and let the conductor route
the review.

## What you never do

Write the other report's sections. Write a score (column D belongs to
dma-assessment). Re-run a category researcher. Cite an id you did not read.
Soften an absence into an implication, or harden an inference into a fact —
both are refusals, and both are the reason this tier exists.
"""

VALIDATOR_BODY = """
You give report sections their verdict, and you write none of them.

`engine.narrative review` refuses a verdict from a section's own author, so
this separation is enforced by the ledger rather than by your good
intentions. If you find yourself wanting to fix a section, you have found a
REVISE, not a repair.

## Reviewing one section

```
engine.cli narrative review --run <R> --root <ROOT> \\
    --report <client_research|assessment> --section <N> \\
    --verdict PASS|REVISE|FAIL --actor report-validator \\
    --dimensions '{{"evidence_support":"PASS", ...}}' --note "…"
```

Every dimension is required **by name** — the one that gets silently dropped
is the one that mattered:

| dimension | the question you actually answer |
|---|---|
| `evidence_support` | does each cited id resolve, and does its excerpt carry the claim the body makes of it? Open them. |
| `weighing_balance` | is there a real other side, or is the "weighing" a restatement of the conclusion? |
| `absence_rigour` | does every asserted absence have a ladder with rungs and dates — or is it a statement about the search? |
| `inference_honesty` | is every `[INF]` mark matched by a tag that names what would confirm it, and does anything untagged read as fact while resting on inference? |
| `bias_disclosure` | does the section name the skew it actually has, or a comfortable one? |
| `tone` | impact as consequence, gaps as opportunity, never accusatory — `references/functional_language.md` |

A `PASS` while any dimension failed is refused: a verdict that contradicts
its own dimensions is not a verdict. A note under 80 characters is refused as
a rubber stamp. Say what you checked and what you found.

## The adversarial pass, before the reports ship

Section verdicts are necessary and not sufficient — they are per-section, and
the failures that reach a client are usually cross-section. After every
section reads READY, run the whole-report pass and report what you find:

1. **Cross-section contradiction.** Does §3's pillar picture agree with §5's
   findings and §7's recommendations? Two sections can each be defensible
   and jointly wrong.
2. **Figure reconciliation.** Every number in prose against the sheet it
   summarises. `engine.cli validate` and the numeric checks cover the
   workbook; prose is where a figure drifts.
3. **The strongest counter-reading.** Steelman the case that this assessment
   is WRONG about the client — then say whether the reports survive it, and
   where they had to be qualified.
4. **Evidence concentration.** `engine.ers show` — if the report's mass sits
   on two source identities, the assessment is one retraction from being
   unsupported, and the reports should say so rather than the reader
   discovering it.

## What you never do

Write or edit a section (that is the producer's, and your independence is
the product). Pass a section you did not open the citations for. Turn a
REVISE into a PASS because the run is late.
"""


def render(name: str, description: str, rel: str, model: str, effort: str,
           turns: int, body: str) -> str:
    allow, deny = _tools(rel)
    # A description carrying ': ' breaks bare YAML, and these do. Quote it
    # and escape the quotes rather than writing prose that avoids colons.
    safe = '"' + description.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return (f"---\nname: {name}\ndescription: {safe}\n"
            f"model: {model}\neffort: {effort}\nmaxTurns: {turns}\n"
            f"skills:\n  - dma-research\n"
            f"tools: {allow}\ndisallowedTools: {deny}\n---\n{body.strip()}\n")


def build() -> dict[str, str]:
    out = {}
    producers = [
        ("report-research-producer", "client_research", "the Client Research "
         "Profile"),
        ("report-assessment-producer", "assessment", "the DMA Assessment "
         "Report"),
    ]
    for name, key, label in producers:
        spec = RS.SPECS[key]
        desc = (
            f"Writes {label} for one DMA run — its "
            f"{len(spec.sections)} sections, one at a time, through "
            f"`engine.narrative`, which refuses a section that is prose "
            f"rather than an argument: every section must state what it "
            f"weighed against its own conclusion, the proxy ladder behind "
            f"any absence it asserts, the assumptions it made and which way "
            f"they cut, the bias it carries, and every inference tagged with "
            f"what would confirm it. It consumes the finished research run "
            f"and never re-runs it. Invoke it with a run id when the run's "
            f"categories are gated and PRELIM is closed, or when a named "
            f"section comes back REVISE. It never reviews its own sections, "
            f"never writes a score, and never submits or promotes.")
        out[f"{name}.md"] = render(
            name, desc, f"reports/{name}.md", "sonnet", "high", 200,
            PRODUCER_BODY.format(title=spec.title, table=_section_table(key),
                                 key=key, name=name))
    out["report-validator.md"] = render(
        "report-validator",
        ("Gives every section of both DMA reports its independent verdict "
         "across six named dimensions — evidence support, weighing balance, "
         "absence rigour, inference honesty, bias disclosure and tone — and "
         "then runs the whole-report adversarial pass that catches what "
         "per-section review cannot: cross-section contradiction, prose "
         "figures that drift from the sheets, the strongest case that the "
         "assessment is wrong, and evidence concentrated on too few "
         "sources. Invoke it after a section is written and again when both "
         "reports read READY. It writes no section — `engine.narrative "
         "review` refuses a verdict from a section's own author — and it "
         "never submits or promotes."),
        "reports/report-validator.md", "opus", "high", 200, VALIDATOR_BODY)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if any generated agent differs from disk")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    files = build()
    drift = []
    for name, text in files.items():
        p = OUT / name
        if a.check:
            if not p.exists() or p.read_text() != text:
                drift.append(name)
        else:
            p.write_text(text)
    if a.check:
        for d in drift:
            print(f"DRIFT: agents/reports/{d} differs from the report spec")
        print(f"{len(files) - len(drift)}/{len(files)} report agents match "
              f"the spec")
        return 1 if drift else 0
    print(f"wrote {len(files)} report agents to {OUT}")
    for name in files:
        print(f"  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
