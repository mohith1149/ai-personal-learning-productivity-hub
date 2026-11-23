from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime
from app.models.base import IdMixin, OwnedMixin, TimestampMixin, in_values

TASK_TYPES = ("one_time", "recurring", "course_lesson", "habit", "project_dev")
TASK_STATUSES = ("pending", "in_progress", "completed", "cancelled")
FREQUENCIES = ("daily", "weekdays", "weekly", "monthly")


class TaskCategory(IdMixin, OwnedMixin, TimestampMixin, Base):
    __tablename__ = "task_categories"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    color: Mapped[str] = mapped_column(String(16), default="#6366f1", nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class RecurringTask(IdMixin, OwnedMixin, TimestampMixin, Base):
    __tablename__ = "recurring_tasks"
    __table_args__ = (
        CheckConstraint(in_values("frequency", FREQUENCIES), name="frequency"),
        CheckConstraint("priority BETWEEN 1 AND 4", name="priority"),
        Index("ix_recurring_user_active", "user_id", "active"),
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("task_categories.id", ondelete="SET NULL")
    )
    priority: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer)
    task_type: Mapped[str] = mapped_column(String(20), default="recurring", nullable=False)
    frequency: Mapped[str] = mapped_column(String(16), nullable=False)
    days_of_week: Mapped[str | None] = mapped_column(String(20))  # "0,2,4" (Mon=0)
    day_of_month: Mapped[int | None] = mapped_column(Integer)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_generated_date: Mapped[date | None] = mapped_column(Date)

    category: Mapped[TaskCategory | None] = relationship()


class Task(IdMixin, OwnedMixin, TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(in_values("task_type", TASK_TYPES), name="task_type"),
        CheckConstraint(in_values("status", TASK_STATUSES), name="status"),
        CheckConstraint("priority BETWEEN 1 AND 4", name="priority"),
        UniqueConstraint("recurring_task_id", "scheduled_date"),
        Index("ix_tasks_user_sched", "user_id", "scheduled_date"),
        Index("ix_tasks_user_status", "user_id", "status"),
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("task_categories.id", ondelete="SET NULL")
    )
    task_type: Mapped[str] = mapped_column(String(20), default="one_time", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=2, nullable=False)  # 1=urgent … 4=low
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    scheduled_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    due_time: Mapped[str | None] = mapped_column(String(5))  # "HH:MM" local time
    estimated_minutes: Mapped[int | None] = mapped_column(Integer)
    actual_minutes: Mapped[int | None] = mapped_column(Integer)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    recurring_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("recurring_tasks.id", ondelete="SET NULL")
    )
    lesson_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_lessons.id", ondelete="SET NULL")
    )
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    challenge_id: Mapped[int | None] = mapped_column(
        ForeignKey("daily_challenges.id", ondelete="SET NULL")
    )
    habit_id: Mapped[int | None] = mapped_column(ForeignKey("habits.id", ondelete="SET NULL"))
    carried_from_date: Mapped[date | None] = mapped_column(Date)
    carry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    category: Mapped[TaskCategory | None] = relationship()
