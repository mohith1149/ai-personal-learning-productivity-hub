"""course lesson completed/completed_at consistency CHECK

Revision ID: b2d5f8c3a1e7
Revises: a1c4e7b92d10
Create Date: 2026-11-23 23:10:00.000000

Hand-written (autogenerate does not detect CHECK constraints on existing tables).
Short name because the naming convention adds the ``ck_course_lessons_`` prefix itself.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b2d5f8c3a1e7"
down_revision: Union[str, Sequence[str], None] = "a1c4e7b92d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Repair any pre-existing inconsistent rows first so the constraint can be added safely.
    op.execute("UPDATE course_lessons SET completed_at = updated_at WHERE status = 'completed' AND completed_at IS NULL")
    op.execute("UPDATE course_lessons SET completed_at = NULL WHERE status <> 'completed' AND completed_at IS NOT NULL")
    with op.batch_alter_table("course_lessons", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "completed_at_matches_status", "(status = 'completed') = (completed_at IS NOT NULL)"
        )


def downgrade() -> None:
    with op.batch_alter_table("course_lessons", schema=None) as batch_op:
        batch_op.drop_constraint("completed_at_matches_status", type_="check")
