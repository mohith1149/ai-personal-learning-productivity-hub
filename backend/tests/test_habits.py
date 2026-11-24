"""Habits: streak maths checked against hand-worked calendars, rules, isolation. 'Today' is Mon 23 Nov 2026 (Kolkata)."""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Habit, HabitLog, User
from app.schemas import habits as s
from app.services import auth as auth_service
from app.services import habits as svc

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


def mk(db, user, name="Reading", **kw) -> dict:
    kw.setdefault("start_date", date(2026, 11, 1))
    return svc.create_habit(db, user, s.HabitCreate(name=name, **kw), now=NOW)


def log(db, user, habit_id, day, completed=True, **kw):
    return svc.set_log(db, user, habit_id, day, s.LogIn(completed=completed, **kw), now=NOW)


# ============================== streak maths (pure) ==============================


def test_daily_streak_counts_consecutive_completed_days():
    assert svc.daily_streak({D(20), D(21), D(22)}, TODAY) == (3, 3)           # today still pending: doesn't break it
    assert svc.daily_streak({D(20), D(21), D(22), D(23)}, TODAY) == (4, 4)    # today done as well


def test_daily_streak_breaks_on_a_missed_day():
    assert svc.daily_streak({D(20), D(21)}, TODAY) == (0, 2)                  # 22nd missed, so nothing is running
    assert svc.daily_streak({D(18), D(19), D(21), D(22)}, TODAY) == (2, 2)
    assert svc.daily_streak({D(10), D(11), D(12), D(13), D(21)}, TODAY) == (0, 4)   # longest run is in the past


def test_daily_streak_with_no_records():
    assert svc.daily_streak(set(), TODAY) == (0, 0)


def test_daily_streak_crosses_month_and_year_boundaries():
    assert svc.daily_streak({date(2025, 12, 30), date(2025, 12, 31), date(2026, 1, 1)}, date(2026, 1, 1)) == (3, 3)


def test_weekly_streak_counts_consecutive_weeks_that_met_the_target():
    done = {D(2), D(3), D(4), D(9), D(10), D(11), D(16), D(17), D(23)}      # weeks of 2nd, 9th: 3 days; 16th: 2; 23rd: 1
    assert svc.weekly_streak(done, 3, TODAY) == (0, 2)                         # 16th week fell short of 3
    assert svc.weekly_streak(done | {D(18)}, 3, TODAY) == (3, 3)               # now the 16th is met too


def test_weekly_streak_current_week_in_progress_does_not_break_it_but_meeting_it_extends_it():
    done = {D(9), D(10), D(11), D(16), D(17), D(18)}
    assert svc.weekly_streak(done, 3, TODAY) == (2, 2)                         # this week (23rd) has nothing yet
    assert svc.weekly_streak(done | {D(23)}, 3, TODAY) == (2, 2)
    assert svc.weekly_streak(done | {D(23), D(24), D(25)}, 3, date(2026, 11, 25)) == (3, 3)


def test_weekly_weeks_run_monday_to_sunday():
    # Sun 22nd belongs to the week of Mon 16th, not to the week of the 23rd
    assert svc.week_start(D(22)) == D(16) and svc.week_start(D(23)) == D(23) and svc.week_start(D(29)) == D(23)
    assert svc.weekly_streak({D(16), D(17), D(22)}, 3, TODAY) == (1, 1)


# ============================== creating habits ==============================


def test_create_defaults_and_trimming(db, user):
    h = svc.create_habit(db, user, s.HabitCreate(name="  Walking  "), now=NOW)
    assert (h["name"], h["frequency"], h["target_per_period"], h["active"], h["start_date"]) == ("Walking", "daily", 1, True, TODAY)
    assert h["streak"] == {"current": 0, "longest": 0, "unit": "days"} and h["done_today"] is False and h["today"] is None
    assert len(h["recent"]) == 28 and h["recent"][-1]["date"] == TODAY and not any(r["completed"] for r in h["recent"])


def test_names_are_unique_per_user_case_insensitively(db, user, other):
    mk(db, user, "Reading")
    with pytest.raises(svc.Conflict):
        mk(db, user, "reading")
    assert svc.create_habit(db, other, s.HabitCreate(name="Reading"), now=NOW)["name"] == "Reading"   # another user is fine


@pytest.mark.parametrize("kw", [
    {"frequency": "daily", "target_per_period": 3}, {"frequency": "weekly", "target_per_period": 0},
    {"frequency": "weekly", "target_per_period": 8}, {"target_value": 0}, {"target_value": -5}, {"name": ""},
])
def test_invalid_habits_are_rejected(kw):
    with pytest.raises(ValueError):
        s.HabitCreate(**{"name": "X", **kw})


