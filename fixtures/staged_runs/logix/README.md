# Staged run fixtures

Six page payloads — `overview.json`, `insights.json`, `heatmap.json`,
`platform.json`, `context.json`, `techstack.json` — exactly as
`get_staged_payload(run_id, page)` returns them for a run the connector has
PASSED on every page.

They drive `tests/skills/test_check_payload_false_positives.py`, whose claim
is the one that cannot be made from unit fixtures: on a whole payload the
connector accepted, the local checker raises none of the four repaired
false-positive classes (AG-03, raw taxonomy code, CG-09, terminal
punctuation).

The directory is empty in the repository and those six cases skip. That is a
gap, stated rather than hidden: until 2026-08-20 the tests pointed at a
scratchpad inside a finished Claude session, so they skipped on every machine
in the world while looking like coverage.

To populate: pull the payloads for a passing run and write them here, or point
`DMA_STAGED_DIR` at a directory that already holds them.
