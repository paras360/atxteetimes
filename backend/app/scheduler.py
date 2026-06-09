"""APScheduler configuration and jobs"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone

from .config import get_settings
from .services.cleanup import run_cleanup
from .services.monitor_job import run_scan
from .services.reminder_job import send_weekly_reminders

logger = logging.getLogger(__name__)
settings = get_settings()

_WEEKDAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler | None:
    return _scheduler


def start_scheduler():
    """Initialize and start the APScheduler."""
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        logger.warning("Scheduler is already running")
        return

    tz = timezone(settings.timezone)
    _scheduler = AsyncIOScheduler(timezone=tz)

    # Tee-time scan every N minutes, Tue-Sun (Tue 06:00 start enforced in job).
    # Schedule the coroutine directly so APScheduler can enforce max_instances=1
    # (a fire-and-forget create_task would return immediately and defeat it).
    _scheduler.add_job(
        run_scan,
        trigger=CronTrigger(
            day_of_week="tue-sun",
            minute=f"*/{settings.scan_interval_minutes}",
            timezone=tz,
        ),
        id="teetime_scan",
        name="Tee Time Scan",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
    )
    logger.info("Scheduled: tee-time scan every %d min (Tue-Sun)", settings.scan_interval_minutes)

    # Daily cleanup at 03:00.
    _scheduler.add_job(
        run_cleanup,
        trigger=CronTrigger(hour=3, minute=0, timezone=tz),
        id="cleanup_found_slots",
        name="Cleanup Found Slots",
        replace_existing=True,
    )
    logger.info("Scheduled: daily cleanup at 03:00")

    # Weekly "set up your watches" reminder, on the scan-start day before it opens.
    if settings.send_weekly_reminder:
        reminder_day = _WEEKDAY_NAMES[settings.scan_start_weekday % 7]
        _scheduler.add_job(
            send_weekly_reminders,
            trigger=CronTrigger(
                day_of_week=reminder_day,
                hour=settings.reminder_hour,
                minute=0,
                timezone=tz,
            ),
            id="weekly_setup_reminder",
            name="Weekly Setup Reminder",
            replace_existing=True,
        )
        logger.info(
            "Scheduled: weekly setup reminder on %s at %02d:00",
            reminder_day, settings.reminder_hour,
        )

    _scheduler.start()
    logger.info("APScheduler started")


def shutdown_scheduler():
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown()
        logger.info("APScheduler shut down")
        _scheduler = None