def test_database_enforces_the_same_limits(db, user):
    db.add(Habit(user_id=user.id, name="A", frequency="weekly", target_per_period=9))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_update_and_switching_frequency(db, user):
    h = mk(db, user, frequency="weekly", target_per_period=4)
    assert (h["week"]["target"], h["streak"]["unit"]) == (4, "weeks")
    d = svc.update_habit(db, user, h["id"], s.HabitUpdate(frequency="daily"), now=NOW)
    assert (d["frequency"], d["target_per_period"], d["week"]["target"], d["streak"]["unit"]) == ("daily", 1, None, "days")
    w = svc.update_habit(db, user, h["id"], s.HabitUpdate(frequency="weekly", target_per_period=2, notes="n", target_value=30, unit="min"), now=NOW)
    assert (w["target_per_period"], w["notes"], w["target_value"], w["unit"]) == (2, "n", 30, "min")
    cleared = svc.update_habit(db, user, h["id"], s.HabitUpdate(target_value=None, unit=None), now=NOW)
    assert cleared["target_value"] is None and cleared["unit"] is None
    assert svc.update_habit(db, user, h["id"], s.HabitUpdate(active=False), now=NOW)["active"] is False
    for field in ("name", "frequency", "active", "start_date", "target_per_period"):
        with pytest.raises(svc.RuleError):
            svc.update_habit(db, user, h["id"], s.HabitUpdate(**{field: None}), now=NOW)
    mk(db, user, "Coding")
    with pytest.raises(svc.Conflict):
        svc.update_habit(db, user, h["id"], s.HabitUpdate(name="coding"), now=NOW)


def test_delete_removes_the_habit_and_its_records(db, user):
    h = mk(db, user)
    log(db, user, h["id"], TODAY)
    svc.delete_habit(db, user, h["id"])
    assert db.query(Habit).count() == 0 and db.query(HabitLog).count() == 0


# ============================== daily records ==============================


def test_completing_today_updates_streak_and_progress_immediately(db, user):
    h = mk(db, user)
    for d in (D(21), D(22)):
        log(db, user, h["id"], d)
    before = svc.get_habit(db, user, h["id"], now=NOW)
    assert (before["streak"]["current"], before["done_today"]) == (2, False)
    after = log(db, user, h["id"], TODAY, value=30, note="30 pages")
    assert (after["streak"]["current"], after["streak"]["longest"], after["done_today"], after["total_completed"]) == (3, 3, True, 3)
    assert (after["today"].value, after["today"].note) == (30, "30 pages")
    assert after["recent"][-3:] == [{"date": D(d), "completed": True, "logged": True} for d in (21, 22, 23)]


def test_one_record_per_day_second_write_replaces_it(db, user):
    h = mk(db, user)
    log(db, user, h["id"], TODAY, value=10)
    out = log(db, user, h["id"], TODAY, value=45, note="more")
    assert db.query(HabitLog).count() == 1 and out["today"].value == 45 and out["total_completed"] == 1


def test_a_not_completed_record_is_a_note_about_a_missed_day_and_does_not_count(db, user):
    h = mk(db, user)
    log(db, user, h["id"], D(21))
    out = log(db, user, h["id"], D(22), completed=False, note="sick")
    assert out["streak"]["current"] == 0 and out["total_completed"] == 1
    assert [r for r in out["recent"] if r["date"] == D(22)] == [{"date": D(22), "completed": False, "logged": True}]


def test_unmarking_a_day_removes_it_and_corrects_the_streak(db, user):
    h = mk(db, user)
    for d in (D(21), D(22), D(23)):
        log(db, user, h["id"], d)
    out = svc.delete_log(db, user, h["id"], D(22), now=NOW)
    assert (out["streak"]["current"], out["streak"]["longest"]) == (1, 1)
    with pytest.raises(svc.NotFound):
        svc.delete_log(db, user, h["id"], D(22), now=NOW)


def test_cannot_record_the_future_or_days_before_the_start_date(db, user):
    h = mk(db, user, start_date=D(10))
    with pytest.raises(svc.RuleError, match="future"):
        log(db, user, h["id"], D(24))
    with pytest.raises(svc.RuleError, match="starts on 2026-11-10"):
        log(db, user, h["id"], D(9))
    log(db, user, h["id"], D(10))   # the start date itself is fine


