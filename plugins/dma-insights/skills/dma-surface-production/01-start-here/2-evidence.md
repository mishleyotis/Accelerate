# Evidence, citation and the peer ladder

## Two legal origins, and only two

**Package evidence** is already in the store with an entity, a run, a tier and a URL. Cite
it; never create it.

**Enrichment** is anything found outside the package. Register it first, cite it second. The
server allocates the id and computes the rank score. Registration is idempotent by content,
so one annual report cited by six cards produces one row.

## Registering an excerpt: re-extract, never retype

The excerpt is verified against the **fetched artefact**, fail-closed, at registration. What
the checker actually does, so you neither over- nor under-correct:

- Whitespace runs — including newlines and paragraph breaks — collapse to one space on BOTH
  sides, and the comparison is case-insensitive. **So re-flowing whitespace is safe.** You do
  not need to reproduce the source's line breaks.
- After that normalisation, your span must appear **contiguously** in the artefact. That is
  the whole test, and it is where hand-repair fails.
- The span must be **50–500 characters**.
- No reachable URL → `url_unreachable`, and nothing is registered.
- A `FACT` with no `source_url` is **automatically downgraded to `INFERENCE`** and told to you
  in `adjustments`. That is not an error; it is the system refusing to let an untraceable
  claim keep a fact's label.

Measured against production, registering one real source: four attempts refused before one
was accepted.

| Attempt | Verdict |
|---|---|
| Two passages joined together | `excerpt_not_verbatim` — the artefact has words between them, so the joined span is contiguous nowhere |
| A hand-written summary of the source | `excerpt_not_verbatim` — the words are not there |
| A Glassdoor URL | `url_unreachable` — the site returns 403 to automated fetch |
| A 123-character literal substring of the fetched page | **accepted**; ERS computed server-side |

The rule that follows: **take the span exactly as the fetched artefact holds it, in one
piece.** Reformatting is fine; joining, trimming a clause, or supplying a missing subject is
not. If the passage you want spans an intervening caption or heading, take the half that
carries the claim rather than stitching.

## The excerpt and the `source_url` are one claim, not two fields

**An excerpt is a verbatim span of the document at `source_url`.** Not of a document that
says the same thing, not of the page you originally read before switching to a URL that
fetched more cleanly, not of the entity's newsroom when the URL points at a directory listing
that mentions the entity. The pairing IS the claim: it says "open this and you will find
these words".

Registering a true claim under a URL that does not contain it is **fabrication by
construction**, and the truth of the claim is not a defence. A reader who clicks the chip
lands on a page that does not say what the card says it says, and every other citation on the
run becomes a thing they have to check.

Measured on a promoted run, four rows out of 178:

| Rows | Excerpt | `source_url` | What it is |
|---|---|---|---|
| `E-CC-001` | BCU's own newsroom prose about a named executive | `ncuso.org/credit-union/68187/` — a third-party directory listing | The claim is true and the URL does not contain it. **Cited nine times on the heatmap** |
| `E-CC-002` | BCU's own merger announcement headline | `bbb.org/.../baxter-credit-union-...` — a Better Business Bureau profile | Same |
| `E-CC-003`, `E-CC-004` | the same two spans | the `bcu.org` newsroom pages that actually carry them | The correct rows, registered separately |

The correct rows existed the whole time. Two documents were read, four rows were minted, and
the pairing crossed over. That is the shape this defect takes: not a fabricated quote, but a
correct quote under the wrong address, produced by holding two sources open at once.

Three rules follow:

1. **Register from the artefact you fetched, in the same step you fetched it.** One source,
   one registration, before moving to the next. Registration is idempotent by content, so
   there is no cost to registering as you go and every cost to batching.
2. **The tool that found the source is never the source.** An Explorium, Clay or BuiltWith
   endpoint in `source_url` means the excerpt was read somewhere else — cite there. Two rows
   on the run above carried an Indeed rating and an RPA stack under
   `vibeprospecting.explorium.ai`, and one carried the literal string `multiple`.
3. **A search-results page is not a document.** `google.com/search?q=…` contains no span you
   can quote and no claim you can cite. A negative search result is a rung in the absence
   ladder (`01-start-here/4-absence-protocol.md`), recorded as `sources_searched` — never an
   evidence row.

`scripts/check_evidence.py` reads a `get_evidence` snapshot and refuses the mechanical shapes
of this. Know what it can and cannot do:

**It catches** — one excerpt registered under two different hosts (the reported four rows fall
out of this immediately, and no verbatim span is a verbatim span of two different documents
without you saying so); a `source_url` that is not a fetchable document URL; a search-results
page; an excerpt with no URL or no publisher name.

