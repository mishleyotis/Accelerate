# Clay enrichment

Clay is how this skill closes evidence gaps that public search cannot. It runs during
synthesis, before you write the surfaces that depend on it, and its output becomes registered
evidence like any other source.

## What Clay is authoritative for

| Surface | Clay call | Data point |
|---|---|---|
| **O7 Leadership** | `find-and-enrich-contacts-at-company` | base contact rows, filtered by title |
| **O12 Thought leadership** | `add-contact-data-points` | `Find Thought Leadership` |
| **O2 Firmographics** | `add-company-data-points` | `Annual Revenue`, `Headcount Growth` |
| **T1 Tech stack** | `add-company-data-points` | `Tech Stack` — this is the machine technographic scan |
| **O3 Why-now signals** | `add-company-data-points` | `Recent News`, `Latest Funding`, `Open Jobs` |
| **C5 Acquisitions** | `add-company-data-points` | `Recent News` + Custom "acquisitions and integrations" |
| **P1 Platform readiness** | `add-company-data-points` | `Open Jobs` — hiring is the cheapest capability signal |
| **O7 tenure and trajectory** | `add-contact-data-points` | `Summarize Work History` |

## The tier a Clay output lands at

Clay is not one tier. The tier follows the underlying source, and getting this wrong changes
the score.

| Data point | Tier | Why |
|---|---|---|
| `Tech Stack` | **T1** | A machine technographic scan is T1, never T4. Filing it at T4 caps the capability at L2.5 and silently suppresses the score — the commonest misclassification in the corpus. |
| `Annual Revenue`, `Latest Funding` | T1–T2 **when a filing is behind it** | Filings and disclosures. For an entity that files nothing, this value is usually **modelled** and has no traceable source — that is an inference, not a T1 fact, and the tier follows the source as it does everywhere else |
| `Open Jobs` | T2–T3 | The posting is first-party; the aggregator is not |
| `Find Thought Leadership` | T2–T3 | T2 for a first-party publication or named conference; T3 for trade press |
| `Recent News` | T3 | Third-party analysis |
| `Summarize Work History` | T3 | Profile-derived |
| Any `Custom` data point | Tier of whatever it returns — **read the source before assigning** | |

## The enrichment budget

Clay's own tool contract says never to add data points unless explicitly asked, because
enrichments cost credits. A DMA synthesis **is** that explicit request — but it is a budget,
not a blank cheque.

**Standing authorisation for one run:**

```
1  company enrichment call          Tech Stack · Annual Revenue · Headcount Growth
                                    Recent News · Open Jobs · Latest Funding
1  leadership contact search        C-suite and technology leadership, filtered
1  contact enrichment call          Find Thought Leadership · Summarize Work History
0-2 targeted Custom data points     ONLY against a named gap you have already tried to
                                    close by search
```

**Outside that budget, ask.** Enriching every contact "to be helpful" is exactly what the
tool contract warns against, and a DMA needs the leadership tier, not the org chart.

## The call sequence

```
STEP 1 — RESOLVE THE COMPANY
  find-and-enrich-company(companyIdentifier=<domain from entity_profile>)
  → taskId
  The domain comes from 01_evidence/entity_profile/, never from a guess. A wrong domain
  produces a real company's data attached to the wrong entity — the contamination class
  the identity gate exists to catch.

  **Where the entity has more than one domain, which one you resolve on changes the
  answer.** Many institutions run a corporate domain and one or more brand domains, and a
  group may run a separate site for its holding entity and its operating one. Resolve on the
  domain the entity's own registry record or filings use, check the returned legal name
  against it, and record the others as aliases rather than resolving each in turn.

  This matters most for the technographic scan, which reads the surfaces it can reach. A
  scan of a brand domain is evidence about **that brand's** estate — its marketing stack,
  its login subdomain, its app bundle — and on a multi-brand institution that is not the
  enterprise's stack. Register the finding with the brand named, and never let a
  brand-domain scan become the enterprise's register row without a second source saying so.

STEP 2 — COMPANY DATA POINTS, ONE CALL
  add-company-data-points(taskId, dataPoints=[
    {type:"Tech Stack"}, {type:"Annual Revenue"}, {type:"Headcount Growth"},
    {type:"Recent News"}, {type:"Open Jobs"}, {type:"Latest Funding"}])

STEP 3 — LEADERSHIP
  find-and-enrich-contacts-at-company(
    companyIdentifier=<domain>,
    contactFilters={ job_title_keywords:[
        "Chief Executive","Chief Information","Chief Technology","Chief Operating",
        "Chief Risk","Chief Data","Chief Digital","Head of Technology",
        "Head of Digital","EVP","SVP Technology"],
      job_title_exclude_keywords:["Intern","Assistant","Coordinator"] })
  → taskId2
  Keep compound titles as ONE string. "VP Finance" is one keyword, not "VP" and "Finance".

STEP 4 — CONTACT DATA POINTS
  add-contact-data-points(taskId2, dataPoints=[
    {type:"Find Thought Leadership"}, {type:"Summarize Work History"}])

STEP 5 — POLL, DO NOT CONCLUDE
  get-task-context(taskId) and get-task-context(taskId2)
  Enrichment is ASYNC. The initial response carries base fields only.
```

## The rule that matters most

> **Never record an absence from a Clay call without first calling `get-task-context`.**

Clay's own contract states this, and it is the same discipline as the absence protocol: the
search response is not the result. An empty leadership panel written before the poll
completed is not a verified absence — it is an unfinished call rendered as a finding.

