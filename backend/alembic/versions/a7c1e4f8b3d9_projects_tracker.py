"""projects: origin, start date, unique titles, completion rules, session task link and notes

Revision ID: a7c1e4f8b3d9
Revises: f6b9d3e2a5c7
Create Date: 2026-11-24 20:00:00.000000

Hand-written. Any pre-existing rows are first made consistent with the new completion rules (the project tables
have never had an API, so normally they are empty), so the CHECK constraints can't fail on old data.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7c1e4f8b3d9"
down_revision: Union[str, Sequence[str], None] = "f6b9d3e2a5c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE projects SET completed_at = updated_at WHERE status = 'completed' AND completed_at IS NULL")
    op.execute("UPDATE projects SET completed_at = NULL WHERE status <> 'completed' AND completed_at IS NOT NULL")
    op.execute("UPDATE project_milestones SET completed_at = updated_at WHERE status = 'done' AND completed_at IS NULL")
    op.execute("UPDATE project_milestones SET completed_at = NULL WHERE status <> 'done' AND completed_at IS NOT NULL")

    with op.batch_alter_table("projects", schema=None) as b:
        b.add_column(sa.Column("origin", sa.String(length=10), nullable=False, server_default="new"))
        b.add_column(sa.Column("start_date", sa.Date(), nullable=True))
        b.create_check_constraint(op.f("ck_projects_origin"), "origin IN ('new', 'existing')")
        b.create_check_constraint(
            op.f("ck_projects_completed_at_matches_status"), "(status = 'completed') = (completed_at IS NOT NULL)"
        )
        b.create_unique_constraint("uq_projects_user_title", ["user_id", "title"])
    with op.batch_alter_table("project_milestones", schema=None) as b:
        b.create_check_constraint(
            op.f("ck_project_milestones_completed_at_matches_status"), "(status = 'done') = (completed_at IS NOT NULL)"
        )
        b.create_unique_constraint("uq_project_milestones_project_title", ["project_id", "title"])
    with op.batch_alter_table("project_sessions", schema=None) as b:
        b.add_column(sa.Column("task_id", sa.Integer(), nullable=True))
        b.add_column(sa.Column("notes", sa.Text(), nullable=True))
        b.create_foreign_key(op.f("fk_project_sessions_task_id_tasks"), "tasks", ["task_id"], ["id"], ondelete="SET NULL")
        b.create_index("ix_project_sessions_user_date", ["user_id", "date"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("project_sessions", schema=None) as b:
        b.drop_index("ix_project_sessions_user_date")
        b.drop_constraint(op.f("fk_project_sessions_task_id_tasks"), type_="foreignkey")
        b.drop_column("notes")
        b.drop_column("task_id")
    with op.batch_alter_table("project_milestones", schema=None) as b:
        b.drop_constraint("uq_project_milestones_project_title", type_="unique")
        b.drop_constraint(op.f("ck_project_milestones_completed_at_matches_status"), type_="check")
    with op.batch_alter_table("projects", schema=None) as b:
        b.drop_constraint("uq_projects_user_title", type_="unique")
        b.drop_constraint(op.f("ck_projects_completed_at_matches_status"), type_="check")
        b.drop_constraint(op.f("ck_projects_origin"), type_="check")
        b.drop_column("start_date")
        b.drop_column("origin")
