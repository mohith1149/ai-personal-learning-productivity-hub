from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime, utcnow
from app.models.base import IdMixin, OwnedMixin, TimestampMixin


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    # Bumped on logout / password change; tokens with an older version are rejected.
    session_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    settings: Mapped["UserSettings"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class UserSettings(TimestampMixin, Base):
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    reminder_email: Mapped[str | None] = mapped_column(String(255))
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reminder_time: Mapped[str] = mapped_column(String(5), default="07:00", nullable=False)  # HH:MM local
    overdue_reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    overdue_reminder_time: Mapped[str] = mapped_column(String(5), default="18:00", nullable=False)
    weekly_report_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    weekly_report_day: Mapped[int] = mapped_column(Integer, default=6, nullable=False)  # 0=Mon … 6=Sun
    weekly_report_time: Mapped[str] = mapped_column(String(5), default="18:00", nullable=False)
    daily_learning_minutes: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    bbg_daily_target: Mapped[int] = mapped_column(Integer, default=2, nullable=False)

    user: Mapped[User] = relationship(back_populates="settings")


class OAuthToken(IdMixin, OwnedMixin, TimestampMixin, Base):
    __tablename__ = "oauth_tokens"
    __table_args__ = (UniqueConstraint("user_id", "provider"),)

    provider: Mapped[str] = mapped_column(String(32), nullable=False)  # github | gmail
    access_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    scope: Mapped[str | None] = mapped_column(String(512))
    account_login: Mapped[str | None] = mapped_column(String(255))
    auth_type: Mapped[str] = mapped_column(String(16), default="oauth", nullable=False)  # oauth | pat


class ActivityLog(IdMixin, OwnedMixin, TimestampMixin, Base):
    """Append-only audit trail; preserves history of every important change."""

    __tablename__ = "activity_log"

    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="user", nullable=False)  # user|ai|system
    details: Mapped[str | None] = mapped_column(Text)  # JSON


class LoginAttempt(IdMixin, Base):
    """Failed-login log used for lockout. Stores the e-mail tried and client IP, never passwords."""

    __tablename__ = "login_attempts"
    __table_args__ = (Index("ix_login_attempts_email_time", "email", "attempted_at"),)

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    attempted_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
