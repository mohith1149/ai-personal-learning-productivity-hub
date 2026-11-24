"""YouTube client: URL validation, metadata, thumbnails, pagination, limits, errors - against a fake API."""
import pytest

from app.services import youtube as y
from tests.fake_youtube import CHANNEL_ID, KEY, UPLOADS_ID, FakeYouTube, vid

PL = "PL" + "p" * 10


# ---------------- URL validation ----------------


@pytest.mark.parametrize("text, expected", [
    ("https://www.youtube.com/@ByteByteGo", y.Source("channel", handle="@ByteByteGo")),
    ("https://www.youtube.com/@ByteByteGo/videos", y.Source("channel", handle="@ByteByteGo")),
    ("https://youtube.com/@ByteByteGo/streams?x=1", y.Source("channel", handle="@ByteByteGo")),
    ("http://m.youtube.com/@byte.byte-go_1", y.Source("channel", handle="@byte.byte-go_1")),
    ("youtube.com/@ByteByteGo", y.Source("channel", handle="@ByteByteGo")),
    ("@ByteByteGo", y.Source("channel", handle="@ByteByteGo")),
    (f"https://www.youtube.com/channel/{CHANNEL_ID}", y.Source("channel", channel_id=CHANNEL_ID)),
    (f"https://www.youtube.com/channel/{CHANNEL_ID}/videos", y.Source("channel", channel_id=CHANNEL_ID)),
    (CHANNEL_ID, y.Source("channel", channel_id=CHANNEL_ID)),
    (f"https://www.youtube.com/playlist?list={PL}", y.Source("playlist", playlist_id=PL)),
    (f"https://www.youtube.com/watch?v=dQw4w9WgXcQ&list={PL}", y.Source("playlist", playlist_id=PL)),
    (f"  https://www.youtube.com/playlist?list={PL}&si=abc  ", y.Source("playlist", playlist_id=PL)),
])
def test_valid_sources(text, expected):
    assert y.parse_source(text) == expected


@pytest.mark.parametrize("text", [
    "", "   ", "hello", "https://example.com/@ByteByteGo", "https://evil-youtube.com/@ByteByteGo",
    "https://youtube.com.evil.test/@ByteByteGo", "ftp://www.youtube.com/@ByteByteGo", "javascript:alert(1)",
    "https://www.youtube.com/", "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # a single video isn't a source
    "https://www.youtube.com/channel/notachannelid", "https://www.youtube.com/playlist", "https://www.youtube.com/playlist?list=",
    "https://www.youtube.com/playlist?list=a b", "https://www.youtube.com/@ab", "https://www.youtube.com/@bad handle!",
    "https://www.youtube.com/c/ByteByteGo", "https://www.youtube.com/user/ByteByteGo", "x" * 600,
])
def test_invalid_sources_are_rejected_with_a_helpful_message(text):
    with pytest.raises(y.YouTubeError) as e:
        y.parse_source(text)
    assert e.value.code == "invalid_url" and len(e.value.message) > 20


def test_legacy_channel_links_explain_what_to_use_instead():
    with pytest.raises(y.YouTubeError, match="@handle"):
        y.parse_source("https://www.youtube.com/c/ByteByteGo")


@pytest.mark.parametrize("iso, seconds", [
    ("PT4M13S", 253), ("PT1H2M3S", 3723), ("PT45S", 45), ("PT2H", 7200), ("P1DT1H", 90000), ("P0D", 0), ("PT0S", 0),
    (None, None), ("", None), ("garbage", None), ("PT-5S", None),
])
def test_duration_parsing(iso, seconds):
    assert y.parse_duration(iso) == seconds


# ---------------- metadata ----------------


def test_channel_metadata_by_handle_and_by_id():
    fake = FakeYouTube()
    for src in (y.Source("channel", handle="@FakeChannel"), y.Source("channel", channel_id=CHANNEL_ID)):
        info = fake.client().resolve(src)
        assert (info.id, info.title, info.handle) == (CHANNEL_ID, "Fake Channel", "@fakechannel")
        assert info.total_available == 120 and info.thumbnail_url == "https://yt3.ggpht.com/fake=s240"
        assert info.uploads_playlist_id == UPLOADS_ID and info.url.endswith(CHANNEL_ID)


