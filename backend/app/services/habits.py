"""Habit tracking.

Rules:
  * Every number shown (streaks, week/month progress, totals) is computed from the daily records in `habit_logs`.
    Nothing is stored or hardcoded, so editing or deleting a record immediately corrects everything.
  * A day counts only if its record says completed. A record with completed=False is a note about a missed day.
  * DAILY habit: streak = consecutive completed days. A day that hasn't been logged YET (today) doesn't break the streak.
  * WEEKLY habit (N days a week, weeks run Monday-Sunday): a week is "met" when it has >= N completed days; the streak counts
    consecutive met weeks. The current, unfinished week doesn't break the streak.
  * Days before the habit's start date never count, and records can't be made before it or in the future (user's timezone).
  * Every query is scoped to the user; someone else's id behaves like "not found".
"""
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.timeutil import user_today
from app.models import Habit, HabitLog, User
from app.schemas import habits as s


class NotFound(Exception):
    pass


class RuleError(ValueError):
    """A business-rule violation (HTTP 422)."""


class Conflict(Exception):
    """Clashes with existing data (HTTP 409)."""


RECENT_DAYS = 28


# ============================== pure calculations (no DB) ==============================


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())  # Monday


def _runs(sorted_units: list, step) -> int:
    best = run = 0
    prev = None
    for u in sorted_units:
        run = run + 1 if prev is not None and u == prev + step else 1
        best = max(best, run)
        prev = u
    return best


def daily_streak(done: set[date], today: date) -> tuple[int, int]:
    """(current, longest) consecutive completed days. Today not being done yet doesn't break the current streak."""
    longest = _runs(sorted(done), timedelta(days=1))
    cursor = today if today in done else today - timedelta(days=1)
    current = 0
    while cursor in done:
        current += 1
        cursor -= timedelta(days=1)
    return current, longest


def weekly_streak(done: set[date], target: int, today: date) -> tuple[int, int]:
    """(current, longest) consecutive weeks with >= target completed days. The unfinished current week doesn't break it."""
    counts: dict[date, int] = {}
    for d in done:
        counts[week_start(d)] = counts.get(week_start(d), 0) + 1
    met = {w for w, n in counts.items() if n >= target}
    longest = _runs(sorted(met), timedelta(days=7))
    cursor = week_start(today)
    if cursor not in met:
        cursor -= timedelta(days=7)
    current = 0
    while cursor in met:
        current += 1
        cursor -= timedelta(days=7)
    return current, longest