**It cannot catch** a single row whose excerpt simply is not on its page — nothing short of
fetching the URL can, and the connector does exactly that at `register_evidence`, which is
why registering as you go is the actual control.

`--review` also prints the publisher named in `source_name` beside the URL's host where they
share no token. **That list is a reading aid and explicitly not a refusal**, because the
comparison is wrong far more often than it is right. On the run measured here it questioned
27 rows and 2 were the crossed pairings: a wire service carrying a vendor's release
(`prnewswire.com` for "Jack Henry Press Release"), an archive (`web.archive.org`), a
regulator's own domain (`consumerfinance.gov` for "CFPB") and a rebrand (`scworld.com` for
"SC Media") accounted for 12 more, and the remaining 13 were rows whose `source_name` was an
internal label — "P3C4 Carry-Forward Consolidation", "MuleSoft Gap Confirmation" — rather
than a publisher at all. That last group is a real defect of its own: `source_name` is what
the evidence drawer prints above the quote, so it is the **publisher and the document**, not
your filing note.

## A source that blocks retrieval cannot be cited at all

Glassdoor, Indeed, ZipRecruiter and the Glassdoor mirrors all return 403 to automated
fetches. A figure whose only source is one of those is **unciteable** — there is no id to
carry it.

That leaves exactly three honest moves, and inventing an id is not among them:

1. Find the same figure somewhere retrievable (an aggregator that republishes it with
   attribution, a filing, a press release) and cite THAT.
2. Carry it as an explicit inference with its route named — what you saw, where, and that the
   source could not be fetched.
3. Omit the figure, and record the attempt in `sources_searched` as a rung that did not
   resolve.

A blocked source belongs in the ladder, never in an `e_ids` list, and never behind a number
presented as cited. `01-start-here/4-absence-protocol.md` owns the ladder's shape.

### Three refusal classes, and they are not the same finding

The verdict word matters, because each class has a different repair and a client reading
the ladder can tell them apart.

| Class | What happened | What the ladder says |
|---|---|---|
| **Blocked** | The host refuses automated retrieval outright — 403 to every fetch. Measured: `glassdoor.com`, `indeed.com`, `ziprecruiter.com`, `trustpilot.com`, `creditunionsonline.com`, `depositaccounts.com`, `cutimes.com`, `bbb.org` profile pages | the source exists and cannot be cited; name the status code |
| **Gone** | The URL 404s or the host no longer serves that path. Measured: machine-scan consoles (`vibeprospecting.explorium.ai`), and an institution's own press archive after a site rebuild | there is nothing behind this id; retire it rather than re-point it |
| **Reachable but the span is not in the artefact** | The fetch succeeds and the number you can see in a browser is **not** in the bytes the verifier receives | the source was reached and the figure could not be verified — say which half failed |

The third class is the one that surprises people, so it gets a name. **The excerpt is
verified against the artefact the SERVER fetches, not against the page you looked at.**
Those differ whenever a host varies its response by client, region or experiment. Measured
on Google Play: the same product page yielded the app's identity block
(`"@type":"SoftwareApplication","name":"BCU Mobile Banking"…`) to both fetchers, and yielded
`aggregateRating` to a local fetch and **not** to the connector's. So the app is citeable
and its star rating is not — a distinction worth carrying, because it lets you register the
identity, keep the rating out of the bar, and record precisely why.

Two habits follow, and they cost one round trip instead of four:

- **Pre-flight the span** against a fetch of your own before you call `register_evidence`,
  then read a refusal as information about the server's artefact rather than about your
  span. `excerpt_not_verbatim` after a clean local match means the two artefacts differ.
- **Prefer the stable half of a page.** Identity blocks, JSON-LD `@type`/`name`/`url`,
  regulator field names and body prose survive re-fetches. Live counters, star averages
  carried to fifteen decimal places, "posted 3 hours ago" and anything a CDN personalises
  do not.

A machine-format span is legitimate evidence when that is how the source states the fact —
a JSON API response is a document. Registered on live runs: `"averageUserRating":4.865…`
from the iTunes lookup API, and NCUA's locator payload. Prefer prose where the source
offers prose; do not manufacture prose where it does not.

## Where a multi-year financial series actually comes from

A financial trajectory is the surface most often shipped thin, and the failure has one
shape: the producer takes the two or three asset figures that happen to appear in press
boilerplate and calls the line a trend. Press boilerplate lags, rounds ("over $6 billion")
and is dated by the release rather than by the reporting period. **Three rounded points from
three press releases is not a trajectory; it is the same number three times.**

