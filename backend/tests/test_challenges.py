"""Daily challenge: planning rules, evidence quality, completion, excusing, computed missed/streaks, suggestions, isolation."""
from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.models import DailyChallenge, Project, ProjectMilestone, ProjectSession, User
from app.schemas import challenges as s
from app.schemas import projects as ps
from app.services import auth as auth_service
from app.services import challenges as svc
from app.services import projects

NOW = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)   # 15:30 Mon 23 Nov in Kolkata
TODAY = date(2026, 11, 23)
REPO = "https://github.com/me/rag-bot"
SUMMARY = "Implemented the retrieval step: chunking, embeddings and a top-k search over the vector store."


def d(n: int) -> date:
    return TODAY + timedelta(days=n)


def at(n: int) -> datetime:
    return NOW + timedelta(days=n)


@pytest.fixture
def user(db) -> User:
    return auth_service.create_first_user(db, email="me@example.com", password="correct-horse-9", display_name="Me", timezone="Asia/Kolkata")


@pytest.fixture
def other(db, user) -> User:
    u = User(id=2, email="o@example.com", password_hash="x", display_name="O", timezone="UTC")
    db.add(u)
    db.commit()
    return u


def project(db, user, title="RAG chatbot", **kw) -> int:
    return projects.create_project(db, user, ps.ProjectCreate(title=title, **kw), now=NOW)["id"]


def plan(db, user, pid=None, day=None, now=NOW, **kw) -> dict:
    body = dict(mode="existing_project", project_id=pid, planned_task="Add the retrieval step", date=day)
    body.update(kw)
    return svc.create_challenge(db, user, s.ChallengeCreate(**body), now=now)


def evidence(**kw) -> s.CompleteIn:
    base = dict(summary=SUMMARY, repo_url=REPO, commit_sha="a1b2c3d4e5f6", commit_message="Add retrieval step to RAG pipeline", minutes=90)
    base.update(kw)
    return s.CompleteIn(**base)


def finish(db, user, cid, now=NOW, **kw):
    return svc.complete_challenge(db, user, cid, evidence(**kw), now=now)


# ============================== schema validation ==============================


@pytest.mark.parametrize("body", [
    dict(mode="existing_project"),                                                   # no project
    dict(mode="existing_project", project_id=1, new_project={"title": "X"}),         # both
    dict(mode="new_project"),                                                        # no description of the new project
    dict(mode="new_project", project_id=1, new_project={"title": "X"}),
    dict(mode="existing_project", project_id=1, planned_task="x"),                    # too short
    dict(mode="existing_project", project_id=1, estimated_minutes=0),
    dict(mode="other", project_id=1),
    dict(mode="existing_project", project_id=1, status="completed"),                  # unknown field
])
def test_plan_validation(body):
    body.setdefault("planned_task", "Add the retrieval step")
    with pytest.raises(ValidationError):
        s.ChallengeCreate(**body)


@pytest.mark.parametrize("kw", [
    dict(summary="too short"), dict(commit_sha="xyz"), dict(commit_sha="abc"), dict(commit_sha="g" * 10), dict(minutes=0), dict(minutes=1441),
    dict(repo_url="https://gitlab.com/me/x"), dict(repo_url="not a url"), dict(commit_message="ab"), dict(commit_message="ok"),
])
def test_evidence_validation(kw):
    with pytest.raises(ValidationError):
        evidence(**kw)


def test_commit_sha_is_lowercased_and_repo_normalised():
    e = evidence(commit_sha="A1B2C3D", repo_url="https://github.com/me/rag-bot.git/")
    assert e.commit_sha == "a1b2c3d" and e.repo_url == REPO


# ============================== planning ==============================


def test_plan_for_an_existing_project(db, user):
    pid = project(db, user)
    c = plan(db, user, pid)
    assert (c["date"], c["status"], c["mode"], c["project"]["id"]) == (TODAY, "planned", "existing_project", pid)
    assert c["can_complete"] is True and c["can_edit"] is True and c["verification_status"] == "unverified"


