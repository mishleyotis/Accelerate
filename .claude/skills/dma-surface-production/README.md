# dma-surface-production

Turns one completed Digital Maturity Assessment into the payload the DMA Insights web
application serves, and promotes it. Runs in Claude Cowork against the DMA Insights MCP
connector.

**Start with `SKILL.md`.** It is the router: what gets produced, the workflow, fifteen
non-negotiable rules, and pointers into everything below. Roughly a ten-minute read.

## Layout

```
SKILL.md          the router — read this first

01-start-here/    read before writing a single field
  1-standing-clauses    identity · grain · register · audience
  2-evidence            tiers · recency · rank score · the peer ladder
  3-language            every gap stated as available value
  4-absence-protocol    never say no until a documented ladder has failed
  5-colour-and-bands    what the payload may and may not carry about colour
  6-entity-shape        sub-vertical · size tier · ownership · brands

02-inputs/        where the material comes from
  1-package             the 15-folder assessment tree, and which artefact wins
  2-clay-enrichment     the enrichment playbook, the budget, the tier map
  3-mcp-tools           the 12 tools and the exchanges worth not guessing

03-pages/         the surface contracts, in production order
  1-heatmap             9 sections — produce first, everything else cites its linkage
  2-overview            12 sections — needs the coverage figures from the heatmap work
  3-insights            2 sections
  4-platform            5 sections sharing one recommendation id space
  5-context             5 sections — internal-only dashboard
  6-techstack           1 section, two surfaces, plus a detail sub-page

04-craft/         how to make it good rather than merely valid
  1-reasoning           the R-Layer, probe sets, nine contradiction classes
  2-platform-story      the highest-defect surface in the corpus
  3-page-narrative      a page tells one story
  4-card-anatomy        the header, sub-header and budget each surface renders into
  5-prompt-standard     for writing a prompt where none exists

05-lifecycle/     gates and continuity
  1-gates               four families, reading a verdict, the reconciliation pairs
  2-versioning          reruns, catalogue bumps, fixing one page

scripts/          run these rather than eyeballing
assets/           payload skeletons, one per section
```

## Reviewing this skill

Read in folder order — `01` through `05` is roughly the order a synthesis session needs them,
and each folder's files are numbered in the order they matter.

If you only have twenty minutes, read `SKILL.md`, then
`01-start-here/1-standing-clauses.md` and `04-craft/1-reasoning.md`. Those three carry the
disciplines that prevent most of the defect classes this product was rebuilt to eliminate.

The page packs in `03-pages/` are long — 56KB for the Overview — because they carry every
surface's contract, information-sources table and synthesis prompt verbatim. They are
reference material, not a read-through.

## Scripts

| Script | When |
|---|---|
| `preflight.py` | Starting or resuming a run. Turns run progress into an ordered plan |
| `clay_plan.py` | Before enrichment. Prints the call sequence and the tier map |
| `check_payload.py` | Before every submit. Structure, budgets, vocabularies, marking |
| `check_language.py` | Before every submit. Accusatory framing and unpaired gaps |
| `check_consistency.py` | Before promotion. The cross-page check no per-page gate can make |
| `score_prompt.py` | After writing a prompt. Scores it against the 14-attribute standard |

All six run standalone with no dependencies beyond the standard library.

## Related documents

This skill is the production half of a six-document set. The others describe what is being
built rather than how to produce content for it: the PRD, the TRD, the Backend Schema, the
Implementation Plan, the Surface Specification and the QA Report.
