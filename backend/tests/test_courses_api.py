"""HTTP-level tests for the course endpoints: auth, validation, serialisation, status codes."""
import pytest

from app.models import Course, CourseLesson, CourseModule, User

SETUP = {"email": "me@example.com", "password": "correct-horse-9", "display_name": "Me", "timezone": "Asia/Kolkata"}


@pytest.fixture
def c(client):
    assert client.post("/api/auth/setup", json=SETUP).status_code == 201
    return client


def new_course(c, **kw) -> dict:
    r = c.post("/api/courses", json={"title": "Agents 101", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def course_with_lessons(c, titles=("Intro", "Reflection", "Tools")) -> dict:
    course = new_course(c)
    mod = c.post(f"/api/courses/{course['id']}/modules", json={"title": "Module 1"}).json()["modules"][0]
    r = c.post(f"/api/courses/{course['id']}/bulk-lessons", json={"module_id": mod["id"], "titles": list(titles)})
    assert r.status_code == 201, r.text
    return r.json()


# ---------------- authentication ----------------

PROTECTED = [
    ("get", "/api/courses"), ("post", "/api/courses"), ("get", "/api/courses/1"), ("patch", "/api/courses/1"),
    ("delete", "/api/courses/1"), ("get", "/api/courses/1/next"), ("post", "/api/courses/1/modules"),
    ("post", "/api/courses/1/bulk-lessons"), ("patch", "/api/modules/1"), ("delete", "/api/modules/1"),
    ("post", "/api/modules/1/move"), ("post", "/api/modules/1/lessons"), ("patch", "/api/lessons/1"),
    ("delete", "/api/lessons/1"), ("post", "/api/lessons/1/move"), ("post", "/api/lessons/1/start"),
    ("post", "/api/lessons/1/complete"), ("post", "/api/lessons/1/uncomplete"), ("get", "/api/learning-sessions"),
    ("post", "/api/learning-sessions"), ("delete", "/api/learning-sessions/1"), ("get", "/api/course-templates"),
    ("post", "/api/course-templates/deeplearning-agentic-ai"),
]


@pytest.mark.parametrize("method, path", PROTECTED)
def test_every_endpoint_requires_login(client, method, path):
    assert getattr(client, method)(path).status_code == 401


# ---------------- courses ----------------


def test_course_round_trip_and_shape(c):
    created = new_course(c, provider="DeepLearning.AI", url="https://example.com/c", priority=1)
    assert created["status"] == "active" and created["progress"]["total_lessons"] == 0
    assert created["next_lesson"] is None and created["modules"] == [] and created["minutes_studied"] == 0
    cid = created["id"]

    got = c.get(f"/api/courses/{cid}").json()
    assert got["title"] == "Agents 101" and got["provider"] == "DeepLearning.AI"
    r = c.patch(f"/api/courses/{cid}", json={"title": "Agents 102", "status": "paused"})
    assert r.status_code == 200 and r.json()["title"] == "Agents 102" and r.json()["status"] == "paused"
    assert c.delete(f"/api/courses/{cid}").status_code == 204
    assert c.get(f"/api/courses/{cid}").status_code == 404


def test_lesson_flow_updates_progress_next_and_course_status(c):
    course = course_with_lessons(c)
    ids = [le["id"] for le in course["modules"][0]["lessons"]]
    assert course["progress"]["percent"] == 0 and course["next_lesson"]["title"] == "Intro"

    r = c.post(f"/api/lessons/{ids[0]}/complete").json()
    assert r["progress"]["completed_lessons"] == 1 and r["progress"]["percent"] == 33
    assert r["next_lesson"]["title"] == "Reflection" and r["started_at"] is not None
    assert r["modules"][0]["completed_lessons"] == 1
    done = r["modules"][0]["lessons"][0]
    assert done["status"] == "completed" and done["completed_at"]

    for lid in ids[1:]:
        r = c.post(f"/api/lessons/{lid}/complete").json()
    assert r["status"] == "completed" and r["completed_at"] and r["next_lesson"] is None and r["progress"]["percent"] == 100

    r = c.post(f"/api/lessons/{ids[2]}/uncomplete").json()
    assert r["status"] == "active" and r["completed_at"] is None and r["next_lesson"]["title"] == "Tools"
    assert c.get(f"/api/courses/{course['id']}/next").json()["id"] == ids[2]


def test_start_then_complete_a_lesson(c):
    course = course_with_lessons(c)
    lid = course["modules"][0]["lessons"][0]["id"]
    r = c.post(f"/api/lessons/{lid}/start").json()
    assert r["modules"][0]["lessons"][0]["status"] == "in_progress" and r["next_lesson"]["status"] == "in_progress"
    c.post(f"/api/lessons/{lid}/complete")
    assert c.post(f"/api/lessons/{lid}/start").status_code == 422  # can't restart a completed lesson


def test_list_filter_and_next_is_null_for_a_course_without_lessons(c):
    a = new_course(c, title="Alpha")
    new_course(c, title="Beta")
    c.patch(f"/api/courses/{a['id']}", json={"status": "archived"})
    assert [x["title"] for x in c.get("/api/courses").json()] == ["Alpha", "Beta"]  # same priority → by title
    assert [x["title"] for x in c.get("/api/courses", params={"status": "archived"}).json()] == ["Alpha"]
    assert c.get(f"/api/courses/{a['id']}/next").json() is None
    assert c.get("/api/courses", params={"status": "bogus"}).status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {}, {"title": ""}, {"title": "   "}, {"title": "x" * 201}, {"title": "ok", "priority": 0}, {"title": "ok", "priority": 5},
        {"title": "ok", "kind": "podcast"}, {"title": "ok", "target_date": "soon"}, {"title": "ok", "status": "completed"},
        {"title": "ok", "user_id": 3}, {"title": "ok", "progress": {"percent": 100}},
        {"title": "ok", "url": "javascript:alert(1)"}, {"title": "ok", "url": "data:text/html,<script>1</script>"},
        {"title": "ok", "url": "ftp://example.com/x"}, {"title": "ok", "url": "example.com/no-scheme"}, {"title": "ok", "url": "https://"},
    ],
)
def test_create_course_validation(c, payload):
    assert c.post("/api/courses", json=payload).status_code == 422


