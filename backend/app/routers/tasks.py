"""HTTP endpoints for tasks, categories and recurring tasks. Thin: validate → call service → serialise."""
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.core.deps import CurrentUser, DbSession
from app.core.timeutil import user_now
from app.models import RecurringTask, Task, User
from app.schemas import tasks as s
from app.services import tasks as svc

tasks_router = APIRouter(prefix="/tasks", tags=["tasks"])
categories_router = APIRouter(prefix="/task-categories", tags=["tasks"])
recurring_router = APIRouter(prefix="/recurring-tasks", tags=["tasks"])


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, svc.NotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


def _task_out(task: Task, user: User) -> s.TaskOut:
    out = s.TaskOut.model_validate(task)
    out.is_overdue = svc.is_overdue(task, user_now(user))
    return out


def _recurring_out(rt: RecurringTask) -> s.RecurringOut:
    return s.RecurringOut.model_validate(rt)


# ---------------- tasks ----------------
# NOTE: fixed paths (/counts) are declared before /{task_id} so they aren't captured as an id.


@tasks_router.get("", response_model=s.TaskList)
def list_tasks(
    user: CurrentUser,
    db: DbSession,
    view: Literal["all", "open", "today", "overdue", "upcoming", "completed"] = "all",
    task_status: Annotated[
        Literal["pending", "in_progress", "completed", "cancelled"] | None, Query(alias="status")
    ] = None,
    category_id: int | None = None,
    priority: Annotated[int | None, Query(ge=1, le=4)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> s.TaskList:
    items, total = svc.list_tasks(
        db, user, view=view, status=task_status, category_id=category_id, priority=priority,
        q=q.strip() if q else None, limit=limit, offset=offset,
    )
    return s.TaskList(items=[_task_out(t, user) for t in items], total=total)


@tasks_router.get("/counts", response_model=s.TaskCounts)
def task_counts(user: CurrentUser, db: DbSession) -> dict[str, int]:
    return svc.counts(db, user)


@tasks_router.post("", response_model=s.TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(body: s.TaskCreate, user: CurrentUser, db: DbSession) -> s.TaskOut:
    try:
        return _task_out(svc.create_task(db, user, body), user)
    except (svc.NotFound, svc.RuleError) as e:
        raise _translate(e) from None


@tasks_router.get("/{task_id}", response_model=s.TaskOut)
def get_task(task_id: int, user: CurrentUser, db: DbSession) -> s.TaskOut:
    try:
        return _task_out(svc.get_task(db, user, task_id), user)
    except svc.NotFound as e:
        raise _translate(e) from None


@tasks_router.patch("/{task_id}", response_model=s.TaskOut)
def update_task(task_id: int, body: s.TaskUpdate, user: CurrentUser, db: DbSession) -> s.TaskOut:
    try:
        return _task_out(svc.update_task(db, user, task_id, body), user)
    except (svc.NotFound, svc.RuleError) as e:
        raise _translate(e) from None


@tasks_router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, user: CurrentUser, db: DbSession) -> Response:
    try:
        svc.delete_task(db, user, task_id)
    except svc.NotFound as e:
        raise _translate(e) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------- categories ----------------


@categories_router.get("", response_model=list[s.CategoryOut])
def list_categories(user: CurrentUser, db: DbSession):
    return svc.list_categories(db, user)


@categories_router.post("", response_model=s.CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(body: s.CategoryCreate, user: CurrentUser, db: DbSession):
    try:
        return svc.create_category(db, user, body)
    except (svc.NotFound, svc.RuleError) as e:
        raise _translate(e) from None


@categories_router.patch("/{category_id}", response_model=s.CategoryOut)
def update_category(category_id: int, body: s.CategoryUpdate, user: CurrentUser, db: DbSession):
    try:
        return svc.update_category(db, user, category_id, body)
    except (svc.NotFound, svc.RuleError) as e:
        raise _translate(e) from None


@categories_router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, user: CurrentUser, db: DbSession) -> Response:
    try:
        svc.delete_category(db, user, category_id)
    except (svc.NotFound, svc.RuleError) as e:
        raise _translate(e) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------- recurring ----------------


@recurring_router.get("", response_model=list[s.RecurringOut])
def list_recurring(user: CurrentUser, db: DbSession):
    return [_recurring_out(r) for r in svc.list_recurring(db, user)]


@recurring_router.post("", response_model=s.RecurringOut, status_code=status.HTTP_201_CREATED)
def create_recurring(body: s.RecurringCreate, user: CurrentUser, db: DbSession):
    try:
        return _recurring_out(svc.create_recurring(db, user, body))
    except (svc.NotFound, svc.RuleError) as e:
        raise _translate(e) from None


@recurring_router.patch("/{rid}", response_model=s.RecurringOut)
def update_recurring(rid: int, body: s.RecurringUpdate, user: CurrentUser, db: DbSession):
    try:
        return _recurring_out(svc.update_recurring(db, user, rid, body))
    except (svc.NotFound, svc.RuleError) as e:
        raise _translate(e) from None


@recurring_router.delete("/{rid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recurring(rid: int, user: CurrentUser, db: DbSession) -> Response:
    try:
        svc.delete_recurring(db, user, rid)
    except svc.NotFound as e:
        raise _translate(e) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
