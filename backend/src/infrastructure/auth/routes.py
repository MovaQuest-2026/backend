"""The account routes this project mounts, and the OAuth router it mounts outside the API prefix.

``router`` carries crudauth's account router under ``/auth``, with ``set-password`` left out,
and its recovery router: email verification, password reset and the confirmed email change.
crudauth's session-management router comes with them: ``GET /sessions``,
``DELETE /sessions/{session_handle}``, ``POST /logout-all`` and ``POST /csrf/refresh``.
``root_routers`` carries crudauth's OAuth router when a provider is configured, and is empty
when none is.

The routes in ``SESSION_ONLY_PATHS`` are mounted behind ``get_session_principal``: changing a
password, moving an address and ending a session are things an account does while signed in,
not things another credential does on its behalf. The ones in ``PASSWORD_BUDGET_PATHS`` check a
password of their own, and are mounted behind the budget crudauth counts a password change
against, which is the account's rather than the caller's address.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, cast
from urllib.parse import quote, urlsplit

from crudauth import Principal
from crudauth.account import build_account_router
from crudauth.email.router import build_email_router
from crudauth.exceptions import ForbiddenException, UnauthorizedException
from crudauth.ratelimit import KeyBy
from crudauth.transports.bearer.tokens import TokenType, verify_token
from crudauth.transports.session.management import build_session_management_router
from crudauth.utils import is_cross_site
from fastapi import APIRouter, Body, Depends, Form, Header, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel
from sqlalchemy import delete, select, update

from ...modules.user.crud import crud_users
from ...modules.user.mobile_tokens import MobileOAuthCode, MobileRefreshToken
from ...wiring.settings import settings
from ..dependencies import AsyncSessionDep
from ..logging import get_logger
from .dependencies import get_optional_principal, get_session_principal
from .deps import OAuth2FormDep, a_redirect_a_link_can_carry, body_a_database_can_hold
from .oauth_dynamic import bind_oauth_request
from .setup import auth as crud_auth
from .setup import session_transport

logger = get_logger()

router = APIRouter(tags=["Authentication"])

SESSION_ONLY_PATHS = ("/change-password", "/email/change-request")
"""The crudauth routes this project reserves for a signed-in session."""

PASSWORD_BUDGET_PATHS = ("/email/change-request",)
"""The crudauth routes whose own password check counts against the account's budget."""

PASSWORD_ATTEMPT_ACTION = "change_password"
"""The action that budget is counted under, the one crudauth's password change uses."""

MOBILE_ACCESS_TTL_SECONDS = 3600
MOBILE_REFRESH_TTL_DAYS = 60

_password_budget = crud_auth.rate_limit(PASSWORD_ATTEMPT_ACTION, key=KeyBy.USER)


class MobileRefreshRequest(BaseModel):
    """Mobile refresh credential body."""

    refresh_token: str


class MobileLogoutRequest(BaseModel):
    """Optional refresh credential to revoke at mobile logout."""

    refresh_token: str | None = None


class MobileOAuthExchangeRequest(BaseModel):
    """Single-use authorization code returned to the native app."""

    code: str


def _mount(source: APIRouter) -> None:
    """Mount ``source``'s routes under ``router``, each with the gates its path calls for."""
    open_router, session_only, counted = APIRouter(), APIRouter(), APIRouter()
    for route in source.routes:
        api_route = cast(APIRoute, route)
        api_route.tags = []
        if api_route.path in PASSWORD_BUDGET_PATHS:
            counted.routes.append(api_route)
        else:
            target = session_only if api_route.path in SESSION_ONLY_PATHS else open_router
            target.routes.append(api_route)

    guards = [Depends(body_a_database_can_hold), Depends(a_redirect_a_link_can_carry)]
    session = Depends(get_session_principal)
    router.include_router(open_router, dependencies=guards)
    router.include_router(session_only, dependencies=[*guards, session])
    router.include_router(counted, dependencies=[*guards, session, Depends(_password_budget)])


_account_router = build_account_router(crud_auth, crud_auth.sessions)
_account_router.routes = [
    route for route in _account_router.routes if isinstance(route, APIRoute) and route.path != "/set-password"
]
_mount(_account_router)

