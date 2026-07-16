# ADR 0013 — Two-phase Cloud Run deploy closes the traffic-shifts-before-migrations race

Date: 2026-05-28
Status: Accepted (closes the 2026-05-28 audit P1 pending-register item E)

## Context

The 2026-05-28 principal-QA audit identified a P1 race window in the
release pipeline:

> Old flow (`infra/deploy.sh`):
>   `terraform apply` → Cloud Run revision created + traffic flipped
>   to it immediately → `migrate.sh` runs while the new image is
>   serving against the OLD schema.

The window is 10-60 seconds. During it, every request from a real
user hits the **new code against the old DB schema**. If a migration
encounters a transient failure (lock contention, transient network
glitch on Cloud SQL, Cloud Build runner reschedule), the new image
keeps serving 5xx on every request, with no automatic rollback.

Additionally, **rollback during this window is non-trivial**: the
operator must manually `gcloud run services update-traffic
--to-revisions <prior>=100`, but the new revision is `latest` so a
subsequent normal deploy might re-promote it.

## Decision

Adopt a **two-phase deploy** that decouples revision creation from
traffic shift:

```
Phase 0: preflight-parameters.sh  (fail-closed on missing secrets)
Phase 1: gcloud builds submit     (build + push images)
Phase 2: gcloud run services update --no-traffic --tag candidate-${SHA}
         (deploy revision, but DO NOT shift traffic)
Phase 3: migrate.sh               (run alembic upgrade head against
                                   live Cloud SQL — OLD revision still
                                   serves 100% traffic)
Phase 4: curl ${TAG_URL}/readyz   (probe NEW revision via its tag URL,
                                   NOT the service URL)
Phase 5: gcloud run services update-traffic --to-latest
         (ONLY now does the new revision receive traffic)
Phase 6: deploy frontend          (promote frontend to new SHA + verify
                                   served <meta x-build-sha>; MUST run
                                   before Phase 7 so verify sees the new
                                   frontend, not the stale prior image)
Phase 7: verify-deploy.sh         (full 4-layer health check on service
                                   URL — checks BOTH backend + frontend
                                   served SHA, so it runs last)
```

The script lives at `apps/dma-insights/infra/deploy-two-phase.sh` and
is invoked from `infra/deploy.sh` — the old single-phase path is
retained ONLY for emergency-rollback / no-migration "skip migrate"
runs (`--skip-migrate`).

### Failure recovery — no rollback needed

At any failure point in phases 2-4 (deploy / migrate / readyz), the
**OLD revision is still serving 100% traffic**. No operator action is
required to restore service. The failed candidate revision is
labelled `candidate-${SHA}` (the gcloud `--tag`) and lives in the
Cloud Run revision list; it can be deleted at leisure:

```bash
gcloud run revisions delete dma-insights-backend-<sha>-<rev> \
  --region=us-central1
```

A `--no-traffic` revision is billed only when it receives requests —
which it doesn't.

### Tag URL is the migration-readiness probe surface

Cloud Run's `--tag candidate-${SHA}` flag exposes the new revision
at a URL of the form
`https://candidate-${SHA}---dma-insights-backend-<hash>-uc.a.run.app`.
This URL routes ONLY to the candidate revision, bypassing the
service-level traffic split. Probing `/readyz` here verifies that
the migration succeeded against the new code WITHOUT shifting any
real-user traffic.

If `/readyz` ever returns non-200 within the 5-attempt backoff
window, we abort the deploy and the operator gets a runbook for
investigation:

```
gcloud run revisions logs read <revision> --region=us-central1
```

## Rationale

1. **Race elimination.** The old flow created an unavoidable 10-60s
   window where the new code served the old schema. The two-phase
   flow makes the window 0s: the migration completes before any
   traffic is shifted.

2. **Operator clarity on failure.** The failure-mode is "OLD
   revision is still serving 100%; new revision exists but has no
   traffic". The operator decides whether to investigate or delete.
   No "is the deploy partial? did half my users see the new code?"
   ambiguity.

3. **Composability with `preflight-parameters.sh`.** Phase 0 fail-
   closes on any missing required parameter. Combined with
   `assert_production_ready(settings, role="backend")` armed in
   `app/main.py`, a misconfigured deploy now fails before the image
   is even built — three failure surfaces upstream of the actual
   bug (build vs deploy vs runtime startup) collapse to one.

