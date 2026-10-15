# Peer benchmark vs peer comparison

The owner's ruling on 2026-10-15, made after the AAA Western and Central New York first promotion:

> "they can include them as part of benchmark scores. But for peer analysis,
> then they are only researched with regard to that entity's focus area.
> Distinguish between peer benchmark (derived from an average of scores of
> already assessed entities), and peer comparison (looking at the selected
> peers and comparing them to the entity being assessed."

DMA Insights uses the word "peer" for two different things. A page, gate or agent must say which one it means. If it carries both, they go in separate fields.

## The two concepts

| | **Peer benchmark** | **Peer comparison** |
|---|---|---|
| Question it answers | "Where does this client sit against institutions like it?" | "What are *these named* institutions doing about the things this client says it is trying to do?" |
| Who is in it | Every already-assessed entity in the client's sub-vertical, promoted or not, excluding the client. One run per entity: its promoted run, otherwise its latest scored run. Withdrawn, superseded and non-ACTIVE entities are left out. | The **selected** peers: the 3–5 institutions PRELIM locks in `Handoff_Lock.locked_peer_set` under a stated selection rule. Only the owner can widen or replace them. |
| What it is | A **number**: mean, median, p25 and p75 per category or cell, with `n`. | **Findings**: per selected peer and per client focus area, what they run, launched or report (deployed / not deployed / unknown, a comparable metric), each with a basis and source. |
| Scope | Every category and cell in the run's scope. | **Only the client's focus areas** (`Focus_Areas`, FA-NN, the cells each focus area names). |
| Researched? | **Never.** It is computed from scores already in the store. | **Yes**, and only on the focus areas. |
| Names anyone? | **Never.** Aggregates only, and no entity id leaves `cohort.py`. Invariant 5 strips cohort `entity_ids` for every audience. | **Yes**, the selected peers by name. The owner allows clients to see them as "identified, not scored" (2026-10-04). |
| Scores the peers? | It *is* scores, but other assessments' scores, averaged. | **No.** This engine never scores a selected peer by category. A per-peer figure is admissible only from a published table someone else scored (`peer_basis = table`). |
| Floor | 3 entities per category or cell, otherwise `cannot_estimate` with the reason. It is never imputed. | No floor on the set; `client_research` §4 wants a lock statement. Each answer can be `unknown` with its search ladder. |
| Computed or stored where | `apps/mcp/dma_mcp/cohort.py` (`assessed_runs`, `cohort_benchmarks`, `cell_benchmarks`) is exposed as `get_cohort_benchmarks`. The workbook copy is `Peer_Benchmarks.Peer_Median / Peer_P25 / Peer_P75 / Peer_N / Peer_Basis`, written by `engine.prelim fill-cohort`. The fit engine fills gap-row peers at fit time (`fit._cell_peers`). | The lock is `Handoff_Lock.locked_peer_set / peer_n / peer_basis`, written by `engine.prelim peers / widen-peers / replace-peers`. Rows go in `Tech_Peer_Deployments` (`TS_ID, Peer, Focus_ID, Deployed, Basis, Source_URL, As_Of`) via `engine.cli techscan peer-record --focus FA-NN`, and in `Platform_Peer_Adoption` via `engine.assessment peer-adoption`. The PEER_FOCUS metric probes are in `relay.report_probes`. |
| Payload fields | `overview.scores.pillars[].peer_median / peer_n / peer_basis / proxy_disclosure`, `heatmap.workbook_scores[].peer_median`, `heatmap.focus_areas[].peer_score / delta`, `overview.findings[].peer_median`, `overview.opportunity.tiles[].addressable_cells[].peer`, `platform.platform_story.platforms[].gaps[].peer_score`, `top_contributors[].peer_median`. | `platform.platform_story.platforms[].peer_deployments[] / peer_coverage / peer_synthesis`, `techstack.techstack.items[].peer_deployments[] / peer_coverage`, Client Research §4.1 "Peer comparison", Assessment Report §6.5. |
| Gates | CG-44 cascade (focus-area `peer_score` to the overview strip), delta arithmetic, grain tolerance. | AG-04 (one row per selected peer per platform tile, each with a basis), CG-51, ET-09 allow-list. |

## How the data flows

```
                 ┌──────────────── PEER BENCHMARK ────────────────┐
 subcap_scores of every assessed entity in the sub-vertical
   (promoted run, else latest scored; client excluded; floor 3)
        │  cohort.assessed_runs → cohort_benchmarks / cell_benchmarks
        ▼
 get_cohort_benchmarks ──► Peer_Benchmarks.Peer_Median/P25/P75/Peer_N
        │                     (engine.prelim fill-cohort, basis "recomputed:
        │                      sub-vertical cohort …")
        ├──► rollup Gap_to_Peer ──► heatmap grid, overview hero, focus-area delta
        └──► fit._cell_peers ──► platform gap rows, opportunity cells
                 └─────── a number; names no one; never researched ───────┘

                 ┌──────────────── PEER COMPARISON ───────────────┐
 PRELIM: engine.prelim peers --peer … --rule …   (3–5 selected peers, locked)
 PRELIM: engine.profile focus --id FA-NN …       (client's stated priorities)
        │
        ▼  research ONLY where a focus area reaches
 techscan peer-record --ts TS-nnn --peer <locked> --focus FA-NN
 relay probes: PEER_FOCUS (metric per peer per focus area),
               PEER_PROBE / PEER_LAYER (only platforms and layers a focus area reaches)
        │
        ▼
 Tech_Peer_Deployments / Platform_Peer_Adoption ──► peer_deployments, peer_coverage,
                                                    peer_synthesis, report §4.1 / §6.5
                 └──── named findings; never scored; never feed peer_median ────┘
```

## Rules the code enforces

| # | Rule | Where it is refused |
|---|---|---|
| R1 | The benchmark counts every assessed entity in the sub-vertical, whether promoted or not. The sub-vertical is resolved through the alias table, so "Insurance Brokers" counts as IB. | `cohort.assessed_runs` |
| R2 | The benchmark names no one. | `cohort.summarise` (aggregates only) |
| R3 | `Peer_Benchmarks.Peer_N` is the **benchmark's** n. It stays blank until the cohort figure is written. The selected set's size lives in `Handoff_Lock.peer_n`. | `prelim.peers / widen_peers / replace_peers` |
| R4 | Selected peers are not scored by category. `--peer-scores` is refused unless `basis = table`. | `prelim.peer_median` |
| R5 | A comparison row names a **locked** peer. Names are matched on the whole name, never on a shared first word. | `techscan.locked_peer` |
| R6 | A comparison row answers a **client focus area**. With no focus area recorded there is no comparison. A product whose cells share no category with the focus area is out of scope. `Focus_ID` is recorded on the row. | `techscan.comparison_focus` |
| R7 | Research probes for selected peers cover only the platforms and register layers a focus area reaches. The PEER_FOCUS metric probe asks one question per peer per focus area. | `relay.report_probes` |
| R8 | A platform tile outside every focus area still carries one row per selected peer for AG-04: `deployed: null`, basis "not compared: outside the client's focus areas". | AG-04 message (`peer_set.named_peer_findings`) |

Tests: `tests/skills/research_engine/test_peer_benchmark_vs_comparison_2026_10_15.py`, `apps/mcp/tests/test_cohort_benchmarks.py`.

## Worked example: AAA Western and Central New York (IB)

- **Benchmark.** Before 2026-10-15 the IB cohort read 2 promoted entities, so every `peer_median` was null. Counting assessed entities as well, it reads OneDigital, TowneBank, Virtuity, Alera and the two promoted brokerages: at least 6, which clears the floor of 3. Alliant and IMA are PENDING_REVIEW and stay out. None of them is named on AAA's pages.
- **Comparison.** The selected peers are Lawley Insurance, NBT Insurance Agency and Tompkins Insurance Agencies (replaced on the owner's word, 2026-10-14: "No AAA clubs at all"). They are researched only on AAA's focus areas, e.g. member digital servicing. They are not researched on the 694 cells, and they are never given a score.

## Where the code still mixes the two, and what each needs

Found by sweeping the repo on 2026-10-15. "Fixed" means fixed in this change.

| # | Where | What is mixed | Status |
|---|---|---|---|
| 1 | `prelim.peers` | Wrote the selected set's size into the benchmark row's `Peer_N`. | **Fixed** (R3) |
| 2 | `prelim.peer_median --peer-scores` | Scored the selected peers by category under any basis. | **Fixed** (R4) |
| 3 | `techscan.peer_record` | Accepted any institution, on any product, with no focus scope. | **Fixed** (R5, R6) |
| 4 | `relay.report_probes` PEER_PROBE / PEER_LAYER | Researched every peer × every platform and layer. | **Fixed** (R7) |
| 5 | `prelim.fill_cohort_peers` source text | Said "active promoted runs". | **Fixed** |
| 6 | `Peer_Benchmarks` | One tab holds the benchmark figure *and* `Peer_Names` (the selected set). | Kept: the app's parser reads this shape. The columns are now documented per concept: `Peer_Names` is comparison only, and `Peer_Median/P25/P75/N` are benchmark only. |
| 7 | widen / replace refused once a `Peer_Median` exists | Ties the selected set's lock to the benchmark figure. Since the benchmark no longer depends on who is selected, the guard is stricter than it needs to be. | **Owner call:** should the owner be able to widen or replace the selected set after the cohort figure is written? Recommended: yes. |
| 8 | CG-44 (`peer_set.o1_cohort_findings`) and the O1, H1 and H4 producer rulebooks | A null **benchmark** median must disclose the **selected** peers by name. | **Owner call.** Recommended: the benchmark disclosure states the cohort ("n assessed IB entities, floor 3"), and the selected peers are named on the comparison surfaces. This supersedes RC-10(c)/D-17 for the benchmark field only. |
| 9 | Assessment Report template §6.1 "Peer scores" (per-peer Overall, strongest/weakest pillar, rank, "highest scoring peer") | Scores the selected peers. | **Owner call.** Recommended: §6.1 becomes "Benchmark position" (cohort mean and quartiles), and the named deep dive moves to §6.5 on focus areas only. |
| 10 | `peer_basis_t` (`table · recomputed · inferred · cannot_estimate`) | The TRD's `recomputed` means a named-peer median re-taken at a smaller n; the engine uses it for the cohort mean. | Kept: Backend Schema authority #1, so the enum is not changed. `recomputed` with a source naming `get_cohort_benchmarks` *is* the benchmark. |
| 11 | `peer_scores` table ("the peer cohort table", Backend Schema) | Holds named-peer figures from legacy packages, and `peer_set.run_peer_set` reads it to identify the selected set. | Kept (schema). Read it as comparison-side legacy data. It never feeds the benchmark mean. |
| 12 | `assessment.py` Executive_Summary "Peer Median (est.) — locked peer set: {names}" | One cell carries both concepts. | Follow-up: split into two cells. |
| 13 | Web: `pages-d3-heatmap.jsx` drawer titled "Peer comparison" over the median bar; `pages-live-client.jsx` "Peers" toggle on the median column; `live-adapter.jsx peerSetsOf` infers a named set from `peer_n: 5, peer_basis: table` | UI copy calls the benchmark "peers". | Follow-up: relabel to "Peer benchmark" (render-layer copy, no payload change). |
| 14 | O1 rulebook `peer_basis: same_subvertical_cohort_median`, drawers `category_proxy` | Values outside the enum. | Follow-up: rulebook text only. |

Items 7–9 change owner-adjudicated behaviour (RC-10, D-17) and client-facing report structure, so they wait for the owner's call.
