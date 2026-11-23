from datetime import date as DateT, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime
from app.models.base import IdMixin, OwnedMixin, TimestampMixin, in_values

EMAIL_TYPES = ("daily_plan", "overdue", "weekly_report", "test")
EMAIL_STATUSES = ("pending", "sent", "failed", "skipped")


class DailyCheckin(IdMixin, OwnedMixin, TimestampMixin, Base):
    __tablename__ = "daily_checkins"
    __table_args__ = (UniqueConstraint("user_id", "date"),)

    date: Mapped[DateT] = mapped_column(Date, nullable=False)
    main_priority: Mapped[str | None] = mapped_column(Text)
    project_mode: Mapped[str | None] = mapped_column(String(20))  # new_project | existing_project
    available_minutes: Mapped[int | None] = mapped_column(Integer)
    schedule_changes: Mapped[str | None] = mapped_column(Text)
    generated_plan: Mapped[str | None] = mapped_column(Text)  # JSON


class DailyCheckout(IdMixin, OwnedMixin, TimestampMixin, Base):
    __tablename__ = "daily_checkouts"
    __table_args__ = (UniqueConstraint("user_id", "date"),)

    date: Mapped[DateT] = mapped_column(Date, nullable=False)
    videos_note: Mapped[str | None] = mapped_column(Text)
    agentic_note: Mapped[str | None] = mapped_column(Text)
    project_done: Mapped[bool | None] = mapped_column(Boolean)
    repo: Mapped[str | None] = mapped_column(String(500))
    commit_made: Mapped[bool | None] = mapped_column(Boolean)
    physical_done: Mapped[bool | None] = mapped_column(Boolean)
    pending_note: Mapped[str | None] = mapped_column(Text)
    completion_score: Mapped[int | None] = mapped_column(Integer)
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class EmailNotification(IdMixin, OwnedMixin, TimestampMixin, Base):
    __tablename__ = "email_notifications"
    __table_args__ = (
        # Idempotency key: one email of each type per period (date or ISO week).
        UniqueConstraint("user_id", "type", "period_key"),
        CheckConstraint(in_values("type", EMAIL_TYPES), name="type"),
        CheckConstraint(in_values("status", EMAIL_STATUSES), name="status"),
    )

    type: Mapped[str] = mapped_column(String(20), nullable=False)
    period_key: Mapped[str] = mapped_column(String(40), nullable=False)
    recipient: Mapped[str | None] = mapped_column(String(255))
    subject: Mapped[str | None] = mapped_column(String(300))
    body_html: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="pending", nullable=False)
    provider: Mapped[str | None] = mapped_column(String(20))
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class WeeklyReport(IdMixin, OwnedMixin, TimestampMixin, Base):
    __tablename__ = "weekly_reports"
    __table_args__ = (UniqueConstraint("user_id", "week_start"),)

    week_start: Mapped[DateT] = mapped_column(Date, nullable=False)
    week_end: Mapped[DateT] = mapped_column(Date, nullable=False)
    metrics: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    ai_summary: Mapped[str | None] = mapped_column(Text)


class AIConversation(IdMixin, OwnedMixin, TimestampMixin, Base):
    __tablename__ = "ai_conversations"

    title: Mapped[str] = mapped_column(String(200), default="New conversation", nullable=False)


class AIMessage(IdMixin, TimestampMixin, Base):
    __tablename__ = "ai_messages"

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)  # JSON content blocks


class AIPendingAction(IdMixin, TimestampMixin, Base):
    __tablename__ = "ai_pending_actions"
    __table_args__ = (
        CheckConstraint(
            in_values("status", ("pending", "approved", "rejected", "executed", "failed")),
            name="status",
        ),
    )

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    tool_use_id: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(60), nullable=False)
    tool_input: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    status: Mapped[str] = mapped_column(String(10), default="pending", nullable=False)
    result: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
