"""The 5-minute tee-time scan job."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Optional

from pytz import timezone

from ..config import get_settings
from ..db import SessionLocal
from ..models import FoundSlot, User, Watch
from .email import get_email_service
from .scraper import COURSES, CloudflareBlocked, Slot, circuit, get_scraper, traffic

ALL_COURSE_IDS = sorted(COURSES.keys())

logger = logging.getLogger(__name__)
settings = get_settings()

WEEKDAY = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
_TZ = timezone(settings.timezone)
ALERT_FRESHNESS = timedelta(minutes=60)
# A tee time must be at least this far in the future to be worth alerting on; a
# slot starting in a couple of minutes is effectively unbookable.
SLOT_BOOKING_LEAD = timedelta(minutes=15)
QUIET_WINDOW_START_HOUR = 14  # Sunday 2pm CT through end of Monday CT.

# Guards against overlapping runs if a scan ever outlives its interval.
_scan_lock = asyncio.Lock()

# Cooldown anchor for the "scraper is blocked" warning email.
_last_blocked_alert_at: datetime | None = None

# date (MM/DD/YYYY) -> when it's worth re-fetching. Dates outside the site's
# booking window render a full page of uncartable rows, so polling them every
# cycle just burns proxy bandwidth.
_unbookable_until: dict[str, datetime] = {}

# Last scan summary, surfaced to the UI for scanner-health display.
_last_scan: dict = {
    "at": None, "ran": False, "in_window": False, "message": "No scan yet.",
    "dates_scanned": [], "total_slots": 0, "new_matches": 0, "scoped": False,
    "duration_seconds": None, "requests": 0, "bytes": 0,
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


def _in_alert_quiet_window(now: datetime) -> bool:
    """Suppress emails from Sunday 2pm CT through end of Monday CT."""
    local_now = now.astimezone(_TZ)
    weekday = local_now.weekday()
    return weekday == WEEKDAY["mon"] or (
        weekday == WEEKDAY["sun"] and local_now.hour >= QUIET_WINDOW_START_HOUR
    )


def _found_at_utc(found_at: datetime) -> datetime:
    """Treat SQLite's naive CURRENT_TIMESTAMP values as UTC."""
    if found_at.tzinfo is None:
        return found_at.replace(tzinfo=dt_timezone.utc)
    return found_at.astimezone(dt_timezone.utc)


def _is_fresh_alert_candidate(slot: FoundSlot, now: datetime) -> bool:
    cutoff = now.astimezone(dt_timezone.utc) - ALERT_FRESHNESS
    return _found_at_utc(slot.found_at) >= cutoff


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


