"""Email notifications via Resend.

Visual system: "Dispatch". A warm bone canvas carries near-black ink, hierarchy
comes from typographic scale rather than weight, and every machine-generated
value -- times, dates, slot counts -- is set in tracked monospace so the tee
sheet reads like a departure board rather than a marketing email.

Two rules hold the system together:

* Exactly one chromatic element. Signal red appears only where a decision is
  being asked for, so scarcity does the work that shouting would otherwise do.
* Exactly one rounded element. Every edge is square except the primary action
  pill, which makes the single decision impossible to miss without a colour
  change or a drop shadow.

Everything is inlined and table-based so it survives the usual email-client CSS
stripping, and no layout depends on border-radius or background-image (both of
which Outlook's Word renderer drops).
"""
import logging
from datetime import datetime
from html import escape as esc

import resend

from ..config import get_settings
from .links import build_search_url

logger = logging.getLogger(__name__)
settings = get_settings()

if settings.resend_api_key:
    resend.api_key = settings.resend_api_key

SEARCH_URL = f"{settings.webtrac_base_url.rstrip('/')}/search.html?display=detail&module=GR"

# ---------------------------------------------------------------------------
# Style tokens (Dispatch)
# ---------------------------------------------------------------------------
CANVAS = "#e9e6e1"    # warm bone page ground
PAPER = "#f7f5f2"     # parchment card surface
INK = "#191919"       # near-black: all text, all borders
FLARE = "#fe3a3a"     # the only chromatic value, reserved for the decision
GRAPHITE = "#6f6b66"  # muted metadata
HAIRLINE = "#d5d0c9"  # warm rules between rows
WHITE = "#ffffff"

# Helvetica is the closest universally-available stand-in for the tight
# neo-grotesque display face; the mono stack degrades to Menlo/Consolas, which
# hold tracking well enough to keep the departure-board rhythm.
_SANS = "'Helvetica Neue',Helvetica,Arial,sans-serif"
_MONO = "'IBM Plex Mono','SFMono-Regular',Menlo,Consolas,'Courier New',monospace"


def _disp(size: int, color: str = INK, tracking: str = "-0.03em",
          lh: str = "0.92") -> str:
    """Display type: large, weight 400, tightly tracked. Scale is the hierarchy."""
    return (
        f"font-family:{_SANS};font-weight:400;font-size:{size}px;"
        f"line-height:{lh};letter-spacing:{tracking};color:{color};"
        f"mso-line-height-rule:exactly;"
    )


def _mono(size: int, color: str = GRAPHITE, tracking: str = "0.09em",
          lh: str = "1.4") -> str:
    """Monospace: every machine-generated value and every wayfinding label."""
    return (
        f"font-family:{_MONO};font-weight:400;font-size:{size}px;"
        f"line-height:{lh};letter-spacing:{tracking};color:{color};"
    )


def _body(size: int = 15, color: str = INK, lh: str = "1.55") -> str:
    return (
        f"font-family:{_SANS};font-weight:400;font-size:{size}px;"
        f"line-height:{lh};letter-spacing:-0.01em;color:{color};"
    )


def _fmt_time(t: str) -> str:
    """'6:10 am' -> '6:10 AM'."""
    return t.replace("am", "AM").replace("pm", "PM").strip()


def _fmt_date(d: str) -> str:
    """'08/15/2026' -> 'SAT AUG 15'. Falls back to the raw string."""
    try:
        return datetime.strptime(d, "%m/%d/%Y").strftime("%a %b %d").upper()
    except (ValueError, TypeError):
        return d


def _spacer(h: int) -> str:
    """Vertical gap as a table row, for use between the shell's top-level rows."""
    return f'<tr><td style="height:{h}px;line-height:{h}px;font-size:{h}px;">&nbsp;</td></tr>'


def _spacer_block(h: int) -> str:
    """Vertical gap as a block element, for use inside a card's content flow."""
    return f'<div style="height:{h}px;line-height:{h}px;font-size:{h}px;">&nbsp;</div>'


def _rule(color: str = HAIRLINE) -> str:
    """A 1px hairline. Borders and whitespace do all the separating; no shadows."""
    return (
        f'<tr><td style="border-top:1px solid {color};font-size:0;line-height:0;">'
        f'&nbsp;</td></tr>'
    )


