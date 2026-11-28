"""Phase 12: hard / light topics and your best focus hours for each weekday."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.services import focus

SETUP = {"email": "me@example.com", "password": "correct-horse-9", "display_name": "Me", "timezone": "Asia/Kolkata"}
TODAY = datetime.now(ZoneInfo("Asia/Kolkata")).date()
WEEK = ["06:00-09:00", "06:00-09:00", "", "06:00-09:00", "06:00-09:00", "08:00-11:00", ""]


@pytest.fixture
def c(client):
    assert client.post("/api/auth/setup", json=SETUP).status_code == 201
    client.get("/api/roadmap")  # the roadmap is created the first time it is opened
    return client


def topics(c) -> list[dict]:
    return [t for st in c.get("/api/roadmap").json()["stages"] for t in st["topics"]]


def today_plan(c) -> dict:
    return c.get("/api/planner").json()


def topic_item(plan: dict, topic_id: int) -> dict | None:
    return next((i for i in plan["items"] if i["key"] == f"topic:{topic_id}"), None)


def mark(c, topic_id: int, difficulty: str):
    return c.patch(f"/api/roadmap/topics/{topic_id}", json={"difficulty": difficulty})


# ============================== the window format ==============================


@pytest.mark.parametrize("w", ["06:00-09:00", "00:00-23:59", "23:00-23:30"])
def test_valid_windows(w):
    assert focus.valid_window(w)


@pytest.mark.parametrize("w", ["", "9-12", "09:00-09:00", "10:00-09:00", "24:00-25:00", "06:00-09:60", "06:00 - 09:00", "06:00-09:00,", "a"])
def test_invalid_windows(w):
    assert not focus.valid_window(w)


def test_decode_and_encode_round_trip():
    raw = focus.encode(WEEK)
    assert focus.decode(raw) == WEEK


@pytest.mark.parametrize("raw", [None, "", ",,,,,,", "06:00-09:00", "x,,,,,,", "10:00-09:00,,,,,,", "06:00-09:00,,,,,,,"])
def test_unset_or_damaged_values_mean_not_set(raw):
    assert focus.decode(raw) is None


def test_encode_of_nothing_is_nothing():
    assert focus.encode(None) is None and focus.encode([""] * 7) is None


# ============================== difficulty on topics ==============================


def test_every_topic_starts_normal(c):
    ts = topics(c)
    assert ts and {t["difficulty"] for t in ts} == {"normal"}


def test_mark_a_topic_hard_and_back(c):
    t = topics(c)[0]
    r = mark(c, t["id"], "hard")
    assert r.status_code == 200 and r.json()["difficulty"] == "hard"
    assert next(x for x in topics(c) if x["id"] == t["id"])["difficulty"] == "hard"
    assert mark(c, t["id"], "light").json()["difficulty"] == "light"
    assert mark(c, t["id"], "normal").json()["difficulty"] == "normal"


def test_a_bad_difficulty_is_rejected_and_nothing_changes(c):
    t = topics(c)[0]
    for bad in ("easy", "HARD", "", 3):
        assert mark(c, t["id"], bad).status_code == 422
    assert c.patch(f"/api/roadmap/topics/{t['id']}", json={"difficulty": None}).status_code in (400, 422)
    assert next(x for x in topics(c) if x["id"] == t["id"])["difficulty"] == "normal"


def test_changing_difficulty_keeps_the_other_fields(c):
    t = topics(c)[0]
    c.patch(f"/api/roadmap/topics/{t['id']}", json={"notes": "keep me"})
    mark(c, t["id"], "hard")
    after = next(x for x in topics(c) if x["id"] == t["id"])
    assert after["notes"] == "keep me" and after["title"] == t["title"] and after["status"] == t["status"]


def test_a_new_topic_can_be_created_hard(c):
    stage = c.get("/api/roadmap").json()["stages"][0]["id"]
    r = c.post("/api/roadmap/topics", json={"stage_id": stage, "title": "Attention from scratch", "difficulty": "hard"})
    assert r.status_code == 201 and r.json()["difficulty"] == "hard"
    plain = c.post("/api/roadmap/topics", json={"stage_id": stage, "title": "A plain one"})
    assert plain.json()["difficulty"] == "normal"


def test_another_users_topic_cannot_be_marked(client):
    client.post("/api/auth/setup", json=SETUP)
    assert client.patch("/api/roadmap/topics/99999", json={"difficulty": "hard"}).status_code == 404


# ============================== focus hours preference ==============================


def test_preferences_start_without_focus_hours(c):
    assert c.get("/api/planner/preferences").json() == {"weekday_minutes": None, "focus_windows": None, "rest_days_per_month": 4}


def test_set_and_read_back_focus_hours(c):
    r = c.patch("/api/planner/preferences", json={"focus_windows": WEEK})
    assert r.status_code == 200 and r.json()["focus_windows"] == WEEK
    assert c.get("/api/planner/preferences").json()["focus_windows"] == WEEK


def test_setting_focus_hours_leaves_the_other_preferences(c):
    c.patch("/api/planner/preferences", json={"weekday_minutes": [60] * 7, "rest_days_per_month": 2})
    c.patch("/api/planner/preferences", json={"focus_windows": WEEK})
    p = c.get("/api/planner/preferences").json()
    assert p["weekday_minutes"] == [60] * 7 and p["rest_days_per_month"] == 2 and p["focus_windows"] == WEEK


def test_other_preferences_do_not_clear_focus_hours(c):
    c.patch("/api/planner/preferences", json={"focus_windows": WEEK})
    c.patch("/api/planner/preferences", json={"rest_days_per_month": 1})
    assert c.get("/api/planner/preferences").json()["focus_windows"] == WEEK


def test_clearing_focus_hours(c):
    c.patch("/api/planner/preferences", json={"focus_windows": WEEK})
    assert c.patch("/api/planner/preferences", json={"focus_windows": None}).json()["focus_windows"] is None
    c.patch("/api/planner/preferences", json={"focus_windows": WEEK})
    assert c.patch("/api/planner/preferences", json={"focus_windows": [""] * 7}).json()["focus_windows"] is None


@pytest.mark.parametrize("bad", [
    ["06:00-09:00"] * 6, ["06:00-09:00"] * 8, ["09:00-06:00"] * 7, ["6-9"] * 7, ["25:00-26:00"] * 7, [5] * 7, "06:00-09:00",
])
def test_bad_focus_hours_are_rejected(c, bad):
    assert c.patch("/api/planner/preferences", json={"focus_windows": bad}).status_code == 422
    assert c.get("/api/planner/preferences").json()["focus_windows"] is None


# ============================== hints on the plan ==============================


def hard_topic_on_plan(c) -> dict:
    """The topic the plan shows today (next up), marked hard."""
    shown = next(i for i in today_plan(c)["items"] if i["kind"] == "topic")
    mark(c, int(shown["key"].split(":")[1]), "hard")
    return topic_item(today_plan(c), int(shown["key"].split(":")[1]))


def test_a_hard_topic_with_no_focus_hours_asks_you_to_set_them(c):
    item = hard_topic_on_plan(c)
    assert item["difficulty"] == "hard" and "set your focus hours" in item["hint"]
    assert today_plan(c)["summary"]["focus_window"] is None


def test_a_hard_topic_names_todays_window(c):
    c.patch("/api/planner/preferences", json={"focus_windows": [f"07:00-10:00"] * 7})
    item = hard_topic_on_plan(c)
    assert "focus hours, 07:00–10:00" in item["hint"]
    assert today_plan(c)["summary"]["focus_window"] == "07:00-10:00"


def test_a_hard_topic_on_a_day_with_no_window_says_so(c):
    c.patch("/api/planner/preferences", json={"focus_windows": ["06:00-09:00"] + [""] * 6})
    day = TODAY.weekday()
    item = hard_topic_on_plan(c)
    if day == 0:
        assert "focus hours, 06:00–09:00" in item["hint"]
    else:
        assert item["hint"] == "Hard topic: no focus hours set for this day"
        assert today_plan(c)["summary"]["focus_window"] is None


def test_a_light_topic_is_for_a_walk_or_the_evening(c):
    shown = next(i for i in today_plan(c)["items"] if i["kind"] == "topic")
    tid = int(shown["key"].split(":")[1])
    mark(c, tid, "light")
    item = topic_item(today_plan(c), tid)
    assert item["difficulty"] == "light" and "walk" in item["hint"]


def test_a_normal_topic_has_no_hint(c):
    item = next(i for i in today_plan(c)["items"] if i["kind"] == "topic")
    assert item["difficulty"] == "normal" and item["hint"] is None


def test_tasks_and_habits_never_get_a_hint(c):
    c.post("/api/tasks", json={"title": "Pay the bill", "due_date": TODAY.isoformat()})
    c.patch("/api/planner/preferences", json={"focus_windows": WEEK})
    for i in today_plan(c)["items"]:
        if i["kind"] in ("task", "habit", "project", "lesson"):
            assert i["hint"] is None and i["difficulty"] is None


def test_a_finished_topic_gets_no_hint(c):
    t = topics(c)[0]
    mark(c, t["id"], "hard")
    c.post(f"/api/roadmap/topics/{t['id']}/status", json={"status": "completed"})
    item = topic_item(today_plan(c), t["id"])
    assert item is not None and item["status"] == "completed" and item["difficulty"] == "hard" and item["hint"] is None


def test_a_rest_day_drops_the_hint_because_the_item_is_excused(c):
    item = hard_topic_on_plan(c)
    assert item["hint"]
    assert c.post("/api/rest-days", json={"date": TODAY.isoformat()}).status_code == 201
    after = topic_item(today_plan(c), int(item["key"].split(":")[1]))
    assert after["status"] == "excused" and after["hint"] is None


def test_focus_hours_are_private_to_each_user(client):
    client.post("/api/auth/setup", json=SETUP)
    client.patch("/api/planner/preferences", json={"focus_windows": WEEK})
    client.post("/api/auth/logout")
    assert client.get("/api/planner/preferences").status_code == 401


# ============================== the assistant sees the hints ==============================


def test_the_assistant_plan_tool_carries_difficulty_and_hint(db):
    import json

    from app.ai import tools
    from app.models import RoadmapTopic
    from app.services import auth as auth_service
    from app.services import prefs, roadmap

    user = auth_service.create_first_user(db, email="a@example.com", password="correct-horse-9", display_name="Ada", timezone="Asia/Kolkata")
    roadmap.ensure_seeded(db, user)
    prefs.settings_row(db, user).focus_windows = focus.encode(["07:00-10:00"] * 7)
    first = db.query(RoadmapTopic).filter_by(user_id=user.id).order_by(RoadmapTopic.id).first()
    first.difficulty = "hard"
    db.commit()
    tool = tools.TOOLS["get_plan"]
    out = json.loads(json.dumps(tools.encode(tool.run(db, user, tool.args.model_validate({})))))
    topic = next(i for i in out["items"] if i["kind"] == "topic")
    assert topic["difficulty"] == "hard" and "07:00–10:00" in topic["hint"]
    assert out["summary"]["focus_window"] == "07:00-10:00"
