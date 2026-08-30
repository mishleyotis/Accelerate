# The end-to-end procedure for ingesting the next DMA

Calibration reference throughout: **Baxter Credit Union**
(`baxter-credit-union-bcu`, SV2). Gates named at each step are hard
acceptance criteria.

---

## Stage 0 — the run comes to exist (worker, not me)

The client folder lands in the Drive intake tree (General DMAs,
`1xIClbzw-SRBJ0Et3SOWnb7YhcBM8b6mo`). `dmai-package-scan` fires
`dmai-worker` every 30 minutes: walk → diff against `import_scans` →
classify artefacts → 4-signal entity cascade → dedupe → parse both
workbooks with `source_cell` → artefact bytes to GCS → excerpt
verification → `scored_cells` stamp. Idempotent; an unchanged tree
creates nothing.

**Check:** `INTAKE_STATUS=1` on the worker Job classifies every folder
(`no_run · run_unparsed · parsed_unsynthesised · synthesised_unpromoted ·
promoted_superseded · promoted_current`) with a `reason`.
`list_pending_runs` shows what is claimable.
`scripts/synthesis_queue.py --pending <json>` picks which run to take and
states a reason for every run it skips (duplicate re-uploads, live claims,
reruns).

## Stage 1 — vet the package before anything is parsed from it

`python scripts/vet_workbooks.py <package-dir>` for the mechanical checks,
then read both workbooks myself for the judgement calls. **A refusal is a
finding, not a failure** — the parser is deterministic and a workbook whose
headers it does not recognise produces the wrong thing silently, and the
wrong thing promotes.

In the same pass, establish and write down the entity's shape:
**sub-vertical, size tier, ownership, brand set**
(`01-start-here/6-entity-shape.md`).

**Scores come from the scoring workbook. Evidence ids, excerpts, ERS and
published dates come from the research workbook. A score is never taken
from the research workbook.**

## Stage 2 — orient, then claim

```
get_run_progress(run_id)      → which pages pass, fail, or are missing
get_client_state(display_id)  → what is served now, and prior runs
claim_run(run_id, session_id, producer_version)
```

Never assume a run is fresh. If pages already pass, **do not re-synthesise
them** — repair what failed, produce what is missing, promote. A rerun must
be produced knowing what the last run said, or the longitudinal surfaces
silently empty.

**Namespace the scratchpad by `run_id`** and assert `run_id` + `display_id`
at every bundle read (standing clause 1).

## Stage 3 — read the contract, then the package

```
get_page_contract(page)          → field tuples AND the per-field doc text
get_report_bundle(run_id)        → the parsed assessment
get_capability_catalogue(run_id) → canonical cell ids and names + alias bridge
```

Read the contract rather than recalling it. The `doc` text is part of the
contract — for a list-of-object field it is the only place the item keys are
stated. **Cell names come from the catalogue, never from report prose.**
`get_page_contract(page)["transport"]` states the chunked-upload limits.

## Stage 4 — start Clay enrichment now, not later

One company call · one leadership search · one contact enrichment · at most
two targeted custom points. `scripts/clay_plan.py --domain <domain>` prints
the sequence and the tier each data point registers at. **Poll
`get-task-context` before concluding anything, including an absence.**
Tier follows the source: `Tech Stack` is T1.

## Stage 5 — produce, page by page, in this order

`heatmap → overview → insights → platform → context → techstack`.
Read the page pack before starting each one. Register every source
**before** citing it and **from the artefact fetched, in the same step**:

```
register_evidence(run_id, item) → {e_id, deduped, ers}
get_evidence(run_id, e_ids)     → {found, not_found, foreign}
```

`foreign` = a real row belonging to another institution. **Contamination:
stop, quarantine, escalate.** Never filter it out and carry on.

Run the absence ladder before writing any empty state. Write the run thesis
after the heatmap and each page's `narrative_thread` (45–75 words) before
submitting that page.

**Draft gate:** at draft 20 of any large array, before writing the 21st —
```
python scripts/check_repetition.py drafts.json --page <page> --at-scale <N>
```
CG-15's template rule is a property of the array and invisible per item.
Baxter's 706 cells score 0.179 against a line of 0.40, so the scale is not
the problem if this refuses me.

## Stage 6 — run the reasoning layer

