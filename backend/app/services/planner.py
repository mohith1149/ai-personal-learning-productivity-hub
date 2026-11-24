"""Daily planner: ONE day view assembled from the owner's other features. Nothing about the plan is stored except excusals.

What appears on a day (the user's local date):
  * TASKS      open tasks scheduled for / due on the day; on TODAY also every open task that is overdue or was scheduled for an earlier
               day. Tasks completed on the day show as completed.
  * LESSONS    TODAY: the next lesson of each active course (one per course per day; once one is completed the course stops asking).
               Any day: lessons completed on it.
  * VIDEOS     TODAY: each active playlist's videos for today's target (Videos page rules). Any day: videos completed on it.
  * TOPICS     TODAY: roadmap topics in progress plus the next topic not completed. Any day: topics completed on it.
  * HABITS     active habits: a daily habit is due every day from its start date, a weekly habit until its week's target is met.
               An unrecorded habit on a PAST day is shown as overdue (it can still be recorded).
  * PROJECTS   TODAY: each active project without a development session today ("work on it"). Any day: projects worked on.
Rules:
  * Completing/reopening an item calls the owning feature's own service, so there is a single source of truth. Only habits can be
    recorded for a past day; everything else is completed on today's plan (its completion time is "now").
  * Rescheduling moves a task's day (and optionally its deadline). It never completes it and never changes its status.
  * Excused = the owner skipped an activity on a day for a stated reason. Excused activities are not counted as missed or overdue
    and are left out of the day's percentage. Completed activities can't be excused; future days can't be excused.
  * The day's percentage is completed / (all activities that count, excused ones left out), floored.
"""
from datetime import date, datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.timeutil import local_day_bounds_utc, user_now, user_today
from app.models import (
    Course, CourseLesson, Habit, LearningSession, PlannerExcusal, Project, ProjectSession, RoadmapStage, RoadmapTopic, Task, User, Video,
    VideoPlaylist,
)
from app.schemas import habits as hs
from app.schemas import planner as s
from app.schemas import tasks as ts
from app.services import courses, habits, roadmap, tasks, videos


class NotFound(Exception):
    pass


class RuleError(ValueError):
    """A business-rule violation (HTTP 422)."""


class Conflict(Exception):
    """Clashes with existing data (HTTP 409)."""


KIND_ORDER = {"task": 0, "habit": 1, "lesson": 2, "video": 3, "topic": 4, "project": 5}
STATUS_ORDER = {"overdue": 0, "pending": 1, "completed": 2, "excused": 3}
TASK_OPEN = tasks.OPEN_STATUSES


def _item(kind: str, ref_id: int, title: str, status: str, link: str, *, subtitle=None, due_date=None, minutes=None, url=None,
          can_complete=True, can_reschedule=False) -> dict:
    return {"key": f"{kind}:{ref_id}", "kind": kind, "ref_id": ref_id, "title": title, "subtitle": subtitle, "status": status,
            "due_date": due_date, "minutes": minutes, "excuse_reason": None, "can_complete": can_complete,
            "can_reschedule": can_reschedule, "can_excuse": False, "link": link, "url": url}


# ============================== building the day ==============================


def _tasks(db: Session, user: User, day: date, today: date, start: datetime, end: datetime, now: datetime | None) -> list[dict]:
    local_now = user_now(user, now)
    cond = or_(Task.scheduled_date == day, Task.due_date == day, and_(Task.completed_at >= start, Task.completed_at < end))
    if day == today:
        cond = or_(cond, and_(Task.status.in_(TASK_OPEN), or_(Task.scheduled_date < today, Task.due_date < today)))
    rows = db.scalars(select(Task).where(Task.user_id == user.id, Task.status != "cancelled", cond).order_by(Task.priority, Task.id))
    out = []
    for t in rows:
        if t.status == "completed":
            if t.completed_at is not None and start <= t.completed_at < end:
                out.append(_item("task", t.id, t.title, "completed", "/tasks", due_date=t.due_date, minutes=t.estimated_minutes,
                                 subtitle="Project task" if t.project_id else None, can_reschedule=False))
            continue
        if day < today:
            status = "overdue"  # it was planned for a past day and is still open
        elif day == today:
            status = "overdue" if (tasks.is_overdue(t, local_now) or (t.scheduled_date is not None and t.scheduled_date < today)) else "pending"
        else:
            status = "pending"
        sub = ["Project task"] if t.project_id else []
        if t.scheduled_date and t.scheduled_date < day:
            sub.append(f"planned for {t.scheduled_date.isoformat()}")
        if t.carry_count:
            sub.append(f"moved {t.carry_count}×")
        out.append(_item("task", t.id, t.title, status, "/tasks", subtitle=" · ".join(sub) or None, due_date=t.due_date,
                         minutes=t.estimated_minutes, can_reschedule=True))
    return out


