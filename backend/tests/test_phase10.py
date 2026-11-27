"""Phase 10: goals with a pace warning, and the timer that logs time to a project / course / topic.
'Today' is Mon 23 Nov 2026 (Kolkata); the injected clock is NOW."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models import Course, CourseLesson, CourseModule, LearningSession, Project, ProjectSession, RoadmapStage, RoadmapTopic, Task, User
from app.services import auth as auth_service
from app.services import goals, rest, timer

NOW = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)   # 15:30 Mon 23 Nov in Kolkata
TODAY = date(2026, 11, 23)


def d(n: int) -> date:
    return TODAY + timedelta(days=n)


def at(n: int) -> datetime:
    return NOW + timedelta(days=n)


@pytest.fixture
def user(db) -> User:
    return auth_service.create_first_user(db, email="me@example.com", password="correct-horse-9", display_name="Me", timezone="Asia/Kolkata")


def mk_course(db, user, lessons=10, finished_ago=(), target=None, title="RAG course", status="active") -> Course:
    """`finished_ago`: days before today on which lessons were completed (one lesson each); the rest are not started."""
    c = Course(user_id=user.id, title=title, target_date=target, status=status)
    m = CourseModule(title="Module", position=0)
    c.modules.append(m)
    db.add(c)
    db.flush()
    for i in range(lessons):
        lesson = CourseLesson(title=f"Lesson {i + 1}", position=i, course_id=c.id)
        if i < len(finished_ago):
            lesson.status, lesson.completed_at = "completed", at(-finished_ago[i])
        m.lessons.append(lesson)
    db.add(c)
    db.commit()
    return c


def goal(db, user, title="RAG course"):
    return next(g for g in goals.list_goals(db, user, NOW) if g["title"] == title)


# ============================== goals: pace ==============================


def test_only_active_courses_with_a_target_date_are_goals(db, user):
    mk_course(db, user, title="No date")
    mk_course(db, user, title="Paused", target=d(10), status="paused")
    mk_course(db, user, title="Real", target=d(10))
    assert [g["title"] for g in goals.list_goals(db, user, NOW)] == ["Real"]


def test_a_course_on_pace_is_on_track(db, user):
    # 14 lessons done in the last 14 days = 1 a day; 10 left with 20 days to go
    mk_course(db, user, lessons=24, finished_ago=range(14), target=d(19))
    g = goal(db, user)
    assert g["status"] == "on_track" and not g["warning"]
    assert g["remaining"] == 10 and g["days_left"] == 20 and g["recent_per_day"] == 1.0 and g["projected_date"] == d(10)


def test_a_course_behind_pace_warns_with_the_projected_date(db, user):
    # 7 done in 14 days (0.5 a day), 20 left, 10 days to go -> needs 2 a day, would finish 40 days out
    mk_course(db, user, lessons=27, finished_ago=range(7), target=d(9))
    g = goal(db, user)
    assert g["status"] == "behind" and g["warning"]
    assert g["needed_per_day"] == 2.0 and g["projected_date"] == d(40)
    assert "31 days after" in g["message"] and "3.5 lessons a week" in g["message"] and "2 lessons a day" in g["message"]


def test_a_course_past_its_date_is_overdue(db, user):
    mk_course(db, user, lessons=5, finished_ago=[1], target=d(-2))
    g = goal(db, user)
    assert g["status"] == "overdue" and g["warning"] and g["days_left"] == 0 and "4 lessons left" in g["message"]


def test_a_finished_course_is_done_not_overdue(db, user):
    mk_course(db, user, lessons=3, finished_ago=[5, 6, 7], target=d(-2))
    g = goal(db, user)
    assert g["status"] == "done" and not g["warning"]


def test_nothing_finished_recently_is_stalled(db, user):
    mk_course(db, user, lessons=10, finished_ago=[30, 31], target=d(30))
    g = goal(db, user)
    assert g["status"] == "stalled" and g["warning"] and g["projected_date"] is None and "14 days" in g["message"]


def test_a_new_goal_with_plenty_of_time_does_not_nag(db, user):
    mk_course(db, user, lessons=10, target=d(60))
    g = goal(db, user)
    assert g["status"] == "not_started" and not g["warning"] and g["projected_date"] is None


def test_a_new_goal_that_needs_a_lesson_a_day_does_warn(db, user):
    mk_course(db, user, lessons=10, target=d(5))
    g = goal(db, user)
    assert g["status"] == "not_started" and g["warning"] and "Start soon" in g["message"]


def test_a_course_with_no_lessons_is_unknown_and_never_guessed(db, user):
    mk_course(db, user, lessons=0, target=d(10))
    g = goal(db, user)
    assert g["status"] == "unknown" and not g["warning"] and g["projected_date"] is None


def test_rest_days_before_the_target_are_not_counted_as_days_to_work(db, user):
    mk_course(db, user, lessons=10, finished_ago=range(14), target=d(9))
    assert goal(db, user)["days_left"] == 10
    rest.add(db, user, d(2), None, NOW)
    rest.add(db, user, d(3), None, NOW)
    assert goal(db, user)["days_left"] == 8


def test_the_target_day_itself_counts(db, user):
    mk_course(db, user, lessons=4, finished_ago=range(14), target=TODAY)
    assert goal(db, user)["days_left"] == 1


def test_lessons_completed_late_at_night_land_on_the_local_day(db, user):
    # 23:30 UTC on the 21st is 05:00 on the 22nd in Kolkata, so it is inside the window either way; check the boundary day
    c = mk_course(db, user, lessons=4, target=d(30))
    lesson = c.modules[0].lessons[0]
    lesson.status, lesson.completed_at = "completed", datetime(2026, 11, 9, 19, 0, tzinfo=timezone.utc)   # 00:30 on the 10th local = 13 days ago
    db.commit()
    assert goal(db, user)["recent_per_day"] == round(1 / 14, 2)
    lesson.completed_at = datetime(2026, 11, 9, 17, 0, tzinfo=timezone.utc)   # 22:30 on the 9th local = 14 days ago: outside the window
    db.commit()
    assert goal(db, user)["recent_per_day"] == 0.0


def test_projects_use_milestones_and_tasks(db, user):
    p = Project(user_id=user.id, title="RAG bot", status="active", target_date=d(40))
    db.add(p)
    db.commit()
    from app.models import ProjectMilestone
    db.add_all([
        ProjectMilestone(project_id=p.id, title="Ingest", status="done", completed_at=at(-1), position=0),
        ProjectMilestone(project_id=p.id, title="Search", status="pending", position=1),
        Task(user_id=user.id, project_id=p.id, title="Write tests", status="pending"),
        Task(user_id=user.id, project_id=p.id, title="Dropped", status="cancelled"),
    ])
    db.commit()
    g = goal(db, user, "RAG bot")
    assert (g["kind"], g["unit"], g["total"], g["done"], g["remaining"]) == ("project", "items", 3, 1, 2)
    assert g["status"] == "on_track"


def test_goals_are_per_user(db, user):
    mk_course(db, user, target=d(10))
    other = User(id=2, email="o@example.com", password_hash="x", display_name="O", timezone="UTC")
    db.add(other)
    db.commit()
    assert goals.list_goals(db, other, NOW) == []


def test_warnings_returns_only_the_ones_to_worry_about(db, user):
    mk_course(db, user, lessons=27, finished_ago=range(7), target=d(9), title="Behind")
    mk_course(db, user, lessons=24, finished_ago=range(14), target=d(19), title="Fine")
    assert [g["title"] for g in goals.warnings(db, user, NOW)] == ["Behind"]


def test_worst_goals_sort_first(db, user):
    mk_course(db, user, lessons=24, finished_ago=range(14), target=d(19), title="Fine")
    mk_course(db, user, lessons=27, finished_ago=range(7), target=d(9), title="Behind")
    mk_course(db, user, lessons=5, finished_ago=[1], target=d(-2), title="Late")
    assert [g["title"] for g in goals.list_goals(db, user, NOW)] == ["Late", "Behind", "Fine"]


# ============================== timer ==============================


def mk_project(db, user, title="RAG bot") -> Project:
    p = Project(user_id=user.id, title=title, status="active")
    db.add(p)
    db.commit()
    return p


def test_a_timer_starts_runs_and_reports_elapsed_time(db, user):
    p = mk_project(db, user)
    assert timer.view(db, user, NOW) is None
    v = timer.start(db, user, "project", p.id, NOW)
    assert v["label"] == "RAG bot" and v["logs_to"] == "Project: RAG bot" and v["elapsed_seconds"] == 0
    assert timer.view(db, user, NOW + timedelta(minutes=5, seconds=10))["elapsed_seconds"] == 310


def test_only_one_timer_at_a_time(db, user):
    p = mk_project(db, user)
    timer.start(db, user, "project", p.id, NOW)
    with pytest.raises(timer.Conflict, match="already running"):
        timer.start(db, user, "project", p.id, NOW)


def test_stopping_a_project_timer_logs_a_development_session(db, user):
    p = mk_project(db, user)
    timer.start(db, user, "project", p.id, NOW)
    out = timer.stop(db, user, summary="Built the chunker", now=NOW + timedelta(minutes=47, seconds=20))
    assert out["minutes"] == 47 and out["logged_to"] == "project" and out["target_id"] == p.id
    s = db.query(ProjectSession).one()
    assert (s.project_id, s.minutes, s.summary, s.date) == (p.id, 47, "Built the chunker", TODAY)
    assert timer.view(db, user, NOW) is None


def test_a_project_timer_without_a_summary_says_what_it_was_on(db, user):
    p = mk_project(db, user)
    timer.start(db, user, "project", p.id, NOW)
    timer.stop(db, user, now=NOW + timedelta(minutes=30))
    assert db.query(ProjectSession).one().summary == "Worked on RAG bot"


def test_a_timer_under_half_a_minute_still_logs_one_minute(db, user):
    p = mk_project(db, user)
    timer.start(db, user, "project", p.id, NOW)
    assert timer.stop(db, user, now=NOW + timedelta(seconds=5))["minutes"] == 1


def test_the_minutes_can_be_corrected_when_stopping(db, user):
    p = mk_project(db, user)
    timer.start(db, user, "project", p.id, NOW)
    out = timer.stop(db, user, minutes=20, now=NOW + timedelta(hours=3))
    assert out["minutes"] == 20 and db.query(ProjectSession).one().minutes == 20


def test_a_timer_left_running_for_over_a_day_must_be_corrected(db, user):
    p = mk_project(db, user)
    timer.start(db, user, "project", p.id, NOW)
    with pytest.raises(timer.RuleError, match="24 hours"):
        timer.stop(db, user, now=NOW + timedelta(hours=30))
    assert timer.view(db, user, NOW + timedelta(hours=30)) is not None   # still running: nothing was lost
    assert db.query(ProjectSession).count() == 0
    timer.stop(db, user, minutes=90, now=NOW + timedelta(hours=30))
    assert db.query(ProjectSession).one().minutes == 90


def test_discarding_logs_nothing(db, user):
    p = mk_project(db, user)
    timer.start(db, user, "project", p.id, NOW)
    timer.discard(db, user)
    assert timer.view(db, user, NOW) is None and db.query(ProjectSession).count() == 0
    with pytest.raises(timer.NotFound):
        timer.discard(db, user)
    with pytest.raises(timer.NotFound):
        timer.stop(db, user, now=NOW)


def test_a_task_of_a_project_logs_to_the_project_and_the_task(db, user):
    p = mk_project(db, user)
    t = Task(user_id=user.id, title="Add retrieval", project_id=p.id, task_type="project_dev", actual_minutes=10)
    db.add(t)
    db.commit()
    timer.start(db, user, "task", t.id, NOW)
    out = timer.stop(db, user, summary="Top-k search", now=NOW + timedelta(minutes=25))
    assert out["logged_to"] == "project"
    s = db.query(ProjectSession).one()
    assert s.project_id == p.id and s.task_id == t.id and s.minutes == 25
    db.refresh(t)
    assert t.actual_minutes == 35


def test_a_plain_task_only_gets_actual_minutes(db, user):
    t = Task(user_id=user.id, title="Read paper")
    db.add(t)
    db.commit()
    timer.start(db, user, "task", t.id, NOW)
    out = timer.stop(db, user, now=NOW + timedelta(minutes=40))
    assert out["logged_to"] == "task" and out["target_id"] is None
    db.refresh(t)
    assert t.actual_minutes == 40 and db.query(ProjectSession).count() == 0 and db.query(LearningSession).count() == 0


def test_a_finished_task_cannot_be_timed(db, user):
    t = Task(user_id=user.id, title="Done", status="completed", completed_at=NOW)
    db.add(t)
    db.commit()
    with pytest.raises(timer.RuleError, match="finished"):
        timer.start(db, user, "task", t.id, NOW)


def test_a_lesson_timer_logs_a_study_session_on_the_course(db, user):
    c = mk_course(db, user, lessons=3)
    lesson = c.modules[0].lessons[1]
    timer.start(db, user, "lesson", lesson.id, NOW)
    out = timer.stop(db, user, now=NOW + timedelta(minutes=33))
    assert out["logged_to"] == "course" and out["target_id"] == c.id
    s = db.query(LearningSession).one()
    assert (s.course_id, s.lesson_id, s.minutes, s.date) == (c.id, lesson.id, 33, TODAY)


def test_a_course_timer_logs_to_the_course(db, user):
    c = mk_course(db, user, lessons=1)
    timer.start(db, user, "course", c.id, NOW)
    timer.stop(db, user, now=NOW + timedelta(minutes=15))
    s = db.query(LearningSession).one()
    assert s.course_id == c.id and s.lesson_id is None


def test_a_topic_timer_logs_study_time_and_starts_the_topic(db, user):
    stage = RoadmapStage(user_id=user.id, title="Basics", position=0)
    topic = RoadmapTopic(user_id=user.id, title="Embeddings", position=0)
    stage.topics.append(topic)
    db.add(stage)
    db.commit()
    timer.start(db, user, "topic", topic.id, NOW)
    out = timer.stop(db, user, now=NOW + timedelta(minutes=50))
    assert out["logged_to"] == "topic" and out["target_id"] == topic.id
    assert db.query(LearningSession).one().roadmap_topic_id == topic.id
    db.refresh(topic)
    assert topic.status == "in_progress"


def test_you_cannot_time_something_that_is_not_yours_or_missing(db, user):
    for kind in ("project", "task", "lesson", "course", "topic"):
        with pytest.raises(timer.NotFound):
            timer.start(db, user, kind, 999, NOW)
    with pytest.raises(timer.RuleError):
        timer.start(db, user, "habit", 1, NOW)


def test_a_failed_log_keeps_the_timer(db, user):
    p = mk_project(db, user)
    timer.start(db, user, "project", p.id, NOW)
    with pytest.raises(timer.RuleError, match="at least 3"):
        timer.stop(db, user, summary="ab", now=NOW + timedelta(minutes=5))
    assert timer.view(db, user, NOW + timedelta(minutes=5)) is not None
    assert db.query(ProjectSession).count() == 0


def test_another_users_things_cannot_be_timed(db, user):
    other = User(id=2, email="o@example.com", password_hash="x", display_name="O", timezone="UTC")
    db.add(other)
    db.commit()
    theirs = mk_project(db, other, "Theirs")
    with pytest.raises(timer.NotFound):
        timer.start(db, user, "project", theirs.id, NOW)
