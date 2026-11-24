"""Projects: computed progress, explicit completion, milestones, linked tasks, development sessions, isolation."""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Project, ProjectMilestone, ProjectSession, Task, User
from app.schemas import projects as s
from app.services import auth as auth_service
from app.services import projects as svc

NOW = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)   # 15:30 Mon 23 Nov in Kolkata
TODAY = date(2026, 11, 23)


@pytest.fixture
def user(db) -> User:
    return auth_service.create_first_user(db, email="me@example.com", password="correct-horse-9", display_name="Me", timezone="Asia/Kolkata")


@pytest.fixture
def other(db, user) -> User:
    u = User(id=2, email="o@example.com", password_hash="x", display_name="O", timezone="UTC")
    db.add(u)
    db.commit()
    return u


def mk(db, user, title="RAG chatbot", **kw) -> dict:
    return svc.create_project(db, user, s.ProjectCreate(title=title, **kw), now=NOW)


def task_done(db, task_id, status="completed"):
    t = db.get(Task, task_id)
    t.status, t.completed_at = status, (NOW if status == "completed" else None)
    db.commit()


# ============================== repo url + tech stack validation ==============================


@pytest.mark.parametrize("url, expected", [
    ("https://github.com/owner/repo", "https://github.com/owner/repo"),
    ("https://github.com/owner/repo.git", "https://github.com/owner/repo"),
    ("https://github.com/owner/repo/", "https://github.com/owner/repo"),
    ("  https://github.com/Some-Owner/my.repo_1  ", "https://github.com/Some-Owner/my.repo_1"),
])
def test_valid_repo_urls_are_normalised(url, expected):
    assert s.ProjectCreate(title="x", repo_url=url).repo_url == expected


@pytest.mark.parametrize("url", [
    "http://github.com/o/r", "https://gitlab.com/o/r", "https://github.com/o", "https://github.com/o/r/tree/main",
    "https://evil-github.com/o/r", "https://github.com.evil.test/o/r", "javascript:alert(1)", "github.com/o/r", "https://github.com//r",
])
def test_invalid_repo_urls_are_rejected(url):
    with pytest.raises(ValueError):
        s.ProjectCreate(title="x", repo_url=url)


def test_tech_stack_is_cleaned_and_limited():
    assert s.ProjectCreate(title="x", tech_stack=[" Python ", "python", "", "FastAPI"]).tech_stack == ["Python", "FastAPI"]
    with pytest.raises(ValueError):
        s.ProjectCreate(title="x", tech_stack=["a"] * 21)
    with pytest.raises(ValueError):
        s.ProjectCreate(title="x", tech_stack=["x" * 41])


def test_target_date_cannot_precede_start_date(db, user):
    with pytest.raises(ValueError):
        s.ProjectCreate(title="x", start_date=date(2026, 5, 2), target_date=date(2026, 5, 1))
    p = mk(db, user, start_date=date(2026, 5, 1))
    with pytest.raises(svc.RuleError):
        svc.update_project(db, user, p["id"], s.ProjectUpdate(target_date=date(2026, 4, 1)), now=NOW)


# ============================== create / update / delete ==============================


def test_new_project_defaults(db, user):
    p = mk(db, user, title="  RAG chatbot  ", tech_stack=["Python", "FastAPI"], repo_url="https://github.com/me/rag")
    assert (p["title"], p["origin"], p["status"], p["priority"], p["start_date"]) == ("RAG chatbot", "new", "active", 2, TODAY)
    assert p["tech_stack"] == ["Python", "FastAPI"] and p["repo_url"] == "https://github.com/me/rag"
    assert p["progress"] == {"milestones_done": 0, "milestones_total": 0, "tasks_done": 0, "tasks_total": 0, "percent": 0}
    assert (p["minutes_spent"], p["session_count"], p["days_active"], p["completed_at"], p["overdue"]) == (0, 0, 0, None, False)
    assert p["milestones"] == p["tasks"] == p["sessions"] == []


def test_existing_project_keeps_its_own_start_date_and_does_not_invent_one(db, user):
    p = mk(db, user, "Old API", origin="existing")
    assert p["origin"] == "existing" and p["start_date"] is None                       # unknown start is not made up
    q = mk(db, user, "Older API", origin="existing", start_date=date(2025, 3, 1))
    assert q["start_date"] == date(2025, 3, 1)


