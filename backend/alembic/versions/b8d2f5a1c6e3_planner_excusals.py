"""planner: excused activities (one activity excused on one day, with a reason)

Revision ID: b8d2f5a1c6e3
Revises: a7c1e4f8b3d9
Create Date: 2026-11-24 22:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

import app.database

revision: str = "b8d2f5a1c6e3"
down_revision: Union[str, Sequence[str], None] = "a7c1e4f8b3d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "planner_excusals",
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("ref_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", app.database.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.database.UTCDateTime(), nullable=False),
        sa.CheckConstraint("kind IN ('task', 'lesson', 'video', 'topic', 'habit', 'project')", name=op.f("ck_planner_excusals_kind")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_planner_excusals_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_planner_excusals")),
        sa.UniqueConstraint("user_id", "kind", "ref_id", "date", name="uq_planner_excusals_item_day"),
    )
    with op.batch_alter_table("planner_excusals", schema=None) as b:
        b.create_index(b.f("ix_planner_excusals_user_id"), ["user_id"], unique=False)
        b.create_index("ix_planner_excusals_user_date", ["user_id", "date"], unique=False)


def downgrade() -> None:
    op.drop_table("planner_excusals")