Regulators publish the series. Find the regulator's own periodic filing before you search
the news:

| Institution | Series | Route |
|---|---|---|
| Credit union | Quarterly 5300 Call Report | NCUA — resolve the **charter number** first, then read Account `010` (TOTAL ASSETS) from `FS220.txt` inside each period's quarterly file |
| Bank / thrift | Quarterly Call Report | FFIEC / FDIC, by RSSD or cert |
| Insurer | Annual statement | NAIC, by NAIC company code |

**The credit-union route, in full, because it is now proven:**

1. **Resolve the charter.** `https://mapping.ncua.gov/api/CreditUnionDetails/GetCreditUnionDetails/<charter>`
   returns JSON — legal name, charter type, status, state, address, CEO, website, assets and
   members for the **latest cycle**, plus `callReportCycleDates` listing every cycle NCUA
   holds. That response is the identity gate and the current point in one fetch, and it is
   reachable with a browser-shaped UA. It takes **no cycle parameter** — asking for an older
   one returns the latest anyway, which is a silent wrong answer if you do not check.
2. **Take the history from the quarterly files**, listed at
   `ncua.gov/analysis/credit-union-corporate-call-report-data/quarterly-data`, one ZIP per
   period (`call-report-data-YYYY-MM.zip`). Inside, `FS220.txt` is keyed by `CU_NUMBER`;
   `ACCT_010` is total assets. Every December file gives one year-end point, so five years is
   five files.
3. **Cite the period, not the dataset in general.** The page carries NCUA's own per-period
   link and label, so each point can carry its own citation naming its own file — a reader
   downloads that file and finds the row. One shared "we used NCUA data" citation makes five
   points look sourced while none of them is checkable.

Two traps this route has already sprung:

- **The Financial Performance Report is not GET-addressable.** `fpr.ncua.gov` is a session
  and form-POST application; its HTML is unreachable to the excerpt verifier, and its tables
  put the label and the number in different cells, so a "verbatim" row lifted from it is a
  reconstruction. The numbers are right and the citation is not.
- **The latest cycle is not December.** NCUA publishes quarterly; at any moment the newest
  regulator reading is a March, June or September cycle sitting above the last year-end.
  That is not a contradiction with the year-end series — it is a later date, and it belongs
  on the card as its own point with its own period label.

## Dating: what to establish, and what to record when you cannot

Every registered row and every rendered item carries a date or carries the reason it does
not. A bare null is refused, because the surface cannot tell "nobody looked" from "somebody
looked and it is not stated", and those are different facts about the research.

Where the date is, in the order worth trying:

1. **The document's own machine metadata** — `datePublished` / `article:published_time` in
   JSON-LD or meta tags, `<time datetime=…>`. Present far more often than the visible page
   suggests, and it is the source's own claim rather than yours.
2. **The reporting period**, for anything filed: a call report cycle, a fiscal year end. Use
   the period the data describes, not the day the regulator published it — that makes an old
   figure band as old, which is the honest reading.
3. **The identifier**, where the platform encodes it. A LinkedIn activity id is a millisecond
   timestamp in its top bits (`id >> 22`), which dates a post whose page shows only "2mo".
4. **A stated month with no day** — "Updated March 2026". Register the first of the month and
   say in the surrounding prose that the source states the month only. Precision you did not
   get is not precision you may imply.
5. **Nothing.** Then `published_date` stays null, the band stays `UNVERIFIED`, and the item
   carries the rung that says the date was searched for — never a band computed from no date.

An undated source is still usable evidence. What it may not do is render as current.

**Where the rung goes matters, and it is not only on the item.** The connector accepts an
absence rung on the item (`opened_on_basis`, `date_basis`, a `sources_searched` ladder) and
that satisfies the dating gate. But the promotion writers explode list items into columns,
so a key the serving DDL does not carry is written nowhere and the client never sees it —
the row still renders with an empty date and no explanation beside it. Measured on a live
run: `opened_on_basis` on two register rows and `announced_on` on an announced merger all
passed validation and none of the three reached the served payload.

So put the rung in **both** places: on the item, where the gate reads it, and in the
section's `r_layer.probes_run` or `empty_state.sources_searched`, which serve whole. One
sentence naming what was searched and what it established is enough, and it is the half the
reader actually gets.

## The quality ladder

