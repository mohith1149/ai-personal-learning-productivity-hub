"""AI roadmap: exact seed, never auto-completed, explicit completion, derived progress and study time, isolation."""
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import LearningSession, RoadmapStage, RoadmapTopic, User
from app.schemas import roadmap as s
from app.services import auth as auth_service
from app.services import roadmap as svc

NOW = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)  # 15:30 on 23 Nov in Kolkata
SETUP = {"email": "me@example.com", "password": "correct-horse-9", "display_name": "Me", "timezone": "Asia/Kolkata"}

# The owner's lists, typed out independently of the code under test.
EXPECTED = {
    "Stage 1 – Programming and Foundations": ["Python", "Java fundamentals", "Data structures and algorithms", "Object-oriented programming", "SQL and databases", "Git and GitHub", "Linux and command line", "APIs and HTTP fundamentals"],
    "Stage 2 – Machine Learning and Deep Learning": ["Machine learning fundamentals", "Supervised and unsupervised learning", "Model evaluation", "Feature engineering", "Scikit-learn", "Neural networks", "PyTorch", "TensorFlow", "Transformers fundamentals"],
    "Stage 3 – Generative AI and LLM Engineering": ["LLM fundamentals", "Tokens and embeddings", "Prompt engineering", "Context windows", "Structured outputs", "Function and tool calling", "RAG", "Vector databases", "Semantic search", "LangChain", "LLM evaluation"],
    "Stage 4 – Agentic AI and Automation": ["AI agents", "Agent architectures", "Tool calling", "Planning and reasoning", "LangGraph", "Multi-agent systems", "MCP", "n8n", "Workflow automation", "Human-in-the-loop approval", "Agent evaluation and observability"],
    "Stage 5 – AI Engineering and Deployment": ["FastAPI", "Backend architecture", "Docker", "PostgreSQL", "AWS", "CI/CD", "Cloud deployment", "Authentication and security", "Monitoring", "Logging", "Testing", "Production AI systems"],
}


@pytest.fixture
def user(db) -> User:
    return auth_service.create_first_user(db, **SETUP)


@pytest.fixture
def other(db, user) -> User:
    u = User(id=2, email="o@example.com", password_hash="x", display_name="O", timezone="UTC")
    db.add(u)
    db.commit()
    return u


def topic(db, user, title):
    return db.scalar(select(RoadmapTopic).where(RoadmapTopic.user_id == user.id, RoadmapTopic.title == title))


def row(db, user, title):
    return next(x for st in svc.get_roadmap(db, user)["stages"] for x in st["topics"] if x["title"] == title)


# ---------------- seed ----------------


def test_first_open_creates_the_owners_exact_five_stages_all_not_started(db, user):
    r = svc.get_roadmap(db, user)
    assert {st["title"]: [t["title"] for t in st["topics"]] for st in r["stages"]} == EXPECTED
    assert [st["position"] for st in r["stages"]] == [1, 2, 3, 4, 5]
    assert all(t["status"] == "not_started" and t["completed_at"] is None and t["minutes_spent"] == 0
               for st in r["stages"] for t in st["topics"])
    assert r["overall"] == {"total": 51, "completed": 0, "in_progress": 0, "not_started": 51, "percent": 0, "minutes_spent": 0}
    assert all(st["percent"] == 0 and st["completed"] == 0 for st in r["stages"])


def test_seeding_happens_once(db, user):
    svc.get_roadmap(db, user)
    svc.get_roadmap(db, user)
    assert db.query(RoadmapStage).count() == 5 and db.query(RoadmapTopic).count() == 51


def test_each_user_gets_their_own_roadmap(db, user, other):
    svc.get_roadmap(db, user)
    assert svc.get_roadmap(db, other)["overall"]["total"] == 51
    assert db.query(RoadmapStage).count() == 10


def test_database_refuses_duplicate_titles_and_unexplained_completion(db, user):
    svc.get_roadmap(db, user)
    st = db.scalar(select(RoadmapStage).where(RoadmapStage.user_id == user.id))
    db.add(RoadmapTopic(user_id=user.id, stage_id=st.id, title="Python", position=99))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    topic(db, user, "Docker").status = "completed"  # completed without completed_at
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_next_topic_is_the_first_one_not_completed(db, user):
    assert svc.get_roadmap(db, user)["next_topic"]["title"] == "Python"
    svc.set_status(db, user, topic(db, user, "Python").id, "completed", now=NOW)
    assert svc.get_roadmap(db, user)["next_topic"]["title"] == "Java fundamentals"
    svc.set_status(db, user, topic(db, user, "Java fundamentals").id, "in_progress")
    assert svc.get_roadmap(db, user)["next_topic"]["title"] == "Java fundamentals"   # in progress is not finished


