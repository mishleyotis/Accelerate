"""Canonical post-backfill derive + self-heal chain (single source of truth).

After `historical_backfill` loads the packages into the DB, this runs every
deterministic derive and the self-healing fills so every surface (Directory /
Overview / Insights / Heatmap / Platform / Context / TechStack / Health /
Recommendations / Intelligence) is complete for all 94 clients before anything
reads them.

WHY THIS EXISTS
  infra/cloudbuild.yaml's `qa-gates` stage used to seed the 113-package corpus
  and then run the 4 production QA harnesses with NOTHING in between — so the QA
  DB held raw-ingested rows only, the render auditor saw ~188 PARTIAL pages, and
  the self-healing audit's verify-only healers found ~660 surface gaps, FAILing
  the build (exit 9). Production never hit this because
  infra/post-deploy-refresh.sh runs the same chain after every deploy.

PARALLELISM (2026-06-18)
  The chain ran as 21 SEQUENTIAL subprocesses (~80s). qa-gates is the LAST build
  stage, so on a near-budget build the chain tipped the 2400s ceiling
  ("context deadline exceeded" mid-chain). The chain now runs as dependency-
  ordered WAVES: steps inside a wave execute CONCURRENTLY, waves run in order.
  The wave boundaries are the safety contract — two steps that write the SAME
  table are NEVER in the same wave, and a reader is never in the same wave as
  its input's writer, so concurrency introduces no row-lock contention or races.
  This roughly halves wall time AND a per-step timeout (DERIVE_STEP_TIMEOUT_SEC,
  default 300s) means a hung step (e.g. a Vertex call wedged on a network blip)
  is killed and the chain continues instead of consuming the whole budget —
  the "self-healing to avoid timeouts" the deploy needs.

CONTRACT
  - WAVES is the source of truth; STEPS is its flattening. The module SET and the
    dependency invariants are locked to infra/post-deploy-refresh.sh by
    tests/test_derive_chain_contract.py (platform tags + peer medians before the
    derives that read them; heal_entities before derive_financials; the `heal_*`
    completeness fills last).
  - Best-effort per step: a step's failure/timeout is logged and the chain
    continues. enrich_corpus + intelligence_recompute are honest-cold/best-effort
    (SOFT_STEPS) — their non-zero/timeout never fails the chain. A non-zero from
    any OTHER (deterministic) step is a real crash and makes the chain exit 1 so
    CI surfaces it — render/heal completeness is ultimately enforced by the
    downstream QA harnesses (qa_render_validation + qa_self_healing_learning_audit
    run the `heal_* --verify-only` gates).
  - Idempotent: every step is fill-if-empty / no-op on unchanged data, so the
    whole chain re-runs with no drift and no duplicate rows.

Exit: 0 when every deterministic step succeeded; 1 if one crashed/timed out.
`--list` prints the canonical step list (flattened) and exits 0.

Usage:
  DATABASE_URL=... python -m app.scripts.run_derive_chain [--list]
"""
from __future__ import annotations

import concurrent.futures
import os
import subprocess
import sys
import time
from pathlib import Path

