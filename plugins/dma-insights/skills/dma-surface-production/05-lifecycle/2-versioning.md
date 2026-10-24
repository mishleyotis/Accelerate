# Versioning, reruns and fixing one page

Four independent version axes. Conflating any two produces a comparison that looks valid
and is not.

| Axis | Key | Set by | Means |
|---|---|---|---|
| **Run** | `run_id · run_seq` | The app, at ingest | One complete assessment of one entity at one point in time. |
| **Catalogue** | `ccg_catalog_version` | The catalogue loader | Which capability catalogue the run was scored against. |
| **Producer** | `producer_version` | The synthesis agent, per submission | Which synthesis produced each section. |
| **Contract** | `contract_version` | The connector, per section | The payload shape the submission validated against. |

## Before producing a rerun

Call `get_client_state(display_id)`. It returns what is currently served **and** the prior
runs. A rerun produced as though it were a first run silently empties every longitudinal
surface — velocity, recurring themes, the seen-in-N-runs chip and version diff all read
across runs.

Specifically, check:

- **Which cells were thin last time.** The thin-evidence register from the prior run is
  next run's research backlog. Closing one is the highest-value work available to you.
- **Which limiting absences were named.** "No dedicated transformation office is evidenced"
  is searchable. Go and search it.
- **Which recommendations landed.** A recommendation carried forward unchanged for three
  runs is either wrong or unactionable, and saying so is a finding.
- **Whether the catalogue version changed.** If it did, read the next section before
  comparing anything.

## Catalogue bumps

Every id resolution is pinned to the run's catalogue version. When the version changes
between runs, comparison is not automatic.

| Comparison | Permitted |
|---|---|
| Same catalogue version | Cell by cell. Scores, coverage, evidence counts, recommendation carry-over |
| Bump, cell bridged by an alias | Cell by cell, with the rename disclosed |
| Bump, cell split or merged | Category grain only. Mark the row `NOT_COMPARABLE` with the reason |
| Bump, cell retired | `NOT_COMPARABLE`. Rendered as retired, never as a drop to zero |
| Composite across a bump | Disclosed as approximate — the denominator changed |

**Refuse rather than annotate.** A renamed cell compared naively reads as a capability that
vanished, gets investigated as a regression, and is a rename. A split cell reads as a score
that halved. Both are the diff asserting more than the data supports.

Resolve renamed cells through the alias bridge in `get_capability_catalogue`.

## Two cell counts that are not the same

- `catalogue_cells` — 851 in the current version, fixed.
- `scored_cells` — this run's own count, smaller and varying, because sub-vertical toggles
  exclude cells an institution cannot legally operate.

Any coverage percentage renders its denominator. Use `scored_cells` unless the surface
explicitly says otherwise, and say which one you used.

## Fixing one page without a rerun

A section can be wrong without the assessment being wrong. Promoted staging rows are
retained, so:

```
1  re-claim the run                    (it is already PROMOTED — that is fine)
2  resubmit ONE page                   supersedes that page's staged row,
                                       carrying a new producer_version
3  promote_run                         asserts a PASS on every page — five come from
                                       the retained rows, one from your submission —
                                       and rewrites every section in one transaction
```

The atomic guarantee is unaffected: promotion is still all-or-nothing across all six pages.
What changes is that five of them needed no re-synthesis.

### A page promoted under an older gate set

`promote_run` re-gates every RETAINED page against today's gates, so fixing one page can be
refused on a page you did not touch (`retained_pages_fail_current_gates`). When the reason
is a key the contract added after that client was promoted, the contract carries the
migration beside the key and the refusal quotes it — do what it says to that one page,
resubmit it, promote. Change nothing else on the page. Two such keys exist today
(2026-10-04):

| Key | Refused by | Migration |
|---|---|---|
| `context.context_sentiment.context_tiles[].state` (RC-09) | CG-03b | on each tile with no rated row: `WORKED_ABSENT` when its `sources_searched` ladder ran and every rung names an outcome, else `UNWORKED`. The refusal proposes the value from the tile's own ladder. Golden 1's promoted context page needs this on two tiles. |
| `overview.firmographics.sub_vertical_undefined` (RC-06) | CG-02 | `false` when the primary sub-vertical has a set in `must_present_by_subvertical`; `true` only where research leaves it undefined (Farm Credit), and say so on the surface. Baxter's promoted overview needs this. |

**Do not re-synthesise a passing page to make the run feel fresh.** It costs a full
production cycle and changes `promoted_at` on rows whose content did not move, which makes
a later regression harder to bisect.