def test_plan_for_a_new_project_creates_it(db, user):
    c = svc.create_challenge(db, user, s.ChallengeCreate(mode="new_project", planned_task="Scaffold the service",
                                                         new_project=s.NewProject(title="Agent playground", repo_url=REPO)), now=NOW)
    p = db.get(Project, c["project"]["id"])
    assert (p.title, p.origin, p.repo_url, p.start_date) == ("Agent playground", "new", REPO, TODAY)


def test_new_project_name_clash_is_a_conflict_and_creates_nothing(db, user):
    project(db, user, "Agent playground")
    with pytest.raises(svc.Conflict):
        svc.create_challenge(db, user, s.ChallengeCreate(mode="new_project", planned_task="Scaffold",
                                                         new_project=s.NewProject(title="agent PLAYGROUND")), now=NOW)
    assert db.query(DailyChallenge).count() == 0


def test_one_challenge_per_day(db, user):
    pid = project(db, user)
    plan(db, user, pid)
    with pytest.raises(svc.Conflict):
        plan(db, user, pid)
    assert plan(db, user, pid, day=d(1))["date"] == d(1)       # a different day is fine


def test_cannot_plan_the_past_or_use_an_inactive_or_foreign_project(db, user, other):
    pid = project(db, user)
    with pytest.raises(svc.RuleError, match="passed"):
        plan(db, user, pid, day=d(-1))
    projects.update_project(db, user, pid, ps.ProjectUpdate(status="paused"), now=NOW)
    with pytest.raises(svc.RuleError, match="active"):
        plan(db, user, pid)
    theirs = Project(user_id=other.id, title="Theirs")
    db.add(theirs)
    db.commit()
    with pytest.raises(svc.NotFound):
        plan(db, user, theirs.id)


def test_edit_start_and_delete_rules(db, user):
    pid = project(db, user)
    c = plan(db, user, pid)
    out = svc.update_challenge(db, user, c["id"], s.ChallengeUpdate(planned_task="Something else", estimated_minutes=45), now=NOW)
    assert (out["planned_task"], out["estimated_minutes"]) == ("Something else", 45)
    with pytest.raises(svc.RuleError):                       # the planned task can't be blanked out
        svc.update_challenge(db, user, c["id"], s.ChallengeUpdate(planned_task=None), now=NOW)
    assert svc.start_challenge(db, user, c["id"], now=NOW)["status"] == "in_progress"
    with pytest.raises(svc.RuleError):
        svc.start_challenge(db, user, c["id"], now=NOW)
    svc.delete_challenge(db, user, c["id"])
    assert db.query(DailyChallenge).count() == 0


def test_a_future_day_cannot_be_started_or_completed(db, user):
    pid = project(db, user)
    c = plan(db, user, pid, day=d(2))
    assert c["can_complete"] is False
    with pytest.raises(svc.RuleError):
        svc.start_challenge(db, user, c["id"], now=NOW)
    with pytest.raises(svc.RuleError, match="before its day"):
        finish(db, user, c["id"])


# ============================== completion needs real evidence ==============================


def test_complete_with_evidence(db, user):
    pid = project(db, user)
    c = plan(db, user, pid)
    out = finish(db, user, c["id"])
    assert (out["status"], out["verification_status"], out["actual_minutes"], out["commit_sha"]) == ("completed", "unverified", 90, "a1b2c3d4e5f6")
    assert out["can_complete"] is False and out["can_edit"] is False and out["completed_at"] is not None
    # a development session was recorded on the project, so project time agrees
    sess = db.query(ProjectSession).one()
    assert (sess.project_id, sess.minutes, sess.date) == (pid, 90, TODAY)
    assert db.get(Project, pid).repo_url == REPO            # the project learned its repository
    assert svc.today_view(db, user, now=NOW)["stats"]["completed"] == 1


