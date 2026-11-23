"""HTTP-level tests: authentication, validation, serialisation and routing for the task endpoints.
Dates are far past/future so these never depend on the real clock."""
import pytest

from app.models import Task, User

PAST, FUTURE = "2020-01-01", "2099-01-01"

SETUP = {
    "email": "me@example.com",
    "password": "correct-horse-9",
    "display_name": "Me",
    "timezone": "Asia/Kolkata",
}


@pytest.fixture
def c(client):
    assert client.post("/api/auth/setup", json=SETUP).status_code == 201
    return client


def new_task(c, **kw):
    r = c.post("/api/tasks", json={"title": "Write tests", **kw})
    assert r.status_code == 201, r.text
    return r.json()


# ---------------- authentication ----------------

PROTECTED = [
    ("get", "/api/tasks"),
    ("post", "/api/tasks"),
    ("get", "/api/tasks/counts"),
    ("get", "/api/tasks/1"),
    ("patch", "/api/tasks/1"),
    ("delete", "/api/tasks/1"),
    ("get", "/api/task-categories"),
    ("post", "/api/task-categories"),
    ("patch", "/api/task-categories/1"),
    ("delete", "/api/task-categories/1"),
    ("get", "/api/recurring-tasks"),
    ("post", "/api/recurring-tasks"),
    ("patch", "/api/recurring-tasks/1"),
    ("delete", "/api/recurring-tasks/1"),
]


@pytest.mark.parametrize("method, path", PROTECTED)
def test_every_endpoint_requires_login(client, method, path):
    assert getattr(client, method)(path).status_code == 401


# ---------------- task CRUD ----------------


def test_create_read_update_delete_round_trip(c):
    created = new_task(c, description="d", priority=1, due_date=FUTURE, due_time="09:30", estimated_minutes=45)
    assert created["status"] == "pending" and created["completed_at"] is None and created["is_overdue"] is False
    assert created["priority"] == 1 and created["task_type"] == "one_time" and created["category"] is None

    tid = created["id"]
    assert c.get(f"/api/tasks/{tid}").json()["title"] == "Write tests"

    r = c.patch(f"/api/tasks/{tid}", json={"title": "Write more tests", "priority": 4})
    assert r.status_code == 200 and r.json()["title"] == "Write more tests" and r.json()["priority"] == 4
    assert r.json()["description"] == "d"  # untouched field survives

    assert c.delete(f"/api/tasks/{tid}").status_code == 204
    assert c.get(f"/api/tasks/{tid}").status_code == 404
    assert c.delete(f"/api/tasks/{tid}").status_code == 404


def test_completing_and_reopening_over_http(c):
    tid = new_task(c, due_date=PAST)["id"]
    assert c.get(f"/api/tasks/{tid}").json()["is_overdue"] is True

    done = c.patch(f"/api/tasks/{tid}", json={"status": "completed", "actual_minutes": 20}).json()
    assert done["status"] == "completed" and done["completed_at"] and done["actual_minutes"] == 20
    assert done["is_overdue"] is False  # completed work is never "overdue"

    reopened = c.patch(f"/api/tasks/{tid}", json={"status": "pending"}).json()
    assert reopened["completed_at"] is None and reopened["is_overdue"] is True


def test_explicit_null_clears_and_blank_string_means_none(c):
    tid = new_task(c, description="x", notes="y")["id"]
    r = c.patch(f"/api/tasks/{tid}", json={"description": None, "notes": "   "}).json()
    assert r["description"] is None and r["notes"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {},  # no title
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 201},
        {"title": "ok", "priority": 0},
        {"title": "ok", "priority": 5},
        {"title": "ok", "due_time": "25:00"},
        {"title": "ok", "due_time": "9:30"},
        {"title": "ok", "due_date": "not-a-date"},
        {"title": "ok", "estimated_minutes": 0},
        {"title": "ok", "estimated_minutes": 100000},
        {"title": "ok", "status": "completed"},  # tasks can't be created already completed
        {"title": "ok", "user_id": 5},  # unknown/forbidden field
        {"title": "ok", "is_overdue": True},  # computed field is not writable
    ],
)
def test_create_validation(c, payload):
    assert c.post("/api/tasks", json=payload).status_code == 422


def test_business_rule_violations_are_422_with_a_readable_message(c):
    r = c.post("/api/tasks", json={"title": "x", "due_time": "09:00"})
    assert r.status_code == 422 and "due date" in r.json()["detail"].lower()
    r = c.post("/api/tasks", json={"title": "x", "scheduled_date": FUTURE, "due_date": PAST})
    assert r.status_code == 422 and "before the scheduled" in r.json()["detail"]
    r = c.post("/api/tasks", json={"title": "x", "category_id": 999})
    assert r.status_code == 422


def test_patch_rejects_nulling_required_fields(c):
    tid = new_task(c)["id"]
    assert c.patch(f"/api/tasks/{tid}", json={"title": None}).status_code == 422
    assert c.patch(f"/api/tasks/{tid}", json={"status": None}).status_code == 422


def test_fixed_paths_are_not_swallowed_by_the_id_route(c):
    assert c.get("/api/tasks/counts").status_code == 200
    assert c.get("/api/tasks/abc").status_code == 422


# ---------------- listing, filters, counts ----------------


