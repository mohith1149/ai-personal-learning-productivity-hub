"""HTTP endpoints for importing from YouTube. Login required. The API key never appears in any response."""
from typing import Annotated, Iterator

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.schemas import youtube as s
from app.services import youtube as yt
from app.services import youtube_import as svc

router = APIRouter(prefix="/youtube", tags=["youtube"])

_STATUS = {
    "invalid_url": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "not_found": status.HTTP_404_NOT_FOUND,
    "private": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "quota": status.HTTP_429_TOO_MANY_REQUESTS,
    "not_configured": status.HTTP_503_SERVICE_UNAVAILABLE,
    "bad_key": status.HTTP_503_SERVICE_UNAVAILABLE,
    "network": status.HTTP_502_BAD_GATEWAY,
    "api_error": status.HTTP_502_BAD_GATEWAY,
}


def _http(e: yt.YouTubeError) -> HTTPException:
    return HTTPException(_STATUS.get(e.code, status.HTTP_502_BAD_GATEWAY), e.message)


def get_client(user: CurrentUser) -> Iterator[yt.YouTubeClient]:
    """One client per request (tests replace this dependency with a fake-transport client). Depends on the
    logged-in user so a signed-out caller gets 401, not a hint about how the server is configured."""
    try:
        client = yt.YouTubeClient(get_settings().youtube_api_key)
    except yt.YouTubeError as e:
        raise _http(e) from None
    try:
        yield client
    finally:
        client.close()


Client = Annotated[yt.YouTubeClient, Depends(get_client)]


@router.get("/status", response_model=s.StatusOut)
def youtube_status(user: CurrentUser):
    return {"configured": bool(get_settings().youtube_api_key)}


@router.post("/preview", response_model=s.PreviewOut)
def preview(body: s.PreviewRequest, user: CurrentUser, db: DbSession, client: Client):
    try:
        return svc.preview(db, user, client, body)
    except yt.YouTubeError as e:
        raise _http(e) from None


@router.post("/import", response_model=s.ImportOut, status_code=status.HTTP_201_CREATED)
def import_videos(body: s.ImportRequest, user: CurrentUser, db: DbSession, client: Client):
    try:
        return svc.import_selected(db, user, client, body)
    except yt.YouTubeError as e:
        raise _http(e) from None
