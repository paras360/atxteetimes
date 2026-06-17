"""The 5-minute tee-time scan job."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from pytz import timezone

from ..config import get_settings
from ..db import SessionLocal
from ..models import FoundSlot, Watch
from .email import get_email_service
from .scraper import COURSES, TeeTimeScraper, Slot

ALL_COURSE_IDS = sorted(COURSES.keys())

logger = logging.getLogger(__name__)
settings = get_settings()

WEEKDAY = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
_TZ = timezone(settings.timezone)

# Guards against overlapping runs if a scan ever outlives its interval.
_scan_lock = asyncio.Lock()

# Last scan summary, surfaced to the UI for scanner-health display.
_last_scan: dict = {
    "at": None, "ran": False, "in_window": False, "message": "No scan yet.",
    "dates_scanned": [], "total_slots": 0, "new_matches": 0, "scoped": False,
}


def get_last_scan() -> dict:
    return dict(_last_scan)


def _now() -> datetime:
    return datetime.now(_TZ)


def in_scan_window(now: datetime) -> bool:
    """Active from scan_start_weekday@scan_start_hour through scan_end_weekday (inclusive).

    Default: Tuesday 06:00 -> Sunday 23:59. Monday is off.
    """
    wd = now.weekday()
    start = settings.scan_start_weekday
    end = settings.scan_end_weekday
    if wd < start or wd > end:
        return False
    if wd == start and now.hour < settings.scan_start_hour:
        return False
    return True


def _to_minutes(time_str: str) -> int | None:
    """'7:10 am' or '07:10' -> minutes since midnight."""
    s = time_str.strip().lower()
    try:
        if "am" in s or "pm" in s:
            ampm = "am" if "am" in s else "pm"
            hm = s.replace("am", "").replace("pm", "").strip()
            h, m = (hm.split(":") + ["0"])[:2]
            h, m = int(h), int(m)
            if ampm == "pm" and h != 12:
                h += 12
            if ampm == "am" and h == 12:
                h = 0
            return h * 60 + m
        h, m = s.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def _within(window_start: str, window_end: str, slot_time: str) -> bool:
    start = _to_minutes(window_start)
    end = _to_minutes(window_end)
    t = _to_minutes(slot_time)
    if start is None or end is None or t is None:
        return False
    return start <= t <= end


def watch_course_ids(watch: Watch) -> list[int]:
    if watch.course_ids == "all":
        return ALL_COURSE_IDS
    return [int(c) for c in watch.course_ids.split(",") if c.strip()]


def upcoming_dates(now: datetime, days: set[str]) -> dict[str, str]:
    """Map MM/DD/YYYY -> weekday code for the next occurrence of each day."""
    out: dict[str, str] = {}
    for d in days:
        wd = WEEKDAY.get(d)
        if wd is None:
            continue
        delta = (wd - now.weekday()) % 7
        target = now + timedelta(days=delta)
        out[target.strftime("%m/%d/%Y")] = d
    return out


def _collect_pending(db, watch: Watch, matches: list[Slot]) -> int:
    """Record matches and return the number of brand-new slots seen.

    De-dup is keyed on (watch, course, date, time). A slot already recorded and
    notified is skipped so we never resend the same alert. Pending email rows
    are retried separately from the database after scanning, so retries are not
    dependent on WebTrac returning the same slot again.
    """
    new_count = 0
    for slot in matches:
        existing = (
            db.query(FoundSlot)
            .filter_by(watch_id=watch.id, course_id=slot.course_id, date=slot.date, time=slot.time)
            .first()
        )
        if existing is None:
            record = FoundSlot(
                watch_id=watch.id, course_id=slot.course_id, course_name=slot.course_name,
                date=slot.date, time=slot.time, open_slots=slot.open_slots,
            )
            db.add(record)
            new_count += 1
        else:
            existing.open_slots = slot.open_slots
    db.commit()
    return new_count


def _send_digest(db, email, watch: Watch, pending: list[FoundSlot]) -> bool:
    """Send a single digest email for all pending slots on a watch.

    Marks rows notified only if the email actually goes out, so a failed send is
    retried in a later digest rather than lost.
    """
    if not pending:
        return False
    for r in pending:
        db.refresh(r)
    pending.sort(key=lambda r: (r.date, _to_minutes(r.time) or 0))
    sent = email.send_slots_digest_email(
        to_email=watch.user.email, user_name=watch.user.name, watch=watch, slots=pending,
    )
    if sent:
        for r in pending:
            r.notified = True
        db.commit()
        logger.info("Digest sent for watch %s: %d slot(s)", watch.id, len(pending))
        return True
    else:
        logger.warning(
            "Watch %s has %d pending slot(s) but email failed; will retry later.",
            watch.id, len(pending),
        )
        return False


def _send_pending_digests(db, email, watches: list[Watch]) -> int:
    """Retry all unnotified slots for each active watch.

    This intentionally reads from the database after the scrape/match phase so
    existing `notified=False` rows still get emailed if a previous Resend outage
    or sandbox error is fixed while WebTrac is flaky or blocked.
    """
    sent_slots = 0
    for watch in watches:
        pending = (
            db.query(FoundSlot)
            .filter(FoundSlot.watch_id == watch.id, FoundSlot.notified.is_(False))
            .all()
        )
        if _send_digest(db, email, watch, pending):
            sent_slots += len(pending)
    return sent_slots


def scan(force: bool = False, user_id: Optional[int] = None) -> dict:
    """Run one scan cycle. Returns a summary dict. Safe to call off the event loop.

    `user_id` scopes the scan to a single user's watches (used by manual "Scan now").
    """
    now = _now()
    if not force and not in_scan_window(now):
        return {
            "ran": False, "in_window": False, "dates_scanned": [],
            "total_slots": 0, "new_matches": 0,
            "message": "Outside scan window (Tue 06:00 - Sun 23:59 CT).",
        }

    db = SessionLocal()
    email = get_email_service()
    new_matches = 0
    total_slots = 0
    dates_scanned: list[str] = []
    try:
        query = db.query(Watch).filter(Watch.active.is_(True))
        if user_id is not None:
            query = query.filter(Watch.user_id == user_id)
        watches = query.all()
        if not watches:
            return {
                "ran": True, "in_window": True, "dates_scanned": [],
                "total_slots": 0, "new_matches": 0,
                "message": "No active watches.",
            }

        all_days = {d for w in watches for d in w.target_days.split(",")}
        date_map = upcoming_dates(now, all_days)

        # The all-courses search is truncated by the site, so we fetch one course
        # at a time. Build the exact set of (date, holes, course) tuples needed.
        needed: set[tuple[str, int, int]] = set()
        for w in watches:
            wdays = set(w.target_days.split(","))
            for dt, day_code in date_map.items():
                if day_code not in wdays:
                    continue
                for cid in watch_course_ids(w):
                    needed.add((dt, w.num_holes, cid))

        scraper = TeeTimeScraper()
        results: dict[tuple[str, int, int], list[Slot]] = {}
        for dt, holes, cid in needed:
            try:
                slots = scraper.fetch(dt, holes=holes, course_id=cid)
                results[(dt, holes, cid)] = slots
                total_slots += len(slots)
            except Exception as e:  # noqa: BLE001
                logger.error("Scan fetch failed for %s (%d holes, course %s): %s", dt, holes, cid, e)
                results[(dt, holes, cid)] = []
        dates_scanned = sorted({dt for dt, _, _ in needed})

        for w in watches:
            wdays = set(w.target_days.split(","))
            matches: list[Slot] = []
            for dt, day_code in date_map.items():
                if day_code not in wdays:
                    continue
                for cid in watch_course_ids(w):
                    for s in results.get((dt, w.num_holes, cid), []):
                        if s.open_slots < w.num_players:
                            continue
                        if not _within(w.window_start, w.window_end, s.time):
                            continue
                        matches.append(s)

            new_count = _collect_pending(db, w, matches)
            new_matches += new_count

        pending_alerts_sent = _send_pending_digests(db, email, watches)

        return {
            "ran": True, "in_window": True, "dates_scanned": dates_scanned,
            "total_slots": total_slots, "new_matches": new_matches,
            "message": (
                f"Scanned {len(dates_scanned)} date(s); {new_matches} new match(es); "
                f"{pending_alerts_sent} pending alert(s) sent."
            ),
        }
    finally:
        db.close()


async def run_scan(force: bool = False, user_id: Optional[int] = None) -> dict:
    """Async entrypoint -- serializes runs and offloads the blocking scan to a thread.

    The scheduler calls this with no args (full, window-gated scan). The manual
    "Scan now" endpoint calls it with force=True and a user_id to scope results.
    """
    async with _scan_lock:
        try:
            result = await asyncio.to_thread(scan, force, user_id)
            if result["ran"]:
                logger.info("Scan: %s", result["message"])
        except Exception as e:  # noqa: BLE001
            logger.exception("Scan job crashed: %s", e)
            result = {
                "ran": False, "in_window": False, "dates_scanned": [],
                "total_slots": 0, "new_matches": 0, "message": f"Scan error: {e}",
            }
        _last_scan.update({**result, "at": _now().isoformat(), "scoped": user_id is not None})
        return result