def _window(done: set[date], start: date, end: date, habit_start: date, today: date, target: int | None) -> dict:
    last = min(end, today)
    first = max(start, habit_start)
    eligible = max((last - first).days + 1, 0)
    completed = sum(1 for d in done if first <= d <= last)
    base = target if target is not None else eligible
    percent = min(100, (100 * completed) // base) if base else None
    return {"start": start, "end": end, "completed": completed, "eligible_days": eligible, "target": target, "percent": percent}


def summarise(h: Habit, today: date) -> dict:
    """Everything the UI shows for one habit, from its logs."""
    start = h.start_date or today
    done = {log.date for log in h.logs if log.completed and log.date >= start}
    by_date = {log.date: log for log in h.logs}
    if h.frequency == "weekly":
        cur, best = weekly_streak(done, h.target_per_period, today)
        unit = "weeks"
    else:
        cur, best = daily_streak(done, today)
        unit = "days"
    ws = week_start(today)
    month_start = today.replace(day=1)
    month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    week = _window(done, ws, ws + timedelta(days=6), start, today, h.target_per_period if h.frequency == "weekly" else None)
    month = _window(done, month_start, month_end, start, today, None)
    if h.frequency == "weekly":
        month["percent"] = None  # a weekly habit has no per-day target to measure a month against
    recent = [{"date": d, "completed": d in done, "logged": d in by_date}
              for d in (today - timedelta(days=i) for i in range(RECENT_DAYS - 1, -1, -1))]
    return {
        "id": h.id, "name": h.name, "description": h.description, "notes": h.notes, "start_date": start,
        "frequency": h.frequency, "target_per_period": h.target_per_period, "target_value": h.target_value, "unit": h.unit,
        "active": h.active, "created_at": h.created_at, "today": by_date.get(today), "done_today": today in done,
        "streak": {"current": cur, "longest": best, "unit": unit}, "week": week, "month": month,
        "total_completed": len(done), "recent": recent,
    }


def is_due_today(summary: dict) -> bool:
    if not summary["active"] or summary["done_today"]:
        return False
    if summary["frequency"] == "weekly":
        return summary["week"]["completed"] < summary["week"]["target"]
    return True


# ============================== lookups ==============================


def _get(db: Session, user: User, habit_id: int) -> Habit:
    # populate_existing: re-read the logs even if this habit is already loaded in the session, so a reply built right
    # after a change never shows stale streaks.
    h = db.scalar(select(Habit).where(Habit.id == habit_id, Habit.user_id == user.id)
                  .options(selectinload(Habit.logs)).execution_options(populate_existing=True))
    if h is None:
        raise NotFound("Habit not found")
    return h


def _name_taken(db: Session, user: User, name: str, except_id: int | None = None) -> bool:
    q = select(Habit.id).where(Habit.user_id == user.id, func.lower(Habit.name) == name.lower())
    if except_id is not None:
        q = q.where(Habit.id != except_id)
    return db.scalar(q) is not None


def list_habits(db: Session, user: User, now: datetime | None = None) -> dict:
    today = user_today(user, now)
    habits = db.scalars(select(Habit).where(Habit.user_id == user.id).order_by(Habit.active.desc(), Habit.id)
                        .options(selectinload(Habit.logs)))
    items = [summarise(h, today) for h in habits]
    return {"items": items, "due_today": sum(is_due_today(i) for i in items)}


def get_habit(db: Session, user: User, habit_id: int, now: datetime | None = None) -> dict:
    return summarise(_get(db, user, habit_id), user_today(user, now))


# ============================== CRUD ==============================


def create_habit(db: Session, user: User, data: s.HabitCreate, now: datetime | None = None) -> dict:
    name = data.name.strip()
    if _name_taken(db, user, name):
        raise Conflict("You already have a habit with that name")
    today = user_today(user, now)
    fields = data.model_dump()
    fields.update(name=name, start_date=data.start_date or today)
    h = Habit(user_id=user.id, **fields)
    db.add(h)
    db.commit()
    return summarise(_get(db, user, h.id), today)


def update_habit(db: Session, user: User, habit_id: int, data: s.HabitUpdate, now: datetime | None = None) -> dict:
    h = _get(db, user, habit_id)
    changes = data.model_dump(exclude_unset=True)
    for required in ("name", "frequency", "target_per_period", "active", "start_date"):
        if required in changes and changes[required] is None:
            raise RuleError(f"{required} can't be empty")
    if "name" in changes:
        changes["name"] = changes["name"].strip()
        if _name_taken(db, user, changes["name"], except_id=h.id):
            raise Conflict("You already have a habit with that name")
    if changes.get("frequency", h.frequency) == "daily":
        changes["target_per_period"] = 1  # a daily habit is once a day; switching to daily resets "N days a week"
    for field, value in changes.items():
        setattr(h, field, value)
    db.commit()
    return summarise(_get(db, user, habit_id), user_today(user, now))


def delete_habit(db: Session, user: User, habit_id: int) -> None:
    """Deletes the habit and all its daily records."""
    db.delete(_get(db, user, habit_id))
    db.commit()


# ============================== daily records ==============================


def _check_day(user: User, h: Habit, day: date, now: datetime | None) -> None:
    if day > user_today(user, now):
        raise RuleError("You can't record a habit for a future day")
    if h.start_date and day < h.start_date:
        raise RuleError(f"This habit starts on {h.start_date.isoformat()}; earlier days can't be recorded")


def set_log(db: Session, user: User, habit_id: int, day: date, data: s.LogIn, now: datetime | None = None) -> dict:
    """Create or replace the record for one day (one record per habit per day)."""
    h = _get(db, user, habit_id)
    _check_day(user, h, day, now)
    log = next((x for x in h.logs if x.date == day), None)
    if log is None:
        log = HabitLog(habit_id=h.id, date=day)
        db.add(log)
    log.completed, log.value, log.note = data.completed, data.value, data.note
    db.commit()
    return summarise(_get(db, user, habit_id), user_today(user, now))


def delete_log(db: Session, user: User, habit_id: int, day: date, now: datetime | None = None) -> dict:
    h = _get(db, user, habit_id)
    log = next((x for x in h.logs if x.date == day), None)
    if log is None:
        raise NotFound("No record for that day")
    db.delete(log)
    db.commit()
    return summarise(_get(db, user, habit_id), user_today(user, now))


def history(db: Session, user: User, habit_id: int, days: int = 90, now: datetime | None = None) -> list[HabitLog]:
    h = _get(db, user, habit_id)
    since = user_today(user, now) - timedelta(days=days - 1)
    return sorted((x for x in h.logs if x.date >= since), key=lambda x: x.date, reverse=True)
