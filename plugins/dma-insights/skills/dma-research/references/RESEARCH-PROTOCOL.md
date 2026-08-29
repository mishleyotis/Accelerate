# The research protocol — one category, one agent, one workbook

The protocol every per-category researcher works under. The sixteen category
manifests in `categories/` bind an agent to its category and point here; this
file carries everything they share, ONCE, because sixteen copies of a
protocol drift sixteen ways (`RULE_HELD_IN_TWO_PLACES_DRIFTS` is the third
most common open defect class in this system's findings memory).

The engine commands below live in
`${CLAUDE_PLUGIN_ROOT}/skills/dma-research/engine/` and every one of them
reads and writes the SAME scoring workbook. The workbook is the substrate —
not an export, not a mirror of some JSON plane. What you do not write there
did not happen.

## Your standing

- You research **one category** of one run. You never write another
  category's rows, never write a score (column D is the assessment stage's),
  never submit, never promote, and never touch the connector's write tools.
- The conductor dispatched you with a `--run` id and `--root`. Everything
  else you need is in the workbook: `engine.cli orient --run R --root ROOT
  --category <YOURS>` is your first command and your compass after every
  interruption. **Obey its `do_first` list literally** — it never says
  "clean" while your work is open, and when it says STOP (the search-op
  ceiling), you checkpoint and end your turn.

## The loop, per work card

`orient` hands you one card: a subcap, its diagnostic questions already
filtered to the run's evidence mode, the toolkit's own source lists, and
query seeds. Work it in this order:

1. **Read the card's questions.** Each carries a facet (`primary`, the five
   probes, the three AI-overlay questions) and — where the toolkit knows —
   `internal_sources` / `public_sources`: the named artefacts that answer
   it. Hunt the NAMED artefacts first; a researcher told what to look for
   stops fishing.
2. **Plan queries** — `engine.cli fuse plan --run R --subcap X --facet works`
   gives the three differently-shaped probes per DQ (presence, responsive,
   toolkit-artefact). Fire them across the search tools you hold (WebSearch;
   Exa and Tavily where present). **Log every search**:
   `engine.cli search --run R --subcap X --facet works --query '…' --hits N
   --kept M`. An unlogged search never happened, and the contradicts gate
   reads the log.
3. **Fuse before you fetch.** Write each tool's ranked results to one JSON
   (`{"lists": [[…],[…]], "query": "<the DQ text>"}`) and run
   `engine.cli fuse --in results.json --query '…' --top 8`. Reciprocal rank
   fusion (k=60) prefers CONSENSUS — a source three probes agree on beats a
   source one probe loved — and the BM25 rerank ABSTAINS on noise instead of
   ranking it. Fetch the ranked list top-down; `below_floor` is yours to
   judge, not silently dropped.
4. **Note as you go.** The moment you have something real — a quote, a lead,
   a contradiction, an absence taking shape — write it to your category
   notebook: `engine.memory note --run R --category <YOURS> --subcap X
   --facet works --kind evidence --claim '…' --excerpt '<VERBATIM 50-500
   chars>' --url … --source-name … --tier T2 --published YYYY-MM-DD`. The
   notebook survives your context; your context does not. Kinds: `evidence`
   (registrable), `lead` (worth chasing, not yet evidence), `absence` (with
   `--ladder`, rung by rung), `contradiction`, `note`.
5. **Consolidate before you synthesise**: `engine.memory consolidate --run R
   --category <YOURS>`. Every note goes through the workbook's own refusals
   — an entry that cannot register is marked BLOCKED in the notebook with
   the ledger's reason. Repair the NOTE (usually the verbatim excerpt or the
   URL), never work around the gate.
6. **Synthesise** the subcap (`engine.cli synthesise --run R --subcap X
   --json rec.json`, with `--actor <your-agent-name>` recorded). The write
   path refuses placeholder prose, unanswered DQ facets, unsupported claim
   labels and undeclared absences — a refusal names exactly what is missing.
   Deferred questions on your card (mode-filtered out) go into
   `Discovery_Questions` as the card gives them (`INT-Q:` / `PUB-Q:`),
   never silently skipped.
7. **The challenge is not yours to write.** Your synthesis author name is
   recorded; a DIFFERENT actor (the conductor routes to `finding-challenger`
   discipline) records the challenge verdict, all seven dimensions by name.
   `record_challenge` refuses a self-challenge — do not try.

## The five volleys — the order that keeps you honest

Every subcap's card carries nine questions: the toolkit `primary`, five
facet probes, three AI-overlay. The five probes are five VOLLEYS at the
same claim, and their order is load-bearing — each exists to break the
anchor the previous one set:

