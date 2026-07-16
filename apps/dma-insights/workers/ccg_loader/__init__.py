"""Capability catalogue loader — reads 4 pillar workbooks + Visualized
Schema HTML, parses 25 canonical tabs per pillar, populates the ccg_* tables.

Run as a Cloud Run Job (manual or via Cloud Scheduler hourly poll of
gs://dma-insights-catalogue-staging/). Atomic + admin-gated: writes to a
staging schema, runs validators, emits a diff for admin approval.
"""
__all__ = ["alias_bridge", "diff", "main", "parsers", "validators"]
