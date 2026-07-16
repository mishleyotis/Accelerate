# DMA Insights — Language Guidelines (do's & don'ts corpus)

**Mandate (operator, 2026-07-08):** *"I warned against accusatory language e.g.
'No CRM' etc. Ensure gaps are phrased as opportunities. Have a corpus on do's
and don'ts in language."*

Every AE-facing surface — focus-area titles/quotes, insight-card WHAT/WHY/
SO-WHAT, top findings, why-now, section narratives, recommendations — must read
as a **forward-looking opportunity brief**, never an accusatory audit. This file
is the single source of truth for that voice. It is enforced two ways:

1. **Deterministic floor** — `app/services/text_hygiene.opportunity_reframe`
   applies the DON'T→DO rewrites below on every persisted pack field (titles,
   quotes, card prose, findings, narratives) as the last export pass. Safe,
   idempotent, citation- and number-preserving, clean-posture-aware.
2. **Generative bar** — the Phase C composer writes to these rules directly and
   the grader's tone check (G-language) fails any item that ships a DON'T
   phrasing, so nothing renders accusatory. The composer produces the nuanced
   rewrite the regex floor cannot (it understands the sentence); the floor
   guarantees nothing regresses when the generative tier is cold.

---

## The one rule

**A gap is an opportunity, stated by what the client can BUILD next — not by
what they are missing, and never by what they "lack" or "fail" to do.** Name the
capability, its readiness, and the move. Keep every number, name, date, system,
and evidence citation verbatim.

---

## DON'T → DO (the rewrite corpus)

Ordered specific→generic; the code mirrors this order so a specific rule wins.

| # | DON'T (accusatory / deficit) | DO (opportunity) | Note |
|---|---|---|---|
| L1 | `No CRM` / `No <Capability>` (headline) | `<Capability> greenfield` / `Opportunity: <Capability>` | headline lead only |
| L2 | `No <X> deployed / in place / present` | `<X> greenfield` | deployment context |
| L3 | `Zero <X>` / `0 <X>` (a capability/tool) | `greenfield <X>` / `an untapped <X>` | not counts of real things |
| L4 | `<X> without <Y>` (a missing companion capability) | `<X>; <Y> is the next opportunity` | clause-end only |
| L5 | `lacks` / `lacking` / `lack of` | `has headroom to build out` / `headroom in` / `the opportunity in` | |
| L6 | `absent` / `missing` | `a near-term opportunity` / `an opportunity to add` | |
| L7 | `fails to` / `failing to` / `does not (yet)` / `cannot` / `unable to` | `has not yet` / `is not yet able to` | |
| L8 | `no <X> detected` / `with no <X>` / `NO <X>` | `<X> not yet in place` / `<X> is an opportunity` | tooling scans |
| L9 | `no public evidence of <X>` / `no public <X>` | `<X> is not publicly disclosed` / `limited public disclosure of <X>` | evidence-availability, not a real gap |
| L10 | `weak` / `immature` / `nascent` / `rudimentary` / `poor` / `deficient` | `an emerging capability with room to mature` / `limited` / `below benchmark` | |
| L11 | `pain point(s)` / `weakness(es)` / `failure(s)` | `area of focus` / `opportunity` / `gap` | |
| L12 | `slipping/falling behind` / `lags` / `erodes` / `widens the gap` | `trailing` / `trails` / `reduces` / `leaves a gap` | |
| L13 | `— NONE Identified` / `— N/A` accusatory tail | *(drop the tail)* | |
| L14 | `Critical finding:` / `CRITICAL:` prefix | *(drop; use severity chip)* | |
| L15 | repeated `no X, no Y, no Z` | reframe EACH clause (`X, Y and Z are the open opportunities`) | list form |

**"gap" is allowed** — it is opportunity-framed (an area to close), and the gold
overlays use it ("Consumer Customer-360 **gap** — Data Cloud **greenfield**").
"greenfield" is a POSITIVE sales term (a clean slate to build on) and is
preferred over any "no/zero" absence phrasing.

---

## Clean-posture EXCEPTIONS — never reframe these (they are positive facts)

A "no / zero / without / nil" that precedes a **risk, compliance, or adverse
event** is a *clean-posture positive* and must be left intact (only the
accusatory "— NONE Identified" tail is trimmed). Reframing them would be absurd
("opportunity to add data breaches").

- `no breaches` / `no incidents` / `no data loss` / `no outage` / `no fraud event`
- `no enforcement action` / `no consent order` / `no litigation` / `no lawsuit`
- `no violations` / `no fines` / `no penalties` / `no sanctions` / `no default`
- `no adverse findings` / `no complaints` / `clean regulatory record`

