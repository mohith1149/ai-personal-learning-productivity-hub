"""Course business logic (courses → modules → lessons, study sessions, templates).

Rules implemented here:
  * Every query is scoped to the owning user. Modules and lessons carry no user_id, so ownership is always
    resolved through their course; someone else's id behaves exactly like "not found".
  * Lesson completion is ONLY ever caused by an explicit call (`complete_lesson`). Nothing marks a lesson done
    as a side effect, and templates never create completed lessons.
  * A course's "completed" state is DERIVED: it is completed exactly when it has lessons and all are completed.
    Un-completing a lesson (or adding a new one) reopens it. A course with no lessons may be completed by hand.
  * Progress percentage is floored so it only reads 100 when every lesson is really done.
  * `lesson.course_id` must always equal its module's course (checked on every create/move).
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.timeutil import user_today
from app.models import Course, CourseLesson, CourseModule, LearningSession, User
from app.schemas import courses as s

COURSE_STATUSES = ("active", "paused", "completed", "archived")


class NotFound(Exception):
    pass


class RuleError(ValueError):
    """A business-rule violation the client should see as HTTP 422."""


class Conflict(Exception):
    """The request clashes with existing data (HTTP 409)."""


# ============================== templates ==============================
# Only content verified against the provider's public page is seeded. Module titles come from
# https://www.deeplearning.ai/courses/agentic-ai ; individual lessons are deliberately NOT pre-filled because the
# published sources disagree on lesson-level details — the user adds the lessons they actually take.

TEMPLATES: dict[str, dict] = {
    "deeplearning-agentic-ai": {
        "title": "Agentic AI",
        "provider": "DeepLearning.AI",
        "url": "https://www.deeplearning.ai/courses/agentic-ai",
        "description": (
            "Taught by Andrew Ng. The five module titles below come from the public course page. Lessons are not "
            "pre-filled: add the ones you take (paste a list into a module) so your progress reflects what you "
            "actually completed."
        ),
        "modules": [
            "Module 1: Introduction to Agentic Workflows",
            "Module 2: Reflection",
            "Module 3: Tool Use",
            "Module 4: Practical Tips for Building Agentic AI",
            "Module 5: Patterns for Highly Autonomous Agents",
        ],
    }
}


def list_templates(db: Session, user: User) -> list[dict]:
    existing_urls = set(db.scalars(select(Course.url).where(Course.user_id == user.id, Course.url.is_not(None))))
    return [
        {"key": key, **{k: t[k] for k in ("title", "provider", "url", "description", "modules")},
         "already_added": t["url"] in existing_urls}
        for key, t in TEMPLATES.items()
    ]


def add_template(db: Session, user: User, key: str) -> Course:
    t = TEMPLATES.get(key)
    if t is None:
        raise NotFound("Template not found")
    if db.scalar(select(Course.id).where(Course.user_id == user.id, Course.url == t["url"])):
        raise Conflict("You have already added this course")
    course = Course(
        user_id=user.id, title=t["title"], provider=t["provider"], url=t["url"], description=t["description"],
        kind="course", status="active", priority=2,
    )
    db.add(course)
    db.flush()
    for i, title in enumerate(t["modules"], start=1):
        db.add(CourseModule(course_id=course.id, title=title, position=i))  # modules only — no lessons, nothing completed
    db.commit()
    return _load_course(db, user, course.id)


# ============================== loading ==============================


def _course_query(user: User):
    return (
        select(Course)
        .where(Course.user_id == user.id)
        .options(selectinload(Course.modules).selectinload(CourseModule.lessons))
    )


def _load_course(db: Session, user: User, course_id: int) -> Course:
    # populate_existing: the session keeps objects after commit (expire_on_commit=False), so without this a
    # reload after a reorder/delete could hand back stale in-memory collections. It also OVERWRITES in-memory
    # state with what is in the database, so pending changes must be flushed first or they would be lost.
    db.flush()
    course = db.scalar(_course_query(user).where(Course.id == course_id).execution_options(populate_existing=True))
    if course is None:
        raise NotFound("Course not found")
    return course


def _get_module(db: Session, user: User, module_id: int) -> CourseModule:
    module = db.scalar(
        select(CourseModule)
        .join(Course, Course.id == CourseModule.course_id)
        .where(CourseModule.id == module_id, Course.user_id == user.id)
    )
    if module is None:
        raise NotFound("Module not found")
    return module


def _get_lesson(db: Session, user: User, lesson_id: int) -> CourseLesson:
    lesson = db.scalar(
        select(CourseLesson)
        .join(Course, Course.id == CourseLesson.course_id)
        .where(CourseLesson.id == lesson_id, Course.user_id == user.id)
    )
    if lesson is None:
        raise NotFound("Lesson not found")
    return lesson


def _all_lessons(course: Course) -> list[CourseLesson]:
    """Lessons in study order: by module position, then lesson position."""
    return [lesson for m in course.modules for lesson in m.lessons]


# ============================== derived values ==============================


def progress(course: Course) -> dict:
    lessons = _all_lessons(course)
    total = len(lessons)
    done = sum(1 for lesson in lessons if lesson.status == "completed")
    return {
        "total_lessons": total,
        "completed_lessons": done,
        "percent": (100 * done) // total if total else 0,
        "total_minutes": sum(lesson.duration_minutes or 0 for lesson in lessons),
        "remaining_minutes": sum(lesson.duration_minutes or 0 for lesson in lessons if lesson.status != "completed"),
    }


def next_lesson(course: Course) -> dict | None:
    """The first lesson, in study order, that is not completed (an in-progress one counts)."""
    for module in course.modules:
        for lesson in module.lessons:
            if lesson.status != "completed":
                return {"id": lesson.id, "title": lesson.title, "module_id": module.id,
                        "module_title": module.title, "status": lesson.status, "url": lesson.url}
    return None


def _minutes_studied(db: Session, course_ids: list[int]) -> dict[int, int]:
    if not course_ids:
        return {}
    rows = db.execute(
        select(LearningSession.course_id, func.sum(LearningSession.minutes))
        .where(LearningSession.course_id.in_(course_ids))
        .group_by(LearningSession.course_id)
    )
    return {cid: int(total) for cid, total in rows}


def _summary_dict(course: Course, studied: dict[int, int]) -> dict:
    return {
        **{k: getattr(course, k) for k in (
            "id", "title", "provider", "url", "description", "kind", "status", "priority", "target_date",
            "started_at", "completed_at", "last_studied_at")},
        "progress": progress(course),
        "next_lesson": next_lesson(course),
        "minutes_studied": studied.get(course.id, 0),
    }


def course_summary(db: Session, course: Course) -> dict:
    return _summary_dict(course, _minutes_studied(db, [course.id]))


def course_detail(db: Session, course: Course) -> dict:
    return {
        **course_summary(db, course),
        "notes": course.notes,
        "modules": [
            {
                "id": m.id, "title": m.title, "position": m.position,
                "total_lessons": len(m.lessons),
                "completed_lessons": sum(1 for lesson in m.lessons if lesson.status == "completed"),
                "lessons": m.lessons,
            }
            for m in course.modules
        ],
    }


# ============================== state machine ==============================


def _sync_course(course: Course, now: datetime | None = None) -> None:
    """Keep the course's status consistent with its lessons. Call after ANY change to lessons."""
    now = now or datetime.now(timezone.utc)
    lessons = _all_lessons(course)
    all_done = bool(lessons) and all(lesson.status == "completed" for lesson in lessons)
    if all_done and course.status in ("active", "paused"):
        course.status = "completed"
        course.completed_at = course.completed_at or now
    elif not all_done and course.status == "completed" and lessons:
        course.status = "active"
        course.completed_at = None
    elif course.status == "completed" and not lessons and course.completed_at is None:
        course.completed_at = now


