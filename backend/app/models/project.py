from datetime import date as DateT, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime
from app.models.base import IdMixin, OwnedMixin, TimestampMixin, in_values

PROJECT_STATUSES = ("active", "paused", "completed", "archived")
IDEA_STATUSES = ("backlog", "in_progress", "done", "dropped")
CHALLENGE_STATUSES = ("planned", "in_progress", "completed", "missed", "excused")
CHALLENGE_MODES = ("new_project", "existing_project")
VERIFICATION_SOURCES = ("github_api", "local_git", "unverified")


class ProjectIdea(IdMixin, OwnedMixin, TimestampMixin, Base):
    __tablename__ = "project_ideas"
    __table_args__ = (
        CheckConstraint(in_values("status", IDEA_STATUSES), name="status"),
        CheckConstraint(
            in_values("difficulty", ("beginner", "intermediate", "advanced")), name="difficulty"
        ),
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    problem_statement: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(String(16), default="intermediate", nullable=False)
    concepts: Mapped[str | None] = mapped_column(Text)  # JSON list
    tech_stack: Mapped[str | None] = mapped_column(Text)
    features: Mapped[str | None] = mapped_column(Text)  # JSON list
    milestones: Mapped[str | None] = mapped_column(Text)  # JSON list
    learning_outcomes: Mapped[str | None] = mapped_column(Text)
    estimated_hours: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="backlog", nullable=False)
    source: Mapped[str] = mapped_column(String(10), default="custom", nullable=False)
    related_topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("roadmap_topics.id", ondelete="SET NULL")
    )


class Project(IdMixin, OwnedMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(in_values("status", PROJECT_STATUSES), name="status"),
        Index("ix_projects_user_status", "user_id", "status"),
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    problem_statement: Mapped[str | None] = mapped_column(Text)
    tech_stack: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    is_ai_project: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    idea_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_ideas.id", ondelete="SET NULL")
    )
    repo_url: Mapped[str | None] = mapped_column(String(500))
    local_path: Mapped[str | None] = mapped_column(String(500))
    repository_id: Mapped[int | None] = mapped_column(
        ForeignKey("git_repositories.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_activity_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    milestones: Mapped[list["ProjectMilestone"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectMilestone.position",
    )


class ProjectMilestone(IdMixin, TimestampMixin, Base):
    __tablename__ = "project_milestones"
    __table_args__ = (CheckConstraint(in_values("status", ("pending", "done")), name="status"),)

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="pending", nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    due_date: Mapped[DateT | None] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    evidence: Mapped[str | None] = mapped_column(Text)

    project: Mapped[Project] = relationship(back_populates="milestones")


class GitRepository(IdMixin, OwnedMixin, TimestampMixin, Base):
    __tablename__ = "git_repositories"
    __table_args__ = (UniqueConstraint("user_id", "full_name"),)

    provider: Mapped[str] = mapped_column(String(16), default="github", nullable=False)
    owner: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    full_name: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    default_branch: Mapped[str | None] = mapped_column(String(100))
    is_private: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    github_id: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    pushed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class GitCommit(IdMixin, TimestampMixin, Base):
    __tablename__ = "git_commits"
    __table_args__ = (
        UniqueConstraint("repository_id", "sha"),
        CheckConstraint(
            in_values("verification_source", VERIFICATION_SOURCES), name="verification_source"
        ),
        Index("ix_commits_repo_date", "repository_id", "committed_at"),
    )

    repository_id: Mapped[int] = mapped_column(
        ForeignKey("git_repositories.id", ondelete="CASCADE"), nullable=False
    )
    sha: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    author_name: Mapped[str | None] = mapped_column(String(200))
    author_login: Mapped[str | None] = mapped_column(String(100))
    committed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    url: Mapped[str | None] = mapped_column(String(500))
    additions: Mapped[int | None] = mapped_column(Integer)
    deletions: Mapped[int | None] = mapped_column(Integer)
    files_changed: Mapped[int | None] = mapped_column(Integer)
    verification_source: Mapped[str] = mapped_column(String(16), default="unverified", nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    repository: Mapped[GitRepository] = relationship()


class DailyChallenge(IdMixin, OwnedMixin, TimestampMixin, Base):
    __tablename__ = "daily_challenges"
    __table_args__ = (
        UniqueConstraint("user_id", "date"),
        CheckConstraint(in_values("status", CHALLENGE_STATUSES), name="status"),
        CheckConstraint(in_values("mode", CHALLENGE_MODES), name="mode"),
        # A completed day must carry evidence; an excused day must carry a reason.
        CheckConstraint(
            "status <> 'completed' OR (evidence_type IS NOT NULL AND implemented_summary IS NOT NULL)",
            name="completed_needs_evidence",
        ),
        CheckConstraint("status <> 'excused' OR excuse_reason IS NOT NULL", name="excused_needs_reason"),
    )

    date: Mapped[DateT] = mapped_column(Date, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    idea_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_ideas.id", ondelete="SET NULL")
    )
    planned_task: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer)
    actual_minutes: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="planned", nullable=False)
    implemented_summary: Mapped[str | None] = mapped_column(Text)
    evidence_type: Mapped[str | None] = mapped_column(String(16))  # commit | milestone
    commit_id: Mapped[int | None] = mapped_column(ForeignKey("git_commits.id", ondelete="SET NULL"))
    milestone_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_milestones.id", ondelete="SET NULL")
    )
    excuse_reason: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    project: Mapped[Project | None] = relationship()
    commit: Mapped[GitCommit | None] = relationship()
    milestone: Mapped[ProjectMilestone | None] = relationship()
