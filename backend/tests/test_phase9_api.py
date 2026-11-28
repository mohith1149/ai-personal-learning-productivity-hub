"""HTTP tests for Phase 9: /api/rest-days, /api/planner/preferences, /api/planner/roll-over."""
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


@pytest.mark.parametrize("method, path", [
    ("get", "/api/rest-days"), ("post", "/api/rest-days"), ("delete", "/api/rest-days/2026-11-23"),
    ("get", "/api/planner/preferences"), ("patch", "/api/planner/preferences"), ("post", "/api/planner/roll-over"),
])
def test_every_endpoint_requires_login(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_rest_day_lifecycle(c):
    r = c.post("/api/rest-days", json={"date": day(1), "reason": "Trip"})
    assert r.status_code == 201, r.text
    assert r.json()["used"] == 1 and r.json()["days"][0] == {"date": day(1), "reason": "Trip"}
    assert c.post("/api/rest-days", json={"date": day(1)}).status_code == 409
    month = day(1)[:7]
    assert c.get("/api/rest-days", params={"month": month}).json()["used"] == 1
    assert c.delete(f"/api/rest-days/{day(1)}").json()["used"] == 0
    assert c.delete(f"/api/rest-days/{day(1)}").status_code == 404


def test_rest_day_validation(c):
    assert c.post("/api/rest-days", json={"date": "nope"}).status_code == 422
    assert c.post("/api/rest-days", json={"date": day(1), "extra": 1}).status_code == 422
    assert c.post("/api/rest-days", json={"date": day(-30)}).status_code == 422
    assert c.get("/api/rest-days", params={"month": "2026-13"}).status_code == 422
    assert c.get("/api/rest-days", params={"month": "1999-01"}).status_code == 422


def test_the_limit_is_changed_in_preferences_and_enforced(c):
    assert c.get("/api/planner/preferences").json() == {"weekday_minutes": None, "focus_windows": None, "rest_days_per_month": 4}
    assert c.patch("/api/planner/preferences", json={"rest_days_per_month": 0}).json()["rest_days_per_month"] == 0
    r = c.post("/api/rest-days", json={"date": day(1)})
    assert r.status_code == 422 and "rest days" in r.json()["detail"]


def test_weekday_hours_round_trip_and_validation(c):
    hours = [240, 240, 240, 240, 240, 120, 60]
    assert c.patch("/api/planner/preferences", json={"weekday_minutes": hours}).json()["weekday_minutes"] == hours
    assert c.get("/api/planner/preferences").json()["weekday_minutes"] == hours
    assert c.patch("/api/planner/preferences", json={"rest_days_per_month": 3}).json()["weekday_minutes"] == hours   # untouched
    assert c.patch("/api/planner/preferences", json={"weekday_minutes": None}).json()["weekday_minutes"] is None   # clears it
    for bad in ([1, 2, 3], [0] * 7 + [1], [1441] + [0] * 6, [-1] + [0] * 6, "x"):
        assert c.patch("/api/planner/preferences", json={"weekday_minutes": bad}).status_code == 422
    assert c.patch("/api/planner/preferences", json={"rest_days_per_month": 32}).status_code == 422
    assert c.patch("/api/planner/preferences", json={"nope": 1}).status_code == 422


def test_overload_shows_in_the_plan(c):
    c.patch("/api/planner/preferences", json={"weekday_minutes": [60] * 7})
    c.post("/api/tasks", json={"title": "Big", "scheduled_date": day(0), "estimated_minutes": 90})
    s = c.get("/api/planner").json()["summary"]
    assert s["overloaded"] is True and s["planned_minutes"] == 90 and s["available_minutes"] == 60


def test_rest_day_in_the_plan_and_challenge_calendar(c):
    c.post("/api/tasks", json={"title": "Read", "scheduled_date": day(0)})
    assert c.post("/api/rest-days", json={"date": day(0)}).status_code == 201
    p = c.get("/api/planner").json()
    assert p["summary"]["rest_day"] is True and p["items"][0]["status"] == "excused" and p["items"][0]["excuse_reason"] == "Rest day"
    assert c.get("/api/challenges/today").json()["rest_day"] is True
    cal = c.get("/api/challenges/calendar", params={"start": day(0), "end": day(1)}).json()
    assert cal["days"][0]["status"] == "rest" and cal["stats"]["rest_days"] == 1


def test_rest_days_show_as_excused_in_reports(c):
    c.post("/api/rest-days", json={"date": day(0)})
    r = c.get("/api/reports/weekly", params={"week_start": day(0)}).json()
    assert r["challenge"]["excused"] >= 1 and {d["challenge"] for d in r["days"]} <= {"completed", "excused", "missed", "planned", "in_progress", "none"}


def test_roll_over_preview_then_apply(c):
    t = c.post("/api/tasks", json={"title": "Unfinished", "scheduled_date": day(0), "estimated_minutes": 30}).json()
    pre = c.post("/api/planner/roll-over", json={"dry_run": True})
    assert pre.status_code == 200 and pre.json()["moved"][0]["task_id"] == t["id"] and pre.json()["dry_run"] is True
    assert c.get(f"/api/tasks/{t['id']}").json()["scheduled_date"] == day(0)
    done = c.post("/api/planner/roll-over", json={})
    assert done.status_code == 200 and done.json()["dry_run"] is False and done.json()["tomorrow"]["date"] == day(1)
    assert c.get(f"/api/tasks/{t['id']}").json()["scheduled_date"] == day(1)
    assert c.post("/api/planner/roll-over", json={}).json()["moved"] == []                  # nothing left to move
    assert c.post("/api/planner/roll-over", json={"task_ids": "x"}).status_code == 422
    assert c.post("/api/planner/roll-over", json={"extra": 1}).status_code == 422


def test_a_task_moved_three_times_is_flagged_in_the_plan(c):
    t = c.post("/api/tasks", json={"title": "Stubborn", "scheduled_date": day(0)}).json()
    for i in range(3):
        r = c.post(f"/api/planner/tasks/{t['id']}/reschedule", json={"date": day(1), "from_date": day(0)})
        assert r.status_code == 200
        c.patch(f"/api/tasks/{t['id']}", json={"scheduled_date": day(0)})   # back onto today's plan, as if the day came round again
    item = c.get("/api/planner").json()["items"][0]
    assert item["slipping"] is True and item["carry_count"] == 3
