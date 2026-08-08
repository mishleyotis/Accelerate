# Scripts

Three, stdlib only, deterministic. They do the mechanical half of the loop. The
naming, the rung choice and the negative control are judgement and stay with
you — a script that made those calls would be guessing with a straight face.

```bash
python drain_local.py <dir> [--json] [--session <ref>]
python triage.py <findings.json> [--json] [--min-sightings N]
python rung.py <refinement.json> --repo <checkout>
```

They chain, and the chain is STEP 1 → STEP 3 → STEP 6:

```bash
python drain_local.py . --json > candidates.json
#   fill verb and locus by hand, record every one through record_finding
#   then pull the store's view back down:
#   list_open_findings(...) > findings.json
python triage.py findings.json
#   ... make the change ...
python rung.py refinement.json --repo "$PWD"
```

## What each refuses

**`drain_local.py`** emits candidates with `verb` and `locus` blank where the
artefact does not state them. It will not guess: those two fields are half the
fingerprint, and a guessed fingerprint merges two defects or splits one.

**`triage.py`** exits **1** when any finding cannot be fingerprinted, and lists
them rather than dropping them. A triage that silently skips what it cannot
parse reports clean cluster sets over the findings it never looked at — the same
silent-skip mode that let `Per issue:` opt out of both CG-13 and AG-03 for as
long as it existed. It also never invents a cluster: no findings prints
"nothing above threshold" and exits 0.

**`rung.py`** exits **2** for "could not check" and never folds that into a
pass. Without `--repo` it cannot resolve a test node, a gate id or a migration,
and it says so. With `--repo` a claimed rung that does not resolve is
**downgraded** to what it is: an R4 whose gate is not in the connector's
registry is an R3 at best, and the next run reads the rung.

## The numbers they print

`triage.py`'s minimum rung is a **floor**, not an answer. It applies three
mechanical rules — a class of three or more is R3 or above, a defect that
reached the client is R3 or above, a recurrence is strictly above its previous
rung — and then hands you the judgement. In particular, on a recurrence it tells
you to run the *existing* check against the new instance first: if that check
passes on a genuine instance, you have a scope defect and widening the same rung
is the upstream move, not climbing one. See `../01-loop/4-closing.md`.
