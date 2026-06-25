"""
evening_audit_pipeline.py — Orchestrate the evening audit pipeline.

Runs each script in order via subprocess, logs every step, and writes a
summary report regardless of individual step outcomes.

Pipeline order:
    1. results_auditor.py    (with retry: exit code 2 means "not yet available")
    2. performance_tracker.py
    3. profit_report.py
    4. email_audit.py

Retry behaviour for results_auditor.py:
    - Exit code 2 means results are not yet published on the Racing Post / API.
    - Wait 15 minutes and retry, up to 3 total attempts.
    - After all retries are exhausted, log a WARNING and continue the pipeline
      so the email still goes out (reporting what's available).

Exit codes:
    0  — pipeline finished (email always attempted)
    1  — pipeline could not start (config error, etc.)
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src.config import get_config
from src.helpers import data_path, log, report_path, today_str
from src.ops import heartbeat, verify_step_outputs, write_run_health
from preflight import run_preflight


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# results_auditor.py exit code meaning "results not yet available"
RESULTS_NOT_READY_CODE: int = 2

# Retry parameters for results_auditor.py
MAX_RESULTS_RETRIES: int = 3
RESULTS_RETRY_WAIT_S: int = 15 * 60  # 15 minutes

# Pipeline definition: (display_name, script_path, extra_args)
PIPELINE_STEPS: list[tuple[str, str, list[str]]] = [
    ("results_auditor",       "results_auditor.py",       []),
    ("daily_outcome_join",    "daily_outcome_join.py",    []),
    ("race_quality_builder",  "race_quality_builder.py",  []),
    ("performance_tracker",   "performance_tracker.py",   []),
    ("result_enricher",       "result_enricher.py",       []),
    ("loser_autopsy_ai",      "loser_autopsy_ai.py",      []),
    ("daily_learning_analysis","daily_learning_analysis.py",[]),
    ("winner_learning",       "winner_learning_loop.py",  []),
    ("nap_miss_autopsy",      "nap_miss_autopsy.py",      []),
    ("method_scoreboard",     "method_pick_check.py",     []),
    ("edge_tracker",          "edge_tracker.py",          []),
    ("dynamic_bet_settle",    "dynamic_bet.py",           ["--settle"]),
    ("ground_breeding_settle","ground_breeding_signal.py",["--settle"]),
    ("jockey_intent_settle",  "jockey_intent_signal.py",  ["--settle"]),
    ("model_param_tuner",     "model_param_tuner.py",     []),
    ("profit_report",         "profit_report.py",         []),
    ("email_audit",           "email_audit.py",           []),
]

# Expected outputs per step ({d} = date). A step that exits 0 without
# producing these is downgraded to FAIL — exit codes alone let a wiped or
# stubbed script "pass" indefinitely (results_auditor incident).
STEP_OUTPUTS: dict[str, list[str]] = {
    "results_auditor":      ["data/results_{d}.json", "reports/results_audit_{d}.txt"],
    "race_quality_builder": ["data/race_quality_cache.json"],
    "performance_tracker":  ["reports/performance_summary_{d}.txt"],
    "profit_report":        ["reports/profit_report_{d}.txt"],
}


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

    log(f"evening_audit_pipeline: [{step_name}] starting — {' '.join(cmd)}")
    started_at = datetime.now(timezone.utc)

    try:
        result = subprocess.run(
            cmd,
            cwd=project_dir,
            capture_output=False,
            timeout=600,
        )
        returncode = result.returncode
    except subprocess.TimeoutExpired:
        log(f"evening_audit_pipeline: [{step_name}] TIMEOUT after 600 s", "ERROR")
        returncode = -1
    except OSError as exc:
        log(f"evening_audit_pipeline: [{step_name}] OS error — {exc}", "ERROR")
        returncode = -1

    finished_at = datetime.now(timezone.utc)
    duration_s = round((finished_at - started_at).total_seconds(), 2)
    status = "PASS" if returncode == 0 else "FAIL"

    log(
        f"evening_audit_pipeline: [{step_name}] {status} "
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
# results_auditor.py with retry
# ---------------------------------------------------------------------------

def _run_results_auditor(project_dir: str) -> dict:
    """Run results_auditor.py with up to MAX_RESULTS_RETRIES attempts.

    Exit code 2 ("not yet available") triggers a wait-and-retry cycle.
    Any other non-zero exit is treated as a normal FAIL with no retry.

    Returns a consolidated result dict (status reflects the final attempt).
    The dict includes an extra key 'attempts' with the per-attempt records.
    """
    step_name = "results_auditor"
    script    = "results_auditor.py"
    args: list[str] = []

    attempts: list[dict] = []
    overall_started = datetime.now(timezone.utc)

    for attempt in range(1, MAX_RESULTS_RETRIES + 1):
        if attempt > 1:
            wait_min = RESULTS_RETRY_WAIT_S // 60
            log(
                f"evening_audit_pipeline: [{step_name}] attempt {attempt}/{MAX_RESULTS_RETRIES} "
                f"— waiting {wait_min} minutes for results to become available"
            )
            time.sleep(RESULTS_RETRY_WAIT_S)

        log(
            f"evening_audit_pipeline: [{step_name}] attempt {attempt}/{MAX_RESULTS_RETRIES}"
        )
        attempt_result = _run_step(step_name, script, args, project_dir)
        attempt_result["attempt"] = attempt
        attempts.append(attempt_result)

        rc = attempt_result["returncode"]

        if rc == 0:
            log(
                f"evening_audit_pipeline: [{step_name}] succeeded on attempt {attempt}"
            )
            break

        if rc == RESULTS_NOT_READY_CODE:
            if attempt < MAX_RESULTS_RETRIES:
                log(
                    f"evening_audit_pipeline: [{step_name}] results not yet available "
                    f"(rc=2) — will retry",
                    "WARNING",
                )
            else:
                log(
                    f"evening_audit_pipeline: [{step_name}] results still not available "
                    f"after {MAX_RESULTS_RETRIES} attempts — continuing pipeline",
                    "WARNING",
                )
            continue

        # Any other non-zero code: no retry.
        log(
            f"evening_audit_pipeline: [{step_name}] failed with rc={rc} "
            "(not a 'not-ready' code — no retry)",
            "ERROR",
        )
        break

    overall_finished = datetime.now(timezone.utc)
    total_duration = round(
        (overall_finished - overall_started).total_seconds(), 2
    )

    final = attempts[-1]
    return {
        "step":         step_name,
        "script":       script,
        "args":         args,
        "started_at":   overall_started.isoformat(),
        "finished_at":  overall_finished.isoformat(),
        "duration_s":   total_duration,
        "returncode":   final["returncode"],
        "status":       final["status"],
        "attempts":     attempts,
    }


# ---------------------------------------------------------------------------
# Summary writers
# ---------------------------------------------------------------------------

def _write_text_summary(date_str: str, results: list[dict], total_s: float) -> None:
    lines: list[str] = [
        "EVENING AUDIT PIPELINE SUMMARY",
        f"Date: {date_str}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Total duration: {total_s:.1f}s",
        "",
        f"{'#':<4} {'Step':<30} {'Status':<6} {'Duration':>10}  RC",
        "-" * 60,
    ]

    for idx, r in enumerate(results, start=1):
        extra = ""
        if "attempts" in r and len(r["attempts"]) > 1:
            extra = f"  [{len(r['attempts'])} attempts]"
        lines.append(
            f"{idx:<4} {r['step']:<30} {r['status']:<6} "
            f"{r['duration_s']:>8.1f}s  {r['returncode']}{extra}"
        )

    pass_count = sum(1 for r in results if r["status"] == "PASS")
    fail_count = len(results) - pass_count
    lines += [
        "",
        f"PASS: {pass_count}  FAIL: {fail_count}  TOTAL: {len(results)}",
    ]

    txt_path = report_path(f"pipeline_evening_{date_str}.txt")
    try:
        with open(txt_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        log(f"evening_audit_pipeline: text summary saved to {txt_path}")
    except OSError as exc:
        log(f"evening_audit_pipeline: failed to write text summary — {exc}", "ERROR")


def _write_json_summary(date_str: str, results: list[dict], total_s: float) -> None:
    doc = {
        "date": date_str,
        "pipeline": "evening_audit",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_duration_s": total_s,
        "pass_count": sum(1 for r in results if r["status"] == "PASS"),
        "fail_count": sum(1 for r in results if r["status"] == "FAIL"),
        "steps": results,
    }
    json_path = data_path(f"pipeline_evening_{date_str}.json")
    try:
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)
        log(f"evening_audit_pipeline: JSON summary saved to {json_path}")
    except (OSError, TypeError) as exc:
        log(f"evening_audit_pipeline: failed to write JSON summary — {exc}", "ERROR")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Run the evening audit pipeline. Returns exit code."""
    log("evening_audit_pipeline.py started")

    date_str = today_str()

    # --- Config -----------------------------------------------------------------
    try:
        cfg = get_config()
        project_dir = cfg.project_dir
    except KeyError as exc:
        log(f"evening_audit_pipeline: missing configuration key — {exc}", "ERROR")
        return 1

    log(f"evening_audit_pipeline: project_dir={project_dir}, date={date_str}")

    # --- Preflight self-check (fail loud before doing real work) -----------------
    if not run_preflight("evening"):
        log("evening_audit_pipeline: preflight FAILED — aborting run (alert emailed)", "ERROR")
        return 1

    # --- Recover yesterday's results if they never landed -------------------------
    # results_auditor is all-or-nothing per day: if even one race published
    # late, the whole day exited rc=2 and — before this — nothing ever retried,
    # leaving a permanent gap in P/L and learning data after one soft notice.
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    y_results = data_path(f"results_{yesterday}.json")
    y_candidates = data_path(f"nap_candidates_{yesterday}.json")
    if not Path(y_results).exists() and Path(y_candidates).exists():
        log(f"evening_audit_pipeline: results_{yesterday}.json missing — recovery attempt")
        recovery = _run_step("results_auditor_catchup", "results_auditor.py", [yesterday], project_dir)
        log(f"evening_audit_pipeline: yesterday recovery — {recovery['status']}")

    # --- Run pipeline -----------------------------------------------------------
    pipeline_start = datetime.now(timezone.utc)
    results: list[dict] = []

    for step_name, script, args in PIPELINE_STEPS:
        # Record run health just before the email step so the audit email can
        # flag a DEGRADED run instead of looking routine.
        if step_name == "email_audit":
            write_run_health("evening", date_str, results)

        if step_name == "results_auditor":
            # Special case: retry on exit code 2.
            result = _run_results_auditor(project_dir)
        else:
            result = _run_step(step_name, script, args, project_dir)

        # Output-manifest check: a PASS that produced nothing is a FAIL.
        if result["status"] == "PASS" and step_name in STEP_OUTPUTS:
            expected = [
                str(Path(project_dir) / tpl.format(d=date_str))
                for tpl in STEP_OUTPUTS[step_name]
            ]
            started_ts = datetime.fromisoformat(result["started_at"]).timestamp()
            problems = verify_step_outputs(expected, started_ts)
            if problems:
                result["status"] = "FAIL"
                for prob in problems:
                    log(
                        f"evening_audit_pipeline: [{step_name}] output check FAILED — {prob}",
                        "ERROR",
                    )

        results.append(result)

        if result["status"] == "FAIL":
            log(
                f"evening_audit_pipeline: [{step_name}] returned non-zero exit code "
                f"{result['returncode']} — continuing pipeline",
                "ERROR",
            )

    pipeline_end = datetime.now(timezone.utc)
    total_s = round((pipeline_end - pipeline_start).total_seconds(), 2)

    pass_count = sum(1 for r in results if r["status"] == "PASS")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")

    log(
        f"evening_audit_pipeline: pipeline complete — "
        f"PASS={pass_count}, FAIL={fail_count}, duration={total_s}s"
    )

    # --- Write summaries --------------------------------------------------------
    _write_text_summary(date_str, results, total_s)
    _write_json_summary(date_str, results, total_s)

    # --- Heartbeat (dead-man's switch) ------------------------------------------
    # Success ping only when every step genuinely passed; otherwise hit the
    # /fail endpoint so the monitor alerts instead of vouching for a broken run.
    heartbeat("evening", ok=(fail_count == 0))

    return 0


if __name__ == "__main__":
    sys.exit(main())
