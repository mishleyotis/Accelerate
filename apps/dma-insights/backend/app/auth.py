"""Admin allow-list and initial role assignment.

The role hierarchy is fixed: ADMIN > ANALYST > AE > CUSTOMER.
Only zennify.com Google accounts (enforced via OIDC hd= + post-issue check)
can authenticate at all. ADMIN_EMAILS is the hardcoded promotion source on
first login; ANALYST_EMAILS is populated by admins via the /admin/users
endpoint and persisted on `users.role`.
"""
from __future__ import annotations

from app.config import get_settings

VALID_ROLES = ("ADMIN", "ANALYST", "AE", "CUSTOMER")


def assign_initial_role(email: str) -> str:
    """Returns the role to assign on first login for this email.

    Subsequent logins read the role from `users.role` directly; admins can
    promote/demote via /admin/users/{id}/role.
    """
    s = get_settings()
    email_normalized = email.lower().strip()
    admin_set = {e.lower() for e in s.admin_emails}
    if email_normalized in admin_set:
        return "ADMIN"
    # Domain enforcement happens upstream; if we get here without @zennify.com
    # something went wrong, but we fall back to AE rather than crash.
    return "AE"


def is_zennify_email(email: str) -> bool:
    s = get_settings()
    return email.lower().endswith("@" + s.google_oauth_hosted_domain.lower())


def role_at_least(role: str, minimum: str) -> bool:
    """`role` meets `minimum`? E.g. ADMIN satisfies ANALYST."""
    if role not in VALID_ROLES or minimum not in VALID_ROLES:
        return False
    return VALID_ROLES.index(role) <= VALID_ROLES.index(minimum)
