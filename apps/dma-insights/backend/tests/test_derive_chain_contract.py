"""Lock the post-backfill derive/heal chain to ONE definition.

`app.scripts.run_derive_chain.STEPS` is the single source of truth for the
ordered derive + self-heal chain. Three consumers must agree, or a fresh
deploy / qa-gates run will silently under-populate surfaces (the bug that made
qa-gates exit 9: corpus seeded, but no derive chain → ~188 PARTIAL renders +
~660 self-healing surface gaps):

  1. infra/post-deploy-refresh.sh runs `run_derive_chain` as ONE Cloud Run Job
     execution after every production deploy (2026-06-18: it used to fire the
     21 modules as separate `--wait` execs — slow, fragile, and drift-prone;
     they ALL logged failed on the 2026-06-18 deploy and the live DB was never
     cleaned). Delegating to run_derive_chain means there is nothing to drift.
  2. infra/cloudbuild.yaml's qa-gates stage runs `run_derive_chain` BETWEEN the
     corpus seed and the QA harnesses, so the CI QA DB reaches the same state.

This test fails loudly if any of them drifts out of lockstep.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.scripts.run_derive_chain import SOFT_STEPS, STEPS, WAVES


def _infra() -> Path:
    here = Path(__file__).resolve()
    for anc in [here.parent, *here.parents]:
        if (anc / "infra" / "post-deploy-refresh.sh").exists():
            return anc / "infra"
        if (anc / "apps" / "dma-insights" / "infra" / "post-deploy-refresh.sh").exists():
            return anc / "apps" / "dma-insights" / "infra"
    raise RuntimeError("could not locate apps/dma-insights/infra")


INFRA = _infra()
REFRESH = (INFRA / "post-deploy-refresh.sh").read_text()
CLOUDBUILD = (INFRA / "cloudbuild.yaml").read_text()

# The chain's deterministic backbone — every module run as `python -m`. The two
# SOFT_STEPS (enrich_corpus, intelligence_recompute) and the trailing
# heal_all_stages are validated separately because post-deploy-refresh.sh runs
# them as their own labelled steps rather than inside the `for mod in` loop.
CHAIN_MODULES = [m for m, _ in STEPS]

# Tables written by MORE THAN ONE step. The wave parallelism is only race-free
# if no two writers of the same table share a wave (Postgres row-lock contention
# / lost-update risk). This map is the safety contract the wave test enforces;
# keep it in sync when a step's write target changes.
#
# 2026-07 data contract (migrations 045-053): the new columns on `runs`
# (evidence_summary/coverage_stats/uncertainty_bands), `insight_cards`
# (affects/platforms/interconnections/theme), `timeline_events`,
# `recommendations` (feature/phase/root_cause_e_ids/outcomes),
# `focus_areas` (grounding/financial_ref/pillars_weight) and
# `platform_scores` (fit_breakdown/sequence_rank) are covered by the
# existing entries below wherever their tables are already multi-writer.
# The NEW tables — raw_artifacts (049), client_knowledge_sections +
# knowledge_section_embeddings (050), subcap_narratives (051) — each
# have at most ONE chain writer today (raw_artifacts is backfill-only;
# subcap_narratives is written by the narrative extractor step). When a
# SECOND chain step starts writing any of them, register the table here
# so the wave-clash test can enforce the parallelism contract.
MULTI_WRITER_TABLES: dict[str, set[str]] = {
    "firmographics": {
        "app.scripts.heal_entities", "app.scripts.derive_sentiment",
        "app.scripts.derive_leadership", "app.scripts.derive_financials",
        "app.scripts.heal_all_stages",
        # Gemini enrichers that fill-if-empty firmographics (waves 7b/7c) —
        # de-duped by field ownership but still same-table writers.
        "app.scripts.enrich_empty_surfaces", "app.scripts.enrich_unavailable",
    },
    "subcap_scores": {
        "app.scripts.apply_catalogue_platforms", "app.scripts.broadcast_peer_medians",
    },
    "runs": {
        "app.scripts.backfill_run_dates", "app.scripts.derive_insights",
        "app.scripts.deepen_narrative", "app.scripts.derive_evidence_surfaces",
    },
    "insight_cards": {"app.scripts.derive_insights", "app.scripts.deepen_narrative"},
    "focus_areas": {"app.scripts.derive_focus_areas", "app.scripts.deepen_narrative"},
    # backfill_recency sets freshness (wave 2); link_evidence_subcaps fills
    # empty linked_subcap_ids via similarity (wave 3b) — different waves.
    "evidence_index": {
        "app.scripts.backfill_recency", "app.scripts.link_evidence_subcaps",
        # citable enrichment rows (E-GEM-* / E-GK-*) — waves 7c/7d, disjoint.
        "app.scripts.enrich_unavailable", "app.scripts.enrich_focus_kpis",
    },
    # The enrichment ledger is written by both iterative enrichers; they run in
    # SEPARATE waves (7c/7d) so the per-gap UPSERTs never race.
    "enrichment_ledger": {
        "app.scripts.enrich_unavailable", "app.scripts.enrich_focus_kpis",
    },
    # Part 7.1: apply_catalogue_platforms persists v1 rows at wave 2; the
    # fit-engine-v2 recompute overwrites them at wave 5 with breakdown +
    # sequence_rank. Never co-wave them.
    "platform_scores": {
        "app.scripts.apply_catalogue_platforms",
        "app.scripts.recompute_platform_fit",
    },
}


def test_steps_are_well_formed() -> None:
    # WAVE 0 is the catalogue-presence guard; the entity-set foundation follows.
    assert CHAIN_MODULES[0] == "app.scripts.ensure_catalogue"
    assert CHAIN_MODULES[1] == "app.scripts.repark_junk_entities"
    assert CHAIN_MODULES[-1] == "app.scripts.heal_all_stages", \
        "heal_all_stages must run LAST (after every derive has filled its stage)"
    assert "workers.intelligence_recompute.main" in CHAIN_MODULES
    assert set(CHAIN_MODULES) >= SOFT_STEPS
    assert len(CHAIN_MODULES) == len(set(CHAIN_MODULES)), "duplicate step in the chain"


def test_platform_and_peers_precede_derives() -> None:
    """apply_catalogue_platforms + broadcast_peer_medians MUST precede the
    derive/enrich steps that read the platform tags + peer medians they set."""
    idx = {m: i for i, m in enumerate(CHAIN_MODULES)}
    assert idx["app.scripts.apply_catalogue_platforms"] < idx["app.scripts.derive_insights"]
    assert idx["app.scripts.broadcast_peer_medians"] < idx["app.scripts.derive_insights"]
    # heal_entities must precede derive_financials (the aum fallback) + the
    # final heal_all_stages gate.
    assert idx["app.scripts.heal_entities"] < idx["app.scripts.derive_financials"]
    assert idx["app.scripts.heal_entities"] < idx["app.scripts.heal_all_stages"]
    # Part 7.1: the fit-engine-v2 recompute reads platform tags (wave 2),
    # cleaned tech stack (absent detection, wave 3) and insight severities
    # + rec dependency edges (wave 4) — it MUST run after all of them.
    recompute = idx["app.scripts.recompute_platform_fit"]
    assert idx["app.scripts.apply_catalogue_platforms"] < recompute
    assert idx["app.scripts.clean_techstack"] < recompute
    assert idx["app.scripts.derive_insights"] < recompute
    assert idx["app.scripts.derive_recommendations"] < recompute
    # The catalogue-presence guard MUST precede every catalogue-reading step:
    # the fit engine's L3/L4-coverage factor + load_catalogue_affinity read the
    # DB ccg_l4_features rows it guarantees, and enrich_corpus grounds on them.
    ensure = idx["app.scripts.ensure_catalogue"]
    assert ensure < idx["app.scripts.apply_catalogue_platforms"]
    assert ensure < recompute
    assert ensure < idx["app.scripts.enrich_corpus"]
    assert ensure == 0, "ensure_catalogue must be the very first step (wave 0)"


def test_post_deploy_refresh_invokes_run_derive_chain() -> None:
    """post-deploy-refresh.sh must run the derive/heal chain on every deploy.

    2026-06-18: it dispatches via `--update-env-vars=DMA_POST_DEPLOY_RUN=
    derive_chain` (the override that WORKS on `gcloud run jobs execute` — the
    prior `--command`/`--args` override silently failed in prod, so the chain
    never ran and the live DB kept its junk-named entities). historical_backfill's
    entrypoint routes that signal to app.scripts.run_derive_chain, running it on
    the backend image (which has the catalogue docs the chain needs)."""
    assert "DMA_POST_DEPLOY_RUN=derive_chain" in REFRESH, (
        "post-deploy-refresh.sh no longer dispatches the derive chain via "
        "DMA_POST_DEPLOY_RUN — the derived surfaces won't be filled on deploy."
    )
    # The dispatch target is wired in historical_backfill's entrypoint; assert
    # the signal→module map so the deploy signal can never drift from the module.
    hb = (INFRA.parent / "backend" / "app" / "scripts"
          / "historical_backfill.py").read_text()
    assert '"derive_chain": ("app.scripts.run_derive_chain"' in hb, (
        "historical_backfill no longer routes DMA_POST_DEPLOY_RUN=derive_chain "
        "to app.scripts.run_derive_chain."
    )
    # The parity gate after the chain must still run (also via the dispatch).
    assert "DMA_POST_DEPLOY_RUN=export_check" in REFRESH
    assert '"export_check": (' in hb and "app.scripts.export_startup_data" in hb


def test_waves_flatten_to_steps() -> None:
    """STEPS is exactly the flattening of WAVES (the source of truth)."""
    assert [s for wave in WAVES for s in wave] == STEPS
    assert WAVES[0] == [("app.scripts.ensure_catalogue", [])], "wave 0 = catalogue guard alone"
    assert WAVES[1] == [("app.scripts.repark_junk_entities", [])], "wave 1 = repark alone"
    assert WAVES[-1] == [("app.scripts.heal_all_stages", [])], "last wave = heal_all_stages alone"


def test_no_wave_runs_two_writers_of_the_same_table() -> None:
    """The parallelism safety contract: two steps that write the same table are
    NEVER in the same wave (else concurrent row writes race / deadlock). This is
    what makes running a wave's steps concurrently safe."""
    for wi, wave in enumerate(WAVES, start=1):
        mods = {m for m, _ in wave}
        for table, writers in MULTI_WRITER_TABLES.items():
            clash = mods & writers
            assert len(clash) <= 1, (
                f"wave {wi} runs {sorted(clash)} concurrently — they all write "
                f"`{table}`, which races. Split them into separate waves."
            )


