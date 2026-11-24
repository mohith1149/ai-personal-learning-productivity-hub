"""Library-level rules: one video per user shared by many collections, soft remove vs permanent delete,
recommendation ordering by publish date, per-collection and overall progress, explicit status changes."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import User, Video, VideoMembership
from app.schemas import videos as s
from app.services import auth as auth_service
from app.services import videos as svc

NOW = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)
D = lambda days: datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=days)  # noqa: E731


@pytest.fixture
def user(db) -> User:
    return auth_service.create_first_user(
        db, email="me@example.com", password="correct-horse-9", display_name="Me", timezone="Asia/Kolkata")


def mk_playlist(db, user, name="ByteByteGo", **kw):
    return svc.create_playlist(db, user, s.PlaylistCreate(name=name, **kw))


def yt(db, user, playlist, vid: str, day: int | None, title: str | None = None):
    """A YouTube video with a publish date (day=None: no date)."""
    outcome, v = svc.upsert_video(db, user, playlist, {
        "title": title or f"T-{vid}", "url": f"https://www.youtube.com/watch?v={vid}", "youtube_video_id": vid,
        "published_at": D(day) if day is not None else None, "thumbnail_url": f"https://i.ytimg.com/vi/{vid}/mq.jpg",
        "duration_seconds": 600, "channel_id": "UCchan", "channel_title": "Chan"})
    db.commit()
    return outcome, v


# ---------------- one library row per YouTube video ----------------


def test_same_youtube_video_in_two_collections_is_one_library_row(db, user):
    a, b = mk_playlist(db, user, "A"), mk_playlist(db, user, "B")
    o1, v1 = yt(db, user, a, "aaaaaaaaaaa", 1)
    o2, v2 = yt(db, user, b, "aaaaaaaaaaa", 1)
    assert (o1, o2) == ("created", "linked") and v1.id == v2.id
    assert db.query(Video).count() == 1 and db.query(VideoMembership).count() == 2
    assert sorted(v1.playlist_ids) == sorted([a.id, b.id])
    assert yt(db, user, a, "aaaaaaaaaaa", 1)[0] == "duplicate" and db.query(VideoMembership).count() == 2


def test_progress_is_shared_across_collections(db, user):
    a, b = mk_playlist(db, user, "A"), mk_playlist(db, user, "B")
    _, v = yt(db, user, a, "aaaaaaaaaaa", 1)
    yt(db, user, b, "aaaaaaaaaaa", 1)
    svc.complete_video(db, user, v.id, now=NOW)
    assert svc.playlist_summary(db, user, a.id)["completed_videos"] == 1
    assert svc.playlist_summary(db, user, b.id)["completed_videos"] == 1
    assert svc.next_videos(db, b, 5) == []


def test_database_refuses_a_second_row_for_the_same_user_and_youtube_id(db, user):
    db.add(Video(user_id=user.id, title="x", youtube_video_id="aaaaaaaaaaa"))
    db.commit()
    db.add(Video(user_id=user.id, title="y", youtube_video_id="aaaaaaaaaaa"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_manual_videos_without_a_youtube_id_are_not_deduplicated(db, user):
    p = mk_playlist(db, user)
    svc.add_video(db, user, p.id, s.VideoCreate(title="Notes A"))
    svc.add_video(db, user, p.id, s.VideoCreate(title="Notes A"))
    assert db.query(Video).count() == 2


def test_bulk_paste_links_an_existing_library_video(db, user):
    a, b = mk_playlist(db, user, "A"), mk_playlist(db, user, "B")
    yt(db, user, a, "aaaaaaaaaaa", 1)
    r = svc.bulk_add_videos(db, user, b.id, s.BulkVideos(lines=["https://youtu.be/aaaaaaaaaaa", "https://youtu.be/bbbbbbbbbbb"]))
    assert (r["added"], r["linked"], r["duplicates"]) == (1, 1, 0) and db.query(Video).count() == 2


def test_reimport_fills_missing_metadata_but_keeps_user_edits(db, user):
    a = mk_playlist(db, user)
    _, v = svc.upsert_video(db, user, a, {"title": "My title", "youtube_video_id": "aaaaaaaaaaa"}), None
    v = db.scalar(select(Video))
    v.notes = "mine"
    db.commit()
    yt(db, user, a, "aaaaaaaaaaa", 3, title="Their title")
    v = db.scalar(select(Video))
    assert v.title == "My title" and v.notes == "mine"
    assert v.thumbnail_url and v.published_at is not None and v.duration_seconds == 600


# ---------------- recommendation order ----------------


def test_default_recommendation_is_oldest_published_first(db, user):
    p = mk_playlist(db, user)
    assert p.recommend_order == "oldest"
    # inserted in a different order than published, plus a hand-added video with no date
    _, new = yt(db, user, p, "ccccccccccc", 30)
    _, old = yt(db, user, p, "aaaaaaaaaaa", 10)
    _, mid = yt(db, user, p, "bbbbbbbbbbb", 20)
    manual = svc.add_video(db, user, p.id, s.VideoCreate(title="No date"))
    assert [v.id for v in svc.next_videos(db, p, 10)] == [old.id, mid.id, new.id, manual.id]
    assert svc.next_video_overall(db, user).id == old.id


def test_newest_first_is_selectable(db, user):
    p = mk_playlist(db, user, recommend_order="newest")
    _, old = yt(db, user, p, "aaaaaaaaaaa", 10)
    _, new = yt(db, user, p, "ccccccccccc", 30)
    assert [v.id for v in svc.next_videos(db, p, 10)] == [new.id, old.id]
    assert svc.next_video_overall(db, user, "newest").id == new.id
    assert svc.next_video_overall(db, user, "oldest").id == old.id


def test_completed_videos_are_never_recommended_in_either_order(db, user):
    for order in ("oldest", "newest"):
        p = mk_playlist(db, user, f"P-{order}", recommend_order=order)
        _, first = yt(db, user, p, "aaaaaaaaaaa" if order == "oldest" else "zzzzzzzzzzz", 1)
        _, second = yt(db, user, p, "bbbbbbbbbbb" if order == "oldest" else "yyyyyyyyyyy", 2)
        head = svc.next_videos(db, p, 1)[0]
        svc.complete_video(db, user, head.id, now=NOW)
        assert svc.next_videos(db, p, 1)[0].id != head.id
        assert head.id not in [v.id for v in svc.next_videos(db, p, 10)]
        assert svc.next_video_overall(db, user, order).id != head.id


def test_in_progress_video_is_still_recommended(db, user):
    p = mk_playlist(db, user)
    _, a = yt(db, user, p, "aaaaaaaaaaa", 1)
    yt(db, user, p, "bbbbbbbbbbb", 2)
    svc.start_video(db, user, a.id)
    assert svc.next_videos(db, p, 1)[0].id == a.id


def test_inactive_collection_is_left_out_of_the_overall_recommendation(db, user):
    p = mk_playlist(db, user, active=False)
    yt(db, user, p, "aaaaaaaaaaa", 1)
    assert svc.next_video_overall(db, user) is None
    q = mk_playlist(db, user, "Other")
    _, v = yt(db, user, q, "aaaaaaaaaaa", 1)  # same video also lives in an active collection
    assert svc.next_video_overall(db, user).id == v.id


def test_recommendation_is_scoped_to_the_user(db, user):
    other = User(id=2, email="o@example.com", password_hash="x", display_name="O", timezone="UTC")
    db.add(other)
    db.commit()
    p = mk_playlist(db, user)
    yt(db, user, p, "aaaaaaaaaaa", 1)
    assert svc.next_video_overall(db, other) is None
    assert svc.library_stats(db, other)["total"] == 0


# ---------------- remove (soft) vs delete permanently ----------------


def test_removed_video_vanishes_everywhere_but_is_restorable(db, user):
    p = mk_playlist(db, user)
    _, a = yt(db, user, p, "aaaaaaaaaaa", 1)
    _, b = yt(db, user, p, "bbbbbbbbbbb", 2)
    svc.remove_video(db, user, a.id, now=NOW)
    assert [v.id for v in svc.list_videos(db, user, p.id)["items"]] == [b.id]
    assert [v.id for v in svc.list_videos(db, user)["items"]] == [b.id]
    assert [v.id for v in svc.list_videos(db, user, view="removed")["items"]] == [a.id]
    assert [v.id for v in svc.next_videos(db, p, 5)] == [b.id]
    assert svc.playlist_summary(db, user, p.id)["total_videos"] == 1
    assert svc.library_stats(db, user)["removed"] == 1
    with pytest.raises(svc.NotFound):
        svc.complete_video(db, user, a.id)  # a removed video can't be acted on until restored
    svc.restore_video(db, user, a.id)
    assert [v.id for v in svc.next_videos(db, p, 5)] == [a.id, b.id]


def test_removed_completed_video_does_not_count_as_progress(db, user):
    p = mk_playlist(db, user)
    _, a = yt(db, user, p, "aaaaaaaaaaa", 1)
    yt(db, user, p, "bbbbbbbbbbb", 2)
    svc.complete_video(db, user, a.id, now=NOW)
    assert svc.playlist_summary(db, user, p.id, NOW)["watched_today"] == 1
    svc.remove_video(db, user, a.id)
    s2 = svc.playlist_summary(db, user, p.id, NOW)
    assert (s2["total_videos"], s2["completed_videos"], s2["watched_today"], s2["percent"]) == (1, 0, 0, 0)
    svc.restore_video(db, user, a.id)
    assert svc.playlist_summary(db, user, p.id, NOW)["completed_videos"] == 1  # history survived the removal


def test_importing_a_removed_video_again_restores_it_without_duplicating(db, user):
    p = mk_playlist(db, user)
    _, a = yt(db, user, p, "aaaaaaaaaaa", 1)
    svc.remove_video(db, user, a.id)
    outcome, again = yt(db, user, p, "aaaaaaaaaaa", 1)
    assert outcome == "linked" and again.id == a.id and again.removed_at is None and db.query(Video).count() == 1


def test_delete_permanently_erases_the_video_and_its_links(db, user):
    a, b = mk_playlist(db, user, "A"), mk_playlist(db, user, "B")
    _, v = yt(db, user, a, "aaaaaaaaaaa", 1)
    yt(db, user, b, "aaaaaaaaaaa", 1)
    svc.delete_video(db, user, v.id)
    assert db.query(Video).count() == 0 and db.query(VideoMembership).count() == 0
    # a removed video can be deleted too, and the id can be imported afresh afterwards
    _, w = yt(db, user, a, "aaaaaaaaaaa", 1)
    svc.remove_video(db, user, w.id)
    svc.delete_video(db, user, w.id)
    assert yt(db, user, a, "aaaaaaaaaaa", 1)[0] == "created"


# ---------------- progress numbers ----------------


def test_per_collection_and_overall_progress(db, user):
    a, b = mk_playlist(db, user, "A"), mk_playlist(db, user, "B")
    ids = {}
    for i, vid in enumerate(("aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc")):
        ids[vid] = yt(db, user, a, vid, i)[1]
    yt(db, user, b, "ccccccccccc", 2)       # shared with A
    yt(db, user, b, "ddddddddddd", 3)
    svc.complete_video(db, user, ids["aaaaaaaaaaa"].id, now=NOW)
    svc.start_video(db, user, ids["bbbbbbbbbbb"].id)
    sa, sb = svc.playlist_summary(db, user, a.id, NOW), svc.playlist_summary(db, user, b.id, NOW)
    assert (sa["total_videos"], sa["completed_videos"], sa["in_progress_videos"], sa["unwatched_videos"], sa["percent"]) == (3, 1, 1, 1, 33)
    assert (sb["total_videos"], sb["completed_videos"], sb["in_progress_videos"], sb["unwatched_videos"], sb["percent"]) == (2, 0, 0, 2, 0)
    overall = svc.library_stats(db, user)
    # 4 distinct videos (C counted once although it is in two collections)
    assert (overall["total"], overall["completed"], overall["in_progress"], overall["unwatched"], overall["percent"]) == (4, 1, 1, 2, 25)


def test_percent_reaches_100_only_when_everything_is_completed(db, user):
    p = mk_playlist(db, user)
    vs = [yt(db, user, p, f"{c * 11}", i)[1] for i, c in enumerate("abc")]
    for v in vs[:2]:
        svc.complete_video(db, user, v.id, now=NOW)
    assert svc.playlist_summary(db, user, p.id)["percent"] == 66
    svc.complete_video(db, user, vs[2].id, now=NOW)
    assert svc.playlist_summary(db, user, p.id)["percent"] == 100
    assert svc.library_stats(db, user)["next_video"] is None


def test_summary_reports_youtube_counts_as_stored_never_estimated(db, user):
    p = mk_playlist(db, user)
    summary = svc.playlist_summary(db, user, p.id)
    assert summary["reported_total"] is None and summary["retrieved_count"] == 0  # unknown stays unknown
    p.reported_total, p.retrieved_count = 500, 100
    db.commit()
    summary = svc.playlist_summary(db, user, p.id)
    assert (summary["reported_total"], summary["retrieved_count"], summary["total_videos"]) == (500, 100, 0)


def test_progress_updates_immediately_after_each_change(db, user):
    p = mk_playlist(db, user)
    _, v = yt(db, user, p, "aaaaaaaaaaa", 1)
    assert svc.library_stats(db, user)["percent"] == 0
    svc.complete_video(db, user, v.id, now=NOW)
    assert svc.library_stats(db, user)["percent"] == 100
    svc.uncomplete_video(db, user, v.id)
    assert svc.library_stats(db, user)["percent"] == 0


# ---------------- status, list filters, sorting ----------------


def test_set_status_covers_every_transition(db, user):
    p = mk_playlist(db, user)
    _, v = yt(db, user, p, "aaaaaaaaaaa", 1)
    assert svc.set_status(db, user, v.id, "watching").completed_at is None
    done = svc.set_status(db, user, v.id, "completed", now=NOW)
    assert done.status == "completed" and done.completed_at == NOW
    first = done.completed_at
    assert svc.set_status(db, user, v.id, "completed", now=NOW + timedelta(days=1)).completed_at == first  # idempotent
    back = svc.set_status(db, user, v.id, "unwatched")
    assert back.status == "unwatched" and back.completed_at is None
    assert svc.set_status(db, user, v.id, "watching").status == "watching"


def test_filters_search_and_sorting(db, user):
    p = mk_playlist(db, user)
    _, a = yt(db, user, p, "aaaaaaaaaaa", 1, title="How DNS works")
    _, b = yt(db, user, p, "bbbbbbbbbbb", 2, title="Rate limiter")
    _, c = yt(db, user, p, "ccccccccccc", 3, title="100% caching")
    svc.complete_video(db, user, a.id, now=NOW)
    svc.complete_video(db, user, c.id, now=NOW + timedelta(hours=1))
    svc.start_video(db, user, b.id)
    ids = lambda **kw: [v.id for v in svc.list_videos(db, user, p.id, **kw)["items"]]  # noqa: E731
    assert ids(status="completed") == [a.id, c.id]  # recommended order = oldest published first
    assert ids(status="watching") == [b.id] and ids(status="unwatched") == []
    assert ids(q="dns") == [a.id] and ids(q="100%") == [c.id] and ids(q="%") == [c.id]  # LIKE wildcards are literal
    assert ids(sort="newest") == [c.id, b.id, a.id] and ids(sort="oldest") == [a.id, b.id, c.id]
    assert ids(view="completed") == [c.id, a.id]                    # most recently completed first
    assert ids(sort="completed", status="completed") == [c.id, a.id]
    assert ids(sort="added")[0] == c.id
    assert ids(view="open") == [b.id]
    page = svc.list_videos(db, user, p.id, sort="oldest", limit=1, offset=1)
    assert page["total"] == 3 and [v.id for v in page["items"]] == [b.id]


def test_library_listing_spans_collections_without_duplicates(db, user):
    a, b = mk_playlist(db, user, "A"), mk_playlist(db, user, "B")
    yt(db, user, a, "aaaaaaaaaaa", 1)
    yt(db, user, b, "aaaaaaaaaaa", 1)
    yt(db, user, b, "bbbbbbbbbbb", 2)
    lib = svc.list_videos(db, user)
    assert lib["total"] == 2 and len(lib["items"]) == 2


def test_manual_order_follows_move_and_ignores_dates(db, user):
    p = mk_playlist(db, user, recommend_order="manual")
    _, a = yt(db, user, p, "aaaaaaaaaaa", 1)
    _, b = yt(db, user, p, "bbbbbbbbbbb", 2)
    assert [v.id for v in svc.next_videos(db, p, 5)] == [a.id, b.id]
    svc.move_video(db, user, b.id, "up", p.id)
    assert [v.id for v in svc.next_videos(db, p, 5)] == [b.id, a.id]


# ---------------- playlist/channel links belong in Import, not in the paste/add forms ----------------

COLLECTION_LINKS = ["https://www.youtube.com/playlist?list=PLCRMIe5FDPsd0gVs500xeOewfySTsmEjf",
                    "https://www.youtube.com/@ByteByteGo", "https://www.youtube.com/channel/UCZgt6AzoyjslHTC9dz0UoTw"]


@pytest.mark.parametrize("url", COLLECTION_LINKS)
def test_add_video_rejects_channel_and_playlist_links(db, user, url):
    p = mk_playlist(db, user)
    with pytest.raises(svc.RuleError, match="Import from YouTube"):
        svc.add_video(db, user, p.id, s.VideoCreate(title="x", url=url))
    assert db.query(Video).count() == 0


def test_paste_rejects_collection_links_but_keeps_real_videos(db, user):
    p = mk_playlist(db, user)
    lines = [*COLLECTION_LINKS, "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLCRMIe5FDPsd0gVs500xeOewfySTsmEjf",
             "https://example.com/some-page"]
    r = svc.bulk_add_videos(db, user, p.id, s.BulkVideos(lines=lines))
    assert r["added"] == 2 and len(r["invalid"]) == 3 and all("Import from YouTube" in i for i in r["invalid"])
