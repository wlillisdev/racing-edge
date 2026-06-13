"""
mailer.py — one safe, reusable SMTP send path for the whole system.

Both the briefing emails and the new reliability alerts (preflight failures,
degraded-run notices) need to send mail the same way. Historically the SMTP
code was copy-pasted into email_report.py and email_audit.py; this module is
the single place that talks to the SMTP server so alerts and briefings can
never drift apart.

Design contract:
    - send_email() NEVER raises. It returns True on success, False on any
      failure (config missing, SMTP error, network error), logging the cause.
      A reliability alert must not itself crash the thing trying to warn you.
"""

from __future__ import annotations

import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from src.config import get_config
from src.helpers import log


def send_email(subject: str, body: str, html_body: Optional[str] = None) -> bool:
    """Send an email via the configured SMTP/TLS server.

    When `html_body` is given the message is sent as multipart/alternative:
    `body` is the plain-text fallback and `html_body` the rich version, so a
    client that blocks HTML still shows the readable text. Plain-text-only
    callers (alerts) pass `body` alone and behaviour is unchanged.

    Returns True if the message was accepted by the server, False otherwise.
    Never raises — callers (including alert paths) can rely on a bool.
    """
    try:
        cfg = get_config()
    except KeyError as exc:
        log(f"mailer: cannot send — missing config key {exc}", "ERROR")
        return False

    msg: MIMEText | MIMEMultipart
    if html_body:
        msg = MIMEMultipart("alternative")
        # Order matters: clients render the LAST part they can display, so the
        # plain-text fallback must come first and the HTML version last.
        msg.attach(MIMEText(body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))
    else:
        msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = cfg.email_sender
    msg["To"] = cfg.email_recipient

    try:
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(cfg.email_sender, cfg.email_password)
            smtp.sendmail(cfg.email_sender, cfg.email_recipient, msg.as_string())
    except smtplib.SMTPException as exc:
        log(f"mailer: SMTP error — {exc}", "ERROR")
        return False
    except OSError as exc:
        log(f"mailer: network/OS error — {exc}", "ERROR")
        return False

    log(f"mailer: sent '{subject}' to {cfg.email_recipient}")
    return True


def send_alert(short_reason: str, detail: str) -> bool:
    """Send a loud, clearly-flagged operational alert email.

    Used by preflight and the pipelines so a broken run shouts instead of
    failing silently. The subject is deliberately alarming and greppable.
    """
    subject = f"🚨 RACING SYSTEM ALERT — {short_reason}"
    body = (
        "RACING INTELLIGENCE — OPERATIONAL ALERT\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"{detail}\n\n"
        "---\n"
        "This is an automated reliability alert. The daily run did not\n"
        "complete cleanly — see the detail above and the task log.\n"
    )
    return send_email(subject, body)
