"""
profit_report.py — Generate the official and shadow profit/ROI report from
the performance log.

Reads performance_log.csv (all historical rows) and produces:
  - Overall official performance stats (NAP selections only)
  - Overall shadow performance stats (clearly labelled, NOT mixed)
  - Grade breakdown (A, B+, B, C)
  - Month breakdown

Outputs:
    reports/profit_report_YYYY-MM-DD.txt

If performance_log.csv is missing → write a "no data yet" report.

Exit codes:
    0  — success
    1  — write error
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.config import get_config
from src.helpers import (
    log,
    report_path,
    today_str,
)


# ---------------------------------------------------------------------------
# CSV path helper
# ---------------------------------------------------------------------------

CSV_FILENAME = "performance_log.csv"


def _csv_path() -> str:
    """Return absolute path to performance_log.csv in the project root."""
    try:
        cfg = get_config()
        return str(Path(cfg.project_dir) / CSV_FILENAME)
    except Exception as exc:
        log(f"profit_report: could not resolve project_dir — {exc}", "WARNING")
        return CSV_FILENAME


def _model_version() -> str:
    try:
        cfg = get_config()
        return cfg.model_version
    except Exception:
        return "v3"


# ---------------------------------------------------------------------------
# CSV reader
# ---------------------------------------------------------------------------

def _load_csv(path: str) -> Optional[list[dict]]:
    """Load all rows from the CSV. Returns None if file is missing."""
    p = Path(path)
    if not p.exists():
        log(f"profit_report: CSV not found at {path}", "WARNING")
        return None
    try:
        with open(p, "r", newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        log(f"profit_report: loaded {len(rows)} rows from {path}")
        return rows
    except OSError as exc:
        log(f"profit_report: error reading CSV — {exc}", "WARNING")
        return None


# ---------------------------------------------------------------------------
# Row parsing helpers
# ---------------------------------------------------------------------------

def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _is_true(val) -> bool:
    return str(val).strip().lower() in ("true", "1", "yes")


def _row_month(row: dict) -> str:
    """Extract YYYY-MM from the date field. Returns empty string on error."""
    raw = row.get("date", "")
    try:
        return raw[:7]  # "YYYY-MM"
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Stats computation
# ---------------------------------------------------------------------------

def _compute_segment_stats(rows: list[dict], is_shadow: bool = False) -> dict:
    """Compute stats for a segment of rows (official or shadow).

    For official rows: use official_stake / official_pl.
    For shadow rows:   use shadow_stake / shadow_pl.
    """
    stake_key = "shadow_stake" if is_shadow else "official_stake"
    pl_key    = "shadow_pl"    if is_shadow else "official_pl"

    total_bets    = 0
    total_wins    = 0
    total_places  = 0
    total_stake   = 0.0
    total_pl      = 0.0

    for row in rows:
        stake = _safe_float(row.get(stake_key))
        if stake <= 0:
            continue
        total_bets  += 1
        total_stake += stake
        total_pl    += _safe_float(row.get(pl_key))

        won_key    = "won"
        placed_key = "placed"
        if _is_true(row.get(won_key)):
            total_wins += 1
        if _is_true(row.get(placed_key)):
            total_places += 1

    strike_rate  = (total_wins   / total_bets  * 100) if total_bets  > 0 else 0.0
    place_rate   = (total_places / total_bets  * 100) if total_bets  > 0 else 0.0
    roi          = (total_pl     / total_stake * 100) if total_stake > 0 else 0.0

    return {
        "total_bets":    total_bets,
        "total_wins":    total_wins,
        "total_places":  total_places,
        "total_pl":      round(total_pl,    2),
        "total_stake":   round(total_stake, 2),
        "strike_rate":   round(strike_rate, 1),
        "place_rate":    round(place_rate,  1),
        "roi":           round(roi,          1),
    }


def _grade_breakdown(rows: list[dict]) -> dict[str, dict]:
    """P/L breakdown by grade for official bets."""
    by_grade: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        stake = _safe_float(row.get("official_stake"))
        if stake <= 0:
            continue
        grade = str(row.get("grade") or "?").strip()
        by_grade[grade].append(row)

    result: dict[str, dict] = {}
    for grade in ["A", "B+", "B", "C"]:
        result[grade] = _compute_segment_stats(by_grade.get(grade, []))
    return result


def _month_breakdown(rows: list[dict]) -> dict[str, dict]:
    """P/L breakdown by month (YYYY-MM) for official bets."""
    by_month: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        stake = _safe_float(row.get("official_stake"))
        if stake <= 0:
            continue
        month = _row_month(row)
        if month:
            by_month[month].append(row)

    result: dict[str, dict] = {}
    for month in sorted(by_month.keys()):
        result[month] = _compute_segment_stats(by_month[month])
    return result


def _shadow_month_breakdown(rows: list[dict]) -> dict[str, dict]:
    """P/L breakdown by month for shadow bets."""
    by_month: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        stake = _safe_float(row.get("shadow_stake"))
        if stake <= 0:
            continue
        month = _row_month(row)
        if month:
            by_month[month].append(row)

    result: dict[str, dict] = {}
    for month in sorted(by_month.keys()):
        result[month] = _compute_segment_stats(by_month[month], is_shadow=True)
    return result


# ---------------------------------------------------------------------------
# Report formatter
# ---------------------------------------------------------------------------

_SEP_DOUBLE = "=" * 56
_SEP_THIN   = "-" * 56


def _fmt_stat_line(label: str, value: str, width: int = 26) -> str:
    return f"  {label:<{width}}{value}"


def _fmt_grade_row(grade: str, stats: dict) -> str:
    bets  = stats["total_bets"]
    wins  = stats["total_wins"]
    pl    = stats["total_pl"]
    roi   = stats["roi"]
    if bets == 0:
        return f"  Grade {grade}: No bets recorded"
    pl_sign = "+" if pl >= 0 else ""
    roi_sign = "+" if roi >= 0 else ""
    return (
        f"  Grade {grade}: {bets} bet{'s' if bets != 1 else ''} | "
        f"{wins} win{'s' if wins != 1 else ''} | "
        f"{pl_sign}{pl:.2f} P/L | "
        f"{roi_sign}{roi:.1f}% ROI"
    )


def _fmt_month_row(month: str, stats: dict) -> str:
    bets = stats["total_bets"]
    wins = stats["total_wins"]
    pl   = stats["total_pl"]
    roi  = stats["roi"]
    pl_sign  = "+" if pl  >= 0 else ""
    roi_sign = "+" if roi >= 0 else ""
    try:
        dt = datetime.strptime(month, "%Y-%m")
        month_label = dt.strftime("%b %Y")
    except ValueError:
        month_label = month
    return (
        f"  {month_label}: {bets} bet{'s' if bets != 1 else ''} | "
        f"{wins} win{'s' if wins != 1 else ''} | "
        f"{pl_sign}{pl:.2f} P/L | "
        f"{roi_sign}{roi:.1f}% ROI"
    )


def _build_report(
    date_str: str,
    model_ver: str,
    official_stats: dict,
    shadow_stats: dict,
    grade_stats: dict[str, dict],
    month_stats: dict[str, dict],
    shadow_month_stats: dict[str, dict],
) -> str:
    o = official_stats
    s = shadow_stats

    o_pl_sign  = "+" if o["total_pl"]  >= 0 else ""
    o_roi_sign = "+" if o["roi"]        >= 0 else ""
    s_pl_sign  = "+" if s["total_pl"]  >= 0 else ""
    s_roi_sign = "+" if s["roi"]        >= 0 else ""

    lines: list[str] = [
        f"PROFIT REPORT -- Racing Intelligence System",
        f"Date: {date_str} | Model: {model_ver}",
        "",
        _SEP_DOUBLE,
        "OFFICIAL PERFORMANCE (NAP selections only)",
        _SEP_DOUBLE,
        _fmt_stat_line("Total Official Bets:", str(o["total_bets"])),
        _fmt_stat_line(
            "Wins:",
            f"{o['total_wins']} ({o['strike_rate']:.1f}%)"
        ),
        _fmt_stat_line(
            "Places:",
            f"{o['total_places']} ({o['place_rate']:.1f}%)"
        ),
        _fmt_stat_line(
            "Cumulative P/L:",
            f"{o_pl_sign}{o['total_pl']:.2f} units"
        ),
        _fmt_stat_line(
            "ROI:",
            f"{o_roi_sign}{o['roi']:.1f}%"
        ),
        "",
        "BY GRADE:",
    ]

    for grade in ["A", "B+", "B", "C"]:
        lines.append(_fmt_grade_row(grade, grade_stats.get(grade, {})))

    if month_stats:
        lines += ["", "BY MONTH:"]
        for month in sorted(month_stats.keys()):
            lines.append(_fmt_month_row(month, month_stats[month]))

    lines += [
        "",
        _SEP_DOUBLE,
        "SHADOW PERFORMANCE (tracking only -- NOT official)",
        _SEP_DOUBLE,
        _fmt_stat_line("Total Shadow Bets:", str(s["total_bets"])),
        _fmt_stat_line(
            "Wins:",
            f"{s['total_wins']} ({s['strike_rate']:.1f}%)"
        ),
        _fmt_stat_line(
            "Places:",
            f"{s['total_places']} ({s['place_rate']:.1f}%)"
        ),
        _fmt_stat_line(
            "Shadow P/L:",
            f"{s_pl_sign}{s['total_pl']:.2f} units"
        ),
        _fmt_stat_line(
            "Shadow ROI:",
            f"{s_roi_sign}{s['roi']:.1f}%"
        ),
    ]

    if shadow_month_stats:
        lines += ["", "BY MONTH (SHADOW):"]
        for month in sorted(shadow_month_stats.keys()):
            lines.append(_fmt_month_row(month, shadow_month_stats[month]))

    lines += [
        "",
        "  [!] Shadow performance is NOT official betting performance.",
        "  [!] Shadow figures are for model learning and comparison only.",
        "",
        _SEP_DOUBLE,
    ]

    return "\n".join(lines)


def _build_no_data_report(date_str: str, model_ver: str) -> str:
    return (
        f"PROFIT REPORT -- Racing Intelligence System\n"
        f"Date: {date_str} | Model: {model_ver}\n\n"
        f"{_SEP_DOUBLE}\n"
        f"No performance data available yet.\n\n"
        f"performance_log.csv has not been created. Run results_auditor.py\n"
        f"and performance_tracker.py first to populate the log.\n"
        f"{_SEP_DOUBLE}\n"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Generate profit report. Returns exit code."""
    log("profit_report.py started")

    date_str: str = today_str()
    model_ver: str = _model_version()
    log(f"profit_report: date={date_str}, model={model_ver}")

    # ------------------------------------------------------------------
    # 1. Load CSV
    # ------------------------------------------------------------------
    csv_path = _csv_path()
    rows = _load_csv(csv_path)

    report_dest = report_path(f"profit_report_{date_str}.txt")

    if rows is None:
        # No CSV yet — write "no data" report.
        log("profit_report: no performance_log.csv — writing no-data report", "WARNING")
        report_text = _build_no_data_report(date_str, model_ver)
        try:
            with open(report_dest, "w", encoding="utf-8") as fh:
                fh.write(report_text)
            log(f"profit_report: no-data report saved → {report_dest}")
        except OSError as exc:
            log(f"profit_report: failed to write no-data report — {exc}", "ERROR")
            return 1
        print(f"profit_report: no data yet — report written to {report_dest}")
        return 0

    # ------------------------------------------------------------------
    # 2. Compute stats
    # ------------------------------------------------------------------

    # Separate official rows (official_stake > 0) from shadow rows
    official_rows = [r for r in rows if _safe_float(r.get("official_stake")) > 0]
    shadow_rows   = [r for r in rows if _safe_float(r.get("shadow_stake"))   > 0]

    official_stats = _compute_segment_stats(official_rows)
    shadow_stats   = _compute_segment_stats(shadow_rows, is_shadow=True)
    grade_stats    = _grade_breakdown(rows)
    month_stats    = _month_breakdown(rows)
    shadow_months  = _shadow_month_breakdown(rows)

    log(
        f"profit_report: official rows={len(official_rows)}, "
        f"shadow rows={len(shadow_rows)}, "
        f"cumulative_pl={official_stats['total_pl']:+.2f}"
    )

    # ------------------------------------------------------------------
    # 3. Build and save report
    # ------------------------------------------------------------------
    report_text = _build_report(
        date_str,
        model_ver,
        official_stats,
        shadow_stats,
        grade_stats,
        month_stats,
        shadow_months,
    )

    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
        log(f"profit_report: report saved → {report_dest}")
    except OSError as exc:
        log(f"profit_report: failed to write report — {exc}", "ERROR")
        return 1

    print(
        f"profit_report: COMPLETE — "
        f"official_bets={official_stats['total_bets']}, "
        f"wins={official_stats['total_wins']}, "
        f"pl={official_stats['total_pl']:+.2f}, "
        f"roi={official_stats['roi']:+.1f}%"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