4. **Migration semantics preserved.** Migrations run against live
   Cloud SQL exactly as before (alembic `upgrade head`). Migration
   021 already documents the "rolling-deploy compatibility" rule:
   every column / type change must be backwards compatible with the
   prior code so the OLD revision can keep serving during the
   migration window. This rule is unchanged.

## Implementation pins

- `apps/dma-insights/infra/deploy-two-phase.sh` — canonical entry
  point. `--skip-build` and `--skip-migrate` flags supported.
- `apps/dma-insights/infra/preflight-parameters.sh` — Phase 0 gate;
  validates all of `GCP_VARS` + `APP_SECRETS` are present + non-empty
  + pattern-matched (project_id regex, region regex, OAuth ID
  ending in `.apps.googleusercontent.com`, REDIS_URL starting with
  `redis://` or `rediss://`, etc.).
- `apps/dma-insights/infra/deploy.sh` — legacy single-phase path
  retained for `--skip-migrate` no-DDL hotfixes. Now also fixed:
  migration detection uses `alembic current` vs disk head rather
  than `git diff HEAD~5..HEAD` (which silently missed migrations
  added in older PRs that hadn't been deployed yet).
- `apps/dma-insights/infra/migrate.sh` — unchanged. Still applies
  alembic upgrade head against Cloud SQL with the recovered
  superuser password.

## Consequences

**Positive:**
- 0-second race window between migration and traffic shift.
- No-rollback failure semantics (OLD revision keeps serving).
- Composable with the preflight parameter validation.
- Tag-URL probe gives a clean signal "did this specific revision
  start up healthily against the new schema?"

**Negative:**
- Deploy is now 6 phases instead of 2. Wall-clock time is longer
  by the readyz-probe backoff window (up to ~45s worst case).
- The candidate revision lingers if the operator forgets to delete
  it after a failed deploy. Cloud Run lists are noisier; we'll
  document a `gcloud run revisions list` cleanup as part of the
  release runbook.
- Two-phase requires Cloud Run revision tags (`--tag`), which
  requires the operator's gcloud version to be reasonably recent
  (>= 422.x); pinned in DEPLOYMENT.md §0.

**Neutral:**
- Frontend deploys are still single-phase (no migrations to gate
  on). Phase 6 is just `gcloud run services update` + promote-to-latest
  + a served-SHA check; it runs before the Phase 7 verify so the
  4-layer health check sees the new frontend image.

## Alternatives considered

1. **Run migrations BEFORE Terraform apply.** Rejected: migrations
   need the just-built backend image (some migrations import
   service code, e.g. for backfill). Building the image, running
   migrations, then deploying the image with the live revision is
   logically what the two-phase flow does anyway.

2. **Blue/green via separate Cloud Run services.** Rejected: doubles
   the Cloud SQL connection budget and complicates the chrome
   (which BE_URL does the FE point at?). Two-phase + tag-URL probe
   achieves the same goal within a single service.

3. **Cloud Run revision min-instances=0 during deploy.** Rejected:
   doesn't solve the schema-mismatch problem; just hides it behind
   cold-starts.

4. **Cloud Run pre-deploy job that runs migrations.** Rejected:
   adds another job to monitor; the two-phase script already does
   this with `migrate.sh` in Phase 3.

## Test pins

- `apps/dma-insights/backend/tests/test_infra_safeguards.py` —
  guards the two-phase script's structure (exists, executable,
  references the 6 phases verbatim, calls preflight-parameters.sh).
- `apps/dma-insights/docs/QA-CONTRACT.md` PROD-01 — verify-deploy.sh
  hard-fails on /readyz drift. The two-phase flow makes this gate
  fire EARLIER (at the tag-URL probe), so any drift surfaces before
  traffic shifts.
- `apps/dma-insights/docs/QA-CONTRACT.md` DEP-12 — pre-deploy
  verification scripts coverage.

## Cross-references

- ADR 0011 — Standalone is the live AE-facing surface (frontend
  deploy semantics).
- CLAUDE.md "Hard rules" — Cloud Run service definitions reference
  immutable SHA tags so rollback targets are deterministic.
- `docs/DEPLOYMENT.md` §0 — release runbook now references
  `deploy-two-phase.sh` as the canonical entrypoint and
  `preflight-parameters.sh` as the prerequisite.
- `docs/QA-CONTRACT.md` PROD-10 — rollback drill is now a 1-line
  `gcloud run services update-traffic --to-revisions <prior>=100`
  rather than a full re-deploy.
