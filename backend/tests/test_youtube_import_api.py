"""Preview + selective import over HTTP, with a fake YouTube. Covers: nothing saved by a preview, only ticked videos
saved, library-wide de-duplication, channel/playlist associations, honest counts, and every failure path."""
import pytest

from app.main import app
from app.routers.youtube import get_client
from app.services import youtube as yt
from tests.fake_youtube import CHANNEL_ID, FakeYouTube, vid

SETUP = {"email": "me@example.com", "password": "correct-horse-9", "display_name": "Me", "timezone": "Asia/Kolkata"}
CHANNEL = "https://www.youtube.com/@fakechannel"
PL = "PL" + "p" * 10
PLAYLIST = f"https://www.youtube.com/playlist?list={PL}"


@pytest.fixture
def fake():
    return FakeYouTube()


@pytest.fixture
def c(client, fake):
    assert client.post("/api/auth/setup", json=SETUP).status_code == 201

    def override():
        cl = fake.client()
        try:
            yield cl
        finally:
            cl.close()

    app.dependency_overrides[get_client] = override
    yield client
    app.dependency_overrides.pop(get_client, None)


def preview(c, url=CHANNEL, limit=10):
    r = c.post("/api/youtube/preview", json={"url": url, "limit": limit})
    assert r.status_code == 200, r.text
    return r.json()


def do_import(c, ids, url=CHANNEL, retrieved=0):
    r = c.post("/api/youtube/import", json={"url": url, "video_ids": ids, "retrieved": retrieved})
    assert r.status_code == 201, r.text
    return r.json()


def library(c, **params):
    return c.get("/api/videos", params={"limit": 500, **params}).json()


# ---------------- auth ----------------