# ============================== courses ==============================


def list_courses(db: Session, user: User, status: str | None = None) -> list[dict]:
    q = _course_query(user).order_by(Course.priority, Course.title)
    if status:
        q = q.where(Course.status == status)
    courses = list(db.scalars(q))
    studied = _minutes_studied(db, [c.id for c in courses])
    return [_summary_dict(c, studied) for c in courses]


def get_course(db: Session, user: User, course_id: int) -> Course:
    return _load_course(db, user, course_id)


def create_course(db: Session, user: User, data: s.CourseCreate) -> Course:
    course = Course(user_id=user.id, **data.model_dump())
    db.add(course)
    db.commit()
    return _load_course(db, user, course.id)


def update_course(db: Session, user: User, course_id: int, data: s.CourseUpdate, now: datetime | None = None) -> Course:
    course = _load_course(db, user, course_id)
    changes = data.model_dump(exclude_unset=True)
    for required in ("title", "kind", "priority", "status"):
        if required in changes and changes[required] is None:
            raise RuleError(f"{required} can't be empty")

    new_status = changes.pop("status", None)
    for field, value in changes.items():
        setattr(course, field, value)

    if new_status is not None and new_status != course.status:
        if new_status == "completed":
            if _all_lessons(course):
                raise RuleError("A course is completed automatically once all its lessons are done")
            course.completed_at = now or datetime.now(timezone.utc)  # lesson-less course: completed by hand
        else:
            course.completed_at = None
        course.status = new_status
    _sync_course(course, now)  # e.g. resuming a course whose lessons are all done leaves it completed
    db.commit()
    return _load_course(db, user, course_id)


