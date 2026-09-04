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

  report-research-producer     writes the Client Research Profile's
                               sections. Knows the research run.
  report-assessment-producer   writes the DMA Assessment Report's
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
    """The full anatomy, not the heading.

    The 2026-08-30 audit found this table printing `sec.heading` under a
    column headed "what it must argue", with the seven apparatus bullets
    below it byte-identical for all sixteen sections — so nothing anywhere
    told a producer what a section CONTAINS, which sheets it reads, whether
    it may ship uncited, or which app surface it feeds. Every field of
    `Section` is rendered here now, and `--check` fails the build when the
    spec moves and the agents do not.
    """
    spec = RS.SPECS[key]
    rows = ["| § | heading | floor | reads | cites | feeds |",
            "|---|---|---|---|---|---|"]
    for sec in spec.sections:
        # The SECTION's own floors from the pinned Doc, not the module
        # defaults: this once printed "1+ × 60w" for the pillar deep dives
        # (pinned: 4 × 800w) and the recommendations (pinned: 5-8 × 350w),
        # so each manifest stated two different floors for the same section.
        if sec.kind in RS.CARD_KINDS:
            span = (f"{sec.card_floor}-{sec.cards_max}" if sec.cards_max
                    and int(sec.cards_max) != sec.card_floor else f"{sec.card_floor}")
            floor = (f"{sec.min_words}w · {span} cards `{sec.card_prefix or ''}…` × "
                     f"{sec.card_min_words}w")
        else:
            floor = f"{sec.min_words}w"
        rows.append(
            f"| {sec.id} | {sec.heading} | {floor} | "
            f"{', '.join(f'`{i}`' for i in sec.inputs)} | "
            f"{'required' if sec.requires_citation else 'not required'} | "
            f"{', '.join(f'`{x}`' for x in sec.surfaces) or '—'} |")
    rows.append("")
    rows.append("**The blocks each section is written in**, in order. A body "
                "missing one, or carrying them out of order, is refused: they "
                "become real Heading2s in the .docx, which is the grain the "
                "app parses and scopes its vectors at.")
    rows.append("")
    for sec in spec.sections:
        if sec.blocks:
            rows.append(f"- **§{sec.id}** — "
                        + "  ·  ".join(f"`## {b}`" for b in sec.blocks))
        elif sec.kind == "section":
            rows.append(f"- **§{sec.id}** — one passage; the Doc numbers no "
                        f"subsections here")
    rows.append("")
    rows.append("**The countable MINIMUM DATA and MUST NOT rules the write "
                "refuses on** (the rest of each control block is in the "
                "pinned Doc, and the validator reads it):")
    rows.append("")
    for sec in spec.sections:
        bits = []
        for chk in sec.checks:
            bits.append(f">= {chk.min}" + (f" (<= {chk.max})" if chk.max else "")
                        + f" {chk.label}" + (" per card" if chk.per_card else ""))
        for fb in sec.forbid:
            bits.append(f"never: {fb.label}")
        if sec.is_card:
            bits.insert(0, f"{sec.card_floor}"
                        + (f"-{sec.cards_max}" if sec.cards_max else "+")
                        + f" cards `{sec.card_prefix}…`, each {sec.card_min_words}+ words")
        if bits:
            rows.append(f"- **§{sec.id}** — " + "; ".join(bits))
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

## Before you write a word: the preconditions, then the template

```
engine.cli narrative preconditions --run <R> --root <ROOT> --report {key}
```

It refuses — and names every reason at once — while PRELIM is open, while
any category's floors gate is not a PASS recorded with `--require-synthesis`,
while the run's templates are unbound, and (for the assessment report) while
the workbook is still at the research stage, the SCORING gate has no recorded
PASS, or the completeness gate holds a tab empty with no reason. `engine.cli
narrative write` runs the same check and refuses the write; do not route
around it by writing rows with any other tool. Owner, 2026-09-03: "Report
writing starts without scoring happening" — this is the check that stops it.

