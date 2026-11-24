"""HTTP-level tests for /api/roadmap: auth, shapes, status codes, validation."""
import pytest

SETUP = {"email": "me@example.com", "password": "correct-horse-9", "display_name": "Me", "timezone": "Asia/Kolkata"}


@pytest.fixture
def c(client):
    assert client.post("/api/auth/setup", json=SETUP).status_code == 201
    return client


def find(c, title):
    return next(t for st in c.get("/api/roadmap").json()["stages"] for t in st["topics"] if t["title"] == title)


@pytest.mark.parametrize("method, path", [
    ("get", "/api/roadmap"), ("post", "/api/roadmap/topics"), ("patch", "/api/roadmap/topics/1"), ("delete", "/api/roadmap/topics/1"),
    ("post", "/api/roadmap/topics/1/status"), ("get", "/api/roadmap/topics/1/study"), ("post", "/api/roadmap/topics/1/study"),
])
def test_every_endpoint_requires_login(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_get_roadmap_shape_and_seed(c):
    r = c.get("/api/roadmap").json()
    assert len(r["stages"]) == 5 and r["overall"]["total"] == 51 and r["overall"]["percent"] == 0
    assert r["next_topic"]["title"] == "Python"
    t = r["stages"][0]["topics"][0]
    assert set(t) == {"id", "stage_id", "title", "description", "position", "status", "notes", "minutes_spent", "study_days",
                      "last_studied_on", "completed_at"}


def test_status_flow_over_http(c):
    t = find(c, "RAG")
    r = c.post(f"/api/roadmap/topics/{t['id']}/status", json={"status": "completed"})
    assert r.status_code == 200 and r.json()["completed_at"] is not None
    overall = c.get("/api/roadmap").json()["overall"]
    assert (overall["completed"], overall["percent"]) == (1, 1)
    assert c.post(f"/api/roadmap/topics/{t['id']}/status", json={"status": "not_started"}).json()["completed_at"] is None
    for bad in ({"status": "done"}, {}, {"status": "completed", "completed_at": "2026-01-01T00:00:00Z"}):
        assert c.post(f"/api/roadmap/topics/{t['id']}/status", json=bad).status_code == 422


def test_topic_cannot_be_completed_by_patch(c):
    t = find(c, "RAG")
    assert c.patch(f"/api/roadmap/topics/{t['id']}", json={"status": "completed"}).status_code == 422
    assert find(c, "RAG")["status"] == "not_started"


def test_add_edit_delete_topic(c):
    stage = c.get("/api/roadmap").json()["stages"][3]["id"]
    r = c.post("/api/roadmap/topics", json={"stage_id": stage, "title": "CrewAI"})
    assert r.status_code == 201 and r.json()["status"] == "not_started"
    assert c.post("/api/roadmap/topics", json={"stage_id": stage, "title": "crewai"}).status_code == 409
    assert c.post("/api/roadmap/topics", json={"stage_id": 99999, "title": "X"}).status_code == 404
    assert c.post("/api/roadmap/topics", json={"stage_id": stage, "title": ""}).status_code == 422
    tid = r.json()["id"]
    assert c.patch(f"/api/roadmap/topics/{tid}", json={"notes": "try it"}).json()["notes"] == "try it"
    assert c.patch(f"/api/roadmap/topics/{tid}", json={"title": "MCP"}).status_code == 409      # already in Stage 4
    assert c.delete(f"/api/roadmap/topics/{tid}").status_code == 204
    assert c.delete(f"/api/roadmap/topics/{tid}").status_code == 404


def test_log_study_and_see_totals(c):
    t = find(c, "Docker")
    r = c.post(f"/api/roadmap/topics/{t['id']}/study", json={"minutes": 40, "notes": "images"})
    assert r.status_code == 201 and r.json()["minutes"] == 40
    got = find(c, "Docker")
    assert (got["minutes_spent"], got["study_days"], got["status"]) == (40, 1, "in_progress")
    assert [x["minutes"] for x in c.get(f"/api/roadmap/topics/{t['id']}/study").json()] == [40]
    assert c.delete(f"/api/learning-sessions/{r.json()['id']}").status_code == 204
    assert find(c, "Docker")["minutes_spent"] == 0
    for bad in ({"minutes": 0}, {"minutes": 2000}, {"minutes": 5, "date": "2999-01-01"}, {}):
        assert c.post(f"/api/roadmap/topics/{t['id']}/study", json=bad).status_code == 422


def test_other_users_topics_look_like_not_found(c, db):
    from app.models import RoadmapStage, RoadmapTopic, User

    db.add(User(id=2, email="o@example.com", password_hash="x", display_name="O", timezone="UTC"))
    db.commit()
    db.add(RoadmapStage(id=500, user_id=2, title="Theirs", position=1))
    db.commit()
    db.add(RoadmapTopic(id=600, user_id=2, stage_id=500, title="Secret", position=1))
    db.commit()
    assert c.patch("/api/roadmap/topics/600", json={"notes": "x"}).status_code == 404
    assert c.post("/api/roadmap/topics/600/status", json={"status": "completed"}).status_code == 404
    assert c.post("/api/roadmap/topics/600/study", json={"minutes": 5}).status_code == 404
    assert c.delete("/api/roadmap/topics/600").status_code == 404
    assert c.post("/api/roadmap/topics", json={"stage_id": 500, "title": "x"}).status_code == 404
    assert all(st["title"] != "Theirs" for st in c.get("/api/roadmap").json()["stages"])