| volley | facet | what it must do |
|---|---|---|
| 1 | `works` | steelman: the best honest case that the capability exists and functions |
| 2 | `fails` | falsify volley 1 with fresh queries — outages, complaints, abandonment, workarounds. NEVER a negated copy of the works query; shape it around failure artefacts (status pages, review sites, regulator complaints) |
| 3 | `value` | quantify: what the capability measurably does for the client — a number, a date, a named outcome, or honestly nothing |
| 4 | `contradicts` | hunt the disconfirming source for whatever volleys 1–3 currently support. Runs BEFORE corroborates so confirmation cannot close ranks first |
| 5 | `corroborates` | only now: the independent second source for what survived volley 4 |

Rules the gates enforce and you must not soften:

- **Every volley fires or is `NOT_RUN: <reason>`** — the synthesise path
  refuses a facet that is neither (AUD-0017). Rich evidence on `works` is
  not a reason to skip `fails`; it is the reason `fails` matters.
- **Fuse within a volley, never across volleys.** RRF consensus is only
  meaningful between probes asking the SAME question; blending `contradicts`
  hits into a `corroborates` list launders disagreement into agreement.
- **A contradiction is a finding, not friction.** Note it
  (`--kind contradiction`) with both sides; consolidation records an OPEN
  disposition the synthesis must argue, not bury.
- **The `contradicts` gate reads the search log**, so an unlogged volley 4
  reads as a volley that never happened — because it didn't.
- The three AI-overlay questions (`ai_deployment`, `ai_data`,
  `ai_constraint`) ride after the volleys and follow the same
  answered-or-NOT_RUN rule.

## Internal artefacts (HYBRID / INTERNAL runs)

Your card's `internal_sources` name the client documents that answer the
DQ. In HYBRID/INTERNAL mode those live in the client's Drive folder — use
your Drive READ tools (`search_files` scoped to the client folder,
`read_file_content` / `download_file_content`) to fetch the NAMED artefact,
then register what it says with `--origin internal` and a verbatim excerpt.
You never write to Drive; the conductor owns backup and shipping.

## After a compaction, a resume, or any interruption

Your context can be summarised away mid-category; the workbook and your
notebook cannot. On the first turn after any interruption, in order:

1. `engine.cli orient --run R --root ROOT --category <YOURS>` — the card
   server re-derives your position from the workbook: volleyed subcaps are
   re-served before anything new, and `do_first` is the recovery plan.
2. `engine.memory status --run R --root ROOT` — what you NOTED but never
   consolidated is still there; consolidate before you research anything
   new, because a note that predates the compaction is evidence your
   context no longer holds.
3. Never re-derive from recall what these two commands state from disk. A
   remembered position that disagrees with `orient` is wrong — the workbook
   is the substrate, and your memory of writing it is not.

## Evidence discipline (the short form; the gates enforce the long one)

- An excerpt is a VERBATIM 50–500 character span of the source, or it is
  not evidence.
- A public claim with no URL is registered `--origin internal` and labelled,
  never laundered into a weak public FACT.
- Proxy evidence establishes what a PEER does, never what this client does:
  a proxy-only case cannot wear FACT.
- An absence needs its ladder — direct, proxy, peer, regulatory — with the
  queries actually fired (the gate counts rungs against the search log).
- Sibling smearing (one document cited across the category to clear floors)
  blocks the gate. Three items per subcap means three items that BEAR.

## Technographics

When a search surfaces a named product in your category's cells, record it:
`engine.techscan record --run R --product … --vendor … --layer OPS|CUST|DATA|INFRA
--status CONFIRMED|INFERRED|CLAIMED|ABSENT --method … --basis '…'`.
CONFIRMED needs evidence ids that resolve; ABSENT needs the search that
establishes it. The scan is the package's fourth deliverable — what you
record here is what ships.

## Closing your category

1. `engine.cli gate --run R --category <YOURS> --require-synthesis` — and
   read the verdict. A FAIL names its blocking terms; repair and re-run.
   Running out of cards is not closure; the gate is.
2. `engine.memory status --run R` — nothing of yours still NOTED or BLOCKED.
3. `engine.memory backup --run R` — the notebook's Drive copy (honest
   outcomes; a NOT_RUN is reported, not assumed pushed).
4. Report to the conductor: the gate verdict, your deferred-question count,
   your techscan rows, and anything you judged UNTESTED. You do not proceed
   to another category.

## Budget

The search-op ceiling is enforced (`orient` withholds the card and says
STOP). Do not read whole state files into your context — `cat` on the
evidence index, the ledger or the engagement set is denied by hook, and the
bounded reads it suggests answer the same questions. One `orient` call is
cheaper than any re-derivation.

## Refusals you must respect rather than route around

Every refusal in this pipeline carries its reason and the repair. The
gates' refusals are the product working — a workaround that gets content
past them is the defect the audit trail will name later, with your actor
name on the provenance row.
