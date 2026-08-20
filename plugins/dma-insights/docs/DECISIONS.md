# Settled decisions — 2026-08-19 program round

Every decision below is settled empirically, from the repository read end to
end and from the parsed promoted output of the two reference clients: Logix
(run `d7ed1d90-d406-4e8e-9ab0-75f91a0c15bb`, the worked test client) and
Baxter (run `c1351d25-a612-4dbe-b498-127bccaf6810`, the positive pattern).
Each entry names the repo locations that ground it and the client evidence
that justifies it. Where the data underdetermined a choice, the assumption is
stated inline and logged for review rather than blocked on.

---

## D1 · The client-facing allowlist and the per-surface exclusion sets

**Decision.** The submit boundary is already fail-closed on fields — CG-04
refuses any key outside the section contract (`apps/mcp/dma_mcp/validation.py:836`),
with the contract registry (`apps/mcp/dma_mcp/contracts.py:_load`) as the
allowlist. What is deny-based today is the SERVE boundary
(`apps/api/dma_api/redaction.py`): four ordered mechanisms (producer
`internal_only` marks → `ALWAYS_STRIP` → customer key/path strips →
`CUSTOMER_WITHHELD` sections). The gap the brief names is real and lands
there: a NEW internal-shaped key that passes a widened contract would serve
by default. The fix is a **customer-audience serve allowlist**: for
`audience=customer`, `redact_section` keeps only keys enumerated per section
in a generated `CUSTOMER_ALLOWLIST` (derived from `contracts_data.json`
fields minus the exclusion classes below) and drops everything else, with
the drop count reported in the redaction receipt. Internal audience stays
deny-based — internal is the working view.

**Exclusion classes** (measured on Logix staging, cited paths):

