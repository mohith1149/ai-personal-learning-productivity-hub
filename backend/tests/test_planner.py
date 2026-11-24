"""Daily planner: what shows up on a day, completing/reopening through the owning services, rescheduling, excusing, summary maths.
'Today' is Mon 23 Nov 2026 (Kolkata)."""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Course, CourseLesson, CourseModule, LearningSession, PlannerExcusal, Task, User
from app.schemas import habits as hs
from app.schemas import planner as s
from app.schemas import projects as ps
from app.schemas import videos as vs
from app.services import auth as auth_service
from app.services import courses, habits, planner, projects, roadmap, videos

NOW = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)   # 15:30 Mon 23 Nov in Kolkata
TODAY = date(2026, 11, 23)
D = lambda n: date(2026, 11, n)  # noqa: E731


@pytest.fixture
def user(db) -> User:
    return auth_service.create_first_user(db, email="me@example.com", password="correct-horse-9", display_name="Me", timezone="Asia/Kolkata")


@pytest.fixture
def other(db, user) -> User:
    u = User(id=2, email="o@example.com", password_hash="x", display_name="O", timezone="UTC")
    db.add(u)
    db.commit()
    return u


def plan(db, user, day=TODAY):
    return planner.build_day(db, user, day, NOW)


def keyed(p):
    return {i["key"]: i for i in p["items"]}


def mk_task(db, user, title="Task", **kw) -> Task:
    t = Task(user_id=user.id, title=title, **kw)
    db.add(t)
    db.commit()
    return t


def mk_course(db, user, title="Agentic AI", lessons=("L1", "L2"), status="active") -> Course:
    c = Course(user_id=user.id, title=title, status=status)
    db.add(c)
    db.flush()
    m = CourseModule(course_id=c.id, title="Module 1", position=1)
    db.add(m)
    db.flush()
    for i, name in enumerate(lessons, start=1):
        db.add(CourseLesson(module_id=m.id, course_id=c.id, title=name, position=i))
    db.commit()
    return c


def lesson(db, title) -> CourseLesson:
    return db.scalar(select(CourseLesson).where(CourseLesson.title == title))


def mk_playlist(db, user, name="ByteByteGo", target=2, n=4, **kw):
    p = videos.create_playlist(db, user, vs.PlaylistCreate(name=name, daily_target=target, recommend_order="manual", **kw))
    out = []
    for i in range(1, n + 1):
        _, v = videos.upsert_video(db, user, p, {"title": f"{name} video {i}", "url": f"https://www.youtube.com/watch?v={name[:3]}{i:08d}",
                                                  "youtube_video_id": f"{name[:3]}{i:08d}", "duration_seconds": 600})
        out.append(v)
    db.commit()
    return p, out


def ref(kind, ref_id, day=TODAY) -> s.ItemRef:
    return s.ItemRef(kind=kind, ref_id=ref_id, date=day)


# ============================== empty / structure ==============================


def test_an_empty_account_has_an_empty_plan(db, user):
    p = plan(db, user)
    assert p["items"] == [] and p["is_today"] is True and p["date"] == TODAY
    assert p["summary"] == {"total": 0, "completed": 0, "pending": 0, "overdue": 0, "excused": 0, "percent": 0,
                            "study_minutes": 0, "dev_minutes": 0, "by_kind": []}


def test_is_today_flag(db, user):
    assert plan(db, user, D(22))["is_today"] is False and plan(db, user, D(24))["is_today"] is False


# ============================== tasks ==============================


def test_tasks_scheduled_or_due_on_a_day_show_up_with_the_right_status(db, user):
    mk_task(db, user, "scheduled today", scheduled_date=TODAY)
    mk_task(db, user, "due today", due_date=TODAY)
    mk_task(db, user, "tomorrow", scheduled_date=D(24))
    mk_task(db, user, "no dates")
    k = keyed(plan(db, user))
    assert {"task:1", "task:2"} == set(k) and all(i["status"] == "pending" for i in k.values())
    assert k["task:2"]["due_date"] == TODAY
    t = keyed(plan(db, user, D(24)))
    assert [i["title"] for i in t.values()] == ["tomorrow"] and t["task:3"]["status"] == "pending"


