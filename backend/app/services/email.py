"""Email notifications via Resend.

The HTML follows the "Streamtime" creative-scrapbook style: a warm linen canvas,
paper-white cards with hairline black borders, a single charcoal hero band, and
sun-yellow pill actions. Everything is inlined and table-based so it survives the
usual email-client CSS stripping.
"""
import logging
from datetime import datetime

import resend

from ..config import get_settings
from .links import build_search_url

logger = logging.getLogger(__name__)
settings = get_settings()

if settings.resend_api_key:
    resend.api_key = settings.resend_api_key

SEARCH_URL = f"{settings.webtrac_base_url.rstrip('/')}/search.html?display=detail&module=GR"

# ---------------------------------------------------------------------------
# Style tokens (Streamtime)
# ---------------------------------------------------------------------------
LINEN = "#f1e8de"
PAPER = "#fbf8f5"
WHITE = "#ffffff"
CHARCOAL = "#2f2c29"
SUN = "#ffde3b"
PINK = "#ff4dd5"
LIME = "#c1f32b"
PERIWINKLE = "#6483ff"
SPRING = "#c6dc3c"
BUBBLEGUM = "#ee84d5"
SAND = "#eadcce"
INK = "#000000"
FOG = "#999999"
HAIRLINE = "#e7dccd"

_STACK_STD = ("'Ease Standard',-apple-system,BlinkMacSystemFont,'Segoe UI',"
              "Roboto,Helvetica,Arial,sans-serif")
_STACK_DISP = ("'Ease Display',-apple-system,BlinkMacSystemFont,'Segoe UI',"
               "Roboto,Helvetica,Arial,sans-serif")


def _text(size: int, color: str, tracking: str, lh: str = "1.2",
          display: bool = False) -> str:
    """Return an inline font style string (single 400 weight, tight tracking)."""
    stack = _STACK_DISP if display else _STACK_STD
    return (
        f"font-family:{stack};font-weight:400;font-size:{size}px;"
        f"line-height:{lh};letter-spacing:{tracking};color:{color};"
    )


def _fmt_time(t: str) -> str:
    """'6:10 am' -> '6:10 AM'."""
    return t.replace("am", "AM").replace("pm", "PM").strip()


def _fmt_date(d: str) -> str:
    """'06/20/2026' -> 'Sat, Jun 20'. Falls back to the raw string."""
    try:
        return datetime.strptime(d, "%m/%d/%Y").strftime("%a, %b %d")
    except (ValueError, TypeError):
        return d


def _pill(href: str, label: str, *, bg: str, color: str, border: str | None = None,
          radius: int = 96, size: int = 16, pad: str = "12px 22px") -> str:
    """A sticker-label pill button."""
    border_css = f"border:1px solid {border};" if border else "border:0;"
    return (
        f'<a href="{href}" style="display:inline-block;background:{bg};{border_css}'
        f'{_text(size, color, "-0.04em")}text-decoration:none;padding:{pad};'
        f'border-radius:{radius}px;">{label}</a>'
    )


def _tag(label: str, *, bg: str) -> str:
    return (
        f'<span style="display:inline-block;background:{bg};'
        f'{_text(12, INK, "-0.96px")}padding:5px 12px;border-radius:5px;">{label}</span>'
    )


_HEADER = f"""
<tr><td style="background:{CHARCOAL};border-radius:5px;padding:22px 26px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
    <td style="vertical-align:middle;">
      <span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:{SUN};vertical-align:middle;margin-right:10px;"></span>
      <span style="{_text(22, WHITE, '-0.88px', display=True)}vertical-align:middle;text-transform:uppercase;">ATX Tee Times</span>
    </td>
    <td style="text-align:right;vertical-align:middle;">
      <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{PINK};margin-left:5px;"></span>
      <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{LIME};margin-left:5px;"></span>
      <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{PERIWINKLE};margin-left:5px;"></span>
    </td>
  </tr></table>
</td></tr>
<tr><td style="height:16px;line-height:16px;font-size:16px;">&nbsp;</td></tr>
"""


