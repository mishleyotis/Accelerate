"""evidence_crawler — a resilient, cross-encoder-grounded backfiller for
evidence rows whose citation has a URL but no excerpt.

Why: ~11% of evidence rows carry a real ``source_url`` (SEC, GlobeNewswire,
company IR sites, …) but arrived with no quoted excerpt, so their heatmap /
drawer citations render a bare link. This worker fetches the ACTUAL cited page
and lifts the passage that best supports the linked capability — never invents
one (a fabricated quote is worse than a missing one), so a fetch failure leaves
the row honestly empty.

Pipeline: fetch (SSRF-gated, robots-honored, budget-bounded) → extract passages
→ cross-encoder support-score against the capability → keep the top passage iff
it clears the same support floor every other citation is held to.

Runs as a Cloud Run Job (out of band from the hermetic qa-gates derive chain,
which must not touch the network), idempotent + additive so re-runs only fill
still-empty rows. State matrix:
  no excerpt-empty rows with a URL      → exits 0, no-op summary
  host trips the circuit breaker        → skipped for the rest of the run
  fetch fails / non-public IP / robots  → row left empty (counted, not fatal)
  no passage clears the support floor   → row left empty (honest)
  --dry-run                             → fetches + scores, writes nothing
"""
