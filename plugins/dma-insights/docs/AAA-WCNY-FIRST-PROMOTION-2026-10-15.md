# AAA Western and Central New York — why the first promotion read incomplete

Run `e7a59709-011f-444a-aa38-0d5b3bb4b715` (request `aaa-wcny-2026-10-14`,
sub-vertical IB, PUBLIC evidence) was promoted 2026-10-15 05:13 UTC with all
six pages PASS. The owner reported: "Peer data is unpromoted. Platform only
has 2 platforms … For 1st time promotions, I seem to have this recurring
problem." Every staged section was read (all six pages, including both
oversize sections), plus the cohort and the fit engine live.

## What the pages served

| Surface | Served | Why |
|---|---|---|
| Overview hero peers | `peer_median` null on 4/4 pillars, `cannot_estimate`, `peer_n` 2 | Cause 1 |
| Heatmap grid peers | 0 of 20 rows with a peer median | Cause 1 |
| Focus areas, findings, gap rows | `peer_score`/`peer` null everywhere (40/40 gap rows, 10/10 opportunity cells) | Cause 1 |
| Cohort patterns | empty, 16 `insufficient_cohorts` at size 2 | Cause 1 |
| Overview opportunity | **2 tiles** (CRM Analytics 66.7, MuleSoft 62.9); 7 discarded | Cause 2 |
| Platform page | 8 cards, 4 of them `INSUFFICIENT_EVIDENCE` at strength 0.0 (Service Cloud, Shield, Data Cloud, Experience Cloud) — 4 of the 6 recommended platforms unranked | Cause 2 |
| Opportunity card / landscape strip | "the technology register is not promoted", "techstack page not yet shipped" | Cause 3 |
| Heatmap evidence index | ends at E-228; other pages cite E-229 … E-253 (recommendations, techstack, firmographics) | Cause 3 |
| Evidence age | "24 later workbook rows are not yet registered" | Cause 3 |

## Cause 1 — the cohort could not see six scored brokerages — FIXED

`get_cohort_benchmarks("IB")` returned **2 entities** against a floor of 3,
so every peer figure on every page was null. The store holds at least six
more scored IB brokerages:

| Entity | Stored `sub_vertical` | Run status | Scored cells |
|---|---|---|---|
| OneDigital Partners | NULL | INGESTED | 701 |
| TowneBank Insurance | "Insurance Brokers" | INGESTED | 701 |
| Virtuity Financial Partners | "Insurance Brokers" | INGESTED | 701 |
| Alera Group | "Insurance Brokerages (IB)" | INGESTED | 597 |
| Alliant Insurance | NULL (PENDING_REVIEW) | INGESTED | 701 |
| IMA Financial | NULL (PENDING_REVIEW) | INGESTED | 702 |

Two filters in `apps/mcp/dma_mcp/cohort.py` hid every one of them:

1. `r.is_active AND r.promoted_at IS NOT NULL` — `is_active` is only ever set
   by promotion, so an assessed-but-unpromoted entity could never be a peer.
   Promotion writes no score: `subcap_scores` is the ingest tier for both.
2. `lower(e.sub_vertical) = lower('IB')` — a literal match against a column
   the corpus spells three ways.

It recurs on first promotions because a new client in a thin sub-vertical is
exactly the case where few peers have been *promoted*, however many have been
*assessed*.

**Fix:** `cohort.assessed_runs` chooses ONE run per entity — its active
promoted run, else its latest scored run — and resolves the sub-vertical
through `subverticals.resolve_subvertical` (the one alias table). A NULL
sub-vertical is inferred from the run's scored variant cells only when they
name one sub-vertical. Excluded: withdrawn runs and every run of a request a
withdrawal named, superseded runs, entities not `ACTIVE` (PENDING_REVIEW is
the corpus's "may be a duplicate" flag — Alliant and IMA stay out until
reviewed). The previous query also never checked `withdrawn_at`; it does now.
The result reports `assessed_unpromoted` as a count; no entity leaves the
module. For AAA this moves IB from 2 to at least 6 peers (OneDigital by
variant inference) — above the floor of 3 for every category the peers score.

