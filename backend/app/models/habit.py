from datetime import date as DateT, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime
from app.models.base import IdMixin, OwnedMixin, TimestampMixin, in_values


class Habit(IdMixin, OwnedMixin, TimestampMixin, Base):
    __tablename__ = "habits"
    __table_args__ = (
        CheckConstraint(in_values("frequency", ("daily", "weekly")), name="frequency"),
        CheckConstraint("target_per_period >= 1", name="target"),
        CheckConstraint("target_per_period <= 7", name="target_max"),
        CheckConstraint("target_value IS NULL OR target_value > 0", name="target_value_positive"),
        UniqueConstraint("user_id", "name", name="uq_habits_user_name"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[DateT | None] = mapped_column(Date)
    frequency: Mapped[str] = mapped_column(String(10), default="daily", nullable=False)
    # daily: must be done every day; weekly: done on `target_per_period` days per week
    target_per_period: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    target_value: Mapped[float | None] = mapped_column(Float)  # e.g. 30 (minutes) / 5000 (steps)
    unit: Mapped[str | None] = mapped_column(String(30))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    logs: Mapped[list["HabitLog"]] = relationship(
        back_populates="habit", cascade="all, delete-orphan"
    )


class HabitLog(IdMixin, TimestampMixin, Base):
    __tablename__ = "habit_logs"
    __table_args__ = (UniqueConstraint("habit_id", "date"),)

    habit_id: Mapped[int] = mapped_column(
        ForeignKey("habits.id", ondelete="CASCADE"), index=True, nullable=False
    )
    date: Mapped[DateT] = mapped_column(Date, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    value: Mapped[float | None] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(Text)

    habit: Mapped[Habit] = relationship(back_populates="logs")