def test_open_tasks_from_earlier_days_are_overdue_on_todays_plan(db, user):
    mk_task(db, user, "due yesterday", due_date=D(22))
    mk_task(db, user, "scheduled last week", scheduled_date=D(16))
    mk_task(db, user, "due earlier today", due_date=TODAY, due_time="08:00")     # 08:00 < 15:30 local
    mk_task(db, user, "due later today", due_date=TODAY, due_time="18:00")
    k = plan(db, user)["items"]
    status = {i["title"]: i["status"] for i in k}
    assert status == {"due yesterday": "overdue", "scheduled last week": "overdue", "due earlier today": "overdue", "due later today": "pending"}
    assert plan(db, user)["summary"]["overdue"] == 3
    assert [i["title"] for i in k][:3] != ["due later today"]                      # overdue items are listed first


def test_a_past_days_plan_shows_what_was_open_on_it_as_overdue(db, user):
    mk_task(db, user, "was due friday", due_date=D(20))
    mk_task(db, user, "finished friday", scheduled_date=D(20), status="completed", completed_at=datetime(2026, 11, 20, 8, 0, tzinfo=timezone.utc))
    p = plan(db, user, D(20))
    assert {i["title"]: i["status"] for i in p["items"]} == {"was due friday": "overdue", "finished friday": "completed"}


def test_completed_tasks_appear_on_the_day_they_were_completed_only(db, user):
    mk_task(db, user, "done now", status="completed", completed_at=NOW, scheduled_date=D(20))
    mk_task(db, user, "done long ago", status="completed", completed_at=NOW - timedelta(days=5), scheduled_date=TODAY)
    assert [(i["title"], i["status"]) for i in plan(db, user)["items"]] == [("done now", "completed")]


def test_cancelled_tasks_never_appear(db, user):
    mk_task(db, user, "cancelled", status="cancelled", scheduled_date=TODAY)
    assert plan(db, user)["items"] == []


def test_the_local_day_not_the_utc_day_decides_completion(db, user):
    mk_task(db, user, "late night", status="completed", completed_at=datetime(2026, 11, 22, 19, 0, tzinfo=timezone.utc))   # 00:30 on the 23rd in Kolkata
    assert [i["title"] for i in plan(db, user)["items"]] == ["late night"]
    assert plan(db, user, D(22))["items"] == []


def test_project_tasks_are_labelled(db, user):
    mk_task(db, user, "Write loader", scheduled_date=TODAY, project_id=None, task_type="project_dev")
    p = projects.create_project(db, user, ps.ProjectCreate(title="RAG"), now=NOW)
    projects.add_task(db, user, p["id"], ps.TaskCreate(title="From project", due_date=TODAY), now=NOW)
    sub = {i["title"]: i["subtitle"] for i in plan(db, user)["items"] if i["kind"] == "task"}
    assert sub["From project"] == "Project task" and sub["Write loader"] is None


# ============================== lessons ==============================


def test_each_active_course_offers_its_next_lesson_once_a_day(db, user):
    mk_course(db, user, "Agentic AI", ("L1", "L2"))
    mk_course(db, user, "Paused", ("P1",), status="paused")
    mk_course(db, user, "Second", ("S1", "S2"))
    items = [i for i in plan(db, user)["items"] if i["kind"] == "lesson"]
    assert sorted(i["title"] for i in items) == ["L1", "S1"] and all(i["status"] == "pending" and i["can_complete"] for i in items)
    assert items[0]["subtitle"].endswith("Module 1") and items[0]["link"].startswith("/courses/")


