# Stress test — Bank of Travelers Rest

Run 2026-09-03 against the pipeline built this session, on a client that had
never been through it. The point was not to produce a deliverable: it was to
find out what the new scripts do when handed a package they were not tuned
on. Everything below is measured, and the parts that could not run say so.

Run `2b5bc7a2-67ac-4d75-aee6-a985ce4e6d74` (`bank-of-travelers-rest`,
sub-vertical RB, 688 scored cells).

## What it found before a single page was produced

**Nineteen runs, eighteen with `scored_cells = 0`.** The package ships two
workbooks and artefact precedence is decided by FILENAME:

| File | Rank | Reality |
|---|---|---|
| `DMA_Scoring_Workbook_*` | 0 → chosen | research-stage v5: 688 rows, column D empty by contract, **0 scored** |
| `DMA_Assessment_Workbook_*` | 1 → discarded | **688 scored, composite 1.71 at `Pillar_Summary!C6`** |

The name won and the scores lost, and the runner-up was discarded at grouping
time so nothing downstream could recover. Fixed by keeping alternates and
falling through only when the ranked choice states no scored cell.

**Four workbooks at three depths in one folder, three byte-identical**, with
the scan reading neither the newest nor the one with scores. Fixed by
excluding copy directories and breaking equal-rank ties on modified time.

## What `check_template.py` said about the workbook

    botr_asm.xlsx: 20 tabs — 11 of 29 read-tabs carry data
    MISSING (18) — the surface each one starves

Against Golden 1's 43 tabs and 28 of 29. BOTR's two workbooks are
COMPLEMENTARY — one holds `Firmographics`, `Focus_Areas`, `Issue_Register`,
`Subcap_Scores`; the other `Entity_Timeline`, `Tech_Register`,
`Report_Narrative`, `Provenance` — so together ~26 of 29 and separately 11
and 13. **Neither is a viable package alone.** That is what binding to a
split, older template produces.

## What the readers did on a client they were not written for

Every reader added this session worked unchanged on a different sub-vertical
and a 20-tab generation:

| | |
|---|---|
| `_stated_overall_grain` | **1.71** from `Pillar_Summary!C6` |
| `parse_grain_summaries` | 4 pillars / 16 categories |
| `parse_scoring_workbook` | 688 scored cells |
| `parse_tech_register` | 19 product rows, each with a detection basis |

## What `self_heal.py` caught in real content

A techstack section was built from BOTR's own 19 register rows, with the T2
layer counts recomputed from T1 rather than stated.

    self-heal: 17 blocking, 0 advisory     (exit 1)

All of them CG-12: **12 of the 19 `detection_basis` values exceed the
160-character face budget**, the longest at 300. Those come straight from the
workbook, so this is a package defect the gate would have refused at submit —
found locally, for free, before a submission was spent.

## What `ship_page.py` did

    techstack: 1 section(s), 10,486 bytes, expect={"techstack.items": 19}
      part 1  fields (root)             2,158b
      part 2  items  techstack.items    8,319b

Run in `all` mode it skipped the five pages with no sections and planned the
one that had them — which is the incremental behaviour the orchestrator now
relies on, doing exactly what it should on a half-finished run.

## Token cost

The old path for this page: print 10,486 bytes in 4000-character chunks, have
an agent retype them into `append_payload_part`, compare byte receipts —
roughly 20–25k tokens, and the only step in the pipeline capable of inventing
content. The new path is one Bash call reading from disk: **zero model tokens
for the payload.**

For scale, the same method on Golden 1's overview (151kB) cost about 330,000
subagent tokens, twice.

## What this test did NOT exercise

**The network submit.** The connector needs its path token from Secret
Manager, and in this session that lookup — and gcloud generally — was refused
by the environment's permission classifier after the CA bundle rotated. So
assembly, planning, `expect` counts and every local gate ran on real BOTR
content; `append_payload_part` and `submit_page_payload` did not.

The transport itself is not unverified — it shipped all six Golden 1 pages
and reproduced the hand transport's parts byte-for-byte — but it has not been
exercised against BOTR, and concurrent shipping has not yet run through a
live assessment end to end. That is the remaining claim, and it is the first
real client run that settles it.
