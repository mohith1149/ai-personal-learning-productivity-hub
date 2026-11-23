"""Task business logic. Routers (UI) and, later, AI tools both call these functions —
the LLM never touches the database directly.

Rules implemented here:
  * Every query is scoped to the owning user (another user's id is indistinguishable from "not found").
  * Overdue is COMPUTED in the user's timezone, never stored, so it can't go stale. There is exactly one
    definition, expressed twice (Python `is_overdue` and SQL `overdue_clause`) and tested for agreement.
  * completed_at is set/cleared only by `_apply_status`, so status and completed_at can't drift apart
    (a DB CHECK constraint backs this up).
  * Recurring tasks are materialised idempotently (unique(recurring_task_id, scheduled_date)).
"""
import calendar
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import ColumnElement, and_, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.timeutil import local_day_bounds_utc, user_now, user_today
from app.models import RecurringTask, Task, TaskCategory, User
from app.schemas import tasks as s

OPEN_STATUSES = ("pending", "in_progress")
VIEWS = ("all", "open", "today", "overdue", "upcoming", "completed")
GENERATION_HORIZON_DAYS = 7  # recurring instances are created this far ahead
MAX_BACKFILL_DAYS = 31  # if the app was closed for longer, only the last month is back-filled
SCHEDULE_FIELDS = {"frequency", "days_of_week", "day_of_month", "end_date"}


class NotFound(Exception):
    pass


class RuleError(ValueError):
    """A business-rule violation the client should see as HTTP 422."""


# ============================== categories ==============================


def list_categories(db: Session, user: User) -> list[TaskCategory]:
    return list(
        db.scalars(select(TaskCategory).where(TaskCategory.user_id == user.id).order_by(func.lower(TaskCategory.name)))
    )


def _get_category(db: Session, user: User, category_id: int) -> TaskCategory:
    cat = db.scalar(select(TaskCategory).where(TaskCategory.id == category_id, TaskCategory.user_id == user.id))
    if cat is None:
        raise NotFound("Category not found")
    return cat


def _ensure_category_name_free(db: Session, user: User, name: str, ignore_id: int | None = None) -> None:
    q = select(TaskCategory.id).where(TaskCategory.user_id == user.id, func.lower(TaskCategory.name) == name.lower())
    existing = db.scalar(q)
    if existing is not None and existing != ignore_id:
        raise RuleError(f"A category named '{name}' already exists")


def create_category(db: Session, user: User, data: s.CategoryCreate) -> TaskCategory:
    _ensure_category_name_free(db, user, data.name)
    cat = TaskCategory(user_id=user.id, name=data.name, color=data.color)
    db.add(cat)
    db.commit()
    return cat


def update_category(db: Session, user: User, category_id: int, data: s.CategoryUpdate) -> TaskCategory:
    cat = _get_category(db, user, category_id)
    if data.name is not None and data.name != cat.name:
        if cat.is_system:
            raise RuleError("Built-in categories can't be renamed")
        _ensure_category_name_free(db, user, data.name, ignore_id=cat.id)
        cat.name = data.name
    if data.color is not None:
        cat.color = data.color
    db.commit()
    return cat


def delete_category(db: Session, user: User, category_id: int) -> None:
    cat = _get_category(db, user, category_id)
    if cat.is_system:
        raise RuleError("Built-in categories can't be deleted")
    db.delete(cat)  # tasks keep existing: their category_id is set to NULL by the FK
    db.commit()


def _check_category(db: Session, user: User, category_id: int | None) -> None:
    if category_id is not None:
        try:
            _get_category(db, user, category_id)
        except NotFound:
            raise RuleError("That category doesn't exist") from None


# ============================== overdue ==============================


def is_overdue(task: Task, now_local: datetime) -> bool:
    """Open task whose due date has passed. A due date alone means overdue from the NEXT day;
    with a due time it means overdue the minute after that time. Scheduled-only tasks are never overdue."""
    if task.status not in OPEN_STATUSES or task.due_date is None:
        return False
    today = now_local.date()
    if task.due_date < today:
        return True
    if task.due_date == today and task.due_time:
        return task.due_time < now_local.strftime("%H:%M")
    return False


