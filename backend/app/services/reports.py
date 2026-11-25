"""Weekly and monthly reports, computed from real records on every request. Nothing is stored and nothing is estimated.

Days are the USER's calendar days (their timezone), so something finished at 23:30 local time counts for that evening even though
the database stores UTC. A day that has not happened yet shows no activity and is left out of the plan percentage."""
import calendar as cal
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.timeutil import local_day_bounds_utc, user_today, user_tz
from app.models import (Course, CourseLesson, DailyChallenge, Habit, HabitLog, LearningSession, Project, ProjectSession, RoadmapTopic, Task,
                        User, Video)
from app.services import challenges, planner

MAX_YEAR_RANGE = (2000, 2100)
KINDS = ("tasks_done", "lessons_done", "videos_done", "topics_done")


class RuleError(ValueError):
    pass


# ============================== periods ==============================


def week_period(user: User, week_start: date | None, now: datetime | None = None) -> tuple[date, date, str, str]:
    """The Monday-to-Sunday week containing `week_start` (default: this week)."""
    anchor = week_start or user_today(user, now)
    if not MAX_YEAR_RANGE[0] <= anchor.year <= MAX_YEAR_RANGE[1]:
        raise RuleError("That date is out of range")
    start = anchor - timedelta(days=anchor.weekday())
    end = start + timedelta(days=6)
    return start, end, "week", f"{start.strftime('%d %b')} to {end.strftime('%d %b %Y')}"


def month_period(user: User, month: str | None, now: datetime | None = None) -> tuple[date, date, str, str]:
    """A calendar month from 'YYYY-MM' (default: this month)."""
    if month is None:
        t = user_today(user, now)
        year, mon = t.year, t.month
    else:
        try:
            y, m = month.split("-")
            year, mon = int(y), int(m)
            if len(y) != 4 or len(m) != 2 or not 1 <= mon <= 12:
                raise ValueError
        except ValueError:
            raise RuleError("The month must look like 2026-11") from None
        if not MAX_YEAR_RANGE[0] <= year <= MAX_YEAR_RANGE[1]:
            raise RuleError("That month is out of range")
    start = date(year, mon, 1)
    end = date(year, mon, cal.monthrange(year, mon)[1])
    return start, end, "month", start.strftime("%B %Y")


# ============================== collecting ==============================


def _local_days(user: User, stamps) -> dict[date, int]:
    """Count UTC timestamps per local calendar day."""
    tz = user_tz(user)
    out: dict[date, int] = defaultdict(int)
    for ts in stamps:
        out[ts.astimezone(tz).date()] += 1
    return out


def _collect(db: Session, user: User, start: date, end: date) -> dict[str, dict[date, int]]:
    """Per-day counts of everything that happened between two local days, inclusive."""
    lo, _ = local_day_bounds_utc(user, start)
    _, hi = local_day_bounds_utc(user, end)

    def stamps(col, *where):
        return db.scalars(select(col).where(*where, col >= lo, col < hi))

    def minutes(model) -> dict[date, int]:
        rows = db.execute(select(model.date, func.sum(model.minutes)).where(model.user_id == user.id, model.date >= start, model.date <= end).group_by(model.date))
        return {d: int(m) for d, m in rows}

    habit_rows = db.execute(select(HabitLog.date, func.count()).join(Habit, Habit.id == HabitLog.habit_id)
                            .where(Habit.user_id == user.id, HabitLog.completed.is_(True), HabitLog.date >= start, HabitLog.date <= end).group_by(HabitLog.date))
    return {
        "tasks_done": _local_days(user, stamps(Task.completed_at, Task.user_id == user.id)),
        "lessons_done": _local_days(user, stamps(CourseLesson.completed_at, CourseLesson.course_id.in_(select(Course.id).where(Course.user_id == user.id)))),
        "videos_done": _local_days(user, stamps(Video.completed_at, Video.user_id == user.id)),
        "topics_done": _local_days(user, stamps(RoadmapTopic.completed_at, RoadmapTopic.user_id == user.id)),
        "study_minutes": minutes(LearningSession),
        "project_minutes": minutes(ProjectSession),
        "habits_done": {d: int(n) for d, n in habit_rows},
    }


def _totals(series: dict[str, dict[date, int]], days: list[date], challenge_days: int) -> dict:
    t = {k: sum(series[k].get(d, 0) for d in days) for k in (*KINDS, "study_minutes", "project_minutes", "habits_done")}
    t["items_done"] = sum(t[k] for k in KINDS)
    t["challenge_days"] = challenge_days
    return t