| Tier | Type | Weight | Ceiling |
|---|---|---|---|
| T1 | Regulatory and audited sources — and machine technographic scans | 1.0 | L5 |
| T2 | Official disclosures; structured internal notes | 0.85 | L5 |
| T3 | Third-party analysis — analyst, app ratings, trade press | 0.7 | L4 |
| T4 | Internal unvalidated narrative | 0.55 | L2.5 |
| T5 | Marketing and claims — requires corroboration | 0.3 | L2 |

Two rules that cost real score accuracy:

- **A machine technographic scan is T1, never T4.** Filing it at T4 caps the capability at
  L2.5 and silently suppresses the score. It was the commonest misclassification in the
  corpus.
- **There is no T6, T7 or T8.** A separate eight-row source-type table renders the weakest
  tier as something that reads stronger than it is, inverting trust exactly where the
  evidence is weakest.

## Recency — one vocabulary

| Age | Band | Recency score |
|---|---|---|
| ≤ 12 months | CURRENT | 5.0 |
| 12–24 months | RECENT | 4.0 |
| 24–36 months | DATED | 3.0 |
| 36–48 months | STALE | 2.0 |
| 48 months+ | ARCHIVAL | 1.0 |
| no date | UNVERIFIED | 1.0 |

An undated item is never rendered as current. Age is computed against the run's pinned
reference date, or it is null. Never a sentinel.

### The whole ladder hangs from `reference_date`

`runs.completed_at` becomes every evidence row's `reference_date`. Without it the generated
`age_months` is null and **every** item bands `UNVERIFIED` — regardless of how many of them
carry a publication date.

Measured on a real run: **120 served items, 45 of them carrying a published date, and all 120
banded UNVERIFIED.** A `FACT` chip then rendered beside an "unverified" label, which a reader
correctly reads as a contradiction.

The date is usually there twice. Check both before concluding a run has none:

- the manifest — `assessment.completed_at`, `assessment_date`, `completed_at`,
  `generated_at`, `execution_timestamp`, `last_updated`
- **the run's own request id.** The corpus names every run
  `DMA-ASM-<ENTITY>-<YYYYMMDD>-<seq>`, so `DMA-ASM-BCU-20260330-0001` states 2026-03-30 as
  plainly as a manifest field would. The worker reads it as a last resort — it is read, not
  guessed.

If a run genuinely has no date, say so on the surface. Never present an item as current when
its band is `UNVERIFIED`.

## The rank score

```
ERS = (0.35 × Tier) + (0.25 × Recency) + (0.20 × Specificity) + (0.20 × Corroboration)

Each factor is scored 1.0–5.0, so the result is bounded 1.0–5.0.
High ≥ 3.5    Medium 2.5–3.5    Low < 2.5

Corroboration  3+ independent / 2 independent / single T1–T2 / single T3 / single T4–T5
               "Independent" means different ORIGINS. An annual report and an investor
               deck from the same institution are ONE source.
```

The server computes this at registration. Never send it; it is ignored.

## The peer fallback ladder

**First, the grain.** The scoring workbook's `Peer_Benchmarks` tab states per-CATEGORY scores
for named peers plus Median / P25 / P75. Measured: **0 of 765 cell rows carry a peer median**,
and that is faithful — the workbook does not state one at cell grain.

So at pillar and category grain you serve the workbook's figure. **At cell grain the app
inherits the category median and labels it a proxy** — you do not restate a per-cell peer
figure, because no source holds one. Read the cohort from the workbook rather than assuming
it; the peers differ by sub-vertical (one credit-union run's tab named CEFCU, Alliant,
Consumers, GreenState and Lake Michigan).

Where the peer table lacks a figure, apply in strict order and stop at the first rung that
yields one.

| # | Rung | Procedure | Records |
|---|---|---|---|
| 1 | Peer table figure | peer_comparison_table.csv carries the cell | `basis = table` |
| 2 | Recompute at lower cohort size | Drop the peer lacking the figure and re-take the median. Floor of three: N=5 → sorted[2]; N=4 → mean of sorted[1..2]; N=3 → sorted[1]. | `basis = recomputed, peer_n records the size actually used` |
| 3 | Adjacency inference | Infer from a neighbouring sub-capability in the same category. | `basis = inferred, labelled INFERENCE with one clause of reasoning` |
| 4 | Proxy ceiling | A signal that caps rather than estimates — e.g. a specialist-headcount ratio below 5% caps its category, negative-dominant review sentiment caps at mid-scale. Lowest cap wins. | `basis = inferred, proxy_disclosure carries the literal phrase 'peer proxy'` |
| 5 | Stop | Print 'Cannot reliably estimate'. | `basis = cannot_estimate, peer_median stays NULL` |