def overdue_clause(today: date, now_hhmm: str) -> ColumnElement[bool]:
    """SQL twin of `is_overdue` (HH:MM strings compare correctly as text)."""
    return and_(
        Task.status.in_(OPEN_STATUSES),
        Task.due_date.is_not(None),
        or_(
            Task.due_date < today,
            and_(Task.due_date == today, Task.due_time.is_not(None), Task.due_time < now_hhmm),
        ),
    )


# ============================== tasks: read ==============================


def _get_task(db: Session, user: User, task_id: int) -> Task:
    task = db.scalar(select(Task).where(Task.id == task_id, Task.user_id == user.id))
    if task is None:
        raise NotFound("Task not found")
    return task


def get_task(db: Session, user: User, task_id: int) -> Task:
    return _get_task(db, user, task_id)


def _view_clause(user: User, view: str, now: datetime | None) -> ColumnElement[bool] | None:
    local = user_now(user, now)
    today = local.date()
    open_ = Task.status.in_(OPEN_STATUSES)
    if view == "all":
        return None
    if view == "open":
        return open_
    if view == "overdue":
        return overdue_clause(today, local.strftime("%H:%M"))
    if view == "today":
        return and_(open_, or_(Task.due_date == today, Task.scheduled_date == today))
    if view == "upcoming":
        return and_(
            open_,
            or_(Task.due_date > today, and_(Task.due_date.is_(None), Task.scheduled_date > today)),
        )
    if view == "completed":
        return Task.status == "completed"
    raise RuleError(f"Unknown view '{view}'")


def list_tasks(
    db: Session,
    user: User,
    *,
    view: str = "all",
    status: str | None = None,
    category_id: int | None = None,
    priority: int | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
    now: datetime | None = None,
) -> tuple[list[Task], int]:
    generate_recurring(db, user, now=now)  # keep today's recurring instances present (idempotent, cheap)

    conds: list[ColumnElement[bool]] = [Task.user_id == user.id]
    view_cond = _view_clause(user, view, now)
    if view_cond is not None:
        conds.append(view_cond)
    if status:
        conds.append(Task.status == status)
    if category_id is not None:
        conds.append(Task.category_id == category_id)
    if priority is not None:
        conds.append(Task.priority == priority)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conds.append(Task.title.ilike(f"%{escaped}%", escape="\\"))

    total = db.scalar(select(func.count()).select_from(Task).where(*conds)) or 0

    stmt = select(Task).where(*conds)
    if view == "completed":
        stmt = stmt.order_by(Task.completed_at.desc(), Task.id.desc())
    else:
        # Open work first; within it: dated before undated, soonest first, timed before untimed, then priority.
        stmt = stmt.order_by(
            case((Task.status.in_(OPEN_STATUSES), 0), else_=1),
            Task.due_date.is_(None),
            Task.due_date,
            Task.due_time.is_(None),
            Task.due_time,
            Task.priority,
            Task.id,
        )
    return list(db.scalars(stmt.limit(limit).offset(offset))), total


def counts(db: Session, user: User, now: datetime | None = None) -> dict[str, int]:
    generate_recurring(db, user, now=now)
    out = {v: (list_tasks_count(db, user, v, now)) for v in VIEWS if v != "all"}
    out["all"] = db.scalar(select(func.count()).select_from(Task).where(Task.user_id == user.id)) or 0
    start, end = local_day_bounds_utc(user, user_today(user, now))
    out["completed_today"] = (
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.user_id == user.id, Task.status == "completed", Task.completed_at >= start, Task.completed_at < end)
        )
        or 0
    )
    return out


def list_tasks_count(db: Session, user: User, view: str, now: datetime | None) -> int:
    cond = _view_clause(user, view, now)
    stmt = select(func.count()).select_from(Task).where(Task.user_id == user.id)
    if cond is not None:
        stmt = stmt.where(cond)
    return db.scalar(stmt) or 0


# ============================== tasks: write ==============================


def _validate_dates(scheduled: date | None, due: date | None, due_time: str | None) -> None:
    if due_time and due is None:
        raise RuleError("A due time needs a due date")
    if scheduled and due and due < scheduled:
        raise RuleError("The due date can't be before the scheduled date")


def _apply_status(task: Task, new_status: str, now: datetime | None = None) -> None:
    """The ONLY place completed_at is set or cleared."""
    if new_status == "completed":
        if task.status != "completed":
            task.completed_at = now or datetime.now(timezone.utc)
    else:
        task.completed_at = None
    task.status = new_status


