"""HTTP endpoints for the AI Engineering roadmap. Login required."""
from fastapi import APIRouter, HTTPException, Response, status

from app.core.deps import CurrentUser, DbSession
from app.schemas import roadmap as s
from app.services import roadmap as svc

router = APIRouter(prefix="/roadmap", tags=["roadmap"])

ERRORS = (svc.NotFound, svc.RuleError, svc.Conflict)


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, svc.NotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, svc.Conflict):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


def _run(fn, *args):
    try:
        return fn(*args)
    except ERRORS as e:
        raise _http(e) from None


@router.get("", response_model=s.RoadmapOut)
def get_roadmap(user: CurrentUser, db: DbSession):
    """The five stages with every topic and computed progress. Creates the roadmap on first use."""
    return svc.get_roadmap(db, user)


@router.post("/topics", response_model=s.TopicOut, status_code=status.HTTP_201_CREATED)
def create_topic(body: s.TopicCreate, user: CurrentUser, db: DbSession):
    return _run(svc.create_topic, db, user, body)


@router.patch("/topics/{topic_id}", response_model=s.TopicOut)
def update_topic(topic_id: int, body: s.TopicUpdate, user: CurrentUser, db: DbSession):
    return _run(svc.update_topic, db, user, topic_id, body)


@router.delete("/topics/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_topic(topic_id: int, user: CurrentUser, db: DbSession) -> Response:
    _run(svc.delete_topic, db, user, topic_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/topics/{topic_id}/status", response_model=s.TopicOut)
def set_topic_status(topic_id: int, body: s.SetTopicStatus, user: CurrentUser, db: DbSession):
    return _run(svc.set_status, db, user, topic_id, body.status)


@router.get("/topics/{topic_id}/study", response_model=list[s.StudyOut])
def list_study(topic_id: int, user: CurrentUser, db: DbSession):
    return _run(svc.list_study, db, user, topic_id)


@router.post("/topics/{topic_id}/study", response_model=s.StudyOut, status_code=status.HTTP_201_CREATED)
def log_study(topic_id: int, body: s.StudyCreate, user: CurrentUser, db: DbSession):
    return _run(svc.log_study, db, user, topic_id, body)
