"""HTTP-level tests for the video endpoints: auth, validation, serialisation, status codes, isolation."""
import pytest

SETUP = {"email": "me@example.com", "password": "correct-horse-9", "display_name": "Me", "timezone": "Asia/Kolkata"}


@pytest.fixture
def c(client):
    assert client.post("/api/auth/setup", json=SETUP).status_code == 201
    return client


def new_playlist(c, **kw) -> dict:
    r = c.post("/api/video-playlists", json={"name": "ByteByteGo", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def add(c, pid, title, **kw) -> dict:
    r = c.post(f"/api/video-playlists/{pid}/videos", json={"title": title, **kw})
    assert r.status_code == 201, r.text
    return r.json()


PROTECTED = [
    ("get", "/api/video-playlists"), ("post", "/api/video-playlists"), ("get", "/api/video-playlists/1"),
    ("patch", "/api/video-playlists/1"), ("delete", "/api/video-playlists/1"),
    ("get", "/api/video-playlists/1/today"), ("get", "/api/video-playlists/1/videos"),
    ("post", "/api/video-playlists/1/videos"), ("post", "/api/video-playlists/1/bulk-videos"),
    ("get", "/api/videos/next"), ("patch", "/api/videos/1"), ("delete", "/api/videos/1"),
    ("post", "/api/videos/1/start"), ("post", "/api/videos/1/complete"), ("post", "/api/videos/1/uncomplete"),
    ("post", "/api/videos/1/move"),
]


@pytest.mark.parametrize("method, path", PROTECTED)
def test_every_endpoint_requires_login(client, method, path):
    assert getattr(client, method)(path).status_code == 401


# ---------------- playlists ----------------


def test_playlist_round_trip_and_shape(c):
    p = new_playlist(c, source_url="https://www.youtube.com/@ByteByteGo", daily_target=2)
    assert p["name"] == "ByteByteGo" and p["daily_target"] == 2 and p["active"] is True
    assert (p["total_videos"], p["completed_videos"], p["percent"]) == (0, 0, 0)
    assert p["next_video"] is None and p["watched_today"] == 0 and p["remaining_today"] == 2

    assert c.get(f"/api/video-playlists/{p['id']}").json()["name"] == "ByteByteGo"
    r = c.patch(f"/api/video-playlists/{p['id']}", json={"name": "BBG", "daily_target": 3, "active": False})
    assert r.status_code == 200 and r.json()["name"] == "BBG" and r.json()["daily_target"] == 3 and not r.json()["active"]
    assert [x["name"] for x in c.get("/api/video-playlists").json()] == ["BBG"]
    assert c.delete(f"/api/video-playlists/{p['id']}").status_code == 204
    assert c.get(f"/api/video-playlists/{p['id']}").status_code == 404
    assert c.get("/api/video-playlists").json() == []


@pytest.mark.parametrize("body", [
    {}, {"name": ""}, {"name": "x" * 121}, {"name": "A", "daily_target": 0}, {"name": "A", "daily_target": 51},
    {"name": "A", "source_url": "javascript:alert(1)"}, {"name": "A", "source_url": "data:text/html,x"},
    {"name": "A", "unknown": 1},
])
def test_playlist_validation(c, body):
    assert c.post("/api/video-playlists", json=body).status_code == 422


def test_duplicate_playlist_name_is_409(c):
    new_playlist(c)
    assert c.post("/api/video-playlists", json={"name": "bytebytego"}).status_code == 409
    other = c.post("/api/video-playlists", json={"name": "Other"}).json()
    assert c.patch(f"/api/video-playlists/{other['id']}", json={"name": "ByteByteGo"}).status_code == 409


def test_patch_null_required_field_is_422(c):
    p = new_playlist(c)
    for f in ("name", "daily_target", "active"):
        assert c.patch(f"/api/video-playlists/{p['id']}", json={f: None}).status_code == 422


# ---------------- videos ----------------


def test_video_round_trip_and_shape(c):
    p = new_playlist(c)
    v = add(c, p["id"], "How DNS works", url="https://youtu.be/dQw4w9WgXcQ", category="Networking",
            description="d", notes="n")
    assert v["status"] == "unwatched" and v["completed_at"] is None and v["position"] == 1
    assert v["youtube_video_id"] == "dQw4w9WgXcQ" and v["playlist_id"] == p["id"]
    r = c.patch(f"/api/videos/{v['id']}", json={"title": "DNS", "notes": None})
    assert r.status_code == 200 and r.json()["title"] == "DNS" and r.json()["notes"] is None
    assert c.delete(f"/api/videos/{v['id']}").status_code == 204
    assert c.delete(f"/api/videos/{v['id']}").status_code == 404


@pytest.mark.parametrize("body", [
    {}, {"title": ""}, {"title": "x" * 301}, {"title": "A", "url": "javascript:alert(1)"},
    {"title": "A", "url": "notaurl"}, {"title": "A", "status": "completed"},  # status cannot be set directly
    {"title": "A", "completed_at": "2026-01-01T00:00:00Z"},
])
def test_video_validation(c, body):
    p = new_playlist(c)
    assert c.post(f"/api/video-playlists/{p['id']}/videos", json=body).status_code == 422


def test_duplicate_youtube_video_is_409(c):
    p = new_playlist(c)
    add(c, p["id"], "A", url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    r = c.post(f"/api/video-playlists/{p['id']}/videos", json={"title": "B", "url": "https://youtu.be/dQw4w9WgXcQ"})
    assert r.status_code == 409


def test_bulk_paste(c):
    p = new_playlist(c)
    lines = ["How DNS works | https://youtu.be/aaaaaaaaaaa", "https://youtu.be/aaaaaaaaaaa", "nope"]
    r = c.post(f"/api/video-playlists/{p['id']}/bulk-videos", json={"lines": lines, "category": "Sys"})
    assert r.status_code == 201 and r.json() == {"added": 1, "duplicates": 1, "invalid": ["nope"]}
    items = c.get(f"/api/video-playlists/{p['id']}/videos").json()["items"]
    assert [i["title"] for i in items] == ["How DNS works"] and items[0]["category"] == "Sys"
    assert c.post(f"/api/video-playlists/{p['id']}/bulk-videos", json={"lines": []}).status_code == 422


# ---------------- completion + recommendation, end to end over HTTP ----------------


def test_completed_video_is_never_recommended_over_http(c):
    p = new_playlist(c)
    a, b, d = (add(c, p["id"], t) for t in ("A", "B", "D"))
    assert c.get(f"/api/video-playlists/{p['id']}").json()["next_video"]["id"] == a["id"]
    assert c.get("/api/videos/next").json()["id"] == a["id"]

    done = c.post(f"/api/videos/{a['id']}/complete").json()
    assert done["status"] == "completed" and done["completed_at"]
    summary = c.get(f"/api/video-playlists/{p['id']}").json()
    assert summary["next_video"]["id"] == b["id"]
    assert (summary["completed_videos"], summary["percent"], summary["watched_today"]) == (1, 33, 1)
    assert c.get("/api/videos/next").json()["id"] == b["id"]
    assert all(v["id"] != a["id"] for v in c.get(f"/api/video-playlists/{p['id']}/today").json()["up_next"])
    assert [v["id"] for v in c.get(f"/api/video-playlists/{p['id']}/videos?view=open").json()["items"]] == [b["id"], d["id"]]

    # reopening is the only way back into the recommendations
    assert c.post(f"/api/videos/{a['id']}/uncomplete").json()["status"] == "unwatched"
    assert c.get("/api/videos/next").json()["id"] == a["id"]


def test_all_completed_means_no_next_video(c):
    p = new_playlist(c)
    v = add(c, p["id"], "A")
    c.post(f"/api/videos/{v['id']}/complete")
    assert c.get("/api/videos/next").json() is None
    assert c.get(f"/api/video-playlists/{p['id']}").json()["next_video"] is None


def test_complete_is_idempotent_over_http(c):
    p = new_playlist(c)
    v = add(c, p["id"], "A")
    first = c.post(f"/api/videos/{v['id']}/complete").json()["completed_at"]
    assert c.post(f"/api/videos/{v['id']}/complete").json()["completed_at"] == first


def test_start_then_cannot_start_completed(c):
    p = new_playlist(c)
    v = add(c, p["id"], "A")
    assert c.post(f"/api/videos/{v['id']}/start").json()["status"] == "watching"
    c.post(f"/api/videos/{v['id']}/complete")
    assert c.post(f"/api/videos/{v['id']}/start").status_code == 422


def test_today_endpoint(c):
    p = new_playlist(c, daily_target=2)
    vids = [add(c, p["id"], t) for t in ("A", "B", "D")]
    c.post(f"/api/videos/{vids[0]['id']}/complete")
    t = c.get(f"/api/video-playlists/{p['id']}/today").json()
    assert (t["daily_target"], t["watched_today"], t["remaining_today"], t["target_met"]) == (2, 1, 1, False)
    assert [v["id"] for v in t["up_next"]] == [vids[1]["id"]]
    c.post(f"/api/videos/{vids[1]['id']}/complete")
    t = c.get(f"/api/video-playlists/{p['id']}/today").json()
    assert t["target_met"] is True and t["up_next"] == []


def test_list_filters_and_validation(c):
    p = new_playlist(c)
    a, b = add(c, p["id"], "Alpha"), add(c, p["id"], "Beta")
    c.post(f"/api/videos/{a['id']}/complete")
    base = f"/api/video-playlists/{p['id']}/videos"
    assert c.get(base).json()["total"] == 2
    assert [v["title"] for v in c.get(base + "?view=completed").json()["items"]] == ["Alpha"]
    assert [v["title"] for v in c.get(base + "?q=bet").json()["items"]] == ["Beta"]
    assert c.get(base + "?view=bogus").status_code == 422
    assert c.get(base + "?limit=0").status_code == 422
    assert c.get(base + "?offset=-1").status_code == 422


def test_move_endpoint(c):
    p = new_playlist(c)
    a, b = add(c, p["id"], "A"), add(c, p["id"], "B")
    assert c.post(f"/api/videos/{b['id']}/move", json={"direction": "up"}).status_code == 200
    items = c.get(f"/api/video-playlists/{p['id']}/videos").json()["items"]
    assert [i["title"] for i in items] == ["B", "A"]
    assert c.post(f"/api/videos/{b['id']}/move", json={"direction": "sideways"}).status_code == 422


def test_deleting_a_playlist_deletes_its_videos(c):
    p = new_playlist(c)
    v = add(c, p["id"], "A")
    c.delete(f"/api/video-playlists/{p['id']}")
    assert c.post(f"/api/videos/{v['id']}/complete").status_code == 404


# ---------------- isolation between users ----------------


def test_another_users_playlist_and_videos_look_like_not_found(c, db):
    from app.models import User, Video, VideoPlaylist
    db.add(User(id=2, email="o@example.com", password_hash="x", display_name="O", timezone="UTC"))
    db.commit()
    db.add(VideoPlaylist(id=50, user_id=2, name="Theirs"))
    db.commit()
    db.add(Video(id=60, user_id=2, playlist_id=50, title="Secret", position=1))
    db.commit()
    assert c.get("/api/video-playlists").json() == []
    assert c.get("/api/video-playlists/50").status_code == 404
    assert c.patch("/api/video-playlists/50", json={"name": "x"}).status_code == 404
    assert c.delete("/api/video-playlists/50").status_code == 404
    assert c.get("/api/video-playlists/50/videos").status_code == 404
    assert c.post("/api/video-playlists/50/videos", json={"title": "x"}).status_code == 404
    assert c.post("/api/videos/60/complete").status_code == 404
    assert c.patch("/api/videos/60", json={"title": "x"}).status_code == 404
    assert c.delete("/api/videos/60").status_code == 404
    assert c.get("/api/videos/next").json() is None


def test_logout_locks_the_video_api(c):
    p = new_playlist(c)
    assert c.post("/api/auth/logout").status_code in (200, 204)
    assert c.get(f"/api/video-playlists/{p['id']}").status_code == 401
