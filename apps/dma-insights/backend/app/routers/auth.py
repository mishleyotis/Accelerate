"""OAuth + JWT issuance.

Flow:
  1. Frontend obtains a Google ID token via @react-oauth/google (with
     `hd=zennify.com` set in the client config).
  2. Frontend POSTs the ID token to /api/v1/auth/google.
  3. We verify the token against Google's JWKS, enforce `hd=zennify.com`
     post-verify (defense-in-depth), upsert the user, issue our session JWT,
     set the `dma_session` HttpOnly cookie.
  4. /api/v1/auth/me returns the decoded profile.
"""
from __future__ import annotations

import jwt as pyjwt
from fastapi import APIRouter, HTTPException, Response, status
from jwt import PyJWKClient
from sqlalchemy import text

from app.auth import assign_initial_role, is_zennify_email
from app.config import get_settings
from app.deps import CurrentUserDep, SessionDep
from app.schemas.auth import CurrentUserResponse, GoogleAuthRequest
from app.services.jwt_service import issue_token
from app.services.rate_limit import RateLimitDevLogin, RateLimitGoogleLogin

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_GOOGLE_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}


_jwk_client: PyJWKClient | None = None


def _jwks() -> PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = PyJWKClient(_GOOGLE_JWKS_URL)
    return _jwk_client


@router.post("/google", response_model=CurrentUserResponse)
async def google_login(
    body: GoogleAuthRequest,
    response: Response,
    session: SessionDep,
    _rl: RateLimitGoogleLogin,
) -> CurrentUserResponse:
    settings = get_settings()

    # Fetch Google's JWKS + decode the Google ID token. Wrap the JWKS
    # call in a broader except than PyJWTError because PyJWKClient can
    # also raise urllib URLErrors / connection timeouts when the JWKS
    # endpoint is slow (cold-start case). Surface those as 503 with a
    # clear detail rather than letting them bubble as opaque 500s.
    try:
        signing_key = _jwks().get_signing_key_from_jwt(body.id_token)
    except pyjwt.PyJWKClientError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Couldn't fetch Google JWKS: {e}",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"JWKS fetch failed: {type(e).__name__}: {e}",
        ) from e

    try:
        decoded = pyjwt.decode(
            body.id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.google_oauth_client_id,
            # pyjwt 2.9 accepts list/set/str for `issuer`; sort for a stable
            # ordering that doesn't change between processes (sets are
            # unordered → would otherwise vary `iss not in [...]` lookup).
            issuer=sorted(_GOOGLE_ISSUERS),
            options={"require": ["exp", "iat", "sub", "email"]},
        )
    except pyjwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Google ID token: {e}",
        ) from e

    email = (decoded.get("email") or "").lower().strip()
    name = decoded.get("name") or decoded.get("given_name") or email
    hd = decoded.get("hd")
    email_verified = decoded.get("email_verified", False)

    if hd != settings.google_oauth_hosted_domain or not is_zennify_email(email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="zennify.com Google account required",
        )
    if not email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="email not verified by Google",
        )

    # Upsert user row. Wrap so DB connection / permission / missing-table
    # errors surface a 503 with the exact detail (Postgres error code +
    # message) instead of a generic 500 the operator can't diagnose.
    try:
        row = (
            await session.execute(
                text(
                    """
                    INSERT INTO users (email, name, role, last_login_at)
                    VALUES (:email, :name, :role, NOW())
                    ON CONFLICT (email) DO UPDATE
                    SET name = EXCLUDED.name,
                        last_login_at = NOW(),
                        updated_at = NOW()
                    RETURNING id, email, name, role
                    """
                ),
                {
                    "email": email,
                    "name": name,
                    "role": assign_initial_role(email),
                },
            )
        ).first()
        await session.commit()
    except Exception as e:
        import sqlalchemy.exc as sa_exc

        await session.rollback()
        msg = str(e)
        if isinstance(e, sa_exc.OperationalError):
            detail = (
                f"DB connection failed during sign-in: {msg}. "
                "Likely causes: Cloud SQL unix socket missing, "
                "DATABASE_URL secret stale, or instance not running."
            )
        elif isinstance(e, sa_exc.ProgrammingError) and "does not exist" in msg.lower():
            detail = (
                f"DB schema not initialised: {msg}. "
                "Run `gcloud run jobs execute dma-insights-migrations "
                "--region us-central1 --wait` to apply Alembic migrations."
            )
        elif isinstance(e, sa_exc.ProgrammingError) and "permission denied" in msg.lower():
            detail = (
                f"DB permission denied for app user: {msg}. "
                "The migrations Cloud Run Job runs post_migrate.py to "
                "GRANT public-schema rights to dma_insights — re-execute it."
            )
        else:
            detail = f"DB error during sign-in: {type(e).__name__}: {msg}"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        ) from e

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Upsert returned no row — possible row-level security misconfiguration",
        )

    token = issue_token(
        user_id=str(row.id), email=row.email, role=row.role, name=row.name
    )
    response.set_cookie(
        key="dma_session",
        value=token,
        httponly=True,
        secure=settings.env != "local",
        samesite="lax",
        max_age=settings.jwt_ttl_hours * 3600,
        path="/",
    )
    return CurrentUserResponse(
        user_id=str(row.id),
        email=row.email,
        role=row.role,
        name=row.name,
        can_act_as=_can_act_as_for_role(row.role),
    )


