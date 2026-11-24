"""AI Engineering roadmap: five stages of topics the owner works through.

Rules:
  * The five stages and their topics (the owner's exact lists) are created ONCE per user, the first time the roadmap is
    opened, all "not started". Nothing is ever marked completed automatically.
  * A topic becomes completed ONLY through `set_status` (an explicit action). DB CHECK: completed <=> completed_at.
  * Study time and study dates are real records (`learning_sessions` rows with a roadmap_topic_id). A topic's minutes,
    study days and last-studied date are always computed from them, so deleting a session corrects the numbers.
  * Logging study time on a not-started topic moves it to "in progress" (never to completed).
  * Progress is computed from topic statuses: stage % = completed / topics in the stage (floored), overall % over all topics.
  * Every query is scoped to the user; another user's id behaves like "not found".
"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.timeutil import user_today
from app.models import LearningSession, RoadmapStage, RoadmapTopic, User
from app.schemas import roadmap as s


class NotFound(Exception):
    pass


class RuleError(ValueError):
    """A business-rule violation (HTTP 422)."""


class Conflict(Exception):
    """Clashes with existing data (HTTP 409)."""


# The owner's roadmap, exactly as specified. Stage descriptions are deliberately empty (nothing invented).
ROADMAP: list[tuple[str, list[str]]] = [
    ("Stage 1 – Programming and Foundations", [
        "Python", "Java fundamentals", "Data structures and algorithms", "Object-oriented programming",
        "SQL and databases", "Git and GitHub", "Linux and command line", "APIs and HTTP fundamentals"]),
    ("Stage 2 – Machine Learning and Deep Learning", [
        "Machine learning fundamentals", "Supervised and unsupervised learning", "Model evaluation", "Feature engineering",
        "Scikit-learn", "Neural networks", "PyTorch", "TensorFlow", "Transformers fundamentals"]),
    ("Stage 3 – Generative AI and LLM Engineering", [
        "LLM fundamentals", "Tokens and embeddings", "Prompt engineering", "Context windows", "Structured outputs",
        "Function and tool calling", "RAG", "Vector databases", "Semantic search", "LangChain", "LLM evaluation"]),
    ("Stage 4 – Agentic AI and Automation", [
        "AI agents", "Agent architectures", "Tool calling", "Planning and reasoning", "LangGraph", "Multi-agent systems",
        "MCP", "n8n", "Workflow automation", "Human-in-the-loop approval", "Agent evaluation and observability"]),
    ("Stage 5 – AI Engineering and Deployment", [
        "FastAPI", "Backend architecture", "Docker", "PostgreSQL", "AWS", "CI/CD", "Cloud deployment",
        "Authentication and security", "Monitoring", "Logging", "Testing", "Production AI systems"]),
]


def ensure_seeded(db: Session, user: User) -> bool:
    """Create the five stages for a user who has none. Idempotent and safe if two requests race (unique titles)."""
    if db.scalar(select(RoadmapStage.id).where(RoadmapStage.user_id == user.id).limit(1)) is not None:
        return False
    try:
        for i, (title, topics) in enumerate(ROADMAP, start=1):
            stage = RoadmapStage(user_id=user.id, title=title, position=i)
            db.add(stage)
            db.flush()
            for j, topic in enumerate(topics, start=1):
                db.add(RoadmapTopic(user_id=user.id, stage_id=stage.id, title=topic, position=j, status="not_started"))
        db.commit()
        return True
    except IntegrityError:  # another request seeded first
        db.rollback()
        return False


# ============================== lookups ==============================


def _get_topic(db: Session, user: User, topic_id: int) -> RoadmapTopic:
    t = db.scalar(select(RoadmapTopic).where(RoadmapTopic.id == topic_id, RoadmapTopic.user_id == user.id))
    if t is None:
        raise NotFound("Topic not found")
    return t


def _study_stats(db: Session, user: User) -> dict[int, tuple[int, int, object]]:
    """topic_id -> (minutes, distinct study days, last study date), computed from the logged sessions."""
    rows = db.execute(
        select(LearningSession.roadmap_topic_id, func.sum(LearningSession.minutes),
               func.count(func.distinct(LearningSession.date)), func.max(LearningSession.date))
        .where(LearningSession.user_id == user.id, LearningSession.roadmap_topic_id.is_not(None))
        .group_by(LearningSession.roadmap_topic_id))
    return {tid: (int(m), int(d), last) for tid, m, d, last in rows}


def _topic_out(t: RoadmapTopic, stats: dict) -> dict:
    minutes, days, last = stats.get(t.id, (0, 0, None))
    return {"id": t.id, "stage_id": t.stage_id, "title": t.title, "description": t.description, "position": t.position,
            "status": t.status, "notes": t.notes, "minutes_spent": minutes, "study_days": days, "last_studied_on": last,
            "completed_at": t.completed_at}


def _percent(done: int, total: int) -> int:
    return (100 * done) // total if total else 0


def get_roadmap(db: Session, user: User) -> dict:
    ensure_seeded(db, user)
    stages = list(db.scalars(select(RoadmapStage).where(RoadmapStage.user_id == user.id)
                             .order_by(RoadmapStage.position, RoadmapStage.id).options(selectinload(RoadmapStage.topics))))
    stats = _study_stats(db, user)
    out, all_total = [], {"total": 0, "completed": 0, "in_progress": 0, "not_started": 0, "minutes_spent": 0}
    next_topic = None
    for st in stages:
        topics = [_topic_out(t, stats) for t in sorted(st.topics, key=lambda t: (t.position, t.id))]
        c = sum(t["status"] == "completed" for t in topics)
        ip = sum(t["status"] == "in_progress" for t in topics)
        minutes = sum(t["minutes_spent"] for t in topics)
        out.append({"id": st.id, "title": st.title, "description": st.description, "position": st.position,
                    "total": len(topics), "completed": c, "in_progress": ip, "not_started": len(topics) - c - ip,
                    "percent": _percent(c, len(topics)), "minutes_spent": minutes, "topics": topics})
        for k, v in (("total", len(topics)), ("completed", c), ("in_progress", ip), ("not_started", len(topics) - c - ip),
                     ("minutes_spent", minutes)):
            all_total[k] += v
        if next_topic is None:
            next_topic = next((t for t in topics if t["status"] != "completed"), None)
    return {"stages": out, "overall": {**all_total, "percent": _percent(all_total["completed"], all_total["total"])},
            "next_topic": next_topic}


# ============================== topics ==============================


def _title_taken(db: Session, stage_id: int, title: str, except_id: int | None = None) -> bool:
    q = select(RoadmapTopic.id).where(RoadmapTopic.stage_id == stage_id, func.lower(RoadmapTopic.title) == title.lower())
    if except_id is not None:
        q = q.where(RoadmapTopic.id != except_id)
    return db.scalar(q) is not None


def create_topic(db: Session, user: User, data: s.TopicCreate) -> dict:
    ensure_seeded(db, user)
    stage = db.scalar(select(RoadmapStage).where(RoadmapStage.id == data.stage_id, RoadmapStage.user_id == user.id))
    if stage is None:
        raise NotFound("Stage not found")
    title = data.title.strip()
    if _title_taken(db, stage.id, title):
        raise Conflict("That stage already has a topic with that name")
    top = db.scalar(select(func.max(RoadmapTopic.position)).where(RoadmapTopic.stage_id == stage.id)) or 0
    t = RoadmapTopic(user_id=user.id, stage_id=stage.id, title=title, description=data.description, position=top + 1)
    db.add(t)
    db.commit()
    return _topic_out(t, {})


def update_topic(db: Session, user: User, topic_id: int, data: s.TopicUpdate) -> dict:
    t = _get_topic(db, user, topic_id)
    changes = data.model_dump(exclude_unset=True)
    if "title" in changes:
        if changes["title"] is None:
            raise RuleError("title can't be empty")
        changes["title"] = changes["title"].strip()
        if _title_taken(db, t.stage_id, changes["title"], except_id=t.id):
            raise Conflict("That stage already has a topic with that name")
    for field, value in changes.items():
        setattr(t, field, value)
    db.commit()
    return _topic_out(t, _study_stats(db, user))


def delete_topic(db: Session, user: User, topic_id: int) -> None:
    """Deletes the topic. Logged study sessions are kept (their topic link is cleared), so study history isn't lost."""
    db.delete(_get_topic(db, user, topic_id))
    db.commit()