**Owner decision to confirm:** this reads the owner's 2026-10-06 rule ("an
average of current entities in the same subvert already assessed") as
*assessed*, not *promoted*. If peers must be promoted first, revert the
`promoted` preference to a filter and promote the six brokerages instead.

## Cause 2 — the evidence floor was judged on arbitrary cells — FIXED

`platform_fit.mean_evidence_strength` averaged the evidence of
`core_of(cand)[:5]`, and `core_of` orders by *damped* opportunity, in which an
unevidenced cell takes the neutral prior (0.55 → 0.82) while a real T3
undated citation is 0.56 → 0.824 and T4 undated 0.385 → 0.754. On a run where
every gap ties — 521 of AAA's 694 cells are declared absences at 1.0 — the
five "driving" cells were simply the alphabetically-first unevidenced ones.
Live, `get_platform_fit` showed Service Cloud's five as P1C2.2.1 … P1C2.2.5,
all `evidence_strength: null`, mean 0.0, `INSUFFICIENT_EVIDENCE`. CRM
Analytics and MuleSoft survived at 0.112 because one T3 cell happened to sort
into their five.

**Fix:** `platform_fit.judged_cells` orders the driving core by the size of
the claim (gap × severity, before the damp), then by evidence. The fit score
does not move. A larger unevidenced gap still outranks better evidence, so a
card whose biggest claims are unevidenced stays honestly insufficient.
`top_contributors` prints the same cells the verdict was judged on.

## Cause 3 — pages staged before the pages they read — FIXED

Heatmap and insights were staged at 03:47, context 04:33, techstack 04:43,
overview and platform 05:00. Techstack had been deferred to version B, and
`_stage_pages_b` shipped a deferred page **last** — after insights, overview
and platform, which read its register. The heatmap was restaged from disk
with the evidence index it was built with, before E-229 … E-253 were
registered. On a rerun, the previous promotion's register and index hide all
of this; on a first run nothing does.

**Fixes:**
- `pipeline._stage_pages_b` ships a deferred page **first** (its refusal is
  still held until every other page has had its turn, R-INTERAC-20261010).
- `promote_checks` gains **CG-ORDER**, blocking at promote:
  - text in `empty_state`, `narrative_thread` or `r_layer` saying the run's
    own register / page / evidence / rows are "not (yet) promoted / shipped /
    registered" — the same class as CG-STALE: promotion makes it false;
  - a heatmap evidence index (H6, "the run's full evidence index") that omits
    an id another page cites, compared within one id form.
  The refusal names the page; resubmitting that page is the repair.

## Not changed here (recorded)

- `heatmap.safeguard_gates.gates[]` is empty in the payload by design — the
  API joins `gate_results` at serve time (`apps/api/dma_api/computed.py`).
- Thin content that is the evidence's, not the pipeline's: sentiment 1 bar,
  financial series empty, issue register empty, 9 INFERRED register rows with
  no CONFIRMED, 61.8 % undated evidence (`Evidence_Detail.recency` was
  `column_mapped_but_empty` at intake).
- CRM Analytics, ranked #1, has no recommendation; Service Cloud's top cells
  are P1C2 governance cells the v7.0 catalogue maps to it.

## To take effect for AAA

1. Deploy (`infra/deploy.sh`) — the cohort, the fit engine and CG-ORDER live
   in the `mcp` service.
2. Re-produce for run `e7a59709`: overview (hero, opportunity, findings),
   heatmap (workbook_scores, focus_areas, evidence, evidence_age), platform,
   insights.landscape — then re-promote. Promote will now refuse the stale
   sentences and the truncated index until they are repaired.

Tests: `apps/mcp/tests/test_cohort_benchmarks.py`,
`apps/mcp/tests/test_first_promotion_aaa_2026_10_15.py`,
`tests/skills/research_engine/test_widen_peers_2026_10_12.py`.
