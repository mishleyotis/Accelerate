"""Embedder worker — produces 768-dim vectors for evidence, insights,
recommendations into the pgvector tables that power the pattern_recognition
service + the RAG /evidence endpoint.

This is the layer that actually makes the AI pattern-matching surfaces
return useful results — without it, evidence_embeddings / insight_embeddings
/ recommendation_embeddings stay empty and every pattern query returns [].

Pipeline (per run):
  1. Find artifacts for the run that have no embedding row yet (or whose
     model_version differs from the current target — handles a re-embed
     after Vertex deprecates an embedding model).
  2. Build the embedding text via the *same* canonical recipes used at
     RAG read time, so cosine distance is meaningful:
        evidence:        source_name + " · " + claim_type + " · " + excerpt
        insight:         title + " · " + what + " · " + why + " · " + so_what
        recommendation:  title + " · " + description
  3. Batch-embed (32 at a time by default) through the injected embed_fn
     callable; live IO calls Vertex text-embedding-004.
  4. UPSERT rows into the *_embeddings tables.

Idempotent: re-running the worker on a run with embeddings already in place
is a no-op (model_version match → skip).
"""
__all__ = ["main", "service"]
