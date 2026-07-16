"""FastAPI dependencies — auth, role gating, audience strip, redis."""
from __future__ import annotations

from typing import Annotated, Literal

import redis.asyncio as redis_async
from fastapi import Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import role_at_least
from app.config import get_settings
from app.database import get_session


class CurrentUser(BaseModel):
    user_id: str
    email: str
    role: Literal["ADMIN", "ANALYST", "AE", "CUSTOMER"]
    name: str = ""


SessionDep = Annotated[AsyncSession, Depends(get_session)]


_redis: redis_async.Redis | None = None


async def get_redis() -> redis_async.Redis:
    global _redis
    if _redis is None:
        _redis = redis_async.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


RedisDep = Annotated[redis_async.Redis, Depends(get_redis)]


async def get_current_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """Resolve current user from JWT (cookie or Authorization header).

    Token verification is delegated to app.services.jwt_service.verify_token;
    that service lands in stage 4 with the full OIDC flow. For now this raises
    401 if no token is presented.
    """
    from app.services.jwt_service import verify_token  # local import to avoid cycle

    token: str | None = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token:
        token = request.cookies.get("dma_session")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    payload = verify_token(token)
    return CurrentUser(**payload)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_role(minimum: str):
    """Returns a dependency that 403s when current user role < minimum."""

    async def _checker(user: CurrentUserDep) -> CurrentUser:
        if not role_at_least(user.role, minimum):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"role '{user.role}' insufficient (needs {minimum}+)",
            )
        return user

    return _checker


require_admin = require_role("ADMIN")
require_analyst = require_role("ANALYST")
require_ae = require_role("AE")


class ViewMode(BaseModel):
    audience: Literal["internal", "customer"]


async def get_view_mode(view: str = "internal") -> ViewMode:
    """Reads `?view=internal|customer` and normalizes.

    Used by audience_strip to decide whether to omit D5 Context / D6 Health /
    ERS rationale on every API response.
    """
    if view not in ("internal", "customer"):
        view = "internal"
    return ViewMode(audience=view)  # type: ignore[arg-type]


ViewModeDep = Annotated[ViewMode, Depends(get_view_mode)]
