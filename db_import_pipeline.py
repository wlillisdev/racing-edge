"""
db_import_pipeline.py — Orchestrate the 21:00 database import chain.

Replaces the raw shell chain
    db_import_racecards.py && db_import_model_candidates.py && ...
which had two silent-failure modes: a failed first step stopped the rest
without any alert, and a "successful" run that imported nothing looked
identical to a healthy one. This orchestrator runs every importer regardless
of earlier failures, emails an alert when anything fails, and pings the
"db" heartbeat honestly (success URL only on a clean run).

PythonAnywhere scheduled task (21:00):
    /home/<user>/racing-edge/venv/bin/python /home/<user>/racing-edge/db_import_pipeline.py

Exit codes:
    0 — all imports passed
    1 — one or more imports failed (alert attempted)
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.config import get_config
from src.helpers import log, today_str
from src.ops import heartbeat

PIPELINE_STEPS: list[tuple[str, str]] = [
    ("db_import_racecards",        "db_import_racecards.py"),
    ("db_import_model_candidates", "db_import_model_candidates.py"),
    ("db_import_market_moves",     "db_import_market_moves.py"),
    ("db_import_results",          "db_import_results.py"),
]


def _run_step(step_name: str, script: str, project_dir: str) -> dict:
    cmd = [sys.executable, str(Path(project_dir) / script)]
    log(f"db_import_pipeline: [{step_name}] starting")
    started_at = datetime.now(timezone.utc)
    try:
        result = subprocess.run(cmd, cwd=project_dir, capture_output=False, timeout=600)
        returncode = result.returncode
    except subprocess.TimeoutExpired:
        log(f"db_import_pipeline: [{step_name}] TIMEOUT after 600 s", "ERROR")
        returncode = -1
    except OSError as exc:
        log(f"db_import_pipeline: [{step_name}] OS error — {exc}", "ERROR")
        returncode = -1
    duration_s = round((datetime.now(timezone.utc) - started_at).total_seconds(), 2)
    status = "PASS" if returncode == 0 else "FAIL"
    log(f"db_import_pipeline: [{step_name}] {status} (rc={returncode}, {duration_s}s)")
    return {"step": step_name, "returncode": returncode, "status": status,
            "duration_s": duration_s}


def main() -> int:
    log("db_import_pipeline.py started")
    date_str = today_str()
    try:
        project_dir = get_config().project_dir
    except KeyError as exc:
        log(f"db_import_pipeline: missing configuration key — {exc}", "ERROR")
        return 1

    # Run ALL importers even when one fails — they are independent, and the
    # old && chain meant one bad import silently starved every later table.
    results = [_run_step(name, script, project_dir) for name, script in PIPELINE_STEPS]
    failed = [r["step"] for r in results if r["status"] == "FAIL"]

    if failed:
        log(f"db_import_pipeline: {len(failed)} import(s) FAILED — {', '.join(failed)}", "ERROR")
        try:
            from src.mailer import send_alert
            send_alert(
                f"DB IMPORT: {len(failed)} step(s) FAILED",
                f"Date: {date_str}\nFailed: {', '.join(failed)}\n"
                "The learning database is not accumulating for these tables. "
                "Check the 21:00 task log on PythonAnywhere.",
            )
        except Exception as exc:
            log(f"db_import_pipeline: could not send failure alert — {exc}", "ERROR")

    heartbeat("db", ok=not failed)
    print(f"db_import_pipeline: {'ALL PASS' if not failed else 'FAILED: ' + ', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
