"""HTTP-level tests for /api/projects: auth, shapes, status codes, validation, and the link with the Tasks API."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

SETUP = {"email": "me@example.com", "password": "correct-horse-9", "display_name": "Me", "timezone": "Asia/Kolkata"}
TODAY = datetime.now(ZoneInfo("Asia/Kolkata")).date()


@pytest.fixture
def c(client):
    assert client.post("/api/auth/setup", json=SETUP).status_code == 201
    return client


def new(c, **kw) -> dict:
    r = c.post("/api/projects", json={"title": "RAG chatbot", **kw})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.parametrize("method, path", [
    ("get", "/api/projects"), ("post", "/api/projects"), ("get", "/api/projects/1"), ("patch", "/api/projects/1"),
    ("delete", "/api/projects/1"), ("post", "/api/projects/1/milestones"), ("post", "/api/projects/1/tasks"),
    ("post", "/api/projects/1/sessions"), ("patch", "/api/project-milestones/1"), ("post", "/api/project-milestones/1/status"),
    ("delete", "/api/project-milestones/1"), ("delete", "/api/project-sessions/1"),
])
def test_every_endpoint_requires_login(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_create_get_list_shape(c):
    p = new(c, tech_stack=["Python", "FastAPI"], repo_url="https://github.com/me/rag.git", objective="learn RAG", origin="existing")
    assert set(p) >= {"id", "title", "origin", "status", "priority", "description", "objective", "tech_stack", "repo_url", "start_date",
                      "target_date", "completed_at", "last_activity_at", "created_at", "progress", "minutes_spent", "session_count",
                      "days_active", "overdue", "notes", "milestones", "tasks", "sessions"}
    assert (p["origin"], p["tech_stack"], p["repo_url"], p["start_date"]) == ("existing", ["Python", "FastAPI"], "https://github.com/me/rag", None)
    listing = c.get("/api/projects").json()
    assert [x["id"] for x in listing] == [p["id"]] and "milestones" not in listing[0]
    assert c.get(f"/api/projects/{p['id']}").json()["title"] == "RAG chatbot"
    assert new(c, title="Second")["start_date"] == TODAY.isoformat()


@pytest.mark.parametrize("body", [
    {}, {"title": ""}, {"title": "x" * 201}, {"title": "A", "origin": "imported"}, {"title": "A", "status": "done"}, {"title": "A", "priority": 0},
    {"title": "A", "priority": 5}, {"title": "A", "repo_url": "https://gitlab.com/o/r"}, {"title": "A", "repo_url": "javascript:alert(1)"},
    {"title": "A", "start_date": "2026-05-02", "target_date": "2026-05-01"}, {"title": "A", "tech_stack": ["x"] * 21},
    {"title": "A", "progress": {"percent": 100}}, {"title": "A", "completed_at": "2026-01-01T00:00:00Z"},
])
def test_validation(c, body):
    assert c.post("/api/projects", json=body).status_code == 422


def test_duplicate_title_is_409(c):
    new(c)
    assert c.post("/api/projects", json={"title": "rag chatbot"}).status_code == 409


def test_update_status_and_delete(c):
    p = new(c)
    r = c.patch(f"/api/projects/{p['id']}", json={"status": "completed", "priority": 1})
    assert r.status_code == 200 and r.json()["completed_at"] is not None and r.json()["priority"] == 1
    assert c.patch(f"/api/projects/{p['id']}", json={"status": "paused"}).json()["completed_at"] is None
    assert c.patch(f"/api/projects/{p['id']}", json={"title": None}).status_code == 422
    assert c.patch(f"/api/projects/{p['id']}", json={"progress": 50}).status_code == 422          # progress can't be set by hand
    assert c.patch("/api/projects/9999", json={"notes": "x"}).status_code == 404
    assert c.get("/api/projects", params={"status": "paused"}).json()[0]["id"] == p["id"]
    assert c.get("/api/projects", params={"status": "active"}).json() == []
    assert c.get("/api/projects", params={"status": "bogus"}).status_code == 422
    assert c.delete(f"/api/projects/{p['id']}").status_code == 204
    assert c.delete(f"/api/projects/{p['id']}").status_code == 404


def test_milestone_flow(c):
    p = new(c)
    r = c.post(f"/api/projects/{p['id']}/milestones", json={"title": "MVP", "due_date": (TODAY - timedelta(days=1)).isoformat()})
    assert r.status_code == 201
    m = r.json()["milestones"][0]
    assert (m["status"], m["overdue"]) == ("pending", True)
    assert c.post(f"/api/projects/{p['id']}/milestones", json={"title": "mvp"}).status_code == 409
    done = c.post(f"/api/project-milestones/{m['id']}/status", json={"status": "done", "evidence": "commit abc"}).json()
    assert done["milestones"][0]["completed_at"] is not None and done["progress"]["percent"] == 100 and done["status"] == "active"
    assert c.post(f"/api/project-milestones/{m['id']}/status", json={"status": "finished"}).status_code == 422
    assert c.patch(f"/api/project-milestones/{m['id']}", json={"status": "done"}).status_code == 422       # only via the status endpoint
    assert c.patch(f"/api/project-milestones/{m['id']}", json={"title": "MVP v2"}).json()["milestones"][0]["title"] == "MVP v2"
    assert c.delete(f"/api/project-milestones/{m['id']}").json()["milestones"] == []
    assert c.delete(f"/api/project-milestones/{m['id']}").status_code == 404


def test_project_tasks_appear_in_the_task_list_and_completing_them_there_moves_progress(c):
    p = new(c)
    d = c.post(f"/api/projects/{p['id']}/tasks", json={"title": "Write loader", "priority": 1, "estimated_minutes": 60}).json()
    assert d["tasks"][0]["status"] == "pending" and d["progress"] == {
        "milestones_done": 0, "milestones_total": 0, "tasks_done": 0, "tasks_total": 1, "percent": 0}
    tid = d["tasks"][0]["id"]
    assert "Write loader" in [t["title"] for t in c.get("/api/tasks", params={"view": "all"}).json()["items"]]   # shows up in Tasks too
    assert c.patch(f"/api/tasks/{tid}", json={"status": "completed"}).status_code == 200                          # completed with the normal task API
    after = c.get(f"/api/projects/{p['id']}").json()
    assert after["progress"]["percent"] == 100 and after["tasks"][0]["completed_at"] is not None
    assert c.patch(f"/api/tasks/{tid}", json={"status": "pending"}).status_code == 200
    assert c.get(f"/api/projects/{p['id']}").json()["progress"]["percent"] == 0


@pytest.mark.parametrize("body", [{"title": ""}, {}, {"title": "x", "priority": 9}, {"title": "x", "estimated_minutes": 0}])
def test_task_validation(c, body):
    assert c.post(f"/api/projects/{new(c)['id']}/tasks", json=body).status_code == 422


def test_session_flow(c):
    p = new(c)
    m = c.post(f"/api/projects/{p['id']}/milestones", json={"title": "MVP"}).json()["milestones"][0]
    r = c.post(f"/api/projects/{p['id']}/sessions", json={"minutes": 90, "summary": "built the retriever", "milestone_id": m["id"], "notes": "n"})
    assert r.status_code == 201 and set(r.json()) == {"id", "project_id", "date", "minutes", "summary", "milestone_id", "task_id", "notes", "created_at"}
    assert r.json()["date"] == TODAY.isoformat()
    d = c.get(f"/api/projects/{p['id']}").json()
    assert (d["minutes_spent"], d["session_count"], d["days_active"]) == (90, 1, 1)
    assert d["sessions"][0]["summary"] == "built the retriever" and d["last_activity_at"] is not None
    assert c.delete(f"/api/project-sessions/{r.json()['id']}").status_code == 204
    assert c.get(f"/api/projects/{p['id']}").json()["minutes_spent"] == 0
    assert c.delete(f"/api/project-sessions/{r.json()['id']}").status_code == 404


@pytest.mark.parametrize("body", [
    {"minutes": 0, "summary": "abcd"}, {"minutes": 5, "summary": ""}, {"minutes": 5}, {"summary": "abcd"},
    {"minutes": 5, "summary": "abcd", "date": "2999-01-01"}, {"minutes": 5, "summary": "abcd", "milestone_id": 99999},
    {"minutes": 5, "summary": "abcd", "task_id": 99999},
])
def test_session_validation(c, body):
    assert c.post(f"/api/projects/{new(c)['id']}/sessions", json=body).status_code == 422


def test_other_users_projects_look_like_not_found(c, db):
    from app.models import Project, ProjectMilestone, ProjectSession, User

    db.add(User(id=2, email="o@example.com", password_hash="x", display_name="O", timezone="UTC"))
    db.commit()
    db.add(Project(id=500, user_id=2, title="Theirs"))
    db.commit()
    db.add(ProjectMilestone(id=600, project_id=500, title="Secret"))
    db.add(ProjectSession(id=700, user_id=2, project_id=500, date=TODAY, minutes=5, summary="abc"))
    db.commit()
    assert c.get("/api/projects/500").status_code == 404
    assert c.patch("/api/projects/500", json={"notes": "x"}).status_code == 404
    assert c.delete("/api/projects/500").status_code == 404
    assert c.post("/api/projects/500/milestones", json={"title": "x"}).status_code == 404
    assert c.post("/api/projects/500/tasks", json={"title": "x"}).status_code == 404
    assert c.post("/api/projects/500/sessions", json={"minutes": 5, "summary": "abcd"}).status_code == 404
    assert c.post("/api/project-milestones/600/status", json={"status": "done"}).status_code == 404
    assert c.patch("/api/project-milestones/600", json={"title": "x"}).status_code == 404
    assert c.delete("/api/project-milestones/600").status_code == 404
    assert c.delete("/api/project-sessions/700").status_code == 404
    assert c.get("/api/projects").json() == []