_mount(build_session_management_router(crud_auth, crud_auth.sessions))

if crud_auth.emails is not None:
    _mount(build_email_router(auth=crud_auth, service=crud_auth.emails))


def _with_the_redirect_guard(source: APIRouter) -> APIRouter:
    """``source``'s routes, each behind the guard on where a flow may send the browser."""
    guarded = APIRouter()
    guarded.include_router(
        source,
        dependencies=[Depends(a_redirect_a_link_can_carry), Depends(bind_oauth_request)],
    )

    return guarded


mobile_oauth_router = APIRouter(prefix=f"{settings.API_PREFIX}/v1/auth/oauth/mobile", tags=["Authentication"])


@mobile_oauth_router.get("/google", summary="Start Google sign-in for the mobile app")
async def start_mobile_google_oauth(redirect_uri: str) -> RedirectResponse:
    """Start the normal Google browser flow and return to a short-lived-code finalizer."""
    _validate_mobile_redirect_uri(redirect_uri)
    callback_path = f"{settings.API_PREFIX}/v1/auth/oauth/mobile/finalize?redirect_uri={quote(redirect_uri, safe='')}"
    authorize_url = f"{settings.API_PREFIX}/v1/auth/oauth/google?redirect_to={quote(callback_path, safe='')}"
    return RedirectResponse(url=authorize_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@mobile_oauth_router.get("/finalize", include_in_schema=False)
async def finalize_mobile_google_oauth(
    redirect_uri: str,
    current_user: Annotated[dict[str, Any], Depends(crud_auth.current_user(transport="session"))],
    db: AsyncSessionDep,
) -> RedirectResponse:
    """Issue a 60-second exchange code for the browser session and return to the app."""
    _validate_mobile_redirect_uri(redirect_uri)
    now = datetime.now(UTC)
    await db.execute(delete(MobileOAuthCode).where(MobileOAuthCode.expires_at <= now))
    code = secrets.token_urlsafe(32)
    db.add(
        MobileOAuthCode(
            user_id=int(current_user["id"]),
            code_hash=_credential_hash(code),
            expires_at=now + timedelta(seconds=60),
        )
    )
    await db.commit()
    return RedirectResponse(
        url=f"{redirect_uri}?code={quote(code, safe='')}",
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )


@router.post("/oauth/exchange", summary="Exchange mobile OAuth code for tokens")
@mobile_oauth_router.post("/exchange", summary="Exchange mobile OAuth code for tokens")
async def exchange_mobile_oauth_code(
    payload: MobileOAuthExchangeRequest,
    db: AsyncSessionDep,
    client: Annotated[str | None, Header(alias="X-Client")] = None,
) -> dict[str, Any]:
    """Atomically consume a one-time code and issue a revocable access/refresh pair."""
    if client != "mobile":
        raise UnauthorizedException("Mobile client required")
    now = datetime.now(UTC)
    code_row = await db.scalar(
        select(MobileOAuthCode).where(
            MobileOAuthCode.code_hash == _credential_hash(payload.code),
            MobileOAuthCode.consumed_at.is_(None),
            MobileOAuthCode.expires_at > now,
        )
    )
    if code_row is None:
        raise UnauthorizedException("Invalid or expired OAuth code")
    consumed = await db.execute(
        update(MobileOAuthCode)
        .where(
            MobileOAuthCode.id == code_row.id,
            MobileOAuthCode.consumed_at.is_(None),
            MobileOAuthCode.expires_at > now,
        )
        .values(consumed_at=now)
    )
    if consumed.rowcount != 1:
        await db.rollback()
        raise UnauthorizedException("Invalid or expired OAuth code")
    user = await crud_users.get(db=db, id=code_row.user_id, is_deleted=False)
    if user is None:
        await db.rollback()
        raise ForbiddenException("Account is inactive")
    tokens = crud_auth.issue_tokens(user)
    await db.execute(delete(MobileRefreshToken).where(MobileRefreshToken.expires_at <= now))
    db.add(
        MobileRefreshToken(
            user_id=code_row.user_id,
            token_hash=_credential_hash(tokens["refresh_token"]),
            expires_at=now + timedelta(days=MOBILE_REFRESH_TTL_DAYS),
        )
    )
    await db.commit()
    return {**tokens, "expires_in": MOBILE_ACCESS_TTL_SECONDS}


def _validate_mobile_redirect_uri(value: str) -> None:
    """Allow only the app callback scheme, host, and path, with no appended parameters."""
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"movaquest", "exp+movaquest"}
        or parsed.netloc != "auth"
        or parsed.path != "/callback"
        or parsed.query
        or parsed.fragment
    ):
        raise ForbiddenException("Mobile OAuth redirect URI is not allowed")


