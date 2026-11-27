"""HTTP tests for Phase 10: /api/goals and /api/timer."""
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


def project(c, title="RAG bot", **kw):
    r = c.post("/api/projects", json={"title": title, "origin": "new", **kw})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.parametrize("method, path", [
    ("get", "/api/goals"), ("get", "/api/timer"), ("post", "/api/timer/start"), ("post", "/api/timer/stop"), ("delete", "/api/timer"),
])
def test_every_endpoint_requires_login(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_goals_lists_projects_and_courses_with_a_target_date(c):
    project(c, "No date")
    project(c, "RAG bot", target_date=day(30))
    r = c.post("/api/courses", json={"title": "RAG course", "target_date": day(20)})
    assert r.status_code == 201, r.text
    goals = c.get("/api/goals").json()
    assert {(g["kind"], g["title"]) for g in goals} == {("project", "RAG bot"), ("course", "RAG course")}
    course = next(g for g in goals if g["kind"] == "course")
    assert course["status"] == "unknown" and course["warning"] is False and course["days_left"] == 21


def test_an_unfinished_project_past_its_date_is_overdue(c):
    p = project(c, "Late", start_date=day(-30), target_date=day(-1))
    c.post(f"/api/projects/{p['id']}/tasks", json={"title": "Ship it"})
    g = c.get("/api/goals").json()[0]
    assert g["status"] == "overdue" and g["warning"] is True and g["remaining"] == 1


def test_timer_lifecycle_logs_to_the_project(c):
    p = project(c)
    assert c.get("/api/timer").json() is None
    r = c.post("/api/timer/start", json={"kind": "project", "ref_id": p["id"]})
    assert r.status_code == 201, r.text
    assert r.json()["label"] == "RAG bot" and r.json()["logs_to"] == "Project: RAG bot"
    assert c.get("/api/timer").json()["project_id"] == p["id"]
    assert c.post("/api/timer/start", json={"kind": "project", "ref_id": p["id"]}).status_code == 409
    r = c.post("/api/timer/stop", json={"minutes": 45, "summary": "Wrote the chunker"})
    assert r.status_code == 200, r.text
    assert r.json()["minutes"] == 45 and r.json()["logged_to"] == "project"
    assert c.get("/api/timer").json() is None
    sessions = c.get(f"/api/projects/{p['id']}").json()
    assert sessions["minutes_spent"] == 45


def test_discard_and_missing_timer(c):
    p = project(c)
    assert c.delete("/api/timer").status_code == 404
    assert c.post("/api/timer/stop", json={}).status_code == 404
    c.post("/api/timer/start", json={"kind": "project", "ref_id": p["id"]})
    assert c.delete("/api/timer").status_code == 204
    assert c.get("/api/timer").json() is None


def test_start_validation(c):
    assert c.post("/api/timer/start", json={"kind": "habit", "ref_id": 1}).status_code == 422
    assert c.post("/api/timer/start", json={"kind": "project", "ref_id": 0}).status_code == 422
    assert c.post("/api/timer/start", json={"kind": "project", "ref_id": 1, "extra": 1}).status_code == 422
    assert c.post("/api/timer/start", json={"kind": "project", "ref_id": 999}).status_code == 404
    assert c.post("/api/timer/stop", json={"minutes": 0}).status_code == 422
    assert c.post("/api/timer/stop", json={"minutes": 2000}).status_code == 422


def test_a_task_timer_adds_to_the_tasks_actual_minutes(c):
    t = c.post("/api/tasks", json={"title": "Read the paper"})
    assert t.status_code == 201, t.text
    tid = t.json()["id"]
    c.post("/api/timer/start", json={"kind": "task", "ref_id": tid})
    out = c.post("/api/timer/stop", json={"minutes": 30}).json()
    assert out["logged_to"] == "task"
    assert c.get(f"/api/tasks/{tid}").json()["actual_minutes"] == 30