# Dependency-ordered WAVES. Steps WITHIN a wave run concurrently; waves run in
# order. SAFETY INVARIANT (do not break when editing): no two steps in the same
# wave write the same table, and no step shares a wave with the writer of a
# table it reads. The firmographics writers (heal_entities → derive_sentiment →
# derive_leadership → derive_financials → heal_all_stages) are therefore spread
# across distinct waves, and the two subcap_scores writers
# (apply_catalogue_platforms, broadcast_peer_medians) are in different waves.
WAVES: list[list[tuple[str, list[str]]]] = [
    # 0. Catalogue-presence guard — GUARANTEE ccg_l3_platforms/ccg_l4_features
    #    are populated before any catalogue-reading step. apply_catalogue_
    #    platforms (wave 2) re-parses the workbooks itself, but recompute_
    #    platform_fit (wave 5), platform_affinity.load_catalogue_affinity and
    #    enrich_corpus (wave 7) read the DB catalogue tables; on an empty
    #    catalogue the platform-fit L3/L4-coverage factor collapses to its
    #    neutral prior and enrichment loses its capability grounding. In prod
    #    the hourly ccg_loader cron keeps them populated; this self-heals the
    #    fresh-DB / disabled-cron / failed-load cases. Idempotent COUNT no-op
    #    when present; runs the ccg_loader when thin. SOFT — never blocks.
    [("app.scripts.ensure_catalogue", [])],
    # 1. Foundation — fixes the ACTIVE entity set everything else reads.
    [("app.scripts.repark_junk_entities", [])],
    # 2. Disjoint bases: subcap platform tags · firmographics heal · run dates ·
    #    evidence recency · issue register. (derive_peers READS subcap_scores +
    #    runs, so it is held back to wave 5 — after both subcap_scores writers
    #    settle — to stay deterministic; co-waving it with apply_catalogue_
    #    platforms made its peer-match count flake by ±1.)
    [("app.scripts.apply_catalogue_platforms", []),
     ("app.scripts.heal_entities", []),
     ("app.scripts.backfill_run_dates", []),
     ("app.scripts.backfill_recency", []),
     ("app.scripts.derive_issues", [])],
    # 3. Reads of wave-2 writes, still pairwise table-disjoint: peer medians
    #    (subcap_scores) · tech stack (needs platform tags) · sentiment
    #    (firmographics) · timeline · alerts.
    [("app.scripts.broadcast_peer_medians", []),
     ("app.scripts.clean_techstack", []),
     ("app.scripts.derive_sentiment", []),
     ("app.scripts.derive_context", []),
     ("app.scripts.derive_alerts", [])],
    # 3b. Ground still-unlinked evidence to subcaps via NLP similarity (Part
    #     6.3 roll-up) so heatmap synthesis drawers render evidence for the
    #     clients whose packages carried no subcap tags. Sole evidence_index
    #     writer in this wave (fills only EMPTY linked_subcap_ids — never
    #     clobbers clean_techstack's tech links, which settled in wave 3);
    #     linked_subcap_ids is consumed at export, so nothing downstream races.
    [("app.scripts.link_evidence_subcaps", [])],
    # 4. Insights (needs platform tags + peer medians) · leadership
    #    (firmographics) · recommendations.
    [("app.scripts.derive_insights", ["--force"]),
     ("app.scripts.derive_leadership", []),
     ("app.scripts.derive_recommendations", [])],
    # 5. Focus areas (needs insights) · financials (firmographics, needs heal) ·
    #    peer roster (reads now-settled subcap_scores; no runs/subcap_scores
    #    writer in this wave so the match is deterministic) · platform fit v2
    #    (reads subcap_scores + insight_cards + tech_stack_entries +
    #    recommendations — all settled by wave 4 — and writes ONLY
    #    platform_scores). Disjoint tables: focus_areas · firmographics ·
    #    entity_peers · platform_scores.
    [("app.scripts.derive_focus_areas", []),
     ("app.scripts.derive_financials", []),
     ("app.scripts.derive_peers", []),
     ("app.scripts.recompute_platform_fit", [])],
    # 6. Narrative deepening — reads insights + focus areas, writes runs +
    #    insight_cards + focus_areas, so it runs alone.
    [("app.scripts.deepen_narrative", [])],
    # 7. Best-effort, Vertex-cold-safe, disjoint tables (cache · profiles) ·
    #    per-subcap narrative floor (sole subcap_narratives writer; reads
    #    wave-4/6-settled insight_cards + recommendations; deterministic,
    #    so NOT a SOFT_STEP).
    # --surfaces all: parity with the regen bake — the default surface
    # set (why_now,platform_story) never sweeps firmographics_extraction
    # / thought_leadership_extraction, so the live-DB qa_gemini_baked
    # gate FAILed on every post-deploy refresh (2026-07-06).
    [("app.scripts.enrich_corpus", ["--surfaces", "all"]),
     ("workers.intelligence_recompute.main", ["--all"]),
     ("app.scripts.derive_subcap_narratives", []),
     # D1 "Evidence & benchmarks" surfaces (runs.evidence_summary /
     # coverage_stats / uncertainty_bands). Writes ONLY runs columns; the
     # other wave-7 steps write vertex cache / profiles / subcap_narratives —
     # disjoint. The last runs-writer (deepen_narrative) is wave 6.
     ("app.scripts.derive_evidence_surfaces", []),
     # D6 Health "cross-entity recurring patterns" — sole cross_entity_patterns
     # writer (disjoint from the cache/profiles/subcap_narratives/runs writers
     # above). Deterministic recurrence count over now-settled subcap_scores +
     # issue_register (waves 2-3); cross-entity so it reads the whole corpus but
     # writes a table nothing else touches. SOFT: a cohort/analytics edge case
     # must never fail the chain, and the panel is non-critical.
     ("workers.cross_entity_patterns.main", ["--all"])],
    # 7b. Gap-driven Gemini enrichment for rendered EMPTIES (all-94 census
    #     2026-07-04): sentiment / acquisitions / financial series /
    #     timeline / insight-gen / focus subcaps / tech evidence. It
    #     fill-if-empty-writes firmographics, timeline_events, insight_cards,
    #     focus_areas and tech_stack_entries. De-duped (no token overlap):
    #     firmographics_extraction DEFERS founded/hq/headcount to 7c, and
    #     focus_kpi_extraction is SUPERSEDED by 7d. Vertex-cold ⇒ probes run,
    #     nothing written (SOFT_STEP). Runs alone (its tables are 7c/7d's too).
    [("app.scripts.enrich_empty_surfaces", [])],
    # 7c. Iterative, ledgered firmographics enrichment for the data-UNAVAILABILITY
    #     fields it OWNS (headcount / hq / assets / regulator / founded). Separate
    #     wave from 7b/7d — shares firmographics + evidence_index + ledger, so it
    #     must not write concurrently. --max-calls bounds per-deploy Vertex spend;
    #     unreached gaps stay pending for the next deploy (SOFT_STEP).
    [("app.scripts.enrich_unavailable", ["--max-calls", "300"])],
    # 7d. Rich-context focus-area KPI enrichment (baseline+target from the DMA
    #     narrative) → focus_area_kpi_overrides + citable evidence. Separate wave
    #     (shares evidence_index + ledger with 7c). SOFT_STEP.
    [("app.scripts.enrich_focus_kpis", ["--max-calls", "300"])],
    # 7e. Deep-research autopilot, leg 1 — all-surface empties census: every
    #     web-verifiable gap (firmographics identity fields, leadership
    #     seats, undated timelines, KPI-less focus areas, thin tech stacks,
    #     zero-evidence cards) files an idempotent G2/G3 clarification into
    #     the research queue. Deterministic, no network, writes only the
    #     queue JSONL + trigger ledger.
    [("app.scripts.route_empty_surfaces", [])],
    # 7f. Leg 2 — the crawler answers open queue rows with cited, debris-
    #     filtered excerpts (pending_review). Network-dependent → SOFT: a
    #     fenced/download-less deploy leaves the queue open for next time.
    [("app.scripts.research_worker", ["--max-rows", "60"])],
    # 7g. Leg 3 — validated answers fold back into evidence_index with
    #     crawler provenance (tier by source kind, strict full-date gate)
    #     and repair the timeline dates their G2s name. Idempotent via the
    #     promoted-keys ledger + (run_id, e_id) upsert; offline ⇒ 0 rows,
    #     exit 0. Writes evidence_index + timeline_events — both settled
    #     (3b / wave 3) and re-audited by heal_all_stages after.
    [("app.scripts.promote_research_answers", [])],
    # 8. All-stages completeness gate — heals firmographics + audits every
    #    surface; MUST run last, after every derive has filled its stage.
    [("app.scripts.heal_all_stages", [])],
]