def test_user_timezone_decides_what_today_is(db, user):
    h = mk(db, user)
    late = datetime(2026, 11, 23, 19, 0, tzinfo=timezone.utc)      # already Tue 24 Nov 00:30 in Kolkata
    out = svc.set_log(db, user, h["id"], D(24), s.LogIn(), now=late)
    assert out["done_today"] is True
    with pytest.raises(svc.RuleError):
        svc.set_log(db, user, h["id"], D(24), s.LogIn(), now=NOW)  # at NOW, the 24th is still the future


def test_value_bounds():
    for bad in (-1, 2_000_000):
        with pytest.raises(ValueError):
            s.LogIn(value=bad)


def test_history_lists_recent_records_newest_first(db, user):
    h = mk(db, user, start_date=date(2026, 8, 1))
    for d in (date(2026, 8, 5), D(1), D(20), D(22)):
        log(db, user, h["id"], d)
    got = svc.history(db, user, h["id"], days=30, now=NOW)
    assert [x.date for x in got] == [D(22), D(20), D(1)]            # 5 Aug is outside the last 30 days


# ============================== progress windows ==============================


def test_daily_week_and_month_progress(db, user):
    h = mk(db, user, start_date=D(1))
    for d in (D(2), D(3), D(4), D(5), D(6), D(7), D(8), D(9), D(10), D(11), D(23)):
        log(db, user, h["id"], d)
    out = svc.get_habit(db, user, h["id"], now=NOW)
    assert (out["week"]["start"], out["week"]["end"]) == (D(23), D(29))
    assert (out["week"]["completed"], out["week"]["eligible_days"], out["week"]["percent"]) == (1, 1, 100)      # only Mon has happened
    assert (out["month"]["completed"], out["month"]["eligible_days"], out["month"]["percent"]) == (11, 23, 47)   # 11/23
    assert (out["month"]["start"], out["month"]["end"]) == (D(1), D(30))


def test_days_before_the_start_date_never_count(db, user):
    h = mk(db, user, start_date=D(10))
    log(db, user, h["id"], D(22))
    log(db, user, h["id"], D(23))
    moved = svc.update_habit(db, user, h["id"], s.HabitUpdate(start_date=D(23)), now=NOW)   # start moved later: the 22nd is ignored
    assert (moved["total_completed"], moved["streak"]["current"], moved["month"]["eligible_days"]) == (1, 1, 1)


def test_weekly_progress_is_measured_against_days_per_week(db, user):
    h = mk(db, user, frequency="weekly", target_per_period=3)
    out = log(db, user, h["id"], D(23))
    assert (out["week"]["completed"], out["week"]["target"], out["week"]["percent"]) == (1, 3, 33)
    assert out["month"]["percent"] is None and out["streak"]["unit"] == "weeks"
    assert svc.list_habits(db, user, now=NOW)["due_today"] == 0      # done today, so not due


def test_weekly_habit_stays_due_until_the_weeks_target_is_met(db, user):
    h = mk(db, user, frequency="weekly", target_per_period=1)
    assert svc.list_habits(db, user, now=NOW)["due_today"] == 1
    log(db, user, h["id"], D(23))
    assert svc.list_habits(db, user, now=NOW)["due_today"] == 0


def test_percent_never_exceeds_100(db, user):
    h = mk(db, user, frequency="weekly", target_per_period=2)
    out = log(db, user, h["id"], D(23))
    assert out["week"]["percent"] == 50
    # a goal of 1 met by 1 day shows exactly 100
    h2 = mk(db, user, "Extra", frequency="weekly", target_per_period=1)
    out2 = log(db, user, h2["id"], D(23))
    assert out2["week"]["percent"] == 100


def test_due_today_counts_only_active_habits_not_yet_done(db, user):
    a, b = mk(db, user, "A"), mk(db, user, "B")
    mk(db, user, "C", active=False)
    assert svc.list_habits(db, user, now=NOW)["due_today"] == 2
    log(db, user, a["id"], TODAY)
    assert svc.list_habits(db, user, now=NOW)["due_today"] == 1
    assert [i["name"] for i in svc.list_habits(db, user, now=NOW)["items"]] == ["A", "B", "C"]    # active ones first


# ============================== isolation ==============================


def test_other_users_habits_are_not_found(db, user, other):
    h = mk(db, user)
    for call in (lambda: svc.get_habit(db, other, h["id"]), lambda: svc.update_habit(db, other, h["id"], s.HabitUpdate(name="X")),
                 lambda: svc.delete_habit(db, other, h["id"]), lambda: svc.set_log(db, other, h["id"], TODAY, s.LogIn(), now=NOW),
                 lambda: svc.delete_log(db, other, h["id"], TODAY), lambda: svc.history(db, other, h["id"])):
        with pytest.raises(svc.NotFound):
            call()
    assert svc.list_habits(db, other)["items"] == []
