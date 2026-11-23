"""Timezone helpers. 'Today', 'overdue' and 'due at 14:00' are always judged in the USER's timezone,
never the server's, so the answer is the same wherever the backend runs."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.models import User


def user_tz(user: User) -> ZoneInfo:
    try:
        return ZoneInfo(user.timezone)
    except Exception:  # unknown/corrupt value must never take the app down
        return ZoneInfo("UTC")


def user_now(user: User, now: datetime | None = None) -> datetime:
    """Current time as an aware datetime in the user's timezone. `now` is injectable for tests."""
    return (now or datetime.now(timezone.utc)).astimezone(user_tz(user))


def user_today(user: User, now: datetime | None = None) -> date:
    return user_now(user, now).date()


def local_day_bounds_utc(user: User, day: date) -> tuple[datetime, datetime]:
    """[start, end) of a local calendar day expressed in UTC (for comparing against UTC timestamps)."""
    tz = user_tz(user)
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)
