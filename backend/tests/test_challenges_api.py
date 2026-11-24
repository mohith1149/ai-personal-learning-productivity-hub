"""HTTP-level tests for /api/challenges: auth, shapes, status codes and a full day end to end."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

SETUP = {"email": "me@example.com", "password": "correct-horse-9", "display_name": "Me", "timezone": "Asia/Kolkata"}
TODAY = datetime.now(ZoneInfo("Asia/Kolkata")).date()
REPO = "https://github.com/me/rag-bot"
SUMMARY = "Implemented the retrieval step: chunking, embeddings and a top-k search over the vector store."
EVIDENCE = {"summary": SUMMARY, "repo_url": REPO, "commit_sha": "a1b2c3d4e5f6", "commit_message": "Add retrieval step to RAG pipeline", "minutes": 90}


def day(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


@pytest.fixture
def c(client):
    assert client.post("/api/auth/setup", json=SETUP).status_code == 201
    return client


def project(c, title="RAG chatbot", **kw):
    r = c.post("/api/projects", json={"title": title, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def plan(c, pid, **kw):
    r = c.post("/api/challenges", json={"mode": "existing_project", "project_id": pid, "planned_task": "Add the retrieval step", **kw})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.parametrize("method, path", [
    ("get", "/api/challenges/today"), ("get", "/api/challenges/calendar"), ("get", "/api/challenges/history"), ("post", "/api/challenges"),
    ("post", "/api/challenges/excuse"), ("get", "/api/challenges/1"), ("patch", "/api/challenges/1"), ("post", "/api/challenges/1/start"),
    ("post", "/api/challenges/1/complete"), ("delete", "/api/challenges/1"),
])
def test_every_endpoint_requires_login(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_today_when_nothing_is_planned(c):
    r = c.get("/api/challenges/today").json()
    assert r["date"] == TODAY.isoformat() and r["challenge"] is None and r["suggestions"] == []
    assert r["stats"] == {"completed": 0, "excused": 0, "missed": 0, "completion_rate": 0, "current_streak": 0, "longest_streak": 0,
                          "total_minutes": 0, "first_day": None}


def test_a_full_day_end_to_end(c):
    pid = project(c)["id"]
    today = c.get("/api/challenges/today").json()
    assert today["suggestions"][0]["project_id"] == pid                       # an idea built from your own project

    ch = plan(c, pid, estimated_minutes=60)
    assert (ch["status"], ch["date"], ch["project"]["title"]) == ("planned", TODAY.isoformat(), "RAG chatbot")
    assert c.get("/api/challenges/today").json()["challenge"]["id"] == ch["id"]
    assert c.post(f"/api/challenges/{ch['id']}/start").json()["status"] == "in_progress"

    done = c.post(f"/api/challenges/{ch['id']}/complete", json=EVIDENCE)
    assert done.status_code == 200, done.text
    out = done.json()
    assert (out["status"], out["verification_status"], out["actual_minutes"]) == ("completed", "unverified", 90)
    # the other features agree: project time, the planner and the stats
    assert len(c.get(f"/api/projects/{pid}").json()["sessions"]) == 1
    assert c.get("/api/planner").json()["summary"]["dev_minutes"] == 90
    stats = c.get("/api/challenges/today").json()["stats"]
    assert (stats["completed"], stats["current_streak"], stats["total_minutes"]) == (1, 1, 90)
    assert c.get("/api/challenges/history").json()[0]["id"] == ch["id"]
    cal = c.get("/api/challenges/calendar", params={"start": day(-2), "end": day(0)}).json()
    assert [x["status"] for x in cal["days"]] == ["none", "none", "completed"]


def test_new_project_mode(c):
    r = c.post("/api/challenges", json={"mode": "new_project", "planned_task": "Scaffold the service", "new_project": {"title": "Agent playground"}})
    assert r.status_code == 201 and r.json()["project"]["title"] == "Agent playground"
    assert [p["title"] for p in c.get("/api/projects").json()] == ["Agent playground"]
    dup = c.post("/api/challenges", json={"mode": "new_project", "date": day(1), "planned_task": "Again", "new_project": {"title": "Agent playground"}})
    assert dup.status_code == 409


@pytest.mark.parametrize("body", [
    {}, {"mode": "existing_project"}, {"mode": "new_project", "planned_task": "xyz"},
    {"mode": "existing_project", "project_id": 1, "planned_task": "xyz", "status": "completed"}, {"mode": "bad", "planned_task": "xyz"},
    {"mode": "new_project", "planned_task": "xyz", "new_project": {"title": "X", "repo_url": "https://gitlab.com/a/b"}},
])
def test_plan_validation(c, body):
    assert c.post("/api/challenges", json=body).status_code == 422


def test_plan_rules_over_http(c):
    pid = project(c)["id"]
    plan(c, pid)
    assert c.post("/api/challenges", json={"mode": "existing_project", "project_id": pid, "planned_task": "Again"}).status_code == 409
    assert c.post("/api/challenges", json={"mode": "existing_project", "project_id": pid, "planned_task": "Past", "date": day(-1)}).status_code == 422
    assert c.post("/api/challenges", json={"mode": "existing_project", "project_id": 99999, "planned_task": "Nope", "date": day(1)}).status_code == 404


@pytest.mark.parametrize("change, expected", [
    ({"summary": "short"}, 422), ({"commit_sha": "zzzzzzz"}, 422), ({"repo_url": "https://example.com/a/b"}, 422), ({"minutes": 0}, 422),
    ({"commit_message": "update"}, 422), ({"summary": "word " * 20}, 422), ({"extra": 1}, 422), ({"repo_url": "https://github.com/me/other"}, 200),
])
def test_completion_needs_real_evidence_over_http(c, change, expected):
    pid = project(c)["id"]
    ch = plan(c, pid)
    r = c.post(f"/api/challenges/{ch['id']}/complete", json={**EVIDENCE, **change})
    assert r.status_code == expected, r.text
    if expected != 200:
        assert c.get(f"/api/challenges/{ch['id']}").json()["status"] == "planned"
        assert c.get(f"/api/projects/{pid}").json()["sessions"] == []


def test_completion_rules_over_http(c):
    pid = project(c, repo_url=REPO)["id"]
    ch = plan(c, pid)
    wrong = c.post(f"/api/challenges/{ch['id']}/complete", json={**EVIDENCE, "repo_url": "https://github.com/me/other"})
    assert wrong.status_code == 422 and "repository is" in wrong.json()["detail"]
    assert c.post(f"/api/challenges/{ch['id']}/complete", json={}).status_code == 422
    assert c.post(f"/api/challenges/{ch['id']}/complete", json=EVIDENCE).status_code == 200
    assert c.post(f"/api/challenges/{ch['id']}/complete", json={**EVIDENCE, "commit_sha": "9f8e7d6c5b4a"}).status_code == 409
    assert c.delete(f"/api/challenges/{ch['id']}").status_code == 422
    assert c.post("/api/challenges/99999/complete", json=EVIDENCE).status_code == 404
    future = plan(c, pid, date=day(1))
    assert c.post(f"/api/challenges/{future['id']}/complete", json={**EVIDENCE, "commit_sha": "9f8e7d6c5b4a"}).status_code == 422


def test_reusing_a_commit_over_http(c):
    pid = project(c)["id"]
    c.post(f"/api/challenges/{plan(c, pid)['id']}/complete", json=EVIDENCE)
    tomorrow = plan(c, pid, date=day(1))
    assert c.post(f"/api/challenges/{tomorrow['id']}/complete", json=EVIDENCE).status_code == 422


def test_edit_and_delete_over_http(c):
    ch = plan(c, project(c)["id"])
    r = c.patch(f"/api/challenges/{ch['id']}", json={"planned_task": "Something else", "estimated_minutes": 30})
    assert r.status_code == 200 and r.json()["planned_task"] == "Something else"
    assert c.patch(f"/api/challenges/{ch['id']}", json={"status": "completed"}).status_code == 422
    assert c.patch(f"/api/challenges/{ch['id']}", json={"planned_task": None}).status_code == 422
    assert c.delete(f"/api/challenges/{ch['id']}").status_code == 204
    assert c.get(f"/api/challenges/{ch['id']}").status_code == 404


def test_excuse_over_http(c):
    assert c.post("/api/challenges/excuse", json={"reason": "no"}).status_code == 422
    assert c.post("/api/challenges/excuse", json={}).status_code == 422
    assert c.post("/api/challenges/excuse", json={"date": day(1), "reason": "Planning ahead"}).status_code == 422
    r = c.post("/api/challenges/excuse", json={"date": day(-2), "reason": "Was travelling"})
    assert r.status_code == 200 and (r.json()["status"], r.json()["excuse_reason"]) == ("excused", "Was travelling")
    assert c.post("/api/challenges/excuse", json={"date": day(-2), "reason": "Again please"}).status_code == 409
    cal = c.get("/api/challenges/calendar", params={"start": day(-2), "end": day(-2)}).json()
    assert cal["days"][0]["status"] == "excused" and cal["stats"]["excused"] == 1


def test_a_missed_day_is_computed(c):
    pid = project(c)["id"]
    c.post("/api/challenges/excuse", json={"date": day(-3), "reason": "Was travelling"})
    cal = c.get("/api/challenges/calendar", params={"start": day(-3), "end": day(0)}).json()
    assert [x["status"] for x in cal["days"]] == ["excused", "missed", "missed", "none"]
    assert cal["stats"]["missed"] == 2


def test_calendar_validation(c):
    assert c.get("/api/challenges/calendar", params={"start": day(0), "end": day(-1)}).status_code == 422
    assert c.get("/api/challenges/calendar", params={"start": day(-900), "end": day(0)}).status_code == 422
    assert c.get("/api/challenges/calendar", params={"start": "bad"}).status_code == 422
    assert len(c.get("/api/challenges/calendar").json()["days"]) == 30
    assert c.get("/api/challenges/history", params={"limit": 0}).status_code == 422


def test_other_users_challenges_are_not_reachable(c, db):
    from app.models import DailyChallenge, User

    db.add(User(id=2, email="o@example.com", password_hash="x", display_name="O", timezone="UTC"))
    db.commit()
    db.add(DailyChallenge(user_id=2, date=TODAY, mode="existing_project", planned_task="secret", status="planned"))
    db.commit()
    cid = db.query(DailyChallenge).one().id
    assert c.get(f"/api/challenges/{cid}").status_code == 404
    assert c.post(f"/api/challenges/{cid}/start").status_code == 404
    assert c.post(f"/api/challenges/{cid}/complete", json=EVIDENCE).status_code == 404
    assert c.delete(f"/api/challenges/{cid}").status_code == 404
    assert c.get("/api/challenges/today").json()["challenge"] is None
