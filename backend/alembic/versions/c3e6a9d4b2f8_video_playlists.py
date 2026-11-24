"""video playlists: playlists table, videos.playlist_id + youtube_video_id

Revision ID: c3e6a9d4b2f8
Revises: b2d5f8c3a1e7
Create Date: 2026-11-24 10:00:00.000000

Hand-written. Existing videos (the table had no API before this milestone, so normally none) are moved into one
"Imported videos" playlist per owner so no row is lost before playlist_id becomes NOT NULL.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

import app.database

revision: str = "c3e6a9d4b2f8"
down_revision: Union[str, Sequence[str], None] = "b2d5f8c3a1e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "video_playlists",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("youtube_playlist_id", sa.String(length=64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("daily_target", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", app.database.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.database.UTCDateTime(), nullable=False),
        sa.CheckConstraint("daily_target BETWEEN 1 AND 50", name=op.f("ck_video_playlists_daily_target")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_video_playlists_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_video_playlists")),
        sa.UniqueConstraint("user_id", "name", name="uq_video_playlists_user_name"),
    )
    with op.batch_alter_table("video_playlists", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_video_playlists_user_id"), ["user_id"], unique=False)

    with op.batch_alter_table("videos", schema=None) as batch_op:
        batch_op.add_column(sa.Column("playlist_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("youtube_video_id", sa.String(length=20), nullable=True))

    # Keep any pre-existing video: give each owner one playlist and attach their videos to it.
    op.execute(
        "INSERT INTO video_playlists (name, daily_target, active, user_id, created_at, updated_at) "
        "SELECT 'Imported videos', 1, 1, user_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP FROM videos GROUP BY user_id"
    )
    op.execute(
        "UPDATE videos SET playlist_id = (SELECT p.id FROM video_playlists p "
        "WHERE p.user_id = videos.user_id AND p.name = 'Imported videos')"
    )

    with op.batch_alter_table("videos", schema=None) as batch_op:
        batch_op.alter_column("playlist_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            op.f("fk_videos_playlist_id_video_playlists"), "video_playlists", ["playlist_id"], ["id"], ondelete="CASCADE"
        )
        batch_op.create_index("ix_videos_playlist_status_pos", ["playlist_id", "status", "position"], unique=False)
        batch_op.create_unique_constraint("uq_videos_playlist_youtube", ["playlist_id", "youtube_video_id"])


def downgrade() -> None:
    with op.batch_alter_table("videos", schema=None) as batch_op:
        batch_op.drop_constraint("uq_videos_playlist_youtube", type_="unique")
        batch_op.drop_index("ix_videos_playlist_status_pos")
        batch_op.drop_constraint(op.f("fk_videos_playlist_id_video_playlists"), type_="foreignkey")
        batch_op.drop_column("youtube_video_id")
        batch_op.drop_column("playlist_id")
    with op.batch_alter_table("video_playlists", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_video_playlists_user_id"))
    op.drop_table("video_playlists")