Poll until values resolve. If they are still in flight, wait and retry rather than writing
the empty state.

## Registering Clay output as evidence

Clay findings are enrichment. They are registered, not cited directly:

```
register_evidence(run_id, item={
  source_name : "<the underlying source Clay surfaced, not 'Clay'>",
  source_url  : "<the source URL Clay returned>",
  excerpt     : "<verbatim 50-500 chars from that source>",
  tier        : <per the table above>,
  claim_type  : "FACT" | "INFERENCE",
  published_date : <the source's date, not the enrichment date>,
  linked_subcap_ids : [...] })
```

**Cite the source, not the tool.** "Clay reports 340 employees" is not evidence; the filing
Clay surfaced is. If Clay returns a value with no traceable source, it is an inference and is
labelled one — it does not become a fact by arriving through an API.

**The identity gate applies to every Clay row.** Clay resolves by domain, and a holding
company, a subsidiary and a same-named institution in another market all have domains. Check
the legal name, the regulator and the order of magnitude before you use a figure.

A source that blocks automated retrieval cannot be registered at all, whatever Clay returned
from it — Glassdoor, Indeed and ZipRecruiter all 403, so `register_evidence` gets
`url_unreachable`. Such a value is an inference with its route named, or it is omitted. See
`01-start-here/2-evidence.md`.

## The contact route lands in real columns, and it lands NOW

Contact output is persisted per person on the leadership roster:
`roster[*].email`, `.linkedin_url`, `.phone`, `.enriched_at`, `.enrichment_basis`.

**The app makes no third-party call while serving** (invariant 1). The AE's click reads a
stored row in milliseconds because you established the route during synthesis. There is no
lazy fetch and no queue that fills in later: a route you do not establish now does not exist
for the AE, and the panel says so rather than offering a control that cannot work.

`enrichment_basis` is the field that makes the rest of the row trustworthy. It names the
filing or profile the tool SURFACED — never the tool. Without it, the contact route is the one
field on that panel asserting something with no provenance, and an AE cannot tell a verified
address from a pattern guess. Where Clay returns a value whose origin it does not name, that
value is an inference: label it, or leave it out.

### A name-similar match is an identity FAILURE, not a near-miss

Measured, and it nearly shipped: a contact search for six named executives returned five
correct matches and, for a named **SVP Chief Data Officer**, an **intern with the same
surname at the same employer**. Attaching it would have put an intern's email on a Chief Data
Officer's row — in front of a client, in a panel whose whole job is "who owns this decision".

The check is one line and it is not optional:

> **The returned TITLE must match the person you searched for.** Surname plus employer is not
> identity.

On failure, quarantine the field with its reason. Do not attach the nearest match, and do not
attach the row with the title silently corrected to the one you were looking for.

## A peer technographic claim is now gated

**AG-04 blocks.** A Clay technographic scan across a named peer set feeds the tech register,
and the moment you state a `peer_coverage` share, three things are required:

- a `peer_deployments[]` breakdown with **one row per peer**, including the peers you could
  NOT establish — those carry `deployed: null`
- `source_url` and `as_of` on every `deployed: true` row
- agreement between the stated share and its own breakdown to within **one peer**
  (`1 / len(rows)`)

So a scan that establishes 2 of 5 peers with 3 unknown is **not 40% coverage**. It is two
established, three unknown — state that, or state no share. Rows with `deployed: null` count
in the denominator, so scope the share to what the breakdown supports.

This replaced a card that decided "✓ deployed" beside a NAMED credit union from
`hashCode(row_id + peerName) % 100`. The claim cannot be manufactured, and a share with
unknowns behind it is not that share.

## When the scan and the register disagree

Measured on a real run: the machine scan reported **Alkami** on the client's domain while the
promoted tech register stated **Lumin Digital** as the digital banking platform. Both cannot
be the live member-facing platform without an explanation.

This is a contradiction, and the resolution is the finding. Work it in this order:

1. **Compare `as_of` dates.** A scan is current; a register row may be a migration that has
   since completed, or one still in flight.
2. **Ask what the scan actually observed.** A technographic scan reads the surfaces it can
   reach — a marketing site, a login subdomain, an app bundle. A vendor detected on
   `www` is not necessarily the member-facing platform behind authentication.
3. **Check for a subsidiary, a predecessor or a partial estate.** Two platforms genuinely
   coexist during a conversion, and "both, in this window" is a legitimate answer with a date.
4. **If it still does not resolve: quarantine and STATE it.** Never average two disagreeing
   figures, never silently prefer the newer one, and never drop one so the card looks clean.

`04-craft/1-reasoning.md` owns the nine contradiction classes and the cross-check procedure.

## What Clay cannot do, and what to do instead

| Gap | Clay | Instead |
|---|---|---|
| Regulatory standing and enforcement | no | The regulator's own registry — a T1 source Clay does not index |
| Peer cell scores | no | The peer table, then the fallback ladder |
| Anything inside the client's estate | no | The assessment package; Clay sees the outside only |
| Sentiment at review-site depth | partial | Named review routes; treat Clay's news sentiment as one route of several |
| Dated event history for the timeline | partial | `Recent News` covers recent; the research workbook covers the rest |

## Automating this

The five steps above are deterministic given a domain, so a session can run them unattended
at the start of production and have the results waiting by the time the surfaces that need
them come up. Run Clay **immediately after reading the bundle and before writing the heatmap
page** — enrichment is slow and async, and the pages that consume it come later.

`scripts/clay_plan.py` prints the exact call sequence for a domain, including the title
filters and the tier each returned data point should be registered at.
