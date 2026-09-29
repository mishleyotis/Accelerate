# Core engine: diagnostic question → search → evidence → subcap row

The loop one category lane runs per work card, through the engine. `RESEARCH-PROTOCOL.md`
is the full protocol; this file is the shape of one card's work. (Rewritten 29-09-2026,
QA audit F-L11-042: the batch-era steps — a Python helper appending to a JSON index, a
second-source connector call per query, a whole-page fetch of every rich document —
described a path the engine refuses.)

## Step 1: the card carries the questions

`engine.cli orient --run R --root ROOT --category <YOURS>` serves one card: the subcap, its
diagnostic questions filtered to the run's evidence mode (the toolkit `primary`, the five
facet probes, the three AI-overlay questions), the toolkit's own `internal_sources` /
`public_sources`, and query seeds. The engine read the Pillar toolkits at `engine.cli start`;
nothing re-parses an XLSX during a run. `references/diagnostic_questions.md` is the fallback
for a run with no toolkit bound, one question per category, and a run on it must say so.

## Step 2: plan the queries at capability grain

`engine.cli fuse plan --run R --subcap X --facet works` gives the three differently-shaped
probes per diagnostic question (presence, responsive, toolkit-artefact). The signals a query
must carry, and the ten-tier ladder behind them, are `references/deep_search_protocol.md`:

| Signal | Source | Mandatory? |
|--------|--------|-----------|
| 1. Diagnostic-question decomposition | subject + verb + qualifier + evidence target | tiers 1–2 |
| 2. Subcap keywords | domain terms from the subcap name and its parent | tier 3 |
| 3. Expected evidence sources | tier-aware targeting (governance → proxy statements, CX → app stores) | tiers 4–5 |
| 4. Proxy signals | when direct evidence is unlikely (board bios, job posts) | tier 7+ when signals are unknown or fewer than three items |
| 5. Contradictory / negative | failures, complaints, enforcement | tier 10, per capability |

**Proxy escalation.** If tiers 1–5 leave a signal unknown or ambiguous, the proxy tiers are
not optional. A cell ends SYNTHESISED or DECLARED ABSENT with its ladder; nothing else.

**Anti-shortcut.** The same query for several subcaps means you are searching at the wrong
level: each diagnostic question asks something different. Search at the capability, log at
the cell (below), and let `evidence_smear` keep the cells distinct.

**Query rules:** the institution name in every query; four to eight words; never the
diagnostic question verbatim; year markers in at least two queries per subcap.

**Which tool, in which order, and what you emit rather than fire** is
`RESEARCH-PROTOCOL.md` § *Tools: first choice, fallback, and what you emit* — the one place
that rule is stated.

**Never fetch a page whole to get an excerpt.** Read a rich document with
`engine.cli fetch --run R --url <U> --query '<the DQ text>'`, which prints at most three
~240-character windows and the page's sha256 and never the page. MEASURED on the six-cell
calibration: a fetched page sits in context and is re-read on **every later turn** — 76 % of
the bill was cache reads (24.45M cache-read tokens, $4.89 of $6.45). One fetch is 5–40K
tokens re-read every turn; three windows are ~200 tokens, read once.

## Step 3: execute and extract

Per subcap: search → fact-level extraction `[E-xxx:Fy]` → tier → recency → claim label →
the cells the fact bears on → red-flag check. For HYBRID/INTERNAL: the five-layer analysis
on every internal document. ERS is computed by `engine.cli ers recompute`, never typed.

