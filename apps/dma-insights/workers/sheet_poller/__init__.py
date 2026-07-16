"""DMA Ops Sheet poller — mirrors 8 tabs into ops_* tables.

Cloud Run Job triggered every 5 min during business hours (hourly otherwise)
by Cloud Scheduler. Per-tab handlers normalize sheet rows into local SQL
rows and emit SSE events on Requests state transitions.
"""
__all__ = ["handlers", "main"]
