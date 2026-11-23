"""Business-rule tests for tasks, with an injected clock so overdue/recurring logic is deterministic.
Test user lives in Asia/Kolkata (UTC+05:30, no DST)."""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.timeutil import user_now
from app.models import RecurringTask, Task, TaskCategory, User
from app.schemas import tasks as s
from app.services import auth as auth_service
from app.services import tasks as svc

# 2026-11-23 is a Monday. 10:00 UTC == 15:30 in Kolkata.
NOW = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)
TODAY = date(2026, 11, 23)


@pytest.fixture
def user(db) -> User:
    return auth_service.create_first_user(
        db, email="me@example.com", password="correct-horse-9", display_name="Me", timezone="Asia/Kolkata"
    )


@pytest.fixture
def other_user(db, user) -> User:
    u = User(id=2, email="other@example.com", password_hash="x", display_name="Other", timezone="UTC")
    db.add(u)
    db.commit()
    return u


def mk(db, user, title="t", **kw) -> Task:
    return svc.create_task(db, user, s.TaskCreate(title=title, **kw))


# ====================== overdue definition ======================


def _t(status="pending", due=None, due_time=None) -> Task:
    return Task(title="x", status=status, due_date=due, due_time=due_time)


@pytest.mark.parametrize(
    "task, expected, why",
    [
        (_t(due=TODAY - timedelta(days=1)), True, "due yesterday, still open"),
        (_t(due=TODAY), False, "due today with no time: not overdue until tomorrow"),
        (_t(due=TODAY, due_time="15:29"), True, "due 15:29, now 15:30"),
        (_t(due=TODAY, due_time="15:30"), False, "due exactly now: not yet overdue"),
        (_t(due=TODAY, due_time="15:31"), False, "due later today"),
        (_t(due=TODAY + timedelta(days=1)), False, "due tomorrow"),
        (_t(due=None), False, "no due date can never be overdue"),
        (_t(status="completed", due=TODAY - timedelta(days=9)), False, "completed is never overdue"),
        (_t(status="cancelled", due=TODAY - timedelta(days=9)), False, "cancelled is never overdue"),
        (_t(status="in_progress", due=TODAY - timedelta(days=1)), True, "started but unfinished is overdue"),
    ],
)
def test_is_overdue_rules(user, task, expected, why):
    assert svc.is_overdue(task, user_now(user, NOW)) is expected, why


def test_overdue_uses_the_users_timezone_not_the_servers(db, user):
    # 19:00 UTC on the 23rd is already 00:30 on the 24th in Kolkata.
    later = datetime(2026, 11, 23, 19, 0, tzinfo=timezone.utc)
    task = _t(due=TODAY)
    assert svc.is_overdue(task, user_now(user, NOW)) is False
    assert svc.is_overdue(task, user_now(user, later)) is True


def test_python_and_sql_overdue_definitions_agree(db, user):
    """`is_overdue` (shown on each task) and `overdue_clause` (the Overdue tab/count) must never disagree."""
    dues = [None, TODAY - timedelta(days=3), TODAY - timedelta(days=1), TODAY, TODAY + timedelta(days=2)]
    times = [None, "00:00", "15:29", "15:30", "15:31", "23:59"]
    for st in ("pending", "in_progress", "completed", "cancelled"):
        for d in dues:
            for tm in times:
                if tm and d is None:
                    continue
                t = Task(user_id=user.id, title=f"{st}-{d}-{tm}", status=st, due_date=d, due_time=tm, priority=3,
                         completed_at=NOW if st == "completed" else None)
                db.add(t)
    db.commit()
    for now in (NOW, datetime(2026, 11, 23, 18, 29, tzinfo=timezone.utc), datetime(2026, 11, 24, 0, 5, tzinfo=timezone.utc)):
        local = user_now(user, now)
        expected = {t.id for t in db.scalars(select(Task)) if svc.is_overdue(t, local)}
        got = {t.id for t in svc.list_tasks(db, user, view="overdue", now=now, limit=500)[0]}
        assert got == expected and expected, f"mismatch at {now}"


