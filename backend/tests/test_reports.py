"""Weekly/monthly reports: built from real records only, in the user's own calendar days, nothing invented."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.models import CourseLesson, RoadmapTopic, Task, User

SETUP = {"email": "me@example.com", "password": "correct-horse-9", "display_name": "Me", "timezone": "Asia/Kolkata"}
TODAY = datetime.now(ZoneInfo("Asia/Kolkata")).date()
LAST_MON = TODAY - timedelta(days=TODAY.weekday() + 7)          # Monday of the previous (fully past) week
PREV_MON = LAST_MON - timedelta(days=7)
REPO = "https://github.com/me/rag-bot"


def utc(d: date, h: int, m: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, h, m, tzinfo=timezone.utc)


@pytest.fixture
def c(client):
    assert client.post("/api/auth/setup", json=SETUP).status_code == 201
    return client


def week(c, start: date) -> dict:
    r = c.get("/api/reports/weekly", params={"week_start": start.isoformat()})
    assert r.status_code == 200, r.text
    return r.json()


def done_task(c, db, when: datetime, title="T") -> None:
    t = c.post("/api/tasks", json={"title": title}).json()
    assert c.patch(f"/api/tasks/{t['id']}", json={"status": "completed"}).status_code == 200
    db.query(Task).filter(Task.id == t["id"]).update({"completed_at": when})
    db.commit()


def by_day(rep: dict, key: str) -> dict:
    return {d["date"]: d[key] for d in rep["days"]}


# ------------------------------ access and input ------------------------------


@pytest.mark.parametrize("path", ["/api/reports/weekly", "/api/reports/monthly"])
def test_login_is_required(client, path):
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("params", [{"month": "2026-13"}, {"month": "2026-1"}, {"month": "26-11"}, {"month": "november"}, {"month": "1999-12"}, {"month": "2101-01"}, {"month": "2026-11-01"}])
def test_a_bad_month_is_a_clean_422(c, params):
    r = c.get("/api/reports/monthly", params=params)
    assert r.status_code == 422 and "month" in r.json()["detail"].lower()


def test_a_bad_or_out_of_range_week_is_rejected(c):
    assert c.get("/api/reports/weekly", params={"week_start": "soon"}).status_code == 422
    assert c.get("/api/reports/weekly", params={"week_start": "1990-01-01"}).status_code == 422


# ------------------------------ periods ------------------------------


def test_any_day_in_a_week_gives_that_monday_to_sunday_week(c):
    for offset in range(7):
        p = week(c, LAST_MON + timedelta(days=offset))["period"]
        assert (p["start"], p["end"], p["days"], p["kind"]) == (LAST_MON.isoformat(), (LAST_MON + timedelta(days=6)).isoformat(), 7, "week")
        assert date.fromisoformat(p["start"]).weekday() == 0 and p["is_current"] is False and p["through"] == p["end"]


def test_the_current_week_is_flagged_and_stops_at_today(c):
    rep = c.get("/api/reports/weekly").json()
    p = rep["period"]
    assert p["is_current"] is True and p["through"] == TODAY.isoformat()
    future = [d for d in rep["days"] if d["date"] > TODAY.isoformat()]
    for d in future:                                                   # a day that hasn't happened shows nothing, not zeros pretending to be a result
        assert d["plan_total"] is None and d["plan_completed"] is None and d["items_done"] == 0 and d["study_minutes"] == 0
    assert all(d["plan_total"] is not None for d in rep["days"] if d["date"] <= TODAY.isoformat())


@pytest.mark.parametrize("month, days", [("2028-02", 29), ("2026-02", 28), ("2026-12", 31), ("2026-04", 30)])
def test_months_have_their_real_length(c, month, days):
    rep = c.get("/api/reports/monthly", params={"month": month}).json()
    assert (rep["period"]["days"], len(rep["days"]), rep["period"]["kind"]) == (days, days, "month")
    assert rep["period"]["start"] == f"{month}-01" and rep["period"]["end"] == f"{month}-{days:02d}"


def test_the_month_label_is_readable(c):
    assert c.get("/api/reports/monthly", params={"month": "2026-03"}).json()["period"]["label"] == "March 2026"


# ------------------------------ a new account ------------------------------


def test_a_new_account_reports_zeros_not_invented_numbers(c):
    rep = week(c, LAST_MON)
    zero = {"tasks_done": 0, "lessons_done": 0, "videos_done": 0, "topics_done": 0, "items_done": 0, "study_minutes": 0, "project_minutes": 0, "habits_done": 0, "challenge_days": 0}
    assert rep["totals"] == zero and rep["previous"] == zero
    assert rep["projects"] == [] and rep["habits"] == []
    assert rep["challenge"] == {"completed": 0, "verified": 0, "missed": 0, "excused": 0, "current_streak": 0}
    assert rep["plan"]["completed"] == 0 and rep["plan"]["percent"] in range(0, 101)


# ------------------------------ counting ------------------------------


def test_completed_tasks_are_counted_on_the_day_they_were_finished(c, db):
    done_task(c, db, utc(LAST_MON, 6))
    done_task(c, db, utc(LAST_MON, 7))
    done_task(c, db, utc(LAST_MON + timedelta(days=3), 6))
    rep = week(c, LAST_MON)
    per = by_day(rep, "tasks_done")
    assert per[LAST_MON.isoformat()] == 2 and per[(LAST_MON + timedelta(days=3)).isoformat()] == 1
    assert rep["totals"]["tasks_done"] == 3 and rep["totals"]["items_done"] == 3
    assert sum(per.values()) == 3                                      # nothing counted twice or on a stray day


def test_a_late_evening_in_utc_belongs_to_the_users_next_day(c, db):
    """19:30 UTC is 01:00 the next morning in Asia/Kolkata; 18:29 UTC is still 23:59 the same day."""
    done_task(c, db, utc(LAST_MON, 19, 30), "late")
    done_task(c, db, utc(LAST_MON, 18, 29), "not yet")
    per = by_day(week(c, LAST_MON), "tasks_done")
    assert per[LAST_MON.isoformat()] == 1 and per[(LAST_MON + timedelta(days=1)).isoformat()] == 1


def test_a_task_that_was_reopened_is_not_counted(c, db):
    done_task(c, db, utc(LAST_MON, 6))
    t = db.query(Task).one()
    c.patch(f"/api/tasks/{t.id}", json={"status": "pending"})
    assert week(c, LAST_MON)["totals"]["tasks_done"] == 0


def test_lessons_topics_and_study_time(c, db):
    course = c.post("/api/courses", json={"title": "Agentic AI"}).json()
    mod = c.post(f"/api/courses/{course['id']}/modules", json={"title": "Intro"}).json()
    lesson = c.post(f"/api/modules/{mod['modules'][0]['id']}/lessons", json={"title": "What is an agent?"}).json()
    lid = [x for m in lesson["modules"] for x in m["lessons"]][0]["id"]
    assert c.post(f"/api/lessons/{lid}/complete").status_code == 200
    db.query(CourseLesson).filter(CourseLesson.id == lid).update({"completed_at": utc(LAST_MON + timedelta(days=1), 5)})
    db.commit()                                                        # release the write lock before the API writes again
    topic = c.get("/api/roadmap").json()["stages"][0]["topics"][0]
    assert c.post(f"/api/roadmap/topics/{topic['id']}/status", json={"status": "completed"}).status_code == 200
    db.query(RoadmapTopic).filter(RoadmapTopic.id == topic["id"]).update({"completed_at": utc(LAST_MON + timedelta(days=2), 5)})
    db.commit()
    day3 = (LAST_MON + timedelta(days=3)).isoformat()
    assert c.post("/api/learning-sessions", json={"course_id": course["id"], "minutes": 40, "date": day3}).status_code == 201
    assert c.post("/api/learning-sessions", json={"course_id": course["id"], "minutes": 20, "date": day3}).status_code == 201
    rep = week(c, LAST_MON)
    assert rep["totals"]["lessons_done"] == 1 and rep["totals"]["topics_done"] == 1 and rep["totals"]["study_minutes"] == 60
    assert by_day(rep, "study_minutes")[day3] == 60 and by_day(rep, "lessons_done")[(LAST_MON + timedelta(days=1)).isoformat()] == 1
    assert rep["totals"]["items_done"] == 2


def test_videos_are_counted_when_finished(c, db):
    from app.models import Video

    pl = c.post("/api/video-playlists", json={"name": "ByteByteGo", "recommend_order": "manual"}).json()
    v = c.post(f"/api/video-playlists/{pl['id']}/videos", json={"title": "How SSH works"}).json()
    assert c.post(f"/api/videos/{v['id']}/complete").status_code == 200
    db.query(Video).filter(Video.id == v["id"]).update({"completed_at": utc(LAST_MON + timedelta(days=4), 5)})
    db.commit()
    rep = week(c, LAST_MON)
    assert rep["totals"]["videos_done"] == 1 and by_day(rep, "videos_done")[(LAST_MON + timedelta(days=4)).isoformat()] == 1


def test_project_time_is_summed_per_day_and_per_project_biggest_first(c):
    a = c.post("/api/projects", json={"title": "RAG chatbot"}).json()
    b = c.post("/api/projects", json={"title": "Agent toolkit"}).json()
    d1, d2 = (LAST_MON + timedelta(days=1)).isoformat(), (LAST_MON + timedelta(days=2)).isoformat()
    for pid, minutes, d in [(a["id"], 30, d1), (a["id"], 30, d2), (b["id"], 90, d1)]:
        assert c.post(f"/api/projects/{pid}/sessions", json={"minutes": minutes, "summary": "worked on it", "date": d}).status_code == 201
    rep = week(c, LAST_MON)
    assert rep["totals"]["project_minutes"] == 150 and by_day(rep, "project_minutes")[d1] == 120
    assert [(p["title"], p["minutes"]) for p in rep["projects"]] == [("Agent toolkit", 90), ("RAG chatbot", 60)]


def test_habit_check_ins_count_only_completed_days_in_the_period(c):
    h = c.post("/api/habits", json={"name": "Reading", "start_date": (LAST_MON - timedelta(days=30)).isoformat()}).json()
    for n, done in [(0, True), (1, True), (2, False), (9, True)]:                  # day 9 is in the NEXT week
        c.put(f"/api/habits/{h['id']}/logs/{(LAST_MON + timedelta(days=n)).isoformat()}", json={"completed": done})
    rep = week(c, LAST_MON)
    assert rep["totals"]["habits_done"] == 2 and rep["habits"] == [{"habit_id": h["id"], "name": "Reading", "done_days": 2}]


def test_the_challenge_block_counts_what_really_happened(c):
    p = c.post("/api/projects", json={"title": "RAG chatbot"}).json()
    day = TODAY.isoformat()
    ch = c.post("/api/challenges", json={"mode": "existing_project", "project_id": p["id"], "planned_task": "Add retrieval"}).json()
    ev = {"summary": "Implemented the retrieval step: chunking, embeddings and a top-k search.", "repo_url": REPO, "commit_sha": "a1b2c3d4e5f6",
          "commit_message": "Add retrieval", "minutes": 45}
    assert c.post(f"/api/challenges/{ch['id']}/complete", json=ev).status_code == 200
    rep = c.get("/api/reports/weekly", params={"week_start": day}).json()
    assert rep["challenge"]["completed"] == 1 and rep["challenge"]["verified"] == 0          # self-reported evidence is never called verified
    assert rep["challenge"]["current_streak"] == 1 and rep["totals"]["challenge_days"] == 1
    assert by_day(rep, "challenge")[day] == "completed"


# ------------------------------ comparison and isolation ------------------------------


def test_the_comparison_is_the_previous_period_like_for_like(c, db):
    done_task(c, db, utc(PREV_MON, 6))
    done_task(c, db, utc(PREV_MON + timedelta(days=2), 6))
    done_task(c, db, utc(LAST_MON, 6))
    rep = week(c, LAST_MON)
    assert rep["totals"]["tasks_done"] == 1 and rep["previous"]["tasks_done"] == 2


def test_an_unfinished_week_is_compared_with_the_same_number_of_days_before(c, db):
    """If only N days of this week have happened, last week's first N days are the fair comparison, not its whole week."""
    this_mon = TODAY - timedelta(days=TODAY.weekday())
    last_mon = this_mon - timedelta(days=7)
    done_task(c, db, utc(last_mon, 6), "inside the window")
    done_task(c, db, utc(last_mon + timedelta(days=6), 6), "sunday, after the window unless today is Sunday")
    rep = c.get("/api/reports/weekly").json()
    elapsed = TODAY.weekday() + 1
    assert rep["previous"]["tasks_done"] == (2 if elapsed == 7 else 1)


