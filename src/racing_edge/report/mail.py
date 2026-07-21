"""Email the day's output — ADAPTS the existing SMTP setup, doesn't reinvent it.

Uses the same env vars the old system's config reads (EMAIL_SENDER / EMAIL_PASSWORD /
EMAIL_RECIPIENT / SMTP_HOST / SMTP_PORT), and reuses the existing HTML renderer
(email_render.to_html) when it's importable — so the trial's pick and dissection can
land in your inbox instead of only the task log. No new account, no new config.

Contract (same as the old mailer): NEVER raises. Returns True if sent, False otherwise —
the caller reports it, so a mail failure can't crash the pick.
"""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import make_msgid

_REQUIRED = ("EMAIL_SENDER", "EMAIL_PASSWORD", "EMAIL_RECIPIENT")


def configured() -> bool:
    """True only if the SMTP credentials are actually present in the environment."""
    return all(os.environ.get(k) for k in _REQUIRED)


def recipient() -> str:
    """The address mail will go to — so the CLI can show it (check it's really yours)."""
    return os.environ.get("EMAIL_RECIPIENT", "")


def send(subject: str, body: str, title: str = "", subtitle: str = ""):
    """Send `body` (plain text) to EMAIL_RECIPIENT over SMTP/TLS, with a styled HTML
    part when email_render is importable. Never raises; returns True on success."""
    if not configured():
        return False
    sender = os.environ["EMAIL_SENDER"]
    password = os.environ["EMAIL_PASSWORD"]
    recipient = os.environ["EMAIL_RECIPIENT"]
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))

    html_body: str | None = None
    try:                                       # reuse the existing renderer if it's on the path
        from email_render import to_html
        html_body = to_html(title or subject, subtitle, body)
    except Exception:
        html_body = None

    msg: MIMEText | MIMEMultipart
    if html_body:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain", "utf-8"))     # plain fallback FIRST
        msg.attach(MIMEText(html_body, "html", "utf-8"))  # HTML last
    else:
        msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg_id = make_msgid()
    msg["Message-ID"] = msg_id

    def _verify_and_rescue() -> str:
        """SELF-VERIFYING DELIVERY (2026-07-19 — 'I am not getting nap email, simple
        as that, find the bug'): SMTP said accepted every time, but Gmail was FILING
        the self-sent betting-shaped mail. So the machine now checks its own mailbox
        over IMAP: found in INBOX -> proven; found in SPAM -> moved to INBOX
        automatically (which also trains Gmail). Never raises."""
        try:
            import imaplib
            import time
            time.sleep(8)                          # give Gmail a moment to file it
            box = imaplib.IMAP4_SSL(
                os.environ.get("IMAP_HOST", "imap.gmail.com"), timeout=25)
            box.login(sender, password)

            def _find(folder: str):
                try:
                    box.select(folder)
                    typ, d = box.search(None, "HEADER", "Message-ID", msg_id)
                    return d[0].split() if typ == "OK" and d and d[0] else []
                except Exception:
                    return []

            if _find("INBOX"):
                box.logout()
                return "delivered to INBOX (verified)"
            spam_ids = _find("[Gmail]/Spam")
            if spam_ids:
                for i in spam_ids:
                    box.copy(i, "INBOX")
                    box.store(i, "+FLAGS", "\\Deleted")
                box.expunge()
                box.logout()
                return "was filed in SPAM — RESCUED to Inbox (Gmail is learning)"
            box.logout()
            return "accepted (not yet filed — check All Mail if missing)"
        except Exception as exc:
            return f"accepted (verify unavailable: {exc.__class__.__name__})"

    # RETRY on transient failure — one shot at 07:30 sharp can lose a day's nap email
    # to a network blip (suspected 2026-07-04). The API client retries; so does this now.
    import time
    for attempt in range(3):
        try:
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.login(sender, password)
                smtp.sendmail(sender, recipient, msg.as_string())
            return _verify_and_rescue()
        except smtplib.SMTPAuthenticationError:
            return False                      # bad credentials — retrying won't help
        except (smtplib.SMTPException, OSError):
            time.sleep(2 * (attempt + 1))
    return False


def main() -> int:
    """SELF-TEST — `python -m racing_edge.report.mail` sends a timestamped test
    through the EXACT nap path (SMTP retry + IMAP verify + spam rescue) and prints
    the verdict. Born 2026-07-22 ('test it'): proving delivery must be one command,
    not a day of waiting for the scheduler."""
    from datetime import datetime

    try:                                       # load .env like the tasks do — but only
        from dotenv import load_dotenv         # the email vars matter for this test
        load_dotenv()
    except ImportError:
        pass
    if not configured():
        print("  ✗ EMAIL NOT CONFIGURED — EMAIL_SENDER / EMAIL_PASSWORD / "
              "EMAIL_RECIPIENT missing from .env")
        return 1
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"  sending test to {recipient()} …", flush=True)
    verdict = send(f"TEST — racing-edge email path ({stamp})",
                   f"Test sent {stamp} UTC through the live nap email path.\n"
                   "If you are reading this, delivery works end to end.",
                   title="Email self-test", subtitle="racing-edge")
    if verdict:
        print(f"  ✓ {verdict}")
        return 0
    print("  ✗ SEND FAILED — SMTP refused (auth error or repeated network failure). "
          "Check EMAIL_PASSWORD (Gmail app password) in .env.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
