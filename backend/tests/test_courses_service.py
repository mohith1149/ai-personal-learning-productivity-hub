"""Business-rule tests for courses → modules → lessons, study sessions and templates (injected clock where it matters).
Test user lives in Asia/Kolkata (UTC+05:30)."""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.models import Course, CourseLesson, CourseModule, LearningSession, User
from app.schemas import courses as s
from app.services import auth as auth_service
from app.services import courses as svc

NOW = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)  # 15:30 on Mon 23 Nov in Kolkata
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


def mk_course(db, user, title="Course", **kw) -> Course:
    return svc.create_course(db, user, s.CourseCreate(title=title, **kw))


def mk_module(db, user, course, title="M") -> CourseModule:
    updated = svc.create_module(db, user, course.id, s.ModuleCreate(title=title))
    return updated.modules[-1]


def mk_lessons(db, user, course, module, titles) -> Course:
    return svc.bulk_create_lessons(db, user, course.id, s.BulkLessons(module_id=module.id, titles=titles))


def lessons_of(course) -> list[CourseLesson]:
    return [le for m in course.modules for le in m.lessons]


@pytest.fixture
def course3(db, user):
    """One course, one module, three lessons (10, 20, unknown minutes)."""
    c = mk_course(db, user, "Agents")
    m = mk_module(db, user, c, "Module 1")
    c = mk_lessons(db, user, c, m, ["Intro", "Reflection", "Tools"])
    for le, mins in zip(lessons_of(c), (10, 20, None)):
        svc.update_lesson(db, user, le.id, s.LessonUpdate(duration_minutes=mins) if mins else s.LessonUpdate(notes="n"))
    return svc.get_course(db, user, c.id)


# ====================== progress & next lesson ======================


def test_progress_floors_the_percentage_and_handles_empty_courses(db, user, course3):
    assert svc.progress(course3) == {"total_lessons": 3, "completed_lessons": 0, "percent": 0, "empty_modules": 0, "total_minutes": 30, "remaining_minutes": 30}
    ids = [le.id for le in lessons_of(course3)]
    c = svc.complete_lesson(db, user, ids[0], now=NOW)
    assert svc.progress(c)["percent"] == 33 and svc.progress(c)["remaining_minutes"] == 20
    c = svc.complete_lesson(db, user, ids[1], now=NOW)
    assert svc.progress(c)["percent"] == 66  # NOT 67: never reads higher than reality
    c = svc.complete_lesson(db, user, ids[2], now=NOW)
    assert svc.progress(c)["percent"] == 100
    empty = mk_course(db, user, "Empty")
    assert svc.progress(empty)["percent"] == 0 and svc.progress(empty)["total_lessons"] == 0


def test_next_lesson_follows_study_order_across_modules(db, user):
    c = mk_course(db, user)
    m1, m2 = mk_module(db, user, c, "One"), mk_module(db, user, c, "Two")
    c = mk_lessons(db, user, c, m2, ["B1", "B2"])
    c = mk_lessons(db, user, c, m1, ["A1", "A2"])
    assert svc.next_lesson(c)["title"] == "A1"  # module order beats creation order
    c = svc.complete_lesson(db, user, lessons_of(c)[0].id, now=NOW)
    assert svc.next_lesson(c)["title"] == "A2"
    c = svc.complete_lesson(db, user, lessons_of(c)[1].id, now=NOW)
    nxt = svc.next_lesson(c)
    assert nxt["title"] == "B1" and nxt["module_title"] == "Two"


def test_an_in_progress_lesson_is_still_next_and_nothing_is_next_when_all_done(db, user, course3):
    first = lessons_of(course3)[0]
    c = svc.start_lesson(db, user, first.id, now=NOW)
    assert svc.next_lesson(c)["title"] == "Intro" and svc.next_lesson(c)["status"] == "in_progress"
    for le in lessons_of(c):
        c = svc.complete_lesson(db, user, le.id, now=NOW)
    assert svc.next_lesson(c) is None


# ====================== completion is explicit ======================


def test_nothing_is_completed_unless_the_user_completes_it(db, user):
    c = mk_course(db, user)
    m = mk_module(db, user, c)
    c = mk_lessons(db, user, c, m, ["a", "b"])
    assert all(le.status == "not_started" and le.completed_at is None for le in lessons_of(c))
    assert c.status == "active" and c.completed_at is None and c.started_at is None


