# Routing — what goes to which agent, and why that is the speed

The pipeline exists so that the smallest true unit of work runs, not the
whole run. A one-card repair that re-produces six pages is the slow response
the hierarchy was built to remove.

## The pipeline, in order

```
route → produce → challenge → consolidate → submit → learn
```

| stage | agent | may submit? |
|---|---|---|
| produce | one of the four surface producers (below) | no |
| challenge | `finding-challenger` (dma-research discipline) | no |
| consolidate | `page-consolidator` (refuses unchallenged input) | no |
| submit + promote | `surface-producer` only | **yes** |
| learn | `qa-overseer` (writes the findings memory) | memory only |

The challenger runs BEFORE the consolidator, always: the consolidator's
method assumes per-claim verdicts exist, and it refuses input without them.
The qa-overseer runs at the END of every production or repair, green or not
— a green run with a buried defect still gets its finding recorded.

## The routing table

| you need | route to |
|---|---|
| any of: hero score card, firmographics, exec summary, why now, thought leadership, leadership panel, financial trajectory, sentiment, ceilings, findings, opportunity tiles, evidence coverage | `overview-surface-producer` |
| any of: workbook grid, focus areas, cell evidence drawers, evidence index, value chain, alerts, safeguard gates, evidence age, cohort patterns | `heatmap-surface-producer` |
| any of: platform cards, recommendations, starters, roadmap, stair-step | `platform-surface-producer` |
| any of: timeline, issue register, regulatory standing, context sentiment, acquisitions, techstack register, insight cards, landscape strip | `context-surface-producer` |
| a package to vet before anything is parsed | `package-vetter` |
| a passing run about to be believed | `adversarial-verifier` |
| what production actually serves | `deployed-app-auditor` |
| a defect class that keeps recurring | `rectifier` |

## Sizing the route

- **One surface flagged** (a reviewer note, a failed gate on one path):
  route exactly that surface to its producer, challenge it, consolidate
  the ONE page, resubmit the one page, promote. Nothing else runs.
- **One page wrong**: all that page's surfaces in parallel to its producer
  (they are independent), one challenge pass, one consolidation, one
  submit.
- **A fresh run**: pages fan out in parallel — each page's produce →
  challenge → consolidate chain is independent of the others until the
  cross-page reconciliation, which the surface-producer runs before
  submitting the set. Promotion stays atomic across all six.
- **Repair after a verdict**: the gate names the JSON path; the path names
  the surface; the surface names the producer. Do not re-produce a page to
  fix a field the verdict located for you.

## Memory duties per stage

Producers read the page rulebook at `03-pages/rulebooks/<page>.md` before
the memory digest — the rulebook is applied by default, not recalled.
Producers read (`get_memory_digest`, `search_findings`) before authoring.
The challenger reports recurrences against finding ids but records nothing.
The qa-overseer alone writes: `record_finding` for the new,
`report_recurrence` for the repeat, `resolve_finding` for the fix that
held, `record_refinement` for the method that worked. Twice-recurred goes
to the rectifier with the finding ids — and with the rulebook file that
should have prevented them, because a recurrence that got past a rulebook
is a defect in the rulebook too.

## Speed notes

The four surface producers run on the fast model tier; the challenger,
consolidator and overseer reason on the strong tier — checking is where
depth pays. Producers return JSON, not prose about JSON. The PreToolUse
hook refuses a doomed submit before the network sees it; treat a hook
refusal exactly like a gate refusal, because it is quoting one.
