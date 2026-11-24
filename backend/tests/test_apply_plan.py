"""The study-plan matcher: reads the real plan file and matches titles without inventing anything."""
import sys
from pathlib import Path
from types import SimpleNamespace as V

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import apply_plan as ap  # noqa: E402

PLAN = Path(__file__).resolve().parents[1] / "plans" / "bytebytego_21_day.txt"


def test_plan_file_has_21_days_of_five_lines():
    items = ap.parse_plan(PLAN)
    days = sorted({d for d, _ in items})
    assert days == list(range(1, 22)) and len(items) == 105
    assert all(sum(1 for d, _ in items if d == n) == 5 for n in days)
    assert items[0] == (1, "Big-O Notation in 3 Minutes")


def test_titles_match_despite_suffixes_and_dashes():
    assert ap.norm("Secret To Optimizing SQL Queries – Understand") == ap.norm("Secret To Optimizing SQL Queries - Understand")
    assert ap.norm("Everything You Need to Know About DNS") == ap.norm("Everything You Need to Know About DNS: Crash Course System Design #4")
    assert ap.version_seconds("Top 6 (4:21 version)") == 261 and ap.version_seconds("Top 6") is None


def test_same_title_twice_is_told_apart_by_length_and_each_used_once():
    a = V(id=1, title="Top 6 Most Popular API Architecture Styles", duration_seconds=261)
    b = V(id=2, title="Top 6 Most Popular API Architecture Styles", duration_seconds=74)
    used: set[int] = set()
    first, _ = ap.match("Top 6 Most Popular API Architecture Styles (4:21 version)", [a, b], used)
    used.add(first.id)
    second, _ = ap.match("Top 6 Most Popular API Architecture Styles (1:14 version)", [a, b], used)
    assert (first.id, second.id) == (1, 2)


def test_unknown_titles_are_skipped_not_guessed():
    vids = [V(id=1, title="Big-O Notation in 3 Minutes", duration_seconds=180)]
    assert ap.match("Use this day to revisit any difficult concepts", vids, set())[0] is None
    assert ap.match("Totally different video about cats", vids, set())[0] is None
