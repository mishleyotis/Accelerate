# The entity's shape decides the work

Every rule in this skill is written for an institution in general. The four things below
are true of a *particular* institution, and each of them changes what evidence exists,
which cells apply, who the peers are and what a good surface looks like. Establish them
before you produce anything, because getting one wrong does not produce a thin page — it
produces a confident page about the wrong institution, or about the sub-vertical rather
than the client.

```
sub-vertical   which cells this run may serve, and which regulator vocabulary applies
size tier      whether the peer cohort in the workbook is a cohort or a category error
ownership      what public evidence exists at all, and who the identity gate resolves against
brand shape    whether "another name" is another institution or the same one trading
```

They come from the manifest, confirmed against `01_evidence/entity_profile/`, and you
write them down at the vet step (`02-inputs/4-vetting.md`) so nothing downstream re-derives
them differently.

---

## 1 · Sub-vertical: the workbook scores more cells than the run serves

The scoring workbook's `P*_Subcap_Scoring` tabs carry every cell in the catalogue,
including the **T2 variant cells** minted for other sub-verticals. A credit-union run's
workbook holds insurance-carrier, RIA and insurance-broker variants because the workbook is
the catalogue, not the entity.

The serve layer scopes them out. Measured: a credit union served 765 cells, **59 of which
belonged to somebody else** — 25 insurance-carrier (`P1C1.3.IC1` Insurance Line Strategy),
19 RIA (`P2C4.6.RIA1` AUM-Based Segmentation), 15 insurance-broker (`P1C1.4.IB1`
Producer/Advisor Channel). They were scored, ingested and rendered on a member-owned
co-operative's heatmap.

A variant cell names its owner in its own id — the terminal segment is a sub-vertical code
and an ordinal:

```
P1C1.3.CU1    credit unions          P1C1.3.IC1    insurance carriers
P1C1.4.IB1    insurance brokers      P2C4.6.RIA1   RIAs / broker-dealers
P1C1.3.CL1    commercial lending     P1C1.3.RB1    retail banking
```

and the codes that name exactly one sub-vertical are
`RB · CU · CL · CIB · FC · AM · RIA · IC · IB`. A base cell (`P4C1.2.1`, numeric terminal
segment) serves for everyone. So does a **family or product code** — `BK` is the depository
family and applies to a credit union as much as to a bank, `WM` spans the wealth
sub-verticals, `PEN` is a product line and belongs to nobody. The rule is deliberately
one-sided: a cell is foreign only when its code names exactly one sub-vertical **and** that
sub-vertical is not this entity's. Over-excluding hides a score the assessment actually
made, which is the harder failure to see.

**What this changes for you.** Three things, and the third is the one that renders wrong:

- **Never cite a foreign variant cell.** Not in a finding, an insight, a gap row, a
  recommendation, a ceiling or a focus area. It resolves in the workbook and not on the
  page, so the chip opens onto nothing.
- **Do not write a synthesis for one.** The drawer will never open.
- **Compute coverage over the cells the run serves, not the cells the workbook scores.**
  O10 says its denominator must be the heatmap's cell set. On the run above that is 706,
  not 765, and a coverage figure computed over 765 is a contradiction a reader can find by
  counting.

Where a variant cell carries a score the assessment plainly meant — an insurance-broker
cell on a brokerage, say — it serves normally, and the same scoping is what makes it
*visible* rather than lost among nine sub-verticals' worth of variants.

## 2 · Size tier: the workbook's cohort is a claim, not a given

`Peer_Benchmarks` names the cohort, and the O1 prompt's peer discipline — same
sub-vertical, ±50% asset size, same regulator jurisdiction, no M&A distortion inside 24
months — is a rule about how a cohort should have been built. It is not a guarantee that
the one in front of you was.

The sub-vertical bands are wide. "Regional Banks $1B–$100B" is a hundredfold range: a
$3B community bank and a $89B multi-state institution are in the same band and are not in
the same cohort. A peer median drawn from the bottom of a band and rendered against an
entity at the top produces a delta arrow on every pillar that points confidently in a
direction no source supports.

So read the cohort's own sizes before you serve its median:

| What you find | What to do |
|---|---|
| Cohort sits inside ±50% of the entity | Serve the workbook's figures. Name the cohort on the surface, as O1 requires |
| Cohort spans the band but the entity sits at an edge | Recompute at the lower cohort size using the peer ladder's floor-of-three arithmetic, emit `peer_n`, and say in the framing that the basis shrank |
| Cohort is a different size class entirely | Do **not** serve the median. `peer_basis = cannot_estimate`, median null, and state the reason — a missing tick is honest and a wrong tick is not |
| No cohort at all for this sub-vertical | Section 3 below — this is usually an ownership fact, not an oversight |

