# ADR 0012 — /ingest/assessment accepts EITHER bot bearer OR admin cookie (fail-closed)

Date: 2026-05-28
Status: Accepted (codifies the 2026-05-28 audit Wave 3 / Probe 8 decision)

## Context

`POST /api/v1/ingest/assessment` is the Claude-project callback
endpoint that the n8n bot pipeline posts results to once an
assessment package has been generated. Historically only the bot
bearer (`Authorization: Bearer <DMA_BOT_API_KEY>`) was accepted.

Two operator pain points surfaced during Wave 3:

1. **Manual operator re-ingest.** When the bot fails or an
   adjustment is needed (e.g. correcting an entity slug after a
   typo in the Ops Sheet), the operator must currently obtain the
   bearer from Secret Manager and craft a `curl -H "Authorization:
   Bearer …"` call. The bearer is the long-lived prod-bot secret
   — every manual touchpoint widens its exposure surface.

2. **Browser-driven re-ingest.** The Admin UI now has a "Re-ingest
   package" affordance that fires from the same authenticated
   admin session (Google SSO → JWT cookie). Forcing the browser to
   attach the bot bearer would either require copying secrets into
   the browser (bad) OR proxying through a backend endpoint that
   re-attaches it (extra layer, identical authority).

A naive fix is to accept either credential and pick the first that
matches. That has a subtle pitfall: if both are presented and the
bearer is wrong (e.g. a stale value from an old rotation) but the
cookie is valid, the server would silently treat the request as
admin and the operator would never learn the bot's credentials
have drifted. A leaked-but-stale bearer + a valid admin cookie
must NOT mask the bearer mismatch.

## Decision

The endpoint accepts EITHER:

- **Bot bearer** (`Authorization: Bearer <DMA_BOT_API_KEY>`) —
  canonical for automated pipeline traffic, OR
- **Admin cookie** (a valid `dma_session` JWT for a user whose role
  is `ADMIN`).

**Both paths use `hmac.compare_digest` for constant-time comparison
on the bearer**, removing the timing-attack defect originally
reported in the audit.

**Exactly one credential is permitted per request.** If `Authorization`
is present:
- correct bearer → 200 path (admin cookie ignored even if also
  present),
- wrong bearer → **HARD 401, do NOT fall through to cookie auth**.

The hard-reject closes the leaked-bearer masking pitfall: when an
operator's stale bearer is presented (e.g. from a rotated key),
the response surfaces "invalid bearer token" rather than silently
treating the call as admin.

When the configured `dma_bot_api_key` is the empty string (local
dev), auth is disabled — matches the existing `app.config`
fail-open contract for development.

## Rationale

1. **Operator ergonomics.** The Admin UI can now drive re-ingest
   from the browser without ever touching the bearer.
2. **Bearer hygiene.** Operators on a recovery shell still use the
   bearer the same way they always did; the mismatch case fails
   loudly instead of silently shifting to cookie auth.
3. **Defense-in-depth.** Both paths emit an `audit_log` row
   tagged with the auth method (`bot_bearer` or `admin_cookie`)
   plus the actor email (cookie) or `bot` (bearer). Drift in the
   admin-cookie path is visible in the audit trail.
4. **Constant-time bearer comparison.** Switching from `==` to
   `hmac.compare_digest` eliminates the timing-leak surface for
   the long-lived prod bearer.

## Implementation pins

- `apps/dma-insights/backend/app/routers/ingest.py` —
  `/ingest/assessment` is the canonical example; the dual-auth
  pattern is **explicitly NOT extended** to `/ingest/package`
  (which is bot-only) or `/rag/answer` (cookie-only with optional
  bearer).
- Constant-time comparison helper:
  ```python
  import hmac
  if not hmac.compare_digest(provided.encode(), expected.encode()):
      raise HTTPException(401, "invalid bearer token")
  ```
- Audit-log fields: `actor` (`bot` or admin email), `auth_method`
  (`bot_bearer` or `admin_cookie`), `route` (`/ingest/assessment`),
  `request_id` (extracted from body).

## Consequences

**Positive:**
- Admin UI re-ingest works without bearer exposure.
- Bearer mismatch surfaces immediately even when a valid cookie
  is also present.
- `hmac.compare_digest` closes the timing-attack vector.

**Negative:**
- Two code paths to maintain. The router test sweep covers both
  (bot-bearer success, bot-bearer wrong→401, admin-cookie success,
  no-auth→401, both-present→bearer wins).
- Audit-log readers must now distinguish `bot_bearer` from
  `admin_cookie` calls when triaging unexpected re-ingests.

**Neutral:**
- The Claude-project bot pipeline continues to use the bearer.
  No change in its caller.

## Alternatives considered

1. **Bearer only, proxy admin UI through a backend endpoint that
   re-attaches the bearer.** Rejected: adds an internal endpoint
   that ultimately bears the same authority — net zero security,
   extra surface.
2. **Cookie only, retire bearer.** Rejected: the bot pipeline runs
   from a server-side worker that has no human session.
3. **Either credential, soft-fall-through.** Rejected: the
   leaked-bearer masking pitfall described above.

## Test pins

- `apps/dma-insights/backend/tests/test_ingest_dual_auth.py` (Wave 3
  Probe 8 — added with this ADR) — covers the 5-state matrix
  documented in `routers/ingest.py` docstring:
  - bot bearer correct → 200
  - bot bearer wrong → 401 (hard reject; does NOT fall through)
  - admin cookie valid → 200
  - no auth → 401
  - non-admin cookie → 403
- `apps/dma-insights/backend/tests/test_security_invariants.py` —
  constant-time comparison guard.

## Cross-references

- ADR 0010 — Clay connector HMAC (sibling fail-closed-on-secret
  pattern).
- CLAUDE.md "Hard rules" — secrets-in-Secret-Manager invariant.
- `docs/QA-CONTRACT.md` PD-11 (Security) — bearer guard test
  enforcement.
- `docs/DEPLOYMENT.md` §0.2 — `DMA_BOT_API_KEY` is in the
  REQUIRED-FOR-PROD parameter set.
