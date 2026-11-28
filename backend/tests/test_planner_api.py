"""HTTP-level tests for /api/planner: auth, shapes, status codes, and a full day across features."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

SETUP = {"email": "me@example.com", "password": "correct-horse-9", "display_name": "Me", "timezone": "Asia/Kolkata"}
TODAY = datetime.now(ZoneInfo("Asia/Kolkata")).date()


def day(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


@pytest.fixture
def c(client):
    assert client.post("/api/auth/setup", json=SETUP).status_code == 201
    return client


def plan(c, d=None):
    r = c.get("/api/planner", params={"day": d} if d else None)
    assert r.status_code == 200, r.text
    return r.json()


def task(c, title, **kw):
    r = c.post("/api/tasks", json={"title": title, **kw})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.parametrize("method, path", [
    ("get", "/api/planner"), ("post", "/api/planner/complete"), ("post", "/api/planner/reopen"), ("post", "/api/planner/excuse"),
    ("post", "/api/planner/unexcuse"), ("post", "/api/planner/tasks/1/reschedule"),
])
def test_every_endpoint_requires_login(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_empty_plan_shape(c):
    p = plan(c)
    assert p["date"] == TODAY.isoformat() and p["is_today"] is True and p["items"] == []
    assert set(p["summary"]) == {"total", "completed", "pending", "overdue", "excused", "percent", "study_minutes", "dev_minutes", "by_kind",
                                "rest_day", "planned_minutes", "available_minutes", "unestimated", "overloaded", "focus_window"}


def test_other_days_and_bad_dates(c):
    assert plan(c, day(1))["is_today"] is False
    assert c.get("/api/planner", params={"day": "not-a-date"}).status_code == 422


def test_a_day_across_features_end_to_end(c):
    t = task(c, "Write report", scheduled_date=day(0))
    late = task(c, "File taxes", due_date=day(-2))
    h = c.post("/api/habits", json={"name": "Reading", "start_date": day(-10)}).json()
    course = c.post("/api/courses", json={"title": "Agentic AI"}).json()
    mod = c.post(f"/api/courses/{course['id']}/modules", json={"title": "Intro"}).json()
    c.post(f"/api/modules/{mod['modules'][0]['id']}/lessons", json={"title": "What is an agent?"})
    p = plan(c)
    kinds = {i["key"]: i for i in p["items"]}
    assert {f"task:{t['id']}", f"task:{late['id']}", f"habit:{h['id']}"} <= set(kinds)
    assert any(i["kind"] == "lesson" and i["title"] == "What is an agent?" for i in p["items"])
    assert kinds[f"task:{late['id']}"]["status"] == "overdue" and p["items"][0]["status"] == "overdue"
    assert p["summary"]["overdue"] == 1 and p["summary"]["completed"] == 0

    done = c.post("/api/planner/complete", json={"kind": "task", "ref_id": t["id"], "date": day(0)})
    assert done.status_code == 200 and {i["key"]: i for i in done.json()["items"]}[f"task:{t['id']}"]["status"] == "completed"
    assert c.get(f"/api/tasks/{t['id']}").json()["status"] == "completed"                       # the Tasks feature agrees
    c.post("/api/planner/complete", json={"kind": "habit", "ref_id": h["id"], "date": day(0)})
    assert c.get(f"/api/habits/{h['id']}").json()["done_today"] is True                         # ... and so does Habits
    lesson = next(i for i in plan(c)["items"] if i["kind"] == "lesson")
    c.post("/api/planner/complete", json={"kind": "lesson", "ref_id": lesson["ref_id"], "date": day(0)})
    assert c.get(f"/api/courses/{course['id']}").json()["progress"]["completed_lessons"] == 1  # ... and Courses
    s = plan(c)["summary"]
    assert (s["completed"], s["total"], s["percent"]) == (3, 4, 75)

    assert c.post("/api/planner/reopen", json={"kind": "task", "ref_id": t["id"], "date": day(0)}).status_code == 200
    assert c.get(f"/api/tasks/{t['id']}").json()["completed_at"] is None


@pytest.mark.parametrize("body", [
    {}, {"kind": "task"}, {"kind": "nonsense", "ref_id": 1, "date": "2026-01-01"}, {"kind": "task", "ref_id": 1, "date": "bad"},
    {"kind": "task", "ref_id": 1, "date": "2026-01-01", "status": "completed"},
])
def test_complete_validation(c, body):
    assert c.post("/api/planner/complete", json=body).status_code == 422


def test_complete_rules_over_http(c):
    t = task(c, "Old", due_date=day(-3))
    assert c.post("/api/planner/complete", json={"kind": "task", "ref_id": t["id"], "date": day(-3)}).status_code == 422
    assert c.post("/api/planner/complete", json={"kind": "task", "ref_id": t["id"], "date": day(1)}).status_code == 422
    assert c.post("/api/planner/complete", json={"kind": "task", "ref_id": 99999, "date": day(0)}).status_code == 404
    assert c.post("/api/planner/complete", json={"kind": "project", "ref_id": 1, "date": day(0)}).status_code == 422
    assert c.get(f"/api/tasks/{t['id']}").json()["status"] == "pending"


def test_reschedule_over_http_does_not_complete(c):
    t = task(c, "Write report", scheduled_date=day(0))
    r = c.post(f"/api/planner/tasks/{t['id']}/reschedule", json={"date": day(2), "from_date": day(0)})
    assert r.status_code == 200 and r.json()["items"] == [] and r.json()["summary"]["completed"] == 0
    got = c.get(f"/api/tasks/{t['id']}").json()
    assert (got["status"], got["completed_at"], got["scheduled_date"]) == ("pending", None, day(2))
    assert [i["title"] for i in plan(c, day(2))["items"]] == ["Write report"]
    assert c.post(f"/api/planner/tasks/{t['id']}/reschedule", json={"date": day(-1), "from_date": day(0)}).status_code == 422
    assert c.post("/api/planner/tasks/99999/reschedule", json={"date": day(1), "from_date": day(0)}).status_code == 404
    assert c.post(f"/api/planner/tasks/{t['id']}/reschedule", json={"date": day(1)}).status_code == 422       # from_date is required


def test_excuse_flow_over_http(c):
    t = task(c, "Dentist", due_date=day(-1))
    r = c.post("/api/planner/excuse", json={"kind": "task", "ref_id": t["id"], "date": day(0), "reason": "Was ill"})
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert (item["status"], item["excuse_reason"]) == ("excused", "Was ill") and r.json()["summary"]["overdue"] == 0 and r.json()["summary"]["total"] == 0
    assert c.post("/api/planner/excuse", json={"kind": "task", "ref_id": t["id"], "date": day(0), "reason": "x"}).status_code == 422
    assert c.post("/api/planner/excuse", json={"kind": "task", "ref_id": t["id"], "date": day(1), "reason": "tomorrow"}).status_code == 422
    back = c.post("/api/planner/unexcuse", json={"kind": "task", "ref_id": t["id"], "date": day(0)})
    assert back.status_code == 200 and back.json()["items"][0]["status"] == "overdue"
    assert c.post("/api/planner/unexcuse", json={"kind": "task", "ref_id": t["id"], "date": day(0)}).status_code == 404


def test_other_users_activities_are_not_reachable(c, db):
    from app.models import Task, User

    db.add(User(id=2, email="o@example.com", password_hash="x", display_name="O", timezone="UTC"))
    db.commit()
    db.add(Task(id=900, user_id=2, title="Secret", scheduled_date=TODAY))
    db.commit()
    assert plan(c)["items"] == []
    assert c.post("/api/planner/complete", json={"kind": "task", "ref_id": 900, "date": day(0)}).status_code == 404
    assert c.post("/api/planner/tasks/900/reschedule", json={"date": day(1), "from_date": day(0)}).status_code == 404
    assert c.post("/api/planner/excuse", json={"kind": "task", "ref_id": 900, "date": day(0), "reason": "not mine"}).status_code == 422
