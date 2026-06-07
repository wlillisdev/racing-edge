"""
weekly_learning_report.py — Generate the weekly learning summary.

CRITICAL: This script runs on Sundays ONLY.
If today is not Sunday (weekday() != 6), it prints a notice and exits 0.

Reads performance_log.csv for the last 7 days (Mon–Sun of the current week).
Reads horse_tracker.json for new flags this week.
Reads the last 7 days of loser_diagnostic / results files for pattern notes.

Output: reports/weekly_learning_report_YYYY-MM-DD.txt

Exit codes:
    0 — success (including "not Sunday" graceful skip)
    1 — write error
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
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
# CSV helpers (mirrors performance_tracker / profit_report conventions)
# ---------------------------------------------------------------------------

CSV_FILENAME = "performance_log.csv"


def _csv_path() -> str:
    try:
        cfg = get_config()
        return str(Path(cfg.project_dir) / CSV_FILENAME)
    except Exception as exc:
        log(f"weekly_learning_report: could not resolve project_dir — {exc}", "WARNING")
        return CSV_FILENAME


def _load_csv() -> list[dict]:
    path = _csv_path()
    p = Path(path)
    if not p.exists():
        log(f"weekly_learning_report: CSV not found at {path}", "WARNING")
        return []
    try:
        with open(p, "r", newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except OSError as exc:
        log(f"weekly_learning_report: error reading CSV — {exc}", "WARNING")
        return []


def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _is_true(val) -> bool:
    return str(val).strip().lower() in ("true", "1", "yes")


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _week_bounds(sunday: date) -> tuple[date, date]:
    """Return (monday, sunday) for the week ending on *sunday*."""
    monday = sunday - timedelta(days=6)
    return monday, sunday


def _row_in_range(row: dict, start: date, end: date) -> bool:
    raw = row.get("date", "")
    try:
        d = date.fromisoformat(raw)
        return start <= d <= end
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Stats computation
# ---------------------------------------------------------------------------

def _compute_week_stats(rows: list[dict]) -> dict:
    """Official bet stats for the given rows."""
    bets = 0
    wins = 0
    pl = 0.0
    stake = 0.0

    for row in rows:
        s = _safe_float(row.get("official_stake"))
        if s <= 0:
            continue
        bets += 1
        stake += s
        if _is_true(row.get("won")):
            wins += 1
        pl += _safe_float(row.get("official_pl"))

    sr = round(wins / bets * 100, 1) if bets > 0 else 0.0
    return {
        "bets":         bets,
        "wins":         wins,
        "pl":           round(pl, 2),
        "stake":        round(stake, 2),
        "strike_rate":  sr,
    }


def _compute_grade_breakdown(rows: list[dict]) -> dict[str, dict]:
    """Grade breakdown for official + shadow rows."""
    by_grade: dict[str, list[dict]] = defaultdict(list)

    for row in rows:
        off_stake = _safe_float(row.get("official_stake"))
        shad_stake = _safe_float(row.get("shadow_stake"))
        if off_stake <= 0 and shad_stake <= 0:
            continue
        grade = str(row.get("grade") or "?").strip()
        by_grade[grade].append(row)

    result: dict[str, dict] = {}
    for grade in ("A", "B+", "B"):
        grade_rows = by_grade.get(grade, [])
        off_rows = [r for r in grade_rows if _safe_float(r.get("official_stake")) > 0]
        shad_rows = [r for r in grade_rows if _safe_float(r.get("shadow_stake")) > 0]

        off_bets = len(off_rows)
        off_wins = sum(1 for r in off_rows if _is_true(r.get("won")))
        off_pl = round(sum(_safe_float(r.get("official_pl")) for r in off_rows), 2)
        shad_bets = len(shad_rows)
        shad_wins = sum(1 for r in shad_rows if _is_true(r.get("won")))

        result[grade] = {
            "official_bets": off_bets,
            "official_wins": off_wins,
            "official_pl":   off_pl,
            "shadow_bets":   shad_bets,
            "shadow_wins":   shad_wins,
        }
    return result


def _compute_all_time_stats(rows: list[dict]) -> dict:
    """All-time official stats."""
    bets = 0
    wins = 0
    pl = 0.0
    stake = 0.0

    for row in rows:
        s = _safe_float(row.get("official_stake"))
        if s <= 0:
            continue
        bets += 1
        stake += s
        if _is_true(row.get("won")):
            wins += 1
        pl += _safe_float(row.get("official_pl"))

    sr = round(wins / bets * 100, 1) if bets > 0 else 0.0
    roi = round(pl / stake * 100, 1) if stake > 0 else 0.0
    return {
        "bets":        bets,
        "wins":        wins,
        "pl":          round(pl, 2),
        "strike_rate": sr,
        "roi":         roi,
    }


# ---------------------------------------------------------------------------
# Tracker new flags helper
# ---------------------------------------------------------------------------

def _new_tracker_flags(monday: date, sunday: date) -> list[dict]:
    """Return entries from horse_tracker.json flagged within this week."""
    tracker_path = data_path("horse_tracker.json")
    tracker_doc = safe_load_json(tracker_path)
    if tracker_doc is None:
        return []

    start_str = monday.isoformat()
    end_str = sunday.isoformat()

    new_flags: list[dict] = []
    for entry in (tracker_doc.get("tracked") or []):
        flagged = entry.get("flagged_date", "")
        if start_str <= flagged <= end_str:
            new_flags.append(entry)
    return new_flags


# ---------------------------------------------------------------------------
# Loser diagnostic notes helper
# ---------------------------------------------------------------------------

def _loser_diagnostic_notes(monday: date, sunday: date) -> list[str]:
    """Scan the last 7 days of results for patterns worth noting.

    Conservative: only report if there are 2+ losses in a row for any
    candidate type, or if going-mismatch appears 2+ times.
    """
    notes: list[str] = []
    consecutive_losses: dict[str, int] = defaultdict(int)
    going_mismatches: list[str] = []

    for offset in range(7):
        check_date = monday + timedelta(days=offset)
        if check_date > sunday:
            break
        date_str = check_date.isoformat()
        results_doc = safe_load_json(data_path(f"results_{date_str}.json"))
        if results_doc is None:
            continue

        for r in (results_doc.get("official_results") or []):
            won = str(r.get("won", "")).lower() in ("true", "1", "yes")
            ctype = str(r.get("candidate_type") or "nap")
            if not won:
                consecutive_losses[ctype] += 1
            else:
                consecutive_losses[ctype] = 0

    for ctype, losses in consecutive_losses.items():
        if losses >= 3:
            notes.append(
                f"  • {ctype.upper()} had {losses} consecutive losses this week — "
                "review selection criteria"
            )

    if not notes:
        notes.append("  No significant loser patterns detected this week.")

    return notes


# ---------------------------------------------------------------------------
# Horses to watch next week
# ---------------------------------------------------------------------------

def _next_week_watch_horses() -> list[str]:
    """Return formatted watch-list entries for the next week section."""
    tracker_path = data_path("horse_tracker.json")
    tracker_doc = safe_load_json(tracker_path)
    if tracker_doc is None:
        return ["  No horses currently tracked."]

    active = [
        e for e in (tracker_doc.get("tracked") or [])
        if e.get("status") == "watching"
    ]
    if not active:
        return ["  No horses currently tracked."]

    lines: list[str] = []
    for entry in active[:10]:  # Cap at 10 for readability
        lines.append(
            f"  • {entry.get('horse_name', 'Unknown')} — "
            f"{entry.get('flag_reason', '?')} | "
            f"Needs: {entry.get('required_conditions', 'N/A')}"
        )
    if len(active) > 10:
        lines.append(f"  ... and {len(active) - 10} more in tracker")
    return lines


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

_SEP = "=" * 45


def _build_report(
    date_str: str,
    monday: date,
    sunday: date,
    week_stats: dict,
    grade_breakdown: dict[str, dict],
    all_time: dict,
    new_flags: list[dict],
    loser_notes: list[str],
    next_week_notes: list[str],
) -> str:
    week_range = f"{monday.isoformat()} to {date_str}"
    pl_sign = "+" if week_stats["pl"] >= 0 else ""
    at_pl_sign = "+" if all_time["pl"] >= 0 else ""
    at_roi_sign = "+" if all_time["roi"] >= 0 else ""

    def grade_line(grade: str) -> str:
        g = grade_breakdown.get(grade, {})
        off_bets = g.get("official_bets", 0)
        off_wins = g.get("official_wins", 0)
        off_pl = g.get("official_pl", 0.0)
        shad_bets = g.get("shadow_bets", 0)
        shad_wins = g.get("shadow_wins", 0)
        pl_s = "+" if off_pl >= 0 else ""
        if grade == "B":
            return (
                f"Grade B:   {off_bets} bets (shadow) | "
                f"{shad_bets} shadow | {shad_wins} shadow wins"
            )
        return (
            f"Grade {grade}:   {off_bets} bets | {off_wins} wins | "
            f"{pl_s}{off_pl:.2f} P/L"
        )

    tracker_flag_lines: list[str] = []
    if new_flags:
        for f in new_flags:
            tracker_flag_lines.append(
                f"  • {f.get('horse_name', 'Unknown')} — "
                f"{f.get('flag_reason', '?')} | "
                f"{f.get('required_conditions', 'N/A')} "
                f"(flagged {f.get('flagged_date', '?')})"
            )
    else:
        tracker_flag_lines.append("  No new tracker flags this week.")

    lines: list[str] = [
        "WEEKLY LEARNING REPORT",
        f"Week ending: {date_str} (Sunday)",
        f"Week range:  {week_range}",
        "",
        _SEP,
        "OFFICIAL PERFORMANCE THIS WEEK",
        _SEP,
        f"Bets placed:        {week_stats['bets']}",
        f"Wins:               {week_stats['wins']} ({week_stats['strike_rate']:.1f}%)",
        f"Official P/L:       {pl_sign}{week_stats['pl']:.2f} units",
        "",
        _SEP,
        "GRADE BREAKDOWN",
        _SEP,
        grade_line("A"),
        grade_line("B+"),
        grade_line("B"),
        "",
        _SEP,
        "LEARNING NOTES THIS WEEK",
        _SEP,
        "New horse tracker flags:",
        *tracker_flag_lines,
        "",
        "Loser diagnostic patterns:",
        *loser_notes,
        "",
        _SEP,
        "RUNNING TOTALS (All-time)",
        _SEP,
        f"Total bets: {all_time['bets']} | "
        f"Win rate: {all_time['strike_rate']:.1f}% | "
        f"P/L: {at_pl_sign}{all_time['pl']:.2f} | "
        f"ROI: {at_roi_sign}{all_time['roi']:.1f}%",
        "",
        _SEP,
        "NEXT WEEK NOTES",
        _SEP,
        "Horses to watch from tracker with conditions needed:",
        *next_week_notes,
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Generate weekly learning report (Sundays only). Returns exit code."""
    log("weekly_learning_report.py started")

    today = date.today()
    day_name = today.strftime("%A")

    # CRITICAL: Sunday-only guard
    if today.weekday() != 6:
        msg = (
            f"Weekly learning report runs on Sundays only. "
            f"Today is {day_name}. Skipping."
        )
        print(msg)
        log(msg, "INFO")
        return 0

    date_str = today_str()
    log(f"weekly_learning_report: Sunday confirmed — date={date_str}")

    monday, sunday = _week_bounds(today)
    log(f"weekly_learning_report: week {monday.isoformat()} → {sunday.isoformat()}")

    # ------------------------------------------------------------------
    # 1. Load CSV and filter to this week
    # ------------------------------------------------------------------
    all_rows = _load_csv()
    week_rows = [r for r in all_rows if _row_in_range(r, monday, sunday)]
    log(f"weekly_learning_report: {len(week_rows)} rows this week, {len(all_rows)} all-time")

    # ------------------------------------------------------------------
    # 2. Compute stats
    # ------------------------------------------------------------------
    week_stats = _compute_week_stats(week_rows)
    grade_breakdown = _compute_grade_breakdown(week_rows)
    all_time = _compute_all_time_stats(all_rows)

    # ------------------------------------------------------------------
    # 3. Tracker flags this week
    # ------------------------------------------------------------------
    new_flags = _new_tracker_flags(monday, sunday)
    log(f"weekly_learning_report: {len(new_flags)} new tracker flags this week")

    # ------------------------------------------------------------------
    # 4. Loser diagnostic notes
    # ------------------------------------------------------------------
    loser_notes = _loser_diagnostic_notes(monday, sunday)

    # ------------------------------------------------------------------
    # 5. Next week watch horses
    # ------------------------------------------------------------------
    next_week_notes = _next_week_watch_horses()

    # ------------------------------------------------------------------
    # 6. Build and save report
    # ------------------------------------------------------------------
    report_text = _build_report(
        date_str,
        monday,
        sunday,
        week_stats,
        grade_breakdown,
        all_time,
        new_flags,
        loser_notes,
        next_week_notes,
    )

    report_dest = report_path(f"weekly_learning_report_{date_str}.txt")
    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
        log(f"weekly_learning_report: report saved → {report_dest}")
    except OSError as exc:
        log(f"weekly_learning_report: failed to write report — {exc}", "ERROR")
        return 1

    print(
        f"weekly_learning_report: COMPLETE — "
        f"week_bets={week_stats['bets']}, "
        f"week_pl={week_stats['pl']:+.2f}, "
        f"all_time_bets={all_time['bets']}, "
        f"all_time_roi={all_time['roi']:+.1f}%"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
