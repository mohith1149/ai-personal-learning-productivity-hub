"""HTTP endpoints for courses, modules, lessons, study sessions and course templates.
Thin: validate → call service → serialise. Every endpoint requires login."""
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.core.deps import CurrentUser, DbSession
from app.models import Course
from app.schemas import courses as s
from app.services import courses as svc

courses_router = APIRouter(prefix="/courses", tags=["courses"])
modules_router = APIRouter(prefix="/modules", tags=["courses"])
lessons_router = APIRouter(prefix="/lessons", tags=["courses"])
sessions_router = APIRouter(prefix="/learning-sessions", tags=["courses"])
templates_router = APIRouter(prefix="/course-templates", tags=["courses"])


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, svc.NotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, svc.Conflict):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


ERRORS = (svc.NotFound, svc.RuleError, svc.Conflict)


def _detail(db: DbSession, course: Course) -> s.CourseDetail:
    return s.CourseDetail.model_validate(svc.course_detail(db, course))


# ---------------- courses ----------------


@courses_router.get("", response_model=list[s.CourseSummary])
def list_courses(
    user: CurrentUser, db: DbSession,
    course_status: Annotated[Literal["active", "paused", "completed", "archived"] | None, Query(alias="status")] = None,
):
    return svc.list_courses(db, user, course_status)


@courses_router.post("", response_model=s.CourseDetail, status_code=status.HTTP_201_CREATED)
def create_course(body: s.CourseCreate, user: CurrentUser, db: DbSession):
    return _detail(db, svc.create_course(db, user, body))


@courses_router.get("/{course_id}", response_model=s.CourseDetail)
def get_course(course_id: int, user: CurrentUser, db: DbSession):
    try:
        return _detail(db, svc.get_course(db, user, course_id))
    except ERRORS as e:
        raise _http(e) from None


@courses_router.patch("/{course_id}", response_model=s.CourseDetail)
def update_course(course_id: int, body: s.CourseUpdate, user: CurrentUser, db: DbSession):
    try:
        return _detail(db, svc.update_course(db, user, course_id, body))
    except ERRORS as e:
        raise _http(e) from None


@courses_router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(course_id: int, user: CurrentUser, db: DbSession) -> Response:
    try:
        svc.delete_course(db, user, course_id)
    except ERRORS as e:
        raise _http(e) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@courses_router.get("/{course_id}/next", response_model=s.NextLesson | None)
def next_lesson(course_id: int, user: CurrentUser, db: DbSession):
    try:
        return svc.next_lesson(svc.get_course(db, user, course_id))
    except ERRORS as e:
        raise _http(e) from None


@courses_router.post("/{course_id}/modules", response_model=s.CourseDetail, status_code=status.HTTP_201_CREATED)
def create_module(course_id: int, body: s.ModuleCreate, user: CurrentUser, db: DbSession):
    try:
        return _detail(db, svc.create_module(db, user, course_id, body))
    except ERRORS as e:
        raise _http(e) from None


@courses_router.post("/{course_id}/bulk-lessons", response_model=s.CourseDetail, status_code=status.HTTP_201_CREATED)
def bulk_lessons(course_id: int, body: s.BulkLessons, user: CurrentUser, db: DbSession):
    try:
        return _detail(db, svc.bulk_create_lessons(db, user, course_id, body))
    except ERRORS as e:
        raise _http(e) from None


# ---------------- modules ----------------


@modules_router.patch("/{module_id}", response_model=s.CourseDetail)
def update_module(module_id: int, body: s.ModuleUpdate, user: CurrentUser, db: DbSession):
    try:
        return _detail(db, svc.update_module(db, user, module_id, body))
    except ERRORS as e:
        raise _http(e) from None


@modules_router.delete("/{module_id}", response_model=s.CourseDetail)
def delete_module(module_id: int, user: CurrentUser, db: DbSession):
    try:
        return _detail(db, svc.delete_module(db, user, module_id))
    except ERRORS as e:
        raise _http(e) from None


