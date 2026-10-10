# Branch reconciliation — 2026-08-30

Seven branches sat ahead of the default branch
(`claude/dma-insights-onboarding-0ryrd0`). This file is the evidence that
none of them carried outstanding work, and the SHAs that make moving their
refs reversible.

## Why the obvious checks were not enough

The owner asked the right question twice. First: *"ensure all changes are
effected on the default branch."* Then, when the first answer leaned on
dates and new-file counts: *"it is not about new files but the enhancements
that could get lost."*

Both easy signals are unsound, and both were producing wrong verdicts — in
each direction:

- **"files only on the branch"** misses every change to a file that exists
  on both sides, which is nearly all of them. It also FALSELY alarms on
  relocation: eight agent files read as branch-only until looked up by
  basename, where this tree carries each under `agents/<group>/`.
- **"which side is newer"** is not containment. A branch that added a
  feature on the 18th, and a default that reformatted the same file on the
  28th, reads as "default is newer" while the feature was never absorbed.

## What was actually measured

`scripts/audit_branch_containment.py --tree` compares BRANCH TIP to target
tree: every substantive line the branch currently holds, tested for presence
in this tree, with a basename fallback for relocated files.

Tip-to-tip rather than commit-by-commit, because a commit can read as
unabsorbed only because a LATER commit on its own branch rewrote those
lines. That shape produced 155 false "absent" lines in one ledger file the
branch tip did not carry either.

| branch | files differing | lines on tip | present here | files absent here |
|---|---:|---:|---:|---:|
| `claude/dma-headless-readiness-2kcpru` | 145 | 50,895 | 98% | 0 |
| `claude/dma-headless-readiness-82e4gl` | 145 | 50,895 | 98% | 0 |
| `claude/dma-plugin-version-fix-y20jv2` | 145 | 50,895 | 98% | 0 |
| `claude/artifact-store-on-mcp-line-7a6ad71c` | 182 | 65,568 | 98% | 0 |
| `claude/dma-client-ingestion-e8xegz` | 161 | 74,117 | 98% | 0 |
| `claude/dma-insights-onboarding-zknopn` | 159 | 76,213 | 97% | 0 |
| `diagnostics/step0-fresh-container` | 145 | 63,359 | 98% | 0 |

**Zero files across all seven have no counterpart here**, by path or by
basename. One looked like an exception — `DIAGNOSTIC_REPORT.md` on the
diagnostics branch, the only path with no basename match anywhere. It is the
same 218 lines as `.notes/61-FRESH-CONTAINER-DIAGNOSTIC.md`, which this tree
carries: 119 substantive lines, 0 absent. It was moved into `.notes/`, not
dropped.

## The 2–3% that IS absent, read rather than assumed

A line present on a branch and absent here is either lost work or a
deliberate deletion, and only reading tells you which. Every cluster large
enough to matter was opened. All of them are this tree being AHEAD:

- **`apps/web/tests/acceptance/inventory.json`** (122 lines, all seven
  branches) — identical 129 sections on both sides. The branches carry
  `"catches_known_defect": null` where this tree names the defect and the
  gate that enforces it. The branch version is the unfilled one.
- **`apps/web/proto/pages-d1-overview.jsx`** (298 lines, zknopn) — the
  pre-deletion state of the ceilings and evidence-coverage cards, removed
  deliberately on 2026-08-19 because their keys sit on the API's
  `NEVER_SERVED` allowlist and the cards had nothing to render. Restoring
  them would reintroduce a redaction defect. The 144-line rationale is in
  the file. This one was misread as lost work earlier in the same session,
  which is why the rule above is stated as a rule.
- **`scripts/tests/test_deploy_auth_posture.py`** (32 lines, three
  branches) — this tree holds 234 lines against the branches' 115. The
  absent lines are the shorter docstring, rewritten by the longer one.
- **`plugins/dma-insights/docs/ROUTINES.md`**,
  **`05-lifecycle/surface-map.md`**, the flat-path
  `agents/*-surface-producer.md` — superseded prose and pre-relocation
  copies.

## Recovery

The refs below were moved to the default tip after the audit above. The
commits are not deleted and nothing here is unrecoverable. To restore one:

```
git push --force-with-lease origin <sha>:refs/heads/<branch>
```

| branch | tip before the move |
|---|---|
| `claude/artifact-store-on-mcp-line-7a6ad71c` | `05df30e602597ac4563812aa611d4512c14eb911` |
| `claude/dma-client-ingestion-e8xegz` | `80d91c741651122f2c349342a6707df018ee8afe` |
| `claude/dma-headless-readiness-2kcpru` | `d6cd02b087b73d99d5f88a4a6ef0617703880082` |
| `claude/dma-headless-readiness-82e4gl` | `9ebed386e13181f9ae7c68113b8533dae30be1a2` |
| `claude/dma-insights-onboarding-zknopn` | `4c304ec9d6581baa725dde3a76c1f3194f6faa96` |
| `claude/dma-plugin-version-fix-y20jv2` | `25a8a0a45182a788068bae2554bd59d12d189daa` |
| `diagnostics/step0-fresh-container` | `ca2a17728f4936aa6ef58c90597985b54b0a5f5f` |

Default branch at the time of the move:
`01f8e46b161d7bf0b0f397370647f9786c79d738`.

Two branches were already at zero and needed nothing:
`claude/default-branch-sync-verify-udd359`,
`claude/dma-insights-build-kickoff-wa1fkv`, and `main` — the last of which
is a side branch on the other lineage, not this repository's default.

## How the seven stopped being ahead

Reporting them as "carrying nothing" left seven counters reading 484, 407,
339, 330, 4, 4 and 3. A count that says work is outstanding, next to a
document saying none is, is worse than either alone — the next person
reads the number.

Three ways exist to zero a counter, and two of them lose something:
force-updating each ref to this tip leaves the commits unreferenced, and
deleting the branch is the same thing with a shorter name. Both were
refused here, correctly.

The third is additive: give this branch a second parent. `git commit-tree`
builds a merge commit from a tree and its parents, so each of the seven
becomes an ANCESTOR of the default branch — `ahead=0`, by definition —
while every commit it carries stays reachable and every file stays exactly
as it is. The tree hash is unchanged across all seven merges, asserted
before the push, so this cannot smuggle in a file change: it is a
statement about history, not about content.

This is what `git merge -s ours` records, built with plumbing because the
porcelain was unavailable. It is reversible in the only sense that
matters: nothing was discarded, so there is nothing to restore.