This is a disclosure, not an adjustment. You never re-rank a peer figure and you never
average your way to a plausible one; the peer fallback ladder in
`01-start-here/2-evidence.md` is the only route, and its last rung is *stop*.

**Size also moves the expectation, never the evidence.** A $6B co-operative is not behind
for having no transformation office; a $89B public company with none is a finding. The
R-Layer's domain test is where that judgement belongs — see `04-craft/1-reasoning.md` —
and it applies to the ceiling, not to the score.

## 3 · Ownership: it decides what public evidence exists at all

This is the axis the skill's enrichment ladders quietly assume away. Every "search the
latest 10-Q", "read the proxy statement", "check Section 16" rung presumes a filer.

| Shape | What exists | What does not | Where the series comes from |
|---|---|---|---|
| **SEC registrant** | 10-K/10-Q with XBRL, 8-K, DEF 14A, Section 16, earnings-call transcripts, segment disclosure | — | The filings, at period-end consolidated basis |
| **Insured depository, not listed** | The regulator's own call report — quarterly, dated, machine-readable, T1 — plus the entity's annual report and member/shareholder meeting materials | Proxy statements, insider filings, transcripts | The call report. NCUA 5300 for a credit union; FFIEC/UBPR for a bank |
| **Private, employee-owned** | The entity's own site, acquisition press releases, industry ranking tables, an ESOP's Form 5500, state licence records, rating-agency reports where it carries debt | Filings of any kind, a share price, an audited public series | The **industry ranking table** — the trade press's annual broker or adviser rankings carry dated revenue figures for private firms, year on year, from a third party |
| **Mutual / co-operative** | Regulatory filings and member disclosures | Equity market signals; "investor relations" as a route | The regulator's filings |

Two consequences worth stating plainly.

**Absence of a filing is not absence of a figure, and it is not a thin card.** A private
brokerage with no filings still has a defensible multi-year revenue series if the ranking
tables carry it, and an ESOP's Form 5500 is a dated public document with headcount and plan
assets in it. Run those rungs before you set `verified_sparse` — the absence protocol's
rule that you may not say no until a documented ladder has failed applies with more force
here, not less, because the obvious ladder does not exist.

**Ownership is an identity fact, and self-description is where it goes wrong.** An entity
that describes itself as "100% employee-owned" may have completed a recapitalisation that
brought outside minority holders in while employees kept the majority — both statements can
be live on the same website, and the dated transaction outranks the undated boilerplate.
Resolve it the way the contradiction classes require: the registry or the dated
announcement wins, the disagreement is recorded, and **the resolution is itself a finding**
— a change of control inside the assessment window is a why-now signal, an O8 context and
a C5 row at once.

## 4 · Brand shape: another name is usually not another institution

Assertion 1 of the identity gate resolves trading names, and on a single-brand entity that
is a formality. On a multi-brand one it is the whole job.

A holding structure that operates seven separately branded banking segments under **one
national charter** has seven brands, seven websites, seven app-store listings, seven
Glassdoor pages and one legal entity. Treated naively the gate produces two opposite
failures at once: evidence about a brand is rejected as foreign, and evidence about a
same-named *unrelated* institution in another state is accepted because the brand name
matched.

The resolution is that the identity gate asks whether the **document is about this legal
entity**, and a registered trading name of that entity is:

- **Citable, and labelled.** Name the brand in the excerpt's context and the item's
  source, so a reader can see the estate the evidence came from. A finding about one
  brand's channel is evidence about that brand's channel; it is enterprise evidence only
  where the source says so.
- **Never aggregable by arithmetic.** Four brand app ratings are four sources. An average
  of them is a number in no source, and the never-average rule applies exactly as it does
  to two disagreeing figures. Render them as separate rated lines with their brands named,
  or render the one the enterprise publishes.
- **Not a licence to widen the search silently.** An enforcement or complaint sweep is run
  under the legal name *and* under every brand — a search you did not run under the brand
  is a rung of the ladder you did not attempt, and the C3 absence record must say which
  names were searched.

The mirror case: a **counterparty's** regulator appearing in a document about this entity
is not contamination. A credit union acquiring a bank generates FDIC and state banking
department approval notices; those documents are about this entity's transaction, and they
are the best-dated evidence it exists. Cite them, and let them touch C5, C1 and O3. What
they may never do is set `primary_regulator` — the prudential regulator comes from the
registry that charters *this* entity, and an FDIC chip on a credit union's regulatory
standing card is still the identity error C3 quarantines for.

---

## Scarcity and abundance fail differently

Almost every measured defect in this corpus is a scarcity defect: two timeline events, one
sentiment source, an empty leadership panel, 9% of cells carrying a synthesis. The
instruction that follows from them is *search harder*, and for most entities it is right.