Also do **not** invert genuine strategy facts stated as absence that are neutral
or favourable to the engagement (e.g. *"CEO: no M&A interest; all capital in
technology"* — a **positive** tech-spend signal). When a "no X" is ambiguous and
not clearly a capability gap, the deterministic floor leaves it for the
generative tier rather than risk an awkward inversion.

---

## DO's — the positive voice (style)

- **Lead with the capability + the move**, not the deficit: *"Cross-channel
  application continuity — a scoped opportunity to unify the member journey"*,
  not *"No unified journey"*.
- **Quantify the opportunity, not the failure**: *"scores 1.0/5 vs a 3.0 peer
  benchmark — the widest headroom in the customer-experience pillar"*.
- **Name the play + system + timing** (the strategic so-what): *"stand up Data
  Cloud on the existing Snowflake foundation before the summer-2026 core
  conversion"*.
- **Keep it grounded**: every figure/name/date/system stays verbatim; every
  claim keeps its evidence citation.
- **Never awkward**: a reframe that produces dangling or double-framed prose
  ("Opportunity: Salesforce Deployed", "greenfield … Opportunity: …") is worse
  than the original — the rule must yield natural copy or not fire.

---

## DON'T's — banned constructions (summary)

Accusatory absence (`No X`, `Zero X`, `lacks`, `without X`, `fails to`,
`cannot`, `absent`, `missing`), deficit adjectives (`weak`, `poor`, `immature`,
`deficient`, `rudimentary`), competitive-decline verbs (`slipping/falling
behind`, `lags`, `erodes`), audit-tone prefixes (`Critical finding:`,
`— NONE Identified`), and internal jargon (raw `P#C#` / `E-###` / `M#` codes,
"subcap", "pillar", "peer cohort", "Severity-to-Maturity Cap Matrix") — the last
group is handled by `text_hygiene.plain` / `scrub_md`.

---

## Consultant-grade output checks (operator, 2026-07-08 — the writing bar)

Beyond word-level tone, every AE-facing narrative (insight-card WHAT/WHY/
SO-WHAT, top-finding body, focus rationale, SCQA, platform story) must read like
a consultant wrote it. These are grader dimensions (Phase-C rubric) and
countercheck segments; the generative composer produces them, the deterministic
floor cleans punctuation and flags violations it cannot fix.

- **C1 — No one-liners; write a paragraph.** Each argument is a **3–5 sentence
  paragraph**, not a single templated line. It states the point, grounds it in
  quoted evidence and specific data (figures, systems, dates, named roles), draws
  the implication, and names the move. *Anti-pattern (banned):* "Cross-Channel
  Application Continuity scores 1.0/5 against a peer median of 3.0 (-2.0) — a
  clear opportunity to close the gap." *Gold:* a paragraph that opens on the
  business consequence, cites the two or three evidence points that prove it,
  contrasts the LOB/peer fact that makes it matter, and closes on the sequenced
  play and its timing.
- **C2 — Headline first, support after.** Lead with the client-specific key
  message (the thesis), then the grounding detail. Never open on a raw balance-
  sheet fact, a bare capability name, or a score recitation.
- **C3 — Varied, natural sentence structure.** No two cards (and no two clients)
  may share a rehearsed template skeleton. The banned recurring frames include
  "Make X a near-term focus … lift it from N to M", "X is one of the least
  developed … capabilities, scoring N/5", "Prioritise X in the next phase;
  sequencing it first lifts …". Vary openings, clause order, and connective
  tissue so the prose reads written-once, not filled-in.
- **C4 — Quote accurate evidence + data.** Every claim carries a specific,
  correct figure/name/date/system traceable to the corpus (the `_verification`
  contract); no vague "significant"/"various" where a number exists; never a
  peer's figure attributed to the entity.
- **C5 — Punctuation is clean and deliberate.** Complete sentences with terminal
  punctuation; em-dashes and semicolons used correctly; no stray citation
  brackets, doubled separators ("— ,,"), truncated clauses, dangling colons, or
  ALL-CAPS shouting. Numbers and units render consistently ($1.8B, 4.8/5, +16.2%).
- **C6 — Opportunity trends (extends the DON'T→DO table).** Capability/technology
  absences become extension opportunities with the capability named forward:
  "No AI/ML" → "Opportunity to extend into AI/ML capabilities"; "No data lake"
  → "Data-platform (data lake) build opportunity"; "No CDP" → "Customer Data
  Platform greenfield". Clause-lead only in the deterministic floor; the
  composer does the mid-sentence, sentence-restructuring rewrites (a "X has no Y"
  SVO is left by the floor because dropping the verb inverts the meaning —
  "has no AI/ML" must never become "has a greenfield AI/ML").

**Grading (Phase-C):** an item PASSES the writing bar only when C1 (≥3 sentences,
≥1 quoted datum), C2 (thesis-first), C3 (not a cohort-shared template n-gram),
C4 (every datum verified), and C5 (punctuation clean) all hold; the countercheck
reports `oneliner`, `template_language`, and `punctuation_debris` per segment so
the gap is measurable across all 94 before ship.

## How to extend

Add a row to the DON'T→DO table above, then add the matching rule to
`_OPPORTUNITY_SUBS` in `app/services/text_hygiene.py` (specific→generic order)
with a unit test in `tests/test_text_hygiene_opportunity.py` using a real
corpus example. The `qa_language_audit` / `countercheck_pack` accusatory-language
scan is the inverse gate — a new DON'T pattern added here should also be added
to the scan so the 94-client pack is measured against it.