# Flattened canonical order (callers / --list / the contract test).
STEPS: list[tuple[str, list[str]]] = [step for wave in WAVES for step in wave]

# Steps allowed to exit non-zero / time out without failing the chain: the
# Vertex warm sweeps + the intelligence worker are honest-cold / best-effort
# (the deterministic fallbacks already populate every REQUIRED field).
# 2026-07-05: the two enrichment sweeps are now bounded-parallel + wall-
# clock budgeted (services.enrichment_runner) and CLAMP their budget under
# DERIVE_STEP_TIMEOUT_SEC, so in practice they exit 0 with remaining-work
# counters (resumable via cache fingerprints) instead of being SIGKILLed
# here — the SOFT classification stays as the safety net.
SOFT_STEPS = {"app.scripts.enrich_corpus", "workers.intelligence_recompute.main",
              "app.scripts.enrich_empty_surfaces", "app.scripts.enrich_unavailable",
              "app.scripts.enrich_focus_kpis", "workers.cross_entity_patterns.main",
              # best-effort catalogue self-heal (idempotent; hourly cron backstops)
              "app.scripts.ensure_catalogue",
              # network-dependent crawler leg of the research autopilot
              "app.scripts.research_worker"}

# Self-healing: cap each step so a wedged process (e.g. a Vertex call hung on a
# network blip) can't consume the build budget. Overridable for slow envs.
STEP_TIMEOUT_SEC = int(os.environ.get("DERIVE_STEP_TIMEOUT_SEC", "300"))