def test_background_ingest_is_async_and_never_blocks_the_chain() -> None:
    """2026-06-18 ROOT CAUSE: the crawler/embedder CHAIN ran with `--wait`
    (blocking) BEFORE the derive chain, so a hung cold-start crawler ate the
    whole deploy window and the repark/heal chain never ran — the live DB kept
    its junk-named duplicate entities ('94 then defaults to the bad UI'). The
    background ingest must be fired `--async` so it can NEVER block the
    deterministic derive chain. (The chain's own ordering is locked by
    test_waves_flatten_to_steps + test_platform_and_peers_precede_derives.)"""
    m = re.search(r'for job in "\$\{CHAIN\[@\]\}"; do(?P<body>.*?)\bdone\b',
                  REFRESH, re.S)
    assert m, "CHAIN execution loop not found in post-deploy-refresh.sh"
    body = m.group("body")
    assert "--async" in body, "CHAIN jobs must be fired --async (non-blocking)"
    assert "--wait" not in body, (
        "CHAIN (crawler/embedder) must NOT use --wait — a blocking crawler "
        "hung the deploy and starved the derive chain on 2026-06-18."
    )


def test_cloudbuild_qa_gates_runs_chain_between_seed_and_harnesses() -> None:
    """qa-gates must run run_derive_chain AFTER the corpus seed and BEFORE the
    render/self-healing harnesses — the exact gap that caused exit 9."""
    seed = CLOUDBUILD.find("historical_backfill --dir /home/app/tests/fixtures")
    chain = CLOUDBUILD.find("app.scripts.run_derive_chain")
    render = CLOUDBUILD.find("app.scripts.qa_render_validation")
    selfheal = CLOUDBUILD.find("app.scripts.qa_self_healing_learning_audit")
    assert seed != -1, "qa-gates no longer seeds the corpus"
    assert chain != -1, "qa-gates no longer runs run_derive_chain — renders will be PARTIAL"
    assert render != -1 and selfheal != -1, "qa-gates harnesses missing"
    assert seed < chain < render, "run_derive_chain must run after seed, before the render harness"
    assert chain < selfheal, "run_derive_chain must run before the self-healing audit"


def test_cloudbuild_runs_full_heal_before_verify_only_audit() -> None:
    """The self-healing audit runs heal_*_--verify-only; the FULL heal
    (heal_all_stages, last in the chain) must have run first, or the verify
    gate finds the very gaps the heal would have filled (exit 9)."""
    # run_derive_chain ends with heal_all_stages (full mode); the audit only
    # runs verify-only internally. Both facts are asserted above + in STEPS.
    assert CHAIN_MODULES[-1] == "app.scripts.heal_all_stages"