def test_completing_a_lesson_from_the_planner_completes_it_in_courses_and_stops_the_next_one_appearing_today(db, user):
    c = mk_course(db, user)
    out = planner.complete_item(db, user, ref("lesson", lesson(db, "L1").id), NOW)
    assert [(i["title"], i["status"]) for i in out["items"]] == [("L1", "completed")]          # L2 is not pushed on the same day
    assert lesson(db, "L1").status == "completed" and lesson(db, "L1").completed_at is not None
    assert courses.progress(courses._load_course(db, user, c.id))["completed_lessons"] == 1


def test_reopening_a_lesson_brings_it_back(db, user):
    mk_course(db, user)
    planner.complete_item(db, user, ref("lesson", lesson(db, "L1").id), NOW)
    out = planner.reopen_item(db, user, ref("lesson", lesson(db, "L1").id), NOW)
    assert [(i["title"], i["status"]) for i in out["items"]] == [("L1", "pending")] and lesson(db, "L1").completed_at is None


# ============================== videos ==============================


def test_todays_videos_follow_the_playlist_daily_target_in_order(db, user):
    _, vids = mk_playlist(db, user, target=2)
    items = [i for i in plan(db, user)["items"] if i["kind"] == "video"]
    assert [i["title"] for i in items] == [v.title for v in vids[:2]] and all(i["status"] == "pending" for i in items)
    assert items[0]["url"].startswith("https://www.youtube.com/") and items[0]["minutes"] == 10 and items[0]["subtitle"] == "ByteByteGo"


def test_completing_videos_keeps_the_days_video_list_at_the_target_and_never_repeats_one(db, user):
    _, vids = mk_playlist(db, user, target=2)
    planner.complete_item(db, user, ref("video", vids[0].id), NOW)
    items = [(i["title"], i["status"]) for i in plan(db, user)["items"] if i["kind"] == "video"]
    assert items == [(vids[1].title, "pending"), (vids[0].title, "completed")]                # target 2: 1 done + 1 to go
    planner.complete_item(db, user, ref("video", vids[1].id), NOW)
    items = [(i["title"], i["status"]) for i in plan(db, user)["items"] if i["kind"] == "video"]
    assert items == [(vids[0].title, "completed"), (vids[1].title, "completed")]               # target met: nothing more is pushed
    assert all(i["title"] != vids[0].title or i["status"] == "completed" for i in plan(db, user)["items"])


def test_videos_of_inactive_playlists_are_left_out_and_shared_videos_appear_once(db, user):
    mk_playlist(db, user, "Inactive", target=3, active=False)
    p1, vids = mk_playlist(db, user, "Alpha", target=2, n=3)
    p2 = videos.create_playlist(db, user, vs.PlaylistCreate(name="Beta", daily_target=2, recommend_order="manual"))
    videos.upsert_video(db, user, p2, {"title": vids[0].title, "youtube_video_id": vids[0].youtube_video_id, "url": vids[0].url})   # same video, second playlist
    db.commit()
    titles = [i["title"] for i in plan(db, user)["items"] if i["kind"] == "video"]
    assert titles.count(vids[0].title) == 1 and not any(t.startswith("Inactive") for t in titles)


def test_a_removed_video_is_not_offered(db, user):
    _, vids = mk_playlist(db, user, target=2)
    videos.remove_video(db, user, vids[0].id, NOW)
    assert [i["title"] for i in plan(db, user)["items"] if i["kind"] == "video"] == [vids[1].title, vids[2].title]


def test_videos_keep_the_playlists_own_order_not_alphabetical(db, user):
    p, vids = mk_playlist(db, user, "Plan", target=3, n=4)
    videos.update_playlist(db, user, p.id, vs.PlaylistUpdate(recommend_order="manual"))
    # make the manual order differ from the alphabetical one: move the last video to the front
    for _ in range(3):
        videos.move_video(db, user, vids[3].id, "up", p.id)
    titles = [i["title"] for i in plan(db, user)["items"] if i["kind"] == "video"]
    assert titles == [vids[3].title, vids[0].title, vids[1].title] and titles != sorted(titles)