def test_unreported_video_count_is_none_not_a_guess():
    fake = FakeYouTube()
    fake.channel_video_count = None
    assert fake.client().resolve(y.Source("channel", handle="@fakechannel")).total_available is None
    fake.channel_video_count = "not-a-number"
    assert fake.client().resolve(y.Source("channel", handle="@fakechannel")).total_available is None


def test_unknown_channel_is_not_found():
    with pytest.raises(y.YouTubeError) as e:
        FakeYouTube().client().resolve(y.Source("channel", handle="@nobodyhere"))
    assert e.value.code == "not_found"


def test_playlist_metadata_and_count():
    info = FakeYouTube().client().resolve(y.Source("playlist", playlist_id=PL))
    assert (info.kind, info.id, info.title, info.total_available) == ("playlist", PL, "Fake playlist", 4)
    assert info.thumbnail_url == "https://i.ytimg.com/vi/x/hqdefault.jpg" and info.channel_title == "Fake Channel"


def test_private_or_unknown_playlist_is_reported_not_found():
    with pytest.raises(y.YouTubeError) as e:
        FakeYouTube().client().resolve(y.Source("playlist", playlist_id="PL" + "z" * 10))
    assert e.value.code == "not_found" and "private" in e.value.message


# ---------------- fetching and pagination ----------------


def channel(fake):
    c = fake.client()
    return c, c.resolve(y.Source("channel", handle="@fakechannel"))


def test_video_details_include_thumbnail_duration_and_dates():
    c, info = channel(FakeYouTube())
    r = c.fetch_videos(info, 3)
    v = r.videos[0]
    assert v.youtube_video_id == vid(120) and v.title == "Video number 120" and v.description == "About 120"
    assert v.thumbnail_url.endswith("mqdefault.jpg") and v.duration_seconds == (120 % 60 + 1) * 60 + 120 % 59
    assert v.published_at.tzinfo is not None and v.channel_id == CHANNEL_ID and v.channel_title == "Fake Channel"
    assert v.url == f"https://www.youtube.com/watch?v={vid(120)}"


@pytest.mark.parametrize("limit, expected_pages", [(10, 1), (25, 1), (50, 1), (51, 2), (100, 2), (101, 3)])
def test_limits_retrieve_exactly_that_many_and_use_page_tokens(limit, expected_pages):
    fake = FakeYouTube()
    c, info = channel(fake)
    r = c.fetch_videos(info, limit)
    assert len(r.videos) == limit and r.pages == expected_pages
    assert [v.youtube_video_id for v in r.videos] == [vid(n) for n in range(120, 120 - limit, -1)]  # newest first, no gaps
    assert r.more_available is True
    assert len(fake.calls("playlistItems")) == expected_pages


def test_all_walks_every_page_without_duplicates_or_gaps():
    fake = FakeYouTube()
    c, info = channel(fake)
    r = c.fetch_videos(info, None)
    ids = [v.youtube_video_id for v in r.videos]
    assert len(ids) == 120 == len(set(ids)) and r.pages == 3 and r.more_available is False
    assert info.total_available == len(ids)  # reported and retrieved agree here; they are separate numbers regardless


def test_limit_larger_than_the_channel_returns_everything():
    c, info = channel(FakeYouTube(uploads=list(range(7, 0, -1))))
    r = c.fetch_videos(info, 100)
    assert len(r.videos) == 7 and r.more_available is False


def test_limit_exactly_equal_to_the_channel_size_is_not_flagged_as_more():
    c, info = channel(FakeYouTube(uploads=list(range(5, 0, -1))))
    assert c.fetch_videos(info, 5).more_available is False


def test_empty_channel():
    c, info = channel(FakeYouTube(uploads=[]))
    r = c.fetch_videos(info, None)
    assert r.videos == [] and r.more_available is False and r.pages == 1


def test_private_and_deleted_videos_are_counted_as_unavailable_and_dont_use_up_the_limit():
    fake = FakeYouTube(uploads=list(range(60, 0, -1)), hidden={60, 58, 55})
    c, info = channel(fake)
    r = c.fetch_videos(info, 10)
    assert len(r.videos) == 10 and r.unavailable >= 3
    assert not {vid(60), vid(58), vid(55)} & {v.youtube_video_id for v in r.videos}
    assert r.videos[0].youtube_video_id == vid(59)


