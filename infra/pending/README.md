# Pending connector patches

Patches built against the commit production's `mcp` service runs, which is
newer than this branch's `apps/mcp`. Apply on that base, then deploy.

## 2026-10-05-ag03-worked-absent-tile.patch

- **Base:** `origin/claude/susser-bank-assessment-0z2cay` @ `98485922`, the
  connector whose gates refused the Cross Insurance context page.
- **Why:** CG-03b requires exactly three context sentiment tiles, and AG-03
  refused a WORKED_ABSENT tile with no evidence ids. The tile item shape
  `{audience, state, rows, e_ids}` declares no absence key, so the employee
  tile could be neither emitted nor omitted. Cross Insurance's review hosts
  (Glassdoor, Indeed, BBB and its own careers page) all refuse the verifier
  with HTTP 403.
- **Change:** an item whose declared `state` is WORKED_ABSENT or UNWORKED,
  carrying no rows, asserts nothing when the SECTION's own ladder is complete
  (`_ladder_gaps == []`). A tile marked RATED, a tile with rows, or a section
  with an incomplete ladder is still refused.
- **Tests:** `apps/mcp/tests/test_ag03_worked_absent_tile.py` (4 cases). The
  full mcp suite gives 1695 passed, 0 failed; the 17 errors need pg8000 and
  error identically without the patch.
- **Apply:**
  `git checkout 98485922 && git apply infra/pending/2026-10-05-ag03-worked-absent-tile.patch && infra/deploy.sh`
- **Unblocks:** connector run `81826be0-a004-4b18-ad7d-6bddfb73d7c5` (Cross
  Insurance). Ship context with `ship_page.py ... context --claim`, then call
  `promote_run`.
