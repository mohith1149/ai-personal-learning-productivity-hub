from datetime import date as DateT, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime
from app.models.base import IdMixin, OwnedMixin, TimestampMixin, in_values

COURSE_KINDS = ("course", "video_series")
COURSE_STATUSES = ("active", "paused", "completed", "archived")
LESSON_TYPES = ("lesson", "video")
LESSON_STATUSES = ("not_started", "in_progress", "completed")
TOPIC_STATUSES = ("not_started", "in_progress", "completed")
VIDEO_STATUSES = ("unwatched", "watching", "completed")


class Course(IdMixin, OwnedMixin, TimestampMixin, Base):
    __tablename__ = "courses"
    __table_args__ = (
        CheckConstraint(in_values("kind", COURSE_KINDS), name="kind"),
        CheckConstraint(in_values("status", COURSE_STATUSES), name="status"),
        Index("ix_courses_user_status", "user_id", "status"),
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(100))
    url: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16), default="course", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    target_date: Mapped[DateT | None] = mapped_column(Date)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_studied_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    modules: Mapped[list["CourseModule"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="CourseModule.position",
    )


class CourseModule(IdMixin, TimestampMixin, Base):
    __tablename__ = "course_modules"
    __table_args__ = (Index("ix_modules_course_pos", "course_id", "position"),)

    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    course: Mapped[Course] = relationship(back_populates="modules")
    lessons: Mapped[list["CourseLesson"]] = relationship(
        back_populates="module",
        cascade="all, delete-orphan",
        order_by="CourseLesson.position",
    )


class CourseLesson(IdMixin, TimestampMixin, Base):
    """Course lesson or ByteByteGo video (lesson_type='video') — the video-progress table."""

    __tablename__ = "course_lessons"
    __table_args__ = (
        CheckConstraint(in_values("lesson_type", LESSON_TYPES), name="lesson_type"),
        CheckConstraint(in_values("status", LESSON_STATUSES), name="status"),
        CheckConstraint(
            "(status = 'completed') = (completed_at IS NOT NULL)", name="completed_at_matches_status"
        ),
        Index("ix_lessons_course_status_pos", "course_id", "status", "position"),
    )

    module_id: Mapped[int] = mapped_column(
        ForeignKey("course_modules.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str | None] = mapped_column(String(500))
    lesson_type: Mapped[str] = mapped_column(String(10), default="lesson", nullable=False)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="not_started", nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    notes: Mapped[str | None] = mapped_column(Text)

    module: Mapped[CourseModule] = relationship(back_populates="lessons")


class RoadmapStage(IdMixin, OwnedMixin, TimestampMixin, Base):
    __tablename__ = "roadmap_stages"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    topics: Mapped[list["RoadmapTopic"]] = relationship(
        back_populates="stage", cascade="all, delete-orphan", order_by="RoadmapTopic.position"
    )


class RoadmapTopic(IdMixin, OwnedMixin, TimestampMixin, Base):
    __tablename__ = "roadmap_topics"
    __table_args__ = (
        CheckConstraint(in_values("status", TOPIC_STATUSES), name="status"),
        CheckConstraint("completion_pct BETWEEN 0 AND 100", name="completion_pct"),
        Index("ix_topics_stage_pos", "stage_id", "position"),
    )

    stage_id: Mapped[int] = mapped_column(
        ForeignKey("roadmap_stages.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="not_started", nullable=False)
    completion_pct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exercises: Mapped[str | None] = mapped_column(Text)
    project_applications: Mapped[str | None] = mapped_column(Text)
    minutes_spent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    last_studied_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    stage: Mapped[RoadmapStage] = relationship(back_populates="topics")


class LearningResource(IdMixin, OwnedMixin, TimestampMixin, Base):
    __tablename__ = "learning_resources"

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str | None] = mapped_column(String(500))
    resource_type: Mapped[str] = mapped_column(String(30), default="article", nullable=False)
    roadmap_topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("roadmap_topics.id", ondelete="CASCADE")
    )
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    notes: Mapped[str | None] = mapped_column(Text)


class LearningSession(IdMixin, OwnedMixin, TimestampMixin, Base):
    __tablename__ = "learning_sessions"
    __table_args__ = (
        CheckConstraint("minutes > 0", name="minutes_positive"),
        Index("ix_sessions_user_date", "user_id", "date"),
    )

    date: Mapped[DateT] = mapped_column(Date, nullable=False)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id", ondelete="SET NULL"))
    lesson_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_lessons.id", ondelete="SET NULL")
    )
    roadmap_topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("roadmap_topics.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)


class VideoPlaylist(IdMixin, OwnedMixin, TimestampMixin, Base):
    """A named list of videos (e.g. "ByteByteGo") with a daily watch target."""

    __tablename__ = "video_playlists"
    __table_args__ = (
        CheckConstraint("daily_target BETWEEN 1 AND 50", name="daily_target"),
        UniqueConstraint("user_id", "name", name="uq_video_playlists_user_name"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500))
    youtube_playlist_id: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    daily_target: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    videos: Mapped[list["Video"]] = relationship(
        back_populates="playlist", cascade="all, delete-orphan", order_by="Video.position"
    )


class Video(IdMixin, OwnedMixin, TimestampMixin, Base):
    """A video in a playlist. Completion is recorded only by explicit user action."""

    __tablename__ = "videos"
    __table_args__ = (
        CheckConstraint(in_values("status", VIDEO_STATUSES), name="status"),
        # The next-video recommendation query is driven by this index.
        Index("ix_videos_user_status_pos", "user_id", "status", "position"),
        Index("ix_videos_playlist_status_pos", "playlist_id", "status", "position"),
        # completed <=> completed_at is set (keeps the history honest)
        CheckConstraint(
            "(status = 'completed') = (completed_at IS NOT NULL)", name="completed_at_matches_status"
        ),
        # The same YouTube video cannot be added twice to one playlist (NULL ids are exempt).
        UniqueConstraint("playlist_id", "youtube_video_id", name="uq_videos_playlist_youtube"),
    )

    playlist_id: Mapped[int] = mapped_column(
        ForeignKey("video_playlists.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str | None] = mapped_column(String(500))
    youtube_video_id: Mapped[str | None] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(12), default="unwatched", nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    notes: Mapped[str | None] = mapped_column(Text)

    playlist: Mapped[VideoPlaylist] = relationship(back_populates="videos")
