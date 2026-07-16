# DMA Insights — source snapshot (2026-07-16)

This is the complete application source tree at commit `d430a220` of branch
`claude/web-app-cloud-run-redeploy-4rrmp6`, with **all fixes from the
2026-07-15/16 session already committed** (platform-fit fix, exec-summary
reasoning layer, QA fit-stale gate, S16 headline normalization at composer +
`/overview` endpoint, KG anti-pattern registry).

## What is included
- All backend source (`apps/dma-insights/backend/app`, `workers`, migrations, scripts)
- All frontend source (`apps/dma-insights/frontend/src`, `standalone-src`, config)
- Infra (Terraform, `cloudbuild.yaml`, `deploy-two-phase.sh`, Dockerfiles)
- Docs & ADRs, plus Zennify product reference docs (`docs/reference/*.html`)

## What is deliberately EXCLUDED (and why)
| Excluded | Reason | Restore from |
|---|---|---|
| The DMCA-named client (all mentions redacted) | Subject of the GitHub DMCA takedown on the original repo | Do NOT re-add — authorized copies only |
| `startup-data/` (94-client corpus) | Proprietary client data; regenerable | Your Drive folders / DMA Bot pipeline / DB backup |
| `tests/fixtures/dma_packages*` | Client DMA packages (docx/xlsx/json) | Your fixtures source |
| `docs/qa/*.tsv`, `docs/qa/*.json`, `tests/fixtures/ml/*.jsonl` | QA-audit matrices & ML labels embedding client narrative | Re-run the QA/ML generation steps |
| `benchmarks/`, all binaries, `en_core_web_sm*.whl`, `.git` history | Large / regenerable / history contains taken-down files | `pip install` / fetch-nlp-models step |

## Start pushing to a NEW private repo
This tree is already a git repo with one clean commit (no taken-down history):
```bash
git remote add origin https://github.com/<you>/<new-private-repo>.git
git push -u origin main     # use a freshly generated PAT/SSH key
```
Then restore the excluded data from your own authorized sources.