def test_titles_are_unique_per_user_case_insensitively(db, user, other):
    mk(db, user)
    with pytest.raises(svc.Conflict):
        mk(db, user, "rag CHATBOT")
    assert svc.create_project(db, other, s.ProjectCreate(title="RAG chatbot"), now=NOW)["title"] == "RAG chatbot"


def test_update_fields_and_clearing(db, user):
    p = mk(db, user, tech_stack=["Python"], description="d", repo_url="https://github.com/me/a")
    u = svc.update_project(db, user, p["id"], s.ProjectUpdate(title="RAG v2", priority=1, tech_stack=["Go"], notes="n",
                                                              objective="learn", repo_url=None, description=None), now=NOW)
    assert (u["title"], u["priority"], u["tech_stack"], u["notes"], u["objective"], u["repo_url"], u["description"]) == (
        "RAG v2", 1, ["Go"], "n", "learn", None, None)
    for field in ("title", "status", "priority", "origin"):
        with pytest.raises(svc.RuleError):
            svc.update_project(db, user, p["id"], s.ProjectUpdate(**{field: None}), now=NOW)
    mk(db, user, "Other")
    with pytest.raises(svc.Conflict):
        svc.update_project(db, user, p["id"], s.ProjectUpdate(title="other"), now=NOW)


def test_status_changes_set_and_clear_completed_at_only_when_explicit(db, user):
    p = mk(db, user)
    done = svc.update_project(db, user, p["id"], s.ProjectUpdate(status="completed"), now=NOW)
    assert done["status"] == "completed" and done["completed_at"] == NOW
    again = svc.update_project(db, user, p["id"], s.ProjectUpdate(status="completed"), now=NOW + timedelta(days=3))
    assert again["completed_at"] == NOW                                                # first completion time kept
    back = svc.update_project(db, user, p["id"], s.ProjectUpdate(status="paused"), now=NOW)
    assert back["status"] == "paused" and back["completed_at"] is None


def test_database_refuses_inconsistent_completion(db, user):
    p = mk(db, user)
    db.get(Project, p["id"]).status = "completed"                                       # without completed_at
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_finishing_every_milestone_does_not_complete_the_project(db, user):
    p = mk(db, user)
    d = svc.add_milestone(db, user, p["id"], s.MilestoneCreate(title="MVP"), now=NOW)
    out = svc.set_milestone_status(db, user, d["milestones"][0]["id"], s.MilestoneStatus(status="done"), now=NOW)
    assert out["progress"]["percent"] == 100 and out["status"] == "active" and out["completed_at"] is None


def test_list_orders_active_first_and_filters_by_status(db, user):
    a = mk(db, user, "A", priority=3)
    b = mk(db, user, "B", priority=1)
    c = mk(db, user, "C", priority=1, status="paused")
    d = mk(db, user, "D", status="completed")
    assert [p["title"] for p in svc.list_projects(db, user, now=NOW)] == ["B", "A", "C", "D"]
    assert [p["title"] for p in svc.list_projects(db, user, "paused", now=NOW)] == ["C"]
    assert d["completed_at"] == NOW and {a["id"], b["id"], c["id"]}


def test_overdue_flag_only_for_active_projects_past_their_target(db, user):
    mk(db, user, "Late", target_date=date(2026, 11, 22))
    mk(db, user, "OnTime", target_date=date(2026, 11, 23))
    mk(db, user, "LatePaused", target_date=date(2026, 11, 1), status="paused")
    flags = {p["title"]: p["overdue"] for p in svc.list_projects(db, user, now=NOW)}
    assert flags == {"Late": True, "OnTime": False, "LatePaused": False}


def test_delete_project_removes_milestones_and_sessions_but_keeps_tasks_detached(db, user):
    p = mk(db, user)
    svc.add_milestone(db, user, p["id"], s.MilestoneCreate(title="M1"), now=NOW)
    svc.add_task(db, user, p["id"], s.TaskCreate(title="Write loader"), now=NOW)
    svc.log_session(db, user, p["id"], s.SessionCreate(minutes=30, summary="set up repo"), now=NOW)
    svc.delete_project(db, user, p["id"])
    assert (db.query(Project).count(), db.query(ProjectMilestone).count(), db.query(ProjectSession).count()) == (0, 0, 0)
    t = db.query(Task).one()
    assert t.title == "Write loader" and t.project_id is None