@pytest.mark.parametrize("method, path", [("get", "/api/youtube/status"), ("post", "/api/youtube/preview"), ("post", "/api/youtube/import")])
def test_youtube_endpoints_require_login(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_signed_out_callers_learn_nothing_about_server_configuration(client):
    assert client.post("/api/youtube/preview", json={"url": CHANNEL}).status_code == 401  # not 503 "not configured"


# ---------------- configuration ----------------


def test_status_reports_configured_without_revealing_the_key(c, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "youtube_api_key", "super-secret-key-value")
    r = c.get("/api/youtube/status")
    assert r.json() == {"configured": True} and "super-secret" not in r.text
    monkeypatch.setattr(get_settings(), "youtube_api_key", None)
    assert c.get("/api/youtube/status").json() == {"configured": False}


def test_without_a_key_preview_explains_how_to_set_one_up(client, monkeypatch):
    from app.config import get_settings

    client.post("/api/auth/setup", json=SETUP)
    monkeypatch.setattr(get_settings(), "youtube_api_key", None)
    r = client.post("/api/youtube/preview", json={"url": CHANNEL})
    assert r.status_code == 503 and "YOUTUBE_API_KEY" in r.json()["detail"]


# ---------------- preview ----------------


def test_preview_shows_source_totals_and_videos_but_saves_nothing(c):
    p = preview(c, limit=10)
    assert p["source"]["kind"] == "channel" and p["source"]["title"] == "Fake Channel" and p["source"]["id"] == CHANNEL_ID
    assert p["source"]["total_available"] == 120 and p["source"]["thumbnail_url"]
    assert p["retrieved"] == 10 == len(p["videos"]) and p["more_available"] is True and p["unavailable"] == 0
    first = p["videos"][0]
    assert first["youtube_video_id"] == vid(120) and first["thumbnail_url"] and first["title"] and first["duration_seconds"]
    assert first["in_library"] is False and first["status"] is None
    assert library(c) == {"items": [], "total": 0}                       # NOTHING imported by previewing
    assert c.get("/api/video-playlists").json() == []                    # ...and no collection created either


def test_distinguishes_total_available_retrieved_and_imported(c):
    p = preview(c, limit=25)
    assert (p["source"]["total_available"], p["retrieved"]) == (120, 25)
    out = do_import(c, [v["youtube_video_id"] for v in p["videos"][:5]], retrieved=p["retrieved"])
    col = out["collection"]
    assert (col["reported_total"], col["retrieved_count"], col["total_videos"]) == (120, 25, 5)


@pytest.mark.parametrize("limit, n", [(10, 10), (25, 25), (50, 50), (100, 100), (7, 7), (None, 120)])
def test_retrieval_options_and_custom_limits(c, limit, n):
    assert preview(c, limit=limit)["retrieved"] == n


def test_all_option_pages_through_the_whole_channel(c, fake):
    p = preview(c, limit=None)
    assert p["retrieved"] == 120 and p["more_available"] is False and len(fake.calls("playlistItems")) == 3


def test_unreported_total_is_null_not_an_estimate(c, fake):
    fake.channel_video_count = None
    p = preview(c, limit=5)
    assert p["source"]["total_available"] is None and p["retrieved"] == 5
    out = do_import(c, [p["videos"][0]["youtube_video_id"]], retrieved=5)
    assert out["collection"]["reported_total"] is None


@pytest.mark.parametrize("limit", [0, -1, 2001, "ten", 1.5])
def test_invalid_limits_are_rejected(c, limit):
    assert c.post("/api/youtube/preview", json={"url": CHANNEL, "limit": limit}).status_code == 422


def test_preview_flags_videos_already_in_the_library(c):
    ids = [v["youtube_video_id"] for v in preview(c)["videos"]]
    do_import(c, ids[:3])
    again = preview(c)
    assert [v["in_library"] for v in again["videos"][:4]] == [True, True, True, False]
    assert again["already_in_library"] == 3


def test_preview_flags_removed_videos_and_shows_status(c):
    ids = [v["youtube_video_id"] for v in preview(c)["videos"]]
    do_import(c, ids[:2])
    items = library(c)["items"]
    c.post(f"/api/videos/{items[0]['id']}/complete")
    c.post(f"/api/videos/{items[1]['id']}/remove")
    flags = {v["youtube_video_id"]: v for v in preview(c)["videos"][:2]}
    done, gone = items[0]["youtube_video_id"], items[1]["youtube_video_id"]
    assert flags[done]["in_library"] and flags[done]["status"] == "completed"
    assert flags[gone]["removed"] and not flags[gone]["in_library"]


def test_playlist_preview(c):
    p = preview(c, url=PLAYLIST, limit=None)
    assert p["source"]["kind"] == "playlist" and p["source"]["total_available"] == 4 and p["source"]["title"] == "Fake playlist"
    assert [v["youtube_video_id"] for v in p["videos"]] == [vid(n) for n in (5, 3, 9, 1)]


def test_private_unavailable_videos_are_reported_separately(c, fake):
    fake.hidden = {120, 119}
    p = preview(c, limit=10)
    assert p["retrieved"] == 10 and p["unavailable"] == 2
    assert vid(120) not in {v["youtube_video_id"] for v in p["videos"]}


# ---------------- import ----------------


def test_only_the_selected_videos_are_imported(c):
    p = preview(c, limit=10)
    chosen = [p["videos"][i]["youtube_video_id"] for i in (0, 4, 9)]
    out = do_import(c, chosen, retrieved=10)
    assert (out["created"], out["linked"], out["already_in_collection"], out["unavailable"]) == (3, 0, 0, 0)
    items = library(c)["items"]
    assert sorted(i["youtube_video_id"] for i in items) == sorted(chosen) and library(c)["total"] == 3
    assert all(i["status"] == "unwatched" and i["completed_at"] is None for i in items)  # never auto-completed


def test_imported_video_carries_full_metadata_and_associations(c):
    ids = [preview(c)["videos"][0]["youtube_video_id"]]
    out = do_import(c, ids)
    col = out["collection"]
    v = library(c)["items"][0]
    assert v["title"] == "Video number 120" and v["description"] == "About 120" and v["url"].endswith(ids[0])
    assert v["thumbnail_url"].endswith("mqdefault.jpg") and v["duration_seconds"] and v["published_at"]
    assert v["channel_id"] == CHANNEL_ID and v["channel_title"] == "Fake Channel" and v["created_at"]
    assert v["playlist_ids"] == [col["id"]]
    assert (col["kind"], col["youtube_channel_id"], col["name"]) == ("channel", CHANNEL_ID, "Fake Channel")
    assert col["source_url"].endswith(CHANNEL_ID) and col["thumbnail_url"] and col["recommend_order"] == "oldest"


def test_importing_twice_never_duplicates(c):
    ids = [v["youtube_video_id"] for v in preview(c)["videos"][:4]]
    first = do_import(c, ids)
    second = do_import(c, ids)
    assert (second["created"], second["already_in_collection"]) == (0, 4)
    assert first["collection"]["id"] == second["collection"]["id"]            # same collection reused
    assert library(c)["total"] == 4 and len(c.get("/api/video-playlists").json()) == 1


def test_repeated_ids_in_one_request_are_imported_once(c):
    i = preview(c)["videos"][0]["youtube_video_id"]
    out = do_import(c, [i, i, i])
    assert out["created"] == 1 and library(c)["total"] == 1


def test_same_video_from_channel_and_playlist_is_one_library_row_with_two_associations(c, fake):
    fake.playlists[PL]["items"] = [120, 119]
    fake.playlists[PL]["count"] = 2
    ch = do_import(c, [vid(120), vid(119), vid(118)])["collection"]
    pl = do_import(c, [vid(120), vid(119)], url=PLAYLIST)
    assert (pl["created"], pl["linked"]) == (0, 2)                              # linked, not duplicated
    assert library(c)["total"] == 3
    v = next(i for i in library(c)["items"] if i["youtube_video_id"] == vid(120))
    assert sorted(v["playlist_ids"]) == sorted([ch["id"], pl["collection"]["id"]]) and pl["collection"]["kind"] == "playlist"
    # completing it once shows up in BOTH collections' progress
    c.post(f"/api/videos/{v['id']}/complete")
    cols = {p["id"]: p for p in c.get("/api/video-playlists").json()}
    assert cols[ch["id"]]["completed_videos"] == 1 and cols[pl["collection"]["id"]]["completed_videos"] == 1
    assert c.get("/api/videos/stats").json()["total"] == 3


def test_playlist_import_stores_the_playlist_association(c):
    out = do_import(c, [vid(5), vid(3)], url=PLAYLIST, retrieved=4)
    col = out["collection"]
    assert (col["kind"], col["youtube_playlist_id"], col["name"], col["reported_total"], col["retrieved_count"]) == (
        "playlist", PL, "Fake playlist", 4, 4)


def test_a_hand_made_playlist_with_the_same_name_is_adopted_not_duplicated(c):
    mine = c.post("/api/video-playlists", json={"name": "fake channel", "daily_target": 3, "recommend_order": "manual"}).json()
    c.post(f"/api/video-playlists/{mine['id']}/videos", json={"title": "My own video"})
    col = do_import(c, [vid(1), vid(2)])["collection"]
    assert col["id"] == mine["id"] and (col["kind"], col["recommend_order"], col["daily_target"]) == ("channel", "oldest", 3)
    assert col["total_videos"] == 3 and col["youtube_channel_id"] == CHANNEL_ID   # its own video is kept
    assert len(c.get("/api/video-playlists").json()) == 1


def test_a_playlist_with_a_clashing_name_but_another_kind_gets_a_suffix(c):
    do_import(c, [vid(1)])                                          # the channel collection "Fake Channel"
    fake_pl = FakeYouTube()
    fake_pl.playlists[PL]["title"] = "Fake Channel"                 # a YouTube playlist that happens to share the name
    app.dependency_overrides[get_client] = lambda: fake_pl.client()
    out = do_import(c, [vid(5)], url=PLAYLIST)
    assert out["collection"]["name"] == "Fake Channel (YouTube)" and out["collection"]["kind"] == "playlist"


def test_removed_video_is_restored_when_imported_again(c):
    do_import(c, [vid(7)])
    vid_row = library(c)["items"][0]
    c.post(f"/api/videos/{vid_row['id']}/remove")
    assert library(c)["total"] == 0
    out = do_import(c, [vid(7)])
    assert (out["created"], out["linked"]) == (0, 1)
    assert library(c)["items"][0]["id"] == vid_row["id"] and library(c)["total"] == 1


def test_unavailable_selection_is_reported_and_skipped(c, fake):
    fake.hidden = {5}
    out = do_import(c, [vid(5), vid(6)])
    assert (out["created"], out["unavailable"]) == (1, 1)


def test_importing_only_unavailable_videos_is_a_clear_error(c, fake):
    fake.hidden = {5}
    r = c.post("/api/youtube/import", json={"url": CHANNEL, "video_ids": [vid(5)]})
    assert r.status_code == 404 and library(c)["total"] == 0 and c.get("/api/video-playlists").json() == []


@pytest.mark.parametrize("body", [
    {"url": CHANNEL, "video_ids": []}, {"url": CHANNEL}, {"video_ids": ["v0000000001"]},
    {"url": CHANNEL, "video_ids": ["short"]}, {"url": CHANNEL, "video_ids": ["bad id!!!!!!"]},
    {"url": CHANNEL, "video_ids": ["v0000000001"] * 2001}, {"url": CHANNEL, "video_ids": ["v0000000001"], "retrieved": -1},
    {"url": CHANNEL, "video_ids": ["v0000000001"], "extra": 1},
])
def test_import_validation(c, body):
    assert c.post("/api/youtube/import", json=body).status_code == 422


def test_imports_are_private_to_each_user(c, db):
    from app.models import User

    do_import(c, [vid(1)])
    db.add(User(id=2, email="o@example.com", password_hash="x", display_name="O", timezone="UTC"))
    db.commit()
    from app.models import Video

    assert db.query(Video).filter(Video.user_id == 2).count() == 0 and db.query(Video).filter(Video.user_id == 1).count() == 1


# ---------------- failure handling ----------------


@pytest.mark.parametrize("url", ["hello", "https://example.com/@x", "https://www.youtube.com/c/Foo", "javascript:alert(1)"])
def test_invalid_urls_get_a_422_with_guidance(c, url):
    r = c.post("/api/youtube/preview", json={"url": url})
    assert r.status_code == 422 and len(r.json()["detail"]) > 15


def test_blank_url_is_rejected_by_validation(c):
    assert c.post("/api/youtube/preview", json={"url": "  "}).status_code == 422


def test_unknown_channel_is_404(c):
    r = c.post("/api/youtube/preview", json={"url": "https://www.youtube.com/@nobodyhere"})
    assert r.status_code == 404 and "channel" in r.json()["detail"]


def test_private_playlist_is_explained(c):
    r = c.post("/api/youtube/preview", json={"url": "https://www.youtube.com/playlist?list=" + "PL" + "z" * 10})
    assert r.status_code == 404 and "private" in r.json()["detail"]


@pytest.mark.parametrize("status_code, reason, http", [
    (403, "quotaExceeded", 429), (400, "keyInvalid", 503), (403, "accessNotConfigured", 503), (500, "backendError", 502),
])
def test_youtube_failures_map_to_meaningful_http_errors(c, fake, status_code, reason, http):
    fake.fail = (status_code, reason)
    r = c.post("/api/youtube/preview", json={"url": CHANNEL})
    assert r.status_code == http and r.json()["detail"] and "boom" not in r.text


def test_quota_exhaustion_during_import_saves_nothing(c, fake):
    ids = [v["youtube_video_id"] for v in preview(c)["videos"][:3]]
    fake.fail = (403, "quotaExceeded")
    r = c.post("/api/youtube/import", json={"url": CHANNEL, "video_ids": ids})
    assert r.status_code == 429 and library(c)["total"] == 0 and c.get("/api/video-playlists").json() == []


def test_network_failure_is_a_502(c, fake):
    fake.network_error = True
    r = c.post("/api/youtube/preview", json={"url": CHANNEL})
    assert r.status_code == 502 and "Couldn't reach YouTube" in r.json()["detail"]


def test_the_api_key_never_appears_in_any_response(c, fake):
    from tests.fake_youtube import KEY

    texts = [c.post("/api/youtube/preview", json={"url": CHANNEL}).text, c.get("/api/youtube/status").text]
    fake.fail = (403, "quotaExceeded")
    texts.append(c.post("/api/youtube/preview", json={"url": CHANNEL}).text)
    assert all(KEY not in t for t in texts)


# ---------------- end to end with the rest of the tracker ----------------


def test_imported_videos_feed_the_recommendation_oldest_first_and_exclude_completed(c):
    ids = [v["youtube_video_id"] for v in preview(c, limit=None)["videos"]]
    col = do_import(c, ids, retrieved=120)["collection"]
    assert col["total_videos"] == 120 and col["percent"] == 0
    nxt = c.get("/api/videos/next").json()
    assert nxt["youtube_video_id"] == vid(1)                                   # oldest published first
    c.post(f"/api/videos/{nxt['id']}/complete")
    again = c.get("/api/videos/next").json()
    assert again["youtube_video_id"] == vid(2)                                 # the completed one is never offered again
    summary = c.get(f"/api/video-playlists/{col['id']}").json()
    assert (summary["completed_videos"], summary["total_videos"], summary["percent"]) == (1, 120, 0)
    assert c.get("/api/videos/next", params={"order": "newest"}).json()["youtube_video_id"] == vid(120)
