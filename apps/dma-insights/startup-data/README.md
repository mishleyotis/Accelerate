# startup-data

A **read-only snapshot of the seeded database**, produced by
`python -m app.scripts.export_startup_data` AFTER the JSON backfill
(`historical_backfill --dir`) + the §2c derive chain have run.

It is the dashboard's first-paint payload so the page never loads empty or
stale; the live API replaces it on the first refetch.

**This folder is NOT the ingest source of truth.** The source of truth is
the DMA package corpus ingested by `historical_backfill`. Do not hand-edit
these files — regenerate them.

Files:
- `clients/{display_id}.json` — one per ACTIVE scored client (identity,
  latest run, scores: overall + P1-P4 pillars + per-subcap; top platform;
  open alerts). Numbers only — no prose/evidence.
- `scores.json` — compact {display_id, name, subvertical, overall, pillars}
  for every client.
- `dashboard.json` — the `/dashboard` response + the `/entities` cards,
  exactly as the API emits them (the first-paint bundle).
- `manifest.json` — client_count + the sorted display_id roster.

Regenerate + verify:
```
python -m app.scripts.export_startup_data --out ../startup-data --sha $(git rev-parse --short HEAD)
python -m app.scripts.export_startup_data --check
```
