"""WebTrac tee-time scraper.

Primary path uses curl_cffi (Chrome TLS impersonation) which bypasses the
site's Cloudflare passive bot check. If that ever gets blocked, an optional
Playwright fallback loads the same pages in a real browser.
"""
from __future__ import annotations

import logging
import random
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from bs4 import BeautifulSoup

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

BASE = settings.webtrac_base_url.rstrip("/")
BOOTSTRAP_URL = f"{BASE}/search.html?display=detail&module=GR"

# (connect, read) timeouts. A tuple makes curl_cffi enforce a hard connect cap
# in addition to the read cap, so a throttled/slow-walling server can't hold a
# single request open for many minutes.
_TIMEOUT = (settings.connect_timeout, settings.request_timeout)

COURSES = {
    1: "Jimmy Clay Golf Course",
    2: "Roy Kizer Golf Course",
    3: "Morris Williams Golf Course",
    4: "Lions Municipal Golf Course",
    5: "Hancock Golf Course",
}

_CSRF_RE = re.compile(r'name="_csrf_token"[^>]*value="([^"]+)"')
_PROXY_PORT_RE = re.compile(r":(\d+)$")

_TRANSPORT_ERRORS: tuple[type[BaseException], ...] | None = None


def _transport_errors() -> tuple[type[BaseException], ...]:
    """curl_cffi failures meaning "this exit is bad", as opposed to "we're banned".

    Resolved lazily because curl_cffi is only imported on first use. Deliberately
    narrower than RequestException so genuine bugs (bad URL, closed session)
    still surface instead of being retried against ten different IPs.
    """
    global _TRANSPORT_ERRORS
    if _TRANSPORT_ERRORS is None:
        from curl_cffi.requests import exceptions as cffi_exc
        _TRANSPORT_ERRORS = (
            cffi_exc.Timeout,
            cffi_exc.ConnectionError,
            cffi_exc.ProxyError,
            cffi_exc.DNSError,
            cffi_exc.SSLError,
        )
    return _TRANSPORT_ERRORS


