"""Business-rule tests for video playlists and videos (injected clock where it matters).
Test user lives in Asia/Kolkata (UTC+05:30)."""
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import User, Video, VideoPlaylist
from app.schemas import videos as s
from app.services import auth as auth_service
from app.services import videos as svc

NOW = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)  # 15:30 on Mon 23 Nov in Kolkata
YT = "https://www.youtube.com/watch?v={}"


@pytest.fixture
def user(db) -> User:
    return auth_service.create_first_user(
        db, email="me@example.com", password="correct-horse-9", display_name="Me", timezone="Asia/Kolkata"
    )


@pytest.fixture
def other_user(db, user) -> User:
    u = User(id=2, email="other@example.com", password_hash="x", display_name="Other", timezone="UTC")
    db.add(u)
    db.commit()
    return u


def mk_playlist(db, user, name="ByteByteGo", **kw) -> VideoPlaylist:
    return svc.create_playlist(db, user, s.PlaylistCreate(name=name, **kw))


def mk_videos(db, user, playlist, n=3) -> list[Video]:
    return [svc.add_video(db, user, playlist.id, s.VideoCreate(title=f"V{i}")) for i in range(1, n + 1)]


# ============================== link parsing ==============================


@pytest.mark.parametrize("url, vid", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://youtube.com/watch?v=dQw4w9WgXcQ&list=PL123&t=5s", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ?si=abc", "dQw4w9WgXcQ"),
    ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/watch?v=short", None),
    ("https://www.youtube.com/playlist?list=PL123", None),
    ("https://example.com/watch?v=dQw4w9WgXcQ", None),
    ("https://evil-youtube.com/watch?v=dQw4w9WgXcQ", None),
    (None, None),
])
def test_youtube_id_extraction(url, vid):
    assert svc.youtube_video_id(url) == vid


@pytest.mark.parametrize("line, expected", [
    ("https://youtu.be/dQw4w9WgXcQ", ("YouTube video dQw4w9WgXcQ", "https://youtu.be/dQw4w9WgXcQ")),
    ("How DNS works | https://youtu.be/dQw4w9WgXcQ", ("How DNS works", "https://youtu.be/dQw4w9WgXcQ")),
    ("- How DNS works - https://example.com/v/1", ("How DNS works", "https://example.com/v/1")),
    ("https://example.com/v/1, trailing", ("trailing", "https://example.com/v/1")),
])
def test_parse_line(line, expected):
    assert svc.parse_line(line) == expected


@pytest.mark.parametrize("line", ["just words", "javascript:alert(1)", "ftp://example.com/x", "http://"])
def test_parse_line_rejects_non_http_links(line):
    assert svc.parse_line(line) is None


# ============================== playlists ==============================


def test_playlist_defaults_and_empty_summary(db, user):
    p = mk_playlist(db, user)
    summary = svc.playlist_summary(db, user, p.id, NOW)
    assert summary["daily_target"] == 1 and summary["active"] is True
    assert (summary["total_videos"], summary["completed_videos"], summary["percent"]) == (0, 0, 0)
    assert summary["next_video"] is None and summary["watched_today"] == 0 and summary["remaining_today"] == 1


def test_playlist_names_are_unique_per_user_ignoring_case(db, user, other_user):
    mk_playlist(db, user, "ByteByteGo")
    with pytest.raises(svc.Conflict):
        mk_playlist(db, user, "bytebytego")
    mk_playlist(db, other_user, "ByteByteGo")  # another owner may reuse the name
    other = mk_playlist(db, user, "Other")
    with pytest.raises(svc.Conflict):
        svc.update_playlist(db, user, other.id, s.PlaylistUpdate(name="BYTEBYTEGO"))
    svc.update_playlist(db, user, other.id, s.PlaylistUpdate(name="Other"))  # renaming to itself is fine


