"""Best focus hours and where each kind of study fits.

You give one window per weekday ("06:00-09:00", or nothing for a day). The planner then tells you:
  * a HARD roadmap topic: do it inside that day's focus window;
  * a LIGHT roadmap topic or a video: fine for a walk, the evening or any spare time.
Nothing here moves or schedules anything; it only words a hint on the item, so a day without a window just gets a reminder to set one."""
import re

DAYS = 7
_WINDOW = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)-([01]\d|2[0-3]):([0-5]\d)$")


def valid_window(w: str) -> bool:
    """HH:MM-HH:MM with the end after the start. An empty string means no window that day."""
    m = _WINDOW.match(w)
    return bool(m) and (int(m[1]), int(m[2])) < (int(m[3]), int(m[4]))


def decode(raw: str | None) -> list[str] | None:
    """The 7 windows Monday..Sunday ('' = none that day), or None when nothing is set or the stored value is damaged."""
    if not raw:
        return None
    parts = raw.split(",")
    if len(parts) != DAYS or any(p and not valid_window(p) for p in parts):
        return None
    return parts if any(parts) else None


def encode(values: list[str] | None) -> str | None:
    return None if values is None or not any(values) else ",".join(values)


def pretty(window: str) -> str:
    return window.replace("-", "–")


def hint(kind: str, difficulty: str | None, status: str, window: str | None, has_any_window: bool) -> str | None:
    """The one-line advice for an open item, or None when there is nothing to say."""
    if status not in ("pending", "overdue"):
        return None
    if kind == "topic" and difficulty == "hard":
        if window:
            return f"Hard topic: do it in your focus hours, {pretty(window)}"
        return "Hard topic: no focus hours set for this day" if has_any_window else "Hard topic: set your focus hours in Settings to plan it well"
    if kind == "video" or (kind == "topic" and difficulty == "light"):
        return "Light: fine for a walk, the evening or spare time"
    return None
