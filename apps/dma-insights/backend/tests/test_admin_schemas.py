"""Tests for admin schemas — role enum + UpdateRoleRequest contract."""
from __future__ import annotations

from datetime import UTC

import pytest
from pydantic import ValidationError

from app.schemas.admin import (
    BuildQaGateOut,
    UpdateRoleRequest,
    UserOut,
)


class TestUpdateRoleRequest:
    def test_valid_roles_accepted(self) -> None:
        for role in ("ADMIN", "ANALYST", "AE", "CUSTOMER"):
            r = UpdateRoleRequest(role=role)  # type: ignore[arg-type]
            assert r.role == role

    def test_lowercase_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UpdateRoleRequest(role="admin")  # type: ignore[arg-type]

    def test_unknown_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UpdateRoleRequest(role="GOD")  # type: ignore[arg-type]


class TestUserOut:
    def test_email_validated(self) -> None:
        from datetime import datetime
        u = UserOut(
            id="00000000-0000-0000-0000-000000000001",
            email="user@zennify.com", name="User", role="AE",
            is_active=True, last_login_at=None,
            created_at=datetime.now(tz=UTC),
        )
        assert u.email == "user@zennify.com"

    def test_bad_email_rejected(self) -> None:
        from datetime import datetime
        with pytest.raises(ValidationError):
            UserOut(
                id="x", email="not-an-email", name="X", role="AE",
                is_active=True, last_login_at=None,
                created_at=datetime.now(tz=UTC),
            )


class TestBuildQaGateOut:
    def test_status_enum(self) -> None:
        from datetime import datetime
        g = BuildQaGateOut(
            id="x", stage="5", gate_id="G05.PARSER.FIDELITY",
            category="parser", description="...", acceptance_criteria="...",
            status="PASS", evidence_url=None,
            evaluated_at=datetime.now(tz=UTC),
            git_sha=None,
        )
        assert g.status == "PASS"

    def test_bad_status_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BuildQaGateOut(
                id="x", stage="5", gate_id="G05.X",
                category="parser", description="...", acceptance_criteria="...",
                status="WIBBLE",  # type: ignore[arg-type]
            )
