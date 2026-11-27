"""Phase 11: the private share link and the public progress page (/share/<token>)."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models import Course, DailyChallenge, GitCommit, GitRepository, Project, RoadmapStage, RoadmapTopic, Task, User
from app.services import auth as auth_service
from app.services import notifications, portfolio

SETUP = {"email": "me@example.com", "password": "correct-horse-9", "display_name": "Ada <b>L</b>", "timezone": "Asia/Kolkata"}
NOW = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def c(client):
    assert client.post("/api/auth/setup", json=SETUP).status_code == 201
    return client


def enable(c) -> str:
    r = c.post("/api/share")
    assert r.status_code == 201, r.text
    return r.json()["token"]


@pytest.fixture
def user(db) -> User:
    return db.query(User).first() or auth_service.create_first_user(db, email="me@example.com", password="correct-horse-9", display_name="Me", timezone="Asia/Kolkata")


def add_commit(db, user, *, private=False, verified=True, message="Add retrieval step\n\nlong body with secrets", sha="a1b2c3d4e5f6a7b8", when=date(2026, 11, 20)):
    repo = db.query(GitRepository).filter_by(user_id=user.id, full_name="me/rag-bot").first()
    if repo is None:
        repo = GitRepository(user_id=user.id, owner="me", name="rag-bot", full_name="me/rag-bot", url="https://github.com/me/rag-bot", is_private=private)
        db.add(repo)
        db.flush()
    commit = GitCommit(repository_id=repo.id, sha=sha, message=message, url=f"https://github.com/me/rag-bot/commit/{sha}", verification_source="github_api" if verified else "unverified")
    proj = db.query(Project).filter_by(user_id=user.id, title="RAG bot").first()
    if proj is None:
        proj = Project(user_id=user.id, title="RAG bot", status="active", tech_stack='["Python", "FastAPI"]', repo_url="https://github.com/me/rag-bot", repository_id=repo.id)
        db.add(proj)
    db.add(commit)
    db.flush()
    db.add(DailyChallenge(
        user_id=user.id, date=when, mode="existing_project", project_id=proj.id, planned_task="x", status="completed", evidence_type="commit",
        implemented_summary="PRIVATE write-up that must never be shown", commit_id=commit.id, repo_url=repo.url, commit_sha=sha,
        verification_status="verified" if verified else "unverified",
    ))
    db.commit()
    return proj


# ============================== management API ==============================


def test_endpoints_need_login(client):
    assert client.get("/api/share").status_code == 401
    assert client.post("/api/share").status_code == 401
    assert client.delete("/api/share").status_code == 401


def test_sharing_is_off_until_you_turn_it_on(c):
    assert c.get("/api/share").json() == {"enabled": False, "token": None, "path": None}
    token = enable(c)
    assert len(token) >= 40
    assert c.get("/api/share").json() == {"enabled": True, "token": token, "path": f"/share/{token}"}


def test_a_new_link_kills_the_old_one(c):
    old = enable(c)
    assert c.get(f"/share/{old}").status_code == 200
    new = enable(c)
    assert new != old
    assert c.get(f"/share/{old}").status_code == 404
    assert c.get(f"/share/{new}").status_code == 200


def test_turning_it_off_kills_the_link(c):
    token = enable(c)
    assert c.delete("/api/share").status_code == 204
    assert c.get(f"/share/{token}").status_code == 404
    assert c.get("/api/share").json()["enabled"] is False


# ============================== the public page ==============================


def test_the_page_needs_no_login_and_wrong_tokens_look_the_same(c, client):
    token = enable(c)
    client.cookies.clear()
    assert client.get(f"/share/{token}").status_code == 200
    a, b = client.get("/share/" + "x" * 43), client.get("/share/short")
    assert a.status_code == b.status_code == 404 and a.json() == b.json()


def test_the_page_is_locked_down(c, client):
    token = enable(c)
    r = c.get(f"/share/{token}")
    assert r.headers["content-type"].startswith("text/html")
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store" and "noindex" in r.headers["x-robots-tag"] and r.headers["referrer-policy"] == "no-referrer"
    assert "<script" not in r.text.lower() and 'name="robots" content="noindex' in r.text


def test_the_name_is_escaped(c):
    html = c.get(f"/share/{enable(c)}").text
    assert "Ada &lt;b&gt;L&lt;/b&gt;" in html and "Ada <b>L</b>" not in html


def test_only_verified_commits_appear_and_only_their_first_line(db, c, user):
    add_commit(db, user)
    add_commit(db, user, verified=False, message="Unverified claim", sha="ffffffff00000000", when=date(2026, 11, 19))
    html = c.get(f"/share/{enable(c)}").text
    assert "Add retrieval step" in html and "me/rag-bot@a1b2c3d" in html and "https://github.com/me/rag-bot/commit/a1b2c3d4e5f6a7b8" in html
    assert "long body with secrets" not in html and "PRIVATE write-up" not in html
    assert "Unverified claim" not in html and "ffffffff" not in html


def test_private_repositories_show_no_name_and_no_link(db, c, user):
    add_commit(db, user, private=True)
    html = c.get(f"/share/{enable(c)}").text
    assert "Add retrieval step" in html and "<code>a1b2c3d</code>" in html
    assert "me/rag-bot" not in html and "commit/a1b2c3d" not in html


def test_topics_courses_and_projects_are_listed_but_not_tasks(db, c, user):
    stage = RoadmapStage(user_id=user.id, title="Foundations", position=0)
    stage.topics.append(RoadmapTopic(user_id=user.id, title="Vector search", position=0, status="completed", completion_pct=100, completed_at=NOW))
    stage.topics.append(RoadmapTopic(user_id=user.id, title="Unfinished topic", position=1))
    db.add(stage)
    db.add(Course(user_id=user.id, title="RAG course", provider="Coursera", status="completed", completed_at=NOW))
    db.add(Course(user_id=user.id, title="Half done", status="active"))
    db.add(Task(user_id=user.id, title="Secret errand"))
    db.add(Project(user_id=user.id, title="Idea only", status="paused"))
    db.add(Project(user_id=user.id, title="Notes bot", status="active", tech_stack='["Go"]'))
    db.commit()
    html = c.get(f"/share/{enable(c)}").text
    assert "Vector search" in html and "Foundations" in html and "RAG course" in html and "Coursera" in html and "Notes bot" in html and ">Go<" in html
    for hidden in ("Unfinished topic", "Half done", "Secret errand", "Idea only", "me@example.com"):
        assert hidden not in html


def test_a_project_with_a_typed_in_repo_url_gets_no_link(db, c, user):
    p = add_commit(db, user)
    p.repository_id = None   # only a typed-in URL: it could be a private repo, so it is never linked
    db.commit()
    html = c.get(f"/share/{enable(c)}").text
    assert "RAG bot" in html and 'href="https://github.com/me/rag-bot"' not in html


def test_a_non_https_repo_link_is_not_made_clickable(db, c, user):
    p = add_commit(db, user)
    repo = db.query(GitRepository).first()
    repo.url = "javascript:alert(1)"
    db.commit()
    html = c.get(f"/share/{enable(c)}").text
    assert "javascript:" not in html


def test_an_empty_page_still_renders(c):
    html = c.get(f"/share/{enable(c)}").text
    assert "No verified commits yet." in html and "No topics finished yet." in html


def test_the_page_lists_only_the_latest_commits_and_says_so(db, c, user):
    for i in range(portfolio.MAX_COMMITS + 3):
        add_commit(db, user, sha=f"{i:040x}", when=date(2026, 1, 1) + timedelta(days=i))
    html = c.get(f"/share/{enable(c)}").text
    assert html.count("Add retrieval step") == portfolio.MAX_COMMITS
    assert f"latest {portfolio.MAX_COMMITS} shown" in html


def test_pages_are_per_user(db, c, user):
    add_commit(db, user)
    other = User(id=2, email="o@example.com", password_hash="x", display_name="Other Person", timezone="UTC")
    db.add(other)
    db.commit()
    html = c.get(f"/share/{enable(c)}").text
    assert "Other Person" not in html


# ============================== weekly e-mail ==============================


def test_the_weekly_e_mail_carries_the_link_only_when_sharing_is_on(db, c, user):
    sent = notifications.render(db, user, "weekly_report", NOW, "https://hub.example.com")
    assert "/share/" not in sent["html"] and "/share/" not in sent["text"]
    token = enable(c)
    db.expire_all()
    user = db.query(User).first()
    sent = notifications.render(db, user, "weekly_report", NOW, "https://hub.example.com/")
    assert f"https://hub.example.com/share/{token}" in sent["html"] and f"https://hub.example.com/share/{token}" in sent["text"]
