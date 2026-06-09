"""
generate_historical_dataset.py — ONE-COMMAND historical-data foundation.

Builds the REAL historical dataset that the model-recalibration and forensic
analysis scripts depend on. Run this ON PYTHONANYWHERE, where the Racing API
credentials and the MySQL database are available (this script makes API + DB
calls via the steps it invokes — it does none directly).

What it does, in order:
    1. Ensure the MySQL schema exists           (database_foundation.py)
    2. Run the historical backtest over a        (historical_backtest.py)
       configurable lookback — fetches real
       racecards + results from the Racing API,
       replays the NAP model, and writes:
           data/backtest_<from>_to_<to>.csv      <- forensic analysis input
           data/backtest_cache/...               <- cached API data
    3. Populate the 11 evidence-warehouse tables from the daily-pipeline JSON
       files, in dependency order:
           db_import_racecards.py        -> races, runners, odds_snapshots
           db_import_results.py          -> results, trainer_market_profiles
           db_import_market_moves.py     -> market_moves, odds_snapshots
           db_import_model_candidates.py -> model_candidates
    4. Log every step and write a summary (text + JSON).

Idempotent / re-runnable:
    - The backtest caches every fetched day under data/backtest_cache/, so a
      second run costs no API calls for already-fetched dates.
    - database_foundation uses CREATE TABLE IF NOT EXISTS.
    - The db_import_* steps use INSERT IGNORE / ON DUPLICATE KEY, so re-imports
      do not duplicate rows.

Usage:
    python generate_historical_dataset.py                 # default 6-month lookback
    python generate_historical_dataset.py --months 12     # 12-month lookback
    python generate_historical_dataset.py --from 2025-06-01 --to 2026-06-07
    python generate_historical_dataset.py --min-score 55  # passthrough to backtest
    python generate_historical_dataset.py --skip-schema   # assume schema already built
    python generate_historical_dataset.py --skip-imports  # backtest/CSV only, no DB
    python generate_historical_dataset.py --import-date 2026-06-08
                                                          # date the db_import_* steps use

Exit codes:
    0  — backtest produced a CSV (the data foundation exists)
    1  — backtest produced no CSV, or the pipeline could not start
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.config import get_config
from src.helpers import data_path, log, report_path, today_str


# ---------------------------------------------------------------------------
# Step runner — same subprocess + logging pattern as daily_pipeline._run_step
# ---------------------------------------------------------------------------

def _run_step(
    step_name: str,
    script: str,
    args: list[str],
    project_dir: str,
    timeout_s: int,
) -> dict:
    """Run a single step as a subprocess.

    Returns a result dict with keys:
        step, script, args, started_at, finished_at, duration_s,
        returncode, status ("PASS" | "FAIL")
    """
    script_path = str(Path(project_dir) / script)
    cmd = [sys.executable, script_path] + args

    log(f"generate_historical_dataset: [{step_name}] starting — {' '.join(cmd)}")
    started_at = datetime.now(timezone.utc)

    try:
        result = subprocess.run(
            cmd,
            cwd=project_dir,
            capture_output=False,   # let stdout/stderr flow to the task log
            timeout=timeout_s,
        )
        returncode = result.returncode
    except subprocess.TimeoutExpired:
        log(f"generate_historical_dataset: [{step_name}] TIMEOUT after {timeout_s}s", "ERROR")
        returncode = -1
    except OSError as exc:
        log(f"generate_historical_dataset: [{step_name}] OS error — {exc}", "ERROR")
        returncode = -1

    finished_at = datetime.now(timezone.utc)
    duration_s = round((finished_at - started_at).total_seconds(), 2)
    status = "PASS" if returncode == 0 else "FAIL"

    log(
        f"generate_historical_dataset: [{step_name}] {status} "
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
# CSV discovery — confirm the backtest actually produced a stable-path CSV
# ---------------------------------------------------------------------------

def _find_backtest_csvs() -> list[Path]:
    """Return all data/backtest_*.csv files, newest first."""
    data_dir = Path(data_path(".gitkeep")).parent  # resolve PROJECT_DIR/data
    return sorted(
        data_dir.glob("backtest_*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _csv_row_count(csv_path: Path) -> int:
    """Count data rows (excluding header) in *csv_path*; 0 on any error."""
    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            return max(0, sum(1 for _ in reader) - 1)
    except (OSError, csv.Error):
        return 0


# ---------------------------------------------------------------------------
# Summary writers (mirrors daily_pipeline)
# ---------------------------------------------------------------------------

def _write_text_summary(date_str: str, results: list[dict], total_s: float,
                        csv_path: Optional[Path], csv_rows: int) -> None:
    lines: list[str] = [
        "HISTORICAL DATASET GENERATION SUMMARY",
        f"Date: {date_str}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Total duration: {total_s:.1f}s",
        f"Backtest CSV:  {csv_path if csv_path else 'NONE PRODUCED'}",
        f"CSV data rows: {csv_rows}",
        "",
        f"{'#':<4} {'Step':<30} {'Status':<8} {'Duration':>10}  RC",
        "-" * 64,
    ]
    for idx, r in enumerate(results, start=1):
        lines.append(
            f"{idx:<4} {r['step']:<30} {r['status']:<8} "
            f"{r['duration_s']:>8.1f}s  {r['returncode']}"
        )

    pass_count = sum(1 for r in results if r["status"] in ("PASS", "SKIPPED"))
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    lines += [
        "",
        f"PASS/SKIP: {pass_count}  FAIL: {fail_count}  TOTAL: {len(results)}",
    ]

    txt_path = report_path(f"historical_dataset_{date_str}.txt")
    try:
        with open(txt_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        log(f"generate_historical_dataset: text summary saved to {txt_path}")
    except OSError as exc:
        log(f"generate_historical_dataset: failed to write text summary — {exc}", "ERROR")


def _write_json_summary(date_str: str, results: list[dict], total_s: float,
                        csv_path: Optional[Path], csv_rows: int) -> None:
    doc = {
        "date": date_str,
        "pipeline": "historical_dataset",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_duration_s": total_s,
        "backtest_csv": str(csv_path) if csv_path else None,
        "backtest_csv_rows": csv_rows,
        "pass_count": sum(1 for r in results if r["status"] in ("PASS", "SKIPPED")),
        "fail_count": sum(1 for r in results if r["status"] == "FAIL"),
        "steps": results,
    }
    json_path = data_path(f"historical_dataset_{date_str}.json")
    try:
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)
        log(f"generate_historical_dataset: JSON summary saved to {json_path}")
    except (OSError, TypeError) as exc:
        log(f"generate_historical_dataset: failed to write JSON summary — {exc}", "ERROR")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="One-command historical-dataset foundation (backtest CSV + DB tables).",
    )
    parser.add_argument(
        "--months", type=int, default=6,
        help="Lookback window in months (default 6 — the Racing API max).",
    )
    parser.add_argument(
        "--from", dest="from_date", type=str, default=None,
        help="Explicit start date YYYY-MM-DD (overrides --months).",
    )
    parser.add_argument(
        "--to", dest="to_date", type=str, default=None,
        help="Explicit end date YYYY-MM-DD (overrides --months).",
    )
    parser.add_argument(
        "--min-score", dest="min_score", type=float, default=None,
        help="Passthrough to historical_backtest --min-score.",
    )
    parser.add_argument(
        "--include-jumps", dest="include_jumps", action="store_true", default=False,
        help="Passthrough to historical_backtest --include-jumps.",
    )
    parser.add_argument(
        "--import-date", dest="import_date", type=str, default=None,
        help="Date the db_import_* steps use (default: today). They read the "
             "daily-pipeline JSON files for that date.",
    )
    parser.add_argument(
        "--skip-schema", action="store_true", default=False,
        help="Skip the database_foundation schema step (assume tables exist).",
    )
    parser.add_argument(
        "--skip-imports", action="store_true", default=False,
        help="Run the backtest only; skip the DB import steps.",
    )
    parser.add_argument(
        "--step-timeout", dest="step_timeout", type=int, default=21600,
        help="Per-step timeout in seconds (default 21600 = 6h; the backtest "
             "over 6 months makes thousands of API calls).",
    )
    return parser.parse_args(argv)


def _build_backtest_args(args: argparse.Namespace) -> list[str]:
    """Translate orchestrator args into historical_backtest.py CLI args."""
    bt_args: list[str] = []
    if args.from_date or args.to_date:
        # historical_backtest uses --start / --end
        if args.from_date:
            bt_args += ["--start", args.from_date]
        if args.to_date:
            bt_args += ["--end", args.to_date]
    else:
        bt_args += ["--months", str(args.months)]
    if args.min_score is not None:
        bt_args += ["--min-score", str(args.min_score)]
    if args.include_jumps:
        bt_args += ["--include-jumps"]
    return bt_args


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Run the historical-dataset generation pipeline. Returns exit code."""
    log("generate_historical_dataset.py started")

    args = _parse_args(sys.argv[1:])
    date_str = today_str()
    import_date = args.import_date or date_str

    # --- Config ---------------------------------------------------------------
    try:
        cfg = get_config()
        project_dir = cfg.project_dir
    except KeyError as exc:
        log(f"generate_historical_dataset: missing configuration key — {exc}", "ERROR")
        return 1

    log(
        f"generate_historical_dataset: project_dir={project_dir}, date={date_str}, "
        f"import_date={import_date}, months={args.months}, "
        f"from={args.from_date}, to={args.to_date}"
    )

    # --- Record CSVs present before the run, so we can detect a fresh one -----
    pre_existing_csvs = {p.name for p in _find_backtest_csvs()}

    # --- Build the step plan --------------------------------------------------
    # Each entry: (step_name, script, args). Steps run in dependency order:
    #   schema -> backtest -> racecards -> results -> market_moves -> candidates
    steps_plan: list[tuple[str, str, list[str]]] = []

    if not args.skip_schema:
        steps_plan.append(("database_foundation", "database_foundation.py", []))

    steps_plan.append(("historical_backtest", "historical_backtest.py",
                       _build_backtest_args(args)))

    if not args.skip_imports:
        steps_plan += [
            ("db_import_racecards",        "db_import_racecards.py",        [import_date]),
            ("db_import_results",          "db_import_results.py",          [import_date]),
            ("db_import_market_moves",     "db_import_market_moves.py",     [import_date]),
            ("db_import_model_candidates", "db_import_model_candidates.py", [import_date]),
        ]

    # --- Run the plan ---------------------------------------------------------
    pipeline_start = datetime.now(timezone.utc)
    results: list[dict] = []
    backtest_ok = False

    for step_name, script, step_args in steps_plan:
        result = _run_step(step_name, script, step_args, project_dir, args.step_timeout)
        results.append(result)

        if step_name == "historical_backtest":
            backtest_ok = result["status"] == "PASS"
            if not backtest_ok:
                # The backtest is the data foundation. If it fails outright we
                # log loudly but still continue so the DB import steps (which
                # may populate today's data) and the summary still run.
                log(
                    "generate_historical_dataset: historical_backtest FAILED — "
                    "the forensic CSV may be missing or stale",
                    "ERROR",
                )

    pipeline_end = datetime.now(timezone.utc)
    total_s = round((pipeline_end - pipeline_start).total_seconds(), 2)

    # --- Verify the backtest produced a stable-path CSV ----------------------
    all_csvs = _find_backtest_csvs()
    newest_csv: Optional[Path] = all_csvs[0] if all_csvs else None
    fresh_csv: Optional[Path] = next(
        (p for p in all_csvs if p.name not in pre_existing_csvs), None
    )
    # Prefer a freshly-written CSV; fall back to the newest existing one.
    csv_path = fresh_csv or newest_csv
    csv_rows = _csv_row_count(csv_path) if csv_path else 0

    if csv_path is None:
        log(
            "generate_historical_dataset: NO backtest CSV found in data/ — "
            "the data foundation was NOT produced",
            "ERROR",
        )
    else:
        kind = "fresh" if fresh_csv else "existing"
        log(
            f"generate_historical_dataset: backtest CSV ({kind}) at {csv_path} "
            f"({csv_rows} data rows)"
        )

    # --- Summaries ------------------------------------------------------------
    _write_text_summary(date_str, results, total_s, csv_path, csv_rows)
    _write_json_summary(date_str, results, total_s, csv_path, csv_rows)

    pass_count = sum(1 for r in results if r["status"] in ("PASS", "SKIPPED"))
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    log(
        f"generate_historical_dataset: complete — PASS/SKIP={pass_count}, "
        f"FAIL={fail_count}, duration={total_s}s, csv_rows={csv_rows}"
    )

    # Exit 1 only if the backtest produced no usable CSV — that is the single
    # hard requirement of this script (the data foundation must exist).
    if csv_path is None or csv_rows == 0:
        log(
            "generate_historical_dataset: exiting 1 — backtest produced no CSV data",
            "ERROR",
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
