"""0033 — the Accept/Reject pair that wrote nothing and could be read by nobody.

Every insight card renders a reasoning trace with an Accept/Reject pair. Measured
in production on 2026-08-08, against the live `dmai-api` revision:

    POST /v1/entities/baxter-credit-union-bcu/insights/IC-1/annotation
         ?audience=internal&role=ADMIN&actor=dma%40zennify.com
    -> HTTP 403 {"error":"unknown_actor",
                 "detail":"the session's email resolves to no active user;
                           user rows are the auth flow's to create"}

Three separate things were missing, and only one of them is a bug in the code
that took the refusal.

## 1. The user row — and why the 403 was RIGHT

`annotations.py` refuses an actor that resolves to no active `users` row. That
refusal is correct and stays: an annotation is attributable or it is not stored.
The defect is upstream — nothing has ever written a `users` row. Authorisation
lives in two deploy-time allowlists (`ADMIN_EMAILS`, `ANALYST_EMAILS`, set on the
`web` service only), and `apps/web/lib/identity.js` says so in its own comment:

    "ADMIN and ANALYST are strict allowlists (deploy-time env; the users table
     replaces this at the auth stage)."

So the allowlist was always a placeholder for this table, and the replacement
never happened. This revision performs it: the allowlisted Workspace identities
become durable `users` rows.

Why seeded here, and not provisioned just-in-time at first sign-in — which would
be the better mechanism, and is still owed:

  * Sign-in happens in the web BFF (`/api/signin` mints the session cookie only
    from a verified Google assertion). The API never observes a sign-in; it
    receives an actor email the BFF forwards afterwards. There is no endpoint
    today at which "this person signed in successfully" is a fact the database
    could learn.
  * Provisioning inside the annotation write instead would mean the FIRST WRITE
    creates the identity it is checked against — which is exactly the check the
    403 performs, deleted. An unknown actor must still be refused, so a write
    path cannot be an enrolment path.
  * The allowlist is an authorisation decision an admin already made and
    committed. Materialising it as rows changes no one's access: an email that
    is not on it still resolves to no user and still takes the 403.

The seed is `ON CONFLICT DO NOTHING`: the allowlist may CREATE a user, and never
overrides a role or a deactivation the database already holds. `google_sub` stays
NULL — it is the OIDC subject and cannot be known until that person signs in;
binding it is the follow-up this revision does not fake. Adding a colleague is
one INSERT, or one re-run with SEED_USERS set; it is not a code change.

## 2. The read path

`svc_api` already holds SELECT on `annotations` (0007 line 265, in the `workflow`
loop) — the grant was never the blocker, so this revision only re-states it
idempotently and prints what production actually has. What was missing is
`svc_mcp`: the connector had NO grant on `annotations` or `users` at all, so the
component that is supposed to consume reviewer feedback could not see it.

Reading annotations does not touch invariant 2. That invariant constrains the
API's WRITES ("content enters only through the connector"); a SELECT adds no
content and no endpoint gains a write. The two rows the API may still write are
unchanged: annotations and alert actions, both behind `Idempotency-Key`.

`annotations` also had no index but its primary key, so the natural read — this
entity's verdicts on this card, newest first — was a sequential scan. Two indexes
here. Plain `CREATE INDEX`, not CONCURRENTLY: Alembic runs the whole upgrade
inside one transaction (`migrations/env.py` opens it and commits at the end), so
CONCURRENTLY cannot execute without abandoning every revision before it, and the
table is empty in production — measured 0 rows, because nothing has ever
successfully written one. The charter's CONCURRENTLY rule is about not locking a
populated table; there is nothing here to lock.

## 3. The consumer

Lives in 0034 and in the connector: every accept/reject becomes a sighting in the
findings memory, carrying the card's own text and its `r_layer`. A verdict with
no claim attached teaches nothing.

Revision ID: 0033
Revises: 0029
Create Date: 2026-08-08
"""
import os

from alembic import op

revision = "0033"
down_revision = "0029"
branch_labels = None
depends_on = None

