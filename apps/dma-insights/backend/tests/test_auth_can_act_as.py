"""B6 tests — server response carries `can_act_as` so the frontend
can populate the SettingsPopover segmented control without having to
re-derive it from the email.

Before this batch the standalone frontend dropped the server-returned
`role` field and re-derived role from `email` via hardcoded
ADMIN_EMAILS / ANALYST_EMAILS sets. This silently dropped any server
promotion or demotion — a user removed from the admin allow-list
server-side would still see admin nav. Two fixes land together:

  1. Backend: `CurrentUserResponse` now exposes `can_act_as` per the
     role hierarchy (downgrade-only). `/api/v1/auth/me`, `/google`,
     and `/dev-login` all populate it.
  2. Frontend (`app-root.jsx::normalizeServerUser`): if the input is
     an object with `role` + `can_act_as`, use those; otherwise fall
     back to email-derived (back-compat for the dev tweaks panel).
"""
from __future__ import annotations

import pytest

from app.routers.auth import _can_act_as_for_role


@pytest.mark.parametrize("role, expected", [
    ("ADMIN",    ["ADMIN", "ANALYST", "AE"]),
    ("ANALYST",  ["ANALYST", "AE"]),
    ("AE",       ["AE"]),
    ("CUSTOMER", ["CUSTOMER"]),
    ("UNKNOWN",  ["AE"]),   # safe default — never elevates
])
def test_can_act_as_downgrade_only(role, expected):
    """Server-side acting-as list mirrors the frontend
    `canActAsForRole`. Never includes a higher role than the user's
    real role; never elevates."""
    assert _can_act_as_for_role(role) == expected


def test_can_act_as_admin_includes_self_and_lower():
    out = _can_act_as_for_role("ADMIN")
    assert "ADMIN" in out
    assert "ANALYST" in out
    assert "AE" in out


def test_can_act_as_ae_includes_only_self():
    out = _can_act_as_for_role("AE")
    assert out == ["AE"], "AE must not be able to act-as ADMIN or ANALYST"


def test_can_act_as_customer_isolated():
    """CUSTOMER is a leaf role — cannot act-as any internal persona."""
    out = _can_act_as_for_role("CUSTOMER")
    assert out == ["CUSTOMER"]
    assert "AE" not in out


def test_current_user_response_includes_can_act_as_field():
    """Schema regression — `CurrentUserResponse` must declare
    `can_act_as: list[Literal[...]]` so OpenAPI clients (the frontend)
    can rely on it."""
    from app.schemas.auth import CurrentUserResponse
    fields = CurrentUserResponse.model_fields
    assert "can_act_as" in fields, \
        "CurrentUserResponse must expose can_act_as for B6 frontend hydration"
