"""HTTP-level tests for /api/habits: auth, shapes, status codes, validation, streaks end to end."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

SETUP = {"email": "me@example.com", "password": "correct-horse-9", "display_name": "Me", "timezone": "Asia/Kolkata"}
TODAY = datetime.now(ZoneInfo("Asia/Kolkata")).date()


def day(n: int) -> str:
    """The date n days ago (0 = today in the user's timezone)."""
    return (TODAY - timedelta(days=n)).isoformat()


@pytest.fixture
def c(client):
    assert client.post("/api/auth/setup", json=SETUP).status_code == 201
    return client


def new(c, **kw) -> dict:
    r = c.post("/api/habits", json={"name": "Reading", "start_date": day(60), **kw})
    assert r.status_code == 201, r.text
    return r.json()


def put(c, hid, d, **kw):
    return c.put(f"/api/habits/{hid}/logs/{d}", json=kw)


@pytest.mark.parametrize("method, path", [
    ("get", "/api/habits"), ("post", "/api/habits"), ("get", "/api/habits/1"), ("patch", "/api/habits/1"), ("delete", "/api/habits/1"),
    ("get", "/api/habits/1/logs"), ("put", "/api/habits/1/logs/2026-01-01"), ("delete", "/api/habits/1/logs/2026-01-01"),
])
def test_every_endpoint_requires_login(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_create_get_list_shape(c):
    h = new(c, description="d", notes="n", target_value=30, unit="pages")
    assert set(h) == {"id", "name", "description", "notes", "start_date", "frequency", "target_per_period", "target_value", "unit",
                      "active", "created_at", "today", "done_today", "streak", "week", "month", "total_completed", "recent"}
    assert (h["frequency"], h["target_value"], h["unit"], h["done_today"], h["total_completed"]) == ("daily", 30, "pages", False, 0)
    listing = c.get("/api/habits").json()
    assert [i["id"] for i in listing["items"]] == [h["id"]] and listing["due_today"] == 1
    assert c.get(f"/api/habits/{h['id']}").json()["name"] == "Reading"


def test_default_start_date_is_today(c):
    r = c.post("/api/habits", json={"name": "Walking"})
    assert r.status_code == 201 and r.json()["start_date"] == day(0)


@pytest.mark.parametrize("body", [
    {}, {"name": ""}, {"name": "x" * 121}, {"name": "A", "frequency": "monthly"}, {"name": "A", "frequency": "daily", "target_per_period": 2},
    {"name": "A", "frequency": "weekly", "target_per_period": 0}, {"name": "A", "frequency": "weekly", "target_per_period": 8},
    {"name": "A", "target_value": 0}, {"name": "A", "start_date": "not-a-date"}, {"name": "A", "streak": 99}, {"name": "A", "unit": "x" * 31},
])
def test_validation(c, body):
    assert c.post("/api/habits", json=body).status_code == 422


def test_duplicate_name_is_409(c):
    new(c)
    assert c.post("/api/habits", json={"name": "reading"}).status_code == 409


def test_update_and_delete(c):
    h = new(c)
    r = c.patch(f"/api/habits/{h['id']}", json={"name": "Deep reading", "frequency": "weekly", "target_per_period": 3, "active": False})
    assert r.status_code == 200 and (r.json()["name"], r.json()["target_per_period"], r.json()["active"]) == ("Deep reading", 3, False)
    assert c.patch(f"/api/habits/{h['id']}", json={"name": None}).status_code == 422
    assert c.patch("/api/habits/9999", json={"name": "X"}).status_code == 404
    assert c.delete(f"/api/habits/{h['id']}").status_code == 204
    assert c.delete(f"/api/habits/{h['id']}").status_code == 404
    assert c.get("/api/habits").json() == {"items": [], "due_today": 0}


def test_streak_is_computed_from_real_records_end_to_end(c):
    h = new(c)
    for n in (3, 2, 1):
        put(c, h["id"], day(n), completed=True)
    r = c.get(f"/api/habits/{h['id']}").json()
    assert (r["streak"]["current"], r["streak"]["longest"], r["done_today"]) == (3, 3, False)
    r = put(c, h["id"], day(0), completed=True, value=25, note="ch. 4").json()
    assert (r["streak"]["current"], r["done_today"], r["today"]["value"], r["today"]["note"]) == (4, True, 25, "ch. 4")
    assert c.get("/api/habits").json()["due_today"] == 0
    r = c.delete(f"/api/habits/{h['id']}/logs/{day(2)}").json()           # un-marking a day breaks the run
    assert (r["streak"]["current"], r["streak"]["longest"]) == (2, 2)
    assert c.delete(f"/api/habits/{h['id']}/logs/{day(2)}").status_code == 404


def test_history_endpoint(c):
    h = new(c)
    for n in (0, 1, 40):
        put(c, h["id"], day(n))
    got = c.get(f"/api/habits/{h['id']}/logs", params={"days": 30}).json()
    assert [x["date"] for x in got] == [day(0), day(1)]
    assert set(got[0]) == {"date", "completed", "value", "note"}
    assert len(c.get(f"/api/habits/{h['id']}/logs").json()) == 3          # default window is 90 days
    for bad in (0, 731):
        assert c.get(f"/api/habits/{h['id']}/logs", params={"days": bad}).status_code == 422


def test_cannot_record_future_or_before_start(c):
    h = new(c, start_date=day(5))
    assert put(c, h["id"], (TODAY + timedelta(days=1)).isoformat()).status_code == 422
    assert put(c, h["id"], day(6)).status_code == 422
    assert put(c, h["id"], day(5)).status_code == 200
    assert put(c, h["id"], "2026-13-45").status_code == 422
    assert put(c, h["id"], day(0), completed="maybe").status_code == 422
    assert put(c, h["id"], day(0), value=-1).status_code == 422
    assert put(c, 99999, day(0)).status_code == 404


def test_other_users_habits_look_like_not_found(c, db):
    from app.models import Habit, User

    db.add(User(id=2, email="o@example.com", password_hash="x", display_name="O", timezone="UTC"))
    db.commit()
    db.add(Habit(id=500, user_id=2, name="Theirs"))
    db.commit()
    assert c.get("/api/habits/500").status_code == 404
    assert c.patch("/api/habits/500", json={"name": "x"}).status_code == 404
    assert c.delete("/api/habits/500").status_code == 404
    assert put(c, 500, day(0)).status_code == 404
    assert c.get("/api/habits/500/logs").status_code == 404
    assert c.get("/api/habits").json()["items"] == []
