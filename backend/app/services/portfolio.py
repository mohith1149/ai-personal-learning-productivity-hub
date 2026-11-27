"""The public progress / portfolio page: what a visitor with your private link can see, and nothing else.

Shown:   your display name; challenge streaks; hours studied and hours of development; the daily challenges whose commit was VERIFIED against
         GitHub (project, first line of the commit message, short hash, date, and a link when the repository is public); roadmap topics and
         courses you completed; your active and completed projects (title, technologies, link when the repository is public).
Never:   tasks, habits, notes, evidence write-ups, e-mail address, private repository names or links, anything unverified.
Every value is HTML-escaped. The page has no scripts, loads nothing from other sites and asks search engines not to index it.
"""
import json
from datetime import datetime, timedelta
from html import escape

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.timeutil import user_today, user_tz
from app.models import Course, DailyChallenge, GitCommit, GitRepository, LearningSession, Project, ProjectSession, RoadmapStage, RoadmapTopic, User
from app.services import challenges

MAX_COMMITS = 60


def _day(user: User, moment: datetime | None):
    if moment is None:
        return None
    return moment.astimezone(user_tz(user)).date() if moment.tzinfo else moment.date()


def _first_line(text: str | None) -> str:
    return (text or "").strip().splitlines()[0][:200] if (text or "").strip() else ""


def _public_url(url: str | None) -> str | None:
    return url if url and url.startswith("https://") else None


def build(db: Session, user: User, now: datetime | None = None) -> dict:
    today = user_today(user, now)
    stats = challenges.calendar(db, user, today - timedelta(days=365), today, now)["stats"]

    rows = db.execute(
        select(DailyChallenge, GitCommit, GitRepository, Project)
        .join(GitCommit, DailyChallenge.commit_id == GitCommit.id)
        .join(GitRepository, GitCommit.repository_id == GitRepository.id)
        .outerjoin(Project, DailyChallenge.project_id == Project.id)
        .where(DailyChallenge.user_id == user.id, DailyChallenge.status == "completed", DailyChallenge.verification_status == "verified")
        .order_by(DailyChallenge.date.desc()).limit(MAX_COMMITS)
    ).all()
    commits = [{
        "date": ch.date, "project": proj.title if proj else None, "message": _first_line(c.message), "sha": c.sha[:7],
        "repo": None if repo.is_private else repo.full_name, "url": None if repo.is_private else _public_url(c.url),
    } for ch, c, repo, proj in rows]
    verified_total = db.scalar(select(func.count()).select_from(DailyChallenge).where(
        DailyChallenge.user_id == user.id, DailyChallenge.status == "completed", DailyChallenge.verification_status == "verified")) or 0

    topics = db.execute(
        select(RoadmapTopic, RoadmapStage.title).join(RoadmapStage, RoadmapTopic.stage_id == RoadmapStage.id)
        .where(RoadmapTopic.user_id == user.id, RoadmapTopic.status == "completed").order_by(RoadmapTopic.completed_at.desc())
    ).all()
    courses = db.scalars(select(Course).where(Course.user_id == user.id, Course.status == "completed").order_by(Course.completed_at.desc())).all()
    projects = db.execute(
        select(Project, GitRepository).outerjoin(GitRepository, Project.repository_id == GitRepository.id)
        .where(Project.user_id == user.id, Project.status.in_(("active", "completed"))).order_by(Project.created_at.desc())).all()

    study = db.scalar(select(func.coalesce(func.sum(LearningSession.minutes), 0)).where(LearningSession.user_id == user.id)) or 0
    dev = db.scalar(select(func.coalesce(func.sum(ProjectSession.minutes), 0)).where(ProjectSession.user_id == user.id)) or 0

    return {
        "name": user.display_name,
        "generated": today,
        "streak": stats["current_streak"], "longest_streak": stats["longest_streak"],
        "study_hours": round(study / 60, 1), "dev_hours": round(dev / 60, 1),
        "verified_total": int(verified_total),
        "commits": commits,
        "topics": [{"title": t.title, "stage": stage, "date": _day(user, t.completed_at)} for t, stage in topics],
        "courses": [{"title": c.title, "provider": c.provider, "date": _day(user, c.completed_at)} for c in courses],
        # a link only when the project is tied to a repository known to be public; a typed-in URL could be a private repo
        "projects": [{"title": p.title, "status": p.status, "stack": _stack(p), "url": _public_url(r.url) if r is not None and not r.is_private else None} for p, r in projects],
    }


