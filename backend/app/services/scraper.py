"""WebTrac tee-time scraper.

Primary path uses curl_cffi (Chrome TLS impersonation) which bypasses the
site's Cloudflare passive bot check. If that ever gets blocked, an optional
Playwright fallback loads the same pages in a real browser.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import quote

from bs4 import BeautifulSoup

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

BASE = settings.webtrac_base_url.rstrip("/")
BOOTSTRAP_URL = f"{BASE}/search.html?display=detail&module=GR"

COURSES = {
    1: "Jimmy Clay Golf Course",
    2: "Roy Kizer Golf Course",
    3: "Morris Williams Golf Course",
    4: "Lions Municipal Golf Course",
    5: "Hancock Golf Course",
}

_CSRF_RE = re.compile(r'name="_csrf_token"[^>]*value="([^"]+)"')


@dataclass
class Slot:
    course_id: int
    course_name: str
    date: str        # MM/DD/YYYY
    time: str        # e.g. "7:10 am"
    open_slots: int


def _extract_csrf(html: str) -> str | None:
    m = _CSRF_RE.search(html)
    return m.group(1) if m else None


def _course_id_for(name: str) -> int:
    low = name.lower()
    for cid, cname in COURSES.items():
        if cname.lower() in low or low in cname.lower():
            return cid
    return 0


def parse_results(html: str) -> list[Slot]:
    """Parse the WebTrac search results table into Slot objects."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("#grwebsearch_output_table")
    slots: list[Slot] = []
    if table is None:
        return slots

    for tr in table.select("tbody tr"):
        def cell(title: str) -> str:
            el = tr.select_one(f'td[data-title="{title}"]')
            return el.get_text(" ", strip=True) if el else ""

        course = cell("Course")
        date = cell("Date")
        time = cell("Time")
        raw_open = cell("Open Slots")
        try:
            open_slots = int(re.sub(r"\D", "", raw_open) or 0)
        except ValueError:
            open_slots = 0

        if not (date and time):
            continue

        cid = _course_id_for(course)
        if cid == 0:
            # Unknown course name; a slot with course_id=0 would produce a
            # broken booking link and fail watch matching.
            logger.warning("Skipping result row with unrecognized course: %r", course)
            continue
        slots.append(Slot(
            course_id=cid,
            course_name=course or COURSES.get(cid, ""),
            date=date,
            time=time.lower(),
            open_slots=open_slots,
        ))
    return slots


def _search_url(token: str, begindate: str, begintime: str = "6:00 am",
                players: int = 1, holes: int = 18, course_id: int | None = None) -> str:
    # IMPORTANT: an empty secondarycode (all courses) returns a TRUNCATED list
    # (roughly the next slot per course). Always search one course at a time to
    # get every available tee time.
    secondarycode = "" if course_id is None else str(course_id)
    return (
        f"{BASE}/search.html?Action=Start&SubAction=&_csrf_token={token}"
        f"&secondarycode={secondarycode}&begintime={quote(begintime)}&begindate={quote(begindate)}"
        f"&numberofplayers={players}&numberofholes={holes}&module=GR"
        f"&multiselectlist_value=&grwebsearch_buttonsearch=yes"
    )


class CloudflareBlocked(RuntimeError):
    pass


class TeeTimeScraper:
    """Fetch tee-time availability for a given date, one course at a time.

    A single instance reuses one HTTP session and CSRF token across many
    fetches, so scanning every course/date in a cycle stays cheap.
    """

    def __init__(self):
        self._session = None
        self._token: str | None = None

    def _ensure_session(self):
        if self._session is None:
            from curl_cffi import requests as cffi
            self._session = cffi.Session(impersonate="chrome")
        return self._session

    def _ensure_token(self, force: bool = False) -> str:
        if self._token and not force:
            return self._token
        session = self._ensure_session()
        boot = session.get(BOOTSTRAP_URL, timeout=settings.request_timeout)
        if boot.status_code != 200 or "Attention Required" in boot.text:
            raise CloudflareBlocked(f"bootstrap status {boot.status_code}")
        token = _extract_csrf(boot.text)
        if not token:
            raise CloudflareBlocked("no csrf token in bootstrap page")
        self._token = token
        return token

    def fetch(self, begindate: str, holes: int = 18, course_id: int | None = None) -> list[Slot]:
        """Return available slots for `begindate` (MM/DD/YYYY) and one course.

        Pass `course_id` (1-5); leaving it None uses the all-courses search,
        which the site truncates and should be avoided for scanning.
        """
        try:
            return self._fetch_curl(begindate, holes, course_id)
        except CloudflareBlocked as e:
            if not settings.use_playwright_fallback:
                logger.error(
                    "Scrape blocked by Cloudflare and Playwright fallback is disabled (%s). "
                    "Set USE_PLAYWRIGHT_FALLBACK=true and install playwright, or use a "
                    "residential proxy. See DEPLOY.md.", e,
                )
                raise
            logger.warning("curl_cffi blocked; trying Playwright fallback for %s", begindate)
            try:
                return self._fetch_playwright(begindate, holes, course_id)
            except ImportError as imp:
                raise RuntimeError(
                    "USE_PLAYWRIGHT_FALLBACK is on but playwright is not installed. "
                    "Add playwright to requirements and run `playwright install chromium`."
                ) from imp

    def _fetch_curl(self, begindate: str, holes: int, course_id: int | None) -> list[Slot]:
        session = self._ensure_session()
        token = self._ensure_token()
        url = _search_url(token, begindate, holes=holes, course_id=course_id)
        r = session.get(url, headers={"referer": BOOTSTRAP_URL}, timeout=settings.request_timeout)
        if r.status_code != 200 or "Attention Required" in r.text:
            # Token may be stale/expired; refresh once and retry.
            token = self._ensure_token(force=True)
            url = _search_url(token, begindate, holes=holes, course_id=course_id)
            r = session.get(url, headers={"referer": BOOTSTRAP_URL}, timeout=settings.request_timeout)
            if r.status_code != 200 or "Attention Required" in r.text:
                raise CloudflareBlocked(f"search status {r.status_code}")
        return parse_results(r.text)

    def _fetch_playwright(self, begindate: str, holes: int, course_id: int | None) -> list[Slot]:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page()
            try:
                page.goto(BOOTSTRAP_URL, timeout=settings.request_timeout * 1000)
                html = page.content()
                token = _extract_csrf(html)
                if not token:
                    raise RuntimeError("no csrf token (playwright)")
                page.goto(_search_url(token, begindate, holes=holes, course_id=course_id),
                          timeout=settings.request_timeout * 1000)
                page.wait_for_load_state("networkidle")
                return parse_results(page.content())
            finally:
                browser.close()