def delete_course(db: Session, user: User, course_id: int) -> None:
    course = _load_course(db, user, course_id)
    db.delete(course)  # modules + lessons cascade; study sessions keep their minutes (course_id → NULL)
    db.commit()


# ============================== modules ==============================


def _next_module_position(db: Session, course_id: int) -> int:
    return (db.scalar(select(func.max(CourseModule.position)).where(CourseModule.course_id == course_id)) or 0) + 1


def _next_lesson_position(db: Session, module_id: int) -> int:
    return (db.scalar(select(func.max(CourseLesson.position)).where(CourseLesson.module_id == module_id)) or 0) + 1


def create_module(db: Session, user: User, course_id: int, data: s.ModuleCreate) -> Course:
    course = _load_course(db, user, course_id)
    db.add(CourseModule(course_id=course.id, title=data.title, position=_next_module_position(db, course.id)))
    db.commit()
    return _load_course(db, user, course_id)


def update_module(db: Session, user: User, module_id: int, data: s.ModuleUpdate) -> Course:
    module = _get_module(db, user, module_id)
    module.title = data.title
    db.commit()
    return _load_course(db, user, module.course_id)


def delete_module(db: Session, user: User, module_id: int) -> Course:
    module = _get_module(db, user, module_id)
    course_id = module.course_id
    db.delete(module)
    db.commit()
    course = _load_course(db, user, course_id)
    _sync_course(course)
    db.commit()
    return _load_course(db, user, course_id)


def _swap_with_neighbour(siblings: list, item, direction: str) -> None:
    i = siblings.index(item)
    j = i - 1 if direction == "up" else i + 1
    if 0 <= j < len(siblings):
        siblings[i].position, siblings[j].position = siblings[j].position, siblings[i].position


def move_module(db: Session, user: User, module_id: int, direction: str) -> Course:
    module = _get_module(db, user, module_id)
    course = _load_course(db, user, module.course_id)
    _swap_with_neighbour(course.modules, next(m for m in course.modules if m.id == module_id), direction)
    db.commit()
    return _load_course(db, user, course.id)


# ============================== lessons ==============================


def create_lesson(db: Session, user: User, module_id: int, data: s.LessonCreate) -> Course:
    module = _get_module(db, user, module_id)
    db.add(CourseLesson(
        module_id=module.id, course_id=module.course_id, position=_next_lesson_position(db, module.id),
        **data.model_dump(),
    ))
    db.flush()
    course = _load_course(db, user, module.course_id)
    _sync_course(course)  # a new unfinished lesson reopens a completed course
    db.commit()
    return _load_course(db, user, module.course_id)


def bulk_create_lessons(db: Session, user: User, course_id: int, data: s.BulkLessons) -> Course:
    module = _get_module(db, user, data.module_id)
    if module.course_id != course_id:
        raise RuleError("That module doesn't belong to this course")
    pos = _next_lesson_position(db, module.id)
    for i, title in enumerate(data.titles):
        db.add(CourseLesson(module_id=module.id, course_id=course_id, title=title, position=pos + i))
    db.flush()
    _sync_course(_load_course(db, user, course_id))
    db.commit()
    return _load_course(db, user, course_id)


def update_lesson(db: Session, user: User, lesson_id: int, data: s.LessonUpdate) -> Course:
    lesson = _get_lesson(db, user, lesson_id)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("title", "x") is None or changes.get("lesson_type", "x") is None:
        raise RuleError("title and lesson_type can't be empty")
    target = changes.pop("module_id", None)
    for field, value in changes.items():
        setattr(lesson, field, value)
    if target is not None and target != lesson.module_id:
        dest = _get_module(db, user, target)
        if dest.course_id != lesson.course_id:
            raise RuleError("A lesson can only be moved within its own course")
        lesson.module_id = dest.id
        lesson.position = _next_lesson_position(db, dest.id)
    db.commit()
    return _load_course(db, user, lesson.course_id)