def _stack(p: Project) -> list[str]:
    try:
        v = json.loads(p.tech_stack) if p.tech_stack else []
        return [str(x) for x in v][:12] if isinstance(v, list) else []
    except ValueError:
        return []


CSS = """
:root{color-scheme:light dark;--bg:#f8fafc;--fg:#0f172a;--mut:#475569;--card:#fff;--line:#e2e8f0;--acc:#4f46e5}
@media (prefers-color-scheme:dark){:root{--bg:#020617;--fg:#f1f5f9;--mut:#94a3b8;--card:#0f172a;--line:#1e293b;--acc:#a5b4fc}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:860px;margin:0 auto;padding:32px 20px 64px}h1{margin:0 0 4px;font-size:1.9rem}h2{margin:36px 0 12px;font-size:1.1rem}
.sub{color:var(--mut);margin:0}.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:24px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}.stat b{display:block;font-size:1.6rem;font-variant-numeric:tabular-nums}
.stat span{color:var(--mut);font-size:.85rem}ul{list-style:none;margin:0;padding:0}li{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin-bottom:8px}
li .t{font-weight:600}li .m{color:var(--mut);font-size:.875rem}a{color:var(--acc)}code{font:13px ui-monospace,SFMono-Regular,Menlo,monospace}
.tag{display:inline-block;background:var(--line);border-radius:999px;padding:0 8px;font-size:.75rem;margin:4px 4px 0 0}footer{margin-top:40px;color:var(--mut);font-size:.8rem}
"""


def _link(text: str, url: str | None) -> str:
    return f'<a href="{escape(url, quote=True)}" rel="noopener noreferrer nofollow">{escape(text)}</a>' if url else escape(text)


def _section(title: str, items: list[str], empty: str) -> str:
    body = "<ul>" + "".join(items) + "</ul>" if items else f'<p class="sub">{escape(empty)}</p>'
    return f"<section><h2>{escape(title)}</h2>{body}</section>"


def render_html(d: dict) -> str:
    stat = lambda v, label: f'<div class="stat"><b>{escape(str(v))}</b><span>{escape(label)}</span></div>'  # noqa: E731
    commits = [
        f'<li><div class="t">{escape(c["message"] or "Verified commit")}</div><div class="m">'
        f'{escape(c["date"].isoformat())}{" · " + escape(c["project"]) if c["project"] else ""}'
        f'{" · " + _link(c["repo"] + "@" + c["sha"], c["url"]) if c["repo"] else " · <code>" + escape(c["sha"]) + "</code>"}</div></li>'
        for c in d["commits"]
    ]
    topics = [f'<li><div class="t">{escape(t["title"])}</div><div class="m">{escape(t["stage"])}{" · finished " + escape(t["date"].isoformat()) if t["date"] else ""}</div></li>' for t in d["topics"]]
    courses = [f'<li><div class="t">{escape(c["title"])}</div><div class="m">{escape(c["provider"] or "")}{" · finished " + escape(c["date"].isoformat()) if c["date"] else ""}</div></li>' for c in d["courses"]]
    projects = [
        f'<li><div class="t">{_link(p["title"], p["url"])}</div><div class="m">{"Completed" if p["status"] == "completed" else "In progress"}</div>'
        + "".join(f'<span class="tag">{escape(s)}</span>' for s in p["stack"]) + "</li>"
        for p in d["projects"]
    ]
    shown = f" (latest {len(d['commits'])} shown)" if d["verified_total"] > len(d["commits"]) else ""
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="robots" content="noindex,nofollow"><meta name="referrer" content="no-referrer">'
        f'<title>{escape(d["name"])}: learning progress</title><style>{CSS}</style></head><body><main>'
        f'<h1>{escape(d["name"])}</h1><p class="sub">Learning progress, updated {escape(d["generated"].isoformat())}. Commits listed here were checked against GitHub.</p>'
        f'<div class="stats">{stat(d["streak"], "day streak")}{stat(d["longest_streak"], "longest streak")}{stat(d["verified_total"], "verified commits")}'
        f'{stat(d["study_hours"], "hours studied")}{stat(d["dev_hours"], "hours building")}{stat(len(d["topics"]), "topics finished")}</div>'
        + _section("Verified commits" + shown, commits, "No verified commits yet.")
        + _section("Projects", projects, "No projects yet.")
        + _section("Topics finished", topics, "No topics finished yet.")
        + _section("Courses completed", courses, "No courses completed yet.")
        + "<footer>Shared by its owner through a private link. Anything not listed here is not shared.</footer></main></body></html>"
    )
