from datetime import datetime

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.database import UTCDateTime, utcnow


class IdMixin:
    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class OwnedMixin:
    """Adds user_id FK (cascade delete) — every user-owned table uses this."""

    @declared_attr
    def user_id(cls) -> Mapped[int]:  # noqa: N805
        return mapped_column(
            ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
        )


def in_values(column: str, values: tuple[str, ...]) -> str:
    """Build a portable CHECK expression: column IN ('a','b')."""
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"