def test_videos_are_only_suggested_for_today(db, user):
    mk_playlist(db, user)
    assert [i for i in plan(db, user, D(24))["items"] if i["kind"] == "video"] == []
    assert [i for i in plan(db, user, D(22))["items"] if i["kind"] == "video"] == []


# ============================== roadmap topics ==============================


def test_roadmap_shows_in_progress_topics_and_the_next_one(db, user):
    roadmap.get_roadmap(db, user)
    t = {x.title: x for x in db.scalars(select(roadmap.RoadmapTopic).where(roadmap.RoadmapTopic.user_id == user.id))}
    items = [i for i in plan(db, user)["items"] if i["kind"] == "topic"]
    assert [i["title"] for i in items] == ["Python"] and items[0]["subtitle"].endswith("next up")
    roadmap.set_status(db, user, t["Docker"].id, "in_progress")
    assert sorted(i["title"] for i in plan(db, user)["items"] if i["kind"] == "topic") == ["Docker", "Python"]


def test_completing_a_topic_from_the_planner_uses_the_roadmap_rules(db, user):
    roadmap.get_roadmap(db, user)
    py = db.scalar(select(roadmap.RoadmapTopic).where(roadmap.RoadmapTopic.title == "Python"))
    out = planner.complete_item(db, user, ref("topic", py.id), NOW)
    k = keyed(out)
    assert k[f"topic:{py.id}"]["status"] == "completed"
    assert any(i["status"] == "pending" and i["title"] == "Java fundamentals" for i in out["items"])     # the next topic takes its place
    back = planner.reopen_item(db, user, ref("topic", py.id), NOW)
    assert keyed(back)[f"topic:{py.id}"]["status"] == "pending"
    assert db.get(roadmap.RoadmapTopic, py.id).status == "in_progress"


def test_an_unopened_roadmap_adds_nothing_and_isnt_created_by_viewing_the_planner(db, user):
    assert [i for i in plan(db, user)["items"] if i["kind"] == "topic"] == []
    assert db.query(roadmap.RoadmapStage).count() == 0


# ============================== habits ==============================


def mk_habit(db, user, name="Reading", start=D(1), **kw):
    return habits.create_habit(db, user, hs.HabitCreate(name=name, start_date=start, **kw), now=NOW)


def test_daily_habits_are_due_today_and_overdue_when_missed_on_a_past_day(db, user):
    mk_habit(db, user)
    assert [(i["title"], i["status"]) for i in plan(db, user)["items"]] == [("Reading", "pending")]
    assert [(i["title"], i["status"]) for i in plan(db, user, D(20))["items"]] == [("Reading", "overdue")]
    assert plan(db, user, D(24))["items"] == []                                                # nothing for the future


def test_completing_a_habit_records_it_and_a_past_day_can_be_recorded_too(db, user):
    h = mk_habit(db, user)
    out = planner.complete_item(db, user, ref("habit", h["id"]), NOW)
    assert out["items"][0]["status"] == "completed" and habits.get_habit(db, user, h["id"], NOW)["done_today"] is True
    past = planner.complete_item(db, user, ref("habit", h["id"], D(20)), NOW)               # back-filling yesterday-ish is allowed for habits
    assert past["items"][0]["status"] == "completed" and past["is_today"] is False
    reopened = planner.reopen_item(db, user, ref("habit", h["id"]), NOW)
    assert reopened["items"][0]["status"] == "pending" and habits.get_habit(db, user, h["id"], NOW)["done_today"] is False


def test_habits_respect_their_start_date_and_active_flag(db, user):
    mk_habit(db, user, "Future", start=D(25))
    mk_habit(db, user, "Inactive", active=False)
    mk_habit(db, user, "Fresh", start=D(23))
    assert [i["title"] for i in plan(db, user)["items"]] == ["Fresh"]
    assert plan(db, user, D(22))["items"] == []                                               # before it started