def create_task(db: Session, user: User, data: s.TaskCreate) -> Task:
    _check_category(db, user, data.category_id)
    _validate_dates(data.scheduled_date, data.due_date, data.due_time)
    task = Task(
        user_id=user.id,
        title=data.title,
        description=data.description,
        notes=data.notes,
        category_id=data.category_id,
        task_type="one_time",
        priority=data.priority,
        status=data.status,
        scheduled_date=data.scheduled_date,
        due_date=data.due_date,
        due_time=data.due_time,
        estimated_minutes=data.estimated_minutes,
    )
    db.add(task)
    db.commit()
    return task


def update_task(db: Session, user: User, task_id: int, data: s.TaskUpdate, now: datetime | None = None) -> Task:
    task = _get_task(db, user, task_id)
    changes = data.model_dump(exclude_unset=True)

    for required in ("title", "priority", "status"):
        if required in changes and changes[required] is None:
            raise RuleError(f"{required} can't be empty")
    if "category_id" in changes:
        _check_category(db, user, changes["category_id"])

    scheduled = changes.get("scheduled_date", task.scheduled_date)
    due = changes.get("due_date", task.due_date)
    due_time = changes.get("due_time", task.due_time)
    if "due_date" in changes and due is None:
        due_time = None  # clearing the date also clears its time
        changes["due_time"] = None
    _validate_dates(scheduled, due, due_time)

    new_status = changes.pop("status", None)
    for field, value in changes.items():
        setattr(task, field, value)
    if new_status is not None:
        _apply_status(task, new_status, now)
    db.commit()
    return task


def delete_task(db: Session, user: User, task_id: int) -> None:
    task = _get_task(db, user, task_id)
    db.delete(task)
    db.commit()


# ============================== recurring ==============================


def _days_to_str(days: list[int] | None) -> str | None:
    return ",".join(str(d) for d in sorted(set(days))) if days else None


def _validate_recurrence(frequency: str, days: list[int] | None, dom: int | None, start: date, end: date | None) -> None:
    if frequency == "weekly" and not days:
        raise RuleError("Weekly tasks need at least one day of the week")
    if frequency == "monthly" and dom is None:
        raise RuleError("Monthly tasks need a day of the month")
    if end and end < start:
        raise RuleError("The end date can't be before the start date")


def occurs_on(rt: RecurringTask, day: date) -> bool:
    """Does this recurring template produce an instance on `day`? (Monday=0)"""
    if day < rt.start_date or (rt.end_date and day > rt.end_date):
        return False
    if rt.frequency == "daily":
        return True
    if rt.frequency == "weekdays":
        return day.weekday() < 5
    if rt.frequency == "weekly":
        return str(day.weekday()) in (rt.days_of_week or "").split(",")
    if rt.frequency == "monthly":
        # Day 31 in a 30-day month (or 29/30 in February) falls on the month's last day instead of vanishing.
        last = calendar.monthrange(day.year, day.month)[1]
        return day.day == min(rt.day_of_month or 1, last)
    return False


def list_recurring(db: Session, user: User) -> list[RecurringTask]:
    return list(
        db.scalars(select(RecurringTask).where(RecurringTask.user_id == user.id).order_by(RecurringTask.id.desc()))
    )


def _get_recurring(db: Session, user: User, rid: int) -> RecurringTask:
    rt = db.scalar(select(RecurringTask).where(RecurringTask.id == rid, RecurringTask.user_id == user.id))
    if rt is None:
        raise NotFound("Recurring task not found")
    return rt


def create_recurring(db: Session, user: User, data: s.RecurringCreate, now: datetime | None = None) -> RecurringTask:
    today = user_today(user, now)
    start = data.start_date or today
    if start < today:
        raise RuleError("A recurring task must start today or later")
    _check_category(db, user, data.category_id)
    _validate_recurrence(data.frequency, data.days_of_week, data.day_of_month, start, data.end_date)
    rt = RecurringTask(
        user_id=user.id,
        title=data.title,
        description=data.description,
        category_id=data.category_id,
        priority=data.priority,
        estimated_minutes=data.estimated_minutes,
        frequency=data.frequency,
        days_of_week=_days_to_str(data.days_of_week) if data.frequency == "weekly" else None,
        day_of_month=data.day_of_month if data.frequency == "monthly" else None,
        start_date=start,
        end_date=data.end_date,
    )
    db.add(rt)
    db.commit()
    generate_recurring(db, user, now=now)
    return rt


