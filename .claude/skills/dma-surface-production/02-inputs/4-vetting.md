# Vetting the workbooks before anything is parsed

You are the first reader of the package and the only one who can refuse it. The parser is
deterministic: handed a workbook whose headers it does not recognise, it does not fail — it
silently produces the wrong thing, and the wrong thing promotes. Every defect listed below
reached production at least once, and each was found on a rendered page rather than at
ingest.

So the order is: **vet, then parse, then match, then escalate, then enrich, then produce.**

```
Drive package
 ├ 1 VET       you · workbook hygiene. Refuse a dirty workbook and say why.
 ├ 2 PARSE     scripts · scoring workbook AND research workbook AND package csv/json
 ├ 3 MATCH     scripts + embeddings · exact id first; embeddings only PROPOSE
 ├ 4 ESCALATE  you · every contention, with candidates and scores, adjudicated in writing
 ├ 5 ENRICH    you · thin cells with plausible public data get the ladder BEFORE any alert
 └ 6 PRODUCE   you · through the connector, gates unchanged
```

## 1 · What to check, and what each failure does downstream

Run `python scripts/vet_workbooks.py <package-dir>` for the mechanical checks, then read the
two workbooks yourself for the judgement ones. The script reports; you decide.

| Check | Why it matters — the actual consequence |
|---|---|
| **Tab inventory** | A generation the parser does not know is rejected wholesale. One client's workbook had a single `Scoring_Workbook` tab where the parser expected per-pillar detail tabs; the whole package failed to ingest. Name the tabs you see. |
| **Header aliases** | `Median`, `P25`, `P75` are STATISTICS. A parser that treats an unrecognised score column as a peer invents peer institutions literally named "Median" — 54 rows of them in one run — and the median cross-check then never runs. |
| **Id formats** | A `Priority` column holding 1…8 is a rank, not an id. Requiring a `REC-` prefix dropped all eight recommendations, which is why a platform page had none. |
| **Duplicate evidence ids** | `Evidence_Master` reusing `E-068`–`E-074` for different sources loses rows silently under `ON CONFLICT DO NOTHING`. 82 in, 75 stored, no observation. Report every collision. |
| **Out-of-range scores** | Anything outside 1.0–5.0, or a blank that later reads as 0. A 0 bands as Activating and looks assessed. |
| **`source_cell` present** | It cannot be backfilled after the scan. Missing means the cell can never be traced to its workbook row. |
| **Category count vs catalogue** | 17 categories means v5.0, 16 means v7.0. An unpinned run joins against the wrong catalogue and EVERY cell name comes back null — 765 nameless heatmap cells in one run. State the version you infer and what you inferred it from. |
| **Peer grain** | Peer medians exist at category and pillar grain, not per subcap. A per-subcap peer figure in a workbook is a copy of its category's; say so, because the app must label it a proxy. |
| **Reference date** | The run's own completion date. Absent, every evidence item bands `UNVERIFIED` regardless of its publication date — 120 items, 45 of them dated, all unverified — and a FACT then renders beside an "unverified" label. Check the manifest AND the request id's `…-YYYYMMDD-NNNN` token. |
| **Excerpt depth** | Excerpts under 50 characters fail registration; excerpts around 80 pass and say nothing. Report the median and the count of empty ones. |

## 2 · Refusing

A refusal is a finding, not a failure. Write it as: what you found, which tab and column,
how many rows, and what would render wrong if it were parsed anyway. Then stop — do not
claim the run.

If the defect is repairable from the research workbook (a missing date, a missing ERS), say
so and continue: the research workbook is authoritative for the evidence tier and the
scoring workbook for scores, and **a score is never taken from the research workbook**.

## 3 · Matching, and when to escalate

Exact id match first, always. Embeddings only ever PROPOSE:

- Below the similarity floor → **contention**, never a silent assignment.
- Two candidates inside a narrow margin of each other → **contention**, even if both are
  above the floor.
- A placeholder or unnamed cell is never a candidate.

Precision over recall. An evidence item linked to the wrong cell is worse than one linked to
none: the wrong link renders as support for a claim it does not support, and it will be read
in a meeting.

Every contention is escalated to you with its candidates and their scores, and you record
the adjudication **with its reason**. An adjudication with no reason is indistinguishable
from a guess six months later.

## 4 · Enriching before alerting

A thin cell is a search you have not done yet. Before any thin-evidence alert is emitted:

1. Run the ladder (`01-start-here/4-absence-protocol.md`) — tiers 1–6 are mandatory.
2. Register whatever you find (`register_evidence`) and link it.
3. Only then, if it is still thin, emit the alert with `sources_searched` and a
   `closure_condition` naming what would settle it.

**Do not exclude a cell for having no evidence.** It keeps its workbook score and its dashed
outline, and the alert states the gap. Hiding a cell hides the finding; the client's
assessment covered it, so the page shows it.

## 5 · What the vet step writes down

Whatever you conclude, record it so the next run does not re-derive it:

- the tab inventory and the generation you matched
- the catalogue version and how you inferred it
- every duplicate id, out-of-range score and missing `source_cell`
- the reference date and where you got it
- the excerpt median, and the count below 50 characters
- every contention and its adjudication
- every ladder that ran and its result

This is the record that makes a rerun cheap and a dispute settleable.
