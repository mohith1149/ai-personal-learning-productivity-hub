"""Project tracker: projects (new or existing), milestones, tasks and development sessions.

Rules:
  * Progress is COMPUTED, never stored: done milestones + completed tasks, over all milestones + non-cancelled tasks
    (floored, so 100% only when everything is done). A project with neither shows 0%.
  * A project becomes "completed", and a milestone "done", only through an explicit action (DB CHECK: completed <=> completed_at).
    Finishing every milestone never completes the project by itself.
  * Project tasks are real rows in `tasks` (task_type 'project_dev', project_id set), so they also appear in the Tasks list; they are
    completed there / through the normal task status. Deleting a project keeps its tasks (detached), because they may matter on their own.
  * A development session is a dated record (minutes + what was done). Hours spent and active days are sums over these records.
  * Every query is scoped to the user; another user's id behaves like "not found".
"""
import json
from datetime import datetime, timezone

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.timeutil import user_today
from app.models import Project, ProjectMilestone, ProjectSession, Task, User
from app.schemas import projects as s


class NotFound(Exception):
    pass


class RuleError(ValueError):
    """A business-rule violation (HTTP 422)."""


class Conflict(Exception):
    """Clashes with existing data (HTTP 409)."""


# ============================== lookups ==============================


def _get(db: Session, user: User, project_id: int) -> Project:
    p = db.scalar(select(Project).where(Project.id == project_id, Project.user_id == user.id))
    if p is None:
        raise NotFound("Project not found")
    return p


def _get_milestone(db: Session, user: User, milestone_id: int) -> ProjectMilestone:
    m = db.scalar(select(ProjectMilestone).join(Project, Project.id == ProjectMilestone.project_id)
                  .where(ProjectMilestone.id == milestone_id, Project.user_id == user.id))
    if m is None:
        raise NotFound("Milestone not found")
    return m


def _name_taken(db: Session, user: User, title: str, except_id: int | None = None) -> bool:
    q = select(Project.id).where(Project.user_id == user.id, func.lower(Project.title) == title.lower())
    if except_id is not None:
        q = q.where(Project.id != except_id)
    return db.scalar(q) is not None


def _stack(p: Project) -> list[str]:
    try:
        v = json.loads(p.tech_stack) if p.tech_stack else []
        return [str(x) for x in v] if isinstance(v, list) else []
    except ValueError:
        return []


# ============================== computed views ==============================


def _percent(done: int, total: int) -> int:
    return (100 * done) // total if total else 0


def _summaries(db: Session, user: User, projects: list[Project], now: datetime | None) -> list[dict]:
    ids = [p.id for p in projects]
    if not ids:
        return []
    ms = {pid: (int(n), int(d or 0)) for pid, n, d in db.execute(
        select(ProjectMilestone.project_id, func.count(), func.sum(case((ProjectMilestone.status == "done", 1), else_=0)))
        .where(ProjectMilestone.project_id.in_(ids)).group_by(ProjectMilestone.project_id))}
    ts = {pid: (int(n), int(d or 0)) for pid, n, d in db.execute(
        select(Task.project_id, func.count(), func.sum(case((Task.status == "completed", 1), else_=0)))
        .where(Task.user_id == user.id, Task.project_id.in_(ids), Task.status != "cancelled").group_by(Task.project_id))}
    ss = {pid: (int(m or 0), int(n), int(d)) for pid, m, n, d in db.execute(
        select(ProjectSession.project_id, func.sum(ProjectSession.minutes), func.count(), func.count(func.distinct(ProjectSession.date)))
        .where(ProjectSession.user_id == user.id, ProjectSession.project_id.in_(ids)).group_by(ProjectSession.project_id))}
    today = user_today(user, now)
    out = []
    for p in projects:
        m_total, m_done = ms.get(p.id, (0, 0))
        t_total, t_done = ts.get(p.id, (0, 0))
        minutes, count, days = ss.get(p.id, (0, 0, 0))
        out.append({
            "id": p.id, "title": p.title, "origin": p.origin, "status": p.status, "priority": p.priority,
            "description": p.description, "objective": p.objective, "tech_stack": _stack(p), "repo_url": p.repo_url,
            "start_date": p.start_date, "target_date": p.target_date, "completed_at": p.completed_at,
            "last_activity_at": p.last_activity_at, "created_at": p.created_at, "minutes_spent": minutes,
            "session_count": count, "days_active": days,
            "progress": {"milestones_done": m_done, "milestones_total": m_total, "tasks_done": t_done, "tasks_total": t_total,
                         "percent": _percent(m_done + t_done, m_total + t_total)},
            "overdue": p.status == "active" and p.target_date is not None and p.target_date < today,
        })
    return out


