# Before you say no

An absence is a finding only if you can show the search that established it. An absence with
no record is a research failure wearing a finding's clothes — and it is the difference
between "no enforcement actions were found" and "no enforcement actions exist".

## The rule

> **Never emit an empty state until a documented proxy ladder has failed.**

Every rung you attempt is recorded, whether it hit or missed. The record ships with the
payload and renders in the empty state.

## The ladder, by signal

Run every rung. Stop at the first hit. Record all attempts either way.

| Signal sought | Rungs, in order |
|---|---|
| **Leadership** | Clay contact search (filtered) → company leadership page → the regulator's officer registry → proxy filings and Section 16 → conference speaker listings → named executives quoted in trade press |
| **Thought leadership** | Clay `Find Thought Leadership` → company newsroom and blog → conference programmes → trade-press bylines → podcast and webinar appearances → published research |
| **Technology stack** | Clay `Tech Stack` scan → the assessment's own tech rows → job postings naming platforms → vendor case studies and press releases → integration and partner directories |
| **Recent events** | Clay `Recent News` → company newsroom → investor releases → the wire archive → trade press |
| **Regulatory standing** | The regulator's enforcement database → the second regulator where dual-chartered → consent-order trackers → the entity's own disclosures |
| **Financial series** | Filings and results releases → investor presentations → the regulator's call-report data → the entity's own annual report |
| **Acquisitions** | Clay `Recent News` → company newsroom → the wire archive → the regulator's approval notices |
| **Peer figures** | The peer table → recompute at lower cohort size → adjacency inference → proxy ceiling → stop (see `evidence.md`) |
| **Sentiment** | App-store reviews → employer review sites → complaint databases → trade press → social listening |

## The ladder has rungs that only exist for some entities

Every rung above that begins "filings", "proxy", "Section 16" or "call report" presumes a
particular kind of filer, and running a ladder whose rungs cannot exist for this entity
produces the most dangerous result in the table: a NEGATIVE that is really a NOT ATTEMPTED,
recorded as a verified absence because the searches were genuinely run.

So before recording a negative, check that the ladder you ran was the one this entity's
shape has. These rungs replace the missing ones:

| Signal sought | Where the entity files nothing |
|---|---|
| **Financial series** | The trade press's annual ranking tables for the sub-vertical — dated third-party figures for private firms, year on year → an ESOP's Form 5500 → the entity's own acquisition announcements, which disclose the target's scale → rating-agency commentary where debt is rated |
| **Leadership** | The entity's own leadership and governance pages → every acquisition announcement, which names leaders on both sides → state licence registries, which name a designated licensed producer → conference programmes → Form 5500's named plan administrator and trustees |
| **Regulatory standing** | The licence registries the entity is registered in — state departments of insurance, NAIC's producer database, SEC IAPD or FINRA BrokerCheck for an affiliated adviser or broker-dealer — rather than a prudential enforcement database that has no jurisdiction over it |
| **Peer figures** | Where every comparable is private too, no rung yields a median. A published *ranking* of those firms is rung 4 — a proxy that discloses itself — and it is not rung 1 |

The mirror problem is a rung that returns three hundred results. That is not a hit either:
a ladder run against an entity that discloses continuously ends in a **selection** decision,
and the selection key is part of the finding. Say which key you used —
`01-start-here/6-entity-shape.md` states one per surface — because a reader who cannot see
why these six of forty will assume they are the only six that exist.

## Recording the ladder

Every empty state carries the ladder that produced it:

```json
"empty_state": {
  "kind": "verified_absent",
  "reason": "No enforcement action located against this entity.",
  "sources_searched": [
    "FDIC enforcement actions database",
    "State banking department orders",
    "Consent-order trackers",
    "The entity's own risk disclosures"
  ],
  "searched_on": "2026-08-03"
}
```

## Four results, and they are not the same

| Result | Means | Renders as |
|---|---|---|
| **HIT** | A rung returned something | The finding, cited |
| **NEGATIVE** | Every rung ran and returned nothing | A verified absence, with the routes shown |
| **NEGATIVE AND APPROPRIATE** | The absence is the correct posture, not a gap | The absence, stated as correct — with why |
| **NOT ATTEMPTED** | The ladder did not run | **Not an absence.** Emit nothing and record the omission |

The third is the one most often missed. Some absences are the right answer — an institution
with no browser-automation estate is not behind, it has correctly declined a capability its
model does not need. Say so, rather than rendering it as a gap.

The fourth is the one that causes damage. An unrun ladder rendered as "none found" is a claim
you have not earned.

## Worked example

From a completed assessment, nine ladders documented before any absence was asserted:

| Signal sought | Routes attempted | Result |
|---|---|---|
| AI announcements beyond the known pilot | Newsroom, investor releases, wire archive, trade press | One found — no others |
| Risk governance in filings | Results-release forward-looking language, proxy searches | **HIT** — named in the entity's own risk language |
| Organisational capability | Job boards, careers page, Section 16, org aggregators | **HIT** — five roles located |
| Executive positioning | Trade press, conference listings, newsroom | **HIT** — three dated quotes |
| Regulatory enforcement | Two regulator databases, consent-order trackers | **Negative** — and regulatory silence is not evidence of control effectiveness |
| Published research | Investment disclosures, analyst roles, research partnerships | **Negative** |
| An alternative to the unused module | 29 internal sources, credit disclosures, lending pages | **Negative** — recorded as an open question, not a finding |
| Browser automation | Internal corpus, automation documentation | **Negative and appropriate** — the catalogue's own descriptor states absence is a defensible posture |
| Security architecture | Full-text search across the engagement corpus | **Not present** — three rows remain provisional on it |

Note the last three. One negative became an **open question** rather than a finding, because
absence of a documented alternative is not evidence of a bad undocumented one. One became
**appropriate**. One became a **stated limitation** that constrained three scores.

## What this changes about how you work

Search first, write second. The ladder is not paperwork after the fact — running it is how
you find the thing that turns an empty card into a cited one. Most ladders hit. The ones that
do not produce a finding you can defend.