def _challenge_completed(db: Session, user: User, start: date, end: date) -> int:
    return db.scalar(select(func.count()).select_from(DailyChallenge).where(DailyChallenge.user_id == user.id, DailyChallenge.status == "completed",
                                                                            DailyChallenge.date >= start, DailyChallenge.date <= end)) or 0


# ============================== the report ==============================


def build(db: Session, user: User, start: date, end: date, kind: str, label: str, now: datetime | None = None) -> dict:
    today = user_today(user, now)
    through = min(end, today)
    length = (end - start).days + 1
    all_days = [start + timedelta(days=i) for i in range(length)]
    counted = [d for d in all_days if d <= today]  # days that have happened
    series = _collect(db, user, start, end)

    ch = challenges.calendar(db, user, start, end, now)
    ch_status = {x["date"]: x["status"] for x in ch["days"]}
    in_period = [d for d in ch["days"] if d["date"] <= today]

    days = []
    plan_total = plan_done = 0
    for d in all_days:
        happened = d <= today
        if happened:
            summary = planner.build_day(db, user, d, now)["summary"]
            pt, pc = summary["total"], summary["completed"]
            plan_total += pt
            plan_done += pc
        else:
            pt = pc = None
        row = {"date": d, "challenge": ch_status.get(d, "none"), "plan_total": pt, "plan_completed": pc}
        for k, v in series.items():
            row[k] = v.get(d, 0) if happened else 0
        row["items_done"] = sum(row[k] for k in KINDS)
        days.append(row)

    c_done = _challenge_completed(db, user, start, end)
    totals = _totals(series, counted, c_done)

    # Compare like with like: the first N days of the previous period, N = days of this one that have happened. (Whole previous period when this one is over.)
    prev_end = start - timedelta(days=1)
    prev_start = start - timedelta(days=7) if kind == "week" else date(prev_end.year, prev_end.month, 1)
    prev_days = [prev_start + timedelta(days=i) for i in range(min(len(counted), (prev_end - prev_start).days + 1))]
    if prev_days:
        previous = _totals(_collect(db, user, prev_days[0], prev_days[-1]), prev_days, _challenge_completed(db, user, prev_days[0], prev_days[-1]))
    else:
        previous = _totals({k: {} for k in (*KINDS, "study_minutes", "project_minutes", "habits_done")}, [], 0)

    verified = db.scalar(select(func.count()).select_from(DailyChallenge).where(DailyChallenge.user_id == user.id, DailyChallenge.status == "completed",
                                                                                 DailyChallenge.verification_status == "verified",
                                                                                 DailyChallenge.date >= start, DailyChallenge.date <= end)) or 0
    project_rows = db.execute(select(Project.id, Project.title, func.sum(ProjectSession.minutes)).join(Project, Project.id == ProjectSession.project_id)
                              .where(ProjectSession.user_id == user.id, ProjectSession.date >= start, ProjectSession.date <= end)
                              .group_by(Project.id, Project.title).order_by(func.sum(ProjectSession.minutes).desc()).limit(8))
    habit_rows = db.execute(select(Habit.id, Habit.name, func.count()).join(HabitLog, HabitLog.habit_id == Habit.id)
                            .where(Habit.user_id == user.id, HabitLog.completed.is_(True), HabitLog.date >= start, HabitLog.date <= end)
                            .group_by(Habit.id, Habit.name).order_by(func.count().desc(), Habit.name))
    return {
        "period": {"kind": kind, "start": start, "end": end, "label": label, "days": length, "is_current": start <= today <= end, "through": through},
        "days": days, "totals": totals, "previous": previous,
        "plan": {"total": plan_total, "completed": plan_done, "percent": (100 * plan_done) // plan_total if plan_total else 0},
        "challenge": {"completed": sum(d["status"] == "completed" for d in in_period), "verified": verified, "missed": sum(d["status"] == "missed" for d in in_period),
                      "excused": sum(d["status"] == "excused" for d in in_period), "current_streak": ch["stats"]["current_streak"]},
        "projects": [{"project_id": i, "title": t, "minutes": int(m)} for i, t, m in project_rows],
        "habits": [{"habit_id": i, "name": n, "done_days": int(c)} for i, n, c in habit_rows],
    }


def weekly(db: Session, user: User, week_start: date | None = None, now: datetime | None = None) -> dict:
    start, end, kind, label = week_period(user, week_start, now)
    return build(db, user, start, end, kind, label, now)


def monthly(db: Session, user: User, month: str | None = None, now: datetime | None = None) -> dict:
    start, end, kind, label = month_period(user, month, now)
    return build(db, user, start, end, kind, label, now)