# ============================== milestones ==============================


def test_milestones_are_ordered_unique_and_marked_done_explicitly(db, user):
    p = mk(db, user)
    svc.add_milestone(db, user, p["id"], s.MilestoneCreate(title="Ingest docs", due_date=date(2026, 11, 20)), now=NOW)
    d = svc.add_milestone(db, user, p["id"], s.MilestoneCreate(title="Build API"), now=NOW)
    assert [(m["title"], m["position"], m["status"]) for m in d["milestones"]] == [("Ingest docs", 1, "pending"), ("Build API", 2, "pending")]
    assert d["milestones"][0]["overdue"] is True and d["milestones"][1]["overdue"] is False
    with pytest.raises(svc.Conflict):
        svc.add_milestone(db, user, p["id"], s.MilestoneCreate(title="ingest DOCS"), now=NOW)
    mid = d["milestones"][0]["id"]
    done = svc.set_milestone_status(db, user, mid, s.MilestoneStatus(status="done", evidence="commit abc123"), now=NOW)
    m = done["milestones"][0]
    assert (m["status"], m["completed_at"], m["evidence"], m["overdue"]) == ("done", NOW, "commit abc123", False)
    assert done["last_activity_at"] == NOW
    again = svc.set_milestone_status(db, user, mid, s.MilestoneStatus(status="done"), now=NOW + timedelta(days=2))
    assert again["milestones"][0]["completed_at"] == NOW and again["milestones"][0]["evidence"] == "commit abc123"
    reopened = svc.set_milestone_status(db, user, mid, s.MilestoneStatus(status="pending"), now=NOW)
    assert reopened["milestones"][0]["status"] == "pending" and reopened["milestones"][0]["completed_at"] is None


def test_edit_and_delete_milestone(db, user):
    p = mk(db, user)
    d = svc.add_milestone(db, user, p["id"], s.MilestoneCreate(title="A"), now=NOW)
    svc.add_milestone(db, user, p["id"], s.MilestoneCreate(title="B"), now=NOW)
    mid = d["milestones"][0]["id"]
    e = svc.update_milestone(db, user, mid, s.MilestoneUpdate(title="A2", description="x", due_date=date(2026, 12, 1)), now=NOW)
    assert (e["milestones"][0]["title"], e["milestones"][0]["description"]) == ("A2", "x")
    with pytest.raises(svc.Conflict):
        svc.update_milestone(db, user, mid, s.MilestoneUpdate(title="b"), now=NOW)
    with pytest.raises(svc.RuleError):
        svc.update_milestone(db, user, mid, s.MilestoneUpdate(title=None), now=NOW)
    left = svc.delete_milestone(db, user, mid, now=NOW)
    assert [m["title"] for m in left["milestones"]] == ["B"]


def test_deleting_a_milestone_keeps_sessions_that_referenced_it(db, user):
    p = mk(db, user)
    d = svc.add_milestone(db, user, p["id"], s.MilestoneCreate(title="A"), now=NOW)
    mid = d["milestones"][0]["id"]
    svc.log_session(db, user, p["id"], s.SessionCreate(minutes=20, summary="work on A", milestone_id=mid), now=NOW)
    svc.delete_milestone(db, user, mid, now=NOW)
    assert db.query(ProjectSession).one().milestone_id is None


# ============================== tasks ==============================


def test_project_tasks_are_real_tasks_linked_to_the_project(db, user):
    p = mk(db, user)
    d = svc.add_task(db, user, p["id"], s.TaskCreate(title="Write loader", priority=1, due_date=date(2026, 11, 30), estimated_minutes=90), now=NOW)
    assert [(t["title"], t["status"], t["priority"], t["estimated_minutes"]) for t in d["tasks"]] == [("Write loader", "pending", 1, 90)]
    row = db.query(Task).one()
    assert (row.project_id, row.task_type, row.user_id) == (p["id"], "project_dev", user.id)


def test_tasks_ordered_open_first_and_cancelled_ones_dont_count_towards_progress(db, user):
    p = mk(db, user)
    for title in ("a", "b", "c", "d"):
        svc.add_task(db, user, p["id"], s.TaskCreate(title=title), now=NOW)
    ids = {t.title: t.id for t in db.query(Task).all()}
    task_done(db, ids["a"])
    task_done(db, ids["b"], status="cancelled")
    d = svc.get_project(db, user, p["id"], now=NOW)
    assert [t["title"] for t in d["tasks"]] == ["c", "d", "a", "b"]                    # open, completed, cancelled
    assert (d["progress"]["tasks_done"], d["progress"]["tasks_total"]) == (1, 3)         # cancelled isn't part of the total


