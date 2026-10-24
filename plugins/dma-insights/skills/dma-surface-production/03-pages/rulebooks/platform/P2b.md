# platform rulebook · P2b · Conversation starters

One surface's rulebook — the positive pattern, the anti-patterns and the exclusion set for P2b. `../platform.md` is the page's index; the packaged contract for the same surface is `../../platform/P2b.md` (QA audit F-E01-026, 28-09-2026).

## P2b · Conversation starters

### Baxter positive pattern

The opener names what exists before what is missing, and the E-IDs stay out of
the spoken text:

> "You have nine products from one vendor in production, five AI systems live
> and a core relationship a quarter of a century old. What we could not find
> anywhere in a scan of your estate is an integration platform, so those
> systems are wired to each other one connection at a time." (rank 1,
> `opens_on: gap`)

> "You announced the merger in June, and the design decisions for systems
> integration get made in the next couple of quarters rather than at
> conversion. That is the window that matters here." (rank 2, `opens_on:
> timing` — the window and what closes it, dated by the client's own event)

The follow-up is a discovery question, not a diagnostic:

> "What does your conversion plan assume about how member data moves between
> the two cores?" (`followup_question`, rank 2)

Shape notes, measured: 5 starters, 5 DISTINCT opening shapes (gap, timing,
their_words, contradiction, system) — at most one per move; every
`their_system_reference` names something from the register (Azure Logic Apps,
the announced merger, the cloud-migrated Symitar core, Genesys/Glia, Tealium
AudienceStream); `peer_reference` is OMITTED on all five rather than filled
with "peers are investing…" filler; the rank-3 their-words opener quotes the
chief technology officer verbatim and dated, and agrees with the quote before
adding to it. Logix's promoted rank-1 and rank-5 are the corrected forms of
9-antipatterns §2's refused openers, worth reading side by side.

### Anti-patterns

- **MEM-0060 / CG-17** — a required list satisfied by `[]` writes no rows and
  the surface vanishes — measured 2026-08-14: `platform.starters.starters`
  on the second promoted client passed every gate as an empty list, promotion
  wrote zero rows, and the page served no starters and no `empty_state`;
  owner report: "Conversation starters disappeared" — the rule: an empty list
  is a claim ("there are none") and must be made deliberately — send the
  items or declare the section's `empty_state`; `may_be_empty` belongs to
  `techstack.dropped` alone. **PERMANENT — never retire** (raised_by_kind
  USER); test: `apps/mcp/tests/test_required_list_not_silently_empty.py`.
- **(no MEM) / AG-12 + 9-antipatterns §2** — an opener that reads as an
  accusation — measured on Logix's earlier round, refused and rewritten:
  "Two things you have told the market do not quite line up", "What it
  cannot do is answer a question", "You do not measure contact-centre
  deflection" — the rule: state the same fact from the value end ("There is
  money sitting in the gap between two things you have already said publicly,
  and I think it is yours to take"); the follow-up question is part of the
  starter, and a consultative opening followed by "why do you not track
  that?" is still an accusation.
- **(no MEM) / S31_platform_distinctiveness** — one opening shape stamped
  five times — measured: 685 of 685 starters across the corpus used one
  shape — the rule: vary the move, at most one starter per opening shape; a
  set that all opens the same way is a template, not a set.
- **(no MEM) / pack-measured quote hygiene** — a garbled quote repaired into
  fiction — measured: 76 starters across 39 clients shipped truncated or
  mid-word quotes — the rule: quoted material is a clean, complete, verbatim
  sentence from a resolvable source; if the mined excerpt is broken, drop to
  a non-quoting shape — never invent the missing half.
- **MEM-0086 / CITATION_NAMES_THE_CONTAINER_NOT_THE_SPAN** — a peer figure
  cited to a page that does not carry it — measured on Logix: Patelco
  $9.62bn, First Technology $28.58bn and Golden 1's 9.94% net worth ratio
  cited to E-CC-296/297, whose excerpts are the NCUA download-table row and
  a file-format sentence; a regex for every named peer and figure over all
  37 cited rows matched 0 — the rule: the cited span carries the figure; a
  derivation trail is a disclosure, not a citation; a `peer_reference` is a
  NAMED institution with a DATED action or the field is omitted.
- **MEM-0085 / ET-09 (CHECKER_FALSE_POSITIVE)** — the run's own recorded
  cohort refused as contamination — measured on Logix: `peer_reference`
  naming Patelco and Golden 1 in full legal form drew 2 of 4 blocking
  reasons while the same run's heatmap named the same five peers in short
  form and passed — the rule: this is a recorded checker defect, not a fact
  about your payload; when ET-09 refuses the run's own named cohort, report
  the recurrence against MEM-0085 rather than silently un-naming the peer or
  shopping for a spelling that slips past.
- **MEM-0081 / DEFAULT_DENY_DELEGATED_TO_THE_PRODUCER** — an all-internal
  section that empties in place instead of being withheld whole — measured:
  Logix marks `starters.starters` internal, and `redact_section(...,
  audience='customer')` serves `{e_ids, produced_at, internal_only,
  producer_version}` — a husk with no content and no reason — while Baxter
  marks nothing and its starters serve to the customer body whole; two
  promoted clients answer "who may read a starter" two ways — the rule: P2b
  is AE-facing by its own contract definition ("openers an AE can say out
  loud"), so mark `starters.starters` and declare the `empty_state` that
  explains the customer view; the real fix — `('platform','starters')` in
  `CUSTOMER_WITHHELD` — is the open finding's, not yours to improvise.

### Exclusion set

The section's content is AE preparation by contract definition: until
`CUSTOMER_WITHHELD` carries `('platform','starters')` (MEM-0081, open), the
producer marks `starters.starters` and `r_layer` in `internal_only` and
accepts that the customer body serves the declared `empty_state` reason in
their place. `provenance` (`TEMPLATE_FILL │ ANALYST`) is required and renders
internal-only — it is an excluded method class at the customer boundary.
`r_layer` never serves to any audience. The customer-visible item row, where
starters serve at all, is `{rank, text, opens_on, named_gap_subcap_id,
peer_reference, their_system_reference, followup_question, e_ids}` —
`opens_on` is a matched vocabulary (lower-case, exact spelling; capitalising
it drops the row out of its filter, AG-05). Probe ladders stay in
`sources_searched`/`searched_on` (Logix's starters `empty_state` carries
both) and drop at the customer boundary; the `reason` is what the customer
reads, so write it as real information, not workflow status.

### Enrichment pathways

Connector pathways, one per opening shape's input: `their_system_reference`
reads the run's own register — facet `techstack` (`explorium` scan T1,
wired, not live; `clay` Tech Stack T1, wired — a machine technographic scan
is T1, never T4; `first_party` platform statements T1-T2). The their-words
opener quotes O12 — facet `thought_leadership` (`clay` Find Thought
Leadership T2-T3 — T2 for a first-party publication or named conference, T3
for trade press, per `02-inputs/clay_taxonomy.json`; `first_party` newsroom
and trade-press rungs T1-T2; `quartr` transcripts T1-T2, declared, not
wired). `peer_reference` — facet `peer_scores`, `clay` peer deployments (T1
per established deployment): a NAMED institution with a DATED action or the
field is omitted (MEM-0086's rule).

Web-search pathways:

- `"[executive] [entity] keynote OR interview OR podcast 2024..2026"` — the
  their-words opener's source; T2 for a first-party publication or named
  conference, T3 for trade press; the registered span is the verbatim
  sentence itself (50–500 chars), and a broken excerpt drops the shape —
  never repair a quote into fiction.
- `"[peer] [action] announcement [year]"` — dates the peer opener; T2 from
  the peer's own newsroom, T3 trade press; cite the span that carries the
  figure, never the container (MEM-0086).
- `"[entity] [system] migration OR rollout OR go-live"` — grounds the
  system opener in the register's own facts at T1-T2; a vendor release
  about the entity is T5 and requires corroboration (W6).
- The contradiction opener adds no search class of its own — both facts
  must already be registered evidence of THIS run, or the opener cannot
  cite and is replaced with a different shape (the prompt's REJECT); the
  searches that failed a shape are ladder rungs, never evidence rows.

Gap-to-pathway: this section emits `empty_required` on `starters` only —
and MEM-0060 is the reason the kind matters: `[]` passes every gate and the
surface vanishes, so the pathway answer is items or a declared
`empty_state`, decided deliberately, never silence.

---
