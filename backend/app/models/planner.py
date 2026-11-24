from datetime import date as DateT

from sqlalchemy import CheckConstraint, Date, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import IdMixin, OwnedMixin, TimestampMixin, in_values

PLANNER_KINDS = ("task", "lesson", "video", "topic", "habit", "project")


class PlannerExcusal(IdMixin, OwnedMixin, TimestampMixin, Base):
    """The owner excused one activity on one day (with a reason). Excused activities are not counted as missed or overdue
    that day. The activity itself is untouched: it is not completed, rescheduled or deleted."""

    __tablename__ = "planner_excusals"
    __table_args__ = (
        CheckConstraint(in_values("kind", PLANNER_KINDS), name="kind"),
        UniqueConstraint("user_id", "kind", "ref_id", "date", name="uq_planner_excusals_item_day"),
        Index("ix_planner_excusals_user_date", "user_id", "date"),
    )

    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    ref_id: Mapped[int] = mapped_column(Integer, nullable=False)  # id of the task / lesson / video / topic / habit / project
    date: Mapped[DateT] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