# ====================== views & counts ======================


def test_views_and_counts(db, user):
    overdue = mk(db, user, "overdue", due_date=TODAY - timedelta(days=2))
    due_today = mk(db, user, "due today", due_date=TODAY)
    sched_today = mk(db, user, "scheduled today", scheduled_date=TODAY)
    upcoming = mk(db, user, "upcoming", due_date=TODAY + timedelta(days=3))
    undated = mk(db, user, "undated")
    done = mk(db, user, "done", due_date=TODAY)
    svc.update_task(db, user, done.id, s.TaskUpdate(status="completed"), now=NOW)
    cancelled = mk(db, user, "cancelled")
    svc.update_task(db, user, cancelled.id, s.TaskUpdate(status="cancelled"))

    def ids(view):
        return {t.id for t in svc.list_tasks(db, user, view=view, now=NOW)[0]}

    assert ids("overdue") == {overdue.id}
    assert ids("today") == {due_today.id, sched_today.id}
    assert ids("upcoming") == {upcoming.id}
    assert ids("open") == {overdue.id, due_today.id, sched_today.id, upcoming.id, undated.id}
    assert ids("completed") == {done.id}
    assert ids("all") == ids("open") | {done.id, cancelled.id}

    c = svc.counts(db, user, now=NOW)
    assert c == {"open": 5, "overdue": 1, "today": 2, "upcoming": 1, "completed": 1, "completed_today": 1, "all": 7}


def test_completed_today_counts_in_users_local_day(db, user):
    t = mk(db, user)
    # Completed at 18:45 UTC on the 22nd == 00:15 local on the 23rd, so it counts for "today" locally.
    svc.update_task(db, user, t.id, s.TaskUpdate(status="completed"), now=datetime(2026, 11, 22, 18, 45, tzinfo=timezone.utc))
    assert svc.counts(db, user, now=NOW)["completed_today"] == 1
    # ...and no longer counts once the local day has rolled over.
    assert svc.counts(db, user, now=datetime(2026, 11, 24, 10, 0, tzinfo=timezone.utc))["completed_today"] == 0


def test_search_treats_wildcards_literally(db, user):
    mk(db, user, "100% done")
    mk(db, user, "plain")
    mk(db, user, "under_score")
    assert [t.title for t in svc.list_tasks(db, user, q="%", now=NOW)[0]] == ["100% done"]
    assert [t.title for t in svc.list_tasks(db, user, q="_", now=NOW)[0]] == ["under_score"]
    assert {t.title for t in svc.list_tasks(db, user, q="PLAIN", now=NOW)[0]} == {"plain"}


def test_open_tasks_sort_by_due_then_priority_and_come_before_done(db, user):
    a = mk(db, user, "late-high", due_date=TODAY + timedelta(days=5), priority=1)
    b = mk(db, user, "soon-low", due_date=TODAY + timedelta(days=1), priority=4)
    c = mk(db, user, "soon-high", due_date=TODAY + timedelta(days=1), priority=1)
    d = mk(db, user, "undated")
    e = mk(db, user, "finished", due_date=TODAY)
    svc.update_task(db, user, e.id, s.TaskUpdate(status="completed"), now=NOW)
    order = [t.id for t in svc.list_tasks(db, user, now=NOW)[0]]
    assert order == [c.id, b.id, a.id, d.id, e.id]


# ====================== status / completed_at ======================


def test_completion_sets_and_clears_completed_at(db, user):
    t = mk(db, user)
    assert t.completed_at is None
    t = svc.update_task(db, user, t.id, s.TaskUpdate(status="completed"), now=NOW)
    assert t.status == "completed" and t.completed_at == NOW
    # Completing again must not move the original completion time.
    t = svc.update_task(db, user, t.id, s.TaskUpdate(status="completed"), now=NOW + timedelta(hours=5))
    assert t.completed_at == NOW
    t = svc.update_task(db, user, t.id, s.TaskUpdate(status="pending"))
    assert t.status == "pending" and t.completed_at is None
    t = svc.update_task(db, user, t.id, s.TaskUpdate(status="completed"), now=NOW)
    t = svc.update_task(db, user, t.id, s.TaskUpdate(status="cancelled"))
    assert t.completed_at is None


