"""Weekly reminder to configure watches before the scan window opens."""
import logging

from sqlalchemy.orm import selectinload

from ..db import SessionLocal
from ..models import User
from .email import get_email_service

logger = logging.getLogger(__name__)


def send_weekly_reminders():
    """Email users who have no active watch, nudging them to set one up.

    Users with an active watch are already covered, so we skip them to avoid
    weekly nagging.
    """
    db = SessionLocal()
    email = get_email_service()
    sent = 0
    skipped = 0
    try:
        for user in db.query(User).options(selectinload(User.watches)).all():
            if any(w.active for w in user.watches):
                skipped += 1
                continue
            if email.send_setup_reminder_email(user.email, user.name):
                sent += 1
        logger.info("Weekly setup reminders: %d sent, %d skipped (already active)", sent, skipped)
    finally:
        db.close()
