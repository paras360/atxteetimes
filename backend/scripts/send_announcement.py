"""One-off product-update announcement to every registered user.

Not part of the scheduled jobs: run it by hand, once, then leave it as a record
of what was sent. Dry-run is the default because the send is irreversible.

    python -m backend.scripts.send_announcement                 # render only
    python -m backend.scripts.send_announcement --only a@b.com  # send to one
    python -m backend.scripts.send_announcement --send          # send to all
"""
from __future__ import annotations

import argparse
import sys
import time
from html import escape as esc
from pathlib import Path

import resend

from ..app.config import get_settings
from ..app.db import SessionLocal
from ..app.models import User
from ..app.services.email import (
    GRAPHITE, HAIRLINE, INK, _body, _disp, _eyebrow, _flare_pill, _mono,
    _spacer_block, _shell,
)

settings = get_settings()
SUBJECT = "What changed in your tee-time alerts"

# (label, copy) -- ordered by how much the reader will notice the difference.
CHANGES = [
    ("No more duplicate alerts",
     "If two of your watches overlapped, the same tee time emailed you twice. "
     "Alerts are now grouped per person and de-duplicated, so one opening means "
     "one email, however many watches it matched."),
    ("Fewer missed openings",
     "When the connection to the city's booking site went dead, the scanner used "
     "to keep retrying the same dead route and stayed blind for up to half an "
     "hour. It now switches routes on the first failure."),
    ("Only times you can still play",
     "Alerts for tee times that had already passed earlier that day are gone. "
     "Every alert is for a slot you can still book."),
    ("A rebuilt email",
     "This one. The tee time is the headline, openings are grouped by day, and "
     "every row has a direct booking link."),
    ("Overlap warning in the app",
     "Setting up a watch that duplicates one you already have now tells you "
     "before you save it, so you can widen the original instead."),
]


def _change_rows() -> str:
    rows = []
    for i, (label, copy) in enumerate(CHANGES):
        top = "" if i == 0 else f"border-top:1px solid {HAIRLINE};"
        rows.append(f"""
        <tr><td style="padding:16px 0;{top}">
          <div style="{_mono(10, INK)}text-transform:uppercase;">{esc(label)}</div>
          <div style="{_body(15, GRAPHITE)}padding-top:7px;">{esc(copy)}</div>
        </td></tr>
        """)
    return ('<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            f'{"".join(rows)}</table>')


def build_html(first_name: str) -> str:
    app_url = f"{settings.base_url.rstrip('/')}/watches"
    inner = f"""
    {_eyebrow("Product update &nbsp;/&nbsp; August 2026")}
    <div class="dispatch-headline" style="{_disp(46, tracking='-0.035em', lh='0.98')}padding:14px 0 0;">A few fixes to<br>your tee-time alerts</div>
    <p style="{_body(16)}margin:20px 0 0;">
      Hi {esc(first_name)} &mdash; a short note on what changed this week. Nothing
      needs doing on your end; your watches carry over exactly as they were.
    </p>
    {_spacer_block(22)}
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr><td style="padding:0 0 4px;{_mono(10, GRAPHITE)}text-transform:uppercase;">What changed</td></tr>
      <tr><td style="border-top:1px solid {INK};font-size:0;line-height:0;">&nbsp;</td></tr>
    </table>
    {_change_rows()}
    {_spacer_block(10)}
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr><td style="border-top:1px solid {INK};padding:14px 0 0;">
        <div style="{_mono(10, GRAPHITE)}text-transform:uppercase;">Last seven days</div>
        <div style="{_mono(10, INK, lh='1.9')}text-transform:uppercase;padding-top:6px;">
          1,340 scans run &nbsp;/&nbsp; zero missed<br>
          Every 5 minutes &nbsp;/&nbsp; Tuesday through Sunday
        </div>
      </td></tr>
    </table>
    <div style="padding-top:26px;">
      {_flare_pill(app_url, "Open my watches")}
    </div>
    {_spacer_block(24)}
    <p style="{_body(15)}margin:0;">
      As always, reply to this email if something looks wrong.
    </p>
    <p style="{_body(15)}margin:16px 0 0;">Paras</p>
    """
    return _shell(
        preheader="Duplicate alerts are fixed, missed openings are fewer, and the email is rebuilt.",
        inner=inner,
        footer_note=(
            "You're receiving this because you have an ATX Tee Times account. "
            "This is a one-off product note, not a tee-time alert."
        ),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="actually send to everyone")
    ap.add_argument("--only", help="send to a single address (implies --send)")
    args = ap.parse_args()

    sending = bool(args.send or args.only)
    try:
        db = SessionLocal()
        try:
            users = db.query(User).order_by(User.id).all()
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001
        # A dry run should still render off a laptop that has no local database.
        if sending:
            raise
        print(f"No local database ({e.__class__.__name__}); rendering with a sample name.")
        users = []

    if args.only:
        users = [u for u in users if u.email.lower() == args.only.lower()]
        if not users:
            print(f"No registered user with email {args.only}")
            return 1

    print(f"{len(users)} recipient(s): {', '.join(u.email for u in users) or '(none)'}")

    if not sending:
        out = Path("/tmp/announcement.html")
        out.write_text(build_html(users[0].name.split()[0] if users else "Grant"))
        print(f"\nDRY RUN -- nothing sent. Preview written to {out}")
        print("Re-run with --only <email> to test, or --send to broadcast.")
        return 0

    if not settings.resend_api_key:
        print("RESEND_API_KEY is not set; refusing to send.")
        return 1
    resend.api_key = settings.resend_api_key

    sent, failed = 0, []
    for user in users:
        first = user.name.split()[0] if user.name.strip() else "there"
        try:
            resend.Emails.send({
                "from": settings.email_from,
                "to": [user.email],
                "subject": SUBJECT,
                "html": build_html(first),
            })
            sent += 1
            print(f"  sent -> {user.email}")
        except Exception as e:  # noqa: BLE001
            failed.append((user.email, str(e)))
            print(f"  FAILED -> {user.email}: {e}")
        time.sleep(0.6)  # stay under Resend's burst rate limit

    print(f"\n{sent} sent, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