def test_database_refuses_inconsistent_completion(db, user):
    t = mk(db, user)
    with pytest.raises(IntegrityError):
        db.execute(update(Task).where(Task.id == t.id).values(status="completed"))  # no completed_at
        db.commit()
    db.rollback()
    with pytest.raises(IntegrityError):
        db.execute(update(Task).where(Task.id == t.id).values(completed_at=NOW))  # completed_at but not completed
        db.commit()


# ====================== validation rules ======================


def test_date_rules(db, user):
    with pytest.raises(svc.RuleError, match="due time needs a due date"):
        mk(db, user, due_time="09:00")
    with pytest.raises(svc.RuleError, match="before the scheduled"):
        mk(db, user, scheduled_date=TODAY, due_date=TODAY - timedelta(days=1))


def test_partial_update_is_validated_against_stored_values(db, user):
    t = mk(db, user, scheduled_date=TODAY + timedelta(days=2), due_date=TODAY + timedelta(days=3))
    with pytest.raises(svc.RuleError, match="before the scheduled"):
        svc.update_task(db, user, t.id, s.TaskUpdate(due_date=TODAY))
    t2 = mk(db, user, due_date=TODAY, due_time="09:00")
    t2 = svc.update_task(db, user, t2.id, s.TaskUpdate(due_date=None))
    assert t2.due_date is None and t2.due_time is None  # clearing the date clears its time


def test_explicit_null_clears_optional_field_but_omitted_field_is_kept(db, user):
    t = mk(db, user, description="keep me", notes="clear me", estimated_minutes=30)
    t = svc.update_task(db, user, t.id, s.TaskUpdate(notes=None))
    assert t.notes is None and t.description == "keep me" and t.estimated_minutes == 30


@pytest.mark.parametrize("field", ["title", "priority", "status"])
def test_required_fields_cannot_be_nulled(db, user, field):
    t = mk(db, user)
    with pytest.raises(svc.RuleError):
        svc.update_task(db, user, t.id, s.TaskUpdate(**{field: None}))


def test_users_cannot_see_or_touch_each_others_data(db, user, other_user):
    theirs = Task(user_id=other_user.id, title="secret", priority=3)
    db.add(theirs)
    db.commit()
    assert svc.list_tasks(db, user, now=NOW)[0] == []
    for call in (
        lambda: svc.get_task(db, user, theirs.id),
        lambda: svc.update_task(db, user, theirs.id, s.TaskUpdate(title="mine now")),
        lambda: svc.delete_task(db, user, theirs.id),
    ):
        with pytest.raises(svc.NotFound):
            call()
    cat = TaskCategory(user_id=other_user.id, name="theirs")
    db.add(cat)
    db.commit()
    with pytest.raises(svc.RuleError, match="doesn't exist"):
        mk(db, user, category_id=cat.id)


# ====================== categories ======================


def test_category_rules(db, user):
    work = svc.create_category(db, user, s.CategoryCreate(name="Work"))
    with pytest.raises(svc.RuleError, match="already exists"):
        svc.create_category(db, user, s.CategoryCreate(name="work"))  # case-insensitive
    t = mk(db, user, category_id=work.id)
    svc.delete_category(db, user, work.id)
    db.refresh(t)
    assert t.category_id is None  # the task survives its category

    system = TaskCategory(user_id=user.id, name="Study", is_system=True)
    db.add(system)
    db.commit()
    with pytest.raises(svc.RuleError, match="can't be renamed"):
        svc.update_category(db, user, system.id, s.CategoryUpdate(name="Other"))
    with pytest.raises(svc.RuleError, match="can't be deleted"):
        svc.delete_category(db, user, system.id)
    assert svc.update_category(db, user, system.id, s.CategoryUpdate(color="#112233")).color == "#112233"


# ====================== recurring: when does it occur ======================


