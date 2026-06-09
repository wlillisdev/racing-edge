"""
market_update_pipeline.py — Orchestrate the market update pipeline.

Runs each script in order via subprocess, logs every step, and writes a
summary report regardless of individual step outcomes.

Pipeline order:
    1. run_daily.py              (refresh racecard)
    2. market_snapshot.py late
    3. market_movers.py
    4. non_runner_scan.py
    5. final_nap_decision.py
    6. final_decision_guard.py
    7. email_market_update.py

Exit codes:
    0  — pipeline finished (email always attempted)
    1  — pipeline could not start (config error, etc.)
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.config import get_config
from src.helpers import data_path, log, report_path, today_str


# ---------------------------------------------------------------------------
# Pipeline definition
# ---------------------------------------------------------------------------

PIPELINE_STEPS: list[tuple[str, str, list[str]]] = [
    ("run_daily",              "run_daily.py",             []),
    ("market_snapshot_late",   "market_snapshot.py",       ["late"]),
    ("market_movers",          "market_movers.py",         []),
    ("non_runner_scan",        "non_runner_scan.py",       []),
    ("final_nap_decision",     "final_nap_decision.py",    []),
    ("final_decision_guard",   "final_decision_guard.py",  []),
    ("email_market_update",    "email_market_update.py",   []),
]


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

    log(f"market_update_pipeline: [{step_name}] starting — {' '.join(cmd)}")
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
        log(f"market_update_pipeline: [{step_name}] TIMEOUT after 600 s", "ERROR")
        returncode = -1
    except OSError as exc:
        log(f"market_update_pipeline: [{step_name}] OS error — {exc}", "ERROR")
        returncode = -1

    finished_at = datetime.now(timezone.utc)
    duration_s = round((finished_at - started_at).total_seconds(), 2)
    status = "PASS" if returncode == 0 else "FAIL"

    log(
        f"market_update_pipeline: [{step_name}] {status} "
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
        "MARKET UPDATE PIPELINE SUMMARY",
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

    txt_path = report_path(f"pipeline_market_{date_str}.txt")
    try:
        with open(txt_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        log(f"market_update_pipeline: text summary saved to {txt_path}")
    except OSError as exc:
        log(f"market_update_pipeline: failed to write text summary — {exc}", "ERROR")


def _write_json_summary(date_str: str, results: list[dict], total_s: float) -> None:
    doc = {
        "date": date_str,
        "pipeline": "market_update",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_duration_s": total_s,
        "pass_count": sum(1 for r in results if r["status"] == "PASS"),
        "fail_count": sum(1 for r in results if r["status"] == "FAIL"),
        "steps": results,
    }
    json_path = data_path(f"pipeline_market_{date_str}.json")
    try:
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)
        log(f"market_update_pipeline: JSON summary saved to {json_path}")
    except (OSError, TypeError) as exc:
        log(f"market_update_pipeline: failed to write JSON summary — {exc}", "ERROR")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Run the market update pipeline. Returns exit code."""
    log("market_update_pipeline.py started")

    date_str = today_str()

    # --- Config -----------------------------------------------------------------
    try:
        cfg = get_config()
        project_dir = cfg.project_dir
    except KeyError as exc:
        log(f"market_update_pipeline: missing configuration key — {exc}", "ERROR")
        return 1

    log(f"market_update_pipeline: project_dir={project_dir}, date={date_str}")

    CRITICAL_GATE_STEPS: frozenset[str] = frozenset({"run_daily"})
    ALWAYS_RUN_STEPS: frozenset[str] = frozenset({"email_market_update"})

    # --- Run pipeline -----------------------------------------------------------
    pipeline_start = datetime.now(timezone.utc)
    results: list[dict] = []
    gate_failed = False

    for step_name, script, args in PIPELINE_STEPS:
        if gate_failed and step_name not in ALWAYS_RUN_STEPS:
            log(f"market_update_pipeline: [{step_name}] SKIPPED — upstream gate failed")
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
                f"market_update_pipeline: [{step_name}] returned non-zero exit code "
                f"{result['returncode']} — continuing pipeline",
                "ERROR",
            )
            if step_name in CRITICAL_GATE_STEPS:
                log(
                    f"market_update_pipeline: [{step_name}] is critical gate — "
                    "skipping to email step",
                    "ERROR",
                )
                gate_failed = True

    pipeline_end = datetime.now(timezone.utc)
    total_s = round((pipeline_end - pipeline_start).total_seconds(), 2)

    pass_count = sum(1 for r in results if r["status"] == "PASS")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")

    log(
        f"market_update_pipeline: pipeline complete — "
        f"PASS={pass_count}, FAIL={fail_count}, duration={total_s}s"
    )

    # --- Write summaries --------------------------------------------------------
    _write_text_summary(date_str, results, total_s)
    _write_json_summary(date_str, results, total_s)

    return 0


if __name__ == "__main__":
    sys.exit(main())
