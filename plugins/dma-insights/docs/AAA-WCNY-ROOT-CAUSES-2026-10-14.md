# AAA Western and Central New York — why categories failed, and what now refuses it

Run `aaa-wcny-2026-10-14` (sub-vertical IB, PUBLIC evidence), session
`session_01FwbNzArGpugwKaBcziks2C`, read end to end on 2026-10-14
(06:32 → 10:46 UTC: 260 transcript pages, every main-session message, every
in-session agent's hand-back, every ledger refusal and gate verdict). The
first research round ran as persisted workflows, whose agents' turns never
reach the session transcript; round 1 is read from its gate verdicts and the
repair round, which replayed every one of its failures in the open.

## The numbers

| | Round 1 (16 workflows) | Repair round (in-session agents) |
|---|---|---|
| Categories passing | 3 of 16 (P1C2, P1C3, P4C3) | 14 of 16 (P2C4, P4C4 deferred for budget) |
| Cells failing | 75 across 13 categories | 0 in the 11 funded categories |
| Research spend | $112.55 against a $95 envelope (est. $82.02, +37%) | $28.04 across 41 agents — **none of it booked** until measured by hand |
| Run ceiling | $110 → stopped `STOPPED_BUDGET` at $129.52 | raised to $180, then $205 |
| Extra challenge passes | — | P3C4 ×3, P2C3 ×2, every other repaired category ×1 |

Round 1's 75 cells by the gate term that failed them:

| Term | Cells | Categories |
|---|---|---|
| `challenge_failed` | 22 | P1C1 6, P2C1 4, P2C2 2, P3C4 2, P4C4 2, P1C4, P2C3, P2C4, P3C2, P3C3 |
| of which an owed facet never searched (`volleys_incomplete`) | 10 | P1C1 5, P3C4 2 (+3 in repair), P4C4 2, P3C3 1 |
| `boilerplate` | 13 | P2C3 4, P2C2 3, P3C1 3, P4C2 3 |
| empty cells left undeclared (`absence_undeclared_empty`) | 25 | P4C4 8, P1C1 5, P2C4 4, P3C3 4, P3C4 2, P2C1 1, P4C1 1 |

## The patterns, and the root cause behind each

### 1. The evidence engine searched for a domain that does not exist — FIXED

`apps/evidence-engine/evidence_engine/tools.py` normalised every entity
domain with `str(x).lower().lstrip("www.")`. `lstrip` strips **characters**,
not a prefix: `westerncentralnyaaa.com` became `esterncentralnyaaa.com`.
Every `site:` probe asked about a non-existent domain (the P1C1 collector
reported it verbatim), and `registry.is_own_host` stopped recognising the
club's own pages, so own-site cards lost their `confirmed` identity and the
engine's results skewed to national-AAA and sister-club pages — the
"all national AAA or other AAA clubs, refused" note that recurs through the
collectors' reports, and part of why 25 cells closed empty. Every client
whose domain starts with **w** (Webster, Wintrust, WSFS, Washington Trust …)
was exposed the same way.

**Prevention:** `_bare_domain` removes only a leading `www.` prefix (and a
scheme/path a caller pasted). `tests/test_entity_domains_2026_10_14.py`
fails 7/7 on the old line. **Takes effect for live runs only after the
evidence service is redeployed (`infra/deploy.sh`).**

### 2. The absence writer accepted what the gate then failed as boilerplate — FIXED

`ledger.declare_absence` composes `What_We_Found` as
`"Searched and not found: {--hunted}. Volleys fired: …"`. A declared absence
carries a `Dominant_Claim`, so `floors_gate` runs `is_fluent_but_empty` over
that field — which demands a figure, date, proper noun, domain or E-id. The
writer never ran the same check. All 13 `boilerplate` cells were declared
absences whose `--hunted` named nothing checkable ("names no figure, date,
proper noun or cited id"); each cost its category a repair collector, an
orchestrator pass and a re-challenge.

**Prevention:** `declare_absence` runs the gate's own predicates over the
composed fields and refuses, telling the writer to name the entity, the
domain searched, a date or an E-id.

### 3. The orchestrator's sheet contradicted the ledger it writes to — FIXED

`workflows/dma-pillar-research.js` (rendered for workflow, lean-tier and
in-session agents alike) stated the rule "`--inferable` and
`--validation-question` come together or not at all" and then printed "the
exact command (every flag below is required)" with `--validation-question`
and **no** `--inferable`. The ledger refused that line **11 times** in the
repair round alone (P4C1 ×3, P4C2 ×3, P2C2 ×3, P3C4, P2C1). The same sheet
said "a Dominant_Claim that asserts an absence is not a synthesis — close it
through 'absence'", while the challenger asks evidenced cells to bound their
claim with a negative ("…, but no source shows an online bind flow"): the
ledger refused that **22 times** for the missing `Absence_Claimed` /
`Proxy_Log` the sheet never mentioned.

**Prevention:** the template carries the pair (or `--not-determinable` in
its place) and says `--hunted` must name something checkable; the sheet
tells an evidenced cell how to bound its claim. A test scans every workflow,
agent manifest and reference for an absence command that spells one flag of
the pair without the other.

### 4. A synthesis was written over a search that was never run — FIXED

`floors_gate` blocks `volleys_incomplete` on every cell and the challenger
FAILs `facet_coverage` on an owed facet nobody searched, but
`append_synthesis` accepted the synthesis (the facet written `NOT_RUN`). The
outcome was certain and paid for twice: P1C1 (5 cells), P3C4 (2, then 3
again in repair) and P4C4 (2) went synthesis → challenge FAIL → repair
collector → second synthesis → second challenge.

**Prevention:** `append_synthesis` refuses while `volley_status` shows a
missing owed facet and names the gap line
(`"<cell>: volleys_incomplete — <facets>"`), so the orchestrator hands it to
the gap wave the workflow already runs **before** the challenge is bought.
This is the owner's 2026-10-09 rule — a rule a challenger can state in one
sentence is refused at the write.

### 5. A CEILING_ESTIMATE could not show the range it was failed for — FIXED

The SKILL table defines `CEILING_ESTIMATE` as ids **plus the uncertainty**.
Nothing required `Uncertainty`, the challenge packet never carried it, and
the challenger's manifest pointed it at `ceiling_band` (a band word) — so
P2C3.6.4 failed `claim_label_fit` for "no ± range", and the writer's fix,
`Ceiling_Band '2.0 (±0.5)'`, was refused as off-vocabulary (twice).

**Prevention:** the ledger refuses a `CEILING_ESTIMATE` without a numeric
`Uncertainty`; `brief._challenge_cell` carries `uncertainty`; the challenger
manifest and the orchestrator sheet name the column.

### 6. A test site and a twice-dated page entered the register — FIXED

P2C1.8.5 rested a "$15 gift card" referral reward on
`test.westerncentralnyaaa.com`; the live site offers a $10 tour discount.
P2C1.5.6 cited one phishing-warning page as CURRENT (E-109) and UNVERIFIED
(E-134, E-135), and failed `recency` on the contradiction.

**Prevention:** `append_evidence` refuses a non-production host (test,
staging, dev, uat, qa, sandbox, preview, demo — sub-domain labels only, so
`dev.to` is untouched). A page has one date: an omitted `--published`
inherits the page's, a conflicting one is refused, and a first date dates
the page's earlier undated rows (logged as `page_dated` in Provenance).

### 7. $28.04 of agent spend never reached the ledger — FIXED

With no Workflow tool after the session restart, the conductor wrote each
rendered prompt to `<root>/briefs/research_agents/<CAT>_<step>.md` and
dispatched "Your complete brief is the file …". `cost.capture_workflows`
books an in-session agent only when its prompt names the **run id**; 41
agents named the run **root** instead and were invisible to every envelope
and ceiling.

**Prevention:** the run root is as unique as the id; capture books an agent
whose prompt names either (a helper that merely read a run file later is
still excluded).

## Patterns recorded, not changed here

- **Sister-entity contamination in a federated brand.** AAA is one brand over
  ~30 independent clubs. The PRELIM conductor locked five AAA clubs as peers
  (fixed in-session: `engine.prelim replace-peers`, PR #104); Clay and Vibe
  technographic readings returned the national estate (logged EMPTY); the
  evidence engine served national-AAA, ACG, AAA Northeast and AAA Life pages
  that collectors had to refuse one by one, and a DFS consent order that
  belonged to AAA Northeast. The owner's binding answer was "Public.
  Strictly focus on that entity. Not the entire AAA" — and it reached the
  agents only as prose in their briefs; nothing in the engine carried it.
  Fix 1 removes the largest cause. A durable
  addition is a run-level `sister_domains` exclusion (aaa.com, acg.aaa.com,
  northeast.aaa.com …) the engine filters before ranking and the ledger
  refuses at registration — an owner decision on scope, so left open.
- **Workbook lock contention.** Sixteen categories write one `.xlsx` through
  one file lock (420 s timeout). P3C2's challenge batch stalled 420 s and
  P1C3's gate needed three attempts. Sharding the workbook per category is
  the structural fix; capping concurrent category workflows is the cheap
  one. Both trade wall-clock for reliability and need the owner's call.
- **Budget calibration.** PRELIM spent $14.07 against a $2 envelope and
  round 1 ran 37% over its estimate; the driver's own recalibration
  (`×1.372`) absorbed the second. The ceiling cannot stop a round it cannot
  see until the workflows return — the same blindness fix 7 closes for
  in-session agents.

## Proof

`tests/skills/research_engine/test_aaa_wcny_root_causes_2026_10_14.py` (one
test per fix, each failing on the pre-fix engine) and
`apps/evidence-engine/tests/test_entity_domains_2026_10_14.py`.