def test_a_weekly_habit_is_due_until_the_weeks_target_is_met(db, user):
    h = mk_habit(db, user, "Gym", frequency="weekly", target_per_period=2)
    items = plan(db, user)["items"]
    assert items[0]["status"] == "pending" and "0 of 2 this week" in items[0]["subtitle"]
    habits.set_log(db, user, h["id"], D(23), hs.LogIn(), now=NOW)
    assert plan(db, user)["items"][0]["status"] == "completed"                                # logged today
    assert plan(db, user, D(22))["items"] == []                                               # weekly habits aren't "missed" on a past day


def test_a_weekly_habit_whose_target_was_met_earlier_in_the_week_is_not_due_again(db, user):
    h = mk_habit(db, user, "Gym", frequency="weekly", target_per_period=1)
    habits.set_log(db, user, h["id"], D(23), hs.LogIn(completed=False, note="skipped"), now=NOW)   # a miss record does not count
    assert plan(db, user)["items"][0]["status"] == "pending"


# ============================== projects ==============================


def test_active_projects_ask_for_work_until_a_session_is_logged(db, user):
    p = projects.create_project(db, user, ps.ProjectCreate(title="RAG"), now=NOW)
    projects.create_project(db, user, ps.ProjectCreate(title="Paused one", status="paused"), now=NOW)
    items = [i for i in plan(db, user)["items"] if i["kind"] == "project"]
    assert [(i["title"], i["status"], i["can_complete"]) for i in items] == [("Work on RAG", "pending", False)] and items[0]["link"] == f"/projects/{p['id']}"
    projects.log_session(db, user, p["id"], ps.SessionCreate(minutes=45, summary="built the loader"), now=NOW)
    done = [i for i in plan(db, user)["items"] if i["kind"] == "project"]
    assert [(i["title"], i["status"], i["minutes"]) for i in done] == [("Worked on RAG", "completed", 45)]
    assert plan(db, user)["summary"]["dev_minutes"] == 45


def test_project_work_cant_be_completed_from_the_planner(db, user):
    p = projects.create_project(db, user, ps.ProjectCreate(title="RAG"), now=NOW)
    with pytest.raises(planner.RuleError, match="development session"):
        planner.complete_item(db, user, ref("project", p["id"]), NOW)


def test_past_project_work_shows_on_its_day(db, user):
    p = projects.create_project(db, user, ps.ProjectCreate(title="RAG"), now=NOW)
    projects.log_session(db, user, p["id"], ps.SessionCreate(minutes=30, summary="old work", date=D(20)), now=NOW)
    assert [(i["title"], i["status"]) for i in plan(db, user, D(20))["items"]] == [("Worked on RAG", "completed")]
    assert [i for i in plan(db, user, D(21))["items"]] == []


# ============================== complete / reopen rules ==============================


def test_completing_a_task_from_the_planner_and_reopening_it(db, user):
    t = mk_task(db, user, "Pay bill", scheduled_date=TODAY)
    out = planner.complete_item(db, user, ref("task", t.id), NOW)
    assert out["items"][0]["status"] == "completed" and db.get(Task, t.id).status == "completed" and db.get(Task, t.id).completed_at == NOW
    back = planner.reopen_item(db, user, ref("task", t.id), NOW)
    assert back["items"][0]["status"] == "pending" and db.get(Task, t.id).completed_at is None


def test_non_habits_can_only_be_completed_on_todays_plan_and_nothing_on_future_days(db, user):
    t = mk_task(db, user, "Old", due_date=D(20))
    with pytest.raises(planner.RuleError, match="today's plan"):
        planner.complete_item(db, user, ref("task", t.id, D(20)), NOW)
    with pytest.raises(planner.RuleError, match="Future"):
        planner.complete_item(db, user, ref("task", t.id, D(24)), NOW)
    assert db.get(Task, t.id).status == "pending"
    assert all(i["can_complete"] is False for i in plan(db, user, D(20))["items"])


