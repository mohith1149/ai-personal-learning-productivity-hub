"""The tools the assistant may call. Each one is a thin wrapper over an existing service function.

  * Arguments are validated by a strict pydantic model (unknown fields rejected). There is no user id argument: every tool runs as the
    signed-in user, so the model can't reach anyone else's data.
  * READ tools run immediately and return data computed by the services. WRITE tools never run directly: the assistant layer stores a
    pending action, and the service is called only after the user approves it (and the arguments are validated again then)."""
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any, Callable, Literal

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.timeutil import user_today
from app.models import User
from app.schemas import challenges as chs
from app.schemas import planner as pls
from app.schemas import projects as pjs
from app.schemas import tasks as tks
from app.services import challenges, courses, dashboard, habits, planner, projects, roadmap, tasks

MAX_ITEMS = 40


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NoArgs(Args):
    pass


class OptionalDay(Args):
    day: date | None = Field(default=None, description="The day to show (YYYY-MM-DD). Defaults to today.")


class CompleteTask(Args):
    task_id: int = Field(description="The id of the task, from get_today_tasks or get_pending_tasks.")


class RescheduleTask(Args):
    task_id: int
    new_date: date = Field(description="The new day (YYYY-MM-DD). Today or later.")
    move_due_date: bool = False


class RecordProgress(Args):
    project_id: int
    minutes: Annotated[int, Field(ge=1, le=1440)]
    summary: str = Field(min_length=3, max_length=5000, description="What was actually done.")


class ChallengePlan(chs.ChallengeCreate):
    """Same fields as the challenge form. (Completing a day needs evidence the user enters themselves, so there is no tool for it.)"""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    kind: Literal["read", "write"]
    args: type[BaseModel]
    run: Callable[[Session, User, Any], Any]
    summarise: Callable[[Any], str] | None = None  # write tools: a plain sentence shown to the user for approval

    def spec(self) -> dict:
        schema = self.args.model_json_schema()
        schema.pop("title", None)
        return {"name": self.name, "description": self.description, "input_schema": schema}


def _cap(items: list) -> list:
    return items[:MAX_ITEMS]


def _task_rows(rows) -> list[dict]:
    return [{"id": t.id, "title": t.title, "status": t.status, "priority": t.priority, "scheduled_date": t.scheduled_date, "due_date": t.due_date,
             "estimated_minutes": t.estimated_minutes} for t in rows]


# ------------------------------ read tools ------------------------------

def _today_tasks(db, user, _):
    rows, total = tasks.list_tasks(db, user, view="today", limit=MAX_ITEMS)
    return {"total": total, "tasks": _task_rows(rows)}


def _pending_tasks(db, user, _):
    rows, total = tasks.list_tasks(db, user, view="open", limit=MAX_ITEMS)
    return {"total": total, "tasks": _task_rows(rows)}


def _plan(db, user, a: OptionalDay):
    p = planner.build_day(db, user, a.day or user_today(user))
    return {"date": p["date"], "summary": p["summary"], "items": _cap([{k: i[k] for k in ("kind", "title", "subtitle", "status", "due_date")} for i in p["items"]])}


def _dashboard(db, user, _):
    d = dashboard.build(db, user)
    d["plan"]["next_items"] = [{k: i[k] for k in ("kind", "title", "status")} for i in d["plan"]["next_items"]]
    return d


def _courses(db, user, _):
    return [{"id": c["id"], "title": c["title"], "status": c["status"], "progress": c["progress"], "next_lesson": (c["next_lesson"] or {}).get("title"),
             "minutes_studied": c["minutes_studied"]} for c in courses.list_courses(db, user)]


def _next_videos(db, user, _):
    return [{"collection": v["name"], "daily_target": v["daily_target"], "watched_today": v["watched_today"], "remaining_today": v["remaining_today"],
             "up_next": v["up_next"]} for v in dashboard._videos(db, user, None)]


def _active_projects(db, user, _):
    return [{"id": p["id"], "title": p["title"], "progress": p["progress"], "minutes_spent": p["minutes_spent"], "repo_url": p["repo_url"],
             "last_activity_at": p["last_activity_at"]} for p in projects.list_projects(db, user, "active")]


def _roadmap(db, user, _):
    r = roadmap.get_roadmap(db, user)
    return {"overall": r["overall"], "next_topic": (r["next_topic"] or {}).get("title"),
            "stages": [{k: s[k] for k in ("title", "total", "completed", "percent")} for s in r["stages"]]}


