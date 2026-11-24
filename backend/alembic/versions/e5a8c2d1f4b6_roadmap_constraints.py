"""roadmap: unique stage/topic titles and the completed <=> completed_at rule

Revision ID: e5a8c2d1f4b6
Revises: d4f7b1c9e3a5
Create Date: 2026-11-24 16:00:00.000000

Hand-written. Safe on existing data: the roadmap tables have never had an API, so they are empty; if rows did exist,
duplicates would make the unique constraints fail loudly rather than silently losing data.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e5a8c2d1f4b6"
down_revision: Union[str, Sequence[str], None] = "d4f7b1c9e3a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("roadmap_stages", schema=None) as b:
        b.create_unique_constraint("uq_roadmap_stages_user_title", ["user_id", "title"])
    with op.batch_alter_table("roadmap_topics", schema=None) as b:
        b.create_unique_constraint("uq_roadmap_topics_stage_title", ["stage_id", "title"])
        b.create_check_constraint(
            op.f("ck_roadmap_topics_completed_at_matches_status"), "(status = 'completed') = (completed_at IS NOT NULL)"
        )


def downgrade() -> None:
    with op.batch_alter_table("roadmap_topics", schema=None) as b:
        b.drop_constraint(op.f("ck_roadmap_topics_completed_at_matches_status"), type_="check")
        b.drop_constraint("uq_roadmap_topics_stage_title", type_="unique")
    with op.batch_alter_table("roadmap_stages", schema=None) as b:
        b.drop_constraint("uq_roadmap_stages_user_title", type_="unique")
