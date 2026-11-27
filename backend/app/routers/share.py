"""Sharing your progress through a private link.

  /api/share        (login)  GET status · POST create or replace the link · DELETE turn sharing off
  /share/{token}    (public) the read-only progress page, plain HTML. Wrong or revoked tokens get the same 404.
"""
import secrets

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.models import User, UserSettings
from app.services import portfolio, prefs

router = APIRouter(prefix="/share", tags=["share"])
public_router = APIRouter(tags=["share"])


class ShareOut(BaseModel):
    enabled: bool
    token: str | None
    path: str | None  # "/share/<token>"; the browser adds its own address


def _view(token: str | None) -> dict:
    return {"enabled": token is not None, "token": token, "path": f"/share/{token}" if token else None}


@router.get("", response_model=ShareOut)
def get_status(user: CurrentUser, db: DbSession):
    return _view(prefs.settings_row(db, user).share_token)


@router.post("", response_model=ShareOut, status_code=status.HTTP_201_CREATED)
def create_or_replace(user: CurrentUser, db: DbSession):
    """The first call turns sharing on. Later calls make a NEW link and the old one stops working."""
    row = prefs.settings_row(db, user)
    row.share_token = secrets.token_urlsafe(32)
    db.commit()
    return _view(row.share_token)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def turn_off(user: CurrentUser, db: DbSession):
    row = prefs.settings_row(db, user)
    row.share_token = None
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
}


@public_router.get("/share/{token}", response_class=HTMLResponse, include_in_schema=False)
def public_page(token: str, db: DbSession):
    if not 20 <= len(token) <= 64:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    row = db.scalar(select(UserSettings).where(UserSettings.share_token == token))
    user = db.get(User, row.user_id) if row else None
    if row is None or user is None or not secrets.compare_digest(row.share_token or "", token):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return HTMLResponse(portfolio.render_html(portfolio.build(db, user)), headers=HEADERS)
