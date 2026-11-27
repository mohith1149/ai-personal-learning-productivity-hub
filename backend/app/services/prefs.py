"""Planning preferences stored on the user's settings row: the hours you have each weekday and the rest-day limit."""
from sqlalchemy.orm import Session

from app.models import User, UserSettings

DAYS = 7
MAX_DAY_MINUTES = 24 * 60


def settings_row(db: Session, user: User) -> UserSettings:
    if user.settings is None:
        user.settings = UserSettings(reminder_email=user.email)
        db.flush()
    return user.settings


def weekday_minutes(db: Session, user: User) -> list[int] | None:
    """Minutes available Monday..Sunday, or None when you haven't set them."""
    raw = settings_row(db, user).weekday_minutes
    if not raw:
        return None
    try:
        values = [int(p) for p in raw.split(",")]
    except ValueError:
        return None
    return values if len(values) == DAYS and all(0 <= v <= MAX_DAY_MINUTES for v in values) else None


def encode(values: list[int] | None) -> str | None:
    return None if values is None else ",".join(str(v) for v in values)
