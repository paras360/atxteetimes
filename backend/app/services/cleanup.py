"""Periodic cleanup of old found-slot records."""
import logging
from datetime import datetime, timedelta, timezone

from ..config import get_settings
from ..db import SessionLocal
from ..models import FoundSlot

logger = logging.getLogger(__name__)
settings = get_settings()


def run_cleanup():
    """Delete found-slot records older than the retention window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.found_slot_retention_days)
    db = SessionLocal()
    try:
        deleted = (
            db.query(FoundSlot)
            .filter(FoundSlot.found_at < cutoff)
            .delete(synchronize_session=False)
        )
        db.commit()
        if deleted:
            logger.info("Cleanup removed %d old found_slots", deleted)
    except Exception as e:  # noqa: BLE001
        logger.error("Cleanup failed: %s", e)
        db.rollback()
    finally:
        db.close()
