# Scripts

Run these rather than eyeballing — they are faster and they do not get tired. All are standalone with no dependencies beyond the standard library, except `precheck_gates.py` and `check_repetition.py`, which import the connector's own gate modules rather than restating them.

`preflight.py` turns run progress into an ordered plan and says which pages not to touch. `clay_plan.py` prints the enrichment sequence. `check_payload.py` and `check_language.py` run before every submit. `check_repetition.py` runs **before you write the twenty-first item of a large array**, not before submit. `check_evidence.py` runs over the evidence register, not a page. `precheck_gates.py` runs the connector's blocking gates locally so a submission is not spent discovering them. `check_consistency.py` runs before promotion and is the only check that reads all six payloads together. `score_prompt.py` scores a prompt you have written.

```bash
python scripts/preflight.py --progress progress.json
python scripts/clay_plan.py --domain example.com
python scripts/check_repetition.py drafts.json --page heatmap --at-scale 708
python scripts/check_payload.py payload.json --page overview
python scripts/check_language.py payload.json
python scripts/check_evidence.py get_evidence.json --review
python scripts/precheck_gates.py payload.json --page overview \
       --evidence get_evidence.json --bundle bundle.json
python scripts/check_consistency.py rundir/ --subvertical CU
python scripts/score_prompt.py prompt.txt
```

`check_repetition.py` answers one question the other checkers structurally cannot: **will this way of writing a synthesis survive seven hundred of them?** CG-15's template rule compares a field's items against each other, so no per-item check can see it, and two producers hit it at submit time on 2026-08-08 — one after building all 708 cells. It reports both of CG-15's numbers per field (phrasing overlap on 8-word spans, claim overlap on the content words left once the contract's mandated frame is stripped), names the clustered items, applies the same absence exemption the gate does, and with `--at-scale N` says what the drafts imply for the full array. It reads a payload, a single section, or a served page. Measured against it, the promoted Baxter run's 706 cell syntheses pass at a highest phrasing overlap of 0.179 against a line of 0.40 — a 700-cell page is writable, and if yours is being refused it is the shape and not the scale.

`check_payload.py` covers the contract, then the gates a local file can answer: face budgets (CG-12), item dating (CG-10), sentence case (CG-11), closed vocabularies on plain TEXT columns (CG-09 — including `arc_shape`, which the connector's own list does not reach), per-ITEM citation (AG-03), and the P2 recommendation card's anatomy.

`check_language.py` enforces two rules and prompts on the rest. The rules are sentence case and **the opening rule**: a prose field may not open on an absence — "No integration platform…", "Nothing shows…", "Lacks…", "Without a…". It is scoped to the first sentence of a field, because a field that names the asset first and states the absence second is the rule being followed.

`check_evidence.py` reads a `get_evidence` snapshot and refuses pairings that cannot both be true — one excerpt registered under two different hosts, a `source_url` that is not a fetchable document, a search-results page, an enrichment tool standing in for the source it found. It cannot tell you whether a single excerpt is on its own page; only fetching it can, which is what `register_evidence` does.

Give `check_consistency.py` the entity's sub-vertical code and it blocks on a cited cell
belonging to another one — the workbook scores the whole catalogue, so those cells resolve
in it and render nowhere. Without the flag it reports the mixture as a warning. It also
reads the run as one argument: every served cell must open a drawer that says something,
coverage must be counted over the cells the grid actually serves, and the constraint in the
hero framing must be recognisable at the top finding, the act-now set, roadmap phase 1 and
the timeline storyline.
