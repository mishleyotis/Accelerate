# overview rulebook · O1b · Capability ceiling &amp; uncertainty

One surface's rulebook — the positive pattern, the anti-patterns and the exclusion set for O1b, with its drilldown(s) DD-15. `../overview.md` is the page's index; the packaged contract for the same surface is `../../overview/O1b.md` (QA audit F-E01-026, 28-09-2026).

## O1b · Capability ceiling &amp; uncertainty

### Baxter positive pattern

> "Three strategy pillars are set out in BCU's own materials — member-first,
> application programming interface-driven technology standards and a data
> strategy for faster decisions — under a board technology committee carrying a
> former Fortune 50 chief information officer. The fullest public statement of
> that strategy is a 2020 conference deck, so its present form is inferred from
> later appointments rather than read." (P1C1 rationale — half (a): what the
> evidence establishes; half (b): the absence that set the ceiling)

> "The current digital strategy document with its refresh date and investment
> envelope; the fullest public statement of it is still the 2020 conference
> deck." (`limiting_absence` — a named, searchable artefact: the research
> backlog for the next run)

Shape notes, measured: 17 rows (the v5.0 category count; a v7.0 run has 16),
every row `claim_label: CEILING_ESTIMATE` with an uncertainty band and named URF
modifiers where applied; `internal_only: ['ceilings.rows']` marked by the
producer.

### Anti-patterns

- **MEM-0087 / the tier rule** — a machine technographic scan registered below T1
  caps ceilings artificially — measured: the same scan output re-registered at T1
  gained +0.85 mean ERS on identical content; a T4 filing caps at L2.5, and the
  pack calls tier misclassification the most common suppression in this corpus —
  the rule: a machine scan is T1, never T4; a ceiling set by a misfiled tier is
  recounted at the true tier, never adjusted in place.
- **measured · both payloads** — one field, two vocabularies: Logix rows state
  the ceiling as a rubric code (`"ceiling": "M3"`, band 0.4) where Baxter states
  a band word (`"ceiling": "Differentiating"`, band 0.3) — the prompt's ladder is
  M1–M5, and an internal table read across clients needs one vocabulary — the
  rule: follow the prompt's ladder here, record the divergence rather than
  papering it, and never let either vocabulary out of this section into
  client-facing prose (`cap_level` M-codes measured escaping into
  `context.issue_register` are the neighbouring leak, D1).
- **(no MEM) / G14 + the pack's enrichment obligation** — a ceiling set by
  absence obliges you to have looked: before emitting a ceiling below M3 on an
  absence, run the ladder for the `limiting_absence` specifically plus the five
  organisational proxies — a ceiling you have not tried to break is an
  assumption; over ±0.8 the row is `ceiling=null` "Cannot reliably estimate",
  because a point estimate past the cap is false precision.

### Exclusion set

This section is **NEVER_SERVED** — it reaches no audience at all (owner
instruction 2026-08-19: internal artifacts "are dropped at the payload boundary
and render nowhere"); it is still promoted, validated and auditable through the
connector, so produce it fully. Mark `rows` internal_only anyway, as both
payloads do. `ceiling`, `uncertainty_band`, `urf_modifiers` and `cap_level` are
excluded key classes everywhere — the generated allowlist's ceilings row keeps
only `{category_id, category_name, claim_label, confidence, e_ids,
limiting_absence, rationale}`, which is what would survive if the section ever
served. `r_layer` reaches no audience.

### Enrichment pathways

- **Connector.** No facet of its own. The pathway that most often moves a
  ceiling is the tech one: a machine technographic scan is T1, never T4
  (`clay` Tech Stack; the `explorium` ingest scan), because a scan misfiled
  at T4 caps at L2.5 — the most common suppression in this corpus.
  `first_party` filings (T1-T2) lift a ceiling wherever the
  `limiting_absence` is a document the entity actually publishes.
- **Web search** (the G14 obligation — a ceiling set by absence obliges you
  to have looked): the `limiting_absence` itself as the target — "[Entity]
  digital strategy refresh OR investment envelope 2025 2026" for a strategy
  ceiling, T2 where the entity states it. The five organisational proxies
  where the absence is organisational (board bios, C-suite digital hires,
  LinkedIn digital titles, conference talks, strategic-plan filings) —
  T2-T3. "[Entity] [category capability] deployment OR case study" — a
  vendor case study is T5 (W6) and cannot raise a ceiling above L2
  uncorroborated. Anything found is minted and the ceiling recounted at the
  true tier; a ladder that returns nothing is recorded in the rationale's
  half (b), never as an evidence row.
- **Gap-to-pathway.** `rows` emits `empty_required` — the only kind this
  section emits. A missing row is a category not yet worked, closed by the
  ladder above run against that category's limiting absence.

---

## DD-15 · Ceiling rationale (drilldown from O1/O1b)

Inline expansion from a capability ceiling row (Drilldown atlas: DD-15,
component CeilingEstimateCard). The spec files the drill under O1 — the hero —
while the rows live on `overview.ceilings` (O1b): one drill, two anchors, one
payload. No separate prompt; the expansion renders the row's `rationale` and
`limiting_absence`, so a row that cannot carry the expansion is an O1b row to
finish.

### Baxter positive pattern

> "Bot inventories and run volumes for the three robotic process automation
> products detected — process-mining output or automation logs would show
> which of them carries the work." (P3C1 `limiting_absence` — named,
> searchable, and written FOR this panel: the next run's research backlog
> rendered where the reader asks "why this ceiling")

Shape notes, measured: the P3C1 row carries `ceiling` Differentiating with
`uncertainty_band` 0.8 at its cap and `urf_modifiers` ["URF-02"] — "the band
widens to its cap because bot counts and run volumes for those three are not
publicly determinable, so utilisation cannot be separated from installation",
which is the two-half rationale discipline doing its work.

### Anti-patterns

- **pointer / O1b's entries** — the tier rule (a machine scan is T1, never
  T4), the one-vocabulary rule and the G14 look-before-you-cap obligation are
  homed under O1b; the expansion renders the same row.
- **(no MEM) / spec DD-15** — "This panel renders from the payload its parent
  surface already carries." An expansion that needs content the row does not
  hold means the row is incomplete — fixed in O1b, never patched at the
  drill.
- **(no MEM) / the boundary, current** — O1b is NEVER_SERVED (owner
  instruction 2026-08-19), so this expansion renders nowhere today; the
  spec's contract for it stands, and the row is still promoted, validated and
  read through the connector — produce it fully.

### Exclusion set

As O1b: the section reaches no audience; `ceiling`, `uncertainty_band`,
`urf_modifiers` and `cap_level` are excluded key classes everywhere, so if
the boundary ever changes, what survives is `{category_id, category_name,
claim_label, confidence, e_ids, limiting_absence, rationale}` — exactly the
pair this panel renders plus its envelope. Never let either ceiling
vocabulary out of the section into client-facing prose.

### Enrichment pathways

- **Connector.** The parent's — the T1 technographic pathways that most often
  raise a ceiling, and `first_party` filings where the limiting absence is a
  published document. See O1b.
- **Web search.** The `limiting_absence` is the query: "[Entity] automation
  inventory OR process mining OR bot run volumes" for the P3C1 exemplar —
  T1-T2 where the entity or a regulator states it, T5 where only a vendor
  does (W6). Whatever is found is minted and the ceiling recounted; a ladder
  that returns nothing is the rationale's half (b), never a row.
- **Gap-to-pathway.** None of its own — `rows` reports `empty_required` on
  the parent. A row whose `limiting_absence` is not searchable is invisible
  to the worklist; G14 and the rationale's two-half rule are the check.

---
