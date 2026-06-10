"""
preflight.py — fail-loud environment self-check, run BEFORE the real work.

The system has repeatedly died silently because the scheduled task ran an
interpreter that was missing dependencies (cron used venv/bin/python without
python-dotenv, so `import dotenv` raised at import time, before main() — no
email, no log the operator would see). This script catches that entire class
of failure and SHOUTS about it via email instead.

It verifies, in order of how fundamental they are:
    1. The running interpreter can import every mandatory dependency.
    2. Config loads and every mandatory env var is present.
    3. The database is reachable.
    4. The Racing API host is reachable + credentials present.   (WARN-only)
    5. SMTP login works (so alerts/briefings can actually send). (WARN-only)
    6. The Anthropic key is present.                             (WARN-only)

CRITICAL failures (1-3) mean the pipeline cannot produce a correct briefing,
so preflight emails a loud alert and exits non-zero — the caller aborts.
WARN failures (4-6) are surfaced but do not block: the pipeline degrades
gracefully (e.g. AI layer off, API hiccup) and still produces a useful run.

Usage:
    python preflight.py            # standalone — prints report, exit 0/1
    from preflight import run_preflight ; ok = run_preflight("morning")

Exit codes:
    0 — all critical checks passed (warnings may exist)
    1 — a critical check failed (an alert email was attempted)
"""

from __future__ import annotations

import importlib
import sys
from datetime import datetime

# NOTE: deliberately minimal imports at module top so this file itself loads
# even on a broken interpreter. We must NOT import src.* at module load (or at
# the top of run_preflight): src.helpers calls get_config() at import time,
# which imports dotenv — the very dependency this script exists to catch. So
# preflight has its own self-contained logger and imports src.* only lazily,
# inside try/except, after the dependency check.


def _log(msg: str, level: str = "INFO") -> None:
    """Self-contained logger — no src.* imports, so it works on a broken env."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts} [{level.upper()}] {msg}", flush=True)

# (dependency import name, friendly name)
_REQUIRED_MODULES = [
    ("dotenv", "python-dotenv"),
    ("requests", "requests"),
    ("mysql.connector", "mysql-connector-python"),
    ("anthropic", "anthropic"),
    ("tabulate", "tabulate"),
]


def _check_dependencies() -> list[str]:
    """Return a list of human-readable failures for any missing dependency."""
    failures: list[str] = []
    for module_name, friendly in _REQUIRED_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # ImportError or anything during import
            failures.append(
                f"cannot import '{module_name}' ({friendly}) — {exc}. "
                f"This interpreter ({sys.executable}) is missing dependencies; "
                f"run: {sys.executable} -m pip install -r requirements.txt"
            )
    return failures


def _check_config() -> tuple[list[str], object]:
    """Confirm config loads with all mandatory keys. Returns (failures, cfg|None)."""
    try:
        from src.config import get_config

        cfg = get_config()
        return [], cfg
    except KeyError as exc:
        return [f"missing mandatory env var {exc} (check .env)"], None
    except Exception as exc:
        return [f"config failed to load — {exc}"], None


def _check_database() -> list[str]:
    """Confirm the database is reachable with a trivial query."""
    try:
        from src.db import get_db

        row = get_db().fetch_one("SELECT 1 AS ok")
        if not row or row.get("ok") != 1:
            return ["database query returned an unexpected result"]
        return []
    except Exception as exc:
        return [f"database unreachable — {exc}"]


def _check_racing_api(cfg) -> list[str]:
    """WARN-only: confirm the Racing API host is reachable + creds present."""
    if not getattr(cfg, "racing_api_username", "") or not getattr(cfg, "racing_api_password", ""):
        return ["Racing API credentials absent (RACING_API_USERNAME/PASSWORD)"]
    try:
        import requests

        # Any HTTP response (even 401/404) proves DNS+TLS+host reachability.
        resp = requests.get(
            cfg.racing_api_base,
            auth=(cfg.racing_api_username, cfg.racing_api_password),
            timeout=15,
        )
        if resp.status_code >= 500:
            return [f"Racing API host returned {resp.status_code} (server-side)"]
        return []
    except Exception as exc:
        return [f"Racing API host unreachable — {exc}"]


def _check_smtp(cfg) -> list[str]:
    """WARN-only: confirm we can log in to SMTP (no message is sent)."""
    try:
        import smtplib

        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(cfg.email_sender, cfg.email_password)
        return []
    except Exception as exc:
        return [f"SMTP login failed — {exc} (briefings/alerts may not send)"]


def _check_anthropic(cfg) -> list[str]:
    """WARN-only: the AI layer needs a key; absence just disables overlays."""
    if not getattr(cfg, "anthropic_api_key", ""):
        return ["ANTHROPIC_API_KEY absent — AI layer will be disabled"]
    return []


def run_preflight(stage: str = "manual") -> bool:
    """Run all checks. Returns True if all CRITICAL checks passed.

    On a critical failure, attempts to email a loud alert before returning
    False so the caller can abort.
    """
    _log(f"preflight: starting ({stage})")
    critical: list[str] = []
    warnings: list[str] = []

    # 1. Dependencies (most fundamental — do this first).
    dep_failures = _check_dependencies()
    critical += dep_failures

    # 2. Config (only meaningful if deps loaded; still safe to attempt).
    cfg = None
    if not dep_failures:
        cfg_failures, cfg = _check_config()
        critical += cfg_failures

    # 3. Database (critical — no DB, no real briefing).
    if cfg is not None:
        critical += _check_database()
        # 4-6 are WARN-only.
        warnings += _check_racing_api(cfg)
        warnings += _check_smtp(cfg)
        warnings += _check_anthropic(cfg)

    # --- Report ---------------------------------------------------------------
    sep = "=" * 60
    print(sep)
    print(f"  PREFLIGHT SELF-CHECK ({stage})")
    print(f"  Interpreter: {sys.executable}")
    print(sep)
    if not critical and not warnings:
        print("  ✅ ALL CHECKS PASSED")
    if critical:
        print(f"  ❌ CRITICAL ({len(critical)}):")
        for c in critical:
            print(f"     • {c}")
    if warnings:
        print(f"  ⚠ WARNINGS ({len(warnings)}) — non-blocking:")
        for w in warnings:
            print(f"     • {w}")
    print(sep)

    for c in critical:
        _log(f"preflight CRITICAL: {c}", "ERROR")
    for w in warnings:
        _log(f"preflight WARNING: {w}", "WARNING")

    if critical:
        # Best-effort loud alert. If deps/config are the very thing broken,
        # the mailer may also fail — that's why the off-box heartbeat exists.
        try:
            from src.mailer import send_alert

            detail = (
                f"Pipeline stage: {stage}\n"
                f"Interpreter: {sys.executable}\n\n"
                "CRITICAL preflight failures (run aborted):\n"
                + "\n".join(f"  • {c}" for c in critical)
                + ("\n\nWarnings:\n" + "\n".join(f"  • {w}" for w in warnings) if warnings else "")
            )
            send_alert(f"PREFLIGHT FAILED ({stage})", detail)
        except Exception as exc:
            _log(f"preflight: could not send alert email — {exc}", "ERROR")
        return False

    _log(f"preflight: passed ({len(warnings)} warning(s))")
    return True


def main() -> int:
    stage = sys.argv[1] if len(sys.argv) > 1 else "manual"
    return 0 if run_preflight(stage) else 1


if __name__ == "__main__":
    sys.exit(main())