def rt_obj(**kw) -> RecurringTask:
    base = dict(title="r", frequency="daily", start_date=date(2026, 1, 1), priority=3)
    return RecurringTask(**{**base, **kw})


def test_occurs_on_each_frequency():
    mon, tue, sat = date(2026, 11, 23), date(2026, 11, 24), date(2026, 11, 28)
    assert svc.occurs_on(rt_obj(frequency="daily"), sat)
    assert svc.occurs_on(rt_obj(frequency="weekdays"), mon) and not svc.occurs_on(rt_obj(frequency="weekdays"), sat)
    weekly = rt_obj(frequency="weekly", days_of_week="0,2")
    assert svc.occurs_on(weekly, mon) and not svc.occurs_on(weekly, tue)
    monthly = rt_obj(frequency="monthly", day_of_month=15)
    assert svc.occurs_on(monthly, date(2026, 12, 15)) and not svc.occurs_on(monthly, date(2026, 12, 14))


def test_monthly_day_31_falls_on_the_last_day_of_short_months():
    m31 = rt_obj(frequency="monthly", day_of_month=31)
    assert svc.occurs_on(m31, date(2026, 2, 28)) and not svc.occurs_on(m31, date(2026, 2, 27))
    assert svc.occurs_on(m31, date(2028, 2, 29))  # leap year
    assert svc.occurs_on(m31, date(2026, 4, 30)) and svc.occurs_on(m31, date(2026, 5, 31))
    # exactly once per month, never twice
    days = [date(2026, 4, 1) + timedelta(days=i) for i in range(30)]
    assert sum(svc.occurs_on(m31, d) for d in days) == 1


def test_occurrence_respects_start_and_end_dates():
    r = rt_obj(start_date=date(2026, 11, 10), end_date=date(2026, 11, 12))
    assert [svc.occurs_on(r, date(2026, 11, d)) for d in (9, 10, 12, 13)] == [False, True, True, False]


# ====================== recurring: generation ======================


def mk_rec(db, user, now=NOW, **kw):
    kw.setdefault("title", "Daily review")
    kw.setdefault("frequency", "daily")
    return svc.create_recurring(db, user, s.RecurringCreate(**kw), now=now)


def instances(db, rt):
    return list(db.scalars(select(Task).where(Task.recurring_task_id == rt.id).order_by(Task.scheduled_date)))


def test_creation_generates_today_through_horizon(db, user):
    rt = mk_rec(db, user)
    days = [t.scheduled_date for t in instances(db, rt)]
    assert days == [TODAY + timedelta(days=i) for i in range(8)]
    t = instances(db, rt)[0]
    assert t.task_type == "recurring" and t.due_date == t.scheduled_date and t.status == "pending"


def test_generation_is_idempotent(db, user):
    rt = mk_rec(db, user)
    before = len(instances(db, rt))
    assert svc.generate_recurring(db, user, now=NOW) == 0
    assert svc.generate_recurring(db, user, now=NOW) == 0
    assert len(instances(db, rt)) == before


def test_generation_moves_forward_with_time(db, user):
    rt = mk_rec(db, user)
    assert svc.generate_recurring(db, user, now=NOW + timedelta(days=2)) == 2
    assert instances(db, rt)[-1].scheduled_date == TODAY + timedelta(days=9)


def test_days_missed_while_app_was_closed_come_back_as_overdue_not_vanish(db, user):
    mk_rec(db, user)
    later = NOW + timedelta(days=12)  # nobody opened the app for 12 days
    svc.generate_recurring(db, user, now=later)
    overdue = svc.list_tasks(db, user, view="overdue", now=later)[0]
    # Days 0..11 are in the past by then and none were done: 8 existing + 4 back-filled, all overdue.
    assert {t.scheduled_date for t in overdue} == {TODAY + timedelta(days=i) for i in range(12)}
    assert all(svc.is_overdue(t, user_now(user, later)) for t in overdue)


