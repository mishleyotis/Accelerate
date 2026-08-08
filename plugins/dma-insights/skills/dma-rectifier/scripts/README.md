# Scripts

Three, stdlib only, deterministic. They do the mechanical half of the loop. The
naming, the rung choice and the negative control are judgement and stay with
you — a script that made those calls would be guessing with a straight face.

```bash
python drain_local.py <dir> [--json] [--session <ref>]
python triage.py <findings.json|digest.json> [--json] [--min-sightings N]
python rung.py <refinement.json> --repo <checkout>
```

They chain, and the chain is STEP 1 → STEP 3 → STEP 6:

```bash
python drain_local.py . --json > candidates.json
#   fill `measurement` — the command, query, status or count WITH its
#   denominator, refused below 30 chars — pick a defect_class from
#   list_defect_classes, then record every one through record_finding.
#   Then pull the store's own view back down:
#   get_memory_digest(days=7) > digest.json     (or list_open_findings)
python triage.py digest.json
#   ... make the change ...
python rung.py refinement.json --repo "$PWD"
```

`triage.py` reads a bare list, a `{findings|results|rows}` envelope, or a whole
`get_memory_digest` payload — recognised by its `open_by_class` key, from which
it takes the new, recurred and ageing rows and de-duplicates them.

## What each refuses

**`drain_local.py`** leaves the fields the artefact does not state blank. It
will not guess: a guessed `defect_class` files one defect under a second
synonym, which is the exact rot the foreign key exists to prevent.

**`triage.py`** exits **1** when any finding cannot be read — no
`defect_class`, no `component`, no title, an unrecognised severity — and lists
them rather than dropping them. A triage that silently skips what it cannot
read reports clean cluster sets over the findings it never looked at, the same
silent-skip mode that let `Per issue:` opt out of both CG-13 and AG-03 for as
long as it existed. It never invents a cluster: no findings prints "nothing
above threshold" and exits 0.

**`rung.py`** exits **2** for "could not check" and never folds that into a
pass. Without `--repo` it cannot resolve a test node, a gate id or a migration,
and it says so. With `--repo`, a `target_kind` that does not resolve is
**downgraded** to what it is: a `GATE` whose gate is absent from the connector's
registry under `apps/mcp` is a `TEST` at best, and the next run reads the
`target_kind`. It also blocks the three conditions that are not about the rung —
a `rationale` that does not open `RUNG: R<n> — ` or disagrees with the
`target_kind`, a refinement with neither `commit_sha` nor `change_ref`, and a
`relation: CLOSES` whose `verification` does not state **both** directions of
the negative control.

## The numbers they print

`triage.py`'s minimum rung is a **floor**, not an answer. It applies four
mechanical rules — three or more findings in a class is R3 or above, a
client-facing component (`web`, `api`) is R3 or above, a BLOCKER is R2 or above,
and a recurrence is strictly above the `target_kind` its previous refinement
used — then hands you the judgement.

Two honesty properties in that floor are worth knowing. On a recurrence it tells
you to run the *existing* check against the new instance first: if that check
passes on a genuine instance you have a scope defect, and widening the same rung
is the upstream move rather than climbing one. And when the record carries no
refinements it says the previous rung is **UNKNOWN** and sends you to
`get_finding` — because `list_open_findings` does not return refinements, and
"not listed" is not "none exists".