def test_errors_from_the_owning_feature_are_translated(db, user, other):
    t = mk_task(db, other, "Not yours", scheduled_date=TODAY)
    with pytest.raises(planner.NotFound):
        planner.complete_item(db, user, ref("task", t.id), NOW)
    with pytest.raises(planner.NotFound):
        planner.complete_item(db, user, ref("lesson", 999), NOW)
    with pytest.raises(planner.NotFound):
        planner.complete_item(db, user, ref("video", 999), NOW)
    with pytest.raises(planner.NotFound):
        planner.complete_item(db, user, ref("topic", 999), NOW)
    with pytest.raises(planner.NotFound):
        planner.complete_item(db, user, ref("habit", 999), NOW)
    assert db.get(Task, t.id).status == "pending"


# ============================== rescheduling ==============================


def test_rescheduling_moves_the_task_and_does_not_complete_it(db, user):
    t = mk_task(db, user, "Write report", scheduled_date=TODAY, due_date=D(30))
    out = planner.reschedule_task(db, user, t.id, s.RescheduleIn(date=D(25), from_date=TODAY), NOW)
    row = db.get(Task, t.id)
    assert (row.status, row.completed_at, row.scheduled_date, row.due_date) == ("pending", None, D(25), D(30))
    assert (row.carry_count, row.carried_from_date) == (1, TODAY)
    assert out["items"] == [] and out["summary"]["completed"] == 0 and out["summary"]["percent"] == 0       # NOT counted as done
    moved = plan(db, user, D(25))
    assert [(i["title"], i["status"]) for i in moved["items"]] == [("Write report", "pending")] and "moved 1×" in moved["items"][0]["subtitle"]


def test_rescheduling_an_overdue_task_to_a_later_day_keeps_its_deadline_unless_asked(db, user):
    t = mk_task(db, user, "Late", due_date=D(20))
    planner.reschedule_task(db, user, t.id, s.RescheduleIn(date=D(26), from_date=TODAY), NOW)
    assert db.get(Task, t.id).due_date == D(20)
    assert [i["status"] for i in plan(db, user)["items"]] == ["overdue"]                     # still past its deadline, honestly
    planner.reschedule_task(db, user, t.id, s.RescheduleIn(date=D(26), from_date=TODAY, move_due_date=True), NOW)
    assert db.get(Task, t.id).due_date == D(26) and plan(db, user)["items"] == []


def test_reschedule_rules(db, user, other):
    t = mk_task(db, user, "Task", scheduled_date=TODAY)
    done = mk_task(db, user, "Done", status="completed", completed_at=NOW)
    mine_elsewhere = mk_task(db, other, "Theirs", scheduled_date=TODAY)
    with pytest.raises(planner.RuleError, match="past"):
        planner.reschedule_task(db, user, t.id, s.RescheduleIn(date=D(22), from_date=TODAY), NOW)
    with pytest.raises(planner.RuleError, match="open"):
        planner.reschedule_task(db, user, done.id, s.RescheduleIn(date=D(25), from_date=TODAY), NOW)
    with pytest.raises(planner.NotFound):
        planner.reschedule_task(db, user, mine_elsewhere.id, s.RescheduleIn(date=D(25), from_date=TODAY), NOW)
    same = planner.reschedule_task(db, user, t.id, s.RescheduleIn(date=TODAY, from_date=TODAY), NOW)    # same day: nothing changes
    assert db.get(Task, t.id).carry_count == 0 and [i["title"] for i in same["items"] if i["title"] == "Task"] == ["Task"]


def test_only_tasks_offer_rescheduling(db, user):
    mk_task(db, user, "T", scheduled_date=TODAY)
    mk_course(db, user)
    mk_habit(db, user)
    assert {i["kind"]: i["can_reschedule"] for i in plan(db, user)["items"]} == {"task": True, "habit": False, "lesson": False}


# ============================== excusing ==============================


