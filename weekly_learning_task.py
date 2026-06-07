"""
weekly_learning_task.py — Orchestrate all end-of-week learning tasks.

CRITICAL: Sunday-only guard.
The FIRST line of main logic checks today's weekday.  If it is not Sunday
(weekday() == 6), the script exits with code 0 immediately.  This prevents
accidental mid-week execution of learning tasks that assume a full week
of data is available.

Tasks run in order (each via subprocess — non-zero exit is logged but
does NOT abort the remaining tasks):
    1. weekly_learning_report.py
    2. horse_tracker.py --review       (review mode summary)
    3. horse_tracker_promoter.py
    4. profit_report.py
    5. db_import_results.py            (optional — logged if not found)
    6. Weekly completion summary print

Output:
    reports/weekly_tasks_summary_YYYY-MM-DD.txt

Exit codes:
    0 — always (individual failures are logged, not propagated)
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.config import get_config
from src.helpers import log, report_path, today_str


# ---------------------------------------------------------------------------
# Task definitions
# ---------------------------------------------------------------------------

# Each entry: (display_name, script_filename, extra_args)
WEEKLY_TASKS: list[tuple[str, str, list[str]]] = [
    ("weekly_learning_report",  "weekly_learning_report.py",  []),
    ("horse_tracker_review",    "horse_tracker.py",            ["--review"]),
    ("horse_tracker_promoter",  "horse_tracker_promoter.py",  []),
    ("profit_report",           "profit_report.py",            []),
    ("db_import_results",       "db_import_results.py",        []),
]


# ---------------------------------------------------------------------------
# Step runner
# ---------------------------------------------------------------------------

def _run_task(
    task_name: str,
    script: str,
    args: list[str],
    project_dir: str,
) -> dict:
    """Run a single task script via subprocess.

    Returns a result dict with:
        task, script, args, started_at, finished_at, duration_s,
        returncode, status ("PASS" | "FAIL" | "SKIP")
    """
    script_path = Path(project_dir) / script

    if not script_path.exists():
        log(
            f"weekly_learning_task: [{task_name}] script not found — "
            f"{script_path} — SKIP",
            "WARNING",
        )
        now_iso = datetime.now(timezone.utc).isoformat()
        return {
            "task":         task_name,
            "script":       script,
            "args":         args,
            "started_at":   now_iso,
            "finished_at":  now_iso,
            "duration_s":   0.0,
            "returncode":   None,
            "status":       "SKIP",
            "note":         "Script not found",
        }

    cmd = [sys.executable, str(script_path)] + args
    log(f"weekly_learning_task: [{task_name}] starting — {' '.join(str(c) for c in cmd)}")
    started_at = datetime.now(timezone.utc)

    returncode: int
    try:
        result = subprocess.run(
            cmd,
            cwd=project_dir,
            capture_output=False,   # let stdout/stderr flow to the task log
            timeout=600,            # 10-minute hard cap per task
        )
        returncode = result.returncode
    except subprocess.TimeoutExpired:
        log(f"weekly_learning_task: [{task_name}] TIMEOUT after 600s", "ERROR")
        returncode = -1
    except OSError as exc:
        log(f"weekly_learning_task: [{task_name}] OS error — {exc}", "ERROR")
        returncode = -1

    finished_at = datetime.now(timezone.utc)
    duration_s = round((finished_at - started_at).total_seconds(), 2)
    status = "PASS" if returncode == 0 else "FAIL"

    log(
        f"weekly_learning_task: [{task_name}] {status} "
        f"(rc={returncode}, duration={duration_s}s)"
    )
    if status == "FAIL":
        log(
            f"weekly_learning_task: [{task_name}] returned non-zero "
            f"({returncode}) — continuing",
            "ERROR",
        )

    return {
        "task":         task_name,
        "script":       script,
        "args":         args,
        "started_at":   started_at.isoformat(),
        "finished_at":  finished_at.isoformat(),
        "duration_s":   duration_s,
        "returncode":   returncode,
        "status":       status,
    }


# ---------------------------------------------------------------------------
# Summary writers
# ---------------------------------------------------------------------------

def _write_summary_report(date_str: str, results: list[dict], total_s: float) -> None:
    """Write the weekly tasks summary to a text file."""
    lines: list[str] = [
        "WEEKLY TASKS SUMMARY",
        f"Date: {date_str} (Sunday)",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Total duration: {total_s:.1f}s",
        "",
        f"{'#':<4} {'Task':<30} {'Status':<6} {'Duration':>10}  RC",
        "-" * 62,
    ]

    for idx, r in enumerate(results, start=1):
        rc_str = str(r["returncode"]) if r["returncode"] is not None else "N/A"
        lines.append(
            f"{idx:<4} {r['task']:<30} {r['status']:<6} "
            f"{r['duration_s']:>8.1f}s  {rc_str}"
        )
        if "note" in r:
            lines.append(f"       Note: {r['note']}")

    pass_count  = sum(1 for r in results if r["status"] == "PASS")
    fail_count  = sum(1 for r in results if r["status"] == "FAIL")
    skip_count  = sum(1 for r in results if r["status"] == "SKIP")

    lines += [
        "",
        f"PASS: {pass_count}  FAIL: {fail_count}  SKIP: {skip_count}  TOTAL: {len(results)}",
        "",
        "Weekly learning cycle complete.",
    ]

    report_dest = report_path(f"weekly_tasks_summary_{date_str}.txt")
    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        log(f"weekly_learning_task: summary saved → {report_dest}")
    except OSError as exc:
        log(f"weekly_learning_task: failed to write summary — {exc}", "ERROR")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Run all weekly learning tasks (Sunday only). Returns 0 always."""

    # CRITICAL: Sunday guard — weekday 6 is Sunday.
    # This must be the first check in main() before any other logic.
    from datetime import datetime as _dt
    if _dt.today().weekday() != 6:
        day_name = _dt.today().strftime("%A")
        msg = (
            f"Weekly learning tasks run on Sundays only. "
            f"Today is {day_name}. Skipping."
        )
        print(msg)
        log(msg, "INFO")
        return 0

    log("weekly_learning_task.py started — Sunday confirmed")

    date_str = today_str()

    # --- Resolve project dir ---
    try:
        cfg = get_config()
        project_dir = cfg.project_dir
    except KeyError as exc:
        log(f"weekly_learning_task: missing configuration key — {exc}", "ERROR")
        # Still attempt to proceed with cwd as fallback
        project_dir = str(Path(__file__).parent)

    log(f"weekly_learning_task: project_dir={project_dir}, date={date_str}")

    # --- Run all tasks --------------------------------------------------
    pipeline_start = datetime.now(timezone.utc)
    results: list[dict] = []

    for task_name, script, args in WEEKLY_TASKS:
        result = _run_task(task_name, script, args, project_dir)
        results.append(result)

    pipeline_end = datetime.now(timezone.utc)
    total_s = round((pipeline_end - pipeline_start).total_seconds(), 2)

    # --- Tally outcomes ---
    pass_count  = sum(1 for r in results if r["status"] == "PASS")
    fail_count  = sum(1 for r in results if r["status"] == "FAIL")
    skip_count  = sum(1 for r in results if r["status"] == "SKIP")

    log(
        f"weekly_learning_task: all tasks complete — "
        f"PASS={pass_count}, FAIL={fail_count}, SKIP={skip_count}, "
        f"total_duration={total_s:.1f}s"
    )

    # --- Save summary report ---
    _write_summary_report(date_str, results, total_s)

    # --- Console completion summary ---
    print("")
    print("=" * 60)
    print("WEEKLY LEARNING CYCLE COMPLETE")
    print(f"  Date:     {date_str} (Sunday)")
    print(f"  Duration: {total_s:.1f}s")
    print(f"  PASS:     {pass_count}")
    print(f"  FAIL:     {fail_count}")
    print(f"  SKIP:     {skip_count}")
    print("=" * 60)
    for r in results:
        rc_str = str(r["returncode"]) if r["returncode"] is not None else "N/A"
        indicator = "OK" if r["status"] in ("PASS", "SKIP") else "!!"
        print(f"  [{indicator}] {r['task']:<30} {r['status']}  rc={rc_str}")
    print("=" * 60)

    # Always exit 0 — failures in individual tasks are non-fatal for the
    # weekly cycle (they are logged and reported, not propagated).
    return 0


if __name__ == "__main__":
    sys.exit(main())