def _run_step(mod: str, args: list[str]) -> tuple[str, int, float, str, str]:
    """Run one step as an isolated subprocess with a hard timeout. Returns
    (label, returncode, seconds, summary). returncode 124 == timed out."""
    label = " ".join([mod, *args])
    t0 = time.monotonic()
    # workers.* steps: in the prod image `workers/` sits beside `app/` at
    # /home/app so `-m workers.…` resolves via cwd. In a bare checkout the
    # package lives at apps/dma-insights/workers (a SIBLING of backend/), so
    # the two workers steps died in 0s with ModuleNotFoundError on every
    # local §6.10 simulate run (2026-07-10 redeployment QA). Append the app
    # dir's parent (…/apps/dma-insights) to PYTHONPATH — a no-op in the
    # image, a fix in the checkout.
    _workers_parent = str(Path(__file__).resolve().parents[3])
    _pypath = os.environ.get("PYTHONPATH", "")
    step_env = {
        **os.environ,
        "PYTHONPATH": (f"{_pypath}{os.pathsep}{_workers_parent}"
                       if _pypath else _workers_parent),
        # Thread the ACTUAL kill timeout to the child so rerank.py's
        # auto-scaling cross-encoder budget (= ½ this) always tracks the
        # real SIGKILL deadline, not an independently-defaulted 300s.
        "DERIVE_STEP_TIMEOUT_SEC": str(STEP_TIMEOUT_SEC),
    }
    try:
        proc = subprocess.run(
            [sys.executable, "-m", mod, *args],
            capture_output=True, text=True, timeout=STEP_TIMEOUT_SEC,
            env=step_env,
        )
        rc, out = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:
        rc = 124
        out = (exc.stdout or "") + (exc.stderr or "") if isinstance(exc.stdout, str) else ""
        out += f"\n[run_derive_chain] killed after {STEP_TIMEOUT_SEC}s timeout"
    dt = time.monotonic() - t0
    summary = next((ln for ln in out.splitlines() if ln.startswith("# ")), "").strip()
    # Failure tail: the ONE line the old report kept ("TypeError: …") hides
    # the crash site entirely — the 2026-07-11 post-deploy refresh burned a
    # diagnosis cycle because neither failing step's traceback survived into
    # Cloud Logging. Keep the last 30 lines on non-zero exit.
    tail = "\n".join(out.splitlines()[-30:]) if rc != 0 and out.strip() else ""
    return (label, rc, dt,
            (summary or out.splitlines()[-1] if out.strip() else summary), tail)