def test_complete_is_idempotent_and_uncomplete_clears(db, user, course3):
    lid = lessons_of(course3)[0].id
    c = svc.complete_lesson(db, user, lid, now=NOW)
    first = next(le for le in lessons_of(c) if le.id == lid).completed_at
    assert first == NOW
    c = svc.complete_lesson(db, user, lid, now=NOW + timedelta(days=3))
    assert next(le for le in lessons_of(c) if le.id == lid).completed_at == first  # keeps the original time
    c = svc.uncomplete_lesson(db, user, lid)
    le = next(le for le in lessons_of(c) if le.id == lid)
    assert le.status == "not_started" and le.completed_at is None


def test_database_refuses_inconsistent_lesson_completion(db, user, course3):
    lid = lessons_of(course3)[0].id
    with pytest.raises(IntegrityError):
        db.execute(update(CourseLesson).where(CourseLesson.id == lid).values(status="completed"))
        db.commit()
    db.rollback()
    with pytest.raises(IntegrityError):
        db.execute(update(CourseLesson).where(CourseLesson.id == lid).values(completed_at=NOW))
        db.commit()


def test_start_marks_in_progress_and_sets_started_at_once(db, user, course3):
    ids = [le.id for le in lessons_of(course3)]
    c = svc.start_lesson(db, user, ids[0], now=NOW)
    assert c.started_at == NOW and c.last_studied_at == NOW
    c = svc.start_lesson(db, user, ids[1], now=NOW + timedelta(hours=5))
    assert c.started_at == NOW and c.last_studied_at == NOW + timedelta(hours=5)  # started_at is never moved
    c = svc.complete_lesson(db, user, ids[0], now=NOW)
    with pytest.raises(svc.RuleError, match="already completed"):
        svc.start_lesson(db, user, ids[0])


# ====================== course state is derived from lessons ======================


def test_course_completes_when_the_last_lesson_is_done_and_reopens_otherwise(db, user, course3):
    ids = [le.id for le in lessons_of(course3)]
    for lid in ids[:2]:
        c = svc.complete_lesson(db, user, lid, now=NOW)
    assert c.status == "active" and c.completed_at is None
    c = svc.complete_lesson(db, user, ids[2], now=NOW)
    assert c.status == "completed" and c.completed_at == NOW
    c = svc.uncomplete_lesson(db, user, ids[1])
    assert c.status == "active" and c.completed_at is None  # reopened, history not faked
    c = svc.complete_lesson(db, user, ids[1], now=NOW + timedelta(days=1))
    assert c.status == "completed" and c.completed_at == NOW + timedelta(days=1)


def test_a_course_is_not_complete_while_a_module_is_still_empty(db, user):
    c = mk_course(db, user)
    m1, m2 = mk_module(db, user, c, "One"), mk_module(db, user, c, "Two")
    c = mk_lessons(db, user, c, m1, ["a", "b"])
    for le in lessons_of(c):
        c = svc.complete_lesson(db, user, le.id, now=NOW)
    assert svc.progress(c)["percent"] == 100 and svc.progress(c)["empty_modules"] == 1
    assert c.status == "active" and c.completed_at is None  # every ADDED lesson is done, but module "Two" has none yet

    c = mk_lessons(db, user, c, m2, ["c"])  # filling the module poses a new unfinished lesson
    assert c.status == "active" and svc.progress(c)["empty_modules"] == 0
    c = svc.complete_lesson(db, user, lessons_of(c)[-1].id, now=NOW)
    assert c.status == "completed"


def test_removing_the_empty_module_lets_the_course_complete(db, user):
    c = mk_course(db, user)
    m1, m2 = mk_module(db, user, c, "One"), mk_module(db, user, c, "Two")
    c = mk_lessons(db, user, c, m1, ["a"])
    c = svc.complete_lesson(db, user, lessons_of(c)[0].id, now=NOW)
    assert c.status == "active"
    c = svc.delete_module(db, user, m2.id)
    assert c.status == "completed"


def test_the_seeded_template_cannot_be_completed_by_finishing_only_the_lessons_you_added(db, user):
    c = svc.add_template(db, user, "deeplearning-agentic-ai")
    c = mk_lessons(db, user, c, c.modules[0], ["Welcome", "What is agentic AI?"])
    for le in lessons_of(c):
        c = svc.complete_lesson(db, user, le.id, now=NOW)
    assert svc.progress(c)["empty_modules"] == 4
    assert c.status == "active" and c.completed_at is None  # four modules are still waiting for their lessons


def test_adding_a_lesson_reopens_a_completed_course(db, user, course3):
    for le in lessons_of(course3):
        c = svc.complete_lesson(db, user, le.id, now=NOW)
    assert c.status == "completed"
    c = svc.create_lesson(db, user, c.modules[0].id, s.LessonCreate(title="Bonus"))
    assert c.status == "active" and c.completed_at is None


