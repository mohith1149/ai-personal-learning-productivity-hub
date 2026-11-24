"""Cross-feature checks: one whole day through every feature, plus sweeps over the entire route table.

Each feature has its own tests. These make sure the features agree with each other (planner = dashboard = feature pages),
that nothing is reachable without login, and that one user can never see another user's data.
"""
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.ai.providers import ScriptedProvider
from app.ai.types import LLMResponse, ToolCall
from app.main import app
from app.routers import assistant as assistant_router

SETUP = {"email": "me@example.com", "password": "correct-horse-9", "display_name": "Me", "timezone": "Asia/Kolkata"}
TODAY = datetime.now(ZoneInfo("Asia/Kolkata")).date()
EVIDENCE = {"summary": "Implemented the retrieval step: chunking, embeddings and a top-k search over the vector store.",
            "repo_url": "https://github.com/me/rag-bot", "commit_sha": "a1b2c3d4e5f6", "commit_message": "Add retrieval step to RAG pipeline", "minutes": 90}
PUBLIC = {("GET", "/api/health"), ("GET", "/api/auth/status"), ("POST", "/api/auth/setup"), ("POST", "/api/auth/login"), ("POST", "/api/auth/logout")}


def day(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


@pytest.fixture
def c(client):
    assert client.post("/api/auth/setup", json=SETUP).status_code == 201
    return client


def api_routes():
    """Every method+path in the app, read from the OpenAPI schema (this FastAPI version nests included routers)."""
    for path, ops in sorted(app.openapi()["paths"].items()):
        for m in sorted(ops):
            if m.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"} and path.startswith("/api"):
                yield m.upper(), path


def concrete(path: str) -> str:
    import re
    return re.sub(r"\{(\w+)\}", lambda m: "2026-01-01" if m.group(1) == "day" else "1", path)


def test_every_route_except_the_public_ones_requires_login(client):
    routes = list(api_routes())
    assert len(routes) > 100                                       # the sweep really covers the app
    open_routes = []
    for method, path in routes:
        status = client.request(method, concrete(path)).status_code
        if (method, path) in PUBLIC:
            continue
        if status != 401:
            open_routes.append((method, path, status))
    assert open_routes == []


def test_no_response_ever_leaks_secrets(c):
    for _, path in [r for r in api_routes() if r[0] == "GET" and "{" not in r[1]]:
        body = c.get(path).text
        for needle in ("password_hash", "$2b$", "correct-horse-9", os.environ["SECRET_KEY"]):    # field names and values, not mentions of env var names
            assert needle not in body, (path, needle)


def test_a_whole_day_through_every_feature_and_all_views_agree(c, monkeypatch):
    # --- set up one of everything
    t_done = c.post("/api/tasks", json={"title": "Write report", "scheduled_date": day(0)}).json()
    t_late = c.post("/api/tasks", json={"title": "File taxes", "due_date": day(-2)}).json()
    habit = c.post("/api/habits", json={"name": "Reading", "start_date": day(-3)}).json()
    course = c.post("/api/courses", json={"title": "Agentic AI"}).json()
    mod = c.post(f"/api/courses/{course['id']}/modules", json={"title": "Intro"}).json()
    c.post(f"/api/modules/{mod['modules'][0]['id']}/lessons", json={"title": "What is an agent?"})
    pl = c.post("/api/video-playlists", json={"name": "BYTEBYTEGO", "daily_target": 2}).json()
    for i in range(3):
        assert c.post(f"/api/video-playlists/{pl['id']}/videos", json={"title": f"Video {i}", "url": f"https://youtu.be/abcdefghij{i}"}).status_code == 201
    proj = c.post("/api/projects", json={"title": "RAG chatbot"}).json()

    def plan():
        return c.get("/api/planner").json()

    def dash():
        return c.get("/api/dashboard").json()

    def agree():
        """The planner, the dashboard and the pages they are built from must tell the same story."""
        d, p = dash(), plan()          # the dashboard is the landing page; it seeds the roadmap, which the planner then includes
        assert d["plan"]["summary"] == p["summary"]
        assert d["plan"]["open_count"] == p["summary"]["pending"] + p["summary"]["overdue"]
        assert p["summary"]["total"] == p["summary"]["completed"] + p["summary"]["pending"] + p["summary"]["overdue"]
        return p, d

    p0, d0 = agree()
    assert p0["summary"]["completed"] == 0 and d0["tasks"]["overdue"] == 1 and d0["challenge"]["today"] is None

    # --- do the work
    assert c.post("/api/planner/complete", json={"kind": "task", "ref_id": t_done["id"], "date": day(0)}).status_code == 200
    first_video = c.get(f"/api/video-playlists/{pl['id']}/videos").json()["items"][0]
    assert c.post(f"/api/videos/{first_video['id']}/status", json={"status": "completed"}).status_code == 200
    assert c.put(f"/api/habits/{habit['id']}/logs/{day(0)}", json={"completed": True}).status_code == 200
    ch = c.post("/api/challenges", json={"mode": "existing_project", "project_id": proj["id"], "planned_task": "Add retrieval"}).json()
    assert c.post(f"/api/challenges/{ch['id']}/complete", json=EVIDENCE).status_code == 200

    p1, d1 = agree()
    assert p1["summary"]["completed"] > p0["summary"]["completed"]
    assert d1["tasks"]["completed_today"] == 1 and d1["tasks"]["overdue"] == 1
    assert d1["videos"][0]["watched_today"] == 1 and d1["videos"][0]["remaining_today"] == 1
    assert d1["habits"]["best_streak"] == 1
    assert d1["challenge"]["today"]["status"] == "completed" and d1["challenge"]["stats"]["current_streak"] == 1
    assert d1["projects"][0]["minutes_spent"] == 90 and d1["week"][-1]["dev_minutes"] == 90
    # the challenge is the owner's own evidence: it must not claim to be verified
    assert d1["challenge"]["today"]["verification_status"] == "unverified"

    # --- the assistant proposes changes; nothing happens until approved, and every view then agrees again
    script = ScriptedProvider([
        LLMResponse(tool_calls=[ToolCall("a", "get_pending_tasks", {})], stop_reason="tool_use"),
        LLMResponse(tool_calls=[ToolCall("b", "complete_task", {"task_id": t_late["id"]}), ToolCall("c", "create_task", {"title": "Review notes", "scheduled_date": day(1)})], stop_reason="tool_use"),
        LLMResponse(text="I proposed two changes. They need your approval."),
    ])
    monkeypatch.setattr(assistant_router, "current_provider", lambda: script)
    out = c.post("/api/ai/chat", json={"message": "clear my backlog"}).json()
    assert [a["tool_name"] for a in out["pending"]] == ["complete_task", "create_task"]
    assert c.get(f"/api/tasks/{t_late['id']}").json()["status"] != "completed"          # proposal only
    assert dash()["tasks"]["overdue"] == 1
    assert [t["title"] for t in c.get("/api/tasks").json()["items"] if t["title"] == "Review notes"] == []

    assert c.post(f"/api/ai/pending/{out['pending'][0]['id']}/approve").json()["status"] == "executed"
    assert c.post(f"/api/ai/pending/{out['pending'][1]['id']}/reject").json()["status"] == "rejected"
    assert c.get(f"/api/tasks/{t_late['id']}").json()["status"] == "completed"
    assert [t["title"] for t in c.get("/api/tasks").json()["items"] if t["title"] == "Review notes"] == []   # rejected -> never created
    p2, d2 = agree()
    assert d2["tasks"]["overdue"] == 0 and p2["summary"]["overdue"] == 0 and p2["summary"]["completed"] > p1["summary"]["completed"]

    # --- the assistant can only see what the features show
    assert c.get("/api/ai/pending").json() == []


def test_a_second_account_row_sees_none_of_it(c, db):
    """Seed a full set of data for user 1 through the API, then read everything as user 2 directly from the services."""
    c.post("/api/tasks", json={"title": "Mine", "scheduled_date": day(0)})
    c.post("/api/habits", json={"name": "Reading", "start_date": day(-1)})
    c.post("/api/projects", json={"title": "Private project"})
    c.post("/api/ai/memories", json={"content": "I like short answers"})

    from app.core.timeutil import user_today
    from app.models import User
    from app.services import dashboard, habits, planner, projects, tasks

    other = User(id=2, email="o@example.com", password_hash="x", display_name="O", timezone="UTC")
    db.add(other)
    db.commit()
    assert tasks.list_tasks(db, other, view="all") == ([], 0)
    d = dashboard.build(db, other)
    assert d["is_empty"] and d["tasks"]["today"] == 0 and d["projects"] == [] and d["habits"]["active"] == 0
    assert "Mine" not in str(planner.build_day(db, other, user_today(other)))
    assert projects.list_projects(db, other) == []
    assert habits.list_habits(db, other)["items"] == []


def test_the_planner_alone_does_not_create_the_roadmap_but_agrees_once_the_dashboard_has_been_opened(c):
    """Deliberate (see test_planner): merely viewing the planner never creates the roadmap. The dashboard (the landing page) does."""
    assert [i for i in c.get("/api/planner").json()["items"] if i["kind"] == "topic"] == []
    d = c.get("/api/dashboard").json()
    p = c.get("/api/planner").json()
    assert [(i["kind"], i["status"]) for i in p["items"] if i["kind"] == "topic"] == [("topic", "pending")]
    assert d["plan"]["summary"] == p["summary"]