@pytest.mark.parametrize("message", ["update", "Update", "wip", "fix", "initial commit", "Initial commit.", "asdf", "...", "done done", "a b"])
def test_meaningless_commit_messages_do_not_count(db, user, message):
    c = plan(db, user, project(db, user))
    with pytest.raises(svc.RuleError, match="commit message"):
        finish(db, user, c["id"], commit_message=message)
    assert db.get(DailyChallenge, c["id"]).status == "planned" and db.query(ProjectSession).count() == 0


@pytest.mark.parametrize("summary", ["a a a a a a a a a a a a a a a a a a a a a a a a a a a a a", "word " * 20, "...................................... ."])
def test_meaningless_summaries_do_not_count(db, user, summary):
    c = plan(db, user, project(db, user))
    with pytest.raises(svc.RuleError, match="actually implemented"):
        finish(db, user, c["id"], summary=summary)


def test_summary_cannot_just_repeat_the_commit_message(db, user):
    c = plan(db, user, project(db, user))
    msg = "Add retrieval step to the RAG pipeline with embeddings"
    with pytest.raises(svc.RuleError, match="repeat"):
        finish(db, user, c["id"], commit_message=msg, summary=msg + "!")


def test_evidence_must_match_the_projects_repository(db, user):
    pid = project(db, user, repo_url=REPO)
    c = plan(db, user, pid)
    with pytest.raises(svc.RuleError, match="repository is"):
        finish(db, user, c["id"], repo_url="https://github.com/me/other-repo")
    assert finish(db, user, c["id"])["status"] == "completed"


def test_the_same_commit_cannot_count_for_two_days(db, user):
    pid = project(db, user)
    finish(db, user, plan(db, user, pid)["id"])
    tomorrow = plan(db, user, pid, day=d(1), now=NOW)
    for sha in ("a1b2c3d4e5f6", "a1b2c3d", "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6aaaa"):      # same commit, short or long form
        with pytest.raises(svc.RuleError, match="already used"):
            finish(db, user, tomorrow["id"], now=at(1), commit_sha=sha)
    assert finish(db, user, tomorrow["id"], now=at(1), commit_sha="9f8e7d6c5b4a")["status"] == "completed"


def test_milestone_must_belong_to_the_project(db, user):
    a, b = project(db, user, "A"), project(db, user, "B")
    ms = projects.add_milestone(db, user, b, ps.MilestoneCreate(title="Ship it"), now=NOW)["milestones"][0]["id"]
    c = plan(db, user, a)
    with pytest.raises(svc.RuleError, match="milestone"):
        finish(db, user, c["id"], milestone_id=ms)
    assert db.query(ProjectSession).count() == 0


def test_milestone_is_linked_but_not_completed_by_the_challenge(db, user):
    pid = project(db, user)
    ms = projects.add_milestone(db, user, pid, ps.MilestoneCreate(title="Ship it"), now=NOW)["milestones"][0]["id"]
    out = finish(db, user, plan(db, user, pid)["id"], milestone_id=ms)
    assert out["milestone"]["id"] == ms and db.get(ProjectMilestone, ms).status == "pending"


def test_cannot_complete_twice_or_on_a_later_day(db, user):
    pid = project(db, user)
    c = plan(db, user, pid)
    finish(db, user, c["id"])
    with pytest.raises(svc.Conflict):
        finish(db, user, c["id"], commit_sha="9f8e7d6c5b4a")
    old = plan(db, user, project(db, user, "Other"), day=d(1))
    with pytest.raises(svc.RuleError, match="passed"):
        finish(db, user, old["id"], now=at(3))


def test_completed_day_cannot_be_deleted_edited_or_excused(db, user):
    c = plan(db, user, project(db, user))
    finish(db, user, c["id"])
    with pytest.raises(svc.RuleError):
        svc.delete_challenge(db, user, c["id"])
    with pytest.raises(svc.RuleError):
        svc.update_challenge(db, user, c["id"], s.ChallengeUpdate(planned_task="changed"), now=NOW)
    with pytest.raises(svc.RuleError):
        svc.excuse_day(db, user, s.ExcuseIn(reason="I was away"), now=NOW)


