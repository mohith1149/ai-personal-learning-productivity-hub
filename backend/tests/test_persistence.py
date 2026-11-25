"""Persistence: the data and the login survive a restart, and the migrations build exactly the schema the code expects.

These start the REAL server (uvicorn in a subprocess) on a database file, so what is tested is what you run, not a test double. One restart is
a crash (the process is killed with no chance to clean up), because committed data must survive that too."""
import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

BACKEND = Path(__file__).resolve().parents[1]
SETUP = {"email": "me@example.com", "password": "correct-horse-9", "display_name": "Ada", "timezone": "Asia/Kolkata"}
TODAY = datetime.now(ZoneInfo("Asia/Kolkata")).date()
LAST_MON = TODAY - timedelta(days=TODAY.weekday() + 7)


def env_for(db_file: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    env.update(DATABASE_URL=f"sqlite:///{db_file.as_posix()}", SECRET_KEY="persistence-test-secret-key-0123456789-abcdef", ENVIRONMENT="test",
               SCHEDULER_MODE="off", EMAIL_PROVIDER="none", AI_PROVIDER="none", GITHUB_TOKEN="", PYTHONUTF8="1")
    return env


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def server(db_file: Path, log_file: Path):
    """The real app on a free port. Yields the base URL; the caller decides how it ends (kill = crash)."""
    port = free_port()
    with open(log_file, "ab") as log:
        proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)], cwd=BACKEND,
                                env=env_for(db_file), stdout=log, stderr=log)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(150):
            if proc.poll() is not None:
                raise RuntimeError(f"server exited early:\n{log_file.read_text(errors='replace')[-2000:]}")
            try:
                if httpx.get(f"{base}/api/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        else:
            raise RuntimeError("server did not start")
        yield base, proc
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)


def migrate(db_file: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env_for(db_file), capture_output=True, text=True, timeout=180)


@pytest.fixture
def home(tmp_path):
    db = tmp_path / "hub.db"
    done = migrate(db)
    assert done.returncode == 0, done.stderr[-2000:]
    return db, tmp_path / "server.log"


# ------------------------------ migrations ------------------------------


def test_the_migrations_build_exactly_the_schema_the_code_expects(tmp_path):
    """`alembic check` fails if a model changed without a migration, so a fresh install can never differ from a developed one."""
    db = tmp_path / "fresh.db"
    assert migrate(db).returncode == 0
    check = subprocess.run([sys.executable, "-m", "alembic", "check"], cwd=BACKEND, env=env_for(db), capture_output=True, text=True, timeout=120)
    assert check.returncode == 0, (check.stdout + check.stderr)[-2500:]


def test_migrating_twice_is_harmless(tmp_path):
    db = tmp_path / "twice.db"
    assert migrate(db).returncode == 0 and migrate(db).returncode == 0


# ------------------------------ restarts ------------------------------


def seed(c: httpx.Client) -> dict:
    """A little of everything, through the real API."""
    assert c.post("/api/auth/setup", json=SETUP).status_code == 201
    task = c.post("/api/tasks", json={"title": "Read the RAG paper", "scheduled_date": TODAY.isoformat()}).json()
    habit = c.post("/api/habits", json={"name": "Reading", "start_date": (LAST_MON - timedelta(days=10)).isoformat()}).json()
    assert c.put(f"/api/habits/{habit['id']}/logs/{(LAST_MON + timedelta(days=1)).isoformat()}", json={"completed": True}).status_code in (200, 201)
    project = c.post("/api/projects", json={"title": "RAG chatbot"}).json()
    assert c.post(f"/api/projects/{project['id']}/sessions", json={"minutes": 75, "summary": "built the retriever", "date": (LAST_MON + timedelta(days=2)).isoformat()}).status_code == 201
    course = c.post("/api/courses", json={"title": "Agentic AI"}).json()
    assert c.post("/api/learning-sessions", json={"course_id": course["id"], "minutes": 30, "date": (LAST_MON + timedelta(days=2)).isoformat()}).status_code == 201
    return {"task": task["id"], "habit": habit["id"], "project": project["id"], "course": course["id"]}


