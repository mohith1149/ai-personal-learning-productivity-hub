"""Dashboard: assembled from the other features, empty for a new account, scoped to the user, consistent with the feature pages."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

SETUP = {"email": "me@example.com", "password": "correct-horse-9", "display_name": "Me", "timezone": "Asia/Kolkata"}
TODAY = datetime.now(ZoneInfo("Asia/Kolkata")).date()
REPO = "https://github.com/me/rag-bot"
EVIDENCE = {"summary": "Implemented the retrieval step: chunking, embeddings and a top-k search over the vector store.", "repo_url": REPO,
            "commit_sha": "a1b2c3d4e5f6", "commit_message": "Add retrieval step to RAG pipeline", "minutes": 90}


def day(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


@pytest.fixture
def c(client):
    assert client.post("/api/auth/setup", json=SETUP).status_code == 201
    return client


def dash(c):
    r = c.get("/api/dashboard")
    assert r.status_code == 200, r.text
    return r.json()


def test_requires_login(client):
    assert client.get("/api/dashboard").status_code == 401


def test_a_new_account_gets_zeros_and_empty_lists_not_invented_data(c):
    d = dash(c)
    assert d["is_empty"] is True and d["date"] == TODAY.isoformat()
    # the only thing on a new account's plan is the first roadmap topic (the roadmap is seeded with your own learning path)
    assert [(i["kind"], i["status"]) for i in d["plan"]["next_items"]] == [("topic", "pending")] and d["plan"]["open_count"] == 1
    assert d["plan"]["summary"]["completed"] == 0
    assert d["videos"] == [] and d["projects"] == [] and d["courses"] == []
    assert d["challenge"]["today"] is None and d["challenge"]["stats"]["completed"] == 0
    assert d["habits"] == {"active": 0, "due_today": 0, "best_streak": 0, "best_streak_name": None, "best_streak_unit": None}
    assert d["tasks"] == {"overdue": 0, "today": 0, "completed_today": 0}
    assert d["roadmap"]["completed"] == 0 and d["roadmap"]["percent"] == 0 and d["roadmap"]["total"] > 0     # the seeded roadmap, nothing done
    assert [w["date"] for w in d["week"]] == [day(n) for n in range(-6, 1)]
    assert all(w["study_minutes"] == 0 and w["dev_minutes"] == 0 for w in d["week"])


def test_everything_is_taken_from_the_features(c):
    t = c.post("/api/tasks", json={"title": "Write report", "scheduled_date": day(0)}).json()
    c.post("/api/tasks", json={"title": "File taxes", "due_date": day(-2)})
    h = c.post("/api/habits", json={"name": "Reading", "start_date": day(-5)}).json()
    c.put(f"/api/habits/{h['id']}/logs/{day(0)}", json={"completed": True})
    c.put(f"/api/habits/{h['id']}/logs/{day(-1)}", json={"completed": True})
    course = c.post("/api/courses", json={"title": "Agentic AI"}).json()
    mod = c.post(f"/api/courses/{course['id']}/modules", json={"title": "Intro"}).json()
    c.post(f"/api/modules/{mod['modules'][0]['id']}/lessons", json={"title": "What is an agent?"})
    p = c.post("/api/projects", json={"title": "RAG chatbot"}).json()
    ch = c.post("/api/challenges", json={"mode": "existing_project", "project_id": p["id"], "planned_task": "Add retrieval"}).json()
    c.post(f"/api/challenges/{ch['id']}/complete", json=EVIDENCE)
    c.post(f"/api/planner/complete", json={"kind": "task", "ref_id": t["id"], "date": day(0)})

    d = dash(c)
    assert d["is_empty"] is False
    assert d["tasks"]["overdue"] == 1 and d["tasks"]["completed_today"] == 1
    assert d["habits"]["active"] == 1 and d["habits"]["best_streak"] == 2 and d["habits"]["best_streak_name"] == "Reading" and d["habits"]["due_today"] == 0
    assert [(x["title"], x["next_lesson"]) for x in d["courses"]] == [("Agentic AI", "What is an agent?")]
    assert [x["title"] for x in d["projects"]] == ["RAG chatbot"] and d["projects"][0]["minutes_spent"] == 90
    assert d["challenge"]["today"]["status"] == "completed" and d["challenge"]["stats"]["current_streak"] == 1
    assert d["week"][-1]["dev_minutes"] == 90
    plan = c.get("/api/planner").json()["summary"]                               # the dashboard agrees with the planner
    assert d["plan"]["summary"] == plan
    titles = [i["title"] for i in d["plan"]["next_items"]]
    assert titles[0] == "File taxes" and "What is an agent?" in titles and "Write report" not in titles   # overdue first, completed items excluded
    assert d["plan"]["open_count"] == plan["pending"] + plan["overdue"]


def test_videos_to_watch_today_come_from_the_playlist_target(c):
    r = c.post("/api/video-playlists", json={"name": "BYTEBYTEGO", "daily_target": 2})
    assert r.status_code == 201, r.text
    pl = r.json()
    for i in range(3):
        r = c.post(f"/api/video-playlists/{pl['id']}/videos", json={"title": f"Video {i}", "url": f"https://youtu.be/abcdefghij{i}"})
        assert r.status_code == 201, r.text
    row = dash(c)["videos"][0]
    assert (row["name"], row["daily_target"], row["watched_today"], row["remaining_today"], row["target_met"]) == ("BYTEBYTEGO", 2, 0, 2, False)
    assert len(row["up_next"]) == 2
    first = c.get(f"/api/video-playlists/{pl['id']}/videos").json()["items"][0]
    c.post(f"/api/videos/{first['id']}/status", json={"status": "completed"})
    row = dash(c)["videos"][0]
    assert (row["watched_today"], row["remaining_today"], len(row["up_next"])) == (1, 1, 1)
    c.post("/api/video-playlists", json={"name": "Inactive", "daily_target": 3})
    pid = [p for p in c.get("/api/video-playlists").json() if p["name"] == "Inactive"][0]["id"]
    c.patch(f"/api/video-playlists/{pid}", json={"active": False})
    assert [v["name"] for v in dash(c)["videos"]] == ["BYTEBYTEGO"]            # inactive collections aren't reminders


def test_projects_list_is_capped_and_least_recently_worked_first(c):
    ids = [c.post("/api/projects", json={"title": f"P{i}"}).json()["id"] for i in range(7)]
    c.post(f"/api/projects/{ids[0]}/sessions", json={"minutes": 30, "summary": "did things"})
    rows = dash(c)["projects"]
    assert len(rows) == 5 and rows[-1]["title"] != "P0" and "P0" not in [r["title"] for r in rows]


def test_other_users_data_is_not_included(c, db):
    from app.models import Task, User

    db.add(User(id=2, email="o@example.com", password_hash="x", display_name="O", timezone="UTC"))
    db.commit()
    db.add(Task(user_id=2, title="Secret", scheduled_date=TODAY))
    db.commit()
    d = dash(c)
    assert d["is_empty"] is True and d["tasks"]["today"] == 0 and d["tasks"]["overdue"] == 0


def test_a_collection_with_nothing_left_to_watch_is_not_listed(c):
    pl = c.post("/api/video-playlists", json={"name": "Empty one", "daily_target": 3}).json()
    assert pl["id"] and dash(c)["videos"] == []