def test_database_refuses_a_completed_day_without_evidence(db, user):
    db.add(DailyChallenge(user_id=user.id, date=TODAY, mode="existing_project", planned_task="x", status="completed"))
    with pytest.raises(IntegrityError):
        db.commit()


# ============================== excusing ==============================


def test_excuse_needs_a_real_reason_and_not_the_future(db, user):
    with pytest.raises(ValidationError):
        s.ExcuseIn(reason="no")
    with pytest.raises(ValidationError):
        s.ExcuseIn(reason="   ")
    with pytest.raises(svc.RuleError, match="passed"):
        svc.excuse_day(db, user, s.ExcuseIn(date=d(1), reason="Planning ahead"), now=NOW)


def test_excuse_today_past_and_an_existing_plan(db, user):
    out = svc.excuse_day(db, user, s.ExcuseIn(date=d(-3), reason="Was travelling"), now=NOW)
    assert (out["status"], out["excuse_reason"], out["project"]) == ("excused", "Was travelling", None)
    c = plan(db, user, project(db, user))
    assert svc.excuse_day(db, user, s.ExcuseIn(reason="Fever"), now=NOW)["id"] == c["id"]
    with pytest.raises(svc.Conflict):
        svc.excuse_day(db, user, s.ExcuseIn(reason="Fever again"), now=NOW)
    svc.delete_challenge(db, user, c["id"])                                         # removing the excuse
    assert db.query(DailyChallenge).filter_by(date=TODAY).count() == 0


def test_an_excused_day_cannot_be_completed(db, user):
    c = plan(db, user, project(db, user))
    svc.excuse_day(db, user, s.ExcuseIn(reason="Fever"), now=NOW)
    with pytest.raises(svc.RuleError, match="Remove the excuse"):
        finish(db, user, c["id"])


def test_database_refuses_an_excused_day_without_reason(db, user):
    db.add(DailyChallenge(user_id=user.id, date=TODAY, mode="existing_project", planned_task="x", status="excused"))
    with pytest.raises(IntegrityError):
        db.commit()


# ============================== missed is computed, never stored ==============================


def test_a_planned_day_that_passed_is_missed_and_stays_planned_in_the_database(db, user):
    c = plan(db, user, project(db, user))
    assert svc.get_challenge(db, user, c["id"], now=NOW)["status"] == "planned"
    later = svc.get_challenge(db, user, c["id"], now=at(1))
    assert later["status"] == "missed" and later["can_complete"] is False and later["can_edit"] is False
    assert db.get(DailyChallenge, c["id"]).status == "planned"


def test_calendar_marks_gaps_missed_only_after_you_started(db, user):
    finish(db, user, plan(db, user, project(db, user), day=d(-5), now=at(-5))["id"], now=at(-5))
    cal = svc.calendar(db, user, d(-7), d(1), now=NOW)
    by = {x["date"]: x["status"] for x in cal["days"]}
    assert by[d(-7)] == by[d(-6)] == "none"                # before the first record: not missed
    assert by[d(-5)] == "completed"
    assert by[d(-4)] == by[d(-1)] == "missed"
    assert by[d(0)] == by[d(1)] == "none"                  # today is still open; the future is empty
    assert cal["stats"]["missed"] == 4


def test_calendar_limits(db, user):
    with pytest.raises(svc.RuleError):
        svc.calendar(db, user, d(0), d(-1), now=NOW)
    with pytest.raises(svc.RuleError):
        svc.calendar(db, user, d(-500), d(0), now=NOW)


# ============================== streaks ==============================


def days(*ns):
    return {d(n) for n in ns}


def test_streak_pure_function():
    assert svc.streaks(set(), set(), TODAY) == (0, 0)
    assert svc.streaks(days(-2, -1, 0), set(), TODAY) == (3, 3)
    assert svc.streaks(days(-2, -1), set(), TODAY) == (2, 2)                  # today not done yet doesn't break it
    assert svc.streaks(days(-3, -2), set(), TODAY) == (0, 2)                  # yesterday missed: broken
    assert svc.streaks(days(-4, -3, -1, 0), set(), TODAY) == (2, 2)
    assert svc.streaks(days(-4, -3, -1, 0), days(-2), TODAY) == (4, 4)        # an excused day is skipped, not counted
    assert svc.streaks(days(0), days(-5, -4), TODAY) == (1, 1)