class _Traffic:
    """Counts the wire bytes a metered proxy actually bills us for.

    `len(response.content)` is the *decompressed* body and overstates the real
    figure roughly threefold, so this sums curl's own request/response sizes.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.requests = 0
        self.bytes = 0

    def record(self, response) -> None:
        wire = sum(
            getattr(response, attr, 0) or 0
            for attr in ("request_size", "upload_size", "header_size", "download_size")
        )
        with self._lock:
            self.requests += 1
            self.bytes += wire

    def snapshot(self) -> tuple[int, int]:
        with self._lock:
            return self.requests, self.bytes

    def status(self) -> dict:
        requests, wire = self.snapshot()
        return {
            "requests": requests,
            "bytes": wire,
            "megabytes": round(wire / 1_048_576, 3),
        }


# Process-wide, since billing is per-egress not per-instance.
traffic = _Traffic()


@dataclass
class Slot:
    course_id: int
    course_name: str
    date: str        # MM/DD/YYYY
    time: str        # e.g. "7:10 am"
    open_slots: int
    # False when the site renders the row but refuses to cart it -- typically a
    # date beyond the booking window. Defaults True so an unrecognized action
    # cell fails open rather than silently muting alerts.
    bookable: bool = True


def _extract_csrf(html: str) -> str | None:
    m = _CSRF_RE.search(html)
    return m.group(1) if m else None


def _course_id_for(name: str) -> int:
    low = name.lower()
    for cid, cname in COURSES.items():
        if cname.lower() in low or low in cname.lower():
            return cid
    return 0


def _header_index(table) -> dict[str, int]:
    """Map lowercased column header text -> cell index."""
    return {
        th.get_text(" ", strip=True).lower(): i
        for i, th in enumerate(table.select("thead th"))
        if th.get_text(" ", strip=True)
    }


def _cell_value(td) -> str:
    """Cell text minus the responsive label span the site injects.

    Each cell renders as `<span class="mobile-column-header">Date</span>08/08/2026`,
    so a naive get_text() would return "Date 08/08/2026".
    """
    parts = []
    for child in td.children:
        classes = child.get("class") or [] if hasattr(child, "get") else []
        if "mobile-column-header" in classes:
            continue
        text = child.get_text(" ", strip=True) if hasattr(child, "get_text") else str(child).strip()
        if text:
            parts.append(text)
    return " ".join(parts).strip()


def _is_bookable(td) -> bool:
    """Whether the Item Action cell offers an add-to-cart link.

    Bookable rows render `class="button success ... cart-button"`; rows outside
    the booking window render `class="button error ..."` with an
    "... is unavailable" aria-label.
    """
    if td is None:
        return True
    link = td.find("a")
    if link is None:
        return True
    classes = " ".join(link.get("class") or []).lower()
    label = (link.get("aria-label") or "").lower()
    if "error" in classes or "unavailable" in label:
        return False
    if "success" in classes or label.startswith("add to cart"):
        return True
    return True


def parse_results(html: str) -> list[Slot]:
    """Parse the WebTrac search results table into Slot objects.

    Reads cells by column header rather than the `data-title` attribute the
    site used to emit, falling back to `data-title` where it still exists.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("#grwebsearch_output_table")
    slots: list[Slot] = []
    if table is None:
        return slots

    columns = _header_index(table)
    rows = table.select("tbody tr")

    for tr in rows:
        tds = tr.find_all("td")

        def cell(title: str) -> str:
            legacy = tr.select_one(f'td[data-title="{title}"]')
            if legacy is not None:
                return legacy.get_text(" ", strip=True)
            idx = columns.get(title.lower())
            if idx is None or idx >= len(tds):
                return ""
            return _cell_value(tds[idx])

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

        action_idx = columns.get("item action")
        action_td = tds[action_idx] if action_idx is not None and action_idx < len(tds) else None

        slots.append(Slot(
            course_id=cid,
            course_name=course or COURSES.get(cid, ""),
            date=date,
            time=time.lower(),
            open_slots=open_slots,
            bookable=_is_bookable(action_td),
        ))

    if rows and not slots:
        # The silent failure mode: a 200 response whose markup we no longer
        # understand looks identical to "no tee times available".
        logger.error(
            "Parsed 0 slots from %d result row(s) - the site's table markup has "
            "likely changed. Headers seen: %s", len(rows), sorted(columns),
        )
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


class _Circuit:
    """Trips on a block and stays open through an exponential backoff.

    Without this, every (date, holes, course) combo re-requests the bootstrap
    page on each 5-minute cycle -- roughly 10k rejected requests a day, which
    only hardens the WAF ban. Once tripped, no request leaves the process until
    the backoff expires.
    """

    def __init__(self) -> None:
        self.consecutive_blocks = 0
        self.blocked_since: datetime | None = None
        self.open_until: datetime | None = None
        self.last_reason: str = ""

    def is_open(self, now: datetime | None = None) -> bool:
        if self.open_until is None:
            return False
        return (now or datetime.now(timezone.utc)) < self.open_until

    def backoff(self) -> timedelta:
        minutes = settings.block_backoff_start_minutes * (2 ** max(0, self.consecutive_blocks - 1))
        return timedelta(minutes=min(minutes, settings.block_backoff_max_minutes))

    def record_block(self, reason: str) -> None:
        now = datetime.now(timezone.utc)
        self.consecutive_blocks += 1
        self.last_reason = reason
        if self.blocked_since is None:
            self.blocked_since = now
        self.open_until = now + self.backoff()
        logger.warning(
            "Scraper blocked (%s); backing off until %s (consecutive=%d).",
            reason, self.open_until.isoformat(timespec="seconds"), self.consecutive_blocks,
        )

    def record_success(self) -> None:
        if self.consecutive_blocks:
            logger.info("Scraper recovered after %d consecutive block(s).", self.consecutive_blocks)
        self.consecutive_blocks = 0
        self.blocked_since = None
        self.open_until = None
        self.last_reason = ""

    def blocked_for(self, now: datetime | None = None) -> timedelta:
        if self.blocked_since is None:
            return timedelta(0)
        return (now or datetime.now(timezone.utc)) - self.blocked_since

    def status(self) -> dict:
        return {
            "blocked": self.blocked_since is not None,
            "blocked_since": self.blocked_since.isoformat() if self.blocked_since else None,
            "open_until": self.open_until.isoformat() if self.open_until else None,
            "consecutive_blocks": self.consecutive_blocks,
            "reason": self.last_reason,
            "using_proxy": bool(settings.scraper_proxy),
            "exit_port": _shared_scraper._port if _shared_scraper else None,
        }