def test_list_filters_pagination_and_counts(c):
    cat = c.post("/api/task-categories", json={"name": "Study"}).json()
    a = new_task(c, title="Alpha", priority=1, category_id=cat["id"], due_date=PAST)
    new_task(c, title="Beta", priority=3, due_date=FUTURE)
    new_task(c, title="Gamma 100%", priority=3)
    done = new_task(c, title="Delta")
    c.patch(f"/api/tasks/{done['id']}", json={"status": "completed"})

    def titles(**params):
        r = c.get("/api/tasks", params=params)
        assert r.status_code == 200
        return [t["title"] for t in r.json()["items"]], r.json()["total"]

    assert titles(view="overdue") == (["Alpha"], 1)
    assert titles(view="upcoming") == (["Beta"], 1)
    assert titles(view="completed") == (["Delta"], 1)
    assert titles(priority=1) == (["Alpha"], 1)
    assert titles(category_id=cat["id"]) == (["Alpha"], 1)
    assert titles(q="100%") == (["Gamma 100%"], 1)
    assert titles(status="completed") == (["Delta"], 1)
    names, total = titles(view="all", limit=2)
    assert len(names) == 2 and total == 4
    assert titles(view="all", limit=2, offset=3)[0] == ["Delta"]

    counts = c.get("/api/tasks/counts").json()
    assert counts == {"open": 3, "overdue": 1, "today": 0, "upcoming": 1, "completed": 1, "completed_today": 1, "all": 4}
    assert c.get("/api/tasks/" + str(a["id"])).json()["category"] == {"id": cat["id"], "name": "Study", "color": "#6366f1"}


@pytest.mark.parametrize("params", [{"view": "bogus"}, {"status": "bogus"}, {"priority": 9}, {"limit": 0}, {"limit": 501}, {"offset": -1}])
def test_list_rejects_bad_query_params(c, params):
    assert c.get("/api/tasks", params=params).status_code == 422


# ---------------- isolation between users ----------------


def test_other_users_tasks_are_invisible(c, db):
    db.add(User(id=2, email="o@example.com", password_hash="x", display_name="O", timezone="UTC"))
    db.commit()
    theirs = Task(user_id=2, title="not yours", priority=3)
    db.add(theirs)
    db.commit()
    assert c.get("/api/tasks").json() == {"items": [], "total": 0}
    assert c.get(f"/api/tasks/{theirs.id}").status_code == 404
    assert c.patch(f"/api/tasks/{theirs.id}", json={"title": "hijack"}).status_code == 404
    assert c.delete(f"/api/tasks/{theirs.id}").status_code == 404
    db.refresh(theirs)
    assert theirs.title == "not yours"


def test_signing_out_locks_the_task_api(c):
    new_task(c)
    assert c.post("/api/auth/logout").status_code == 204
    assert c.get("/api/tasks").status_code == 401


# ---------------- categories ----------------


def test_category_endpoints(c):
    r = c.post("/api/task-categories", json={"name": "Work", "color": "#112233"})
    assert r.status_code == 201 and r.json()["is_system"] is False
    cid = r.json()["id"]
    assert c.post("/api/task-categories", json={"name": "WORK"}).status_code == 422  # duplicate, any case
    assert c.post("/api/task-categories", json={"name": "Bad", "color": "red"}).status_code == 422
    assert c.patch(f"/api/task-categories/{cid}", json={"name": "Job"}).json()["name"] == "Job"
    tid = new_task(c, category_id=cid)["id"]
    assert c.delete(f"/api/task-categories/{cid}").status_code == 204
    assert c.get(f"/api/tasks/{tid}").json()["category_id"] is None
    assert c.delete(f"/api/task-categories/{cid}").status_code == 404
    assert c.get("/api/task-categories").json() == []


# ---------------- recurring ----------------


def test_recurring_endpoints_generate_tasks_and_expose_days_as_a_list(c):
    r = c.post("/api/recurring-tasks", json={"title": "Gym", "frequency": "weekly", "days_of_week": [4, 0, 0]})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["days_of_week"] == [0, 4] and body["active"] is True and body["last_generated_date"]

    made = c.get("/api/tasks", params={"view": "all"}).json()["items"]
    assert made and all(t["task_type"] == "recurring" and t["recurring_task_id"] == body["id"] for t in made)

    assert c.patch(f"/api/recurring-tasks/{body['id']}", json={"active": False}).json()["active"] is False
    assert c.get("/api/recurring-tasks").json()[0]["title"] == "Gym"
    assert c.delete(f"/api/recurring-tasks/{body['id']}").status_code == 204
    assert c.get("/api/recurring-tasks").json() == []
    assert len(c.get("/api/tasks").json()["items"]) == len(made)  # generated tasks outlive the template


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "x", "frequency": "hourly"},
        {"title": "x", "frequency": "weekly"},  # needs days
        {"title": "x", "frequency": "weekly", "days_of_week": [7]},
        {"title": "x", "frequency": "monthly"},  # needs a day
        {"title": "x", "frequency": "monthly", "day_of_month": 32},
        {"title": "x", "frequency": "daily", "start_date": "2000-01-01"},  # in the past
    ],
)
def test_recurring_validation(c, payload):
    assert c.post("/api/recurring-tasks", json=payload).status_code == 422