Then read the Doc you are writing INTO, pinned in the repo:
`references/templates/{markdown}` — every section's control block (PURPOSE,
FEEDS, INPUTS, LENGTH, MINIMUM DATA, MUST INCLUDE, MUST NOT, FAIL IF) and its
tables — and `references/templates/gold_reference.json`, the Golden 1
measurements a finished report meets. `engine.cli narrative contract --report
{key}` prints the same contract as the engine enforces it, block by block,
with the countable MINIMUM DATA rules the write refuses on.

## The sections you own

{table}

## Writing one

```
engine.cli narrative write --run <R> --root <ROOT> \\
    --report {key} --section <N> --json section.json --actor {name}
```

A section whose kind is `pillar` or `recommendation` (the Doc's card
sections — one pillar deep dive per pillar in scope, five to eight `REC-NN`
recommendations) is a **list**, not a passage: each card is its own row and
needs its own `--card <id>`. Without one the write is refused — and before
that refusal existed, every write to such a section overwrote the last, so a
list section held one row against its blocking card floor and the floor was
arithmetically unreachable through the only sanctioned writer. The floors
column in the table above is the pinned Doc's, per section.

`engine.cli narrative contract --report {key}` prints each section's blocks,
inputs, citation rule and the surfaces it feeds. Read it before you write.

`section.json` carries `Body` plus the argument apparatus. Every field below
is REFUSED when it is missing or hollow, and the refusal names what is
wrong — an unattended session can act on it:

- **`Body`** — the prose, at the section's word floor, **written in that
  section's declared blocks**: a line `## <block>` for each, in the order the
  table above gives them. They are not decoration. The app parses a report at
  Heading2 grain and scopes its vectors from tokens inside those headings, so
  a section written as one undivided passage arrives as a single row
  belonging to no pillar. Mark every claim the evidence does not carry on its
  own with `[INF]`, in place.
- **`Evidence_IDs`** — ids from THIS run's register. Fail-closed: an id that
  does not resolve refuses the write, because this is the artefact a client
  reads. The five sections marked *not required* above describe the RUN
  rather than the client and may ship uncited; every other one may not.
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

## Before you review anything

You are the gate that admits a .docx: `engine.cli report` renders only when
every section carries your PASS. So you check the run before the prose —
a PASS on a section of a run that should not have been written is your
defect, not the producer's.

```
engine.cli narrative preconditions --run <R> --root <ROOT> --report <key>
engine.template binding --run <R> --root <ROOT>
```

The first must print `ready: true` — PRELIM closed, every category gated
with `--require-synthesis`, the templates bound, the SCORING gate PASS and
the workbook complete for the assessment report, the five-year financial
trajectory banked for both. The second names the pinned Doc the report is
written to; read that Doc's markdown export
(`references/templates/client_profile_template.md` or
`assessment_report_template.md`) and `references/templates/gold_reference.json`
before you open a section — you are reviewing against the Doc's control
blocks and the Golden 1 depth, not against your sense of a good report.
A section written before the run was ready gets FAIL, whatever its prose.

Your last act before handing back is the gold gate on the rendered file:

```
python3 -m engine.gold_standard report <report.docx> --kind <research|assessment>
```

A report you passed that the gate fails is a review that was not done.

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


GOLD_BLOCK = """

## Gold standard — the deliverable-first loop (mandatory)

Before you write a word, read `docs/GOLD-STANDARD.md` and open the reference package
(**Golden 1 Credit Union**) so you know the exact shape — the section list, the tables,
the coverage disclosure, the M-band labels, the AI-and-data overlay per pillar, the
rebuttal per recommendation. Authoring first and meeting the standard only in QA is the
failure this loop exists to prevent.

When the report is written, run the gate on your OWN output before you hand back:

```
python3 -m engine.gold_standard report <report.docx> --kind <research|assessment>
```

Do not return until it prints `PASS`, and re-run it after any change to a section, a
score reference, or a figure. Every finding maps to a goeasy-Ltd defect in
`docs/goeasy-findings-register.md`. Never ship a hedge — "Not established this run",
"surface-production stage", "no score yet", a bare "N/A" or "0" where a value belongs. A
genuine gap is a disclosed Coverage Unknown or an ABSENT firmographic with a route,
never a hedge. Reproduce every numbered template section and leave no `{{token}}`."""


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
                                 key=key, name=name, markdown=spec.markdown)
            + GOLD_BLOCK)
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
