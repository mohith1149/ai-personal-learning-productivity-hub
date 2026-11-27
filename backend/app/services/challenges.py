"""Daily AI project challenge: one primary project task per calendar day, with evidence and accountability.

Rules (enforced here AND by DB CHECKs on `daily_challenges`):
  * One challenge per user per day. A day is planned for today or the future (never the past) and works on a NEW project (created
    with the plan) or an EXISTING active project.
  * A day is completed only for TODAY and only with evidence: a meaningful summary, a GitHub repo link, a commit hash and a meaningful
    commit message, and the time spent. Junk summaries/messages ("update", "wip", one word...) don't count; one commit can't be used for two
    days. The evidence is stored as 'unverified': nothing is checked against GitHub until Phase 4, which is the step that can tell whether a
    commit really exists and isn't empty. Until then this is an honour-system record, and the app says so.
  * 'missed' is never stored. A planned/started day that has passed, or a past day with no record (once you have started), is shown as missed.
    That means nothing silently changes the data and nothing is auto-completed.
  * An excused day needs a reason and may be set for today or any past day; it neither adds to nor breaks the streak.
  * Completing a day also records a normal development session on the project, so project time, the planner and the project page agree.
  * Streaks and totals are computed from the records, never stored.
"""
import re
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.timeutil import user_today
from app.models import Course, DailyChallenge, Project, ProjectMilestone, RoadmapStage, RoadmapTopic, Task, User
from app.schemas import challenges as s
from app.schemas import projects as ps
from app.services import courses, projects, rest


class NotFound(Exception):
    pass


class RuleError(ValueError):
    """A business-rule violation (HTTP 422)."""


class Conflict(Exception):
    """Clashes with existing data (HTTP 409)."""


MAX_CALENDAR_DAYS = 400
JUNK_MESSAGES = {"update", "updates", "fix", "fixes", "wip", "commit", "changes", "change", "test", "tests", "tmp", "misc", "stuff",
                 "initial commit", "first commit", "asdf", "done", "work", "edit", "edits", "."}
OPEN = ("planned", "in_progress")


# ============================== evidence quality ==============================


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+", text)


def check_commit_message(message: str) -> None:
    cleaned = " ".join(_words(message)).lower()
    if cleaned in JUNK_MESSAGES or len({w.lower() for w in _words(message)}) < 2 or len(cleaned) < 8:
        raise RuleError("That commit message doesn't describe any work. Use a real one, like 'Add retrieval step to the RAG pipeline'")


def check_summary(summary: str, commit_message: str) -> None:
    words = _words(summary)
    if len(words) < 5 or len({w.lower() for w in words}) < 4:
        raise RuleError("Describe what you actually implemented in a few real sentences")
    if " ".join(words).lower() == " ".join(_words(commit_message)).lower():
        raise RuleError("The summary can't just repeat the commit message. Say what you built and what you learned")


# ============================== lookups ==============================


def _get(db: Session, user: User, challenge_id: int) -> DailyChallenge:
    c = db.scalar(select(DailyChallenge).where(DailyChallenge.id == challenge_id, DailyChallenge.user_id == user.id))
    if c is None:
        raise NotFound("Challenge not found")
    return c


def _on(db: Session, user: User, day: date) -> DailyChallenge | None:
    return db.scalar(select(DailyChallenge).where(DailyChallenge.user_id == user.id, DailyChallenge.date == day))


def _effective(c: DailyChallenge, today: date) -> str:
    return "missed" if c.status in OPEN and c.date < today else c.status


def _out(c: DailyChallenge, today: date) -> dict:
    status = _effective(c, today)
    return {
        "id": c.id, "date": c.date, "mode": c.mode, "status": status,
        "project": {"id": c.project.id, "title": c.project.title, "repo_url": c.project.repo_url} if c.project else None,
        "planned_task": c.planned_task, "estimated_minutes": c.estimated_minutes, "actual_minutes": c.actual_minutes,
        "implemented_summary": c.implemented_summary, "repo_url": c.repo_url, "commit_sha": c.commit_sha, "commit_message": c.commit_message,
        "evidence_notes": c.evidence_notes, "milestone": {"id": c.milestone.id, "title": c.milestone.title} if c.milestone else None,
        "verification_status": c.verification_status, "excuse_reason": c.excuse_reason, "completed_at": c.completed_at,
        "can_complete": c.date == today and c.status in OPEN,
        "can_edit": c.date >= today and c.status in OPEN,
    }


