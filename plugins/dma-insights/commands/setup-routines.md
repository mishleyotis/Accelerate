---
description: Reconcile the DMA Insights scheduled routines against the plugin's manifest — create what is missing, resume what is paused, correct a drifted schedule, and report any duplicate.
---

Reconcile the scheduled routines. **Report first; change nothing without being asked.**

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/setup_routines.py"
```

Read the plan back to the user and stop there. Then:

- If everything is `ok`, say so and name the four routines with their schedules.
- If anything is `MISSING`, `PAUSED` or `DRIFTED`, explain what that means for
  the product — a missing `dmai-package-scan` means **no new client is ever
  ingested**, and the app serves a frozen corpus — then offer to apply:

  ```bash
  python "${CLAUDE_PLUGIN_ROOT}/scripts/setup_routines.py" --apply \
      --service-account <the scheduler's service account>
  ```

- If anything is `DUPLICATE`, name the job and the routine it duplicates, and
  say what the duplication costs (the same work fired twice on two schedules).
  Deleting needs `--apply --delete-duplicates` **and** the user's explicit go
  ahead — this project hosts around two dozen scheduler jobs belonging to other
  systems, and although the duplicate rule matches only on identical Cloud Run
  target, a deletion is not reversible.

Never widen the duplicate rule, and never delete a job the tool did not itself
classify as a duplicate.
