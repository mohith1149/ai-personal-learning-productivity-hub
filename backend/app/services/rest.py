"""Planned rest days: a limited number per calendar month, so one sick day or a holiday doesn't end a streak.

Rules:
  * A rest day can be set for today, up to 3 days back (you were ill and noticed late) or up to a year ahead.
  * At most `UserSettings.rest_days_per_month` per calendar month (the month the rest day falls in). Past that you must excuse a day
    on the challenge page with a reason, as before.
  * A day with a completed challenge can't be a rest day: you did the work, so it simply counts.
  * Effects, applied by the owning features: the challenge streak skips the day (it neither adds nor breaks), the day isn't counted as
    missed, and the planner leaves the day's open items out of the percentage. Habit streaks are NOT changed.
"""
import calendar as cal
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import user_today
from app.models import DailyChallenge, RestDay, User
from app.services import prefs

BACK_DAYS = 3
AHEAD_DAYS = 366
MAX_PER_MONTH = 31


class RuleError(ValueError):
    pass


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def cap(db: Session, user: User) -> int:
    return prefs.settings_row(db, user).rest_days_per_month


def set_of(db: Session, user: User, start: date, end: date) -> set[date]:
    """The rest days between two dates, inclusive."""
    return set(db.scalars(select(RestDay.date).where(RestDay.user_id == user.id, RestDay.date >= start, RestDay.date <= end)))


def all_days(db: Session, user: User) -> set[date]:
    return set(db.scalars(select(RestDay.date).where(RestDay.user_id == user.id)))


def month_view(db: Session, user: User, year: int, month: int) -> dict:
    start, end = date(year, month, 1), date(year, month, cal.monthrange(year, month)[1])
    rows = db.scalars(select(RestDay).where(RestDay.user_id == user.id, RestDay.date >= start, RestDay.date <= end).order_by(RestDay.date)).all()
    limit = cap(db, user)
    return {"month": f"{year:04d}-{month:02d}", "cap": limit, "used": len(rows), "left": max(0, limit - len(rows)),
            "days": [{"date": r.date, "reason": r.reason} for r in rows]}


def add(db: Session, user: User, day: date, reason: str | None, now: datetime | None = None) -> dict:
    today = user_today(user, now)
    if day < today - timedelta(days=BACK_DAYS):
        raise RuleError(f"A rest day can be set for today, the last {BACK_DAYS} days or the future")
    if day > today + timedelta(days=AHEAD_DAYS):
        raise RuleError("That is too far ahead for a rest day")
    if db.scalar(select(RestDay).where(RestDay.user_id == user.id, RestDay.date == day)):
        raise Conflict("That day is already a rest day")
    if db.scalar(select(DailyChallenge).where(DailyChallenge.user_id == user.id, DailyChallenge.date == day, DailyChallenge.status == "completed")):
        raise RuleError("You completed the challenge that day, so it counts as it is")
    view = month_view(db, user, day.year, day.month)
    if view["used"] >= view["cap"]:
        name = day.strftime("%B")
        raise RuleError(f"You've used all {view['cap']} rest days for {name}. Change the limit in Settings, or excuse the day on the Challenge page with a reason")
    db.add(RestDay(user_id=user.id, date=day, reason=(reason or "").strip() or None))
    db.commit()
    return month_view(db, user, day.year, day.month)


def remove(db: Session, user: User, day: date) -> dict:
    row = db.scalar(select(RestDay).where(RestDay.user_id == user.id, RestDay.date == day))
    if row is None:
        raise NotFound("That day isn't a rest day")
    db.delete(row)
    db.commit()
    return month_view(db, user, day.year, day.month)