# ---------------- status ----------------


def test_completion_is_only_by_explicit_action(db, user):
    svc.get_roadmap(db, user)
    t = topic(db, user, "Python")
    svc.log_study(db, user, t.id, s.StudyCreate(minutes=600), now=NOW)          # lots of study ...
    assert topic(db, user, "Python").status == "in_progress"                      # ... never completes it
    assert topic(db, user, "Python").completed_at is None


def test_set_status_transitions_and_idempotent_completion(db, user):
    svc.get_roadmap(db, user)
    t = topic(db, user, "RAG")
    assert svc.set_status(db, user, t.id, "in_progress")["completed_at"] is None
    done = svc.set_status(db, user, t.id, "completed", now=NOW)
    assert done["status"] == "completed" and done["completed_at"] == NOW
    again = svc.set_status(db, user, t.id, "completed", now=datetime(2026, 12, 1, tzinfo=timezone.utc))
    assert again["completed_at"] == NOW                                           # first completion time kept
    back = svc.set_status(db, user, t.id, "not_started")
    assert back["status"] == "not_started" and back["completed_at"] is None


def test_progress_is_computed_per_stage_and_overall(db, user):
    svc.get_roadmap(db, user)
    for title in ("Python", "Java fundamentals", "Git and GitHub", "FastAPI"):
        svc.set_status(db, user, topic(db, user, title).id, "completed", now=NOW)
    svc.set_status(db, user, topic(db, user, "SQL and databases").id, "in_progress")
    r = svc.get_roadmap(db, user)
    s1, s5 = r["stages"][0], r["stages"][4]
    assert (s1["total"], s1["completed"], s1["in_progress"], s1["not_started"], s1["percent"]) == (8, 3, 1, 4, 37)   # 37.5 floored
    assert (s5["completed"], s5["percent"]) == (1, 8)                                                              # 1/12 = 8.3
    assert r["overall"] == {"total": 51, "completed": 4, "in_progress": 1, "not_started": 46, "percent": 7, "minutes_spent": 0}


def test_stage_reaches_100_only_when_every_topic_is_completed(db, user):
    svc.get_roadmap(db, user)
    ids = [t.id for t in db.scalars(select(RoadmapTopic).join(RoadmapStage).where(
        RoadmapStage.position == 1, RoadmapStage.user_id == user.id))]
    for i in ids[:-1]:
        svc.set_status(db, user, i, "completed", now=NOW)
    assert svc.get_roadmap(db, user)["stages"][0]["percent"] == 87
    svc.set_status(db, user, ids[-1], "completed", now=NOW)
    assert svc.get_roadmap(db, user)["stages"][0]["percent"] == 100


# ---------------- topics ----------------


def test_add_edit_and_delete_topics(db, user):
    r = svc.get_roadmap(db, user)
    stage = r["stages"][2]["id"]
    new = svc.create_topic(db, user, s.TopicCreate(stage_id=stage, title="  Fine-tuning  ", description="LoRA etc."))
    assert new["title"] == "Fine-tuning" and new["status"] == "not_started" and new["position"] == 12
    assert svc.get_roadmap(db, user)["stages"][2]["total"] == 12 and svc.get_roadmap(db, user)["overall"]["total"] == 52
    with pytest.raises(svc.Conflict):
        svc.create_topic(db, user, s.TopicCreate(stage_id=stage, title="fine-tuning"))        # case-insensitive
    svc.create_topic(db, user, s.TopicCreate(stage_id=r["stages"][0]["id"], title="Fine-tuning"))  # another stage is fine
    edited = svc.update_topic(db, user, new["id"], s.TopicUpdate(notes="read the LoRA paper", title="Fine-tuning LLMs"))
    assert edited["notes"] == "read the LoRA paper" and edited["title"] == "Fine-tuning LLMs"
    with pytest.raises(svc.Conflict):
        svc.update_topic(db, user, new["id"], s.TopicUpdate(title="RAG"))
    with pytest.raises(svc.RuleError):
        svc.update_topic(db, user, new["id"], s.TopicUpdate(title=None))
    svc.delete_topic(db, user, new["id"])
    assert svc.get_roadmap(db, user)["stages"][2]["total"] == 11