def test_other_users_records_never_appear(c, db):
    done_task(c, db, utc(LAST_MON, 6), "mine")
    db.add(User(id=2, email="o@example.com", password_hash="x", display_name="O", timezone="UTC"))
    db.commit()
    db.add(Task(user_id=2, title="theirs", status="completed", completed_at=utc(LAST_MON, 6)))
    db.commit()
    assert week(c, LAST_MON)["totals"]["tasks_done"] == 1


def test_the_report_agrees_with_the_planner_for_each_day(c):
    """The plan figures are the planner's own numbers, so the report can't disagree with the Daily planner page."""
    rep = week(c, LAST_MON)
    for d in rep["days"][:3]:
        plan = c.get("/api/planner", params={"date": d["date"]}).json()["summary"]
        assert (d["plan_total"], d["plan_completed"]) == (plan["total"], plan["completed"])


def test_a_month_report_builds_in_reasonable_time(c):
    import time

    t = time.time()
    assert c.get("/api/reports/monthly", params={"month": LAST_MON.strftime("%Y-%m")}).status_code == 200
    assert time.time() - t < 5


def test_the_assistant_can_read_the_same_report(c, db):
    import json

    from app.services import assistant as svc

    done_task(c, db, utc(LAST_MON, 6))
    user = db.get(User, 1)
    text, is_error = svc._run_tool(db, user, "get_weekly_report", {"day": (LAST_MON + timedelta(days=2)).isoformat()})
    out = json.loads(text)
    assert not is_error and out["totals"]["tasks_done"] == 1 and len(out["per_day"]) == 7
    assert out["totals"] == week(c, LAST_MON)["totals"]                              # the chat and the Reports page can't disagree
    assert svc._run_tool(db, user, "get_weekly_report", {"day": "2026-11-01", "user_id": 2})[1] is True   # no extra arguments
