"""FastAPI dependencies shared by routers."""
import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.security import SESSION_COOKIE, decode_access_token
from app.database import get_db
from app.models import User

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(request: Request, db: DbSession) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    auth = request.headers.get("Authorization", "")
    if not token and auth.lower().startswith("bearer "):
        token = auth[7:]
    decoded = decode_access_token(token) if token else None
    user = db.get(User, decoded[0]) if decoded else None
    # A token is valid only while its session_version matches (logout bumps the version).
    if user is None or decoded is None or decoded[1] != user.session_version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_automation_key(x_automation_key: Annotated[str | None, Header()] = None) -> None:
    """Guards /api/automation/* (called by n8n)."""
    expected = get_settings().automation_api_key
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AUTOMATION_API_KEY not configured")
    if not x_automation_key or not secrets.compare_digest(x_automation_key, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid automation key")