root_routers: tuple[APIRouter, ...] = (
    (_with_the_redirect_guard(crud_auth.oauth_router), mobile_oauth_router) if crud_auth.oauth is not None else ()
)


@router.post(
    "/login",
    summary="User Login",
    description="""
            Authenticates a user and creates a new session.

            This endpoint accepts username/email and password credentials and verifies them.
            On successful authentication:
            - A new session is created
            - A session ID is set as an HTTP-only cookie
            - A CSRF token is generated for protection against CSRF attacks

            With remember_me=true the session cookie persists across browser
            restarts; otherwise it ends with the browser session.

            The endpoint is protected by rate limiting to prevent brute force attacks.
            After multiple failed attempts, further login attempts will be temporarily blocked.
            A request the browser marks as sent from another site is refused, so a
            third-party page can't sign a visitor into an account it controls.
            """,
    responses={
        200: {"description": "Login successful, session created"},
        401: {"description": "Authentication failed"},
        403: {"description": "Cross-site login request"},
        429: {"description": "Too many login attempts, try again later"},
    },
    response_description="The signed-in user's id and username, and the CSRF token for subsequent requests",
)
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2FormDep,
    db: AsyncSessionDep,
    remember_me: Annotated[bool, Form()] = False,
    client: Annotated[str | None, Header(alias="X-Client")] = None,
) -> dict[str, Any]:
    """Login endpoint to get session cookies.

    Credentials go through crudauth's ``authenticate_password`` (timing-equalized
    check, disabled-account guard, escalating lockout that answers 429 +
    Retry-After), and the session is completed by the session transport, which
    sets the cookies and fires the ``on_after_login`` hook.
    """
    if client != "mobile" and is_cross_site(request):
        raise ForbiddenException("Cross-site login requests are not allowed.")

    user = await crud_auth.authenticate_password(db, form_data.username, form_data.password, request=request)
    if client == "mobile":
        tokens = crud_auth.issue_tokens(user)
        refresh_token = tokens["refresh_token"]
        now = datetime.now(UTC)
        await db.execute(delete(MobileRefreshToken).where(MobileRefreshToken.expires_at <= now))
        db.add(
            MobileRefreshToken(
                user_id=crud_auth.repo.user_id(user),
                token_hash=_credential_hash(refresh_token),
                expires_at=now + timedelta(days=MOBILE_REFRESH_TTL_DAYS),
            )
        )
        await db.commit()
        return {
            **tokens,
            "expires_in": MOBILE_ACCESS_TTL_SECONDS,
        }

    return await session_transport.complete_login(
        request,
        response,
        user,
        {
            "remember_me": remember_me,
            "metadata": {"login_type": "password", "username": crud_auth.repo.get(user, "username")},
        },
    )