@modules_router.post("/{module_id}/move", response_model=s.CourseDetail)
def move_module(module_id: int, body: s.Move, user: CurrentUser, db: DbSession):
    try:
        return _detail(db, svc.move_module(db, user, module_id, body.direction))
    except ERRORS as e:
        raise _http(e) from None


@modules_router.post("/{module_id}/lessons", response_model=s.CourseDetail, status_code=status.HTTP_201_CREATED)
def create_lesson(module_id: int, body: s.LessonCreate, user: CurrentUser, db: DbSession):
    try:
        return _detail(db, svc.create_lesson(db, user, module_id, body))
    except ERRORS as e:
        raise _http(e) from None


# ---------------- lessons ----------------
# Mutations return the whole updated course so the UI can refresh progress, next lesson and status in one step.


@lessons_router.patch("/{lesson_id}", response_model=s.CourseDetail)
def update_lesson(lesson_id: int, body: s.LessonUpdate, user: CurrentUser, db: DbSession):
    try:
        return _detail(db, svc.update_lesson(db, user, lesson_id, body))
    except ERRORS as e:
        raise _http(e) from None


@lessons_router.delete("/{lesson_id}", response_model=s.CourseDetail)
def delete_lesson(lesson_id: int, user: CurrentUser, db: DbSession):
    try:
        return _detail(db, svc.delete_lesson(db, user, lesson_id))
    except ERRORS as e:
        raise _http(e) from None


@lessons_router.post("/{lesson_id}/move", response_model=s.CourseDetail)
def move_lesson(lesson_id: int, body: s.Move, user: CurrentUser, db: DbSession):
    try:
        return _detail(db, svc.move_lesson(db, user, lesson_id, body.direction))
    except ERRORS as e:
        raise _http(e) from None


@lessons_router.post("/{lesson_id}/start", response_model=s.CourseDetail)
def start_lesson(lesson_id: int, user: CurrentUser, db: DbSession):
    try:
        return _detail(db, svc.start_lesson(db, user, lesson_id))
    except ERRORS as e:
        raise _http(e) from None


@lessons_router.post("/{lesson_id}/complete", response_model=s.CourseDetail)
def complete_lesson(lesson_id: int, user: CurrentUser, db: DbSession):
    try:
        return _detail(db, svc.complete_lesson(db, user, lesson_id))
    except ERRORS as e:
        raise _http(e) from None


@lessons_router.post("/{lesson_id}/uncomplete", response_model=s.CourseDetail)
def uncomplete_lesson(lesson_id: int, user: CurrentUser, db: DbSession):
    try:
        return _detail(db, svc.uncomplete_lesson(db, user, lesson_id))
    except ERRORS as e:
        raise _http(e) from None


# ---------------- study sessions ----------------


@sessions_router.get("", response_model=list[s.SessionOut])
def list_sessions(
    user: CurrentUser, db: DbSession, course_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50, offset: Annotated[int, Query(ge=0)] = 0,
):
    return svc.list_sessions(db, user, course_id, limit, offset)


@sessions_router.post("", response_model=s.SessionOut, status_code=status.HTTP_201_CREATED)
def create_session(body: s.SessionCreate, user: CurrentUser, db: DbSession):
    try:
        return svc.create_session(db, user, body)
    except ERRORS as e:
        raise _http(e) from None


@sessions_router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: int, user: CurrentUser, db: DbSession) -> Response:
    try:
        svc.delete_session(db, user, session_id)
    except ERRORS as e:
        raise _http(e) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------- templates ----------------


@templates_router.get("", response_model=list[s.TemplateOut])
def list_templates(user: CurrentUser, db: DbSession):
    return svc.list_templates(db, user)


@templates_router.post("/{key}", response_model=s.CourseDetail, status_code=status.HTTP_201_CREATED)
def add_template(key: str, user: CurrentUser, db: DbSession):
    try:
        return _detail(db, svc.add_template(db, user, key))
    except ERRORS as e:
        raise _http(e) from None