def test_deleting_a_topic_keeps_its_study_history(db, user):
    svc.get_roadmap(db, user)
    t = topic(db, user, "Docker")
    svc.log_study(db, user, t.id, s.StudyCreate(minutes=30), now=NOW)
    svc.delete_topic(db, user, t.id)
    assert db.query(LearningSession).count() == 1 and db.query(LearningSession).one().roadmap_topic_id is None


def test_cannot_add_to_a_stage_that_is_not_yours(db, user, other):
    stage = svc.get_roadmap(db, user)["stages"][0]["id"]
    with pytest.raises(svc.NotFound):
        svc.create_topic(db, other, s.TopicCreate(stage_id=stage, title="Sneaky"))


# ---------------- study time and dates ----------------


def test_study_time_and_days_come_from_logged_sessions(db, user):
    svc.get_roadmap(db, user)
    t = topic(db, user, "PyTorch")
    svc.log_study(db, user, t.id, s.StudyCreate(minutes=45), now=NOW)
    svc.log_study(db, user, t.id, s.StudyCreate(minutes=30, date=date(2026, 11, 20), notes="tensors"), now=NOW)
    svc.log_study(db, user, t.id, s.StudyCreate(minutes=15), now=NOW)                       # same day as the first
    r = row(db, user, "PyTorch")
    assert (r["minutes_spent"], r["study_days"], r["last_studied_on"], r["status"]) == (90, 2, date(2026, 11, 23), "in_progress")
    assert svc.get_roadmap(db, user)["overall"]["minutes_spent"] == 90
    assert svc.get_roadmap(db, user)["stages"][1]["minutes_spent"] == 90
    listed = svc.list_study(db, user, t.id)
    assert [(x.date, x.minutes) for x in listed] == [(date(2026, 11, 23), 15), (date(2026, 11, 23), 45), (date(2026, 11, 20), 30)]


def test_deleting_a_session_corrects_the_numbers(db, user):
    from app.services import courses

    svc.get_roadmap(db, user)
    t = topic(db, user, "Docker")
    a = svc.log_study(db, user, t.id, s.StudyCreate(minutes=60), now=NOW)
    svc.log_study(db, user, t.id, s.StudyCreate(minutes=20, date=date(2026, 11, 1)), now=NOW)
    courses.delete_session(db, user, a.id)                         # the existing study-session delete works for topics too
    r = row(db, user, "Docker")
    assert (r["minutes_spent"], r["last_studied_on"]) == (20, date(2026, 11, 1))


@pytest.mark.parametrize("bad", [0, -5, 1441])
def test_study_minutes_are_bounded(bad):
    with pytest.raises(ValueError):
        s.StudyCreate(minutes=bad)


def test_cannot_log_study_in_the_future(db, user):
    svc.get_roadmap(db, user)
    with pytest.raises(svc.RuleError):
        svc.log_study(db, user, topic(db, user, "Docker").id, s.StudyCreate(minutes=10, date=date(2026, 11, 24)), now=NOW)


def test_logging_study_does_not_move_a_completed_topic_back(db, user):
    svc.get_roadmap(db, user)
    t = topic(db, user, "Docker")
    svc.set_status(db, user, t.id, "completed", now=NOW)
    svc.log_study(db, user, t.id, s.StudyCreate(minutes=10), now=NOW)
    assert topic(db, user, "Docker").status == "completed"


# ---------------- isolation ----------------


def test_other_users_topics_are_not_found(db, user, other):
    svc.get_roadmap(db, user)
    tid = topic(db, user, "Python").id
    for call in (lambda: svc.update_topic(db, other, tid, s.TopicUpdate(notes="x")), lambda: svc.delete_topic(db, other, tid),
                 lambda: svc.set_status(db, other, tid, "completed"), lambda: svc.list_study(db, other, tid),
                 lambda: svc.log_study(db, other, tid, s.StudyCreate(minutes=5))):
        with pytest.raises(svc.NotFound):
            call()
