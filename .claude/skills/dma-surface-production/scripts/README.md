# Scripts

Run these rather than eyeballing — they are faster and they do not get tired. All six are standalone with no dependencies beyond the standard library.

`preflight.py` turns run progress into an ordered plan and says which pages not to touch. `clay_plan.py` prints the enrichment sequence. `check_payload.py` and `check_language.py` run before every submit. `check_consistency.py` runs before promotion and is the only check that reads all six payloads together. `score_prompt.py` scores a prompt you have written.

```bash
python scripts/preflight.py --progress progress.json
python scripts/clay_plan.py --domain example.com
python scripts/check_payload.py payload.json --page overview
python scripts/check_language.py payload.json
python scripts/check_consistency.py rundir/ --subvertical CU
python scripts/score_prompt.py prompt.txt
```

Give `check_consistency.py` the entity's sub-vertical code and it blocks on a cited cell
belonging to another one — the workbook scores the whole catalogue, so those cells resolve
in it and render nowhere. Without the flag it reports the mixture as a warning. It also
reads the run as one argument: every served cell must open a drawer that says something,
coverage must be counted over the cells the grid actually serves, and the constraint in the
hero framing must be recognisable at the top finding, the act-now set, roadmap phase 1 and
the timeline storyline.