def delete_lesson(db: Session, user: User, lesson_id: int) -> Course:
    lesson = _get_lesson(db, user, lesson_id)
    course_id = lesson.course_id
    db.delete(lesson)
    db.commit()
    course = _load_course(db, user, course_id)
    _sync_course(course)
    db.commit()
    return _load_course(db, user, course_id)


def move_lesson(db: Session, user: User, lesson_id: int, direction: str) -> Course:
    lesson = _get_lesson(db, user, lesson_id)
    course = _load_course(db, user, lesson.course_id)
    module = next(m for m in course.modules if m.id == lesson.module_id)
    _swap_with_neighbour(module.lessons, next(le for le in module.lessons if le.id == lesson_id), direction)
    db.commit()
    return _load_course(db, user, course.id)


def start_lesson(db: Session, user: User, lesson_id: int, now: datetime | None = None) -> Course:
    lesson = _get_lesson(db, user, lesson_id)
    if lesson.status == "completed":
        raise RuleError("This lesson is already completed. Un-complete it first to study it again")
    now = now or datetime.now(timezone.utc)
    lesson.status = "in_progress"
    course = _load_course(db, user, lesson.course_id)
    course.started_at = course.started_at or now
    course.last_studied_at = now
    db.commit()
    return _load_course(db, user, lesson.course_id)


def complete_lesson(db: Session, user: User, lesson_id: int, now: datetime | None = None) -> Course:
    """The ONLY way a lesson becomes completed. Idempotent: completing again keeps the first completion time."""
    lesson = _get_lesson(db, user, lesson_id)
    now = now or datetime.now(timezone.utc)
    if lesson.status != "completed":
        lesson.status = "completed"
        lesson.completed_at = now
    course = _load_course(db, user, lesson.course_id)
    course.started_at = course.started_at or now
    course.last_studied_at = now
    _sync_course(course, now)
    db.commit()
    return _load_course(db, user, lesson.course_id)


def uncomplete_lesson(db: Session, user: User, lesson_id: int, now: datetime | None = None) -> Course:
    lesson = _get_lesson(db, user, lesson_id)
    lesson.status = "not_started"
    lesson.completed_at = None
    course = _load_course(db, user, lesson.course_id)
    _sync_course(course, now)
    db.commit()
    return _load_course(db, user, lesson.course_id)


# ============================== study sessions ==============================


def list_sessions(db: Session, user: User, course_id: int | None = None, limit: int = 50, offset: int = 0) -> list[LearningSession]:
    q = select(LearningSession).where(LearningSession.user_id == user.id)
    if course_id is not None:
        q = q.where(LearningSession.course_id == course_id)
    return list(db.scalars(q.order_by(LearningSession.date.desc(), LearningSession.id.desc()).limit(limit).offset(offset)))


def create_session(db: Session, user: User, data: s.SessionCreate, now: datetime | None = None) -> LearningSession:
    course = _load_course(db, user, data.course_id)
    if data.lesson_id is not None:
        try:
            lesson = _get_lesson(db, user, data.lesson_id)
        except NotFound:
            lesson = None
        if lesson is None or lesson.course_id != course.id:
            raise RuleError("That lesson doesn't belong to this course")
    today = user_today(user, now)
    day = data.date or today
    if day > today:
        raise RuleError("You can't log study time in the future")
    session = LearningSession(
        user_id=user.id, course_id=course.id, lesson_id=data.lesson_id, date=day, minutes=data.minutes, notes=data.notes
    )
    db.add(session)
    if day == today:
        course.last_studied_at = now or datetime.now(timezone.utc)
        course.started_at = course.started_at or course.last_studied_at
    db.commit()
    return session


def delete_session(db: Session, user: User, session_id: int) -> None:
    session = db.scalar(select(LearningSession).where(LearningSession.id == session_id, LearningSession.user_id == user.id))
    if session is None:
        raise NotFound("Study session not found")
    db.delete(session)
    db.commit()


def weekly_minutes(db: Session, user: User, now: datetime | None = None) -> int:
    """Minutes studied in the last 7 local days (today included). Used by the dashboard later."""
    today = user_today(user, now)
    return int(db.scalar(
        select(func.coalesce(func.sum(LearningSession.minutes), 0)).where(
            LearningSession.user_id == user.id, LearningSession.date > today - timedelta(days=7), LearningSession.date <= today
        )
    ) or 0)