def _slot_datetime(date_str: str, time_str: str) -> datetime | None:
    """Combine 'MM/DD/YYYY' + '6:10 am' into a timezone-aware CT datetime."""
    minutes = _to_minutes(time_str)
    if minutes is None:
        return None
    try:
        day = datetime.strptime(date_str, "%m/%d/%Y")
    except (ValueError, TypeError):
        return None
    naive = day.replace(hour=minutes // 60, minute=minutes % 60)
    return _TZ.localize(naive)


def _is_future_slot(slot: Slot, now: datetime) -> bool:
    """True only if the tee time is still ahead of `now` (plus a booking lead).

    Without this, a morning slot that frees up later in the day (e.g. a 6:10 am
    cancellation surfacing at 10 am) would be alerted even though it has already
    passed.
    """
    slot_dt = _slot_datetime(slot.date, slot.time)
    if slot_dt is None:
        return False
    return slot_dt >= now.astimezone(_TZ) + SLOT_BOOKING_LEAD


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


def _dedupe_slots(pending: list[FoundSlot]) -> tuple[list[FoundSlot], list[FoundSlot]]:
    """Split pending rows into the ones to show and the duplicates to suppress.

    Two overlapping watches each record their own row for the same tee time,
    which previously sent the user one near-identical email per watch. The
    duplicates are returned so the caller can still mark them notified; leaving
    them pending would just re-send them on the next cycle.
    """
    seen: set[tuple[int, str, str]] = set()
    unique: list[FoundSlot] = []
    duplicates: list[FoundSlot] = []
    for slot in pending:
        key = (slot.course_id, slot.date, slot.time)
        if key in seen:
            duplicates.append(slot)
        else:
            seen.add(key)
            unique.append(slot)
    return unique, duplicates


def _contributing_watches(watches: list[Watch], slots: list[FoundSlot]) -> list[Watch]:
    """The watches that actually produced `slots`, in first-seen order."""
    by_id = {w.id: w for w in watches}
    out: list[Watch] = []
    for slot in slots:
        watch = by_id.get(slot.watch_id)
        if watch is not None and watch not in out:
            out.append(watch)
    return out


def _send_digest(db, email, watches: list[Watch], slots: list[FoundSlot],
                 duplicates: list[FoundSlot]) -> bool:
    """Send one digest email covering every pending slot for a single user.

    Marks rows notified only if the email actually goes out, so a failed send is
    retried in a later digest rather than lost.
    """
    if not slots:
        return False
    for r in slots + duplicates:
        db.refresh(r)
    slots.sort(key=lambda r: (r.date, _to_minutes(r.time) or 0))
    user = watches[0].user
    sent = email.send_slots_digest_email(
        to_email=user.email, user_name=user.name,
        watches=_contributing_watches(watches, slots), slots=slots,
    )
    if sent:
        for r in slots + duplicates:
            r.notified = True
        db.commit()
        logger.info("Digest sent to %s: %d slot(s).", user.email, len(slots))
        return True
    logger.warning(
        "User %s has %d pending slot(s) but email failed; will retry later.",
        user.email, len(slots),
    )
    return False


def _send_pending_digests(db, email, watches: list[Watch], now: datetime,
                          force: bool = False) -> int:
    """Retry fresh, unnotified slots, sending at most one email per user.

    Grouping by user rather than by watch is what keeps overlapping watches from
    producing duplicate emails for the same tee time. Opportunity history remains
    visible in the dashboard, but email alert candidates are intentionally
    stricter: no quiet-window emails and no stale backlog emails after the retry
    freshness window has passed. A forced/manual "Scan now" bypasses the quiet
    window so the user always gets the email.
    """
    if not force and _in_alert_quiet_window(now):
        logger.info("Alert quiet window active; skipping pending digest emails.")
        return 0

    by_user: dict[int, list[Watch]] = defaultdict(list)
    for watch in watches:
        by_user[watch.user_id].append(watch)

    sent_slots = 0
    for user_id, user_watches in by_user.items():
        pending = (
            db.query(FoundSlot)
            .filter(
                FoundSlot.watch_id.in_([w.id for w in user_watches]),
                FoundSlot.notified.is_(False),
            )
            .all()
        )
        eligible = [slot for slot in pending if _is_fresh_alert_candidate(slot, now)]
        stale = len(pending) - len(eligible)
        if stale:
            logger.info(
                "User %s has %d stale pending slot(s); keeping visible but not emailing.",
                user_id, stale,
            )
        if not eligible:
            continue

        unique, duplicates = _dedupe_slots(eligible)
        if duplicates:
            logger.info(
                "Collapsed %d duplicate slot(s) from overlapping watches for user %s.",
                len(duplicates), user_id,
            )
        if _send_digest(db, email, user_watches, unique, duplicates):
            sent_slots += len(unique)
    return sent_slots


def _maybe_send_blocked_alert(db, email) -> bool:
    """Warn account owners once the scraper has been blocked for a while.

    Rate-limited by `blocked_alert_cooldown_hours` so a multi-day outage sends a
    periodic nudge rather than one email every five minutes.
    """
    global _last_blocked_alert_at
    if not settings.send_blocked_alerts:
        return False

    now_utc = datetime.now(dt_timezone.utc)
    blocked_for = circuit.blocked_for(now_utc)
    if blocked_for < timedelta(minutes=settings.blocked_alert_after_minutes):
        return False
    if _last_blocked_alert_at is not None:
        cooldown = timedelta(hours=settings.blocked_alert_cooldown_hours)
        if now_utc - _last_blocked_alert_at < cooldown:
            return False

    recipients = (
        db.query(User)
        .join(Watch, Watch.user_id == User.id)
        .filter(Watch.active.is_(True))
        .distinct()
        .all()
    )
    sent = 0
    for user in recipients:
        if email.send_scraper_blocked_email(
            to_email=user.email, user_name=user.name,
            blocked_for=blocked_for, reason=circuit.last_reason,
        ):
            sent += 1
    if sent:
        _last_blocked_alert_at = now_utc
        logger.warning("Sent scraper-blocked alert to %d recipient(s).", sent)
    return bool(sent)


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

    started = time.monotonic()
    requests_before, bytes_before = traffic.snapshot()
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

        scraper = get_scraper()
        results: dict[tuple[str, int, int], list[Slot]] = {}
        deadline = time.monotonic() + settings.scan_budget_seconds
        budget_hit = False
        blocked = False
        throttled_dates = {
            dt for (dt, _, _) in needed
            if _unbookable_until.get(dt) and now < _unbookable_until[dt]
        }
        if throttled_dates:
            logger.info(
                "Skipping %d date(s) outside the booking window this cycle: %s",
                len(throttled_dates), ", ".join(sorted(throttled_dates)),
            )
        for dt, holes, cid in sorted(needed):
            if dt in throttled_dates:
                continue
            if time.monotonic() >= deadline:
                budget_hit = True
                logger.warning(
                    "Scan budget of %ds exceeded; skipping remaining %d fetch(es) this cycle.",
                    settings.scan_budget_seconds,
                    len(needed) - len(results),
                )
                break
            try:
                slots = scraper.fetch(dt, holes=holes, course_id=cid)
                results[(dt, holes, cid)] = slots
                total_slots += len(slots)
            except CloudflareBlocked as e:
                # One block means the whole host is blocked; retrying the other
                # combos would just pile requests onto the WAF.
                blocked = True
                logger.error("Scan aborted - scraper blocked (%s).", e)
                break
            except Exception as e:  # noqa: BLE001
                logger.error("Scan fetch failed for %s (%d holes, course %s): %s", dt, holes, cid, e)
                results[(dt, holes, cid)] = []
        # Only count dates we actually fetched, so the UI reflects real coverage.
        dates_scanned = sorted({dt for (dt, _, _) in results})

        # A date that returned rows but nothing cartable is outside the booking
        # window; damp it down until it's worth another look.
        cooldown = timedelta(minutes=settings.unbookable_recheck_minutes)
        for dt in dates_scanned:
            day_slots = [s for (d, _, _), v in results.items() if d == dt for s in v]
            if not day_slots:
                continue
            if any(s.bookable for s in day_slots):
                _unbookable_until.pop(dt, None)
            else:
                _unbookable_until[dt] = now + cooldown
                logger.info(
                    "%s has %d slot(s) but none bookable yet; rechecking after %s.",
                    dt, len(day_slots), (now + cooldown).strftime("%H:%M"),
                )

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
                        if settings.require_bookable and not s.bookable:
                            continue
                        if not _within(w.window_start, w.window_end, s.time):
                            continue
                        if not _is_future_slot(s, now):
                            continue
                        matches.append(s)

            new_count = _collect_pending(db, w, matches)
            new_matches += new_count

        pending_alerts_sent = _send_pending_digests(db, email, watches, now, force=force)

        if blocked:
            _maybe_send_blocked_alert(db, email)

        elapsed = time.monotonic() - started
        requests_after, bytes_after = traffic.snapshot()
        cycle_requests = requests_after - requests_before
        cycle_bytes = bytes_after - bytes_before
        logger.info(
            "Scan traffic: %d request(s), %.1f KB this cycle; %.1f MB total since start.",
            cycle_requests, cycle_bytes / 1024, bytes_after / 1_048_576,
        )

        budget_note = " (scan budget hit; coverage partial)" if budget_hit else ""
        blocked_note = (
            f" BLOCKED: scraper is being refused by the site ({circuit.last_reason}); "
            "set SCRAPER_PROXY to a residential proxy." if blocked else ""
        )
        return {
            "ran": True, "in_window": True, "dates_scanned": dates_scanned,
            "total_slots": total_slots, "new_matches": new_matches,
            "blocked": blocked,
            "duration_seconds": round(elapsed, 1),
            "requests": cycle_requests,
            "bytes": cycle_bytes,
            "message": (
                f"Scanned {len(dates_scanned)} date(s) in {elapsed:.0f}s; "
                f"{new_matches} new match(es); {pending_alerts_sent} pending alert(s) sent."
                f"{budget_note}{blocked_note}"
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
