"""
performance_tracker.py — Update the permanent performance log (CSV) after
each day's results.

CRITICAL BUG FIX: The original implementation used REPORT_DATE before it was
defined, causing a NameError. This implementation defines `date_str` at the
very top of main() — before any conditional logic — so it is always in scope.

Pipeline:
    1. Load data/results_YYYY-MM-DD.json.
       If missing → log WARNING and exit 0 (gracefully, no crash).
    2. Load/create performance_log.csv with correct headers.
    3. For each official result, read cumulative P/L from the last CSV row,
       compute new cumulative, then append a new row.
    4. Save reports/performance_summary_YYYY-MM-DD.txt.

CSV columns:
    date, horse, race_id, course, off_time, candidate_type, grade, score,
    sp_decimal, position, won, placed, official_stake, official_pl,
    shadow_stake, shadow_pl, cumulative_official_pl, model_version

Exit codes:
    0  — success (including graceful "no results file" case)
    1  — write error
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.config import get_config
from src.helpers import (
    data_path,
    log,
    report_path,
    safe_load_json,
    today_str,
)


# ---------------------------------------------------------------------------
# CSV configuration
# ---------------------------------------------------------------------------

CSV_FILENAME = "performance_log.csv"

CSV_HEADERS: list[str] = [
    "date",
    "horse",
    "race_id",
    "course",
    "off_time",
    "candidate_type",
    "grade",
    "score",
    "sp_decimal",
    "position",
    "won",
    "placed",
    "official_stake",
    "official_pl",
    "shadow_stake",
    "shadow_pl",
    "cumulative_official_pl",
    "model_version",
]


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def _csv_path() -> str:
    """Return absolute path to performance_log.csv in the project root."""
    try:
        cfg = get_config()
        return str(Path(cfg.project_dir) / CSV_FILENAME)
    except Exception as exc:
        log(f"performance_tracker: could not resolve project_dir — {exc}", "WARNING")
        return CSV_FILENAME


def _ensure_csv(path: str) -> None:
    """Create the CSV file with headers if it does not exist."""
    p = Path(path)
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_HEADERS)
            writer.writeheader()
        log(f"performance_tracker: created new CSV at {path}")


def _read_last_cumulative_pl(path: str) -> float:
    """Read the cumulative_official_pl value from the last data row in the CSV.

    Returns 0.0 if the CSV is empty (headers only) or does not exist.
    """
    p = Path(path)
    if not p.exists():
        return 0.0
    try:
        with open(p, "r", newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            last_cumulative: float = 0.0
            found_row = False
            for row in reader:
                raw = row.get("cumulative_official_pl", "0")
                try:
                    last_cumulative = float(raw)
                    found_row = True
                except (ValueError, TypeError):
                    pass
            return last_cumulative if found_row else 0.0
    except OSError as exc:
        log(f"performance_tracker: error reading CSV — {exc}", "WARNING")
        return 0.0


def _read_all_rows(path: str) -> list[dict]:
    """Return all data rows from the CSV as a list of dicts."""
    p = Path(path)
    if not p.exists():
        return []
    try:
        with open(p, "r", newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            return list(reader)
    except OSError as exc:
        log(f"performance_tracker: error reading CSV rows — {exc}", "WARNING")
        return []


def _append_row(path: str, row: dict) -> bool:
    """Append a single dict row to the CSV. Returns True on success."""
    try:
        with open(path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_HEADERS, extrasaction="ignore")
            writer.writerow(row)
        return True
    except OSError as exc:
        log(f"performance_tracker: error appending CSV row — {exc}", "ERROR")
        return False


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------

def _compute_stats(all_rows: list[dict]) -> dict:
    """Compute running totals from all CSV rows."""
    total_bets = 0
    total_wins = 0
    total_places = 0
    total_stake = 0.0
    cumulative_pl = 0.0

    for row in all_rows:
        try:
            stake = float(row.get("official_stake") or 0)
        except (ValueError, TypeError):
            stake = 0.0
        if stake <= 0:
            continue

        total_bets += 1
        total_stake += stake

        won_val = str(row.get("won", "")).lower()
        if won_val in ("true", "1", "yes"):
            total_wins += 1

        placed_val = str(row.get("placed", "")).lower()
        if placed_val in ("true", "1", "yes"):
            total_places += 1

        try:
            pl = float(row.get("official_pl") or 0)
        except (ValueError, TypeError):
            pl = 0.0
        cumulative_pl += pl

    strike_rate = (total_wins / total_bets * 100) if total_bets > 0 else 0.0
    roi = (cumulative_pl / total_stake * 100) if total_stake > 0 else 0.0

    return {
        "total_bets": total_bets,
        "total_wins": total_wins,
        "total_places": total_places,
        "total_stake": round(total_stake, 2),
        "cumulative_pl": round(cumulative_pl, 2),
        "strike_rate": round(strike_rate, 1),
        "roi": round(roi, 1),
    }


# ---------------------------------------------------------------------------
# Report formatter
# ---------------------------------------------------------------------------

def _format_summary_report(
    date_str: str,
    today_results: list[dict],
    today_pl: float,
    running_stats: dict,
) -> str:
    lines: list[str] = [
        "PERFORMANCE TRACKER UPDATE",
        f"Date: {date_str}",
        "",
        "Today's Official Results:",
    ]

    if not today_results:
        lines.append("  No official selections recorded today.")
    else:
        for res in today_results:
            ctype = res.get("candidate_type", "").upper()
            horse = res.get("horse", "Unknown")
            pos = res.get("position")
            pos_str = f"{pos}" if pos else "N/R"
            pl = res.get("official_pl", 0.0)
            pl_str = f"{pl:+.2f}"
            lines.append(f"  {ctype}: {horse} — {pos_str} | P/L: {pl_str} units")

    pl_sign = "+" if today_pl >= 0 else ""
    lines += [
        f"  Official P/L Today: {pl_sign}{today_pl:.2f} units",
        "",
        "Running Totals:",
        f"  Total Bets:     {running_stats['total_bets']}",
        f"  Wins:           {running_stats['total_wins']}",
        f"  Strike Rate:    {running_stats['strike_rate']:.1f}%",
        f"  Cumulative P/L: {running_stats['cumulative_pl']:+.2f} units",
        f"  ROI:            {running_stats['roi']:+.1f}%",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Update performance log. Returns exit code."""
    log("performance_tracker.py started")

    # CRITICAL: Define date_str at the very top of main(), before any
    # conditional logic, to prevent NameError (the original bug).
    date_str: str = today_str()
    log(f"performance_tracker: date={date_str}")

    # Resolve model version from config (graceful fallback).
    try:
        cfg = get_config()
        model_version: str = cfg.model_version
    except Exception as exc:
        log(f"performance_tracker: could not load config — {exc}", "WARNING")
        model_version = "v3"

    # ------------------------------------------------------------------
    # 1. Load results file — graceful exit if missing
    # ------------------------------------------------------------------
    results_path = data_path(f"results_{date_str}.json")
    results_doc: Optional[dict] = safe_load_json(results_path)

    if results_doc is None:
        log(
            f"performance_tracker: results file not found at {results_path}. "
            "Run results_auditor.py first. Exiting gracefully.",
            "WARNING",
        )
        # Write a brief summary noting no data available.
        report_dest = report_path(f"performance_summary_{date_str}.txt")
        try:
            with open(report_dest, "w", encoding="utf-8") as fh:
                fh.write(
                    f"PERFORMANCE TRACKER UPDATE\n"
                    f"Date: {date_str}\n\n"
                    f"No results data available for {date_str}.\n"
                    f"Run results_auditor.py to generate results first.\n"
                )
        except OSError as exc:
            log(f"performance_tracker: could not write no-data report — {exc}", "WARNING")
        return 0   # Graceful exit — not a crash

    # ------------------------------------------------------------------
    # 2. Load/create CSV
    # ------------------------------------------------------------------
    csv_path = _csv_path()
    _ensure_csv(csv_path)
    log(f"performance_tracker: CSV at {csv_path}")

    # ------------------------------------------------------------------
    # 3. Process official results and append to CSV
    # ------------------------------------------------------------------
    official_results: list[dict] = results_doc.get("official_results") or []
    shadow_results: list[dict] = results_doc.get("shadow_results") or []

    # Re-run protection: the CSV is append-only with no upsert, so running the
    # evening pipeline twice (e.g. after late results) would double-book P/L
    # and corrupt cumulative_official_pl forever. Skip rows already logged.
    existing_keys: set[tuple[str, str, str]] = set()
    for prev in _read_all_rows(csv_path):
        existing_keys.add((
            str(prev.get("date") or ""),
            str(prev.get("race_id") or ""),
            str(prev.get("horse") or ""),
        ))

    # Read current cumulative before we start appending.
    cumulative_pl = _read_last_cumulative_pl(csv_path)
    log(f"performance_tracker: starting cumulative P/L = {cumulative_pl:+.2f}")

    today_pl: float = 0.0
    appended_count: int = 0
    skipped_dupes: int = 0
    write_errors: int = 0

    def _row_for(res: dict, official_stake: float, official_pl: float,
                 shadow_stake: float, shadow_pl_val: float, cum: float) -> dict:
        return {
            "date":                 date_str,
            "horse":                res.get("horse", ""),
            "race_id":              res.get("race_id", ""),
            "course":               res.get("course", ""),
            "off_time":             res.get("off_time", ""),
            "candidate_type":       res.get("candidate_type", ""),
            "grade":                res.get("grade", ""),
            "score":                res.get("score", 0),
            "sp_decimal":           res.get("sp_decimal", ""),
            "position":             res.get("position", ""),
            "won":                  res.get("won", False),
            "placed":               res.get("placed", False),
            "official_stake":       official_stake,
            "official_pl":          official_pl,
            "shadow_stake":         shadow_stake,
            "shadow_pl":            shadow_pl_val,
            "cumulative_official_pl": cum,
            "model_version":        model_version,
        }

    for res in official_results:
        key = (date_str, str(res.get("race_id") or ""), str(res.get("horse") or ""))
        if key in existing_keys:
            skipped_dupes += 1
            continue
        existing_keys.add(key)

        official_stake = float(res.get("official_stake") or 0)
        official_pl = float(res.get("official_pl") or 0)
        cumulative_pl = round(cumulative_pl + official_pl, 2)
        today_pl = round(today_pl + official_pl, 2)

        row = _row_for(res, official_stake, official_pl, 0.0, 0.0, cumulative_pl)
        if _append_row(csv_path, row):
            appended_count += 1
        else:
            write_errors += 1

    # Shadow results: persisted as their own rows (shadow_stake=1.0 paper bet)
    # so the profit report's shadow section has data — previously these were
    # collected nightly and discarded, leaving the section at zero forever.
    # Shadow P/L never touches official cumulative.
    for res in shadow_results:
        key = (date_str, str(res.get("race_id") or ""), str(res.get("horse") or ""))
        if key in existing_keys:
            skipped_dupes += 1
            continue
        existing_keys.add(key)

        try:
            shadow_pl_val = float(res.get("official_pl") or res.get("shadow_pl") or 0)
        except (ValueError, TypeError):
            shadow_pl_val = 0.0
        row = _row_for(res, 0.0, 0.0, 1.0, shadow_pl_val, cumulative_pl)
        if _append_row(csv_path, row):
            appended_count += 1
        else:
            write_errors += 1

    if skipped_dupes:
        log(f"performance_tracker: skipped {skipped_dupes} already-logged row(s) (re-run)")

    log(
        f"performance_tracker: appended {appended_count} row(s), "
        f"{write_errors} write error(s). "
        f"Today's P/L = {today_pl:+.2f}, cumulative = {cumulative_pl:+.2f}"
    )

    if write_errors > 0:
        log(f"performance_tracker: {write_errors} CSV write errors", "ERROR")
        return 1

    # ------------------------------------------------------------------
    # 4. Compute running stats from the full CSV
    # ------------------------------------------------------------------
    all_rows = _read_all_rows(csv_path)
    running_stats = _compute_stats(all_rows)

    # ------------------------------------------------------------------
    # 5. Save daily summary report
    # ------------------------------------------------------------------
    summary_text = _format_summary_report(
        date_str,
        official_results,
        today_pl,
        running_stats,
    )
    report_dest = report_path(f"performance_summary_{date_str}.txt")
    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(summary_text)
        log(f"performance_tracker: summary report saved → {report_dest}")
    except OSError as exc:
        log(f"performance_tracker: failed to write summary report — {exc}", "ERROR")
        return 1

    print(
        f"performance_tracker: COMPLETE — "
        f"appended={appended_count}, "
        f"today_pl={today_pl:+.2f}, "
        f"total_bets={running_stats['total_bets']}, "
        f"cumulative_pl={running_stats['cumulative_pl']:+.2f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
