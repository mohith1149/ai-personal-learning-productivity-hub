"""HTTP endpoints for projects, milestones, project tasks and development sessions. Login required."""
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.core.deps import CurrentUser, DbSession
from app.schemas import projects as s
from app.services import projects as svc

router = APIRouter(prefix="/projects", tags=["projects"])
milestones_router = APIRouter(prefix="/project-milestones", tags=["projects"])
sessions_router = APIRouter(prefix="/project-sessions", tags=["projects"])

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


@router.get("", response_model=list[s.ProjectSummary])
def list_projects(user: CurrentUser, db: DbSession,
                  project_status: Annotated[Literal["active", "paused", "completed", "archived"] | None, Query(alias="status")] = None):
    return svc.list_projects(db, user, project_status)


@router.post("", response_model=s.ProjectDetail, status_code=status.HTTP_201_CREATED)
def create_project(body: s.ProjectCreate, user: CurrentUser, db: DbSession):
    return _run(svc.create_project, db, user, body)


@router.get("/{project_id}", response_model=s.ProjectDetail)
def get_project(project_id: int, user: CurrentUser, db: DbSession):
    return _run(svc.get_project, db, user, project_id)


@router.patch("/{project_id}", response_model=s.ProjectDetail)
def update_project(project_id: int, body: s.ProjectUpdate, user: CurrentUser, db: DbSession):
    return _run(svc.update_project, db, user, project_id, body)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, user: CurrentUser, db: DbSession) -> Response:
    _run(svc.delete_project, db, user, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{project_id}/milestones", response_model=s.ProjectDetail, status_code=status.HTTP_201_CREATED)
def add_milestone(project_id: int, body: s.MilestoneCreate, user: CurrentUser, db: DbSession):
    return _run(svc.add_milestone, db, user, project_id, body)


@router.post("/{project_id}/tasks", response_model=s.ProjectDetail, status_code=status.HTTP_201_CREATED)
def add_task(project_id: int, body: s.TaskCreate, user: CurrentUser, db: DbSession):
    """Creates a real task linked to the project. Complete it through the task's own status (Tasks page / PATCH /tasks/{id})."""
    return _run(svc.add_task, db, user, project_id, body)


@router.post("/{project_id}/sessions", response_model=s.SessionOut, status_code=status.HTTP_201_CREATED)
def log_session(project_id: int, body: s.SessionCreate, user: CurrentUser, db: DbSession):
    return _run(svc.log_session, db, user, project_id, body)


@milestones_router.patch("/{milestone_id}", response_model=s.ProjectDetail)
def update_milestone(milestone_id: int, body: s.MilestoneUpdate, user: CurrentUser, db: DbSession):
    return _run(svc.update_milestone, db, user, milestone_id, body)


@milestones_router.post("/{milestone_id}/status", response_model=s.ProjectDetail)
def set_milestone_status(milestone_id: int, body: s.MilestoneStatus, user: CurrentUser, db: DbSession):
    return _run(svc.set_milestone_status, db, user, milestone_id, body)


@milestones_router.delete("/{milestone_id}", response_model=s.ProjectDetail)
def delete_milestone(milestone_id: int, user: CurrentUser, db: DbSession):
    return _run(svc.delete_milestone, db, user, milestone_id)


@sessions_router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: int, user: CurrentUser, db: DbSession) -> Response:
    _run(svc.delete_session, db, user, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