# ============================== streaks and totals (computed) ==============================


def streaks(completed: set[date], excused: set[date], today: date) -> tuple[int, int]:
    """(current, longest). Completed days count; excused days are skipped (they neither add nor break); anything else breaks.
    Today not being done yet doesn't break the current streak."""
    days = completed | excused
    if not completed:
        return 0, 0
    first = min(days)
    longest = run = 0
    d = first
    while d <= today:
        if d in completed:
            run += 1
            longest = max(longest, run)
        elif d in excused or d == today:
            pass
        else:
            run = 0
        d += timedelta(days=1)
    current, d = 0, today
    while d >= first:
        if d in completed:
            current += 1
        elif d in excused or d == today:
            pass
        else:
            break
        d -= timedelta(days=1)
    return current, longest


def stats(db: Session, user: User, now: datetime | None = None) -> dict:
    today = user_today(user, now)
    rows = list(db.execute(select(DailyChallenge.date, DailyChallenge.status, DailyChallenge.actual_minutes)
                           .where(DailyChallenge.user_id == user.id)))
    first = min((r.date for r in rows), default=None)
    completed = {r.date for r in rows if r.status == "completed"}
    excused = {r.date for r in rows if r.status == "excused"}
    rest_days = {d for d in rest.all_days(db, user) if d <= today}  # planned rest days behave like excused days
    # missed = every day from the first record up to yesterday that is neither completed nor excused
    span = (today - first).days if first and first < today else 0
    missed = sum(1 for i in range(span) if (first + timedelta(days=i)) not in completed | excused | rest_days)
    current, longest = streaks(completed, excused | rest_days, today)
    return {
        "completed": len(completed), "excused": len(excused), "rest_days": len(rest_days), "missed": missed,
        "completion_rate": (100 * len(completed)) // (len(completed) + missed) if completed or missed else 0,
        "current_streak": current, "longest_streak": longest,
        "total_minutes": sum(r.actual_minutes or 0 for r in rows if r.status == "completed"), "first_day": first,
    }


# ============================== suggestions ==============================


