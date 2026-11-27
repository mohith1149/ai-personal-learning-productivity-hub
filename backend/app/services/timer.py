"""A stopwatch you can start on a task, lesson, course, roadmap topic or project. Stopping it logs the time where it belongs.

Rules:
  * One timer at a time. Starting a second one is refused (stop or discard the first), so time is never counted twice.
  * Nothing is logged while it runs. Stopping logs the elapsed minutes (rounded, at least 1) as
      - a development session on the project (a task that belongs to a project logs to that project, with the task attached),
      - otherwise a study session on the course / lesson, or on the roadmap topic.
    A task's actual minutes also grow by the logged time. A task with no project, course or lesson only gets that.
  * You can correct the minutes when stopping (you forgot it was running). Past 24 hours the minutes must be given.
  * Discarding logs nothing. The timer belongs to its owner and survives a page reload, since it lives in the database.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import user_today
from app.models import ActiveTimer, Course, CourseLesson, Project, RoadmapTopic, Task, User
from app.schemas import courses as cs
from app.schemas import projects as ps
from app.schemas import roadmap as rs
from app.services import courses, projects, roadmap, tasks

MAX_MINUTES = 1440


class NotFound(Exception):
    pass


class RuleError(ValueError):
    pass


class Conflict(Exception):
    pass


def _current(db: Session, user: User) -> ActiveTimer | None:
    return db.scalar(select(ActiveTimer).where(ActiveTimer.user_id == user.id))


def _elapsed_seconds(t: ActiveTimer, now: datetime) -> int:
    started = t.started_at if t.started_at.tzinfo else t.started_at.replace(tzinfo=timezone.utc)
    return max(0, int((now - started).total_seconds()))


def view(db: Session, user: User, now: datetime | None = None) -> dict | None:
    t = _current(db, user)
    if t is None:
        return None
    now = now or datetime.now(timezone.utc)
    where = None
    if t.project_id is not None:
        p = db.get(Project, t.project_id)
        where = f"Project: {p.title}" if p and p.user_id == user.id else None
    elif t.course_id is not None:
        c = db.get(Course, t.course_id)
        where = f"Course: {c.title}" if c and c.user_id == user.id else None
    elif t.topic_id is not None:
        where = "Roadmap topic"
    return {"kind": t.kind, "label": t.label, "started_at": t.started_at, "elapsed_seconds": _elapsed_seconds(t, now), "logs_to": where,
            "task_id": t.task_id, "lesson_id": t.lesson_id, "topic_id": t.topic_id, "course_id": t.course_id, "project_id": t.project_id}


def _own(db: Session, model, user: User, ident: int, what: str):
    row = db.get(model, ident)
    if row is None or row.user_id != user.id:
        raise NotFound(f"{what} not found")
    return row


def start(db: Session, user: User, kind: str, ref_id: int, now: datetime | None = None) -> dict:
    if _current(db, user) is not None:
        raise Conflict("A timer is already running. Stop it (to log the time) or discard it first")
    now = now or datetime.now(timezone.utc)
    fields: dict = {}
    if kind == "project":
        p = _own(db, Project, user, ref_id, "Project")
        label, fields = p.title, {"project_id": p.id}
    elif kind == "task":
        t = _own(db, Task, user, ref_id, "Task")
        if t.status not in tasks.OPEN_STATUSES:
            raise RuleError("That task is already finished, so there is nothing to time")
        label, fields = t.title, {"task_id": t.id, "project_id": t.project_id}
        if t.project_id is None and t.lesson_id is not None:
            lesson = db.get(CourseLesson, t.lesson_id)
            if lesson is not None:
                fields.update(lesson_id=lesson.id, course_id=lesson.course_id)
    elif kind == "lesson":
        lesson = db.get(CourseLesson, ref_id)
        course = db.get(Course, lesson.course_id) if lesson else None
        if lesson is None or course is None or course.user_id != user.id:
            raise NotFound("Lesson not found")
        label, fields = lesson.title, {"lesson_id": lesson.id, "course_id": course.id}
    elif kind == "course":
        c = _own(db, Course, user, ref_id, "Course")
        label, fields = c.title, {"course_id": c.id}
    elif kind == "topic":
        topic = _own(db, RoadmapTopic, user, ref_id, "Topic")
        label, fields = topic.title, {"topic_id": topic.id}
    else:
        raise RuleError("You can time a task, lesson, course, roadmap topic or project")
    db.add(ActiveTimer(user_id=user.id, started_at=now, kind=kind, label=label[:300], **fields))
    db.commit()
    return view(db, user, now)


def discard(db: Session, user: User) -> None:
    t = _current(db, user)
    if t is None:
        raise NotFound("No timer is running")
    db.delete(t)
    db.commit()


def stop(db: Session, user: User, minutes: int | None = None, summary: str | None = None, now: datetime | None = None) -> dict:
    t = _current(db, user)
    if t is None:
        raise NotFound("No timer is running")
    now = now or datetime.now(timezone.utc)
    elapsed = _elapsed_seconds(t, now)
    if minutes is None:
        minutes = max(1, round(elapsed / 60))
        if minutes > MAX_MINUTES:
            raise RuleError("This timer has run for more than 24 hours. Enter the minutes you actually worked")
    if not 1 <= minutes <= MAX_MINUTES:
        raise RuleError("Minutes must be between 1 and 1440")

    label, task_id, lesson_id, topic_id, course_id, project_id = t.label, t.task_id, t.lesson_id, t.topic_id, t.course_id, t.project_id
    where, target_id = "task", None
    db.delete(t)  # removed in the same transaction as the log, so a failure keeps the timer and a success never logs twice
    try:
        task = db.get(Task, task_id) if task_id is not None else None
        if task is not None and task.user_id != user.id:
            task = None
        if project_id is not None:
            note = (summary or "").strip() or f"Worked on {label}"
            if len(note) < 3:
                raise RuleError("Say briefly what you did (at least 3 characters)")
            projects.log_session(db, user, project_id, ps.SessionCreate(minutes=minutes, summary=note, task_id=task.id if task else None), now)
            where, target_id = "project", project_id
        elif course_id is not None:
            courses.create_session(db, user, cs.SessionCreate(course_id=course_id, lesson_id=lesson_id, minutes=minutes), now)
            where, target_id = "course", course_id
        elif topic_id is not None:
            roadmap.log_study(db, user, topic_id, rs.StudyCreate(minutes=minutes), now)
            where, target_id = "topic", topic_id
        if task is not None:
            task.actual_minutes = (task.actual_minutes or 0) + minutes
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"minutes": minutes, "logged_to": where, "target_id": target_id, "label": label, "date": user_today(user, now)}