def snapshot(c: httpx.Client) -> dict:
    """What the app shows right now, reduced to comparable facts."""
    rep = c.get("/api/reports/weekly", params={"week_start": LAST_MON.isoformat()}).json()
    return {
        "auth": c.get("/api/auth/status").json()["authenticated"],
        "tasks": sorted(t["title"] for t in c.get("/api/tasks", params={"view": "all"}).json()["items"]),
        "habits": sorted(h["name"] for h in c.get("/api/habits").json()["items"]),
        "projects": [(p["title"], p["minutes_spent"]) for p in c.get("/api/projects").json()],
        "courses": [(x["title"], x["minutes_studied"]) for x in c.get("/api/courses").json()],
        "report": rep["totals"],
        "report_projects": rep["projects"],
        "roadmap_topics": c.get("/api/roadmap").json()["overall"]["total"],
    }


def test_data_and_login_survive_a_crash_and_a_clean_restart(home):
    db, log = home
    with server(db, log) as (base, proc):
        c = httpx.Client(base_url=base, timeout=20)
        ids = seed(c)
        before = snapshot(c)
        assert before["auth"] is True and before["tasks"] == ["Read the RAG paper"] and before["report"]["project_minutes"] == 75 and before["report"]["study_minutes"] == 30
        cookies = dict(c.cookies)
        proc.kill()                                                    # a crash: no shutdown hooks, no flush
        proc.wait(timeout=10)

    with server(db, log) as (base, proc):                              # a different process, a different port, the same database file
        c = httpx.Client(base_url=base, timeout=20, cookies=cookies)   # the cookie from before the crash
        assert snapshot(c) == before                                   # still signed in, nothing lost, every figure identical
        assert c.get(f"/api/tasks/{ids['task']}").json()["title"] == "Read the RAG paper"
        assert c.post("/api/tasks", json={"title": "Written after the restart"}).status_code == 201
        proc.terminate()                                               # a clean stop this time
        proc.wait(timeout=20)

    with server(db, log) as (base, _):
        c = httpx.Client(base_url=base, timeout=20)
        assert c.get("/api/auth/status").json()["authenticated"] is False          # no cookie, so signed out
        assert c.post("/api/auth/login", json={"email": SETUP["email"], "password": SETUP["password"]}).status_code == 200   # the password still works
        assert sorted(t["title"] for t in c.get("/api/tasks", params={"view": "all"}).json()["items"]) == ["Read the RAG paper", "Written after the restart"]
        assert c.post("/api/auth/login", json={"email": SETUP["email"], "password": "wrong-password-1"}).status_code == 401


def test_signing_out_survives_a_restart_too(home):
    """A signed-out cookie must stay dead after a restart (the session is revoked in the database, not just forgotten in memory)."""
    db, log = home
    with server(db, log) as (base, proc):
        c = httpx.Client(base_url=base, timeout=20)
        assert c.post("/api/auth/setup", json=SETUP).status_code == 201
        old = dict(c.cookies)
        assert c.post("/api/auth/logout").status_code in (200, 204)
        assert c.get("/api/auth/status").json()["authenticated"] is False
        proc.kill()
        proc.wait(timeout=10)
    with server(db, log) as (base, _):
        assert httpx.Client(base_url=base, timeout=20, cookies=old).get("/api/auth/status").json()["authenticated"] is False


def test_the_database_file_alone_carries_everything(home, tmp_path):
    """Copy the file while the server is stopped and run a second server on the copy: it is a complete backup."""
    import shutil

    db, log = home
    with server(db, log) as (base, proc):
        c = httpx.Client(base_url=base, timeout=20)
        seed(c)
        before = snapshot(c)
        cookies = dict(c.cookies)
        proc.terminate()
        proc.wait(timeout=20)
    copy = tmp_path / "copy.db"
    shutil.copyfile(db, copy)
    for ext in ("-wal", "-shm"):
        if Path(f"{db}{ext}").exists():
            shutil.copyfile(f"{db}{ext}", f"{copy}{ext}")
    with server(copy, tmp_path / "copy.log") as (base, _):
        assert snapshot(httpx.Client(base_url=base, timeout=20, cookies=cookies)) == before