def list_projects(db: Session, user: User, status: str | None = None, now: datetime | None = None) -> list[dict]:
    q = select(Project).where(Project.user_id == user.id)
    if status:
        q = q.where(Project.status == status)
    projects = list(db.scalars(q.order_by(case((Project.status == "active", 0), (Project.status == "paused", 1), else_=2),
                                         Project.priority, Project.title)))
    return _summaries(db, user, projects, now)


def get_project(db: Session, user: User, project_id: int, now: datetime | None = None) -> dict:
    p = _get(db, user, project_id)
    out = _summaries(db, user, [p], now)[0]
    today = user_today(user, now)
    out["notes"] = p.notes
    out["milestones"] = [
        {"id": m.id, "title": m.title, "description": m.description, "status": m.status, "position": m.position,
         "due_date": m.due_date, "completed_at": m.completed_at, "evidence": m.evidence,
         "overdue": m.status == "pending" and m.due_date is not None and m.due_date < today}
        for m in p.milestones]
    tasks = db.scalars(select(Task).where(Task.user_id == user.id, Task.project_id == p.id)
                       .order_by(case((Task.status == "completed", 1), (Task.status == "cancelled", 2), else_=0), Task.priority, Task.id))
    out["tasks"] = [{"id": t.id, "title": t.title, "status": t.status, "priority": t.priority, "due_date": t.due_date,
                     "estimated_minutes": t.estimated_minutes, "completed_at": t.completed_at} for t in tasks]
    out["sessions"] = list(db.scalars(select(ProjectSession).where(ProjectSession.user_id == user.id, ProjectSession.project_id == p.id)
                                      .order_by(ProjectSession.date.desc(), ProjectSession.id.desc()).limit(200)))
    return out


# ============================== projects ==============================


def create_project(db: Session, user: User, data: s.ProjectCreate, now: datetime | None = None) -> dict:
    title = data.title.strip()
    if _name_taken(db, user, title):
        raise Conflict("You already have a project with that name")
    now = now or datetime.now(timezone.utc)
    fields = data.model_dump()
    fields.update(title=title, tech_stack=json.dumps(data.tech_stack),
                  start_date=data.start_date or (user_today(user, now) if data.origin == "new" else None))
    p = Project(user_id=user.id, **fields)
    if data.status == "completed":
        p.completed_at = now
    db.add(p)
    db.commit()
    return get_project(db, user, p.id, now)


def update_project(db: Session, user: User, project_id: int, data: s.ProjectUpdate, now: datetime | None = None) -> dict:
    p = _get(db, user, project_id)
    changes = data.model_dump(exclude_unset=True)
    for required in ("title", "origin", "status", "priority"):
        if required in changes and changes[required] is None:
            raise RuleError(f"{required} can't be empty")
    if "title" in changes:
        changes["title"] = changes["title"].strip()
        if _name_taken(db, user, changes["title"], except_id=p.id):
            raise Conflict("You already have a project with that name")
    if "tech_stack" in changes:
        changes["tech_stack"] = json.dumps(changes["tech_stack"] or [])
    start = changes.get("start_date", p.start_date)
    target = changes.get("target_date", p.target_date)
    if start and target and target < start:
        raise RuleError("The target date can't be before the start date")
    new_status = changes.pop("status", None)
    for field, value in changes.items():
        setattr(p, field, value)
    if new_status is not None:
        if new_status == "completed":
            if p.status != "completed":
                p.completed_at = now or datetime.now(timezone.utc)
        else:
            p.completed_at = None
        p.status = new_status
    db.commit()
    return get_project(db, user, project_id, now)


def delete_project(db: Session, user: User, project_id: int) -> None:
    """Deletes the project, its milestones and its sessions. Its tasks stay in the task list, detached from the project."""
    p = _get(db, user, project_id)
    db.query(Task).filter(Task.user_id == user.id, Task.project_id == p.id).update({Task.project_id: None})
    db.delete(p)
    db.commit()


# ============================== milestones ==============================


def _milestone_title_taken(db: Session, project_id: int, title: str, except_id: int | None = None) -> bool:
    q = select(ProjectMilestone.id).where(ProjectMilestone.project_id == project_id, func.lower(ProjectMilestone.title) == title.lower())
    if except_id is not None:
        q = q.where(ProjectMilestone.id != except_id)
    return db.scalar(q) is not None