# The committed allowlist, verbatim from infra/deploy.sh's defaults
# (ADMIN_EMAILS / ANALYST_EMAILS). Override at migrate time with
# SEED_USERS="email:ROLE,email:ROLE" — the point of the env is that adding a
# colleague never needs a new revision.
DEFAULT_SEED = "mishley.otiende@zennify.com:ADMIN,dma@zennify.com:ADMIN"

ROLES = ("AE", "ANALYST", "ADMIN")


def _seed_list():
    raw = os.environ.get("SEED_USERS") or DEFAULT_SEED
    out = []
    for spec in filter(None, (s.strip() for s in raw.split(","))):
        email, _, role = spec.partition(":")
        email = email.strip().lower()
        role = (role.strip() or "AE").upper()
        if not email or "@" not in email:
            print(f"VERIFY 0033 seed skipped (not an address): {spec!r}", flush=True)
            continue
        if role not in ROLES:
            print(f"VERIFY 0033 seed skipped ({email}): role {role!r} not in "
                  f"{ROLES}", flush=True)
            continue
        out.append((email, role))
    return out


def _display_name(email: str) -> str:
    """The web derives a display name from the verified email's local part; the
    same derivation here so a seeded row and a signed-in session agree."""
    local = email.split("@")[0]
    return " ".join(p.capitalize() for p in local.replace(".", " ")
                    .replace("-", " ").replace("_", " ").split() if p)


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. the user rows ────────────────────────────────────────────────
    for email, role in _seed_list():
        conn.exec_driver_sql(
            """INSERT INTO users (email, display_name, role, is_active, created_at)
               VALUES (%s, %s, %s::user_role_t, true, now())
               ON CONFLICT (email) DO NOTHING""",
            (email, _display_name(email), role))

    # ── 2. the read path ───────────────────────────────────────────────
    # Re-stated idempotently beside the reason, so the next reader looking for
    # "may the API read annotations?" finds the answer here and not in 0007.
    op.execute("GRANT SELECT ON annotations TO svc_api")
    # New: the connector consumes reviewer feedback (0034). SELECT only — the
    # connector never writes an annotation; a verdict is the reviewer's.
    op.execute("GRANT SELECT ON annotations, users TO svc_mcp")

    op.execute(
        """CREATE INDEX IF NOT EXISTS annotations_anchor_idx
             ON annotations (entity_id, anchor_kind, anchor_id, created_at DESC)""")
    op.execute(
        """CREATE INDEX IF NOT EXISTS annotations_unread_idx
             ON annotations (created_at, id)""")
    op.execute(
        "COMMENT ON INDEX annotations_unread_idx IS "
        "'the consumer''s cursor: ingest_reviewer_feedback walks "
        "(created_at, id) forward so a verdict is turned into a finding "
        "exactly once'")

    # ── verification: the log lines ARE the production proof (private IP) ──
    rows = conn.exec_driver_sql(
        "SELECT email, role::text, is_active, google_sub IS NOT NULL "
        "  FROM users ORDER BY email").fetchall()
    print(f"VERIFY 0033 users rows={len(rows)}", flush=True)
    for email, role, active, bound in rows:
        print(f"VERIFY 0033 user {email} role={role} active={active} "
              f"google_sub_bound={bound}", flush=True)
    grants = conn.exec_driver_sql(
        """SELECT grantee, privilege_type
             FROM information_schema.role_table_grants
            WHERE table_name IN ('annotations','users')
              AND grantee IN ('svc_api','svc_mcp')
            ORDER BY 1,2""").fetchall()
    print("VERIFY 0033 grants " + ", ".join(f"{g}:{p}" for g, p in grants),
          flush=True)
    n = conn.exec_driver_sql("SELECT count(*) FROM annotations").scalar()
    print(f"VERIFY 0033 annotations rows={n}", flush=True)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS annotations_unread_idx")
    op.execute("DROP INDEX IF EXISTS annotations_anchor_idx")
    op.execute("REVOKE SELECT ON annotations, users FROM svc_mcp")
    # The seeded users are NOT deleted: annotations reference them, and an
    # identity that has expressed a verdict is history, not schema.