def _eyebrow(text: str, color: str = GRAPHITE) -> str:
    """Tracked uppercase mono label sitting above a display line."""
    return f'<div style="{_mono(11, color, lh="1.3")}text-transform:uppercase;">{text}</div>'


def _flare_pill(href: str, label: str) -> str:
    """The single rounded element in the system, and the only use of red."""
    return (
        f'<a href="{href}" style="display:inline-block;background:{FLARE};'
        f'border:1px solid {FLARE};{_mono(12, WHITE, lh="1")}text-transform:uppercase;'
        f'text-decoration:none;padding:15px 26px;border-radius:35px;'
        f'mso-padding-alt:15px 26px;">{label}</a>'
    )


def _ghost_link(href: str, label: str) -> str:
    """Square, hairline-bordered secondary action. Never competes with the pill."""
    return (
        f'<a href="{href}" style="display:inline-block;background:transparent;'
        f'border:1px solid {INK};{_mono(11, INK, lh="1")}text-transform:uppercase;'
        f'text-decoration:none;padding:9px 14px;mso-padding-alt:9px 14px;">{label}</a>'
    )


_MASTHEAD = f"""
<tr><td style="padding:0 2px 14px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
    <td style="vertical-align:middle;">
      <span style="display:inline-block;width:9px;height:9px;background:{FLARE};vertical-align:middle;margin-right:9px;"></span><span style="{_mono(11, INK)}text-transform:uppercase;vertical-align:middle;">ATX Tee Times</span>
    </td>
    <td style="text-align:right;vertical-align:middle;">
      <span style="{_mono(11, GRAPHITE)}text-transform:uppercase;">Dispatch</span>
    </td>
  </tr></table>
</td></tr>
<tr><td style="border-top:1px solid {INK};font-size:0;line-height:0;">&nbsp;</td></tr>
"""


def _shell(preheader: str, inner: str, footer_note: str) -> str:
    """Bone canvas, hairline masthead, one square parchment card.

    The layout is fluid up to 600px rather than fixed at it, so the oversized
    display type still fits a 320px viewport. The media query is a refinement
    for clients that honour <style>; the inline styles alone remain legible
    everywhere else.
    """
    return f"""\
<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only">
<meta name="supported-color-schemes" content="light">
<style>
  @media only screen and (max-width:620px) {{
    .dispatch-card {{ padding:24px 18px !important; }}
    .dispatch-count {{ font-size:60px !important; }}
    .dispatch-time {{ font-size:34px !important; }}
    .dispatch-headline {{ font-size:34px !important; }}
    .dispatch-slot {{ font-size:20px !important; }}
  }}
</style>
</head>
<body style="margin:0;padding:0;background:{CANVAS};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:{CANVAS};">{preheader}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{CANVAS};">
  <tr><td align="center" style="padding:28px 12px 32px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;">
      {_MASTHEAD}
      {_spacer(18)}
      <tr><td class="dispatch-card" style="background:{PAPER};border:1px solid {INK};padding:34px 32px;">
        {inner}
      </td></tr>
      {_spacer(16)}
      <tr><td style="padding:0 2px;">
        <p style="{_mono(10, GRAPHITE, lh='1.7')}margin:0;">{footer_note}</p>
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>"""