def _spacer(h: int = 16) -> str:
    return f'<tr><td style="height:{h}px;line-height:{h}px;font-size:{h}px;">&nbsp;</td></tr>'


def _shell(preheader: str, inner: str, footer_note: str) -> str:
    """Wrap card content in the warm-linen page with header band and footer."""
    return f"""\
<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only">
</head>
<body style="margin:0;padding:0;background:{LINEN};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:{LINEN};">{preheader}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{LINEN};">
  <tr><td align="center" style="padding:24px 12px;">
    <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:600px;max-width:600px;">
      {_HEADER}
      <tr><td style="background:{PAPER};border:1px solid {INK};border-radius:5px;padding:28px;">
        {inner}
      </td></tr>
      {_spacer(16)}
      <tr><td style="padding:0 6px;">
        <p style="{_text(12, FOG, '-0.6px', lh='1.6')}margin:0;">{footer_note}</p>
      </td></tr>
      {_spacer(8)}
    </table>
  </td></tr>
</table>
</body></html>"""


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

            # Cap the rows so a mass re-detection can't render a wall of slots.
            # Every slot is still marked notified by the caller, so the overflow
            # is never re-sent later.
            shown = slots[: max(1, settings.max_slots_per_email)]
            overflow = count - len(shown)

            row_html = []
            for i, s in enumerate(shown):
                last = i == len(shown) - 1
                border = "" if last else f"border-bottom:1px solid {HAIRLINE};"
                row_html.append(f"""
                <tr>
                  <td style="padding:14px 0;{border}">
                    <div style="{_text(16, INK, '-0.7px')}">{s.course_name}</div>
                    <div style="{_text(12, FOG, '-0.5px')}padding-top:4px;">{_fmt_date(s.date)} &nbsp;&middot;&nbsp; {s.open_slots} open</div>
                  </td>
                  <td style="padding:14px 8px;{border}text-align:center;white-space:nowrap;">
                    <span style="display:inline-block;background:{SUN};{_text(14, INK, '-0.4px')}padding:6px 13px;border-radius:96px;">{_fmt_time(s.time)}</span>
                  </td>
                  <td style="padding:14px 0 14px 8px;{border}text-align:right;white-space:nowrap;">
                    {_pill(s.booking_url, "Book", bg=WHITE, color=INK, border=INK, size=14, pad="7px 16px")}
                  </td>
                </tr>
                """)

            inner = f"""
            {_tag(watch.label, bg=SPRING)}
            <h1 style="{_text(30, INK, '-1.02px', lh='1.05')}margin:16px 0 6px;">{count} {time_word} opened up</h1>
            <p style="{_text(16, FOG, '-0.7px')}margin:0 0 20px;">
              Matching your watch &mdash; {watch.num_players} {players_word}, {watch.num_holes} holes.
            </p>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
              {''.join(row_html)}
            </table>
            {f'<p style="{_text(14, INK, "-0.6px")}margin:14px 0 0;">+ {overflow} more open {"slot" if overflow == 1 else "slots"} &mdash; open WebTrac to see them all.</p>' if overflow else ''}
            <div style="padding-top:24px;">
              {_pill(SEARCH_URL, "Open WebTrac to book &rarr;", bg=SUN, color=INK, radius=160, pad="15px 26px")}
            </div>
            <p style="{_text(12, FOG, '-0.5px', lh='1.6')}margin:16px 0 0;">
              Tee times go fast &mdash; book quickly.
            </p>
            """
            html = _shell(
                preheader=f"{count} {time_word} just opened for {watch.label}",
                inner=inner,
                footer_note=(
                    "You're receiving this because you set up a watch on ATX Tee "
                    "Times Watcher. We only email when new times open, not on every scan."
                ),
            )
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
            inner = f"""
            {_tag("Weekly setup", bg=SAND)}
            <h1 style="{_text(30, INK, '-1.02px', lh='1.05')}margin:16px 0 6px;">Set up your tee-time watches</h1>
            <p style="{_text(18, INK, '-0.8px', lh='1.35')}margin:0 0 8px;">Hi {user_name}, the weekly scan starts this morning.</p>
            <p style="{_text(16, FOG, '-0.7px', lh='1.45')}margin:0 0 22px;">
              Make sure your watches are configured so we can alert you the moment a
              matching tee time opens up this week. We scan every 5 minutes, Tuesday
              through Sunday.
            </p>
            <div>
              {_pill(app_url, "Review my watches", bg=SUN, color=INK, radius=160, pad="15px 26px")}
            </div>
            <p style="{_text(12, FOG, '-0.5px', lh='1.6')}margin:18px 0 0;">
              Prefer to browse first? {_pill(search_url, "Open the Austin WebTrac golf search", bg=WHITE, color=INK, border=INK, size=12, pad="6px 14px")}
            </p>
            """
            html = _shell(
                preheader="The weekly tee-time scan starts this morning.",
                inner=inner,
                footer_note="You're receiving this because you have an ATX Tee Times Watcher account.",
            )
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


    @classmethod
    def send_scraper_blocked_email(cls, to_email: str, user_name: str,
                                   blocked_for, reason: str) -> bool:
        """Warn that the site is refusing our requests, so no alerts can arrive."""
        if not settings.resend_api_key:
            logger.warning("RESEND_API_KEY not set; skipping blocked alert to %s", to_email)
            return False
        try:
            hours = int(blocked_for.total_seconds() // 3600)
            minutes = int((blocked_for.total_seconds() % 3600) // 60)
            duration = f"{hours}h {minutes}m" if hours else f"{minutes}m"
            inner = f"""
            {_tag("Scanner offline", bg=BUBBLEGUM)}
            <h1 style="{_text(30, INK, '-1.02px', lh='1.05')}margin:16px 0 6px;">Tee-time scanning is blocked</h1>
            <p style="{_text(18, INK, '-0.8px', lh='1.35')}margin:0 0 8px;">
              Hi {user_name}, the Austin WebTrac site has been refusing our requests for {duration}.
            </p>
            <p style="{_text(16, FOG, '-0.7px', lh='1.45')}margin:0 0 20px;">
              Until this clears, no tee times can be detected and you will not receive
              alerts &mdash; even if times open up. Your watches are unchanged and will
              resume automatically once access is restored.
            </p>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                   style="background:{SAND};border-radius:5px;">
              <tr><td style="padding:16px 18px;">
                <div style="{_text(12, FOG, '-0.5px')}">Reason reported</div>
                <div style="{_text(16, INK, '-0.7px')}padding-top:5px;">{reason or "blocked by site"}</div>
              </td></tr>
            </table>
            <div style="padding-top:24px;">
              {_pill(SEARCH_URL, "Check WebTrac manually &rarr;", bg=SUN, color=INK, radius=160, pad="15px 26px")}
            </div>
            """
            html = _shell(
                preheader=f"Scanning has been blocked for {duration} - no alerts until it clears.",
                inner=inner,
                footer_note=(
                    "You're receiving this because you have an active watch. We send this "
                    "at most once every "
                    f"{settings.blocked_alert_cooldown_hours} hours while scanning is down."
                ),
            )
            params = {
                "from": settings.email_from,
                "to": [to_email],
                "subject": f"Heads up: tee-time scanning is blocked ({duration})",
                "html": html,
            }
            result = resend.Emails.send(params)
            logger.info("Blocked alert sent to %s: %s", to_email, result)
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to send blocked alert to %s: %s", to_email, e)
            return False


def get_email_service() -> EmailService:
    return EmailService()