# ============================== progress ==============================


def test_progress_combines_milestones_and_tasks_and_floors(db, user):
    p = mk(db, user)
    for title in ("M1", "M2"):
        svc.add_milestone(db, user, p["id"], s.MilestoneCreate(title=title), now=NOW)
    for title in ("t1", "t2", "t3"):
        svc.add_task(db, user, p["id"], s.TaskCreate(title=title), now=NOW)
    d = svc.get_project(db, user, p["id"], now=NOW)
    assert d["progress"] == {"milestones_done": 0, "milestones_total": 2, "tasks_done": 0, "tasks_total": 3, "percent": 0}
    svc.set_milestone_status(db, user, d["milestones"][0]["id"], s.MilestoneStatus(status="done"), now=NOW)
    task_done(db, db.query(Task).filter_by(title="t1").one().id)
    task_done(db, db.query(Task).filter_by(title="t2").one().id)
    d = svc.get_project(db, user, p["id"], now=NOW)
    assert d["progress"] == {"milestones_done": 1, "milestones_total": 2, "tasks_done": 2, "tasks_total": 3, "percent": 60}   # 3 of 5
    task_done(db, db.query(Task).filter_by(title="t3").one().id)
    assert svc.get_project(db, user, p["id"], now=NOW)["progress"]["percent"] == 80                                         # 4 of 5
    svc.set_milestone_status(db, user, d["milestones"][1]["id"], s.MilestoneStatus(status="done"), now=NOW)
    assert svc.get_project(db, user, p["id"], now=NOW)["progress"]["percent"] == 100


def test_progress_floors_and_reaches_100_only_when_everything_is_done(db, user):
    p = mk(db, user)
    for title in ("a", "b", "c"):
        svc.add_task(db, user, p["id"], s.TaskCreate(title=title), now=NOW)
    ids = [t.id for t in db.query(Task).order_by(Task.id)]
    task_done(db, ids[0])
    assert svc.get_project(db, user, p["id"], now=NOW)["progress"]["percent"] == 33
    task_done(db, ids[1])
    assert svc.get_project(db, user, p["id"], now=NOW)["progress"]["percent"] == 66
    task_done(db, ids[2])
    assert svc.get_project(db, user, p["id"], now=NOW)["progress"]["percent"] == 100


def test_progress_follows_a_task_being_reopened(db, user):
    p = mk(db, user)
    svc.add_task(db, user, p["id"], s.TaskCreate(title="a"), now=NOW)
    tid = db.query(Task).one().id
    task_done(db, tid)
    assert svc.get_project(db, user, p["id"], now=NOW)["progress"]["percent"] == 100
    task_done(db, tid, status="pending")
    assert svc.get_project(db, user, p["id"], now=NOW)["progress"]["percent"] == 0


def test_summaries_for_many_projects_dont_mix_numbers_up(db, user):
    a, b = mk(db, user, "A"), mk(db, user, "B")
    svc.add_task(db, user, a["id"], s.TaskCreate(title="x"), now=NOW)
    svc.add_milestone(db, user, b["id"], s.MilestoneCreate(title="m"), now=NOW)
    svc.log_session(db, user, b["id"], s.SessionCreate(minutes=45, summary="did things"), now=NOW)
    got = {p["title"]: p for p in svc.list_projects(db, user, now=NOW)}
    assert (got["A"]["progress"]["tasks_total"], got["A"]["progress"]["milestones_total"], got["A"]["minutes_spent"]) == (1, 0, 0)
    assert (got["B"]["progress"]["tasks_total"], got["B"]["progress"]["milestones_total"], got["B"]["minutes_spent"]) == (0, 1, 45)


# ============================== development sessions ==============================