def update_recurring(
    db: Session, user: User, rid: int, data: s.RecurringUpdate, now: datetime | None = None
) -> RecurringTask:
    """Title/priority/etc. edits apply to instances generated from now on. A SCHEDULE change (frequency, days,
    day of month, end date) also replaces the future instances that are still untouched (pending, after today),
    so the next week reflects the new rule immediately. Past, today's, started and completed tasks are never touched."""
    rt = _get_recurring(db, user, rid)
    changes = data.model_dump(exclude_unset=True)
    for required in ("title", "priority", "frequency", "active"):
        if required in changes and changes[required] is None:
            raise RuleError(f"{required} can't be empty")
    if "category_id" in changes:
        _check_category(db, user, changes["category_id"])

    frequency = changes.get("frequency", rt.frequency)
    days = changes["days_of_week"] if "days_of_week" in changes else (
        [int(x) for x in rt.days_of_week.split(",")] if rt.days_of_week else None
    )
    dom = changes.get("day_of_month", rt.day_of_month)
    end = changes.get("end_date", rt.end_date)
    _validate_recurrence(frequency, days, dom, rt.start_date, end)

    was_active = rt.active
    for field, value in changes.items():
        if field == "days_of_week":
            continue
        setattr(rt, field, value)
    if rt.active and not was_active:
        # Resuming means "carry on from today": days it was paused are skipped, not back-filled as overdue.
        rt.last_generated_date = max(
            rt.last_generated_date or date.min, user_today(user, now) - timedelta(days=1)
        )
    rt.days_of_week = _days_to_str(days) if frequency == "weekly" else None
    if frequency != "monthly":
        rt.day_of_month = None
    if SCHEDULE_FIELDS & changes.keys():
        today = user_today(user, now)
        for stale in db.scalars(
            select(Task).where(
                Task.recurring_task_id == rt.id, Task.scheduled_date > today, Task.status == "pending"
            )
        ):
            db.delete(stale)
        rt.last_generated_date = today  # regeneration resumes tomorrow under the new rule
    db.commit()
    if rt.active:
        generate_recurring(db, user, now=now)
    return rt


def delete_recurring(db: Session, user: User, rid: int) -> None:
    """Deleting a template keeps the tasks it already produced (their recurring_task_id becomes NULL)."""
    rt = _get_recurring(db, user, rid)
    db.delete(rt)
    db.commit()


def generate_recurring(db: Session, user: User, now: datetime | None = None) -> int:
    """Create missing instances for every active template up to today + horizon. Idempotent.

    Back-fills days missed while the app was closed (so a skipped daily task shows up as OVERDUE rather than
    silently vanishing), limited to MAX_BACKFILL_DAYS. Returns how many tasks were created."""
    today = user_today(user, now)
    horizon = today + timedelta(days=GENERATION_HORIZON_DAYS)
    earliest = today - timedelta(days=MAX_BACKFILL_DAYS)
    created = 0
    templates = db.scalars(
        select(RecurringTask).where(RecurringTask.user_id == user.id, RecurringTask.active.is_(True))
    ).all()
    for rt in templates:
        first = max(rt.start_date, earliest)
        if rt.last_generated_date:
            first = max(first, rt.last_generated_date + timedelta(days=1))
        last = min(horizon, rt.end_date) if rt.end_date else horizon
        if first > last:
            continue
        existing = set(
            db.scalars(
                select(Task.scheduled_date).where(
                    Task.recurring_task_id == rt.id, Task.scheduled_date.between(first, last)
                )
            )
        )
        day = first
        while day <= last:
            if day not in existing and occurs_on(rt, day):
                db.add(
                    Task(
                        user_id=user.id,
                        title=rt.title,
                        description=rt.description,
                        category_id=rt.category_id,
                        task_type="recurring",
                        priority=rt.priority,
                        estimated_minutes=rt.estimated_minutes,
                        scheduled_date=day,
                        due_date=day,
                        recurring_task_id=rt.id,
                    )
                )
                created += 1
            day += timedelta(days=1)
        rt.last_generated_date = last
    try:
        db.commit()
    except IntegrityError:
        # Lost a race with another request generating the same instances: the unique constraint protected us.
        db.rollback()
        return 0
    return created
