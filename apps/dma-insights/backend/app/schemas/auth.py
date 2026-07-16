"""Auth-flow request/response schemas."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class GoogleAuthRequest(BaseModel):
    id_token: str = Field(..., min_length=10)


RoleT = Literal["ADMIN", "ANALYST", "AE", "CUSTOMER"]


class CurrentUserResponse(BaseModel):
    user_id: str
    email: EmailStr
    role: RoleT
    name: str = ""
    # Roles the user is allowed to act-as via the SettingsPopover
    # segmented control. Always includes the user's real role and any
    # strictly-lower role (downgrade-only). The frontend uses this to
    # render the segmented control and to clamp any localStorage tamper
    # of `dma:acting-as`.
    can_act_as: list[RoleT] = Field(default_factory=list)

    model_config = {"from_attributes": True}