def test_only_http_links_are_accepted_and_blank_means_none(c):
    ok = new_course(c, url="http://example.com/a?b=1#c")
    assert ok["url"] == "http://example.com/a?b=1#c"
    blank = new_course(c, url="   ", provider="")
    assert blank["url"] is None and blank["provider"] is None
    assert c.patch(f"/api/courses/{ok['id']}", json={"url": "javascript:alert(1)"}).status_code == 422
    assert c.patch(f"/api/courses/{ok['id']}", json={"url": None}).json()["url"] is None


def test_manual_completion_rules_over_http(c):
    book = new_course(c, title="Book")
    assert c.patch(f"/api/courses/{book['id']}", json={"status": "completed"}).json()["status"] == "completed"
    course = course_with_lessons(c)
    r = c.patch(f"/api/courses/{course['id']}", json={"status": "completed"})
    assert r.status_code == 422 and "automatically" in r.json()["detail"]
    assert c.patch(f"/api/courses/{course['id']}", json={"title": None}).status_code == 422


# ---------------- modules & lessons ----------------


def test_module_and_lesson_crud_move_and_validation(c):
    course = new_course(c)
    cid = course["id"]
    for title in ("A", "B"):
        course = c.post(f"/api/courses/{cid}/modules", json={"title": title}).json()
    a, b = course["modules"]
    assert c.post(f"/api/courses/{cid}/modules", json={"title": ""}).status_code == 422

    moved = c.post(f"/api/modules/{b['id']}/move", json={"direction": "up"}).json()
    assert [m["title"] for m in moved["modules"]] == ["B", "A"]
    assert c.post(f"/api/modules/{b['id']}/move", json={"direction": "sideways"}).status_code == 422
    assert c.patch(f"/api/modules/{a['id']}", json={"title": "A2"}).json()["modules"][1]["title"] == "A2"

    r = c.post(f"/api/modules/{a['id']}/lessons", json={"title": "L1", "url": "https://x.example/l1", "duration_minutes": 12, "lesson_type": "video"})
    assert r.status_code == 201
    lesson = r.json()["modules"][1]["lessons"][0]
    assert lesson["duration_minutes"] == 12 and lesson["lesson_type"] == "video" and lesson["course_id"] == cid
    assert r.json()["progress"]["total_minutes"] == 12

    for bad in ({"title": ""}, {"title": "x", "duration_minutes": 0}, {"title": "x", "duration_minutes": 5000},
                {"title": "x", "lesson_type": "quiz"}, {"title": "x", "url": "javascript:1"}, {"title": "x", "course_id": 9}):
        assert c.post(f"/api/modules/{a['id']}/lessons", json=bad).status_code == 422

    r = c.patch(f"/api/lessons/{lesson['id']}", json={"module_id": b["id"], "notes": "hi"}).json()
    assert [m["total_lessons"] for m in r["modules"]] == [1, 0]
    assert c.patch(f"/api/lessons/{lesson['id']}", json={"title": None}).status_code == 422
    after = c.delete(f"/api/lessons/{lesson['id']}").json()
    assert after["progress"]["total_lessons"] == 0
    assert c.delete(f"/api/modules/{a['id']}").json()["modules"][0]["title"] == "B"