@router.get("/me", response_model=CurrentUserResponse)
async def me(user: CurrentUserDep) -> CurrentUserResponse:
    return CurrentUserResponse(
        user_id=user.user_id,
        email=user.email,
        role=user.role,
        name=user.name,
        can_act_as=_can_act_as_for_role(user.role),
    )


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie("dma_session", path="/")
    return {"ok": True}


@router.post("/dev-login", response_model=CurrentUserResponse)
async def dev_login(
    email: str,
    response: Response,
    session: SessionDep,
    _rl: RateLimitDevLogin,
) -> CurrentUserResponse:
    """Development-only login bypass — issues a session JWT without Google OAuth.

    ONLY active when settings.env == 'local'. Returns 403 in all other envs.
    Used by Playwright E2E tests to set up persona sessions without GCP creds.
    """
    settings = get_settings()
    if settings.env != "local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="dev-login is only available in local env",
        )
    if not is_zennify_email(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="email must be @zennify.com",
        )

    role = assign_initial_role(email)
    name = email.split("@")[0].replace(".", " ").title()

    row = (
        await session.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": email},
        )
    ).first()

    if row is None:
        row = (
            await session.execute(
                text(
                    "INSERT INTO users (email, name, role) "
                    "VALUES (:email, :name, :role) "
                    "RETURNING id"
                ),
                {"email": email, "name": name, "role": role},
            )
        ).first()
        await session.commit()

    user_id = str(row.id)  # type: ignore[union-attr]
    token = issue_token(
        user_id=user_id,
        email=email,
        role=role,
        name=name,
    )
    response.set_cookie(
        "dma_session",
        token,
        httponly=True,
        secure=settings.env != "local",
        samesite="lax",
        path="/",
        max_age=3600,
    )
    return CurrentUserResponse(
        user_id=user_id, email=email, role=role, name=name,
        can_act_as=_can_act_as_for_role(role),
    )


def _can_act_as_for_role(role: str) -> list[str]:
    """Downgrade-only acting-as list. Mirrors the frontend
    `canActAsForRole` so server and client agree on the segmented
    control's option set — even if a malicious client localStorage-
    tampers, the server-supplied list is the upper bound."""
    if role == "ADMIN":
        return ["ADMIN", "ANALYST", "AE"]
    if role == "ANALYST":
        return ["ANALYST", "AE"]
    if role == "CUSTOMER":
        return ["CUSTOMER"]
    return ["AE"]