# Process-wide: the ban applies to the host, not to any one scraper instance.
circuit = _Circuit()

_shared_scraper: "TeeTimeScraper | None" = None
_scraper_lock = threading.Lock()


def get_scraper() -> "TeeTimeScraper":
    """Return the process-wide scraper.

    Scans are serialized, so one long-lived instance is safe and lets the HTTP
    session, cookies, and CSRF token survive between cycles -- which reuses the
    TCP/TLS connection and avoids re-bootstrapping on every scan.
    """
    global _shared_scraper
    with _scraper_lock:
        if _shared_scraper is None:
            _shared_scraper = TeeTimeScraper()
        return _shared_scraper


class TeeTimeScraper:
    """Fetch tee-time availability for a given date, one course at a time.

    A single instance reuses one HTTP session and CSRF token across many
    fetches, so scanning every course/date in a cycle stays cheap.
    """

    def __init__(self):
        self._session = None
        self._token: str | None = None
        self._token_at: datetime | None = None
        self._port: int | None = None

    def _proxy_url(self) -> str | None:
        """Current proxy URL with the sticky port swapped in."""
        base = settings.scraper_proxy
        if not base:
            return None
        if self._port is None:
            self._port = random.randint(settings.proxy_port_min, settings.proxy_port_max)
        return _PROXY_PORT_RE.sub(f":{self._port}", base)

    def _rotate_ip(self) -> None:
        """Move to a different sticky port, i.e. a different residential IP."""
        self._port = random.randint(settings.proxy_port_min, settings.proxy_port_max)
        self.reset(keep_port=True)

    def _ensure_session(self):
        if self._session is None:
            from curl_cffi import requests as cffi
            kwargs = {"impersonate": "chrome"}
            proxy = self._proxy_url()
            if proxy:
                kwargs["proxy"] = proxy
            self._session = cffi.Session(**kwargs)
        return self._session

    def reset(self, keep_port: bool = False) -> None:
        """Drop the session and token so the next fetch starts clean."""
        if self._session is not None:
            try:
                self._session.close()
            except Exception:  # noqa: BLE001
                pass
        self._session = None
        self._token = None
        self._token_at = None
        if not keep_port:
            self._port = None

    def _token_expired(self) -> bool:
        if self._token_at is None:
            return True
        age = datetime.now(timezone.utc) - self._token_at
        return age >= timedelta(minutes=settings.csrf_token_ttl_minutes)

    def _ensure_token(self, force: bool = False) -> str:
        if self._token and not force and not self._token_expired():
            return self._token
        session = self._ensure_session()
        boot = session.get(BOOTSTRAP_URL, timeout=_TIMEOUT)
        traffic.record(boot)
        if boot.status_code != 200 or "Attention Required" in boot.text:
            raise CloudflareBlocked(f"bootstrap status {boot.status_code}")
        token = _extract_csrf(boot.text)
        if not token:
            raise CloudflareBlocked("no csrf token in bootstrap page")
        self._token = token
        self._token_at = datetime.now(timezone.utc)
        return token

    def fetch(self, begindate: str, holes: int = 18, course_id: int | None = None) -> list[Slot]:
        """Return available slots for `begindate` (MM/DD/YYYY) and one course.

        Pass `course_id` (1-5); leaving it None uses the all-courses search,
        which the site truncates and should be avoided for scanning.

        Raises CloudflareBlocked without touching the network while the circuit
        breaker is open.
        """
        if circuit.is_open():
            raise CloudflareBlocked(
                f"circuit open until {circuit.open_until.isoformat(timespec='seconds')} "
                f"({circuit.last_reason})"
            )

        # About half of residential exit IPs are already WAF-blocked, so treat a
        # block as "bad IP" and hop sticky ports rather than failing the scan.
        # Timeouts get a separate, much smaller budget: they mean the exit is
        # slow or dead rather than banned, and each one burns the full read
        # timeout, so retrying ten of them would blow the scan budget.
        using_proxy = bool(settings.scraper_proxy)
        block_attempts = settings.proxy_max_ip_attempts if using_proxy else 1
        timeout_attempts = settings.proxy_max_timeout_attempts if using_proxy else 1
        blocks = 0
        timeouts = 0
        last_block: CloudflareBlocked | None = None

        while True:
            try:
                slots = self._fetch_curl(begindate, holes, course_id)
            except CloudflareBlocked as e:
                blocks += 1
                last_block = e
                if blocks >= block_attempts:
                    break
                logger.debug("Exit IP blocked (%s); rotating (block %d/%d).",
                             e, blocks, block_attempts)
                self._rotate_ip()
                continue
            except _transport_errors() as e:
                # Never trips the breaker: an unreachable exit says nothing about
                # whether the site is banning us. But we must still abandon the
                # IP, or every remaining fetch this cycle stalls behind it.
                timeouts += 1
                self._rotate_ip()
                if timeouts >= timeout_attempts:
                    logger.warning(
                        "Exit IP unreachable %dx for %s (%s); rotated away, skipping "
                        "this fetch until the next cycle.", timeouts, begindate, e,
                    )
                    raise
                logger.info("Exit IP unreachable (%s); rotating and retrying %s.", e, begindate)
                continue
            if blocks or timeouts:
                logger.info(
                    "Found a working exit IP for %s after %d block(s) and %d timeout(s).",
                    begindate, blocks, timeouts,
                )
            circuit.record_success()
            return slots

        # Every IP we tried was refused: fall back to Playwright if enabled,
        # otherwise trip the breaker so we stop hammering.
        self.reset()
        if not settings.use_playwright_fallback:
            circuit.record_block(str(last_block))
            logger.error(
                "Blocked on %d exit IP(s) (%s). If SCRAPER_PROXY is unset, the host's own "
                "IP is banned - set a residential/ISP proxy. See DEPLOY.md.",
                blocks, last_block,
            )
            raise last_block
        logger.warning("curl_cffi blocked; trying Playwright fallback for %s", begindate)
        try:
            slots = self._fetch_playwright(begindate, holes, course_id)
        except ImportError as imp:
            circuit.record_block(str(last_block))
            raise RuntimeError(
                "USE_PLAYWRIGHT_FALLBACK is on but playwright is not installed. "
                "Add playwright to requirements and run `playwright install chromium`."
            ) from imp
        except Exception:
            circuit.record_block(str(last_block))
            raise
        circuit.record_success()
        return slots

    def _fetch_curl(self, begindate: str, holes: int, course_id: int | None) -> list[Slot]:
        session = self._ensure_session()
        token = self._ensure_token()
        url = _search_url(token, begindate, holes=holes, course_id=course_id)
        r = session.get(url, headers={"referer": BOOTSTRAP_URL}, timeout=_TIMEOUT)
        traffic.record(r)
        if r.status_code != 200 or "Attention Required" in r.text:
            # Token may be stale/expired; refresh once and retry.
            token = self._ensure_token(force=True)
            url = _search_url(token, begindate, holes=holes, course_id=course_id)
            r = session.get(url, headers={"referer": BOOTSTRAP_URL}, timeout=_TIMEOUT)
            traffic.record(r)
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