def test_backfill_is_capped(db, user):
    rt = mk_rec(db, user)
    db.execute(update(RecurringTask).where(RecurringTask.id == rt.id).values(
        start_date=date(2025, 1, 1), last_generated_date=date(2025, 6, 1)))
    db.commit()
    svc.generate_recurring(db, user, now=NOW)
    earliest = min(t.scheduled_date for t in instances(db, rt) if t.scheduled_date < TODAY - timedelta(days=1))
    assert earliest >= TODAY - timedelta(days=svc.MAX_BACKFILL_DAYS)


def test_pausing_and_resuming_skips_the_paused_days(db, user):
    rt = mk_rec(db, user)
    svc.update_recurring(db, user, rt.id, s.RecurringUpdate(active=False), now=NOW)
    later = NOW + timedelta(days=20)
    assert svc.generate_recurring(db, user, now=later) == 0  # paused → nothing generated
    svc.update_recurring(db, user, rt.id, s.RecurringUpdate(active=True), now=later)
    new = [t for t in instances(db, rt) if t.scheduled_date > TODAY + timedelta(days=7)]
    assert min(t.scheduled_date for t in new) == TODAY + timedelta(days=20)  # resumes today, no back-fill of the gap


def test_end_date_stops_generation(db, user):
    rt = mk_rec(db, user, end_date=TODAY + timedelta(days=2))
    assert [t.scheduled_date for t in instances(db, rt)][-1] == TODAY + timedelta(days=2)


def test_deleting_an_instance_does_not_resurrect_it(db, user):
    rt = mk_rec(db, user)
    gone = instances(db, rt)[1]
    svc.delete_task(db, user, gone.id)
    svc.generate_recurring(db, user, now=NOW)
    assert gone.scheduled_date not in [t.scheduled_date for t in instances(db, rt)]


def test_deleting_a_template_keeps_the_tasks_it_made(db, user):
    rt = mk_rec(db, user)
    n = len(instances(db, rt))
    svc.delete_recurring(db, user, rt.id)
    remaining = list(db.scalars(select(Task)))
    assert len(remaining) == n and all(t.recurring_task_id is None for t in remaining)


def test_schedule_change_replaces_future_untouched_instances_only(db, user):
    rt = mk_rec(db, user)
    inst = {t.scheduled_date: t for t in instances(db, rt)}
    started = inst[TODAY + timedelta(days=2)]
    svc.update_task(db, user, started.id, s.TaskUpdate(status="in_progress"))
    done = inst[TODAY + timedelta(days=3)]
    svc.update_task(db, user, done.id, s.TaskUpdate(status="completed"), now=NOW)

    svc.update_recurring(db, user, rt.id, s.RecurringUpdate(frequency="weekly", days_of_week=[0]), now=NOW)  # Mondays only
    days = [t.scheduled_date for t in instances(db, rt)]
    assert TODAY in days  # today's instance is never removed
    assert started.scheduled_date in days and done.scheduled_date in days  # started/completed work survives
    # everything else in the next week that remains must be a Monday (the new rule) or the protected ones
    others = [d for d in days if d not in (TODAY, started.scheduled_date, done.scheduled_date)]
    assert all(d.weekday() == 0 for d in others)
    assert TODAY + timedelta(days=7) in others  # next Monday was generated under the new rule


def test_recurring_validation(db, user):
    with pytest.raises(svc.RuleError, match="at least one day"):
        mk_rec(db, user, frequency="weekly")
    with pytest.raises(svc.RuleError, match="day of the month"):
        mk_rec(db, user, frequency="monthly")
    with pytest.raises(svc.RuleError, match="today or later"):
        mk_rec(db, user, start_date=TODAY - timedelta(days=1))
    with pytest.raises(svc.RuleError, match="end date"):
        mk_rec(db, user, start_date=TODAY + timedelta(days=5), end_date=TODAY + timedelta(days=1))


def test_listing_tasks_materialises_recurring_lazily(db, user):
    rt = mk_rec(db, user)
    db.query(Task).delete()
    db.execute(update(RecurringTask).where(RecurringTask.id == rt.id).values(last_generated_date=None))
    db.commit()
    items, _ = svc.list_tasks(db, user, view="today", now=NOW)
    assert [t.scheduled_date for t in items] == [TODAY]