def suggestions(db: Session, user: User, now: datetime | None = None) -> list[dict]:
    """Ideas for today, built from your own data: active projects, the roadmap, active courses and yesterday's work. No AI involved."""
    out: list[dict] = []
    active = list(db.scalars(select(Project).where(Project.user_id == user.id, Project.status == "active")
                             .order_by(Project.last_activity_at.is_(None).desc(), Project.last_activity_at, Project.priority, Project.id).limit(4)))
    for p in active:
        milestone = db.scalar(select(ProjectMilestone).where(ProjectMilestone.project_id == p.id, ProjectMilestone.status == "pending")
                              .order_by(ProjectMilestone.position, ProjectMilestone.id))
        task = db.scalar(select(Task).where(Task.user_id == user.id, Task.project_id == p.id, Task.status.in_(("pending", "in_progress")))
                         .order_by(Task.priority, Task.id))
        if milestone:
            what, detail = f"Work towards the milestone '{milestone.title}' in {p.title}", "Next milestone"
        elif task:
            what, detail = f"{task.title} ({p.title})", "Next open task"
        else:
            what, detail = f"Continue {p.title}", "Active project"
        if p.last_activity_at:
            detail += f" · last worked on {p.last_activity_at.date().isoformat()}"
        else:
            detail += " · not worked on yet"
        out.append({"source": "project", "mode": "existing_project", "project_id": p.id, "title": p.title, "detail": detail, "planned_task": what})
    row = db.execute(select(RoadmapTopic, RoadmapStage.title).join(RoadmapStage, RoadmapStage.id == RoadmapTopic.stage_id)
                     .where(RoadmapTopic.user_id == user.id, RoadmapTopic.status != "completed")
                     .order_by(RoadmapTopic.status != "in_progress", RoadmapStage.position, RoadmapTopic.position, RoadmapTopic.id)).first()
    if row:
        topic, stage = row
        out.append({"source": "roadmap", "mode": "new_project", "project_id": None, "title": f"Apply: {topic.title}", "detail": f"{stage} · roadmap topic",
                    "planned_task": f"Build a small project that applies {topic.title}"})
    for course in db.scalars(courses._course_query(user).where(Course.status == "active").order_by(Course.priority, Course.title).limit(2)):
        nxt = courses.next_lesson(course)
        if nxt:
            out.append({"source": "course", "mode": "new_project", "project_id": None, "title": f"Apply: {nxt['title']}", "detail": f"{course.title} · next lesson",
                        "planned_task": f"Build something that applies the lesson '{nxt['title']}'"})
    today = user_today(user, now)
    last = db.scalar(select(DailyChallenge).where(DailyChallenge.user_id == user.id, DailyChallenge.status == "completed", DailyChallenge.date < today)
                     .order_by(DailyChallenge.date.desc()))
    if last and last.project and last.project.status == "active" and not any(o["project_id"] == last.project_id for o in out):
        out.append({"source": "previous", "mode": "existing_project", "project_id": last.project_id, "title": last.project.title,
                    "detail": f"You worked on this on {last.date.isoformat()}", "planned_task": f"Continue {last.project.title}"})
    elif last and last.project and last.project.status == "active":
        for o in out:  # already suggested as a project: note that it was yesterday's work
            if o["project_id"] == last.project_id:
                o["detail"] = (o["detail"] or "") + f" · your last challenge ({last.date.isoformat()})"
    return out


# ============================== reads ==============================


def today_view(db: Session, user: User, now: datetime | None = None) -> dict:
    today = user_today(user, now)
    c = _on(db, user, today)
    return {"date": today, "rest_day": today in rest.all_days(db, user), "challenge": _out(c, today) if c else None, "stats": stats(db, user, now),
            "suggestions": [] if c and c.status in ("completed", "excused") else suggestions(db, user, now)}


def get_challenge(db: Session, user: User, challenge_id: int, now: datetime | None = None) -> dict:
    return _out(_get(db, user, challenge_id), user_today(user, now))


def history(db: Session, user: User, limit: int = 60, now: datetime | None = None) -> list[dict]:
    today = user_today(user, now)
    rows = db.scalars(select(DailyChallenge).where(DailyChallenge.user_id == user.id).order_by(DailyChallenge.date.desc()).limit(limit))
    return [_out(c, today) for c in rows]


def calendar(db: Session, user: User, start: date, end: date, now: datetime | None = None) -> dict:
    if end < start:
        raise RuleError("The end date can't be before the start date")
    if (end - start).days + 1 > MAX_CALENDAR_DAYS:
        raise RuleError(f"Ask for at most {MAX_CALENDAR_DAYS} days at a time")
    today = user_today(user, now)
    first = db.scalar(select(func.min(DailyChallenge.date)).where(DailyChallenge.user_id == user.id))
    rows = {c.date: c for c in db.scalars(select(DailyChallenge).where(DailyChallenge.user_id == user.id, DailyChallenge.date >= start,
                                                                       DailyChallenge.date <= end))}
    rest_days = rest.set_of(db, user, start, end)
    days, d = [], start
    while d <= end:
        c = rows.get(d)
        if c:
            status, title, cid = _effective(c, today), (c.project.title if c.project else None), c.id
            if status == "missed" and d in rest_days:
                status = "rest"
        elif d in rest_days:
            status, title, cid = "rest", None, None
        elif first and first <= d < today:
            status, title, cid = "missed", None, None
        else:
            status, title, cid = "none", None, None
        days.append({"date": d, "status": status, "project_title": title, "challenge_id": cid})
        d += timedelta(days=1)
    return {"start": start, "end": end, "days": days, "stats": stats(db, user, now)}


