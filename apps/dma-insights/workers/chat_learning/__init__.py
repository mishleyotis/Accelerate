"""Adversarial-learning rollup worker.

Nightly job that:
  1. Embeds new chat_messages.content via text-embedding-004 (if missing).
  2. Clusters user questions via KMeans.
  3. Computes per-cluster effectiveness = weighted avg of feedback ratings
     (weight by recency).
  4. Writes one chat_learning_signals row per cluster per surface.

The /answer endpoint reads from chat_learning_signals to bias retrieval
ordering when the incoming question's embedding is close to a known
cluster centroid with high effectiveness — closing the loop.
"""
__all__ = ["main", "service"]