def set_status(db: Session, user: User, topic_id: int, status: str, now: datetime | None = None) -> dict:
    """The ONLY way a topic becomes completed. Completing twice keeps the first completion time."""
    t = _get_topic(db, user, topic_id)
    now = now or datetime.now(timezone.utc)
    if status == "completed":
        if t.status != "completed":
            t.status, t.completed_at = "completed", now
    else:
        t.status, t.completed_at = status, None
    db.commit()
    return _topic_out(t, _study_stats(db, user))


# ============================== study sessions ==============================


def list_study(db: Session, user: User, topic_id: int, limit: int = 100) -> list[LearningSession]:
    _get_topic(db, user, topic_id)
    return list(db.scalars(select(LearningSession).where(
        LearningSession.user_id == user.id, LearningSession.roadmap_topic_id == topic_id)
        .order_by(LearningSession.date.desc(), LearningSession.id.desc()).limit(limit)))


def log_study(db: Session, user: User, topic_id: int, data: s.StudyCreate, now: datetime | None = None) -> LearningSession:
    t = _get_topic(db, user, topic_id)
    today = user_today(user, now)
    day = data.date or today
    if day > today:
        raise RuleError("You can't log study time in the future")
    session = LearningSession(user_id=user.id, roadmap_topic_id=t.id, date=day, minutes=data.minutes, notes=data.notes)
    db.add(session)
    if t.status == "not_started":
        t.status = "in_progress"  # studying has begun; completing is still the owner's explicit choice
    db.commit()
    return session
