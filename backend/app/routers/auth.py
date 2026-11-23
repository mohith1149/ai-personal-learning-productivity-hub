from fastapi import APIRouter, HTTPException, Request, Response, status

from app.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.core.security import (
    SESSION_COOKIE,
    create_access_token,
    decode_access_token,
)
from app.models import User
from app.schemas.auth import AuthStatus, LoginRequest, SetupRequest, UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, user: User) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        create_access_token(user.id, user.session_version),
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,  # not readable by JavaScript → not stealable via XSS
        samesite="lax",  # not sent on cross-site POSTs → CSRF protection
        secure=settings.cookie_secure,
        path="/",
    )


@router.get("/status", response_model=AuthStatus)
def auth_status(request: Request, db: DbSession) -> AuthStatus:
    """Public: tells the frontend whether to show Setup, Login or the app."""
    token = request.cookies.get(SESSION_COOKIE)
    decoded = decode_access_token(token) if token else None
    user = db.get(User, decoded[0]) if decoded else None
    if user is not None and decoded and decoded[1] != user.session_version:
        user = None
    return AuthStatus(
        setup_required=auth_service.setup_required(db),
        authenticated=user is not None,
        user=UserOut.model_validate(user) if user else None,
    )


@router.post("/setup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def setup(body: SetupRequest, response: Response, db: DbSession) -> User:
    try:
        user = auth_service.create_first_user(
            db,
            email=body.email,
            password=body.password,
            display_name=body.display_name,
            timezone=body.timezone,
        )
    except auth_service.SetupAlreadyDone:
        raise HTTPException(status.HTTP_409_CONFLICT, "Setup has already been completed") from None
    _set_session_cookie(response, user)
    return user


@router.post("/login", response_model=UserOut)
def login(body: LoginRequest, request: Request, response: Response, db: DbSession) -> User:
    if auth_service.setup_required(db):
        raise HTTPException(status.HTTP_409_CONFLICT, "Setup has not been completed")
    try:
        user = auth_service.authenticate(
            db,
            email=body.email,
            password=body.password,
            ip=request.client.host if request.client else None,
        )
    except auth_service.LockedOut as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many failed attempts. Try again later.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from None
    except auth_service.InvalidCredentials:
        # Same message whether the e-mail or the password was wrong.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password") from None
    _set_session_cookie(response, user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, user: CurrentUser, db: DbSession) -> Response:
    auth_service.revoke_sessions(db, user)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user