def main() -> None:
    if "--list" in sys.argv[1:]:
        for mod, args in STEPS:
            print(" ".join([mod, *args]))
        raise SystemExit(0)

    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        raise SystemExit(2)

    failed_hard: list[str] = []
    failed_soft: list[str] = []
    # Observability (NLP_DEGRADED contract): report the NLP tier ONCE at chain
    # start so a permanently-degraded platform (spaCy model or scikit-learn
    # absent from the image) is visible to operators instead of silently
    # dropping surface quality. Never fatal — degradation is graceful.
    from app.services.nlp import tier_health
    try:
        from app.services.nlp import get_nlp, is_degraded
        from app.services.nlp.similarity import _build_matrix
        get_nlp()
        spacy_ok = not is_degraded()
        sim_ok = _build_matrix(["a b c", "b c d"]) is not None
        tier = "FULL" if (spacy_ok and sim_ok) else "DEGRADED"
        print(f"# run_derive_chain: NLP tier={tier} "
              f"(spacy={'on' if spacy_ok else 'REGEX'} "
              f"similarity={'on' if sim_ok else 'OFF'})", flush=True)
        # Semantic (MiniLM bi-encoder) + cross-encoder tiers — surface the
        # silent-degrade case (2026-07-14 audit): if the baked model is
        # missing the whole corpus quietly drops to TF-IDF.
        st = tier_health.tier_status()
        sm, ce = st["semantic_minilm"], st["cross_encoder"]
        print(f"# run_derive_chain: semantic={'on' if sm['available'] else 'OFF(' + str(sm['reason']) + ')'} "
              f"cross_encoder={'on' if ce['available'] else 'OFF(' + str(ce['reason']) + ')'}",
              flush=True)
    except Exception as exc:  # never block the chain on a probe
        print(f"# run_derive_chain: NLP tier probe skipped ({exc})", flush=True)
    # Fail-loud preflight (production opt-in): when DMA_REQUIRE_SEMANTIC=1 a
    # missing/broken baked MiniLM model is fatal here rather than silently
    # serving a TF-IDF corpus. A deliberate DMA_DISABLE_SEMANTIC=1 opt-out is
    # honoured. Intentionally OUTSIDE the swallow-all probe above.
    tier_health.require_semantic_tier()
    print(f"# run_derive_chain: {len(STEPS)} steps in {len(WAVES)} waves "
          f"(step timeout {STEP_TIMEOUT_SEC}s)", flush=True)

    for wi, wave in enumerate(WAVES, start=1):
        labels = ", ".join(m for m, _ in wave)
        print(f"--- wave {wi}/{len(WAVES)} [{len(wave)} parallel]: {labels}", flush=True)
        # Each wave's steps write disjoint tables, so concurrency is race-free.
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(wave)) as ex:
            results = list(ex.map(lambda s: _run_step(s[0], s[1]), wave))
        for (mod, _args), (label, rc, dt, summary, tail) in zip(wave, results, strict=True):
            if rc == 0:
                print(f"  ✓ {label} ({dt:.0f}s) {summary[:88]}", flush=True)
            elif mod in SOFT_STEPS:
                failed_soft.append(label)
                why = "timeout" if rc == 124 else f"exit {rc}"
                print(f"  ⚠ {label} {why} ({dt:.0f}s) — best-effort, continuing", flush=True)
            else:
                failed_hard.append(label)
                why = "TIMED OUT" if rc == 124 else f"exit {rc}"
                print(f"  ✗ {label} {why} ({dt:.0f}s)", flush=True)
                if summary:
                    print(f"      {summary[:200]}", flush=True)
                if tail:
                    print(f"      ──── {label} output tail ────", flush=True)
                    for ln in tail.splitlines():
                        print(f"      │ {ln[:300]}", flush=True)

    ok = len(STEPS) - len(failed_hard) - len(failed_soft)
    print(f"# run_derive_chain done: {ok} ok, {len(failed_hard)} failed, "
          f"{len(failed_soft)} soft-failed (of {len(STEPS)})", flush=True)
    raise SystemExit(1 if failed_hard else 0)


if __name__ == "__main__":
    main()
