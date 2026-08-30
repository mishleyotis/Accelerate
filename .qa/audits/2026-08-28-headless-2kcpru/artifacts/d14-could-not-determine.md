# Deliverable 14 — What this audit could not determine, and what would settle it

| # | Question | Why it is open | What would settle it |
|---|---|---|---|
| 1 | **Do 20 of the high-severity claims survive adversarial challenge?** | 47 of 67 planned verification agents ran (41 upheld, 6 refuted). The other **20 were killed by an account spend limit** mid-phase — `"You've hit your individual spend limit · your session limit resets 6:10pm UTC"`. All 20 were *verification* agents; every *measurement* agent completed, so the checks are done and the second opinion is missing on those 20. | Re-run the two workflows with `resumeFromRunId` after the limit resets; completed agents replay from cache, so only the 20 failures re-execute. |
| 2 | **Is production actually serving HEAD?** (`S9-07`, BLOCKED) | No gcloud SDK and no credential in this container. I verified the *wiring* — `infra/deploy.sh:489-495` does call `scripts/verify_deployed.py`, and deliberately non-fatally ("the services are already rolled by this point") — but not the byte comparison itself. | gcloud plus a service account with `roles/run.viewer` and `roles/artifactregistry.reader` on `digital-maturity-assessor`, then `verify_deployed.py` in full (not `--quick`). |
| 3 | **Does batching dilute challenge scrutiny?** (`S6-11`, BLOCKED) | The capability-size distribution is measurable and stark — 136 capabilities, median 5, largest 29, and 23 capabilities (17%) hold 29% of all subcaps — but verdict *distribution* against batch size needs real challenge records, and no archived run ledger exists in either tree. | One archived research run directory with a populated `01_evidence/ledger.jsonl` carrying `kind=verdict` records across capabilities of differing size. Then it is a one-line group-by. |
| 4 | **Which of the 69 gates have never fired in production?** | 7 of 69 have a live refusal in the current queue. The other 62 cannot be assessed: `gate_results` is empty in my local DB and no connector tool exposes production gate history. | A read of the production `gate_results` table, or a connector tool that aggregates it — neither exists among the 33. |
| 5 | **Would a Routine's connector grant survive to a dispatched child?** | Moot in practice and untested in principle: no DMA Routine carries a search connector at all, so there is nothing to propagate. The propagation question only becomes answerable once one is granted. | Grant Exa or Tavily to `dma-synthesis-sequence`, fire it, and introspect a dispatched child's tool list. |
| 6 | **Do the two report renderers produce a document that matches the pinned v8 templates?** | Neither renderer targets the pinned shape — one declares "template v6.3" and emits 5 sections plus 3 appendices against v8's 8, and `report_parser.py` expects a superseded 12-section report. I could compare *structures*, not *rendered output*, because no renderer runs end to end without a real run tree. | A completed run tree plus the templates, then render and diff section-by-section. |

## One methodological limit worth stating

The audit's own verification standard — *measuring the same thing a different way* — was applied
unevenly. Where I re-ran a claimant's command I sometimes reproduced their error rather than
testing it; the `50 of 55` routing anchors is the recorded instance, and the corrected figure is
**48 of 53**. Where a second measurement used a different method (the anchor *column* rather than a
line grep; the DB registry beside the Python registry) it caught things the first pass missed.
Twenty claims currently have only the first kind of check.