def test_paused_course_still_completes_and_archived_one_is_left_alone(db, user, course3):
    svc.update_course(db, user, course3.id, s.CourseUpdate(status="paused"))
    for le in lessons_of(course3):
        c = svc.complete_lesson(db, user, le.id, now=NOW)
    assert c.status == "completed"

    c2 = mk_course(db, user, "Old")
    m = mk_module(db, user, c2)
    c2 = mk_lessons(db, user, c2, m, ["x"])
    svc.update_course(db, user, c2.id, s.CourseUpdate(status="archived"))
    c2 = svc.complete_lesson(db, user, lessons_of(c2)[0].id, now=NOW)
    assert c2.status == "archived"  # archiving is the user's explicit choice; it is not overridden


def test_manual_completion_only_for_courses_without_lessons(db, user, course3):
    with pytest.raises(svc.RuleError, match="completed automatically"):
        svc.update_course(db, user, course3.id, s.CourseUpdate(status="completed"))
    book = mk_course(db, user, "A book")
    book = svc.update_course(db, user, book.id, s.CourseUpdate(status="completed"), now=NOW)
    assert book.status == "completed" and book.completed_at == NOW
    book = svc.update_course(db, user, book.id, s.CourseUpdate(status="active"))
    assert book.status == "active" and book.completed_at is None


def test_pause_resume_archive_and_required_fields(db, user, course3):
    for st in ("paused", "active", "archived", "active"):
        assert svc.update_course(db, user, course3.id, s.CourseUpdate(status=st)).status == st
    for field in ("title", "status", "priority", "kind"):
        with pytest.raises(svc.RuleError):
            svc.update_course(db, user, course3.id, s.CourseUpdate(**{field: None}))
    c = svc.update_course(db, user, course3.id, s.CourseUpdate(description=None, title="Renamed"))
    assert c.title == "Renamed" and c.description is None


def test_deleting_the_only_unfinished_lesson_completes_the_course_by_the_same_rule(db, user):
    c = mk_course(db, user)
    m = mk_module(db, user, c)
    c = mk_lessons(db, user, c, m, ["done", "skipped"])
    done, skipped = lessons_of(c)
    svc.complete_lesson(db, user, done.id, now=NOW)
    c = svc.delete_lesson(db, user, skipped.id)
    assert c.status == "completed"  # derived: every remaining lesson is complete


def test_deleting_a_module_removes_its_lessons_and_resyncs(db, user):
    c = mk_course(db, user)
    m1, m2 = mk_module(db, user, c, "A"), mk_module(db, user, c, "B")
    c = mk_lessons(db, user, c, m1, ["a1"])
    c = mk_lessons(db, user, c, m2, ["b1", "b2"])
    c = svc.delete_module(db, user, m2.id)
    assert [m.title for m in c.modules] == ["A"] and [le.title for le in lessons_of(c)] == ["a1"]
    assert db.scalar(select(CourseLesson).where(CourseLesson.title == "b1")) is None


# ====================== ordering ======================


def test_modules_and_lessons_can_be_moved_up_and_down(db, user):
    c = mk_course(db, user)
    a, b, cc = (mk_module(db, user, c, t) for t in "ABC")
    assert [m.title for m in svc.get_course(db, user, c.id).modules] == ["A", "B", "C"]
    c = svc.move_module(db, user, cc.id, "up")
    assert [m.title for m in c.modules] == ["A", "C", "B"]
    c = svc.move_module(db, user, a.id, "up")  # already first: no-op
    assert [m.title for m in c.modules] == ["A", "C", "B"]
    c = svc.move_module(db, user, b.id, "down")  # already last: no-op
    assert [m.title for m in c.modules] == ["A", "C", "B"]

    c = mk_lessons(db, user, c, a, ["l1", "l2", "l3"])
    first = c.modules[0].lessons[0]
    c = svc.move_lesson(db, user, first.id, "down")
    assert [le.title for le in c.modules[0].lessons] == ["l2", "l1", "l3"]
    assert svc.next_lesson(c)["title"] == "l2"  # study order follows the new order