def test_database_also_enforces_unique_playlist_name(db, user):
    mk_playlist(db, user)
    db.add(VideoPlaylist(user_id=user.id, name="ByteByteGo"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


@pytest.mark.parametrize("target", [0, 51, -1])
def test_daily_target_range_is_enforced_by_schema_and_database(db, user, target):
    with pytest.raises(ValueError):
        s.PlaylistCreate(name="X", daily_target=target)
    db.add(VideoPlaylist(user_id=user.id, name="Raw", daily_target=target))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_update_playlist_rejects_null_required_fields(db, user):
    p = mk_playlist(db, user)
    for field in ("name", "daily_target", "active"):
        with pytest.raises(svc.RuleError):
            svc.update_playlist(db, user, p.id, s.PlaylistUpdate(**{field: None}))


def test_delete_playlist_removes_its_videos(db, user):
    p = mk_playlist(db, user)
    mk_videos(db, user, p, 2)
    svc.delete_playlist(db, user, p.id)
    assert db.query(Video).count() == 0 and db.query(VideoPlaylist).count() == 0


def test_playlist_source_url_must_be_http(db):
    for bad in ("javascript:alert(1)", "data:text/html,x", "ftp://x.test/a"):
        with pytest.raises(ValueError):
            s.PlaylistCreate(name="X", source_url=bad)


# ============================== videos: CRUD ==============================


def test_videos_are_appended_in_order_and_start_unwatched(db, user):
    p = mk_playlist(db, user)
    a, b, c = mk_videos(db, user, p)
    assert [v.position for v in (a, b, c)] == [1, 2, 3]
    assert all(v.status == "unwatched" and v.completed_at is None for v in (a, b, c))


def test_add_video_extracts_youtube_id_and_rejects_duplicate(db, user):
    p = mk_playlist(db, user)
    v = svc.add_video(db, user, p.id, s.VideoCreate(title="A", url=YT.format("dQw4w9WgXcQ")))
    assert v.youtube_video_id == "dQw4w9WgXcQ"
    with pytest.raises(svc.Conflict):
        svc.add_video(db, user, p.id, s.VideoCreate(title="Same", url="https://youtu.be/dQw4w9WgXcQ"))
    # the same video may live in a different playlist
    p2 = mk_playlist(db, user, "Second")
    svc.add_video(db, user, p2.id, s.VideoCreate(title="Same", url="https://youtu.be/dQw4w9WgXcQ"))


def test_videos_without_youtube_ids_are_never_treated_as_duplicates(db, user):
    p = mk_playlist(db, user)
    svc.add_video(db, user, p.id, s.VideoCreate(title="A", url="https://example.com/1"))
    svc.add_video(db, user, p.id, s.VideoCreate(title="B", url="https://example.com/1"))
    svc.add_video(db, user, p.id, s.VideoCreate(title="C"))
    svc.add_video(db, user, p.id, s.VideoCreate(title="D"))
    assert db.query(Video).count() == 4


def test_update_video_changes_fields_and_recomputes_youtube_id(db, user):
    p = mk_playlist(db, user)
    v = svc.add_video(db, user, p.id, s.VideoCreate(title="A", url=YT.format("dQw4w9WgXcQ")))
    svc.update_video(db, user, v.id, s.VideoUpdate(title="B", notes="n", category="Networking"))
    assert (v.title, v.notes, v.category, v.youtube_video_id) == ("B", "n", "Networking", "dQw4w9WgXcQ")
    svc.update_video(db, user, v.id, s.VideoUpdate(url=YT.format("aaaaaaaaaaa")))
    assert v.youtube_video_id == "aaaaaaaaaaa"
    svc.update_video(db, user, v.id, s.VideoUpdate(url=None))
    assert v.youtube_video_id is None and v.url is None
    with pytest.raises(svc.RuleError):
        svc.update_video(db, user, v.id, s.VideoUpdate(title=None))


def test_update_video_url_to_an_existing_video_conflicts(db, user):
    p = mk_playlist(db, user)
    svc.add_video(db, user, p.id, s.VideoCreate(title="A", url=YT.format("dQw4w9WgXcQ")))
    b = svc.add_video(db, user, p.id, s.VideoCreate(title="B", url=YT.format("aaaaaaaaaaa")))
    with pytest.raises(svc.Conflict):
        svc.update_video(db, user, b.id, s.VideoUpdate(url=YT.format("dQw4w9WgXcQ")))


def test_delete_video(db, user):
    p = mk_playlist(db, user)
    v, w, _ = mk_videos(db, user, p)
    svc.delete_video(db, user, v.id)
    assert [x.id for x in svc.list_videos(db, user, p.id)["items"]][0] == w.id
    with pytest.raises(svc.NotFound):
        svc.delete_video(db, user, v.id)


# ============================== bulk paste ==============================


def test_bulk_add_reports_added_duplicates_and_invalid(db, user):
    p = mk_playlist(db, user)
    svc.add_video(db, user, p.id, s.VideoCreate(title="Existing", url=YT.format("dQw4w9WgXcQ")))
    lines = [
        "How DNS works | https://youtu.be/aaaaaaaaaaa",
        "https://www.youtube.com/watch?v=bbbbbbbbbbb",
        "again https://youtu.be/aaaaaaaaaaa",          # duplicate inside the paste
        "https://youtu.be/dQw4w9WgXcQ",                # already in the playlist
        "no link here",
        "javascript:alert(1)",
        "Plain page | https://example.com/v/1",
    ]
    r = svc.bulk_add_videos(db, user, p.id, s.BulkVideos(lines=lines, category="Systems"))
    assert (r["added"], r["duplicates"]) == (3, 2)
    assert r["invalid"] == ["no link here", "javascript:alert(1)"]
    items = svc.list_videos(db, user, p.id)["items"]
    assert [v.title for v in items] == ["Existing", "How DNS works", "YouTube video bbbbbbbbbbb", "Plain page"]
    assert [v.position for v in items] == [1, 2, 3, 4]
    assert items[1].category == "Systems"


def test_bulk_limits(db, user):
    with pytest.raises(ValueError):
        s.BulkVideos(lines=[])
    with pytest.raises(ValueError):
        s.BulkVideos(lines=["https://example.com/x"] * 201)


# ============================== completion ==============================


def test_complete_sets_status_and_time_and_is_idempotent(db, user):
    p = mk_playlist(db, user)
    v = mk_videos(db, user, p, 1)[0]
    first = svc.complete_video(db, user, v.id, now=NOW)
    assert first.status == "completed" and first.completed_at == NOW
    later = datetime(2026, 11, 24, 8, 0, tzinfo=timezone.utc)
    again = svc.complete_video(db, user, v.id, now=later)
    assert again.completed_at == NOW  # the first completion time is kept


def test_uncomplete_clears_completion_time(db, user):
    p = mk_playlist(db, user)
    v = mk_videos(db, user, p, 1)[0]
    svc.complete_video(db, user, v.id, now=NOW)
    back = svc.uncomplete_video(db, user, v.id)
    assert back.status == "unwatched" and back.completed_at is None


def test_start_marks_watching_but_refuses_completed(db, user):
    p = mk_playlist(db, user)
    a, b, _ = mk_videos(db, user, p)
    assert svc.start_video(db, user, a.id).status == "watching"
    svc.complete_video(db, user, b.id)
    with pytest.raises(svc.RuleError):
        svc.start_video(db, user, b.id)


def test_database_refuses_completed_without_time_and_time_without_completed(db, user):
    p = mk_playlist(db, user)
    a, b, _ = mk_videos(db, user, p)
    a.status = "completed"
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    b.completed_at = NOW
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ============================== recommendation (the critical rule) ==============================


def test_next_video_is_first_in_order(db, user):
    p = mk_playlist(db, user)
    a, b, c = mk_videos(db, user, p)
    assert svc.playlist_summary(db, user, p.id, NOW)["next_video"].id == a.id


def test_completed_video_is_never_recommended(db, user):
    p = mk_playlist(db, user)
    a, b, c = mk_videos(db, user, p)
    svc.complete_video(db, user, a.id, now=NOW)
    assert [v.id for v in svc.next_videos(db, p.id, 10)] == [b.id, c.id]
    assert svc.playlist_summary(db, user, p.id, NOW)["next_video"].id == b.id
    assert svc.next_video_overall(db, user).id == b.id


def test_completing_out_of_order_skips_only_that_video(db, user):
    p = mk_playlist(db, user)
    a, b, c = mk_videos(db, user, p)
    svc.complete_video(db, user, b.id, now=NOW)
    assert [v.id for v in svc.next_videos(db, p.id, 10)] == [a.id, c.id]


def test_watching_video_is_still_recommended(db, user):
    p = mk_playlist(db, user)
    a, b, _ = mk_videos(db, user, p)
    svc.start_video(db, user, a.id)
    assert svc.next_videos(db, p.id, 1)[0].id == a.id


def test_nothing_recommended_when_everything_is_completed(db, user):
    p = mk_playlist(db, user)
    for v in mk_videos(db, user, p, 2):
        svc.complete_video(db, user, v.id, now=NOW)
    assert svc.next_videos(db, p.id, 5) == [] and svc.next_video_overall(db, user) is None
    summary = svc.playlist_summary(db, user, p.id, NOW)
    assert summary["next_video"] is None and summary["percent"] == 100


def test_reopened_video_can_be_recommended_again_only_after_explicit_reopen(db, user):
    p = mk_playlist(db, user)
    a, b, _ = mk_videos(db, user, p)
    svc.complete_video(db, user, a.id, now=NOW)
    assert svc.next_videos(db, p.id, 1)[0].id == b.id
    svc.uncomplete_video(db, user, a.id)
    assert svc.next_videos(db, p.id, 1)[0].id == a.id


def test_recommendation_survives_reordering(db, user):
    p = mk_playlist(db, user)
    a, b, c = mk_videos(db, user, p)
    svc.complete_video(db, user, a.id, now=NOW)
    svc.move_video(db, user, c.id, "up")  # order is now a, c, b
    assert [v.id for v in svc.next_videos(db, p.id, 10)] == [c.id, b.id]


def test_overall_next_skips_inactive_playlists_and_other_users(db, user, other_user):
    old = mk_playlist(db, user, "Old")
    new = mk_playlist(db, user, "New")
    theirs = mk_playlist(db, other_user, "Theirs")
    mk_videos(db, user, old, 1)
    n = mk_videos(db, user, new, 1)[0]
    mk_videos(db, other_user, theirs, 1)
    svc.update_playlist(db, user, old.id, s.PlaylistUpdate(active=False))
    assert svc.next_video_overall(db, user).id == n.id
    svc.update_playlist(db, user, new.id, s.PlaylistUpdate(active=False))
    assert svc.next_video_overall(db, user) is None


# ============================== today / daily target ==============================


def test_today_counts_only_videos_completed_today_in_the_users_timezone(db, user):
    p = mk_playlist(db, user, daily_target=3)
    vids = mk_videos(db, user, p, 6)
    # 23 Nov 15:30 Kolkata. Local day = 22 Nov 18:30Z .. 23 Nov 18:30Z.
    svc.complete_video(db, user, vids[0].id, now=datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc))   # today
    svc.complete_video(db, user, vids[1].id, now=datetime(2026, 11, 22, 19, 0, tzinfo=timezone.utc))  # 00:30 today local
    svc.complete_video(db, user, vids[2].id, now=datetime(2026, 11, 22, 18, 0, tzinfo=timezone.utc))  # 23:30 YESTERDAY local
    t = svc.today(db, user, p.id, now=NOW)
    assert (t["daily_target"], t["watched_today"], t["remaining_today"], t["target_met"]) == (3, 2, 1, False)
    assert [v.id for v in t["up_next"]] == [vids[3].id]  # the next unwatched, never a completed one


def test_today_up_next_has_one_entry_per_remaining_video(db, user):
    p = mk_playlist(db, user, daily_target=3)
    vids = mk_videos(db, user, p, 5)
    t = svc.today(db, user, p.id, now=NOW)
    assert [v.id for v in t["up_next"]] == [v.id for v in vids[:3]]


def test_target_met_when_enough_watched_and_extra_videos_do_not_go_negative(db, user):
    p = mk_playlist(db, user, daily_target=2)
    vids = mk_videos(db, user, p, 5)
    for v in vids[:3]:
        svc.complete_video(db, user, v.id, now=NOW)
    t = svc.today(db, user, p.id, now=NOW)
    assert t["watched_today"] == 3 and t["remaining_today"] == 0 and t["target_met"] is True and t["up_next"] == []


def test_today_with_fewer_videos_left_than_the_target(db, user):
    p = mk_playlist(db, user, daily_target=5)
    mk_videos(db, user, p, 2)
    assert len(svc.today(db, user, p.id, now=NOW)["up_next"]) == 2


def test_uncompleting_removes_the_video_from_todays_count(db, user):
    p = mk_playlist(db, user, daily_target=1)
    v = mk_videos(db, user, p, 1)[0]
    svc.complete_video(db, user, v.id, now=NOW)
    assert svc.today(db, user, p.id, now=NOW)["target_met"] is True
    svc.uncomplete_video(db, user, v.id)
    assert svc.today(db, user, p.id, now=NOW)["target_met"] is False


# ============================== progress, listing, ordering ==============================


def test_progress_is_floored_and_counts_only_completed(db, user):
    p = mk_playlist(db, user)
    a, b, c = mk_videos(db, user, p)
    svc.start_video(db, user, a.id)
    svc.complete_video(db, user, b.id, now=NOW)
    svc.complete_video(db, user, c.id, now=NOW)
    s_ = svc.playlist_summary(db, user, p.id, NOW)
    assert (s_["total_videos"], s_["completed_videos"], s_["percent"]) == (3, 2, 66)


def test_list_views_search_and_pagination(db, user):
    p = mk_playlist(db, user)
    for t in ("How DNS works", "100% cache_hits", "Load balancing", "Rate limiter"):
        svc.add_video(db, user, p.id, s.VideoCreate(title=t))
    items = svc.list_videos(db, user, p.id)["items"]
    svc.complete_video(db, user, items[0].id, now=NOW)
    assert svc.list_videos(db, user, p.id, "open")["total"] == 3
    assert [v.title for v in svc.list_videos(db, user, p.id, "completed")["items"]] == ["How DNS works"]
    assert [v.title for v in svc.list_videos(db, user, p.id, q="dns")["items"]] == ["How DNS works"]
    # LIKE wildcards in the search box are literal characters
    assert [v.title for v in svc.list_videos(db, user, p.id, q="100%")["items"]] == ["100% cache_hits"]
    assert svc.list_videos(db, user, p.id, q="%")["total"] == 1
    assert svc.list_videos(db, user, p.id, q="_")["total"] == 1
    page = svc.list_videos(db, user, p.id, limit=2, offset=2)
    assert page["total"] == 4 and [v.title for v in page["items"]] == ["Load balancing", "Rate limiter"]


def test_move_up_down_and_edges(db, user):
    p = mk_playlist(db, user)
    a, b, c = mk_videos(db, user, p)
    order = lambda: [v.title for v in svc.list_videos(db, user, p.id)["items"]]  # noqa: E731
    svc.move_video(db, user, c.id, "up")
    assert order() == ["V1", "V3", "V2"]
    svc.move_video(db, user, a.id, "up")      # already first: no change
    svc.move_video(db, user, b.id, "down")    # already last: no change
    assert order() == ["V1", "V3", "V2"]
    svc.move_video(db, user, a.id, "down")
    assert order() == ["V3", "V1", "V2"]


def test_move_works_even_when_positions_have_gaps_or_ties(db, user):
    p = mk_playlist(db, user)
    a, b, c = mk_videos(db, user, p)
    a.position, b.position, c.position = 5, 5, 9
    db.commit()
    svc.move_video(db, user, b.id, "down")
    # ties break by id, so the order was a, b, c; moving b down gives a, c, b
    assert [v.id for v in svc.list_videos(db, user, p.id)["items"]] == [a.id, c.id, b.id]
    positions = [v.position for v in svc.list_videos(db, user, p.id)["items"]]
    assert positions == [1, 2, 3]


# ============================== isolation between users ==============================


def test_other_users_data_is_not_found(db, user, other_user):
    p = mk_playlist(db, user)
    v = mk_videos(db, user, p, 1)[0]
    for call in (
        lambda: svc.playlist_summary(db, other_user, p.id),
        lambda: svc.update_playlist(db, other_user, p.id, s.PlaylistUpdate(name="X")),
        lambda: svc.delete_playlist(db, other_user, p.id),
        lambda: svc.add_video(db, other_user, p.id, s.VideoCreate(title="X")),
        lambda: svc.bulk_add_videos(db, other_user, p.id, s.BulkVideos(lines=["https://example.com/a"])),
        lambda: svc.list_videos(db, other_user, p.id),
        lambda: svc.today(db, other_user, p.id),
        lambda: svc.update_video(db, other_user, v.id, s.VideoUpdate(title="X")),
        lambda: svc.delete_video(db, other_user, v.id),
        lambda: svc.start_video(db, other_user, v.id),
        lambda: svc.complete_video(db, other_user, v.id),
        lambda: svc.uncomplete_video(db, other_user, v.id),
        lambda: svc.move_video(db, other_user, v.id, "up"),
    ):
        with pytest.raises(svc.NotFound):
            call()
    assert svc.list_playlists(db, other_user) == []
