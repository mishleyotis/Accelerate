"""Customer intelligence recompute worker.

Cloud Run Job (one-shot) for backfill / manual recompute via `--entity-id`,
plus a long-lived `--subscribe` mode that consumes `dma.ingest.completed`
Pub/Sub messages and recomputes the affected entity's profile.

The recompute pipeline is pure-logic + DI:

  1. ``service.assemble_snapshots()`` rolls ACTIVE runs for the entity
     into ``customer_intelligence.RunSnapshot`` items.
  2. ``customer_intelligence.compute_profile()`` derives the deterministic
     rollup (velocity, themes, gaps, tech drift, archetype history).
  3. ``service.build_summary_payload()`` builds the Vertex Pro prompt and
     the structured-output schema; the live path calls vertex_client.
  4. ``grounding_validator`` checks every cited E-ID belongs to the
     bundled evidence; on rejection we fall back to a deterministic
     template based on the rollups.
  5. ``service.upsert_profile()`` writes/updates the
     ``customer_intelligence_profiles`` row.

Idempotency: if ``profile.computed_for_run_id`` matches the entity's
latest_run_id AND ``profile.catalogue_version`` matches the run's
catalogue, the worker returns ``idempotent_skip`` without contacting
Vertex.
"""