| Class | Logix evidence | Already handled? |
|---|---|---|
| Reasoning traces (`r_layer`) | 52 objects run-wide, marked | Yes — `NEVER_SERVED_KEYS`, every audience |
| Red-team transcript (`storyline_challenge`) | exec_summary volleys[5] | Yes — `CUSTOMER_STRIP_KEYS` + renderer deleted 2026-08-19 |
| Ceilings / evidence census | ceilings rows[16] M-codes, coverage tiers | Yes — `NEVER_SERVED` (no audience) |
| Contact routes | roster emails + 7 linkedin_urls (4 unmarked) | Yes — `CUSTOMER_STRIP_CONTACT_KEYS` by key at any depth |
| Cross-entity ids | none present (patterns[] empty) | Yes — `ALWAYS_STRIP` |
| **Probe ladders** | `cell_evidence` 4,527 `sources_searched` strings over 705 cells, `queries_run` 29 raw searches in alerts, `searched_on` in 20 empty_states | **No** — `cell_evidence` is not customer-withheld; ladders serve. **New:** `CUSTOMER_STRIP_KEYS += (sources_searched, queries_run, searched_on)`; `empty_state.reason` and `closure_condition` stay (owner adjudication 2026-08-14: a producer's real reason renders; a probe never does) |
| **Tier codes outside the census** | `heatmap.evidence` rows[16].tier, `cell_evidence` items[97].tier | **Partial** — census is NEVER_SERVED, but the evidence index serves tiers to customers. **New:** `tier`, `ers` join customer strip keys; internal keeps them |
| **M-code caps outside ceilings** | `context.issue_register` issues[].capped_subcap_ids[].cap_level='M3' | Context page is `CUSTOMER_WITHHELD_PAGES` entire — covered; a gate (below) pins M-codes to internal-marked fields anyway |
| Build metadata | 3 inconsistent `produced_at` values in one run | Envelope `produced_at` serves per section deliberately (MEM-0051); in-body copies are contract fields — keep, but CG-05 consistency note logged for review |
| `[L3-*]` codes in prose | 7 codes inside `catalogue_path`/`l4_feature` strings | Rendering resolves labels (RC6); codes inside *prose* remain — assumption: acceptable internally, and the customer never sees the platform drill fields that carry them; logged for review |

**Fail-closed proof:** the allowlist is *generated* from `contracts_data.json`
at build time (same pattern as `enum_fields.json`), so a new contract field
defaults to **absent from the customer allowlist** until explicitly
classified — the "new internal artifact nobody thought to deny" drops by
default. A regression test feeds a payload with an invented key and asserts
the customer body never carries it.

## D2 · The per-surface rulebook schema

**Decision.** Rulebooks are markdown files at
`skills/dma-surface-production/03-pages/rulebooks/<page>.md`, one per page
slug (heatmap, overview, insights, platform, context, techstack), with
firmographics carried as a card-level entry inside the overview and context
rulebooks. The schema mirrors the page packs exactly, because that is the
grammar the producers already read (no YAML front matter anywhere in
03-pages — `03-pages/1-heatmap.md:1-22`):

```
# Rulebook: <page> · v<N> (<date>)
## <SurfaceID> · <Title>            ← same anchors as the page pack;
                                      spec-named drilldowns get sections too
### Baxter positive pattern         ← quoted exemplars + shape notes
### Anti-patterns                   ← entries keyed MEM-#### / gate-id;
                                      user-flagged entries carry the marker
                                      **PERMANENT — never retire** and name
                                      their regression test
### Exclusion set                   ← the internal-only keys/paths for this
                                      surface, from D1
### Enrichment pathways             ← connector sources per facet with tier
                                      bands (enrichment_sources.json +
                                      clay_taxonomy.json), 3–6 web-search
                                      query patterns with the tier each
                                      result registers at and the
                                      register_evidence rule that applies,
                                      and the list_enrichment_gaps
                                      kind-to-pathway map
```

v2 (2026-08-19) added the `### Enrichment pathways` subsection to every
surface section.

**Load path (constraint [E], structural not hook):** each producer agent's
Method step 2 — already "get_memory_digest + search_findings for the routed
surfaces" (`agents/production/heatmap/heatmap-surface-producer.md:43-50`) — gains "read
`03-pages/rulebooks/<page>.md`" before authoring. The rulebook is versioned
in its title line; the rectifier is the only writer (constraint [B]).

**Evidence.** Producers demonstrably read the page packs' `### Prompt`
blocks (31 GATES: lines across the packs); the memory-first path is uniform
across all four producer agents; `assets/section_templates.json` fixes the
34-section vocabulary the rulebooks key on.

## D3 · Rubric weights, thresholds, and convergence

**Decision.** Seven dimensions, weighted: root-cause correctness 0.25 ·
generalization 0.15 · evidence-weighing 0.15 · regression coverage
(fails-before/passes-after) 0.15 · no-theater 0.10 · narrative contribution
to the AE storyline 0.10 · non-regression 0.10. **Admission threshold 0.75.**
Below threshold returns to the adversarial enrich-and-adjudicate loop.

**Calibration anchors (real graded material, not invented):**
- Score ~0.3 anchor: the pre-fix tile state (MEM-0095 — two factor
  vocabularies for one number, no gate) — root-cause absent, regression
  coverage absent.
- Score ~0.6 anchor: the hand-fixed tiles *without* CG-31 — target fixed,
  no regression coverage, fails "generalization" (next submission free to
  regress).
- Score ≥0.75 anchor: CG-31 as landed (`apps/mcp/dma_mcp/validation2.py:1493`,
  nine tests, legacy names refused BY NAME) — root cause, coverage, and
  non-regression all present.

**Convergence thresholds (learning curve):** first-pass promotion **clean**
= 0 blocking reasons; **near-clean** = ≤2 blocking reasons, none in a learned
class, repaired without re-synthesis; learned-class recurrence = 0 across the
final two learned clients AND the held-out; user-flagged recurrence = 0
anywhere, ever. Baseline for "declining": Logix round-1 ≈ dozens of owner
reports across 5 rounds; Baxter re-promote under new gates = 80→47→21→1→0
reasons paid in one day (measured 2026-08-19).

## D4 · Tech-stack confirmation thresholds

**Decision.** A row surfaces on the customer-audience Tech Stack page only
when ALL hold (internal audience sees the full register with status chips):

1. **Status** ∈ {CONFIRMED, ABSENT}. ABSENT stays: Baxter's 3 ABSENT rows
   carry the gap argument the page exists to make (Salesforce Data Cloud /
   CRM Analytics / MuleSoft named searched-and-not-found). INFERRED and
   CLAIMED are internal-audience only — resolves CLAUDE.md's open decision
   "visual treatment of CLAIMED vs INFERRED" for the customer audience.
2. **Corroborated**: ≥2 evidence ids from distinct registrable domains, OR a
   single source of tier T1–T2 that is a filing, live technical observation,
   the institution's own materials, or a job posting. Logix calibration: 15
   of 32 rows are single-source; of those, live-observation rows (TS-014
   Cloudflare headers) pass, scan-only rows (TS-029 Avaya, TS-030 Marketo)
   fail.
3. **Material**: mapped to a DMA layer with `linked_subcap_ids` non-empty.
   Generic web-presence/martech (Logix TS-016 HubSpot CMS, TS-017 GA/GTM/
   Hotjar, TS-027 iCIMS careers portal) fails materiality unless its
   `dma_impact` names a scored capability it moves — TS-017's DATA-layer
   placement inflating `layers[].detected` is the measured defect.
4. **Correctly attributed**: `identity_ok IS NOT FALSE` on every cited row.
5. **Tier rule preserved**: a machine technographic scan is **T1, never T4**
   (single-sourced in `02-inputs/clay_taxonomy.json`, rendered by
   `clay_plan.py --tier-table` into `02-inputs/2-clay-enrichment.md`; MEM measurement: re-registering at T1 gained +0.85 mean ERS).

Applied to Logix today this serves 9 CONFIRMED − 2 noise (TS-016 martech via
materiality, TS-027 careers) + 1 ABSENT = **8 rows customer-facing**, 32
internal. Enforced as the serve-side allowlist filter (D1 mechanism) plus a
submit-time warn (not block) when a CONFIRMED row is single-source scan-only.

## D5 · The subcap-to-evidence labeled set

**Decision.** The labeled set lives at
`fixtures/linkage_labels_logix.json`: 60 rows of
`(subcap_id, e_id, label ∈ {STRONG, WEAK, ABSENT}, why)` built from Logix —
seeded with the 15 adjudicated triples (8 STRONG, 4 WEAK, 3 ABSENT, recorded
in the Phase-0 engine-linkage report with the page's own synthesis text as
the justification), extended to 60 by adjudicating the measured divergence
set: 31 page-cited-but-unlinked pairs and 90 table-linked-but-uncited pairs
(66 pairs overlap cleanly). Precision/recall harness:
`scripts/tests/test_linkage_against_labels.py` — a STRONG label missing from
both page and table is a recall failure; an ABSENT label present as a page
citation is a precision failure; **any mislink, orphan, or phantom is a hard
test failure**, per the brief. Baseline measured 2026-08-19: 97 page pairs,
156 table pairs, 66 overlap — the divergence itself is finding-worthy and is
recorded.

## D6 · Model pinning

**Decision** (constraint [C]: static front matter only, from what the repo
exposes today — 8 agents on `model: opus`, 4 producers on `model: sonnet`):

| Role | Agent(s) | Pin |
|---|---|---|
| Reasoner / adjudicator | surface-producer, finding-challenger, page-consolidator, adversarial-verifier, qa-overseer, rectifier, deployed-app-auditor, package-vetter | `opus` (as today) |
| Producers (mechanical card units) | 4 per-page producers | `sonnet` (as today) |
| **Grader** | new `learning-grader` agent | `claude-sonnet-5`, maxTurns 40 |
| **Test generator** | new `learning-testgen` agent | `claude-haiku-4-5-20251001`, maxTurns 60 |

Grader and test generator are independent of the fixer (anti-gaming): neither
carries Write/Edit nor any connector write tool; both return structured
verdicts the rectifier consumes.

## D7 · The learning sequence and the held-out client

**Decision** (from the live queue: 287 pending, 172 distinct, 109 surplus
duplicates, every client 7-facets-never-enriched):

- **Learners, in order:** 1) T. Rowe Price (v7.0, 595 cells, 874 evidence
  rows all excerpted — the cleanest), 2) Houlihan Lokey (v7.0, CIB, 0 dated
  evidence — exercises UNVERIFIED banding), 3) Hughes FCU (v7.0, CU, same
  sub-vertical as the references), 4) SL Green (v5.0, REIT — unusual
  sub-vertical + v5.0 path), 5) Corporate America CU (corporate-CU subtype,
  twin-folder ingest history).