def _lessons(db: Session, user: User, day: date, today: date, start: datetime, end: datetime) -> list[dict]:
    out, courses_with_done = [], set()
    done = db.execute(
        select(CourseLesson, Course.title).join(Course, Course.id == CourseLesson.course_id)
        .where(Course.user_id == user.id, CourseLesson.completed_at >= start, CourseLesson.completed_at < end)
        .order_by(CourseLesson.completed_at))
    for lesson, course_title in done:
        courses_with_done.add(lesson.course_id)
        out.append(_item("lesson", lesson.id, lesson.title, "completed", f"/courses/{lesson.course_id}", subtitle=course_title,
                         minutes=lesson.duration_minutes, url=lesson.url))
    if day == today:
        active = db.scalars(courses._course_query(user).where(Course.status == "active").order_by(Course.priority, Course.title))
        for course in active:
            if course.id in courses_with_done:
                continue  # one lesson per active course per day
            nxt = courses.next_lesson(course)
            if nxt:
                out.append(_item("lesson", nxt["id"], nxt["title"], "pending", f"/courses/{course.id}",
                                 subtitle=f"{course.title} · {nxt['module_title']}", url=nxt["url"]))
    return out


def _videos(db: Session, user: User, day: date, today: date, start: datetime, end: datetime, now: datetime | None) -> list[dict]:
    out, seen = [], set()
    done = db.scalars(select(Video).where(Video.user_id == user.id, Video.removed_at.is_(None), Video.status == "completed",
                                          Video.completed_at >= start, Video.completed_at < end).order_by(Video.completed_at))
    for v in done:
        seen.add(v.id)
        out.append(_item("video", v.id, v.title, "completed", "/videos", subtitle=v.channel_title, url=v.url,
                         minutes=(v.duration_seconds or 0) // 60 or None))
    if day == today:
        for p in db.scalars(select(VideoPlaylist).where(VideoPlaylist.user_id == user.id, VideoPlaylist.active.is_(True)).order_by(VideoPlaylist.id)):
            for v in videos.today(db, user, p.id, now)["up_next"]:
                if v.id in seen:
                    continue
                seen.add(v.id)
                out.append(_item("video", v.id, v.title, "pending", f"/videos?playlist={p.id}", subtitle=p.name, url=v.url,
                                 minutes=(v.duration_seconds or 0) // 60 or None))
    return out


def _topics(db: Session, user: User, day: date, today: date, start: datetime, end: datetime) -> list[dict]:
    out, seen = [], set()
    q = select(RoadmapTopic, RoadmapStage.title).join(RoadmapStage, RoadmapStage.id == RoadmapTopic.stage_id).where(RoadmapTopic.user_id == user.id)
    for t, stage in db.execute(q.where(RoadmapTopic.completed_at >= start, RoadmapTopic.completed_at < end).order_by(RoadmapTopic.completed_at)):
        seen.add(t.id)
        out.append(_item("topic", t.id, t.title, "completed", "/roadmap", subtitle=stage))
    if day == today:
        open_q = q.where(RoadmapTopic.status != "completed").order_by(RoadmapStage.position, RoadmapTopic.position, RoadmapTopic.id)
        rows = list(db.execute(open_q))
        picks = [r for r in rows if r[0].status == "in_progress"]
        if rows and rows[0] not in picks:
            picks.append(rows[0])  # the next topic in roadmap order
        for t, stage in picks:
            if t.id not in seen:
                seen.add(t.id)
                out.append(_item("topic", t.id, t.title, "pending", "/roadmap", subtitle=f"{stage} · {'in progress' if t.status == 'in_progress' else 'next up'}"))
    return out


def _habits(db: Session, user: User, day: date, today: date) -> list[dict]:
    if day > today:
        return []
    out = []
    for h in db.scalars(select(Habit).where(Habit.user_id == user.id, Habit.active.is_(True)).order_by(Habit.id).options(selectinload(Habit.logs))):
        if h.start_date and day < h.start_date:
            continue
        done_today = any(log.date == day and log.completed for log in h.logs)
        sub = "Every day" if h.frequency == "daily" else f"{h.target_per_period} days a week"
        if done_today:
            out.append(_item("habit", h.id, h.name, "completed", "/habits", subtitle=sub))
        elif h.frequency == "daily":
            out.append(_item("habit", h.id, h.name, "pending" if day == today else "overdue", "/habits", subtitle=sub))
        elif day == today:
            week = habits.summarise(h, today)["week"]
            if week["completed"] < week["target"]:
                out.append(_item("habit", h.id, h.name, "pending", "/habits", subtitle=f"{sub} · {week['completed']} of {week['target']} this week"))
    return out


def _projects(db: Session, user: User, day: date, today: date) -> list[dict]:
    if day > today:
        return []
    worked = {pid: int(m) for pid, m in db.execute(
        select(ProjectSession.project_id, func.sum(ProjectSession.minutes)).where(ProjectSession.user_id == user.id, ProjectSession.date == day)
        .group_by(ProjectSession.project_id))}
    out = []
    for p in db.scalars(select(Project).where(Project.user_id == user.id).order_by(Project.priority, Project.id)):
        if p.id in worked:
            out.append(_item("project", p.id, f"Worked on {p.title}", "completed", f"/projects/{p.id}", subtitle=f"{worked[p.id]} min logged",
                             minutes=worked[p.id], can_complete=False))
        elif day == today and p.status == "active":
            out.append(_item("project", p.id, f"Work on {p.title}", "pending", f"/projects/{p.id}", subtitle="Log a development session when you're done",
                             can_complete=False))
    return out


def build_day(db: Session, user: User, day: date, now: datetime | None = None) -> dict:
    today = user_today(user, now)
    start, end = local_day_bounds_utc(user, day)
    items = [*_tasks(db, user, day, today, start, end, now), *_habits(db, user, day, today), *_lessons(db, user, day, today, start, end),
             *_videos(db, user, day, today, start, end, now), *_topics(db, user, day, today, start, end), *_projects(db, user, day, today)]

    excused = {(e.kind, e.ref_id): e.reason for e in db.scalars(select(PlannerExcusal).where(PlannerExcusal.user_id == user.id, PlannerExcusal.date == day))}
    for it in items:
        reason = excused.get((it["kind"], it["ref_id"]))
        if reason is not None and it["status"] != "completed":
            it["status"], it["excuse_reason"] = "excused", reason
        it["can_excuse"] = day <= today and it["status"] != "completed"
        if day > today:
            it["can_complete"] = it["can_reschedule"] = False
        elif it["kind"] != "habit" and day != today:
            it["can_complete"] = False  # non-habit items are completed on today's plan
    # Stable sort: within a status and type the owning feature's own order is kept (your video plan order, task priority, ...).
    items.sort(key=lambda i: (STATUS_ORDER[i["status"]], KIND_ORDER[i["kind"]]))

    counted = [i for i in items if i["status"] != "excused"]
    done = sum(i["status"] == "completed" for i in counted)
    study = db.scalar(select(func.coalesce(func.sum(LearningSession.minutes), 0)).where(LearningSession.user_id == user.id, LearningSession.date == day)) or 0
    dev = db.scalar(select(func.coalesce(func.sum(ProjectSession.minutes), 0)).where(ProjectSession.user_id == user.id, ProjectSession.date == day)) or 0
    summary = {
        "total": len(counted), "completed": done, "pending": sum(i["status"] == "pending" for i in counted),
        "overdue": sum(i["status"] == "overdue" for i in counted), "excused": len(items) - len(counted),
        "percent": (100 * done) // len(counted) if counted else 0, "study_minutes": int(study), "dev_minutes": int(dev),
        "by_kind": [{"kind": k, "total": sum(i["kind"] == k for i in counted), "completed": sum(i["kind"] == k and i["status"] == "completed" for i in counted)}
                    for k in KIND_ORDER if any(i["kind"] == k for i in counted)],
    }
    return {"date": day, "is_today": day == today, "items": items, "summary": summary}


# ============================== actions ==============================


def _translate(exc: Exception) -> Exception:
    """Errors raised by the owning feature's service become planner errors with the same message."""
    name = type(exc).__name__
    cls = {"NotFound": NotFound, "Conflict": Conflict}.get(name, RuleError)
    return cls(str(exc))


_FOREIGN = (tasks.NotFound, tasks.RuleError, courses.NotFound, courses.RuleError, courses.Conflict, videos.NotFound, videos.RuleError,
            videos.Conflict, roadmap.NotFound, roadmap.RuleError, roadmap.Conflict, habits.NotFound, habits.RuleError, habits.Conflict)


def _check_actionable(user: User, ref: s.ItemRef, now: datetime | None) -> None:
    today = user_today(user, now)
    if ref.date > today:
        raise RuleError("Future days can't be changed yet")
    if ref.kind == "project":
        raise RuleError("Log a development session on the project page to record project work")
    if ref.kind != "habit" and ref.date != today:
        raise RuleError("This can only be completed or reopened on today's plan")


def complete_item(db: Session, user: User, ref: s.ItemRef, now: datetime | None = None) -> dict:
    _check_actionable(user, ref, now)
    try:
        if ref.kind == "task":
            tasks.update_task(db, user, ref.ref_id, ts.TaskUpdate(status="completed"), now)
        elif ref.kind == "lesson":
            courses.complete_lesson(db, user, ref.ref_id, now)
        elif ref.kind == "video":
            videos.complete_video(db, user, ref.ref_id, now)
        elif ref.kind == "topic":
            roadmap.set_status(db, user, ref.ref_id, "completed", now)
        elif ref.kind == "habit":
            habits.set_log(db, user, ref.ref_id, ref.date, hs.LogIn(completed=True), now)
    except _FOREIGN as e:
        raise _translate(e) from None
    return build_day(db, user, ref.date, now)


def reopen_item(db: Session, user: User, ref: s.ItemRef, now: datetime | None = None) -> dict:
    _check_actionable(user, ref, now)
    try:
        if ref.kind == "task":
            tasks.update_task(db, user, ref.ref_id, ts.TaskUpdate(status="pending"), now)
        elif ref.kind == "lesson":
            courses.uncomplete_lesson(db, user, ref.ref_id, now)
        elif ref.kind == "video":
            videos.uncomplete_video(db, user, ref.ref_id)
        elif ref.kind == "topic":
            roadmap.set_status(db, user, ref.ref_id, "in_progress", now)
        elif ref.kind == "habit":
            habits.delete_log(db, user, ref.ref_id, ref.date, now)
    except _FOREIGN as e:
        raise _translate(e) from None
    return build_day(db, user, ref.date, now)


def reschedule_task(db: Session, user: User, task_id: int, data: s.RescheduleIn, now: datetime | None = None) -> dict:
    """Move an open task to another day. Its status and completion are untouched: rescheduling is NOT completing."""
    today = user_today(user, now)
    t = db.scalar(select(Task).where(Task.id == task_id, Task.user_id == user.id))
    if t is None:
        raise NotFound("Task not found")
    if t.status not in TASK_OPEN:
        raise RuleError("Only open tasks can be rescheduled")
    if data.date < today:
        raise RuleError("A task can't be rescheduled into the past")
    if data.date != t.scheduled_date:
        t.carried_from_date = t.scheduled_date or t.carried_from_date
        t.carry_count += 1
        t.scheduled_date = data.date
    if data.move_due_date:
        t.due_date = data.date
    db.commit()
    return build_day(db, user, data.from_date, now)


def _on_plan(plan: dict, ref: s.ItemRef) -> dict:
    for it in plan["items"]:
        if it["kind"] == ref.kind and it["ref_id"] == ref.ref_id:
            return it
    raise RuleError("That activity isn't on this day's plan")


def excuse_item(db: Session, user: User, data: s.ExcuseIn, now: datetime | None = None) -> dict:
    if data.date > user_today(user, now):
        raise RuleError("You can't excuse an activity on a future day")
    plan = build_day(db, user, data.date, now)
    item = _on_plan(plan, data)  # also proves the activity exists and belongs to this user (it was built from the user's data)
    if item["status"] == "completed":
        raise RuleError("A completed activity doesn't need an excuse")
    row = db.scalar(select(PlannerExcusal).where(PlannerExcusal.user_id == user.id, PlannerExcusal.kind == data.kind,
                                                 PlannerExcusal.ref_id == data.ref_id, PlannerExcusal.date == data.date))
    if row is None:
        db.add(PlannerExcusal(user_id=user.id, kind=data.kind, ref_id=data.ref_id, date=data.date, reason=data.reason.strip()))
    else:
        row.reason = data.reason.strip()
    db.commit()
    return build_day(db, user, data.date, now)


def remove_excuse(db: Session, user: User, ref: s.ItemRef, now: datetime | None = None) -> dict:
    row = db.scalar(select(PlannerExcusal).where(PlannerExcusal.user_id == user.id, PlannerExcusal.kind == ref.kind,
                                                 PlannerExcusal.ref_id == ref.ref_id, PlannerExcusal.date == ref.date))
    if row is None:
        raise NotFound("That activity isn't excused")
    db.delete(row)
    db.commit()
    return build_day(db, user, ref.date, now)