R-Layer A–E on every ranked, causal or comparative claim, recorded as
`r_layer`. Surface probe sets plus the four universal probes (foreign
variant cell · cohort scale · shape-blind ladder · cohort sentence).
Cross-check every fact appearing twice; quarantine contradictions, never
average.

## Stage 7 — local checks, then submit

```
python scripts/check_payload.py payload.json --page <page> \
       --subvertical <CODE> --cells bundle.json
python scripts/check_language.py payload.json
python scripts/precheck_gates.py payload.json --page <page> \
       --evidence get_evidence.json --bundle get_report_bundle.json
```

`--subvertical` turns ET-05 on and `--cells` turns CG-14 on; without them
those print "not run", **which is not a pass**.

Then:
```
submit_page_payload(run_id, page, payload, provenance, producer_version)
   → {submission_id, verdict}
# or, for a payload too large to inline:
open_payload → append_payload_part × N → submit_page_payload(upload_id=…)
```

**Gates it must clear:** contract pass · evidence pass · AG-03 · AG-04 ·
CG-01 grain · CG-09 · CG-10 · CG-11 · CG-12 · CG-14 · CG-15 · CG-16/17 ·
ET-01 · ET-04 · ET-05 · ET-09 · V1–V4. SG results (e.g. SG-S8) record and
disclose; they do not block.

**Read the verdict literally and repair the cause, not the symptom.**
Resubmission supersedes cleanly — but it also costs a pass if the page was
passing, and inside a promotion window that blocks every other page, which
is why the local checks come first.

## Stage 8 — reconcile the whole run

```
python scripts/check_consistency.py <rundir>/ --subvertical <CODE>
```

Seven reconciliation pairs, foreign variant cells, silent drawers, coverage
denominators, and whether the five narrative anchors describe one
constraint. A contradiction *between* pages survives every per-page gate.

## Stage 9 — challenge the storyline, then answer the panel

Five volleys (client executive · finance officer · incumbent vendor · rival
on the shortlist · the AE), recorded with what changed. **Five `held` is a
finding, not a triumph.** Then the fifteen answered questions, 40–110 words,
cited. If a volley changes the storyline, resubmit the affected pages and
re-run `check_consistency.py`.

## Stage 10 — promote

```
promote_run(run_id) → all six pages, one transaction, all or nothing
```

`incomplete_run` names the missing and unpassed pages. Re-promotion is
idempotent. Note the current behaviour: a **retained** page that fails
today's **blocking** gates refuses with `retained_pages_fail_current_gates`
and names them — resubmit only those pages, the other retained rows are
still good. SG reasons are excluded from that refusal and still
disclose-and-promote.

## Stage 11 — verify what a client can actually load

`promote` proves the payload was accepted. Between a passing payload and a
rendered page sit a redaction walker, a generated column, a materialised
view, a cache key and a frontend resolver — none of which the payload saw.

```
python scripts/audit_promoted_client.py --api https://<api-host> --entity <slug>
```

Checks A–F: serialised leaves · em-dash dead ends in content · **the drop
signature** (a field null on 100% of 3+ rows — the signature of a value lost
between producer and serve; 32 such paths were live on Baxter for five days
while it was cited as the gold standard) · alert ceiling · enrichment
visible · **redaction holds against the CUSTOMER body**.

The `dma-insights:deployed-app-auditor` agent does the same against the live
app and reports `UNVERIFIABLE` rather than collapsing to PASS when it cannot
fetch.

## Fixing one card later

No new run needed. Promoted staging rows are retained: re-claim → resubmit
only the affected page → `promote_run` again. Read
`05-lifecycle/2-versioning.md` first for reruns and catalogue bumps.

---

## The seventeen non-negotiables (short form)

1 never assign a score · 2 never invent an identifier (I create only `ic_id`,
`f_id`, `fa_id`, `ts_id`, `wn_id` + authored `rec_id`) · 3 register before
citing, and cite at the item · 4 a quoted figure and its named cell are one
row within 0.05 · 5 every figure passes the identity gate · 6 a derived value
is computed or null · 7 mark internal rungs in the payload · 8 absent beats
wrong · 9 counts are computed, not asserted · 10 order is meaning · 11 run the
ladder before saying no · 12 frame every gap as available value, and no prose
field opens on an absence · 13 a page tells one story · 14 argue against my own
conclusion before shipping it · 15 never average two disagreeing figures ·
16 serve the entity's cell set and count over the same one · 17 every served
cell opens a drawer that says something.