**The empty-cell gate — what the ENGINE enforces (2026-09-03; owner: "some
subcaps are marked as no evidence without any enrichment efforts").** The
tiers above are how you THINK about a search; what closes a cell is
measured by `engine.floors_gate` and refused by `engine.cli absence`:

- every askable volley (`primary`, `works`, `fails`, `value`, `contradicts`,
  `corroborates`) has a LOGGED `engine.cli search --subcap <cell> --facet <f>`
  — `volleys_incomplete` and `primary_unfired` are blocking gate terms;

  **Search at the capability, log at the cell.** Your packet's *Work next —
  grouped by capability* section names the group each open cell belongs to
  and the union of volleys owed across it. One query usually answers the
  whole group, so fire it once and log it against every cell it bears on:
  `engine.cli search --subcap P1C1.1.1 --subcap P1C1.1.2 --subcap P1C1.1.3
  --facet works --tool exa`. Repeating `--subcap` writes one row per cell —
  which is what `volley_status` reads, so a sibling left off the list is a
  sibling the gate calls unsearched — and charges the search-op ceiling
  ONCE, because one tool call was made. Measured on the real catalogue: 686
  cells under 129 capabilities, and doing this drops a full run from 7,546
  turns to 3,905.

  It is a discovery pass, not the whole cell. `evidence_smear` blocks a cell
  whose shared evidence exceeds half its citations, so every cell still
  needs sources of its own — take the group find, then differentiate. That
  cap is exactly what keeps this capability-grain searching rather than the
  category-level mapping `deep_search_protocol.md` calls its #1 failure
  mode;
- at least one search for the cell ran through an ENRICHMENT connector
  (`--tool exa|tavily|clay|explorium|vibe|indeed|quartr|drive`), not only the
  built-in web tools — `absence_single_tool` blocks, and the declaration
  refuses without it.

  **If no connector is bound at all**, this is the one check you cannot
  satisfy, and no agent can attach one from inside a run. Pass
  `--enrichment-unavailable` and the absence is written with REDUCED rigour
  and the reason on the row. It is VERIFIED, not taken on trust: the run's
  own `connectors_baseline.json` — written by the preflight before any cell
  was worked — must show the families missing. A bound connector you simply
  did not ask, or a run with no baseline at all, is still refused, and says
  which. Everything else on this list still applies: the degraded path lifts
  the connector rung and nothing else. **Your brief names this flag when the
  baseline proves it, and only then** — a dispatch packet that does not
  mention `--enrichment-unavailable` is telling you the connectors are
  reachable and your searches should go through the relay, not that you may
  reach for the escape;
- the run's own register does not already NAME the cell (`engine.brief
  reuse --subcap <cell>` shows what a sibling lane bought — same-cell rows,
  same-capability rows, and up to two `proposed_from_other_categories`
  suggestions scored against the whole register). A proposal is a
  SUGGESTION: cite it with `engine.cli attach --e-id <E> --subcap <your own
  cell>`, which names an existing row without minting a duplicate, or
  dismiss it with `--decline --why '<reason>'`. Nothing is ever attached on
  your behalf — the semantic matcher was measured at 57.7% precision and
  that is the lesson the propose-never-attach rule carries;
- the ladder names its `direct` and `proxy` rungs with queries the
  Search_Log carries, and the proxy log says which proxy class was hunted.

Only `engine.cli absence` may close an empty cell; a notebook note, a
synthesis record or a hand-set `Absence_Claimed` does NOT (the validator's
rule 8 and `is_declared_absent` read the Provenance row the command writes).
Every evidence item MUST carry a specific, resolvable URL — the ledger
refuses a public row without one.

## Step 4: register into the workbook — through the engine only

There is ONE workbook and ONE writer. `engine.cli evidence` registers a
source (excerpt 50–500 verbatim chars, tier, date, the cells it supports);
**verbatim is checked, not asserted**: the span is compared against the text
`engine.cli fetch` cached for that URL, and a span the page does not carry is
refused `excerpt_not_verbatim` (whitespace and case are normalised, nothing
else). A URL nothing in this run has read is refused `excerpt_unverified`;
when the page genuinely cannot be fetched — a 403 WAF, a paywall, a
connector's own extract — `--unverified '<what stopped it>'` registers it and
records `UNVERIFIED: <reason>` on the row's Access_Status. Recorded, never
silent — and it never excuses a span a fetched page contradicts.
`engine.cli synthesise` closes an evidenced cell; `engine.cli absence`
closes an empty one. Column D (Score) is the assessment stage's, struck by
`engine.assessment score` and never here. The workbook's shape is
`engine/contract.py` (41 sheets, `SubCap_Name` seeded from the catalogue,
formatted; `python3 -m engine.cli columns` prints the pillar sheets' 33
columns) — never a layout recalled from a template or from this file, and
never a second workbook built beside the run (the retired
`populate_workbook.py` refuses for this reason).
