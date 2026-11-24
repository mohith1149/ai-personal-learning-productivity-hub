"""Apply a day-by-day study plan to a video collection.

    python scripts/apply_plan.py plans/bytebytego_21_day.txt "BYTEBYTEGO"            # dry run: shows the matching only
    python scripts/apply_plan.py plans/bytebytego_21_day.txt "BYTEBYTEGO" --apply    # saves

Plan file: "Day N – title" lines followed by "1. video title" lines. Titles are matched to videos ALREADY in that
collection (nothing is created or invented). Matching ignores case, punctuation, "(M:SS version)" and
"Crash Course System Design #n" suffixes; when two videos share a title, "(4:21 version)" picks by duration.
Lines that match no video (e.g. "Use this day to revisit ...") are reported and skipped.

With --apply the collection's recommend_order becomes "manual", its videos are placed in plan order, and its daily
target is set to the largest day size, so "today" shows the next day's videos in order. Nothing is marked watched.
"""
import argparse
import difflib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import Video, VideoMembership, VideoPlaylist  # noqa: E402


def norm(title: str) -> str:
    t = re.sub(r"\((\d+:\d+) version\)", "", title, flags=re.I)
    t = re.sub(r":?\s*crash course system design #\d+", "", t, flags=re.I)
    t = re.sub(r"\(.*?\)", "", t)
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def version_seconds(title: str) -> int | None:
    m = re.search(r"\((\d+):(\d+) version\)", title, flags=re.I)
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def parse_plan(path: Path) -> list[tuple[int, str]]:
    items, day = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if m := re.match(r"^Day\s+(\d+)\b", line):
            day = int(m.group(1))
        elif m := re.match(r"^\d+\.\s+(.*)$", line):
            items.append((day, m.group(1).strip()))
    return items


def match(title: str, videos: list[Video], used: set[int]) -> tuple[Video | None, str]:
    key, want = norm(title), version_seconds(title)
    free = [v for v in videos if v.id not in used]
    exact = [v for v in free if norm(v.title) == key]
    if not exact:
        scored = sorted(((difflib.SequenceMatcher(None, key, norm(v.title)).ratio(), v) for v in free), key=lambda x: -x[0])
        if scored and scored[0][0] >= 0.9 and (len(scored) == 1 or scored[0][0] - scored[1][0] > 0.03):
            return scored[0][1], f"close match ({scored[0][0]:.2f}): {scored[0][1].title}"
        return None, "no video with this title"
    if len(exact) == 1:
        return exact[0], "exact"
    if want is not None:
        best = min(exact, key=lambda v: abs((v.duration_seconds or 10**6) - want))
        return best, f"same title twice, chose by length ({best.duration_seconds}s vs ~{want}s)"
    return exact[0], "same title twice, took the first"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("playlist")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    items = parse_plan(Path(args.plan))
    with SessionLocal() as db:
        pl = db.scalar(select(VideoPlaylist).where(VideoPlaylist.name == args.playlist))
        if pl is None:
            print(f"No collection named {args.playlist!r}.")
            return 1
        videos = list(db.scalars(select(Video).join(VideoMembership, VideoMembership.video_id == Video.id)
                                 .where(VideoMembership.playlist_id == pl.id, Video.removed_at.is_(None))))
        used: set[int] = set()
        ordered: list[tuple[int, Video]] = []
        problems = 0
        for day, title in items:
            v, how = match(title, videos, used)
            if v is None:
                problems += 1
                print(f"  SKIPPED  day {day}: {title}  ({how})")
                continue
            used.add(v.id)
            ordered.append((day, v))
            if how != "exact":
                print(f"  note     day {day}: {title}  ->  {how}")
        left = [v for v in videos if v.id not in used]
        print(f"\nPlan lines: {len(items)} | matched: {len(ordered)} | skipped: {problems} | videos in collection: {len(videos)} | "
              f"in collection but not in plan: {len(left)}")
        for v in left:
            print("  not in plan:", v.title)
        sizes = [sum(1 for d, _ in ordered if d == n) for n in sorted({d for d, _ in ordered})]
        print(f"Days: {len(sizes)} | videos per day: {sizes}")
        if not args.apply:
            print("\nDry run only. Nothing was changed. Add --apply to save.")
            return 0
        members = {m.video_id: m for m in db.scalars(select(VideoMembership).where(VideoMembership.playlist_id == pl.id))}
        pos = 1
        for _, v in ordered:
            members[v.id].position = pos
            pos += 1
        for v in left:  # anything outside the plan goes after it, in its old order
            members[v.id].position = pos
            pos += 1
        pl.recommend_order = "manual"
        pl.daily_target = max(sizes)
        db.commit()
        print(f"\nSaved. Order is now manual, daily target = {pl.daily_target}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