def _sheet(shown, attribute: bool) -> str:
    """The departure board: tee times grouped under a date, one row each.

    Grouping lifts the date out of every row, which matters most in the large
    digests where the same string would otherwise repeat twenty times over.
    `attribute` adds the originating watch to each row, which only earns its
    space when one email spans several watches.
    """
    groups: dict[str, list] = {}
    for s in shown:
        groups.setdefault(s.date, []).append(s)

    parts = [f"""
    <tr>
      <td style="padding:0 0 9px;{_mono(10, GRAPHITE)}text-transform:uppercase;">Tee sheet</td>
      <td style="padding:0 0 9px;{_mono(10, GRAPHITE)}text-transform:uppercase;text-align:right;">Book</td>
    </tr>
    <tr><td colspan="2" style="border-top:1px solid {INK};font-size:0;line-height:0;">&nbsp;</td></tr>
    """]

    seen = 0
    for date, rows in groups.items():
        parts.append(
            f'<tr><td colspan="2" style="padding:13px 0 3px;{_mono(10, INK)}'
            f'text-transform:uppercase;">{_fmt_date(date)}</td></tr>'
        )
        for s in rows:
            seen += 1
            meta = f"{s.open_slots} open"
            if attribute and s.watch is not None:
                meta += f" &nbsp;/&nbsp; {esc(s.watch.label)}"
            # The final rule would otherwise dangle just above the CTA.
            border = "" if seen == len(shown) else f"border-bottom:1px solid {HAIRLINE};"
            parts.append(f"""
            <tr>
              <td style="padding:12px 0 14px;{border}">
                <div class="dispatch-slot" style="{_mono(23, INK, tracking='0.01em', lh='1.1')}">{_fmt_time(s.time)}</div>
                <div style="{_body(15)}padding-top:6px;">{esc(s.course_name)}</div>
                <div style="{_mono(10, GRAPHITE)}text-transform:uppercase;padding-top:5px;">{meta}</div>
              </td>
              <td style="padding:12px 0 14px 12px;{border}text-align:right;vertical-align:middle;white-space:nowrap;">
                {_ghost_link(s.booking_url, "Book")}
              </td>
            </tr>
            """)

    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        f'{"".join(parts)}</table>'
    )