def test_lessons_can_move_between_modules_of_the_same_course_only(db, user):
    c = mk_course(db, user)
    m1, m2 = mk_module(db, user, c, "A"), mk_module(db, user, c, "B")
    c = mk_lessons(db, user, c, m1, ["x"])
    c = mk_lessons(db, user, c, m2, ["y"])
    x = c.modules[0].lessons[0]
    c = svc.update_lesson(db, user, x.id, s.LessonUpdate(module_id=m2.id))
    assert [le.title for le in c.modules[1].lessons] == ["y", "x"]  # appended at the end
    assert all(le.course_id == c.id and le.module_id == m.id for m in c.modules for le in m.lessons)

    other = mk_course(db, user, "Other")
    om = mk_module(db, user, other, "Z")
    with pytest.raises(svc.RuleError, match="within its own course"):
        svc.update_lesson(db, user, x.id, s.LessonUpdate(module_id=om.id))


def test_bulk_add_keeps_order_appends_and_checks_the_module_belongs_to_the_course(db, user):
    c = mk_course(db, user)
    m = mk_module(db, user, c)
    c = mk_lessons(db, user, c, m, ["one", "two"])
    c = mk_lessons(db, user, c, m, ["three", "four"])
    assert [le.title for le in lessons_of(c)] == ["one", "two", "three", "four"]
    other = mk_course(db, user, "Other")
    with pytest.raises(svc.RuleError, match="doesn't belong"):
        svc.bulk_create_lessons(db, user, other.id, s.BulkLessons(module_id=m.id, titles=["x"]))
    with pytest.raises(svc.NotFound):
        svc.bulk_create_lessons(db, user, c.id, s.BulkLessons(module_id=9999, titles=["x"]))


# ====================== ownership ======================


def test_other_users_courses_modules_and_lessons_are_invisible(db, user, other_user):
    theirs = Course(user_id=other_user.id, title="secret")
    db.add(theirs)
    db.commit()
    m = CourseModule(course_id=theirs.id, title="m", position=1)
    db.add(m)
    db.commit()
    le = CourseLesson(module_id=m.id, course_id=theirs.id, title="l", position=1)
    db.add(le)
    db.commit()

    assert svc.list_courses(db, user) == []
    calls = [
        lambda: svc.get_course(db, user, theirs.id),
        lambda: svc.update_course(db, user, theirs.id, s.CourseUpdate(title="mine")),
        lambda: svc.delete_course(db, user, theirs.id),
        lambda: svc.create_module(db, user, theirs.id, s.ModuleCreate(title="x")),
        lambda: svc.update_module(db, user, m.id, s.ModuleUpdate(title="x")),
        lambda: svc.delete_module(db, user, m.id),
        lambda: svc.move_module(db, user, m.id, "up"),
        lambda: svc.create_lesson(db, user, m.id, s.LessonCreate(title="x")),
        lambda: svc.complete_lesson(db, user, le.id),
        lambda: svc.uncomplete_lesson(db, user, le.id),
        lambda: svc.start_lesson(db, user, le.id),
        lambda: svc.delete_lesson(db, user, le.id),
        lambda: svc.move_lesson(db, user, le.id, "up"),
        lambda: svc.create_session(db, user, s.SessionCreate(course_id=theirs.id, minutes=5)),
    ]
    for call in calls:
        with pytest.raises(svc.NotFound):
            call()
    db.refresh(le)
    assert le.status == "not_started" and le.title == "l"


# ====================== templates ======================


def test_template_seeds_structure_only_with_nothing_completed(db, user):
    listed = svc.list_templates(db, user)
    assert [t["key"] for t in listed] == ["deeplearning-agentic-ai"] and listed[0]["already_added"] is False
    c = svc.add_template(db, user, "deeplearning-agentic-ai")
    assert c.title == "Agentic AI" and c.provider == "DeepLearning.AI" and c.url.startswith("https://www.deeplearning.ai/")
    assert [m.title for m in c.modules] == listed[0]["modules"] and len(c.modules) == 5
    assert lessons_of(c) == []  # lessons are not invented
    assert c.status == "active" and c.completed_at is None and c.started_at is None
    assert svc.progress(c) == {"total_lessons": 0, "completed_lessons": 0, "percent": 0, "empty_modules": 5, "total_minutes": 0, "remaining_minutes": 0}
    assert svc.list_templates(db, user)[0]["already_added"] is True


def test_template_cannot_be_added_twice_and_unknown_keys_fail(db, user):
    svc.add_template(db, user, "deeplearning-agentic-ai")
    with pytest.raises(svc.Conflict):
        svc.add_template(db, user, "deeplearning-agentic-ai")
    with pytest.raises(svc.NotFound):
        svc.add_template(db, user, "no-such-template")
    assert len(svc.list_courses(db, user)) == 1