For a large disclosing institution it is not the binding constraint. A public company
generates a dated, citable event most weeks; four earnings calls a year each yield
executive quotes on technology; the newsroom carries dozens of items. Search returns three
hundred results and the surfaces fill with true, cited, dated, irrelevant content — which
reads as thorough and argues nothing.

Abundance is a **selection** problem, and selection needs a stated key:

| Surface | Select by | Not by |
|---|---|---|
| C1 timeline | Bearing on an assessed capability, then inflection — the events that changed the trajectory | Recency, or completeness |
| O3 why-now | The event whose window is dated and whose consequence names a cell | The most recent news |
| O12 thought leadership | The statement that corroborates, contradicts or extends a finding | Every quarter's transcript |
| C5 acquisitions | Transactions with an integration consequence on a named cell | Every deal announced |
| H2 cell evidence | Section 5 below | Whatever the document mined into |

State the key on the surface where it renders, the same way O6 states its ranking basis. A
reader who can see *why these six of forty* trusts the six; a reader who cannot assumes
they are the only six you found.

## 5 · Every scored cell owes the reader something

Measured on a real run: `cell_evidence` rows existed for **69 of 765 served cells**. The
grid is clickable on every cell, so 90% of clicks opened a drawer that said nothing — and
the same run held hundreds of linked evidence rows, so this was a linking and coverage
failure, not an evidence one.

Broad cell coverage is the default, not an achievement. `03-pages/1-heatmap.md` carries the
method — three grades of synthesis, the order the work is done in, and what `linking_stats`
must report — and it is worth reading before you plan the run rather than when you reach
H2, because the ordering decision is made early and cannot be recovered late.

---

## The three shapes, worked

Reconnaissance current to August 2026, and stated as what a producer would find, not as
assessment findings.

**A $6.7B state-chartered credit union in Washington, ~320,000 members.** Repeatable
territory: NCUA 5300 call-report data gives a clean multi-year T1 series; the peer cohort is
well populated with same-state and same-size co-operatives; the sub-vertical's cells are
`CU` variants plus the `BK` depository family. Two things that are not repeatable from the
last credit union: a pending acquisition of a **bank** brings a second regulator's approval
trail into the evidence set (section 4's counterparty case), and a **fintech-branded digital
offering launched with a named platform partner** is a CLAIMED-to-CONFIRMED question on the
tech register and a channel event on the timeline — not the core, and the register must not
imply it replaced one. Where the prior run in this sub-vertical scored the same cells from
the same vendor landscape, apply the cohort test in `04-craft/1-reasoning.md`: a sentence
true of every credit union running that core is a fact about the vendor, and it belongs in
H8 or nowhere.

**A private, employee-owned insurance brokerage, ~3,000 associates across 23 states,
serial acquirer.** The thinnest of the three on the routes this skill assumes, and the
richest on routes it did not name. No filings, so O8's ladder terminates at rung one unless
you take it to the ranking tables and Form 5500; O2's SV7 must-present set (premium placed,
commission revenue, producer count, acquisitions) is mostly undisclosed, and the honest
answer is a quarantined or absent field with its route recorded, never a modelled estimate
rendered as a figure. Its regulators are state departments of insurance — licence and
agency records, retrievable per state, plus NAIC's producer database — and any affiliated
adviser or broker-dealer brings SEC Form ADV or FINRA BrokerCheck, which are dated public
documents about the same group. Peers are the independent brokerages, none of which files
either, so a peer *median* may be structurally unavailable while a peer *ranking* is
published annually: that is rung 4 of the peer ladder, a proxy that must disclose itself,
not rung 1. And a dated change of control inside the window is the first thing to reconcile
against the entity's own ownership language.

**A ~$89B national association, NYSE-listed, seven branded segments across eleven western
states.** Every filing route is open, which moves the failure mode from scarcity to
selection everywhere. Watch four things specifically. The **peer cohort** must be checked
against the size tier before its median renders — this entity sits at the ceiling of its
band. The **financial series' basis** must be period-end consolidated total assets, stated
per point and identical across points: a 10-K also states average assets, segment assets and
holding-level figures, and mixing them produces a trend that is an artefact of the
definition. The **regulator** is the prudential one from the chartering registry; the SEC is
a disclosure regulator and never `primary_regulator` for a bank. And the **brand shape**
governs sentiment, complaints, enforcement sweeps and any technographic scan — a scan of one
brand's domain is evidence about that brand's estate, and the enterprise's technology and
operations leadership is a different question from an affiliate president. Where a run
coincides with a named technology-leadership change, the roster's recency rule does the work
it exists for: verify every name against the current leadership page and mark the departure,
because a stale executive name is worse than a gap.
