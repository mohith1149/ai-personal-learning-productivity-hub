"""Dashboard: one read-only summary assembled from the other features' services.

Nothing is stored for the dashboard. Every number comes from the same functions the feature pages use, so the dashboard can't disagree with
them, and a brand-new account simply gets zeros and empty lists (never invented figures)."""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.timeutil import user_today
from app.models import LearningSession, ProjectSession, User
from app.services import challenges, courses, habits, planner, projects, roadmap, tasks, videos

NEXT_ITEMS = 6
MAX_PROJECTS = 5


def _week(db: Session, user: User, today) -> list[dict]:
    start = today - timedelta(days=6)

    def per_day(model) -> dict:
        rows = db.execute(select(model.date, func.sum(model.minutes)).where(model.user_id == user.id, model.date >= start, model.date <= today)
                          .group_by(model.date))
        return {d: int(m) for d, m in rows}

    study, dev = per_day(LearningSession), per_day(ProjectSession)
    days = [start + timedelta(days=i) for i in range(7)]
    return [{"date": d, "study_minutes": study.get(d, 0), "dev_minutes": dev.get(d, 0)} for d in days]


def _videos(db: Session, user: User, now: datetime | None) -> list[dict]:
    out = []
    for p in videos.list_playlists(db, user, now):
        if not p["active"] or p["daily_target"] <= 0:
            continue
        t = videos.today(db, user, p["id"], now)
        if not t["target_met"] and not t["up_next"]:
            continue  # nothing left to watch in this collection, so there is nothing to remind about
        out.append({"playlist_id": p["id"], "name": p["name"], "daily_target": t["daily_target"], "watched_today": t["watched_today"],
                    "remaining_today": t["remaining_today"], "target_met": t["target_met"], "up_next": [v.title for v in t["up_next"]]})
    return out


def _habits(db: Session, user: User, now: datetime | None) -> dict:
    data = habits.list_habits(db, user, now)
    active = [h for h in data["items"] if h["active"]]
    best = max(active, key=lambda h: h["streak"]["current"], default=None)
    has = best is not None and best["streak"]["current"] > 0
    return {"active": len(active), "due_today": data["due_today"], "best_streak": best["streak"]["current"] if has else 0,
            "best_streak_name": best["name"] if has else None, "best_streak_unit": best["streak"]["unit"] if has else None}


def build(db: Session, user: User, now: datetime | None = None) -> dict:
    today = user_today(user, now)
    rm = roadmap.get_roadmap(db, user)  # first: it seeds the roadmap on first use, and the plan below includes roadmap topics
    plan = planner.build_day(db, user, today, now)
    open_items = [i for i in plan["items"] if i["status"] in ("overdue", "pending")]
    counts = tasks.counts(db, user, now)
    plist = projects.list_projects(db, user, "active", now)
    plist.sort(key=lambda p: (p["last_activity_at"] is not None, p["last_activity_at"].timestamp() if p["last_activity_at"] else 0))  # least recently worked first
    clist = courses.list_courses(db, user, "active")
    road = rm["overall"], rm["next_topic"]
    today_view = challenges.today_view(db, user, now)
    vids = _videos(db, user, now)
    hab = _habits(db, user, now)
    all_projects = projects.list_projects(db, user, None, now)
    has_playlists = bool(videos.list_playlists(db, user, now))
    is_empty = (counts["all"] == 0 and not clist and not all_projects and not has_playlists and not hab["active"]
                and today_view["stats"]["first_day"] is None and not courses.list_courses(db, user))
    return {
        "date": today,
        "plan": {"summary": plan["summary"], "next_items": open_items[:NEXT_ITEMS], "open_count": len(open_items)},
        "videos": vids,
        "challenge": {"today": today_view["challenge"], "stats": today_view["stats"]},
        "habits": hab,
        "tasks": {"overdue": counts["overdue"], "today": counts["today"], "completed_today": counts["completed_today"]},
        "projects": [{"id": p["id"], "title": p["title"], "percent": p["progress"]["percent"], "minutes_spent": p["minutes_spent"],
                      "last_activity_at": p["last_activity_at"].isoformat() if p["last_activity_at"] else None} for p in plist[:MAX_PROJECTS]],
        "courses": [{"id": c["id"], "title": c["title"], "percent": c["progress"]["percent"],
                     "next_lesson": c["next_lesson"]["title"] if c["next_lesson"] else None} for c in clist],
        "roadmap": {"total": road[0]["total"], "completed": road[0]["completed"], "in_progress": road[0]["in_progress"], "percent": road[0]["percent"],
                    "next_topic": road[1]["title"] if road[1] else None},
        "week": _week(db, user, today),
        "is_empty": is_empty,
    }
