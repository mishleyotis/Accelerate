# Gold-standard NLP: the DMA Insights synthesis engine as an AI system

Goal (user mandate, 2026-07-08): the derive/enrich scripts should stop being
siloed regex passes and behave like **one AI system inside the web app** — it
adaptively extracts (even from novel folder/document structures), builds a
single cohesive understanding of each client, **challenges its own evidence and
resolves contradictions before surfacing anything**, and writes AE-ready,
almost-human, deeply-grounded storylines. Counterchecked against the
Claude-written overlays (the gold standard) across **all 94** reports, and
built to generalize to new/varied reports.

## The reconciliation that makes "non-deterministic" safe to ship

Non-deterministic *reasoning*, deterministic *artifact*:

- The system **generates once** at ingest/regen (LLM-hot), **persists** the
  output keyed by an input fingerprint (`synthesis_orchestrator`), and **serves
  that forever** — zero tokens per reload, and the committed pack is stable so
  the pack-parity gate holds. Re-generation fires only when inputs change.
- Cold CI / credential-less regen falls back to the **grounded deterministic
  tier** (the enhanced scripts + `SemanticIndex` TF-IDF fallback), so a build
  never blocks on Vertex and never fabricates.

So "gold-standard, super-intelligent, non-deterministic" == LLM-grade synthesis,
adversarially grounded, persisted, with a deterministic safety net.

## Layers (each surface flows through all of them)

**L0 — Adaptive extraction.** Classify/route each package's folders + documents;
when a structure is unknown, an LLM structure-classifier maps it to the canonical
`report_sections` / evidence schema (heuristic + `en_core_web_sm` fallback). New
folder/doc shapes are learned into a routing memory, not hard-failed.

**L1 — Shared EntityKnowledge (anti-silo).** One canonical per-entity state built
once and read by *every* surface composer: canonical capabilities (via
`CatalogueResolver`, one label per subcap), the embedded evidence corpus
(`SemanticIndex`), scores, financials, leadership, tech stack, signals, and the
resolved contradiction set. A fact surfaced on one card is *retrievable by any
other script* for supplemental grounding — cohesive, never duplicated.

**L2 — Adversarial grounding (`nlp/knowledge.py` + `nlp/contradiction`).** Every
claim is challenged before it can surface:
 1. *Topical support* — the cited evidence must be semantically aligned to the
    claim's capability (`SemanticIndex.relevance` ≥ threshold), else the citation
    is dropped/replaced (kills the exec-roster-under-"Speed-to-Lead"
    misattribution).
 2. *Ownership* — a figure whose subject is a peer/benchmark is rejected (peer
    NPS fence).
 3. *Freshness/tier* — stale or low-tier evidence is down-weighted.
 4. *Contradiction* — opposing claims about the same subject are detected
    (semantic same-subject + polarity opposition) and **resolved** (higher tier
    → more recent → client-owned → more specific wins); the loser is suppressed
    and the resolution noted, never surfaced as a conflict.

**L3 — Generative synthesis (non-deterministic, persisted).** Vertex composes
each surface from the *grounded* knowledge state — key-message-first, storyline-
coherent, human-like — then a citation validator asserts every claim maps to a
verified in-corpus E-ID (fail-closed → deterministic composer). Persisted via
`synthesis_orchestrator`.

**L4 — Storyline cohesion.** A single transformation thesis per entity threads
focus → why-now → insight cards → platform → recommendations, consistently
labelled. Cross-surface consistency checks run before export.

**L5 — Completeness critic + self-repair.** A final pass asks "what is missing,
ungrounded, or internally inconsistent?" and loops the offending surface.

## Industry-grade stack (offline, baked into the image)

- **sentence-transformers / all-MiniLM-L6-v2** — semantic topical alignment,
  contradiction same-subject detection, evidence dedup (`nlp/semantic.py`).
- **spaCy `en_core_web_sm`** — NER, sentence/clause segmentation, noun-phrase
  key-messages.
- **scikit-learn** — TF-IDF fallback tier + clustering (trend/archetype).
- **rapidfuzz** — fuzzy seat/label/entity reconciliation + dedup.
- **dateparser** — robust FY/event dating.
- **Vertex Gemini** (flash/pro) — L3 generative synthesis + L0 structure
  classification, persisted; deterministic fallback everywhere.

## Validation (all 94, not a sample)

Every phase re-runs the full 94-client chain and the **countercheck harness**:
(a) diff each surface vs the 5 committed Claude overlays (gold standard); (b)
criteria scan — misattribution (TF-IDF/MiniLM), raw-dump leads, out-of-scope
anchors, pipe-row quotes, broken leadership → all driven to 0. Cross-surface
cohesion + contradiction-free assertions gated. Iterate until the deterministic
tier meets, and the LLM tier surpasses, the overlay benchmark.

## Pre-redeploy gate (MANDATORY — nothing promotes to live traffic until all pass)

1. **Per-SEGMENT enhancement countercheck (all 94).** The harness reports, for
   EACH surface/segment (SCQA, firmographics, financial trajectory, sentiment,
   leadership, top-findings, insight cards, heatmap drilldowns, platform,
   focus, evidence, why-now), the residual enhancement areas — not a single
   pass/fail. Benchmarked against every gold-standard writeup (the committed
   overlays + the quality criteria). Output is a per-segment scorecard; each
   segment must be at or above the overlay bar (defects 0, cohesion + grounding
   asserted) before ship. This is explicitly an enhancement-discovery pass, so
   any new gaps it surfaces feed another rewire round.
2. **Full production deployment SIMULATION (prod, no traffic).** Before the real
   promote we ship the whole thing THROUGH the production path and verify it
   lands cleanly, WITHOUT cutting traffic:
   - the gated **Cloud Build** pipeline runs end-to-end (backend-tests-live-PG,
     regen-startup-pack across 94, qa-gates, e2e-personas, frontend+worker
     builds, migrations dry-run) — a green build IS the ship simulation;
   - **two-phase deploy Phases 2-4**: build+push images → run migrations against
     the live DB → create a **candidate Cloud Run revision at `--no-traffic`** →
     probe its tagged URL `/readyz` (canonical migration-drift detector). This
     exercises the exact production deploy on real infra.
   - Only after the candidate serves `/readyz` green AND the per-segment
     countercheck is at benchmark does **Phase 5 (`update-traffic --to-latest`)**
     run — the single, final promote. A failed simulation blocks the promote;
     the old revision keeps 100% of traffic throughout.

## Phased build

1. Semantic tier (`nlp/semantic.py`) — **done**, proven on the FCMA case.
2. Adversarial grounding + shared knowledge (`nlp/knowledge.py`) — in progress.
3. Rewire composers (`derive_insights`/`deepen_narrative`/`section_analysis`/
   platform/focus) onto L1+L2; fix misattribution/oos/quote-provenance/leadership.
4. Bake the stack into `backend.Dockerfile` (+pyproject +cloudbuild pip-list,
   vendored MiniLM) so prod/CI get the MiniLM tier; fallback keeps CI green.
5. L3 generative synthesis + citation validator + persistence.
6. L0 adaptive extraction + L5 completeness critic.
7. Full-94 countercheck to zero; single redeploy.