- **Stress profiles:** brick-city-capital (14 cells — sparse), thrivent (696
  cells, 0 excerpts, 0 links — the no-rows platform-fit failure), bank-of-utah
  (PENDING_REVIEW identity, undated).
- **Held-out (never learned from):** **BOK Financial** — v7.0, 650 cells,
  balanced on every axis, ACTIVE; its PENDING_REVIEW twin (`bok-financial`)
  is adjudicated before the run starts.
- Twin-entity adjudications (fpcu/hapo/hvcu/patelco/slg) and the 109
  duplicate rows are resolved by the dedup rules already implemented in the
  worker (artefact priority → newer completion → section count → lexicographic;
  losers marked, never deleted) — `is_latest_for_request=true` picks work.
- Mix note: the corpus is 87% v5.0 but the learners bias v7.0 deliberately —
  v7.0 is the current catalogue and the serving future; SL Green + Corporate
  America carry the v5.0 path so both lineages stay exercised. Assumption
  logged for review.

---

*Standing constraint acknowledgements:* the connector remains a data bridge
([A]) — every gate/allowlist change here ships through the repo and CI/CD;
rulebooks load structurally through the skill, never a hook ([E]); the
authoritative exclusion gate is `apps/mcp` + `apps/api` server code with the
client mirror failing open ([F]); the `precheck_gates.py` invocation anchor
fix is [G].