# ============================== planning ==============================


def create_challenge(db: Session, user: User, data: s.ChallengeCreate, now: datetime | None = None) -> dict:
    today = user_today(user, now)
    day = data.date or today
    if day < today:
        raise RuleError("You can't plan a challenge for a day that has passed")
    if _on(db, user, day):
        raise Conflict("That day already has a challenge")
    if data.mode == "existing_project":
        try:
            project = projects._get(db, user, data.project_id)
        except projects.NotFound:
            raise NotFound("Project not found") from None
        if project.status != "active":
            raise RuleError("Only an active project can be today's challenge. Reactivate it on the Projects page first")
        project_id = project.id
    else:
        np = data.new_project
        if projects._name_taken(db, user, np.title):
            raise Conflict("You already have a project with that name. Choose 'existing project' to continue it")
        created = projects.create_project(db, user, ps.ProjectCreate(title=np.title, origin="new", description=np.description, repo_url=np.repo_url),
                                          now)
        project_id = created["id"]
    c = DailyChallenge(user_id=user.id, date=day, mode=data.mode, project_id=project_id, planned_task=data.planned_task.strip(),
                       estimated_minutes=data.estimated_minutes, status="planned")
    db.add(c)
    db.commit()
    return _out(c, today)


def update_challenge(db: Session, user: User, challenge_id: int, data: s.ChallengeUpdate, now: datetime | None = None) -> dict:
    c, today = _get(db, user, challenge_id), user_today(user, now)
    if not (c.date >= today and c.status in OPEN):
        raise RuleError("Only a planned challenge for today or later can be edited")
    changes = data.model_dump(exclude_unset=True)
    if changes.get("planned_task", "x") is None:
        raise RuleError("The planned task can't be empty")
    for k, v in changes.items():
        setattr(c, k, v.strip() if isinstance(v, str) else v)
    db.commit()
    return _out(c, today)


def start_challenge(db: Session, user: User, challenge_id: int, now: datetime | None = None) -> dict:
    c, today = _get(db, user, challenge_id), user_today(user, now)
    if c.date != today or c.status != "planned":
        raise RuleError("Only today's planned challenge can be started")
    c.status = "in_progress"
    db.commit()
    return _out(c, today)


def delete_challenge(db: Session, user: User, challenge_id: int, now: datetime | None = None) -> None:
    c = _get(db, user, challenge_id)
    if c.status == "completed":
        raise RuleError("A completed challenge is part of your record and can't be deleted")
    db.delete(c)
    db.commit()


# ============================== evidence: complete / excuse ==============================