def test_playlist_fetch_keeps_playlist_order():
    c = FakeYouTube().client()
    info = c.resolve(y.Source("playlist", playlist_id=PL))
    r = c.fetch_videos(info, None)
    assert [v.youtube_video_id for v in r.videos] == [vid(n) for n in (5, 3, 9, 1)] and r.unavailable == 0


def test_hard_cap_marks_the_preview_truncated(monkeypatch):
    monkeypatch.setattr(y, "HARD_CAP", 100)
    c, info = channel(FakeYouTube(uploads=list(range(300, 0, -1))))
    r = c.fetch_videos(info, None)
    assert len(r.videos) == 100 and r.more_available is True


def test_video_details_batches_ids_in_groups_of_50():
    fake = FakeYouTube()
    ids = [vid(n) for n in range(1, 121)]
    out = fake.client().video_details(ids)
    assert [v.youtube_video_id for v in out] == ids and len(fake.calls("videos")) == 3  # 50 + 50 + 20


# ---------------- failures ----------------


def test_missing_key_is_a_clear_not_configured_error():
    for key in (None, ""):
        with pytest.raises(y.YouTubeError) as e:
            y.YouTubeClient(key)
        assert e.value.code == "not_configured" and "YOUTUBE_API_KEY" in e.value.message


@pytest.mark.parametrize("status, reason, code", [
    (403, "quotaExceeded", "quota"), (403, "dailyLimitExceeded", "quota"), (429, "rateLimitExceeded", "quota"),
    (400, "keyInvalid", "bad_key"), (403, "accessNotConfigured", "bad_key"), (403, "ipRefererBlocked", "bad_key"),
    (403, "somethingElse", "bad_key"), (404, "playlistNotFound", "not_found"), (403, "playlistItemsNotAccessible", "private"),
    (500, "backendError", "api_error"), (503, "x", "api_error"), (418, "x", "api_error"),
])
def test_api_errors_become_meaningful_messages(status, reason, code):
    fake = FakeYouTube()
    fake.fail = (status, reason)
    with pytest.raises(y.YouTubeError) as e:
        fake.client().resolve(y.Source("channel", handle="@fakechannel"))
    assert e.value.code == code and e.value.message
    assert "boom" not in e.value.message and KEY not in e.value.message  # raw API text/key never leak


def test_wrong_key_is_reported_as_bad_key():
    from app.services.youtube import YouTubeClient
    import httpx

    fake = FakeYouTube()
    c = YouTubeClient("some-other-key", http=httpx.Client(transport=httpx.MockTransport(fake)))
    with pytest.raises(y.YouTubeError) as e:
        c.resolve(y.Source("channel", handle="@fakechannel"))
    assert e.value.code == "bad_key"


def test_network_failure_is_reported_without_internals():
    fake = FakeYouTube()
    fake.network_error = True
    with pytest.raises(y.YouTubeError) as e:
        fake.client().resolve(y.Source("channel", handle="@fakechannel"))
    assert e.value.code == "network" and "no route" not in e.value.message


def test_quota_running_out_midway_surfaces_instead_of_returning_a_silent_partial_result():
    fake = FakeYouTube()
    c, info = channel(fake)
    fake.fail, fake.fail_after = (403, "quotaExceeded"), len(fake.requests) + 3  # first page ok (2 calls), then die
    with pytest.raises(y.YouTubeError) as e:
        c.fetch_videos(info, None)
    assert e.value.code == "quota"


def test_unreadable_reply_is_an_api_error():
    import httpx

    c = y.YouTubeClient(KEY, http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>"))))
    with pytest.raises(y.YouTubeError) as e:
        c.resolve(y.Source("channel", handle="@x" * 2))
    assert e.value.code == "api_error"


# ---------------- the key never travels in the URL ----------------


def test_api_key_is_sent_as_a_header_never_in_the_url():
    fake = FakeYouTube()
    c, info = channel(fake)
    c.fetch_videos(info, 5)
    assert fake.requests
    for r in fake.requests:
        assert r.headers["X-Goog-Api-Key"] == KEY
        assert KEY not in str(r.url) and "key" not in r.url.params