def add_milestone(db: Session, user: User, project_id: int, data: s.MilestoneCreate, now: datetime | None = None) -> dict:
    p = _get(db, user, project_id)
    title = data.title.strip()
    if _milestone_title_taken(db, p.id, title):
        raise Conflict("This project already has a milestone with that name")
    top = db.scalar(select(func.max(ProjectMilestone.position)).where(ProjectMilestone.project_id == p.id)) or 0
    db.add(ProjectMilestone(project_id=p.id, title=title, description=data.description, due_date=data.due_date, position=top + 1))
    db.commit()
    return get_project(db, user, project_id, now)


def update_milestone(db: Session, user: User, milestone_id: int, data: s.MilestoneUpdate, now: datetime | None = None) -> dict:
    m = _get_milestone(db, user, milestone_id)
    changes = data.model_dump(exclude_unset=True)
    if "title" in changes:
        if changes["title"] is None:
            raise RuleError("title can't be empty")
        changes["title"] = changes["title"].strip()
        if _milestone_title_taken(db, m.project_id, changes["title"], except_id=m.id):
            raise Conflict("This project already has a milestone with that name")
    for field, value in changes.items():
        setattr(m, field, value)
    db.commit()
    return get_project(db, user, m.project_id, now)


def set_milestone_status(db: Session, user: User, milestone_id: int, data: s.MilestoneStatus, now: datetime | None = None) -> dict:
    """The ONLY way a milestone becomes done. Marking done twice keeps the first completion time."""
    m = _get_milestone(db, user, milestone_id)
    now = now or datetime.now(timezone.utc)
    if data.status == "done":
        if m.status != "done":
            m.status, m.completed_at = "done", now
        if data.evidence is not None:
            m.evidence = data.evidence
        _get(db, user, m.project_id).last_activity_at = now
    else:
        m.status, m.completed_at = "pending", None
    db.commit()
    return get_project(db, user, m.project_id, now)


def delete_milestone(db: Session, user: User, milestone_id: int, now: datetime | None = None) -> dict:
    m = _get_milestone(db, user, milestone_id)
    pid = m.project_id
    db.delete(m)  # sessions that pointed at it keep their record (link cleared)
    db.commit()
    return get_project(db, user, pid, now)


# ============================== tasks ==============================


def add_task(db: Session, user: User, project_id: int, data: s.TaskCreate, now: datetime | None = None) -> dict:
    p = _get(db, user, project_id)
    db.add(Task(user_id=user.id, project_id=p.id, task_type="project_dev", title=data.title.strip(), description=data.description,
                priority=data.priority, due_date=data.due_date, estimated_minutes=data.estimated_minutes, status="pending"))
    db.commit()
    return get_project(db, user, project_id, now)


# ============================== development sessions ==============================


def log_session(db: Session, user: User, project_id: int, data: s.SessionCreate, now: datetime | None = None) -> ProjectSession:
    p = _get(db, user, project_id)
    now = now or datetime.now(timezone.utc)
    today = user_today(user, now)
    day = data.date or today
    if day > today:
        raise RuleError("You can't log development time in the future")
    if data.milestone_id is not None:
        m = db.scalar(select(ProjectMilestone).where(ProjectMilestone.id == data.milestone_id, ProjectMilestone.project_id == p.id))
        if m is None:
            raise RuleError("That milestone doesn't belong to this project")
    if data.task_id is not None:
        t = db.scalar(select(Task).where(Task.id == data.task_id, Task.user_id == user.id, Task.project_id == p.id))
        if t is None:
            raise RuleError("That task doesn't belong to this project")
    session = ProjectSession(user_id=user.id, project_id=p.id, date=day, minutes=data.minutes, summary=data.summary.strip(),
                             milestone_id=data.milestone_id, task_id=data.task_id, notes=data.notes)
    db.add(session)
    p.started_at = p.started_at or now
    p.last_activity_at = max(filter(None, (p.last_activity_at, now))) if day == today else p.last_activity_at
    db.commit()
    return session


def delete_session(db: Session, user: User, session_id: int) -> int:
    """Deletes one development session; returns its project id."""
    sess = db.scalar(select(ProjectSession).where(ProjectSession.id == session_id, ProjectSession.user_id == user.id))
    if sess is None:
        raise NotFound("Development session not found")
    pid = sess.project_id
    db.delete(sess)
    db.commit()
    return pid