def test_template_can_be_added_by_each_user_separately(db, user, other_user):
    svc.add_template(db, user, "deeplearning-agentic-ai")
    assert svc.list_templates(db, other_user)[0]["already_added"] is False
    svc.add_template(db, other_user, "deeplearning-agentic-ai")


# ====================== study sessions ======================


def test_session_rules(db, user, course3):
    lesson = lessons_of(course3)[0]
    ok = svc.create_session(db, user, s.SessionCreate(course_id=course3.id, lesson_id=lesson.id, minutes=45), now=NOW)
    assert ok.date == TODAY  # defaults to today in the user's timezone
    late = datetime(2026, 11, 23, 19, 0, tzinfo=timezone.utc)  # 00:30 on the 24th in Kolkata
    assert svc.create_session(db, user, s.SessionCreate(course_id=course3.id, minutes=5), now=late).date == date(2026, 11, 24)
    with pytest.raises(svc.RuleError, match="future"):
        svc.create_session(db, user, s.SessionCreate(course_id=course3.id, minutes=5, date=TODAY + timedelta(days=1)), now=NOW)
    other = mk_course(db, user, "Other")
    with pytest.raises(svc.RuleError, match="doesn't belong"):
        svc.create_session(db, user, s.SessionCreate(course_id=other.id, lesson_id=lesson.id, minutes=5), now=NOW)
    with pytest.raises(svc.NotFound):
        svc.create_session(db, user, s.SessionCreate(course_id=9999, minutes=5), now=NOW)


def test_sessions_feed_minutes_studied_and_last_studied(db, user, course3):
    svc.create_session(db, user, s.SessionCreate(course_id=course3.id, minutes=30), now=NOW)
    svc.create_session(db, user, s.SessionCreate(course_id=course3.id, minutes=15, date=TODAY - timedelta(days=2)), now=NOW)
    summary = svc.list_courses(db, user)[0]
    assert summary["minutes_studied"] == 45
    c = svc.get_course(db, user, course3.id)
    assert c.last_studied_at == NOW and c.started_at == NOW
    # logging time on a past day must not pretend you studied just now
    c2 = mk_course(db, user, "Fresh")
    svc.create_session(db, user, s.SessionCreate(course_id=c2.id, minutes=10, date=TODAY - timedelta(days=3)), now=NOW)
    assert svc.get_course(db, user, c2.id).last_studied_at is None


def test_session_listing_filtering_deleting_and_surviving_course_deletion(db, user, course3):
    other = mk_course(db, user, "Other")
    a = svc.create_session(db, user, s.SessionCreate(course_id=course3.id, minutes=10, date=TODAY - timedelta(days=1)), now=NOW)
    b = svc.create_session(db, user, s.SessionCreate(course_id=course3.id, minutes=20), now=NOW)
    svc.create_session(db, user, s.SessionCreate(course_id=other.id, minutes=5), now=NOW)
    assert [x.id for x in svc.list_sessions(db, user, course_id=course3.id)] == [b.id, a.id]  # newest first
    assert len(svc.list_sessions(db, user)) == 3
    svc.delete_session(db, user, a.id)
    with pytest.raises(svc.NotFound):
        svc.delete_session(db, user, a.id)
    svc.delete_course(db, user, course3.id)
    kept = db.get(LearningSession, b.id)
    db.refresh(kept)  # read what the DATABASE holds (the session caches objects after commit)
    assert kept is not None and kept.course_id is None and kept.minutes == 20  # time studied is never lost


def test_weekly_minutes_window(db, user, course3):
    for days_ago, mins in ((0, 10), (6, 20), (7, 40), (30, 80)):
        svc.create_session(db, user, s.SessionCreate(course_id=course3.id, minutes=mins, date=TODAY - timedelta(days=days_ago)), now=NOW)
    assert svc.weekly_minutes(db, user, now=NOW) == 30  # today + the 6 days before; the 7-day-old one is out


# ====================== listing ======================


def test_listing_filters_by_status_and_orders_by_priority_then_title(db, user):
    mk_course(db, user, "Zeta", priority=1)
    mk_course(db, user, "Beta", priority=2)
    mk_course(db, user, "Alpha", priority=2)
    paused = mk_course(db, user, "Paused one")
    svc.update_course(db, user, paused.id, s.CourseUpdate(status="paused"))
    assert [c["title"] for c in svc.list_courses(db, user)] == ["Zeta", "Alpha", "Beta", "Paused one"]
    assert [c["title"] for c in svc.list_courses(db, user, "paused")] == ["Paused one"]
    assert svc.list_courses(db, user, "completed") == []