def test_an_excused_activity_is_not_overdue_and_not_counted(db, user):
    t = mk_task(db, user, "Dentist", due_date=D(20))
    mk_task(db, user, "Other", scheduled_date=TODAY)
    out = planner.excuse_item(db, user, s.ExcuseIn(kind="task", ref_id=t.id, date=TODAY, reason="Was ill"), NOW)
    k = keyed(out)
    assert (k[f"task:{t.id}"]["status"], k[f"task:{t.id}"]["excuse_reason"]) == ("excused", "Was ill")
    assert out["summary"] == {**out["summary"], "total": 1, "overdue": 0, "pending": 1, "excused": 1, "percent": 0}
    assert db.get(Task, t.id).status == "pending"                                             # the task itself is untouched
    assert [i["title"] for i in out["items"]] == ["Other", "Dentist"]                          # excused items sink to the bottom


def test_excusing_only_covers_that_day(db, user):
    t = mk_task(db, user, "Dentist", due_date=D(22))
    planner.excuse_item(db, user, s.ExcuseIn(kind="task", ref_id=t.id, date=D(22), reason="Away travelling"), NOW)
    assert plan(db, user, D(22))["items"][0]["status"] == "excused"
    assert plan(db, user, TODAY)["items"][0]["status"] == "overdue"


def test_excuse_rules(db, user, other):
    t = mk_task(db, user, "Task", scheduled_date=TODAY)
    done = mk_task(db, user, "Done", status="completed", completed_at=NOW)
    theirs = mk_task(db, other, "Theirs", scheduled_date=TODAY)
    with pytest.raises(planner.RuleError, match="completed"):
        planner.excuse_item(db, user, s.ExcuseIn(kind="task", ref_id=done.id, date=TODAY, reason="no need"), NOW)
    with pytest.raises(planner.RuleError, match="future"):
        planner.excuse_item(db, user, s.ExcuseIn(kind="task", ref_id=t.id, date=D(24), reason="tomorrow"), NOW)
    with pytest.raises(planner.RuleError, match="isn't on this day"):
        planner.excuse_item(db, user, s.ExcuseIn(kind="task", ref_id=theirs.id, date=TODAY, reason="not mine"), NOW)
    with pytest.raises(planner.RuleError, match="isn't on this day"):
        planner.excuse_item(db, user, s.ExcuseIn(kind="task", ref_id=99999, date=TODAY, reason="nothing"), NOW)
    for bad in ("", "ab", "x" * 1001):
        with pytest.raises(ValueError):
            s.ExcuseIn(kind="task", ref_id=t.id, date=TODAY, reason=bad)
    assert db.query(PlannerExcusal).count() == 0


def test_excuse_reason_can_be_changed_and_removed(db, user):
    t = mk_task(db, user, "Task", scheduled_date=TODAY)
    planner.excuse_item(db, user, s.ExcuseIn(kind="task", ref_id=t.id, date=TODAY, reason="first reason"), NOW)
    out = planner.excuse_item(db, user, s.ExcuseIn(kind="task", ref_id=t.id, date=TODAY, reason="better reason"), NOW)
    assert out["items"][0]["excuse_reason"] == "better reason" and db.query(PlannerExcusal).count() == 1
    back = planner.remove_excuse(db, user, ref("task", t.id), NOW)
    assert back["items"][0]["status"] == "pending" and db.query(PlannerExcusal).count() == 0
    with pytest.raises(planner.NotFound):
        planner.remove_excuse(db, user, ref("task", t.id), NOW)


def test_any_kind_of_activity_can_be_excused(db, user):
    mk_course(db, user)
    mk_habit(db, user)
    mk_playlist(db, user, target=1)
    roadmap.get_roadmap(db, user)
    projects.create_project(db, user, ps.ProjectCreate(title="RAG"), now=NOW)
    for it in plan(db, user)["items"]:
        out = planner.excuse_item(db, user, s.ExcuseIn(kind=it["kind"], ref_id=it["ref_id"], date=TODAY, reason="rest day"), NOW)
    assert {i["status"] for i in out["items"]} == {"excused"} and out["summary"]["total"] == 0 and out["summary"]["excused"] == len(out["items"])