def _habits(db, user, _):
    h = habits.list_habits(db, user)
    return {"due_today": h["due_today"], "habits": [{"id": x["id"], "name": x["name"], "active": x["active"], "done_today": x["done_today"],
                                                      "streak": x["streak"]} for x in h["items"]]}


def _challenge(db, user, _):
    t = challenges.today_view(db, user)
    c = t["challenge"]
    return {"date": t["date"], "stats": t["stats"], "today": c and {k: c[k] for k in ("status", "planned_task", "verification_status", "excuse_reason")},
            "note": "Evidence is entered by the user and is not verified against GitHub."}


# ------------------------------ write tools (run only after approval) ------------------------------

def _create_task(db, user, a: tks.TaskCreate):
    t = tasks.create_task(db, user, a)
    return {"id": t.id, "title": t.title}


def _complete_task(db, user, a: CompleteTask):
    t = tasks.update_task(db, user, a.task_id, tks.TaskUpdate(status="completed"))
    return {"id": t.id, "title": t.title, "status": t.status}


def _reschedule(db, user, a: RescheduleTask):
    planner.reschedule_task(db, user, a.task_id, pls.RescheduleIn(date=a.new_date, from_date=user_today(user), move_due_date=a.move_due_date))
    return {"id": a.task_id, "scheduled_date": a.new_date}


def _record(db, user, a: RecordProgress):
    s = projects.log_session(db, user, a.project_id, pjs.SessionCreate(minutes=a.minutes, summary=a.summary))
    return {"session_id": s.id, "minutes": s.minutes}


def _challenge_plan(db, user, a: ChallengePlan):
    c = challenges.create_challenge(db, user, chs.ChallengeCreate(**a.model_dump()))
    return {"id": c["id"], "date": c["date"], "planned_task": c["planned_task"]}


def _task_line(a: tks.TaskCreate) -> str:
    return f'Create the task "{a.title}"' + (f" for {a.scheduled_date}" if a.scheduled_date else "") + (f", due {a.due_date}" if a.due_date else "")


TOOLS: dict[str, Tool] = {t.name: t for t in [
    Tool("get_today_tasks", "Tasks scheduled or due today, plus overdue ones.", "read", NoArgs, _today_tasks),
    Tool("get_pending_tasks", "All open (not completed) tasks.", "read", NoArgs, _pending_tasks),
    Tool("get_plan", "The daily plan for a day: tasks, lessons, videos, roadmap topics, habits and project work, with each item's status.", "read", OptionalDay, _plan),
    Tool("get_dashboard", "An overview of today: plan progress, videos to watch, challenge streak, habits, tasks, projects, courses, roadmap.", "read", NoArgs, _dashboard),
    Tool("get_course_progress", "Courses with lesson progress and the next lesson.", "read", NoArgs, _courses),
    Tool("get_next_video", "Video collections with a daily target: how many were watched today and which are next.", "read", NoArgs, _next_videos),
    Tool("get_active_projects", "Active projects with progress and time spent.", "read", NoArgs, _active_projects),
    Tool("get_roadmap_progress", "Progress through the AI learning roadmap and the next topic.", "read", NoArgs, _roadmap),
    Tool("get_habit_status", "Habits with today's status and streaks.", "read", NoArgs, _habits),
    Tool("get_challenge_status", "Today's daily project challenge, streaks and missed days. Evidence is self-reported and unverified.", "read", NoArgs, _challenge),
    Tool("create_task", "Propose a new task. The user must approve it before it is created.", "write", tks.TaskCreate, _create_task, _task_line),
    Tool("complete_task", "Propose marking a task completed. The user must approve it.", "write", CompleteTask, _complete_task, lambda a: f"Mark task #{a.task_id} as completed"),
    Tool("reschedule_task", "Propose moving a task to another day. It does not complete the task. The user must approve it.", "write", RescheduleTask, _reschedule,
         lambda a: f"Move task #{a.task_id} to {a.new_date}"),
    Tool("record_project_progress", "Propose logging a development session on a project. The user must approve it.", "write", RecordProgress, _record,
         lambda a: f"Log {a.minutes} minutes on project #{a.project_id}: {a.summary[:120]}"),
    Tool("create_project_challenge", "Propose today's (or a future day's) daily project challenge. The user must approve it.", "write", ChallengePlan, _challenge_plan,
         lambda a: f'Plan the challenge "{a.planned_task}" for {a.date or "today"}'),
]}


def specs() -> list[dict]:
    return [t.spec() for t in TOOLS.values()]


def describe(name: str, args: BaseModel) -> str:
    t = TOOLS[name]
    return t.summarise(args) if t.summarise else name


def encode(value: Any) -> Any:
    return jsonable_encoder(value)
