# Second-pass verification of the 20 claims the spend limit left unchecked

Verified in-process after Workflow/Agent tools were disabled. Method rule applied throughout:
**measure the same thing a different way**, never re-run the claimant's command.

## V1 — "run_seq is allocated by an unguarded read-modify-write" — PARTIALLY REFUTED

- **"Read-modify-write": HOLDS.** `apps/worker/dma_worker/persist.py:394-395` is
  `SELECT COALESCE(max(run_seq),0)+1 FROM runs WHERE entity_id=%s` followed by
  `run_seq = cur.fetchone()[0]` — no `FOR UPDATE`, no sequence.
- **"No unique constraint": HOLDS.** `pg_indexes` on `runs` returns 4 — `runs_pkey`,
  `runs_active_uq` (entity_id WHERE is_active), `runs_source_artefact_uq`, `runs_withdrawn`.
  **None covers `(entity_id, run_seq)`.**
- **"Unguarded": REFUTED for the current path.** `job_main.py:862` takes
  `pg_try_advisory_lock(815002)` *before* the scan, and `persist_package` is reached from
  `_ingest_one` inside it. The comment names this exact race: *"One scan at a time: the
  Scheduler fires every 30 minutes and manual executions overlap it — a second execution
  exits clean instead of racing the diff into duplicate runs."*

**Corrected claim, and it is sharper than the original for this audit's question:** the
database permits a duplicate `(entity_id, run_seq)` and only an *application-level* advisory
lock in `job_main.py` prevents one. **Retire the Drive scan and the guard goes with it** — a
Slack or Routine intake path that creates runs outside `job_main.py` inherits no protection,
because the constraint that would have caught it was never added. Severity MAJOR stands; the
mechanism changes from "no guard" to "the only guard is the component being removed".

## V2 — "strip_working_area.py and patch_validator.py do not exist" — CONFIRMED
Different method: a filesystem walk rather than a repo grep.
`find / -name 'strip_working_area*' -o -name 'patch_validator*'` returns **nothing** outside my
own audit prompt — absent from the repo, the v4.2 archive, and every installed package.

## V3 — "No production code path runs a workbook validator" — CONFIRMED
Different method: call-site search across the deployables, excluding tests.
`grep -rn 'validate_workbook' apps/ packages/ migrations/ scripts/ infra/ --include='*.py'
--include='*.sh' --include='*.yml' | grep -v /tests/` returns **zero**. The validator exists only
in the archive and is invoked only by prose.

## V4 — "parser_observations is written durably and read by nothing" — CONFIRMED
Different method: reader search across every service other than the writer.
The only non-worker references are two `DELETE` cleanups in `apps/mcp/tests/`. Zero readers in
`apps/api`, non-test `apps/mcp`, `apps/web`, `packages`, `scripts`, `infra`. The intake failure
record has one writer and no consumer.

## V5 — "qa_auditor.py cannot tell a good workbook from a garbage one" — CONFIRMED, AND THE CAUSE IS WORSE
Different method: I built both fixtures myself and then diagnosed *why*, rather than observing
that the outputs matched.

Both a varied workbook and a degenerate one (every score 3.0, one rationale repeated 240 times,
`E-001` everywhere) produce **byte-identical output**: `QA audit complete: 0/0 checks passed`,
the same 4 issues, verdict **FAIL**, and **exit code 0**.

**The cause is a sheet-name mismatch, and it is systemic across the whole governance layer.**
`qa_auditor.py:117` looks for `P{n}_Scoring_Detail`; `grep -c 'Subcap_Scoring' qa_auditor.py`
= **0**. So does `generate_governance_outputs.py:363`, and so does
`dma-governance/scripts/gov_auditor.py:59-60,68` — whose remediation text even reads *"Populate
P1-P4_Scoring_Detail sheets"*.

Against that, `apps/worker/dma_worker/workbook_parser.py:264-276` settled the question by
measurement: `P{n}_Subcap_Scoring` is authoritative and `_Scoring_Detail` is *"the calculation
chain behind it — pre-critic, intermediate, and not what the summary sheets cite."* Contract v3
does not ship `_Scoring_Detail` at all.

**Consequence, and it answers Stage 8 directly:** the governance `ISS-XXX` issue register — the
deliverable the owner wants published to the app — is not merely unpublishable, it is
**unproducible**. The three tools that write it cannot read the workbook the pipeline now
produces. Run against a contract-v3 workbook they execute **0 of 6 check families** and emit
four false `CRITICAL` "Missing sheet" rows *as* the register. And `qa_auditor.py` writes
`qa_results/` into the current working directory, which in a repo-rooted session is the repo.

**Also unmeasured until now:** `qa_auditor.py` imports `pandas`, which is declared in
`dma-assessment/scripts/requirements.txt` but is one of 7 skill scripts that need it — and
`plugins/dma-insights/scripts/audit_skills.py` classifies a missing third-party import as `env`
rather than breakage, so a runner without pandas reports these scripts healthy.