def test_bulk_lessons_validation(c):
    course = course_with_lessons(c, titles=("x",))
    mid = course["modules"][0]["id"]
    cid = course["id"]
    assert c.post(f"/api/courses/{cid}/bulk-lessons", json={"module_id": mid, "titles": []}).status_code == 422
    assert c.post(f"/api/courses/{cid}/bulk-lessons", json={"module_id": mid, "titles": ["ok", ""]}).status_code == 422
    assert c.post(f"/api/courses/{cid}/bulk-lessons", json={"module_id": mid, "titles": ["t"] * 201}).status_code == 422
    assert c.post(f"/api/courses/{cid}/bulk-lessons", json={"module_id": 9999, "titles": ["t"]}).status_code == 404
    other = new_course(c, title="Other")
    assert c.post(f"/api/courses/{other['id']}/bulk-lessons", json={"module_id": mid, "titles": ["t"]}).status_code == 422


# ---------------- isolation between users ----------------


def test_other_users_data_is_invisible_over_http(c, db):
    db.add(User(id=2, email="o@example.com", password_hash="x", display_name="O", timezone="UTC"))
    db.commit()
    theirs = Course(user_id=2, title="secret")
    db.add(theirs)
    db.commit()
    m = CourseModule(course_id=theirs.id, title="m", position=1)
    db.add(m)
    db.commit()
    le = CourseLesson(module_id=m.id, course_id=theirs.id, title="l", position=1)
    db.add(le)
    db.commit()

    assert c.get("/api/courses").json() == []
    for method, path, body in [
        ("get", f"/api/courses/{theirs.id}", None), ("patch", f"/api/courses/{theirs.id}", {"title": "x"}),
        ("delete", f"/api/courses/{theirs.id}", None), ("get", f"/api/courses/{theirs.id}/next", None),
        ("post", f"/api/courses/{theirs.id}/modules", {"title": "x"}), ("patch", f"/api/modules/{m.id}", {"title": "x"}),
        ("delete", f"/api/modules/{m.id}", None), ("post", f"/api/modules/{m.id}/lessons", {"title": "x"}),
        ("post", f"/api/lessons/{le.id}/complete", None), ("post", f"/api/lessons/{le.id}/start", None),
        ("delete", f"/api/lessons/{le.id}", None),
        ("post", "/api/learning-sessions", {"course_id": theirs.id, "minutes": 5}),
    ]:
        kw = {"json": body} if body is not None else {}
        assert getattr(c, method)(path, **kw).status_code == 404, f"{method} {path}"
    db.refresh(le)
    assert le.status == "not_started"


def test_signing_out_locks_the_course_api(c):
    new_course(c)
    assert c.post("/api/auth/logout").status_code == 204
    assert c.get("/api/courses").status_code == 401


# ---------------- study sessions ----------------


def test_study_session_endpoints(c):
    course = course_with_lessons(c)
    lid = course["modules"][0]["lessons"][0]["id"]
    r = c.post("/api/learning-sessions", json={"course_id": course["id"], "lesson_id": lid, "minutes": 40, "notes": "focused"})
    assert r.status_code == 201 and r.json()["minutes"] == 40 and r.json()["lesson_id"] == lid
    sid = r.json()["id"]
    assert c.get(f"/api/courses/{course['id']}").json()["minutes_studied"] == 40
    assert [x["id"] for x in c.get("/api/learning-sessions", params={"course_id": course["id"]}).json()] == [sid]

    for bad in ({"course_id": course["id"], "minutes": 0}, {"course_id": course["id"], "minutes": 2000},
                {"course_id": course["id"], "minutes": 5, "date": "2099-01-01"}, {"minutes": 5},
                {"course_id": course["id"], "minutes": 5, "date": "yesterday"}):
        assert c.post("/api/learning-sessions", json=bad).status_code == 422
    assert c.post("/api/learning-sessions", json={"course_id": 9999, "minutes": 5}).status_code == 404
    assert c.delete(f"/api/learning-sessions/{sid}").status_code == 204
    assert c.delete(f"/api/learning-sessions/{sid}").status_code == 404
    assert c.get("/api/learning-sessions", params={"limit": 0}).status_code == 422


# ---------------- templates ----------------


def test_template_endpoints_seed_structure_only_and_refuse_duplicates(c):
    listed = c.get("/api/course-templates").json()
    assert listed[0]["key"] == "deeplearning-agentic-ai" and listed[0]["already_added"] is False and len(listed[0]["modules"]) == 5

    r = c.post("/api/course-templates/deeplearning-agentic-ai")
    assert r.status_code == 201
    course = r.json()
    assert course["provider"] == "DeepLearning.AI" and len(course["modules"]) == 5
    assert course["progress"] == {"total_lessons": 0, "completed_lessons": 0, "percent": 0, "total_minutes": 0, "remaining_minutes": 0}
    assert course["status"] == "active" and course["completed_at"] is None and course["next_lesson"] is None

    assert c.post("/api/course-templates/deeplearning-agentic-ai").status_code == 409
    assert c.post("/api/course-templates/nope").status_code == 404
    assert c.get("/api/course-templates").json()[0]["already_added"] is True
    assert len(c.get("/api/courses").json()) == 1


def test_fixed_paths_are_not_swallowed_by_id_routes(c):
    assert c.get("/api/courses/abc").status_code == 422
    assert c.get("/api/course-templates").status_code == 200