def test_stats_from_records(db, user):
    pid = project(db, user)
    for n, sha in ((-3, "aaaaaaa1"), (-2, "aaaaaaa2"), (-1, "aaaaaaa3")):
        finish(db, user, plan(db, user, pid, day=d(n), now=at(n))["id"], now=at(n), commit_sha=sha, minutes=60)
    out = svc.today_view(db, user, now=NOW)["stats"]
    assert (out["completed"], out["missed"], out["current_streak"], out["longest_streak"], out["total_minutes"]) == (3, 0, 3, 3, 180)
    assert out["completion_rate"] == 100 and out["first_day"] == d(-3)
    assert svc.stats(db, user, now=at(2))["current_streak"] == 0 and svc.stats(db, user, now=at(2))["missed"] == 2


def test_completion_rate_floors(db, user):
    pid = project(db, user)
    finish(db, user, plan(db, user, pid, day=d(-3), now=at(-3))["id"], now=at(-3), commit_sha="aaaaaaa1")
    assert svc.stats(db, user, now=NOW)["completion_rate"] == 33          # 1 done, 2 missed -> 33, never rounded up


# ============================== suggestions ==============================


def test_suggestions_come_from_projects_roadmap_and_courses(db, user):
    from app.services import roadmap

    roadmap.ensure_seeded(db, user)
    pid = project(db, user, "RAG chatbot")
    projects.add_milestone(db, user, pid, ps.MilestoneCreate(title="Retrieval works"), now=NOW)
    paused = project(db, user, "Old one")
    projects.update_project(db, user, paused, ps.ProjectUpdate(status="paused"), now=NOW)
    got = svc.suggestions(db, user, now=NOW)
    sources = [g["source"] for g in got]
    assert sources[0] == "project" and "roadmap" in sources
    first = got[0]
    assert first["project_id"] == pid and first["mode"] == "existing_project" and "Retrieval works" in first["planned_task"]
    assert all(g["project_id"] != paused for g in got)
    assert next(g for g in got if g["source"] == "roadmap")["mode"] == "new_project"


def test_suggestions_are_empty_with_no_data(db, user):
    assert svc.suggestions(db, user, now=NOW) == []


def test_no_suggestions_once_the_day_is_done(db, user):
    pid = project(db, user)
    finish(db, user, plan(db, user, pid)["id"])
    assert svc.today_view(db, user, now=NOW)["suggestions"] == []


def test_the_least_recently_worked_project_is_suggested_first(db, user):
    a, b = project(db, user, "A"), project(db, user, "B")
    projects.log_session(db, user, a, ps.SessionCreate(minutes=30, summary="did things"), now=NOW)
    assert svc.suggestions(db, user, now=NOW)[0]["project_id"] == b


def test_the_last_challenge_project_is_noted(db, user):
    pid = project(db, user)
    finish(db, user, plan(db, user, pid)["id"])
    out = svc.suggestions(db, user, now=at(1))
    assert out[0]["project_id"] == pid and "last challenge" in out[0]["detail"]


# ============================== isolation ==============================


def test_other_users_challenges_are_not_reachable(db, user, other):
    db.add(DailyChallenge(user_id=other.id, date=TODAY, mode="existing_project", planned_task="secret", status="planned"))
    db.commit()
    cid = db.query(DailyChallenge).one().id
    for call in (lambda: svc.get_challenge(db, user, cid, now=NOW), lambda: svc.start_challenge(db, user, cid, now=NOW),
                 lambda: svc.delete_challenge(db, user, cid), lambda: finish(db, user, cid)):
        with pytest.raises(svc.NotFound):
            call()
    assert svc.today_view(db, user, now=NOW)["challenge"] is None and svc.history(db, user, now=NOW) == []
    assert plan(db, user, project(db, user))["date"] == TODAY                  # their row on the same day doesn't block yours
