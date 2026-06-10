"""
ops.py — operational reliability utilities (heartbeat + run health).

Two small, dependency-light primitives that turn silent failures into loud,
visible ones:

1. HEARTBEAT (dead-man's switch)
   Each pipeline pings a configured URL ONLY when it finishes successfully.
   An external monitor (e.g. healthchecks.io or cron-job.org) is configured to
   email YOU if that ping does not arrive by a deadline. Because the monitor
   lives OFF PythonAnywhere, it fires even when the run never starts at all
   (wrong interpreter, CPU quota, disabled task) — the exact failure mode that
   produces total silence today. If no URL is configured the ping is a no-op,
   so this is safe to ship disabled.

2. RUN HEALTH
   The pipeline records which steps passed/failed to a small JSON file BEFORE
   the email step runs, so the email can tag a DEGRADED run instead of sending
   a confident-looking briefing built on broken upstream data.

Neither function ever raises into the pipeline.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.helpers import data_path, log, safe_load_json

# Env var names for the per-pipeline heartbeat ping URLs.
_HEARTBEAT_ENV = {
    "morning": "HEARTBEAT_URL_MORNING",
    "evening": "HEARTBEAT_URL_EVENING",
}


def heartbeat(stage: str) -> bool:
    """Ping the dead-man's-switch URL for *stage* ("morning"|"evening").

    Returns True if a ping was sent and accepted, False if no URL is configured
    or the ping failed. Never raises — a monitoring ping must not break a run.
    """
    env_name = _HEARTBEAT_ENV.get(stage)
    url = os.environ.get(env_name, "").strip() if env_name else ""
    if not url:
        log(f"ops.heartbeat: no {env_name} configured — skipping ping", "INFO")
        return False
    try:
        import requests  # local import: keep ops importable even if requests is absent

        requests.get(url, timeout=10)
        log(f"ops.heartbeat: pinged {stage} heartbeat OK")
        return True
    except Exception as exc:  # never let a monitoring ping break the pipeline
        log(f"ops.heartbeat: ping failed for {stage} — {exc}", "WARNING")
        return False


def _health_path(stage: str, date_str: str) -> str:
    return data_path(f"run_health_{stage}_{date_str}.json")


def write_run_health(stage: str, date_str: str, results: list[dict]) -> None:
    """Persist per-step pass/fail status so the email step can flag a DEGRADED run.

    *results* is the pipeline's list of step dicts (each has 'step' and 'status').
    Called just BEFORE the email step runs. Never raises.
    """
    failed = [r.get("step") for r in results if r.get("status") == "FAIL"]
    doc = {
        "stage": stage,
        "date": date_str,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fail_count": len(failed),
        "failed_steps": failed,
        "total_steps": len(results),
    }
    try:
        with open(_health_path(stage, date_str), "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)
    except (OSError, TypeError) as exc:
        log(f"ops.write_run_health: could not write health file — {exc}", "WARNING")


def read_run_health(stage: str, date_str: str) -> Optional[dict]:
    """Return the run-health doc for *stage*/*date*, or None if absent.

    Absent is normal when an email script is run by hand (outside the pipeline);
    callers treat None as "assume healthy" to preserve existing behaviour.
    """
    doc = safe_load_json(_health_path(stage, date_str))
    return doc if isinstance(doc, dict) else None


def degraded_banner(stage: str, date_str: str) -> str:
    """Return a prominent banner string if the run was degraded, else ''.

    Used by the email scripts to prepend a warning to the body.
    """
    health = read_run_health(stage, date_str)
    if not health or not health.get("fail_count"):
        return ""
    failed = ", ".join(str(s) for s in (health.get("failed_steps") or [])) or "unknown"
    bar = "!" * 60
    return (
        f"{bar}\n"
        f"  ⚠ DEGRADED RUN — {health['fail_count']} of {health.get('total_steps','?')} "
        f"pipeline steps FAILED\n"
        f"  Failed: {failed}\n"
        f"  Treat the content below with caution — it may be stale or incomplete.\n"
        f"{bar}\n\n"
    )


def degraded_subject_tag(stage: str, date_str: str) -> str:
    """Return ' [DEGRADED: N failed]' for the email subject, or '' if healthy."""
    health = read_run_health(stage, date_str)
    if not health or not health.get("fail_count"):
        return ""
    return f" [DEGRADED: {health['fail_count']} failed]"
