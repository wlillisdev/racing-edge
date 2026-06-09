"""
daily_pipeline.py — Orchestrate the morning pipeline.

Runs each script in order via subprocess, logs every step, and writes a
summary report regardless of individual step outcomes.

Usage:
    python daily_pipeline.py          # normal run (skips run_daily.py if racecard
                                      # exists and was fetched within 4 hours)
    python daily_pipeline.py --force  # force re-fetch even if racecard is fresh

Pipeline order:
    1. run_daily.py
    2. market_snapshot.py morning
    3. custom_signposts.py
    4. race_shortlist.py
    5. race_reader.py
    6. full_form_reader.py
    7. trainer_profile_reader.py
    8. nap_selector_v3.py
    9. cluster_review.py
    10. morning_briefing_report.py
    11. email_report.py

Exit codes:
    0  — all steps passed (or non-fatal failures were logged)
    1  — pipeline could not start (config error, etc.)
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.config import get_config
from src.helpers import data_path, log, report_path, safe_load_json, today_str


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# How recently a racecard must have been fetched to skip run_daily.py.
RACECARD_FRESHNESS_HOURS: float = 4.0

# Pipeline definition: (display_name, script_path, extra_args)
PIPELINE_STEPS: list[tuple[str, str, list[str]]] = [
    ("run_daily",              "run_daily.py",             []),
    ("market_snapshot_morning","market_snapshot.py",       ["morning"]),
    ("custom_signposts",       "custom_signposts.py",      []),
    ("race_shortlist",         "race_shortlist.py",        []),
    ("race_reader",            "race_reader.py",           []),
    ("full_form_reader",       "full_form_reader.py",      []),
    ("trainer_profile_reader", "trainer_profile_reader.py",[]),
    ("form_reader_ai",         "form_reader_ai.py",        []),
    ("race_shape_ai",          "race_shape_ai.py",         []),
    ("nap_selector_v3",        "nap_selector_v3.py",       []),
    ("nap_arbiter_ai",         "nap_arbiter_ai.py",        []),
    ("cluster_review",         "cluster_review.py",        []),
    ("morning_briefing_report","morning_briefing_report.py",[]),
    ("briefing_writer_ai",     "briefing_writer_ai.py",    []),
    ("email_report",           "email_report.py",          []),
]


# ---------------------------------------------------------------------------
# Freshness check
# ---------------------------------------------------------------------------

def _racecard_is_fresh(date_str: str) -> bool:
    """Return True if today's racecard exists and was fetched within the
    freshness window (RACECARD_FRESHNESS_HOURS)."""
    racecard_path = data_path(f"racecards_{date_str}.json")
    if not Path(racecard_path).exists():
        return False

    data = safe_load_json(racecard_path)
    if data is None:
        return False

    fetched_at_str: Optional[str] = data.get("fetched_at")
    if not fetched_at_str:
        return False

    try:
        fetched_at = datetime.fromisoformat(fetched_at_str)
        # Normalise to UTC-aware if necessary.
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        age_hours = (now - fetched_at).total_seconds() / 3600
        return age_hours < RACECARD_FRESHNESS_HOURS
    except (ValueError, TypeError) as exc:
        log(f"daily_pipeline: could not parse fetched_at '{fetched_at_str}' — {exc}", "WARNING")
        return False


# ---------------------------------------------------------------------------
# Step runner
# ---------------------------------------------------------------------------

def _run_step(
    step_name: str,
    script: str,
    args: list[str],
    project_dir: str,
) -> dict:
    """Run a single pipeline step as a subprocess.

    Returns a result dict with keys:
        step, script, args, started_at, finished_at, duration_s,
        returncode, status ("PASS" | "FAIL")
    """
    script_path = str(Path(project_dir) / script)
    cmd = [sys.executable, script_path] + args

    log(f"daily_pipeline: [{step_name}] starting — {' '.join(cmd)}")
    started_at = datetime.now(timezone.utc)

    try:
        result = subprocess.run(
            cmd,
            cwd=project_dir,
            capture_output=False,   # let stdout/stderr flow to the task log
            timeout=600,            # 10-minute hard cap per step
        )
        returncode = result.returncode
    except subprocess.TimeoutExpired:
        log(f"daily_pipeline: [{step_name}] TIMEOUT after 600 s", "ERROR")
        returncode = -1
    except OSError as exc:
        log(f"daily_pipeline: [{step_name}] OS error — {exc}", "ERROR")
        returncode = -1

    finished_at = datetime.now(timezone.utc)
    duration_s = round((finished_at - started_at).total_seconds(), 2)
    status = "PASS" if returncode == 0 else "FAIL"

    log(
        f"daily_pipeline: [{step_name}] {status} "
        f"(rc={returncode}, duration={duration_s}s)"
    )

    return {
        "step": step_name,
        "script": script,
        "args": args,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_s": duration_s,
        "returncode": returncode,
        "status": status,
    }


# ---------------------------------------------------------------------------
# Summary writers
# ---------------------------------------------------------------------------

def _write_text_summary(date_str: str, results: list[dict], total_s: float) -> None:
    lines: list[str] = [
        "MORNING PIPELINE SUMMARY",
        f"Date: {date_str}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Total duration: {total_s:.1f}s",
        "",
        f"{'#':<4} {'Step':<30} {'Status':<6} {'Duration':>10}  RC",
        "-" * 60,
    ]

    for idx, r in enumerate(results, start=1):
        lines.append(
            f"{idx:<4} {r['step']:<30} {r['status']:<6} "
            f"{r['duration_s']:>8.1f}s  {r['returncode']}"
        )

    pass_count = sum(1 for r in results if r["status"] == "PASS")
    fail_count = len(results) - pass_count
    lines += [
        "",
        f"PASS: {pass_count}  FAIL: {fail_count}  TOTAL: {len(results)}",
    ]

    txt_path = report_path(f"pipeline_morning_{date_str}.txt")
    try:
        with open(txt_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        log(f"daily_pipeline: text summary saved to {txt_path}")
    except OSError as exc:
        log(f"daily_pipeline: failed to write text summary — {exc}", "ERROR")


def _write_json_summary(date_str: str, results: list[dict], total_s: float) -> None:
    doc = {
        "date": date_str,
        "pipeline": "morning",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_duration_s": total_s,
        "pass_count": sum(1 for r in results if r["status"] == "PASS"),
        "fail_count": sum(1 for r in results if r["status"] == "FAIL"),
        "steps": results,
    }
    json_path = data_path(f"pipeline_morning_{date_str}.json")
    try:
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)
        log(f"daily_pipeline: JSON summary saved to {json_path}")
    except (OSError, TypeError) as exc:
        log(f"daily_pipeline: failed to write JSON summary — {exc}", "ERROR")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Run the morning pipeline. Returns exit code."""
    log("daily_pipeline.py started")

    force = "--force" in sys.argv
    date_str = today_str()

    # --- Config -----------------------------------------------------------------
    try:
        cfg = get_config()
        project_dir = cfg.project_dir
    except KeyError as exc:
        log(f"daily_pipeline: missing configuration key — {exc}", "ERROR")
        return 1

    log(f"daily_pipeline: project_dir={project_dir}, date={date_str}, force={force}")

    # --- Freshness check for run_daily.py ---------------------------------------
    skip_run_daily = False
    if not force and _racecard_is_fresh(date_str):
        log(
            f"daily_pipeline: racecard is fresh (< {RACECARD_FRESHNESS_HOURS}h old) — "
            "skipping run_daily.py (use --force to override)"
        )
        skip_run_daily = True

    # Steps that gate all downstream work. If these fail, skip data-processing
    # steps (no racecard = no point scoring runners), but always run the email.
    CRITICAL_GATE_STEPS: frozenset[str] = frozenset({"run_daily"})
    # Steps that always run regardless (email must always fire so the operator
    # is notified of failures even when the pipeline partially breaks).
    ALWAYS_RUN_STEPS: frozenset[str] = frozenset({"email_report"})

    # --- Run pipeline -----------------------------------------------------------
    pipeline_start = datetime.now(timezone.utc)
    results: list[dict] = []
    gate_failed = False  # Set True when a critical gate step fails

    for step_name, script, args in PIPELINE_STEPS:
        # Apply freshness skip only to run_daily.
        if step_name == "run_daily" and skip_run_daily:
            log(f"daily_pipeline: [run_daily] SKIPPED (racecard fresh)")
            results.append({
                "step": step_name,
                "script": script,
                "args": args,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "duration_s": 0.0,
                "returncode": 0,
                "status": "SKIPPED",
            })
            continue

        # Skip data-processing steps when the racecard gate failed.
        # email_report always runs so the operator is notified.
        if gate_failed and step_name not in ALWAYS_RUN_STEPS:
            log(f"daily_pipeline: [{step_name}] SKIPPED — upstream gate failed (no racecard data)")
            results.append({
                "step": step_name, "script": script, "args": args,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "duration_s": 0.0, "returncode": 0, "status": "SKIPPED",
            })
            continue

        result = _run_step(step_name, script, args, project_dir)
        results.append(result)

        if result["status"] == "FAIL":
            log(
                f"daily_pipeline: [{step_name}] returned non-zero exit code "
                f"{result['returncode']} — continuing pipeline",
                "ERROR",
            )
            if step_name in CRITICAL_GATE_STEPS:
                log(
                    f"daily_pipeline: [{step_name}] is a critical gate — "
                    "skipping data-processing steps (email will still fire)",
                    "ERROR",
                )
                gate_failed = True

    pipeline_end = datetime.now(timezone.utc)
    total_s = round((pipeline_end - pipeline_start).total_seconds(), 2)

    pass_count = sum(1 for r in results if r["status"] in ("PASS", "SKIPPED"))
    fail_count = sum(1 for r in results if r["status"] == "FAIL")

    log(
        f"daily_pipeline: pipeline complete — "
        f"PASS/SKIP={pass_count}, FAIL={fail_count}, duration={total_s}s"
    )

    # --- Write summaries --------------------------------------------------------
    _write_text_summary(date_str, results, total_s)
    _write_json_summary(date_str, results, total_s)

    # Treat as success even if some non-critical steps failed; the email step
    # always runs regardless, so the operator is always informed.
    return 0


if __name__ == "__main__":
    sys.exit(main())