## D8 · Connector identity: open ingress, in-app gate, "DMA Insights" by name

Owner, 2026-08-20. The connector must be reachable from claude.ai's
custom-connector dialog and "anyone with the @zennify domain is authorized";
its display name — in its own initialize response, in the claude.ai install,
and in every document — is **DMA Insights**.

The dialog's client speaks OAuth, not Google IAM, so the 2026-08-16
IAM-closed posture could not serve it. Resolution: ingress reopened and the
identity check moved INTO the app (`apps/mcp/dma_mcp/oauth_gate.py`), which
reads more than IAM did, not less — the 2026-08-16 lesson ("nothing on the
other side read it") is honoured by construction:

- **Rung A — Google-signed ID token**: the routine service account
  (audience must be the service URL), or any verified `@zennify.com`
  account (service URL or the gcloud CLI audience). The plugin path is
  unchanged.
- **Rung B — Google OAuth access token**: minted through the pre-registered
  **DMA Insights** Google OAuth client (Secret Manager:
  `dmai-oauth-client-id`, `dmai-oauth-client-secret`); audience must be
  that client (the anti-passthrough property) and the email a verified
  `@zennify.com` address.
- **Revised the same day, after measuring what a generic OAuth client
  actually needs.** Google cannot BE the authorization server here: it
  publishes no `registration_endpoint`, so a client that registers
  dynamically — which the claude.ai dialog does — has nowhere to register;
  and it issues a refresh token only for `access_type=offline` plus
  `prompt=consent`, proprietary parameters a standard client never sends,
  so the connection died hourly and had to be re-made. This app therefore
  IS the authorization server (`apps/mcp/dma_mcp/oauth_as.py`): it
  registers clients, runs authorization-code with mandatory PKCE S256,
  and issues its own access and refresh tokens, all HMAC-signed and
  stateless. It holds the Google client secret (`dmai-oauth-client-secret`)
  because it performs the code exchange, and a signing key
  (`dmai-oauth-signing-key`) that mints and verifies its own tokens;
  rotating that key revokes every token issued. Google remains the
  IDENTITY PROVIDER and still decides who the person is.
- Discovery (`/.well-known/oauth-protected-resource`) is public; every 401
  carries the `WWW-Authenticate` metadata pointer the dialog follows.
- The capability path token stays as defense in depth on the service path;
  authenticated callers reach bare `/mcp` without it. Rotation story
  unchanged.
- The IAM `domain:zennify.com` / deployer invoker grants remain in
  `infra/deploy.sh`: inert under open ingress, load-bearing again if
  ingress is ever re-closed.