def test_sessions_add_up_to_time_days_and_activity(db, user):
    p = mk(db, user)
    svc.log_session(db, user, p["id"], s.SessionCreate(minutes=45, summary="built the loader"), now=NOW)
    svc.log_session(db, user, p["id"], s.SessionCreate(minutes=30, summary="fixed a bug"), now=NOW)
    svc.log_session(db, user, p["id"], s.SessionCreate(minutes=60, summary="wrote tests", date=date(2026, 11, 20), notes="n"), now=NOW)
    d = svc.get_project(db, user, p["id"], now=NOW)
    assert (d["minutes_spent"], d["session_count"], d["days_active"]) == (135, 3, 2)
    assert d["last_activity_at"] == NOW
    assert [x.summary for x in d["sessions"]] == ["fixed a bug", "built the loader", "wrote tests"]       # newest day first, then newest entry


def test_session_rules(db, user):
    p = mk(db, user)
    with pytest.raises(svc.RuleError, match="future"):
        svc.log_session(db, user, p["id"], s.SessionCreate(minutes=10, summary="from tomorrow", date=date(2026, 11, 24)), now=NOW)
    for bad in ({"minutes": 0, "summary": "xxx"}, {"minutes": 1441, "summary": "xxx"}, {"minutes": 5, "summary": ""}, {"minutes": 5, "summary": "ab"}, {"minutes": 5}):
        with pytest.raises(ValueError):
            s.SessionCreate(**bad)


def test_session_must_reference_this_projects_own_milestone_and_task(db, user):
    p, q = mk(db, user, "P"), mk(db, user, "Q")
    dq = svc.add_milestone(db, user, q["id"], s.MilestoneCreate(title="Qm"), now=NOW)
    svc.add_task(db, user, q["id"], s.TaskCreate(title="Qt"), now=NOW)
    with pytest.raises(svc.RuleError, match="milestone"):
        svc.log_session(db, user, p["id"], s.SessionCreate(minutes=5, summary="abc", milestone_id=dq["milestones"][0]["id"]), now=NOW)
    with pytest.raises(svc.RuleError, match="task"):
        svc.log_session(db, user, p["id"], s.SessionCreate(minutes=5, summary="abc", task_id=db.query(Task).one().id), now=NOW)
    ok = svc.log_session(db, user, q["id"], s.SessionCreate(minutes=5, summary="abc", milestone_id=dq["milestones"][0]["id"]), now=NOW)
    assert ok.milestone_id == dq["milestones"][0]["id"]


def test_first_session_sets_started_at_and_back_dated_one_does_not_touch_last_activity(db, user):
    p = mk(db, user)
    assert db.get(Project, p["id"]).started_at is None
    svc.log_session(db, user, p["id"], s.SessionCreate(minutes=10, summary="old work", date=date(2026, 11, 1)), now=NOW)
    row = db.get(Project, p["id"])
    assert row.started_at == NOW and row.last_activity_at is None


def test_delete_session(db, user):
    p = mk(db, user)
    sess = svc.log_session(db, user, p["id"], s.SessionCreate(minutes=40, summary="a thing"), now=NOW)
    assert svc.delete_session(db, user, sess.id) == p["id"]
    assert svc.get_project(db, user, p["id"], now=NOW)["minutes_spent"] == 0
    with pytest.raises(svc.NotFound):
        svc.delete_session(db, user, sess.id)


# ============================== isolation ==============================


def test_other_users_projects_are_not_found(db, user, other):
    p = mk(db, user)
    d = svc.add_milestone(db, user, p["id"], s.MilestoneCreate(title="M"), now=NOW)
    mid = d["milestones"][0]["id"]
    sess = svc.log_session(db, user, p["id"], s.SessionCreate(minutes=5, summary="abc"), now=NOW)
    calls = [lambda: svc.get_project(db, other, p["id"]), lambda: svc.update_project(db, other, p["id"], s.ProjectUpdate(notes="x")),
             lambda: svc.delete_project(db, other, p["id"]), lambda: svc.add_milestone(db, other, p["id"], s.MilestoneCreate(title="X")),
             lambda: svc.add_task(db, other, p["id"], s.TaskCreate(title="X")),
             lambda: svc.log_session(db, other, p["id"], s.SessionCreate(minutes=5, summary="abc")),
             lambda: svc.update_milestone(db, other, mid, s.MilestoneUpdate(title="X")),
             lambda: svc.set_milestone_status(db, other, mid, s.MilestoneStatus(status="done")),
             lambda: svc.delete_milestone(db, other, mid), lambda: svc.delete_session(db, other, sess.id)]
    for call in calls:
        with pytest.raises(svc.NotFound):
            call()
    assert svc.list_projects(db, other) == []