class EmailService:
    """Send tee-time-found notifications."""

    @classmethod
    def send_slots_digest_email(cls, to_email: str, user_name: str, watches, slots) -> bool:
        """Send one digest listing every newly-opened slot for a user.

        `slots` is a list of FoundSlot rows (already sorted and de-duplicated),
        and `watches` are the watches that produced them -- a user with several
        overlapping watches gets one email, not one per watch. Only call this
        with slots that haven't been alerted yet so we never resend the same email.

        A single opening gets a different hero to a batch: the tee time itself
        becomes the headline, because that is the only fact the reader needs.
        """
        if not settings.resend_api_key:
            logger.warning("RESEND_API_KEY not set; skipping digest to %s", to_email)
            return False
        if not slots or not watches:
            return False
        try:
            count = len(slots)
            time_word = "tee time" if count == 1 else "tee times"
            single_watch = watches[0] if len(watches) == 1 else None
            labels = [esc(w.label) for w in watches]

            # Cap the rows so a mass re-detection can't render a wall of slots.
            # Every slot is still marked notified by the caller, so the overflow
            # is never re-sent later.
            shown = slots[: max(1, settings.max_slots_per_email)]
            overflow = count - len(shown)

            if single_watch is not None:
                scope = labels[0]
                subject_tail = f": {single_watch.label}"
            else:
                scope = f"{len(watches)} watches"
                subject_tail = f" across {len(watches)} watches"

            if count == 1:
                # One opening: lead with the tee time, not with a count.
                s = slots[0]
                hero = f"""
                {_eyebrow(f"{_fmt_date(s.date)} &nbsp;/&nbsp; {esc(s.course_name).upper()}")}
                <div class="dispatch-time" style="{_mono(44, INK, tracking='-0.01em', lh='1.05')}padding:14px 0 0;">{_fmt_time(s.time)}</div>
                <div style="{_mono(11, GRAPHITE)}text-transform:uppercase;padding-top:10px;">{s.open_slots} slots open &nbsp;/&nbsp; {scope}</div>
                """
                body = ""
                cta_label = "Book this tee time"
                cta_href = s.booking_url
                subject = f"{_fmt_time(s.time)} opened at {s.course_name}"
                preheader = f"{_fmt_time(s.time)} on {_fmt_date(s.date)} at {s.course_name}."
            else:
                hero = f"""
                {_eyebrow(f"{count} openings &nbsp;/&nbsp; {scope}")}
                <div class="dispatch-count" style="{_disp(78)}padding:12px 0 0;">{count}</div>
                <div class="dispatch-headline" style="{_disp(30, tracking='-0.02em', lh='1.1')}padding-top:6px;">{time_word} opened up</div>
                """
                body = f"""
                {_spacer_block(26)}
                {_sheet(shown, attribute=single_watch is None)}
                {f'<p style="{_mono(11, GRAPHITE)}text-transform:uppercase;margin:16px 0 0;">+ {overflow} more &mdash; open WebTrac to see them all</p>' if overflow else ''}
                """
                cta_label = "Open WebTrac to book"
                cta_href = SEARCH_URL
                subject = f"{count} {time_word} opened{subject_tail}"
                preheader = f"{count} {time_word} just opened. Tee times go fast."

            inner = f"""
            {hero}
            {body}
            <div style="padding-top:30px;">
              {_flare_pill(cta_href, cta_label)}
            </div>
            <div style="{_mono(10, GRAPHITE, lh='1.7')}text-transform:uppercase;padding-top:16px;">
              Tee times go fast &mdash; book quickly
            </div>
            """
            html = _shell(
                preheader=preheader,
                inner=inner,
                footer_note=(
                    "You're receiving this because you set up a watch on ATX Tee Times. "
                    "We only email when new times open, not on every scan."
                ),
            )
            params = {
                "from": settings.email_from,
                "to": [to_email],
                "subject": subject,
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
            inner = f"""
            {_eyebrow("Weekly setup &nbsp;/&nbsp; scan opens today")}
            <div class="dispatch-headline" style="{_disp(46, tracking='-0.035em', lh='0.98')}padding:14px 0 0;">Set up your<br>tee-time watches</div>
            <p style="{_body(16)}margin:20px 0 0;">
              Hi {esc(user_name)}, the weekly scan starts this morning. Make sure your
              watches are configured so we can alert you the moment a matching tee
              time opens up.
            </p>
            {_spacer_block(24)}
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
              <tr><td style="border-top:1px solid {INK};font-size:0;line-height:0;">&nbsp;</td></tr>
              <tr><td style="padding:14px 0;{_mono(11, GRAPHITE)}text-transform:uppercase;">
                Scan interval &nbsp;/&nbsp; every 5 minutes<br>
                Coverage &nbsp;/&nbsp; Tuesday through Sunday
              </td></tr>
            </table>
            <div style="padding-top:22px;">
              {_flare_pill(app_url, "Review my watches")}
            </div>
            <div style="padding-top:18px;">
              {_ghost_link(build_search_url(), "Browse WebTrac first")}
            </div>
            """
            html = _shell(
                preheader="The weekly tee-time scan starts this morning.",
                inner=inner,
                footer_note="You're receiving this because you have an ATX Tee Times account.",
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
            {_eyebrow("Scanner offline", FLARE)}
            <div class="dispatch-headline" style="{_disp(46, tracking='-0.035em', lh='0.98')}padding:14px 0 0;">Scanning is<br>blocked</div>
            <p style="{_body(16)}margin:20px 0 0;">
              Hi {esc(user_name)}, the Austin WebTrac site has been refusing our
              requests for {duration}. Until this clears no tee times can be detected,
              so you will not receive alerts even if times open up. Your watches are
              unchanged and resume automatically once access is restored.
            </p>
            {_spacer_block(24)}
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
              <tr><td style="border-top:1px solid {INK};font-size:0;line-height:0;">&nbsp;</td></tr>
              <tr><td style="padding:14px 0;">
                <div style="{_mono(10, GRAPHITE)}text-transform:uppercase;">Duration</div>
                <div style="{_mono(20, INK, tracking='0.01em')}padding-top:4px;">{duration}</div>
              </td></tr>
              <tr><td style="border-top:1px solid {HAIRLINE};padding:14px 0;">
                <div style="{_mono(10, GRAPHITE)}text-transform:uppercase;">Reason reported</div>
                <div style="{_body(15)}padding-top:4px;">{esc(reason) or "blocked by site"}</div>
              </td></tr>
            </table>
            <div style="padding-top:22px;">
              {_flare_pill(SEARCH_URL, "Check WebTrac manually")}
            </div>
            """
            html = _shell(
                preheader=f"Scanning has been blocked for {duration} - no alerts until it clears.",
                inner=inner,
                footer_note=(
                    "You're receiving this because you have an active watch. We send this "
                    f"at most once every {settings.blocked_alert_cooldown_hours} hours "
                    "while scanning is down."
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
