import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import Strict

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _time(v: str | None) -> str | None:
    if v is not None and not _HHMM.match(v):
        raise ValueError("Use a 24-hour time like 07:30")
    return v


class SettingsOut(BaseModel):
    reminder_email: str | None
    email_enabled: bool
    reminder_time: str
    overdue_reminders_enabled: bool
    overdue_reminder_time: str
    weekly_report_enabled: bool
    weekly_report_day: int
    weekly_report_time: str
    server_ready: bool  # the server has e-mail credentials; without them nothing can be sent


class SettingsUpdate(Strict):
    reminder_email: EmailStr | None = None
    email_enabled: bool | None = None
    reminder_time: str | None = None
    overdue_reminders_enabled: bool | None = None
    overdue_reminder_time: str | None = None
    weekly_report_enabled: bool | None = None
    weekly_report_day: int | None = Field(default=None, ge=0, le=6)
    weekly_report_time: str | None = None

    _t = field_validator("reminder_time", "overdue_reminder_time", "weekly_report_time")(_time)


class NotificationOut(BaseModel):
    id: int
    type: Literal["daily_plan", "overdue", "weekly_report", "test"]
    period_key: str
    status: Literal["pending", "sent", "failed", "skipped"]
    recipient: str | None
    subject: str | None
    error: str | None
    attempts: int
    sent_at: datetime | None
    created_at: datetime


class PreviewOut(BaseModel):
    subject: str | None
    html: str | None
    would_send: bool


class RunDueOut(BaseModel):
    handled: int
    sent: int
    failed: int
    skipped: int
