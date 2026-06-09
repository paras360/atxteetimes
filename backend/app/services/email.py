"""Email notifications via Resend."""
import logging

import resend

from ..config import get_settings
from .links import build_search_url

logger = logging.getLogger(__name__)
settings = get_settings()

if settings.resend_api_key:
    resend.api_key = settings.resend_api_key

SEARCH_URL = f"{settings.webtrac_base_url.rstrip('/')}/search.html?display=detail&module=GR"


class EmailService:
    """Send tee-time-found notifications."""

    @classmethod
    def send_slots_digest_email(cls, to_email: str, user_name: str, watch, slots) -> bool:
        """Send one digest listing every newly-opened slot for a watch.

        `slots` is a list of FoundSlot rows (already sorted). Only call this with
        slots that haven't been alerted yet so we never resend the same email.
        """
        if not settings.resend_api_key:
            logger.warning("RESEND_API_KEY not set; skipping digest to %s", to_email)
            return False
        if not slots:
            return False
        try:
            count = len(slots)
            time_word = "tee time" if count == 1 else "tee times"
            players_word = "player" if watch.num_players == 1 else "players"
            rows = "".join(
                f"""
                <tr>
                    <td style="padding:8px 10px; border-bottom:1px solid #eee;">{s.course_name}</td>
                    <td style="padding:8px 10px; border-bottom:1px solid #eee;">{s.date}</td>
                    <td style="padding:8px 10px; border-bottom:1px solid #eee;">{s.time}</td>
                    <td style="padding:8px 10px; border-bottom:1px solid #eee; text-align:center;">{s.open_slots}</td>
                    <td style="padding:8px 10px; border-bottom:1px solid #eee;">
                        <a href="{s.booking_url}" style="color:#111;">Open</a>
                    </td>
                </tr>
                """
                for s in slots
            )
            html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 640px; margin: 0 auto;">
                <h2 style="margin-bottom: 4px;">{count} {time_word} opened up</h2>
                <p style="color:#555; margin-top:0;">
                    Matching your watch "<strong>{watch.label}</strong>"
                    ({watch.num_players} {players_word}, {watch.num_holes} holes)
                </p>
                <table style="border-collapse:collapse; width:100%; margin:16px 0; font-size:14px;">
                    <thead>
                        <tr style="text-align:left; color:#666;">
                            <th style="padding:8px 10px; border-bottom:2px solid #111;">Course</th>
                            <th style="padding:8px 10px; border-bottom:2px solid #111;">Date</th>
                            <th style="padding:8px 10px; border-bottom:2px solid #111;">Time</th>
                            <th style="padding:8px 10px; border-bottom:2px solid #111; text-align:center;">Open</th>
                            <th style="padding:8px 10px; border-bottom:2px solid #111;">Book</th>
                        </tr>
                    </thead>
                    <tbody>{rows}</tbody>
                </table>
                <p style="color:#888; font-size:12px; margin-top:16px;">
                    Tee times go fast - book quickly. You're receiving this because you set up a
                    watch on ATX Tee Times Watcher. We only email when new times open, not on every scan.
                </p>
            </div>
            """
            params = {
                "from": settings.email_from,
                "to": [to_email],
                "subject": f"{count} {time_word} opened: {watch.label}",
                "html": html,
            }
            result = resend.Emails.send(params)
            logger.info("Digest email sent to %s (%d slots): %s", to_email, count, result)
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to send digest email to %s: %s", to_email, e)
            return False

    @classmethod
    def send_setup_reminder_email(cls, to_email: str, user_name: str) -> bool:
        """Weekly nudge to configure watches before the scan window opens."""
        if not settings.resend_api_key:
            logger.warning("RESEND_API_KEY not set; skipping reminder to %s", to_email)
            return False
        try:
            app_url = f"{settings.base_url.rstrip('/')}/watches"
            search_url = build_search_url()  # generic Golf search, prefilled module
            html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 560px; margin: 0 auto;">
                <h2 style="margin-bottom: 4px;">Set up your tee-time watches</h2>
                <p style="color:#555; margin-top:0;">Hi {user_name}, the weekly scan starts this morning.</p>
                <p>Make sure your watches are configured so we can alert you the moment a
                   matching tee time opens up this week (we scan every 5 minutes,
                   Tuesday through Sunday).</p>
                <a href="{app_url}"
                   style="display:inline-block; background:#111; color:#fff; padding:10px 18px;
                          text-decoration:none; border-radius:6px; margin:8px 0;">
                    Review my watches
                </a>
                <p style="color:#888; font-size:12px; margin-top:16px;">
                    Prefer to browse first? <a href="{search_url}">Open the Austin WebTrac golf search</a>.
                </p>
                <p style="color:#888; font-size:12px;">
                    You're receiving this because you have an ATX Tee Times Watcher account.
                </p>
            </div>
            """
            params = {
                "from": settings.email_from,
                "to": [to_email],
                "subject": "Set up your tee-time watches for this week",
                "html": html,
            }
            result = resend.Emails.send(params)
            logger.info("Setup reminder sent to %s: %s", to_email, result)
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to send setup reminder to %s: %s", to_email, e)
            return False


def get_email_service() -> EmailService:
    return EmailService()
