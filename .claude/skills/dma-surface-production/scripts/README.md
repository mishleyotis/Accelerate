# Scripts

Run these rather than eyeballing — they are faster and they do not get tired. All six are standalone with no dependencies beyond the standard library.

`preflight.py` turns run progress into an ordered plan and says which pages not to touch. `clay_plan.py` prints the enrichment sequence. `check_payload.py` and `check_language.py` run before every submit. `check_consistency.py` runs before promotion and is the only check that reads all six payloads together. `score_prompt.py` scores a prompt you have written.

```bash
python scripts/preflight.py --progress progress.json
python scripts/clay_plan.py --domain example.com
python scripts/check_payload.py payload.json --page overview
python scripts/check_language.py payload.json
python scripts/check_consistency.py rundir/
python scripts/score_prompt.py prompt.txt
```