def complete_challenge(db: Session, user: User, challenge_id: int, data: s.CompleteIn, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    c, today = _get(db, user, challenge_id), user_today(user, now)
    if c.status == "completed":
        raise Conflict("This challenge is already completed")
    if c.status not in OPEN:
        raise RuleError("An excused day can't be completed. Remove the excuse first")
    if c.date > today:
        raise RuleError("You can't complete a challenge before its day")
    if c.date < today:
        raise RuleError("That day has passed, so it can't be completed any more. You can excuse it with a reason")
    check_commit_message(data.commit_message)
    check_summary(data.summary, data.commit_message)
    project = db.scalar(select(Project).where(Project.id == c.project_id, Project.user_id == user.id)) if c.project_id else None
    if project is None:
        raise RuleError("This challenge has no project to attach the evidence to")
    if project.repo_url and project.repo_url != data.repo_url:
        raise RuleError(f"This project's repository is {project.repo_url}. The evidence must be a commit in that repository")
    for other in db.scalars(select(DailyChallenge).where(DailyChallenge.user_id == user.id, DailyChallenge.status == "completed",
                                                         DailyChallenge.repo_url == data.repo_url, DailyChallenge.id != c.id)):
        if other.commit_sha.startswith(data.commit_sha) or data.commit_sha.startswith(other.commit_sha):
            raise RuleError(f"That commit was already used as evidence for {other.date.isoformat()}. Each day needs its own work")
    if data.milestone_id is not None:
        m = db.scalar(select(ProjectMilestone).where(ProjectMilestone.id == data.milestone_id, ProjectMilestone.project_id == project.id))
        if m is None:
            raise RuleError("That milestone doesn't belong to this project")
    # record the development time on the project first; it commits together with the challenge below
    projects.log_session(db, user, project.id, ps.SessionCreate(minutes=data.minutes, summary=data.summary, date=today,
                                                                milestone_id=data.milestone_id, notes=data.evidence_notes), now)
    if not project.repo_url:
        project.repo_url = data.repo_url  # the project now knows its repository
    c.status, c.evidence_type, c.implemented_summary = "completed", "commit", data.summary.strip()
    c.repo_url, c.commit_sha, c.commit_message = data.repo_url, data.commit_sha, data.commit_message.strip()
    c.actual_minutes, c.milestone_id, c.evidence_notes = data.minutes, data.milestone_id, data.evidence_notes
    c.verification_status, c.completed_at = "unverified", now
    db.commit()
    return _out(c, today)


def excuse_day(db: Session, user: User, data: s.ExcuseIn, now: datetime | None = None) -> dict:
    today = user_today(user, now)
    day = data.date or today
    if day > today:
        raise RuleError("You can only excuse today or a day that has passed")
    c = _on(db, user, day)
    if c is None:
        c = DailyChallenge(user_id=user.id, date=day, mode="existing_project", planned_task="No challenge was planned", status="planned")
        db.add(c)
    elif c.status == "completed":
        raise RuleError("A completed day doesn't need an excuse")
    elif c.status == "excused":
        raise Conflict("That day is already excused")
    c.status, c.excuse_reason = "excused", data.reason.strip()
    db.commit()
    return _out(c, today)


# ============================== GitHub verification ==============================


def verify_challenge(db: Session, user: User, challenge_id: int, client, now: datetime | None = None) -> dict:
    """Check the stored commit against GitHub. Only a pass flips `verification_status` to 'verified'; a failed check
    changes nothing (the day stays completed but unverified) and says which check failed. `client` is a GitHubClient."""
    now = now or datetime.now(timezone.utc)
    c, today = _get(db, user, challenge_id), user_today(user, now)
    if c.status != "completed" or not c.commit_sha or not c.repo_url:
        raise RuleError("Only a completed challenge with a commit can be verified")
    info = client.get_commit(c.repo_url, c.commit_sha)  # GitHubError propagates; the router maps it
    checks = [{"name": "Commit exists", "ok": True, "detail": f"Found {info.sha[:10]} in {c.repo_url.removeprefix('https://github.com/')}"}]
    first_line = info.message.strip().splitlines()[0].strip().lower() if info.message.strip() else ""
    mine = c.commit_message.strip().splitlines()[0].strip().lower()
    checks.append({"name": "Message matches", "ok": bool(first_line) and (mine in first_line or first_line in mine),
                   "detail": "The commit message matches what you entered" if mine in first_line or first_line in mine
                   else f'GitHub says: "{info.message.strip().splitlines()[0][:80] if info.message.strip() else ""}"'})
    window_ok = info.committed_at is not None and c.date - timedelta(days=1) <= info.committed_at.date() <= c.date + timedelta(days=1)
    checks.append({"name": "Made on the day", "ok": window_ok,
                   "detail": "Committed within a day of the challenge date" if window_ok
                   else f"Committed {info.committed_at.date().isoformat() if info.committed_at else 'at an unknown time'}, the challenge is for {c.date.isoformat()}"})
    changed = info.files_changed > 0 or info.additions + info.deletions > 0
    checks.append({"name": "Changes code", "ok": changed,
                   "detail": f"{info.files_changed} file(s), +{info.additions} -{info.deletions}" if changed else "The commit changes no files"})
    ok = all(k["ok"] for k in checks)
    if ok:
        c.commit_sha, c.verification_status = info.sha, "verified"
        db.commit()
    return {"verified": ok, "checks": checks, "challenge": _out(c, today)}