@router.post(
    "/logout",
    response_model=None,
    summary="User Logout",
    description="""
            Terminates the current user session.

            This endpoint:
            - Invalidates the active session in the storage backend
            - Clears the cookies of every configured transport

            After logout, the user will need to authenticate again to access
            protected resources. Any existing session tokens will no longer be valid.
            """,
    responses={200: {"description": "Logout successful, session terminated"}, 401: {"description": "Not authenticated"}},
    response_description="Confirmation of successful logout",
)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSessionDep,
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    payload: Annotated[MobileLogoutRequest | None, Body()] = None,
) -> Response | dict[str, str]:
    """End the session the cookie names, clear the cookies and run the logout hook.

    The session transport does all of it (CSRF-protected); the dependency is what
    reserves the route for a session.
    """
    if principal is None:
        raise UnauthorizedException("Not authenticated")
    if principal.transport == "bearer":
        if payload is not None and payload.refresh_token:
            await db.execute(
                delete(MobileRefreshToken)
                .where(
                    MobileRefreshToken.user_id == principal.user_id,
                    MobileRefreshToken.token_hash == _credential_hash(payload.refresh_token),
                )
            )
            await db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    if principal.transport != "session":
        raise UnauthorizedException("Session authentication required")

    await session_transport.complete_logout(request, response, db)

    return {"message": "Logged out successfully"}


@router.post("/refresh", summary="Rotate mobile refresh token")
async def refresh_mobile_tokens(payload: MobileRefreshRequest, db: AsyncSessionDep) -> dict[str, Any]:
    """Validate and atomically consume one refresh token before issuing its replacement."""
    now = datetime.now(UTC)
    token_hash = _credential_hash(payload.refresh_token)
    token_row = await db.scalar(
        select(MobileRefreshToken).where(
            MobileRefreshToken.token_hash == token_hash,
            MobileRefreshToken.expires_at > now,
        )
    )
    claims = verify_token(payload.refresh_token, settings.SECRET_KEY, TokenType.REFRESH)
    if token_row is None or claims is None:
        raise UnauthorizedException("Invalid or expired refresh token")
    try:
        user_id = int(claims["sub"])
    except (KeyError, TypeError, ValueError) as error:
        raise UnauthorizedException("Invalid or expired refresh token") from error
    if token_row.user_id != user_id:
        raise UnauthorizedException("Invalid or expired refresh token")

    user = await crud_users.get(db=db, id=user_id, is_deleted=False)
    if user is None or claims.get("ver", 0) != crud_auth.repo.token_version(user):
        raise UnauthorizedException("Invalid or expired refresh token")

    consumed = await db.execute(
        delete(MobileRefreshToken)
        .where(
            MobileRefreshToken.id == token_row.id,
            MobileRefreshToken.expires_at > now,
        )
    )
    if consumed.rowcount != 1:
        await db.rollback()
        raise UnauthorizedException("Invalid or expired refresh token")

    tokens = crud_auth.issue_tokens(user)
    await db.execute(delete(MobileRefreshToken).where(MobileRefreshToken.expires_at <= now))
    db.add(
        MobileRefreshToken(
            user_id=user_id,
            token_hash=_credential_hash(tokens["refresh_token"]),
            expires_at=now + timedelta(days=MOBILE_REFRESH_TTL_DAYS),
        )
    )
    await db.commit()
    return {**tokens, "expires_in": MOBILE_ACCESS_TTL_SECONDS}


def _credential_hash(token: str) -> str:
    """Hash a high-entropy token or code before persistence."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@router.get("/check-auth")
async def check_auth(
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    db: AsyncSessionDep,
) -> dict[str, Any]:
    """
    Check if the user is authenticated and return basic user information.

    This is useful for clients to verify authentication status. It responds to both
    authenticated and anonymous callers (anonymous gets ``authenticated: false``
    rather than a 401).

    Returns:
        Authentication status and user information if authenticated.
    """
    if principal is None:
        return {"authenticated": False, "message": "Not authenticated"}

    try:
        user = await crud_users.get(db=db, id=principal.user_id, is_deleted=False)

        if not user:
            return {"authenticated": False, "message": "User not found"}

        session_id = principal.metadata.get("session_id")
        session = await crud_auth.sessions.validate_session(session_id) if session_id else None

        return {
            "authenticated": True,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "oauth_provider": user.get("oauth_provider"),
            },
            "session": {
                "created_at": session.created_at.isoformat() if session and session.created_at else None,
                "last_activity": session.last_activity.isoformat() if session and session.last_activity else None,
            },
        }
    except Exception as e:
        logger.error(f"Error checking authentication: {str(e)}", exc_info=True)
        return {"authenticated": False, "message": "Error checking authentication status"}
