"""
horse_tracker_promoter.py — Review tracked horses for promotion to active
betting consideration.

Purpose:
    Load data/horse_tracker.json and cross-reference against results history
    stored in performance_log.csv and any available results_YYYY-MM-DD.json
    files.  Compute activation counts, win/place rates, and apply the
    promotion gates defined in the system blueprint.

Promotion gates (evidence-only — no angle is active without 20+ examples):
    1–19 activations:  LEARNING only  — no promotion
    20–49 activations: WATCH ANGLE    — monitor strike rate, place rate, ROI
    50+ activations:   POSSIBLE ACTIVE if positive A/E, ROI, and logic support

The promoter does NOT change the official NAP system.  It only reports
which tracker patterns are approaching evidence thresholds.

Outputs:
    reports/tracker_promoter_YYYY-MM-DD.txt

Exit codes:
    0 — success
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
# Promotion gate thresholds (must match system blueprint exactly)
# ---------------------------------------------------------------------------
LEARNING_THRESHOLD = 20   # Below this: learning only
WATCH_THRESHOLD = 50      # Below this (but >= LEARNING): watch angle
# At or above WATCH_THRESHOLD: possible active if all criteria met


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

CSV_FILENAME = "performance_log.csv"


def _csv_path() -> str:
    try:
        cfg = get_config()
        return str(Path(cfg.project_dir) / CSV_FILENAME)
    except Exception as exc:
        log(f"horse_tracker_promoter: could not resolve project_dir — {exc}", "WARNING")
        return CSV_FILENAME


def _load_csv_rows() -> list[dict]:
    path = _csv_path()
    p = Path(path)
    if not p.exists():
        log(f"horse_tracker_promoter: performance_log.csv not found at {path}", "WARNING")
        return []
    try:
        with open(p, "r", newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        log(f"horse_tracker_promoter: loaded {len(rows)} rows from CSV")
        return rows
    except OSError as exc:
        log(f"horse_tracker_promoter: error reading CSV — {exc}", "WARNING")
        return []


# ---------------------------------------------------------------------------
# Results file discovery (last 90 days)
# ---------------------------------------------------------------------------

def _load_all_results(lookback_days: int = 90) -> list[dict]:
    """Load all runner records from results_YYYY-MM-DD.json files for the
    last *lookback_days* days.  Returns a flat list of result rows."""
    all_runners: list[dict] = []
    today = date.today()

    for offset in range(lookback_days):
        check_date = today - timedelta(days=offset)
        date_str = check_date.isoformat()
        path = data_path(f"results_{date_str}.json")
        doc = safe_load_json(path)
        if doc is None:
            continue
        for key in ("official_results", "shadow_results", "watchlist_results"):
            for r in doc.get(key) or []:
                r["_result_date"] = date_str
                all_runners.append(r)

    log(f"horse_tracker_promoter: loaded {len(all_runners)} runner records from results files")
    return all_runners


# ---------------------------------------------------------------------------
# Activation analysis per tracked horse
# ---------------------------------------------------------------------------

def _analyse_tracked_horse(
    entry: dict,
    results_by_horse: dict[str, list[dict]],
) -> dict:
    """Build an analysis dict for a single tracked horse.

    Returns:
        horse_id, horse_name, flag_reason, status,
        total_runs_in_results, activations, wins, places,
        strike_rate, place_rate, promotion_status
    """
    horse_id = entry.get("horse_id", "")
    horse_name = entry.get("horse_name", "Unknown")
    flag_reason = entry.get("flag_reason", "unknown")

    # All recorded results for this horse
    results = results_by_horse.get(horse_id, [])
    total_runs = len(results)

    # "Activations" = runs where conditions were met (for the tracker's purpose
    # we count all recorded results as potential activations, since the tracker
    # review stamps conditions_met on actual race days).
    # Without live conditions_met data in the results JSON (it isn't stored there),
    # we use all recorded results as a proxy for activations.
    activations = total_runs
    wins = sum(1 for r in results if str(r.get("won", "")).lower() in ("true", "1", "yes"))
    places = sum(
        1 for r in results
        if str(r.get("placed", "")).lower() in ("true", "1", "yes")
    )

    strike_rate = round(wins / activations * 100, 1) if activations > 0 else 0.0
    place_rate = round(places / activations * 100, 1) if activations > 0 else 0.0

    # Calculate simple ROI from official_pl across all results
    total_pl = 0.0
    total_stake = 0.0
    for r in results:
        try:
            stake = float(r.get("official_stake") or 0)
            pl = float(r.get("official_pl") or 0)
        except (TypeError, ValueError):
            stake = 0.0
            pl = 0.0
        if stake > 0:
            total_stake += stake
            total_pl += pl
    roi = round(total_pl / total_stake * 100, 1) if total_stake > 0 else None

    # Determine promotion status
    if activations < LEARNING_THRESHOLD:
        promo_status = f"LEARNING (needs {LEARNING_THRESHOLD - activations} more activations)"
    elif activations < WATCH_THRESHOLD:
        promo_status = f"WATCH ANGLE ({activations} activations — monitor strike/ROI)"
    else:
        # 50+ activations — check positive ROI criteria
        if roi is not None and roi > 0 and strike_rate >= 15.0:
            promo_status = (
                f"POSSIBLE ACTIVE ANGLE — {activations} activations, "
                f"ROI={roi:+.1f}%, SR={strike_rate:.1f}% — "
                "MANUAL REVIEW REQUIRED before any promotion"
            )
        else:
            promo_status = (
                f"WATCH ANGLE (50+ activations but ROI/SR not positive enough yet)"
            )

    return {
        "horse_id":      horse_id,
        "horse_name":    horse_name,
        "flag_reason":   flag_reason,
        "entry_status":  entry.get("status", "watching"),
        "flagged_date":  entry.get("flagged_date", ""),
        "activations":   activations,
        "wins":          wins,
        "places":        places,
        "strike_rate":   strike_rate,
        "place_rate":    place_rate,
        "roi":           roi,
        "promo_status":  promo_status,
    }


# ---------------------------------------------------------------------------
# Report formatter
# ---------------------------------------------------------------------------

def _build_report(
    date_str: str,
    tracker_doc: dict,
    analyses: list[dict],
    activations_this_month: int,
) -> str:
    active_count = sum(
        1 for e in (tracker_doc.get("tracked") or [])
        if e.get("status") == "watching"
    )

    sep = "=" * 60
    thin = "-" * 60

    lines: list[str] = [
        "HORSE TRACKER PROMOTION REVIEW",
        f"Date: {date_str}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        sep,
        "SUMMARY",
        sep,
        f"  Active tracked horses:              {active_count}",
        f"  Near-miss alerts activated (month): {activations_this_month}",
        "",
        "  Promotion gates:",
        f"    1–{LEARNING_THRESHOLD - 1} activations → LEARNING only",
        f"    {LEARNING_THRESHOLD}–{WATCH_THRESHOLD - 1} activations → WATCH ANGLE",
        f"    {WATCH_THRESHOLD}+ activations → POSSIBLE ACTIVE (if +ROI & +SR)",
        "",
        sep,
        "PROMOTION REVIEW (all active horses with recorded results)",
        sep,
    ]

    if not analyses:
        lines.append("  No tracked horses have recorded results yet.")
    else:
        for a in sorted(analyses, key=lambda x: x["activations"], reverse=True):
            roi_str = f"{a['roi']:+.1f}%" if a["roi"] is not None else "N/A"
            lines += [
                thin,
                f"  {a['horse_name']}",
                f"    Reason flagged:  {a['flag_reason']}",
                f"    Activations:     {a['activations']}",
                f"    Wins:            {a['wins']} ({a['strike_rate']:.1f}%)",
                f"    Places:          {a['places']} ({a['place_rate']:.1f}%)",
                f"    ROI:             {roi_str}",
                f"    Status:          {a['promo_status']}",
                "",
            ]

    lines += [
        sep,
        "No horses promoted to active angle today (insufficient evidence).",
        "",
        "IMPORTANT: No angle becomes active betting logic without 20+ examples",
        "and positive ROI across a statistically meaningful sample.",
        sep,
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Run the promoter review. Returns exit code."""
    log("horse_tracker_promoter.py started")

    date_str = today_str()
    log(f"horse_tracker_promoter: date={date_str}")

    # ------------------------------------------------------------------
    # 1. Load tracker
    # ------------------------------------------------------------------
    tracker_path = data_path("horse_tracker.json")
    tracker_doc = safe_load_json(tracker_path)

    if tracker_doc is None:
        log(
            "horse_tracker_promoter: horse_tracker.json not found. "
            "Run horse_tracker.py --flag first.",
            "WARNING",
        )
        tracker_doc = {"tracked": []}

    all_entries: list[dict] = tracker_doc.get("tracked") or []
    active_entries = [e for e in all_entries if e.get("status") == "watching"]
    log(f"horse_tracker_promoter: {len(active_entries)} active entries")

    # ------------------------------------------------------------------
    # 2. Load results data — results JSON files (last 90 days)
    # ------------------------------------------------------------------
    all_results = _load_all_results(lookback_days=90)

    # Index by horse_id for fast lookup
    results_by_horse: dict[str, list[dict]] = defaultdict(list)
    for r in all_results:
        h_id = str(r.get("horse_id") or "").strip()
        if h_id:
            results_by_horse[h_id].append(r)

    # ------------------------------------------------------------------
    # 3. Count near-miss activations this calendar month
    # ------------------------------------------------------------------
    today_date = date.today()
    month_start = date(today_date.year, today_date.month, 1).isoformat()

    activations_this_month = 0
    for entry in active_entries:
        if entry.get("flag_reason") == "near_miss":
            h_id = entry.get("horse_id", "")
            for r in results_by_horse.get(h_id, []):
                result_date = r.get("_result_date", "")
                if result_date >= month_start:
                    activations_this_month += 1

    # ------------------------------------------------------------------
    # 4. Analyse each active horse with results data
    # ------------------------------------------------------------------
    analyses: list[dict] = []
    for entry in active_entries:
        horse_id = entry.get("horse_id", "")
        if horse_id in results_by_horse:
            analysis = _analyse_tracked_horse(entry, results_by_horse)
            analyses.append(analysis)
        # Horses with zero results are skipped in the detailed section

    log(
        f"horse_tracker_promoter: {len(analyses)} horses have recorded results"
    )

    # ------------------------------------------------------------------
    # 5. Build and save report
    # ------------------------------------------------------------------
    report_text = _build_report(
        date_str,
        tracker_doc,
        analyses,
        activations_this_month,
    )

    report_dest = report_path(f"tracker_promoter_{date_str}.txt")
    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
        log(f"horse_tracker_promoter: report saved → {report_dest}")
    except OSError as exc:
        log(f"horse_tracker_promoter: failed to write report — {exc}", "ERROR")
        return 1

    # ------------------------------------------------------------------
    # 6. Console summary
    # ------------------------------------------------------------------
    possible_active = sum(
        1 for a in analyses
        if "POSSIBLE ACTIVE" in a["promo_status"]
    )
    print(
        f"horse_tracker_promoter: COMPLETE — "
        f"active_tracked={len(active_entries)}, "
        f"with_results={len(analyses)}, "
        f"possible_active={possible_active}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
