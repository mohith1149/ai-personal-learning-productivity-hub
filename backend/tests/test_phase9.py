"""Phase 9: planned rest days, the daily-hours overload flag, rolling unfinished tasks to tomorrow, and slipping tasks.
'Today' is Mon 23 Nov 2026 (Kolkata)."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models import Task, User
from app.schemas import challenges as cs
from app.schemas import planner as s
from app.schemas import projects as ps
from app.services import auth as auth_service
from app.services import challenges, planner, prefs, projects, rest

NOW = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)   # 15:30 Mon 23 Nov in Kolkata
TODAY = date(2026, 11, 23)  # a Monday


def d(n: int) -> date:
    return TODAY + timedelta(days=n)


@pytest.fixture
def user(db) -> User:
    return auth_service.create_first_user(db, email="me@example.com", password="correct-horse-9", display_name="Me", timezone="Asia/Kolkata")


def mk_task(db, user, title="Task", **kw) -> Task:
    t = Task(user_id=user.id, title=title, **kw)
    db.add(t)
    db.commit()
    return t


def plan(db, user, day=TODAY):
    return planner.build_day(db, user, day, NOW)


def set_week(db, user, minutes):
    prefs.settings_row(db, user).weekday_minutes = prefs.encode(minutes)
    db.commit()


def finish_day(db, user, pid, n):
    """Complete the challenge for the day n days from today (n <= 0), with its own commit."""
    when = NOW + timedelta(days=n)
    c = challenges.create_challenge(db, user, cs.ChallengeCreate(mode="existing_project", project_id=pid, planned_task="Add the retrieval step"), now=when)
    return challenges.complete_challenge(db, user, c["id"], cs.CompleteIn(
        summary="Implemented the retrieval step: chunking, embeddings and a top-k search over the vector store.",
        repo_url="https://github.com/me/rag-bot", commit_sha=f"a1b2c3d4e5{abs(n):02d}", commit_message="Add retrieval step to RAG pipeline", minutes=90), now=when)


# ============================== rest days ==============================


def test_a_rest_day_can_be_set_and_removed(db, user):
    out = rest.add(db, user, TODAY, "Fever", NOW)
    assert out["used"] == 1 and out["cap"] == 4 and out["left"] == 3 and out["days"][0]["reason"] == "Fever"
    assert rest.remove(db, user, TODAY)["used"] == 0
    with pytest.raises(rest.NotFound):
        rest.remove(db, user, TODAY)


def test_the_monthly_limit_is_enforced_per_calendar_month(db, user):
    prefs.settings_row(db, user).rest_days_per_month = 2
    db.commit()
    rest.add(db, user, d(1), None, NOW)
    rest.add(db, user, d(2), None, NOW)
    with pytest.raises(rest.RuleError, match="all 2 rest days for November"):
        rest.add(db, user, d(3), None, NOW)
    assert rest.add(db, user, date(2026, 12, 5), None, NOW)["month"] == "2026-12"   # December has its own allowance


def test_a_zero_limit_turns_rest_days_off(db, user):
    prefs.settings_row(db, user).rest_days_per_month = 0
    db.commit()
    with pytest.raises(rest.RuleError):
        rest.add(db, user, TODAY, None, NOW)


def test_rest_day_date_rules(db, user):
    rest.add(db, user, d(-3), None, NOW)   # a sick day noticed late
    with pytest.raises(rest.RuleError):
        rest.add(db, user, d(-4), None, NOW)
    with pytest.raises(rest.RuleError):
        rest.add(db, user, d(400), None, NOW)
    with pytest.raises(rest.Conflict):
        rest.add(db, user, d(-3), None, NOW)


def test_a_completed_challenge_day_cannot_be_a_rest_day(db, user):
    pid = projects.create_project(db, user, ps.ProjectCreate(title="RAG chatbot"), now=NOW)["id"]
    finish_day(db, user, pid, 0)
    with pytest.raises(rest.RuleError, match="completed"):
        rest.add(db, user, TODAY, None, NOW)


def test_a_rest_day_keeps_the_streak_and_is_not_missed(db, user):
    pid = projects.create_project(db, user, ps.ProjectCreate(title="RAG chatbot"), now=NOW)["id"]
    finish_day(db, user, pid, -2)
    finish_day(db, user, pid, 0)                        # yesterday has nothing
    before = challenges.stats(db, user, NOW)
    assert before["missed"] == 1 and before["current_streak"] == 1
    rest.add(db, user, d(-1), "Fever", NOW)
    after = challenges.stats(db, user, NOW)
    assert after["missed"] == 0 and after["current_streak"] == 2 and after["rest_days"] == 1
    cal = challenges.calendar(db, user, d(-2), d(1), NOW)
    assert [x["status"] for x in cal["days"]] == ["completed", "rest", "completed", "none"]


def test_a_future_rest_day_shows_on_the_calendar_and_today_view(db, user):
    rest.add(db, user, TODAY, None, NOW)
    rest.add(db, user, d(2), None, NOW)
    assert challenges.today_view(db, user, NOW)["rest_day"] is True
    cal = challenges.calendar(db, user, TODAY, d(3), NOW)
    assert [x["status"] for x in cal["days"]] == ["rest", "none", "rest", "none"]
    assert challenges.stats(db, user, NOW)["rest_days"] == 1   # only days up to today count


def test_on_a_rest_day_open_items_are_excused_not_overdue(db, user):
    mk_task(db, user, "Write notes", scheduled_date=d(-1), estimated_minutes=30)
    mk_task(db, user, "Read paper", scheduled_date=TODAY, estimated_minutes=30)
    assert plan(db, user)["summary"]["overdue"] == 1
    rest.add(db, user, TODAY, None, NOW)
    p = plan(db, user)
    assert p["summary"]["rest_day"] is True and p["summary"]["overdue"] == 0 and p["summary"]["pending"] == 0
    assert p["summary"]["excused"] == 2 and p["summary"]["total"] == 0 and p["summary"]["percent"] == 0
    assert {i["excuse_reason"] for i in p["items"]} == {"Rest day"} and not any(i["can_excuse"] for i in p["items"])


def test_work_done_on_a_rest_day_still_counts(db, user):
    t = mk_task(db, user, "Read paper", scheduled_date=TODAY)
    rest.add(db, user, TODAY, None, NOW)
    planner.complete_item(db, user, s.ItemRef(kind="task", ref_id=t.id, date=TODAY), NOW)
    p = plan(db, user)
    assert p["summary"]["completed"] == 1 and p["summary"]["total"] == 1 and p["summary"]["percent"] == 100


# ============================== daily hours ==============================


def test_no_hours_set_never_flags_overload(db, user):
    mk_task(db, user, "Huge", scheduled_date=TODAY, estimated_minutes=900)
    s_ = plan(db, user)["summary"]
    assert s_["available_minutes"] is None and s_["overloaded"] is False and s_["planned_minutes"] == 900


def test_a_day_over_its_hours_is_flagged(db, user):
    set_week(db, user, [120, 120, 120, 120, 120, 60, 60])   # Monday = 120
    mk_task(db, user, "A", scheduled_date=TODAY, estimated_minutes=90)
    assert plan(db, user)["summary"]["overloaded"] is False
    mk_task(db, user, "B", scheduled_date=TODAY, estimated_minutes=45)
    s_ = plan(db, user)["summary"]
    assert s_["planned_minutes"] == 135 and s_["available_minutes"] == 120 and s_["overloaded"] is True


def test_exactly_the_available_time_is_not_overloaded(db, user):
    set_week(db, user, [120] * 7)
    mk_task(db, user, "A", scheduled_date=TODAY, estimated_minutes=120)
    assert plan(db, user)["summary"]["overloaded"] is False


def test_the_hours_follow_the_weekday(db, user):
    set_week(db, user, [240, 30, 240, 240, 240, 240, 240])   # Tuesday = 30
    mk_task(db, user, "A", scheduled_date=d(1), estimated_minutes=60)
    mk_task(db, user, "B", scheduled_date=TODAY, estimated_minutes=60)
    assert plan(db, user, d(1))["summary"]["overloaded"] is True and plan(db, user)["summary"]["overloaded"] is False


def test_items_without_a_time_are_counted_not_guessed(db, user):
    set_week(db, user, [60] * 7)
    mk_task(db, user, "Timed", scheduled_date=TODAY, estimated_minutes=30)
    mk_task(db, user, "Untimed", scheduled_date=TODAY)
    s_ = plan(db, user)["summary"]
    assert s_["planned_minutes"] == 30 and s_["unestimated"] == 1 and s_["overloaded"] is False


def test_a_rest_day_is_never_overloaded(db, user):
    set_week(db, user, [10] * 7)
    mk_task(db, user, "A", scheduled_date=TODAY, estimated_minutes=300)
    rest.add(db, user, TODAY, None, NOW)
    assert plan(db, user)["summary"]["overloaded"] is False


def test_a_zero_hour_day_with_work_is_overloaded(db, user):
    set_week(db, user, [0, 60, 60, 60, 60, 60, 60])
    mk_task(db, user, "A", scheduled_date=TODAY, estimated_minutes=15)
    assert plan(db, user)["summary"]["overloaded"] is True


def test_bad_stored_hours_are_ignored(db, user):
    prefs.settings_row(db, user).weekday_minutes = "1,2,three"
    db.commit()
    assert prefs.weekday_minutes(db, user) is None
    assert plan(db, user)["summary"]["available_minutes"] is None


# ============================== rolling over ==============================


def roll(db, user, **kw):
    return planner.roll_over(db, user, s.RollOverIn(**kw), NOW)


def test_roll_over_moves_unfinished_tasks_to_tomorrow(db, user):
    a = mk_task(db, user, "Late", scheduled_date=d(-2), estimated_minutes=30)
    b = mk_task(db, user, "Today", scheduled_date=TODAY, estimated_minutes=60)
    done = mk_task(db, user, "Done", scheduled_date=TODAY, status="completed", completed_at=NOW)
    out = roll(db, user)
    assert {m["task_id"] for m in out["moved"]} == {a.id, b.id} and out["dry_run"] is False
    db.refresh(a), db.refresh(b), db.refresh(done)
    assert a.scheduled_date == d(1) and b.scheduled_date == d(1) and done.scheduled_date == TODAY
    assert a.carry_count == 1 and a.carried_from_date == d(-2) and b.carried_from_date == TODAY
    assert out["tomorrow"]["date"] == d(1) and out["tomorrow"]["planned_minutes"] == 90


def test_dry_run_changes_nothing(db, user):
    t = mk_task(db, user, "Today", scheduled_date=TODAY, estimated_minutes=60)
    out = roll(db, user, dry_run=True)
    assert out["dry_run"] is True and [m["task_id"] for m in out["moved"]] == [t.id] and out["tomorrow"]["planned_minutes"] == 60
    db.refresh(t)
    assert t.scheduled_date == TODAY and t.carry_count == 0
    assert plan(db, user, d(1))["summary"]["planned_minutes"] == 0


def test_roll_over_reports_an_overloaded_tomorrow(db, user):
    set_week(db, user, [240, 60, 240, 240, 240, 240, 240])   # Tuesday = 60
    mk_task(db, user, "Tomorrow already", scheduled_date=d(1), estimated_minutes=40)
    mk_task(db, user, "Today", scheduled_date=TODAY, estimated_minutes=40)
    out = roll(db, user, dry_run=True)["tomorrow"]
    assert out["planned_minutes"] == 80 and out["available_minutes"] == 60 and out["overloaded"] is True


def test_roll_over_can_pick_tasks_and_skips_excused_and_already_tomorrow(db, user):
    a = mk_task(db, user, "A", scheduled_date=TODAY)
    b = mk_task(db, user, "B", scheduled_date=TODAY)
    c = mk_task(db, user, "C", scheduled_date=TODAY)
    planner.excuse_item(db, user, s.ExcuseIn(kind="task", ref_id=c.id, date=TODAY, reason="Waiting on someone"), NOW)
    due_today_planned_tomorrow = mk_task(db, user, "D", scheduled_date=d(1), due_date=TODAY)
    assert {m["task_id"] for m in roll(db, user, dry_run=True)["moved"]} == {a.id, b.id}   # C excused, D already tomorrow
    out = roll(db, user, task_ids=[a.id])
    assert [m["task_id"] for m in out["moved"]] == [a.id]
    db.refresh(b), db.refresh(c), db.refresh(due_today_planned_tomorrow)
    assert b.scheduled_date == TODAY and c.scheduled_date == TODAY and due_today_planned_tomorrow.carry_count == 0


def test_roll_over_with_nothing_to_move(db, user):
    out = roll(db, user)
    assert out["moved"] == [] and out["tomorrow"]["total"] == 0


def test_roll_over_ignores_other_users_and_cancelled_tasks(db, user):
    other = User(id=2, email="o@example.com", password_hash="x", display_name="O", timezone="UTC")
    db.add(other)
    db.commit()
    mk_task(db, other, "Theirs", scheduled_date=TODAY)
    mk_task(db, user, "Cancelled", scheduled_date=TODAY, status="cancelled")
    assert roll(db, user)["moved"] == []


# ============================== slipping ==============================


def test_a_task_moved_three_times_is_slipping(db, user):
    t = mk_task(db, user, "Write the report", scheduled_date=TODAY)
    for i in range(1, 4):
        assert plan(db, user)["items"][0]["slipping"] is (i > 3)
        planner.reschedule_task(db, user, t.id, s.RescheduleIn(date=d(i), from_date=TODAY), NOW)
        t.scheduled_date = TODAY  # keep it on today's plan so the flag can be read
        db.commit()
    item = plan(db, user)["items"][0]
    assert item["carry_count"] == 3 and item["slipping"] is True
    assert [x["task_id"] for x in planner.slipping_tasks(db, user)] == [t.id]


def test_slipping_tasks_lists_only_open_ones_worst_first(db, user):
    mk_task(db, user, "Twice", carry_count=2)
    three = mk_task(db, user, "Three", carry_count=3)
    five = mk_task(db, user, "Five", carry_count=5)
    mk_task(db, user, "Finished", carry_count=9, status="completed", completed_at=NOW)
    assert [x["task_id"] for x in planner.slipping_tasks(db, user)] == [five.id, three.id]


def test_the_assistant_tool_lists_slipping_tasks(db, user):
    import json

    from app.services import assistant

    mk_task(db, user, "Stuck", carry_count=4)
    text, is_error = assistant._run_tool(db, user, "get_slipping_items", {})
    assert is_error is False
    out = json.loads(text)
    assert out["slipping_tasks"][0]["title"] == "Stuck" and out["slipping_tasks"][0]["moved_times"] == 4
    assert assistant._run_tool(db, user, "get_slipping_items", {"user_id": 2})[1] is True   # no extra arguments


def test_the_prompt_tells_the_assistant_to_ask_why_first():
    from app.ai.prompt import system_prompt

    text = system_prompt("Me", TODAY)
    assert "get_slipping_items" in text and "ONE short, kind question" in text