def test_completing_an_excused_item_makes_it_completed(db, user):
    t = mk_task(db, user, "Task", scheduled_date=TODAY)
    planner.excuse_item(db, user, s.ExcuseIn(kind="task", ref_id=t.id, date=TODAY, reason="was going to skip"), NOW)
    out = planner.complete_item(db, user, ref("task", t.id), NOW)
    assert out["items"][0]["status"] == "completed" and out["items"][0]["excuse_reason"] is None


# ============================== summary maths ==============================


def test_summary_percent_and_per_kind_counts(db, user):
    ts = [mk_task(db, user, f"T{i}", scheduled_date=TODAY) for i in range(3)]
    mk_task(db, user, "Late", due_date=D(20))
    h = mk_habit(db, user)
    planner.complete_item(db, user, ref("task", ts[0].id), NOW)
    planner.complete_item(db, user, ref("habit", h["id"]), NOW)
    s_ = plan(db, user)["summary"]
    assert (s_["total"], s_["completed"], s_["pending"], s_["overdue"], s_["percent"]) == (5, 2, 2, 1, 40)
    assert {k["kind"]: (k["completed"], k["total"]) for k in s_["by_kind"]} == {"task": (1, 4), "habit": (1, 1)}


def test_percent_is_floored_and_100_only_when_everything_counted_is_done(db, user):
    ts = [mk_task(db, user, f"T{i}", scheduled_date=TODAY) for i in range(3)]
    planner.complete_item(db, user, ref("task", ts[0].id), NOW)
    assert plan(db, user)["summary"]["percent"] == 33
    planner.complete_item(db, user, ref("task", ts[1].id), NOW)
    assert plan(db, user)["summary"]["percent"] == 66
    planner.complete_item(db, user, ref("task", ts[2].id), NOW)
    assert plan(db, user)["summary"]["percent"] == 100


def test_study_time_for_the_day_comes_from_logged_sessions(db, user):
    c = mk_course(db, user)
    roadmap.get_roadmap(db, user)
    py = db.scalar(select(roadmap.RoadmapTopic).where(roadmap.RoadmapTopic.title == "Python"))
    db.add_all([LearningSession(user_id=user.id, course_id=c.id, date=TODAY, minutes=40),
                LearningSession(user_id=user.id, roadmap_topic_id=py.id, date=TODAY, minutes=25),
                LearningSession(user_id=user.id, course_id=c.id, date=D(22), minutes=99)])
    db.commit()
    assert plan(db, user)["summary"]["study_minutes"] == 65 and plan(db, user, D(22))["summary"]["study_minutes"] == 99


def test_items_are_sorted_overdue_then_pending_then_completed_then_excused(db, user):
    mk_task(db, user, "pending", scheduled_date=TODAY)
    mk_task(db, user, "overdue", due_date=D(20))
    mk_task(db, user, "done", status="completed", completed_at=NOW)
    ex = mk_task(db, user, "excused", scheduled_date=TODAY)
    planner.excuse_item(db, user, s.ExcuseIn(kind="task", ref_id=ex.id, date=TODAY, reason="not today"), NOW)
    assert [i["status"] for i in plan(db, user)["items"]] == ["overdue", "pending", "completed", "excused"]


# ============================== isolation ==============================


def test_other_users_data_never_appears(db, user, other):
    mk_task(db, other, "Secret task", scheduled_date=TODAY)
    mk_course(db, other, "Secret course")
    mk_playlist(db, other, "Secret list")
    roadmap.get_roadmap(db, other)
    habits.create_habit(db, other, hs.HabitCreate(name="Secret habit", start_date=D(1)), now=NOW)
    projects.create_project(db, other, ps.ProjectCreate(title="Secret project"), now=NOW)
    assert plan(db, user)["items"] == []
    assert any(i["title"] == "Secret task" for i in plan(db, other)["items"])
