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

_REQUIRED = ("EMAIL_SENDER", "EMAIL_PASSWORD", "EMAIL_RECIPIENT")


def configured() -> bool:
    """True only if the SMTP credentials are actually present in the environment."""
    return all(os.environ.get(k) for k in _REQUIRED)


def recipient() -> str:
    """The address mail will go to — so the CLI can show it (check it's really yours)."""
    return os.environ.get("EMAIL_RECIPIENT", "")


def send(subject: str, body: str, title: str = "", subtitle: str = "") -> bool:
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

    try:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(sender, password)
            smtp.sendmail(sender, recipient, msg.as_string())
    except (smtplib.SMTPException, OSError):
        return False
    return True
