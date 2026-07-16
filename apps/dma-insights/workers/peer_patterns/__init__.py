"""Cross-DMA pattern recognition worker.

Reads every ACTIVE run's subcap_scores per subvertical, clusters entities
into N maturity archetypes via KMeans, and writes peer_archetypes rows.
The /entities/{display_id}/archetype endpoint reads from this table.
"""
__all__ = ["main", "service"]
