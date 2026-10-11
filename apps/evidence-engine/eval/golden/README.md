# The golden set — versioned, real, never tuned on the held-out client

Built by `eval/build_golden.py` from the staged `heatmap.evidence` sections
the connector serves for the reference runs (read with
`get_staged_payload`, saved beside the build, their sha256 pinned in each
version's `manifest.json`). Nothing here is invented.

| Version | Built | Tuning | Held-out | Reason |
|---|---|---|---|---|
| v1 | 2026-10-10 | Golden 1 (`40971653…`, the repo's named gold package) + Baxter (`c1351d25…`, the brief's) | Logix (`d7ed1d90…`) | first build; see docs/DISCOVERY.md §1 for why Golden 1 anchors tuning |

Changing the set requires a new version directory, a row in this table
with the reason, and the metric deltas across versions reported in
`docs/EVAL-REPORT.md`. Files per version:

- `tuning_positives.json` / `heldout_positives.json` — rows with a public
  URL whose excerpt meets the card contract: the sources the engine must
  re-find (`source_recall`) and the spans it must be able to verify.
- `tuning_negatives.json` / `heldout_negatives.json` — rows the engine must
  NOT reproduce, each with its `defects` (`hard_clip`,
  `not_sentence_complete`, `machine_text`, `internal_jargon`,
  `connector_or_scan_row`, `no_public_url`; `undated` alone is not a defect
  of the row but a labelling obligation: the engine returns `UNVERIFIED`).
- `manifest.json` — inputs, hashes, counts, defect census.

The directory is excluded from the engine's no-client-strings scan by
construction (it legitimately names clients); nothing under
`evidence_engine/` reads it.