**Never impute a value into the cell.** A proxied figure must disclose itself with the
literal phrase *peer proxy* — a governance check greps for it — and must never claim
identical methodology. A proxy that reads as a measurement is the peer-fabrication failure
this ladder exists to prevent.

## Linking

An item supports a cell when it **speaks to that capability**, not when it was found while
researching the category. The commonest cause of over-linking is one category-level search
mapped identically onto five sub-capabilities.

A cell whose every drawer is empty is a **linking** failure, not an evidence gap. Diagnose
before enriching — enriching a linker bug adds evidence that also will not render.

### Registration without linkage is an incomplete registration

`register_evidence` takes `linked_subcap_ids` on the item, and the call is idempotent by
content: re-registering the same url + claim + span returns the same id and **accumulates**
that call's cell links. So linkage is never a separate errand — it is the second half of
registering the source, and a row that lands without it has been half-registered.

**An unlinked citation is worse than no citation at all.** An uncited sentence asks nothing
of the reader. A citation invites them to drill in, and when the row behind it links to
nothing the drawer answers *"no cell links served for this item"* — an orphan, under a real
client's name, reached by following exactly the affordance you gave them. Measured on a
promoted run: **178 served evidence rows, 72 with no cell link, 28 of those cited by a
section.** The row the client actually clicked was a Great Place To Work profile behind an
employee sentiment tile.

**ET-07** now refuses this at submit. A cited id resolves to a row carrying at least one
cell link, or the citation is stated as supporting none.

### The honest exception, and how to state it

Some sources genuinely support no capability cell, and forcing one onto them is the
**misattribution** failure from the table below — the quietest of the four, because nothing
breaks. So say so instead. Two ways, and both reach the reader:

1. **By the grain of the section citing it.** A section that does not reason at cell grain
   carries these sources as a matter of course, and ET-07 exempts it by name:
   `overview.firmographics`, `overview.financial_series`, `overview.leadership`,
   `overview.thought_leadership`, `overview.evidence_coverage`,
   `context.regulatory_standing`, `heatmap.evidence_age`. The exemption belongs to the
   section, not to the source: the same registry entry cited by the timeline owes a cell,
   because the timeline is making a claim about the capability history.
2. **By naming the id in prose the section serves whole** — a rung in
   `r_layer.probes_run` or in `empty_state.sources_searched` that names the `e_id` and says
   why it links to none. A general sentence about linkage does not count; the rung has to
   name the id, or one boilerplate paragraph would excuse every orphan on the page.

The classes that legitimately link to nothing, from the same run:

| Class | Example | Why it links to no cell |
|---|---|---|
| Entity identity / firmographic | the NCUSO registry entry: charter number, 46 branches, 369,985 members | the shape of the institution, not a capability |
| Regulator period filing | one NCUA quarterly call-report file per year-end | a financial point on the trajectory card |
| Regulator perimeter | the CFPB's own statement of which institutions it supervises | a fact about the regulator's scope |
| Regulator database search | the complaint database's hit count for this entity | a recorded search, not a measure of capability |
| Peer comparator | four other credit unions' app-store ratings | the benchmark this entity is read against, not evidence about it |
| Bureau grade | a BBB letter grade | composite, no scale, no sample — it draws no bar and caps no cell |

Everything outside those classes owes a cell. When you are unsure, ask what a reader who
clicks the chip is entitled to see: if the answer is "which part of the assessment this
bears on", link it; if the answer is "who this institution is", state the class.

## Four failure modes, ordered by damage

| Failure | What the client sees | Caught by |
|---|---|---|
| **Fabricated** — no such row | A chip that opens nothing | Pattern and existence checks, fail-closed |
| **Foreign** — a real row, another entity | A competitor's data on their page | Cohort filter plus the identity gate. **Stop production.** |
| **Misattributed** — real row, wrong cell | Evidence that does not support the claim | Linker thresholds. The quietest failure: nothing breaks |
| **Unverifiable excerpt** | A quote not in the source | Verified against the fetched artefact at registration |

## When you cannot establish an id

In order, stopping at the first that applies:

1. **Enrich.** Find a real source, register it, cite the returned id. This is the answer
   most of the time and the highest-value work on any surface.
2. **Drop the claim, keep the surface.** A shorter honest card beats a complete unfounded one.
3. **Emit the empty state with what was searched.** Absence with a recorded search is a
   finding. Absence with no record is a research failure wearing a finding's clothes.

Never keep the claim and remove the citation. An uncited claim is excluded by the serve
layer anyway, so it is wasted work as well as wrong.
