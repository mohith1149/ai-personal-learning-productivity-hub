"""task completed/completed_at consistency CHECK

Revision ID: a1c4e7b92d10
Revises: 3fe8e7449f3d
Create Date: 2026-11-23 21:40:00.000000

Hand-written: Alembic autogenerate does not detect CHECK constraints on existing tables.
Short names are used because the metadata naming convention adds the ``ck_tasks_`` prefix itself.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a1c4e7b92d10"
down_revision: Union[str, Sequence[str], None] = "3fe8e7449f3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Repair any pre-existing inconsistent rows first so the constraint can be added safely.
    op.execute("UPDATE tasks SET completed_at = updated_at WHERE status = 'completed' AND completed_at IS NULL")
    op.execute("UPDATE tasks SET completed_at = NULL WHERE status <> 'completed' AND completed_at IS NOT NULL")
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "completed_consistency", "(status = 'completed') = (completed_at IS NOT NULL)"
        )


def downgrade() -> None:
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_constraint("completed_consistency", type_="check")
