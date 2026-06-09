"""Build deep links into the WebTrac golf search.

These links land the user on the Golf search page with the course, date, time,
party size, and hole count pre-filled so they can book in one or two clicks. We
intentionally omit `Action=Start` because that requires a session-bound CSRF
token; instead the form is pre-populated and the user presses Search.
"""
from urllib.parse import quote

from ..config import get_settings

settings = get_settings()
_BASE = settings.webtrac_base_url.rstrip("/")


def build_search_url(
    course_id: int | None = None,
    date: str | None = None,
    time: str | None = None,
    players: int = 4,
    holes: int = 18,
) -> str:
    """Return a prefilled WebTrac Golf search URL.

    `date` is MM/DD/YYYY and `time` is like "7:10 am" (as parsed from results).
    """
    params = [
        "display=detail",
        "module=GR",
        f"secondarycode={course_id or ''}",
        f"numberofplayers={players}",
        f"numberofholes={holes}",
    ]
    if date:
        params.append(f"begindate={quote(date)}")
    if time:
        params.append(f"begintime={quote(time)}")
    return f"{_BASE}/search.html?" + "&".join(params)
