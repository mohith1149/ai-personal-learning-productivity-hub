"""Goals with a pace warning. A goal is a course or a project that has a target date; nothing new is stored.

For each active course / project with a target date the pace is worked out from what you really finished:
  * remaining   course: lessons not completed.  project: milestones and tasks not done (cancelled tasks don't count).
  * days left   from today to the target date, both included, minus the planned rest days in between.
  * needed      remaining / days left.
  * your pace   items finished in the last 14 days / 14 (completion dates, in your local days).
  * projected   today + remaining / your pace.

Status: done | overdue | behind | stalled | not_started | on_track | unknown
  behind       projected finish is after the target date
  stalled      you finished things before, but nothing in the last 14 days
  not_started  nothing finished yet (warns only when it already needs at least one item a day)
  unknown      nothing to count yet (a course without lessons, a project without milestones or tasks)
`warning` is true for overdue, behind, stalled and a hurried not_started. Nothing is guessed: with no history there is no projection.
"""
import math
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.timeutil import user_today, user_tz
from app.models import Course, CourseModule, Project, ProjectMilestone, Task, User
from app.services import rest

WINDOW_DAYS = 14


def _local_day(user: User, moment: datetime | None) -> date | None:
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(user_tz(user)).date()


def _rate(per_day: float, unit: str) -> str:
    if per_day >= 1:
        n = round(per_day, 1)
        return f"{n:g} {unit} a day"
    per_week = round(per_day * 7, 1)
    return f"{per_week:g} {unit} a week"


def _short(day: date) -> str:
    return f"{day.day} {day.strftime('%b')}"


def _pace(*, kind: str, ref_id: int, title: str, target: date, total: int, finished_days: list[date], unit: str, today: date, rest_days: set[date]) -> dict:
    done = len(finished_days)
    remaining = max(0, total - done)
    span = (target - today).days + 1
    days_left = 0 if span <= 0 else max(0, span - sum(1 for d in rest_days if today <= d <= target))
    window_start = today - timedelta(days=WINDOW_DAYS - 1)
    recent = sum(1 for d in finished_days if window_start <= d <= today)
    per_day = recent / WINDOW_DAYS
    needed = remaining / max(days_left, 1) if remaining else 0.0
    projected = today + timedelta(days=math.ceil(remaining / per_day)) if remaining and per_day > 0 else None

    if total == 0:
        status, msg = "unknown", f"Nothing to count yet: add {unit} so the pace can be worked out."
    elif remaining == 0:
        status, msg = "done", f"All {unit} are done."
    elif target < today:
        status, msg = "overdue", f"Past the target date ({_short(target)}) with {remaining} {unit} left."
    elif per_day == 0 and done == 0:
        hurried = needed >= 1
        status = "not_started"
        msg = f"Not started: {remaining} {unit} to do by {_short(target)}, about {_rate(needed, unit)}."
        if hurried:
            msg += " Start soon or move the date."
    elif per_day == 0:
        status = "stalled"
        msg = f"Nothing finished in the last {WINDOW_DAYS} days. {remaining} {unit} left by {_short(target)} needs about {_rate(needed, unit)}."
    elif projected is not None and projected > target:
        status = "behind"
        late = (projected - target).days
        msg = (f"At your pace of {_rate(per_day, unit)} you'd finish on {_short(projected)}, {late} {'day' if late == 1 else 'days'} after "
               f"{_short(target)}. You need about {_rate(needed, unit)}.")
    else:
        status = "on_track"
        msg = f"On track: at your pace of {_rate(per_day, unit)} you'd finish around {_short(projected)} (target {_short(target)})."

    warning = status in ("overdue", "behind", "stalled") or (status == "not_started" and needed >= 1)
    return {
        "kind": kind, "id": ref_id, "title": title, "target_date": target, "status": status, "warning": warning, "message": msg,
        "unit": unit, "total": total, "done": done, "remaining": remaining, "days_left": days_left,
        "needed_per_day": round(needed, 2), "recent_per_day": round(per_day, 2), "projected_date": projected,
    }


_ORDER = {"overdue": 0, "behind": 1, "stalled": 2, "not_started": 3, "unknown": 4, "on_track": 5, "done": 6}


def list_goals(db: Session, user: User, now: datetime | None = None) -> list[dict]:
    today = user_today(user, now)
    rest_days = rest.all_days(db, user)
    out: list[dict] = []

    courses = db.scalars(select(Course).where(Course.user_id == user.id, Course.status == "active", Course.target_date.is_not(None))
                         .options(selectinload(Course.modules).selectinload(CourseModule.lessons))).all()
    for c in courses:
        lessons = [lesson for m in c.modules for lesson in m.lessons]
        days = [d for d in (_local_day(user, lesson.completed_at) for lesson in lessons if lesson.status == "completed") if d]
        out.append(_pace(kind="course", ref_id=c.id, title=c.title, target=c.target_date, total=len(lessons), finished_days=days, unit="lessons",
                         today=today, rest_days=rest_days))

    projects = db.scalars(select(Project).where(Project.user_id == user.id, Project.status == "active", Project.target_date.is_not(None))
                          .options(selectinload(Project.milestones))).all()
    for p in projects:
        tasks = db.scalars(select(Task).where(Task.user_id == user.id, Task.project_id == p.id, Task.status != "cancelled")).all()
        items = [(m.status == "done", m.completed_at) for m in p.milestones] + [(t.status == "completed", t.completed_at) for t in tasks]
        days = [d for d in (_local_day(user, at) for ok, at in items if ok) if d]
        # a finished item with no date still counts as done; it just can't show a recent pace
        undated = sum(1 for ok, at in items if ok) - len(days)
        out.append(_pace(kind="project", ref_id=p.id, title=p.title, target=p.target_date, total=len(items),
                         finished_days=days + [date.min] * undated, unit="items", today=today, rest_days=rest_days))

    out.sort(key=lambda g: (_ORDER[g["status"]], g["target_date"]))
    return out


def warnings(db: Session, user: User, now: datetime | None = None) -> list[dict]:
    return [g for g in list_goals(db, user, now) if g["warning"]]
