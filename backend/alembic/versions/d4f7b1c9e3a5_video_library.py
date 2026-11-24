"""video library: one video per user, collections reference it through video_memberships

Revision ID: d4f7b1c9e3a5
Revises: c3e6a9d4b2f8
Create Date: 2026-11-24 14:00:00.000000

Hand-written (SQLite batch mode; autogenerate misses the CHECK constraints).

Data is preserved:
  * every existing videos.playlist_id becomes a row in video_memberships (keeping its position);
  * the same YouTube video present in several playlists collapses into ONE library row (the oldest id wins) and
    every playlist keeps its membership of it - notes/status of the surviving row are kept;
  * existing playlists keep their hand-set order (recommend_order = 'manual').
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

import app.database

revision: str = "d4f7b1c9e3a5"
down_revision: Union[str, Sequence[str], None] = "c3e6a9d4b2f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("video_playlists", schema=None) as b:
        b.add_column(sa.Column("kind", sa.String(length=12), nullable=False, server_default="collection"))
        b.add_column(sa.Column("youtube_channel_id", sa.String(length=64), nullable=True))
        b.add_column(sa.Column("thumbnail_url", sa.String(length=500), nullable=True))
        b.add_column(sa.Column("reported_total", sa.Integer(), nullable=True))
        b.add_column(sa.Column("retrieved_count", sa.Integer(), nullable=False, server_default="0"))
        b.add_column(sa.Column("recommend_order", sa.String(length=8), nullable=False, server_default="manual"))
        b.create_check_constraint(op.f("ck_video_playlists_kind"), "kind IN ('collection', 'playlist', 'channel')")
        b.create_check_constraint(
            op.f("ck_video_playlists_recommend_order"), "recommend_order IN ('oldest', 'newest', 'manual')"
        )

    with op.batch_alter_table("videos", schema=None) as b:
        b.add_column(sa.Column("thumbnail_url", sa.String(length=500), nullable=True))
        b.add_column(sa.Column("duration_seconds", sa.Integer(), nullable=True))
        b.add_column(sa.Column("published_at", app.database.UTCDateTime(), nullable=True))
        b.add_column(sa.Column("channel_id", sa.String(length=64), nullable=True))
        b.add_column(sa.Column("channel_title", sa.String(length=200), nullable=True))
        b.add_column(sa.Column("removed_at", app.database.UTCDateTime(), nullable=True))

    op.create_table(
        "video_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("playlist_id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["playlist_id"], ["video_playlists.id"], name=op.f("fk_video_memberships_playlist_id_video_playlists"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], name=op.f("fk_video_memberships_video_id_videos"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_video_memberships")),
        sa.UniqueConstraint("playlist_id", "video_id", name="uq_video_memberships_playlist_video"),
    )
    with op.batch_alter_table("video_memberships", schema=None) as b:
        b.create_index(b.f("ix_video_memberships_playlist_id"), ["playlist_id"], unique=False)
        b.create_index(b.f("ix_video_memberships_video_id"), ["video_id"], unique=False)

    op.execute("INSERT INTO video_memberships (playlist_id, video_id, position) SELECT playlist_id, id, position FROM videos")

    # Collapse duplicates of the same YouTube video (per user) into the oldest row.
    bind = op.get_bind()
    dupes = bind.execute(sa.text(
        "SELECT v.id, k.keep FROM videos v JOIN "
        "(SELECT user_id, youtube_video_id, MIN(id) AS keep FROM videos WHERE youtube_video_id IS NOT NULL "
        " GROUP BY user_id, youtube_video_id HAVING COUNT(*) > 1) k "
        "ON k.user_id = v.user_id AND k.youtube_video_id = v.youtube_video_id WHERE v.id <> k.keep"
    )).all()
    for dup_id, keep_id in dupes:
        # re-point memberships unless the survivor is already in that playlist
        bind.execute(sa.text(
            "UPDATE video_memberships SET video_id = :keep WHERE video_id = :dup AND playlist_id NOT IN "
            "(SELECT playlist_id FROM video_memberships WHERE video_id = :keep)"), {"keep": keep_id, "dup": dup_id})
        bind.execute(sa.text("DELETE FROM video_memberships WHERE video_id = :dup"), {"dup": dup_id})
        bind.execute(sa.text("DELETE FROM videos WHERE id = :dup"), {"dup": dup_id})

    with op.batch_alter_table("videos", schema=None) as b:
        b.drop_constraint("uq_videos_playlist_youtube", type_="unique")
        b.drop_index("ix_videos_playlist_status_pos")
        b.drop_index("ix_videos_user_status_pos")
        b.drop_constraint(op.f("fk_videos_playlist_id_video_playlists"), type_="foreignkey")
        b.drop_column("playlist_id")
        b.drop_column("position")
        b.create_unique_constraint("uq_videos_user_youtube", ["user_id", "youtube_video_id"])
        b.create_index("ix_videos_user_status_published", ["user_id", "status", "published_at"], unique=False)


def downgrade() -> None:
    """Best effort: a video that sat in several collections keeps only its first one."""
    with op.batch_alter_table("videos", schema=None) as b:
        b.drop_index("ix_videos_user_status_published")
        b.drop_constraint("uq_videos_user_youtube", type_="unique")
        b.add_column(sa.Column("playlist_id", sa.Integer(), nullable=True))
        b.add_column(sa.Column("position", sa.Integer(), nullable=False, server_default="0"))
    op.execute(
        "UPDATE videos SET playlist_id = (SELECT m.playlist_id FROM video_memberships m WHERE m.video_id = videos.id "
        "ORDER BY m.id LIMIT 1), position = COALESCE((SELECT m.position FROM video_memberships m "
        "WHERE m.video_id = videos.id ORDER BY m.id LIMIT 1), 0)"
    )
    op.execute("DELETE FROM videos WHERE playlist_id IS NULL")
    with op.batch_alter_table("videos", schema=None) as b:
        b.alter_column("playlist_id", existing_type=sa.Integer(), nullable=False)
        b.create_foreign_key(
            op.f("fk_videos_playlist_id_video_playlists"), "video_playlists", ["playlist_id"], ["id"], ondelete="CASCADE"
        )
        b.create_index("ix_videos_playlist_status_pos", ["playlist_id", "status", "position"], unique=False)
        b.create_index("ix_videos_user_status_pos", ["user_id", "status", "position"], unique=False)
        b.create_unique_constraint("uq_videos_playlist_youtube", ["playlist_id", "youtube_video_id"])
        for col in ("removed_at", "channel_title", "channel_id", "published_at", "duration_seconds", "thumbnail_url"):
            b.drop_column(col)
    op.drop_table("video_memberships")
    with op.batch_alter_table("video_playlists", schema=None) as b:
        b.drop_constraint(op.f("ck_video_playlists_recommend_order"), type_="check")
        b.drop_constraint(op.f("ck_video_playlists_kind"), type_="check")
        for col in ("recommend_order", "retrieved_count", "reported_total", "thumbnail_url", "youtube_channel_id", "kind"):
            b.drop_column(col)
