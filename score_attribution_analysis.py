"""
score_attribution_analysis.py — Model calibration and attribution analysis.

Reads the most recent backtest CSV (data/backtest_*.csv) produced by
historical_backtest.py and analyses:
  1. Score-band calibration (actual win rate per narrow band)
  2. Grade A vs B+ performance and optimal minimum-score threshold
  3. Threshold sweep 55–80: ROI, strike rate, Sharpe-like ratio
  4. Sub-score correlation with winning outcome
  5. Grade × race-type × class interaction ("golden zone")
  6. Near-miss analysis (winner in scored field but not picked)
  7. Score ceiling / component utilisation analysis

Outputs:
  reports/score_attribution_{date}.txt
  data/score_attribution_{date}.json

Usage:
  python score_attribution_analysis.py
  python score_attribution_analysis.py --csv data/my_file.csv

Exit codes:
  0 — report produced
  1 — fatal error (no data, write failure)
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import defaultdict
from datetime import date
from glob import glob
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR    = PROJECT_DIR / "data"
REPORTS_DIR = PROJECT_DIR / "reports"


def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# CSV column name constants
# (Matches keys set in historical_backtest.py all_records dict, lines 490-517)
# ---------------------------------------------------------------------------

COL_DATE        = "date"
COL_SCORE       = "score"
COL_GRADE       = "grade"
COL_FORM        = "form_score"
COL_SUIT        = "suit_score"          # abbreviated in backtest CSV
COL_CTX         = "ctx_score"
COL_TRAIN       = "train_score"
COL_MKT         = "mkt_score"
COL_IS_WIN      = "is_win"
COL_IS_PLACE    = "is_place"
COL_HAS_RESULT  = "has_result"
COL_SP_DEC      = "sp_dec"
COL_RACE_TYPE   = "race_type"
COL_RACE_CLASS  = "race_class"
COL_TYPE_GROUP  = "type_group"
COL_CLASS_GROUP = "class_group"
COL_DIST_GROUP  = "dist_group"
COL_GOING_GROUP = "going_group"
COL_SCORE_BAND  = "score_band"
COL_POSITION    = "position"
COL_HORSE_ID    = "horse_id"
COL_DATE_COL    = "date"

# Sub-score ceilings (from nap_selector_v3.py docstring)
SUBSCORE_CEILINGS = {
    COL_FORM:  40.0,
    COL_SUIT:  25.0,
    COL_CTX:   15.0,
    COL_TRAIN: 15.0,
    COL_MKT:    5.0,   # practical maximum (min is -10)
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _safe_bool(val) -> bool:
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in ("true", "1", "yes")


def _parse_row(row: dict) -> dict:
    """Normalise a CSV row — convert types, handle missing columns."""
    return {
        COL_DATE:        row.get(COL_DATE, ""),
        COL_SCORE:       _safe_float(row.get(COL_SCORE)),
        COL_GRADE:       row.get(COL_GRADE, ""),
        COL_FORM:        _safe_float(row.get(COL_FORM)) if COL_FORM in row else None,
        COL_SUIT:        _safe_float(row.get(COL_SUIT)) if COL_SUIT in row else None,
        COL_CTX:         _safe_float(row.get(COL_CTX)) if COL_CTX in row else None,
        COL_TRAIN:       _safe_float(row.get(COL_TRAIN)) if COL_TRAIN in row else None,
        COL_MKT:         _safe_float(row.get(COL_MKT)) if COL_MKT in row else None,
        COL_IS_WIN:      _safe_bool(row.get(COL_IS_WIN, False)),
        COL_IS_PLACE:    _safe_bool(row.get(COL_IS_PLACE, False)),
        COL_HAS_RESULT:  _safe_bool(row.get(COL_HAS_RESULT, False)),
        COL_SP_DEC:      _safe_float(row.get(COL_SP_DEC)),
        COL_RACE_TYPE:   row.get(COL_RACE_TYPE, ""),
        COL_RACE_CLASS:  row.get(COL_RACE_CLASS, ""),
        COL_TYPE_GROUP:  row.get(COL_TYPE_GROUP, ""),
        COL_CLASS_GROUP: row.get(COL_CLASS_GROUP, ""),
        COL_DIST_GROUP:  row.get(COL_DIST_GROUP, ""),
        COL_GOING_GROUP: row.get(COL_GOING_GROUP, ""),
        COL_SCORE_BAND:  row.get(COL_SCORE_BAND, ""),
        COL_POSITION:    row.get(COL_POSITION, ""),
        COL_HORSE_ID:    row.get(COL_HORSE_ID, ""),
    }


def _load_csv(path: str) -> list[dict]:
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(_parse_row(row))
    return rows


def _load_results_cache() -> dict[str, dict]:
    """
    Load per-day result caches from data/backtest_cache/results/*.json.
    Returns {date_str: {horse_id: {position, sp_dec}}} where available.
    Falls back to empty dict if directory doesn't exist.
    """
    results_dir = DATA_DIR / "backtest_cache" / "results"
    lookup: dict[str, dict] = {}
    if not results_dir.exists():
        return lookup
    for jf in results_dir.glob("*.json"):
        date_key = jf.stem
        try:
            with open(jf, encoding="utf-8") as fh:
                data = json.load(fh)
            # Format may be {date: {horse_id: {...}}} or flat {horse_id: {...}}
            if date_key in data:
                lookup[date_key] = data[date_key]
            else:
                lookup[date_key] = data
        except (OSError, json.JSONDecodeError):
            pass
    return lookup


def _find_latest_csv() -> Optional[str]:
    pattern = str(DATA_DIR / "backtest_*.csv")
    matches = glob(pattern)
    if not matches:
        return None
    # Sort by modification time, return most recent
    return max(matches, key=os.path.getmtime)


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------

def _pearson(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation coefficient. Returns 0.0 if n < 2 or no variance."""
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denom_x = math.sqrt(sum((x - mx) ** 2 for x in xs))
    denom_y = math.sqrt(sum((y - my) ** 2 for y in ys))
    if denom_x == 0 or denom_y == 0:
        return 0.0
    return num / (denom_x * denom_y)


def _roi(wins: int, n: int, pl: float) -> float:
    return (pl / n * 100) if n > 0 else 0.0


def _strike(wins: int, n: int) -> float:
    return (wins / n * 100) if n > 0 else 0.0


# ---------------------------------------------------------------------------
# Section 2: Score-band calibration
# ---------------------------------------------------------------------------

def calibration_table(rows: list[dict], band_width: int = 2) -> list[dict]:
    """
    Build calibration table in narrow score bands.
    band_width=2 → bands 55-57, 57-59, ... 83-85, 85+
    Returns list of dicts sorted by band_low.
    """
    from collections import defaultdict
    # Only rows with result data
    result_rows = [r for r in rows if r[COL_HAS_RESULT]]

    buckets: dict[int, list] = defaultdict(list)
    BAND_MIN = 55
    BAND_MAX = 85

    for r in result_rows:
        score = r[COL_SCORE]
        if score < BAND_MIN:
            continue
        if score >= BAND_MAX:
            band_low = BAND_MAX
        else:
            band_low = int((score - BAND_MIN) // band_width) * band_width + BAND_MIN
        buckets[band_low].append(r)

    table = []
    all_lows = sorted(buckets.keys())
    prev_win_rate = None

    for low in all_lows:
        bucket = buckets[low]
        high = (low + band_width) if low < BAND_MAX else None
        n = len(bucket)
        wins = sum(1 for r in bucket if r[COL_IS_WIN])
        pl = sum((r[COL_SP_DEC] - 1.0) if r[COL_IS_WIN] else -1.0 for r in bucket)
        win_rate = (wins / n * 100) if n > 0 else None
        roi_val = (pl / n * 100) if n > 0 else None

        inversion = False
        if prev_win_rate is not None and win_rate is not None and n >= 5:
            inversion = win_rate < prev_win_rate

        label = f"{low}-{high}" if high else f"{low}+"
        entry = {
            "band":       label,
            "band_low":   low,
            "n":          n,
            "wins":       wins,
            "win_rate":   round(win_rate, 1) if win_rate is not None else None,
            "roi":        round(roi_val, 1) if roi_val is not None else None,
            "inversion":  inversion,
        }
        table.append(entry)
        if n >= 5:
            prev_win_rate = win_rate

    return table


# ---------------------------------------------------------------------------
# Section 3: Grade analysis
# ---------------------------------------------------------------------------

def grade_analysis(rows: list[dict]) -> dict:
    result_rows = [r for r in rows if r[COL_HAS_RESULT]]

    grade_stats: dict[str, dict] = {}
    for grade in ("A", "B+", "B", "C", "D"):
        subset = [r for r in result_rows if r[COL_GRADE] == grade]
        n = len(subset)
        wins = sum(1 for r in subset if r[COL_IS_WIN])
        pl = sum((r[COL_SP_DEC] - 1.0) if r[COL_IS_WIN] else -1.0 for r in subset)
        grade_stats[grade] = {
            "n": n, "wins": wins,
            "win_rate": round(_strike(wins, n), 1),
            "roi":      round(_roi(wins, n, pl), 1),
        }

    # Optimal minimum score threshold search: 55, 60, 62, 65, 67, 70
    threshold_results = {}
    for thresh in (55, 60, 62, 65, 67, 70):
        subset = [r for r in result_rows if r[COL_SCORE] >= thresh]
        n = len(subset)
        wins = sum(1 for r in subset if r[COL_IS_WIN])
        pl = sum((r[COL_SP_DEC] - 1.0) if r[COL_IS_WIN] else -1.0 for r in subset)
        threshold_results[thresh] = {
            "n":        n,
            "wins":     wins,
            "win_rate": round(_strike(wins, n), 1),
            "roi":      round(_roi(wins, n, pl), 1),
        }

    return {"by_grade": grade_stats, "by_threshold": threshold_results}


# ---------------------------------------------------------------------------
# Section 4: Threshold sweep (ROI and Sharpe-like)
# ---------------------------------------------------------------------------

def threshold_sweep(rows: list[dict], min_bets: int = 30) -> dict:
    result_rows = [r for r in rows if r[COL_HAS_RESULT]]

    results = []
    best_roi_entry = None
    best_sharpe_entry = None

    for thresh in range(55, 81):
        subset = [r for r in result_rows if r[COL_SCORE] >= thresh]
        n = len(subset)
        wins = sum(1 for r in subset if r[COL_IS_WIN])
        pl = sum((r[COL_SP_DEC] - 1.0) if r[COL_IS_WIN] else -1.0 for r in subset)
        roi_val = _roi(wins, n, pl)
        sharpe = (roi_val / math.sqrt(n)) if n >= min_bets else None

        entry = {
            "threshold": thresh,
            "n":         n,
            "wins":      wins,
            "win_rate":  round(_strike(wins, n), 1),
            "roi":       round(roi_val, 1),
            "sharpe":    round(sharpe, 3) if sharpe is not None else None,
            "valid":     n >= min_bets,
        }
        results.append(entry)

        if n >= min_bets:
            if best_roi_entry is None or roi_val > best_roi_entry["roi"]:
                best_roi_entry = entry
            if sharpe is not None and (
                best_sharpe_entry is None or sharpe > (best_sharpe_entry["sharpe"] or -999)
            ):
                best_sharpe_entry = entry

    return {
        "sweep":             results,
        "best_roi":          best_roi_entry,
        "best_sharpe":       best_sharpe_entry,
        "min_bets_required": min_bets,
    }


# ---------------------------------------------------------------------------
# Section 5: Sub-score correlation
# ---------------------------------------------------------------------------

def subscore_correlation(rows: list[dict]) -> dict:
    result_rows = [r for r in rows if r[COL_HAS_RESULT]]
    outcome = [1.0 if r[COL_IS_WIN] else 0.0 for r in result_rows]

    sub_cols = [COL_FORM, COL_SUIT, COL_CTX, COL_TRAIN, COL_MKT]
    sub_names = {
        COL_FORM:  "Form Quality   (0-40)",
        COL_SUIT:  "Suitability    (0-25)",
        COL_CTX:   "Race Context   (0-15)",
        COL_TRAIN: "Trainer Intent (0-15)",
        COL_MKT:   "Market Overlay (-10/+5)",
    }

    # Check if sub-scores are present in data
    first_with_sub = next(
        (r for r in result_rows if r.get(COL_FORM) is not None), None
    )
    sub_scores_available = first_with_sub is not None

    correlations = {}
    if sub_scores_available:
        for col in sub_cols:
            vals = [r[col] for r in result_rows if r.get(col) is not None]
            outs = [
                1.0 if result_rows[i][COL_IS_WIN] else 0.0
                for i, r in enumerate(result_rows)
                if r.get(col) is not None
            ]
            if len(vals) < 5:
                continue
            corr = _pearson(vals, outs)
            winners = [r for r in result_rows if r[COL_IS_WIN] and r.get(col) is not None]
            losers  = [r for r in result_rows if not r[COL_IS_WIN] and r.get(col) is not None]
            avg_win  = (sum(r[col] for r in winners) / len(winners)) if winners else None
            avg_loss = (sum(r[col] for r in losers)  / len(losers))  if losers  else None
            correlations[col] = {
                "name":     sub_names.get(col, col),
                "pearson":  round(corr, 4),
                "avg_win":  round(avg_win, 2)  if avg_win  is not None else None,
                "avg_loss": round(avg_loss, 2) if avg_loss is not None else None,
                "diff":     round(avg_win - avg_loss, 2) if avg_win is not None and avg_loss is not None else None,
                "n":        len(vals),
            }

        best_col = max(
            correlations,
            key=lambda c: abs(correlations[c]["pearson"]) if correlations[c]["pearson"] else 0,
            default=None,
        )
    else:
        # Sub-scores not in CSV — provide expected contribution ranges from model logic
        correlations = {
            COL_FORM: {
                "name":    sub_names[COL_FORM],
                "note":    "Not in CSV. RPR rank (0-15) + position points (0-20) + trend (-3/+3) + freshness (-4/+2). Widest absolute range.",
            },
            COL_SUIT: {
                "name":    sub_names[COL_SUIT],
                "note":    "Not in CSV. Distance/going/course win history (0-23 with full_form, 0-10 fallback).",
            },
            COL_CTX: {
                "name":    sub_names[COL_CTX],
                "note":    "Not in CSV. Field size (0-8) + class bonus (−4 to +5). Narrow range.",
            },
            COL_TRAIN: {
                "name":    sub_names[COL_TRAIN],
                "note":    "Not in CSV. Strike% bonus (0-8) + wind surgery (0-3) + commentary (0-2). Moderate range.",
            },
            COL_MKT: {
                "name":    sub_names[COL_MKT],
                "note":    "Not in CSV. Morning price band (−6 to +5) + market movement (−10 to +5). Highest ceiling suppression risk.",
            },
        }
        best_col = None

    return {
        "sub_scores_available": sub_scores_available,
        "correlations":         correlations,
        "best_discriminator":   best_col,
    }


# ---------------------------------------------------------------------------
# Section 6: Grade × Race type × Class interaction
# ---------------------------------------------------------------------------

def grade_racetype_class_interaction(rows: list[dict], min_n: int = 5) -> dict:
    result_rows = [r for r in rows if r[COL_HAS_RESULT]]

    # Grade × type_group
    gt: dict[str, dict] = defaultdict(lambda: {"n": 0, "wins": 0, "pl": 0.0})
    for r in result_rows:
        key = f"{r[COL_GRADE]} × {r[COL_TYPE_GROUP]}"
        gt[key]["n"] += 1
        if r[COL_IS_WIN]:
            gt[key]["wins"] += 1
            gt[key]["pl"] += r[COL_SP_DEC] - 1.0
        else:
            gt[key]["pl"] -= 1.0

    # Grade × class_group
    gc: dict[str, dict] = defaultdict(lambda: {"n": 0, "wins": 0, "pl": 0.0})
    for r in result_rows:
        key = f"{r[COL_GRADE]} × {r[COL_CLASS_GROUP]}"
        gc[key]["n"] += 1
        if r[COL_IS_WIN]:
            gc[key]["wins"] += 1
            gc[key]["pl"] += r[COL_SP_DEC] - 1.0
        else:
            gc[key]["pl"] -= 1.0

    # Grade A only: type × class
    golden: dict[str, dict] = defaultdict(lambda: {"n": 0, "wins": 0, "pl": 0.0})
    for r in [r for r in result_rows if r[COL_GRADE] == "A"]:
        key = f"{r[COL_TYPE_GROUP]} × {r[COL_CLASS_GROUP]}"
        golden[key]["n"] += 1
        if r[COL_IS_WIN]:
            golden[key]["wins"] += 1
            golden[key]["pl"] += r[COL_SP_DEC] - 1.0
        else:
            golden[key]["pl"] -= 1.0

    def _finalise(d: dict) -> list[dict]:
        out = []
        for key, v in d.items():
            n, wins, pl = v["n"], v["wins"], v["pl"]
            if n < min_n:
                continue
            out.append({
                "combo":    key,
                "n":        n,
                "wins":     wins,
                "win_rate": round(_strike(wins, n), 1),
                "roi":      round(_roi(wins, n, pl), 1),
            })
        return sorted(out, key=lambda x: -x["roi"])

    gt_list    = _finalise(gt)
    gc_list    = _finalise(gc)
    golden_list = _finalise(golden)

    best_gt     = gt_list[0]     if gt_list     else None
    best_gc     = gc_list[0]     if gc_list     else None
    golden_zone = golden_list[0] if golden_list else None

    return {
        "grade_x_type":      gt_list,
        "grade_x_class":     gc_list,
        "grade_a_x_typexcls": golden_list,
        "best_grade_type":   best_gt,
        "best_grade_class":  best_gc,
        "golden_zone":       golden_zone,
    }


# ---------------------------------------------------------------------------
# Section 7: Near-miss analysis
# ---------------------------------------------------------------------------

def near_miss_analysis(rows: list[dict], results_cache: dict) -> dict:
    """
    Analyse days where we picked the top scorer but still lost.
    Uses the CSV data (one row per race top scorer) to check:
    - Days where the actual winner likely had a higher score (proxy: winner position in data).

    Because the CSV only contains the TOP scorer per race (not all runners), we
    use a conservative heuristic: for each day's race selections, we check if
    there was any winning horse in our dataset that day that we did NOT select.
    We also check coverage: what fraction of days had ANY winner in our data.
    """
    # Group rows by date
    by_date: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_date[r[COL_DATE]].append(r)

    total_days = 0
    days_winner_in_data = 0
    days_we_selected_winner = 0
    days_we_missed_winner = 0
    miss_details = []

    for d, day_rows in sorted(by_date.items()):
        result_rows = [r for r in day_rows if r[COL_HAS_RESULT]]
        if not result_rows:
            continue
        total_days += 1
        winners = [r for r in result_rows if r[COL_IS_WIN]]

        if winners:
            days_winner_in_data += 1
            # The row with highest score on this day
            best_scored = max(result_rows, key=lambda r: r[COL_SCORE])
            if best_scored[COL_IS_WIN]:
                days_we_selected_winner += 1
            else:
                days_we_missed_winner += 1
                # Find the actual winner with their score
                winner = winners[0]
                miss_details.append({
                    "date":          d,
                    "our_pick":      best_scored[COL_HORSE_ID],
                    "our_score":     best_scored[COL_SCORE],
                    "our_grade":     best_scored[COL_GRADE],
                    "winner_score":  winner[COL_SCORE],
                    "winner_grade":  winner[COL_GRADE],
                    "score_gap":     round(best_scored[COL_SCORE] - winner[COL_SCORE], 2),
                })

    coverage_pct = round(days_winner_in_data / total_days * 100, 1) if total_days else 0
    selection_accuracy = round(days_we_selected_winner / days_winner_in_data * 100, 1) if days_winner_in_data else 0

    # Among misses: how many times did the winner have a higher score?
    winner_had_higher_score = sum(
        1 for m in miss_details if m["score_gap"] < 0
    )
    winner_had_lower_score = sum(
        1 for m in miss_details if m["score_gap"] >= 0
    )

    return {
        "total_days_with_results":   total_days,
        "days_winner_in_data":       days_winner_in_data,
        "coverage_pct":              coverage_pct,
        "days_we_selected_winner":   days_we_selected_winner,
        "days_we_missed_winner":     days_we_missed_winner,
        "selection_accuracy_pct":    selection_accuracy,
        "miss_winner_had_higher_score": winner_had_higher_score,
        "miss_winner_had_lower_score":  winner_had_lower_score,
        "miss_sample":               miss_details[:20],
    }


# ---------------------------------------------------------------------------
# Section 8: Score ceiling / component utilisation
# ---------------------------------------------------------------------------

def ceiling_analysis(rows: list[dict]) -> dict:
    sub_cols = [COL_FORM, COL_SUIT, COL_CTX, COL_TRAIN, COL_MKT]
    thresholds = {
        COL_FORM:  [30.0, 35.0, 40.0],
        COL_SUIT:  [15.0, 20.0, 25.0],
        COL_CTX:   [10.0, 12.0, 15.0],
        COL_TRAIN: [10.0, 12.0, 15.0],
        COL_MKT:   [3.0,  5.0],
    }
    ceilings = {
        COL_FORM: 40.0, COL_SUIT: 25.0, COL_CTX: 15.0,
        COL_TRAIN: 15.0, COL_MKT: 5.0,
    }
    sub_names = {
        COL_FORM:  "Form Quality",
        COL_SUIT:  "Suitability",
        COL_CTX:   "Race Context",
        COL_TRAIN: "Trainer Intent",
        COL_MKT:   "Market Overlay",
    }

    result = {}
    rows_with_sub = [r for r in rows if r.get(COL_FORM) is not None]
    sub_available = len(rows_with_sub) > 0

    if not sub_available:
        return {
            "sub_scores_available": False,
            "note": "Sub-scores not in CSV. Cannot compute ceiling utilisation from data alone.",
            "theoretical_analysis": {
                COL_FORM: {
                    "name": sub_names[COL_FORM],
                    "ceiling": 40.0,
                    "max_achievable": "~35 (RPR top=15 + LTO win=12 + improving trend=3 + ideal break=2 + 3 runs ago=3). Rarely hit ceiling.",
                },
                COL_SUIT: {
                    "name": sub_names[COL_SUIT],
                    "ceiling": 25.0,
                    "max_achievable": "23 with full_form (dist win=10 + going win=8 + course win=5). Fallback max=10. Chronically underclaimed in backtest mode.",
                },
                COL_CTX: {
                    "name": sub_names[COL_CTX],
                    "ceiling": 15.0,
                    "max_achievable": "13 (small field 6=8 + Class 1=5). Grade 1 gives same 5pts.",
                },
                COL_TRAIN: {
                    "name": sub_names[COL_TRAIN],
                    "ceiling": 15.0,
                    "max_achievable": "13 (hot trainer=8 + wind surgery=3 + commentary=2). Rarely 15.",
                },
                COL_MKT: {
                    "name": sub_names[COL_MKT],
                    "ceiling": 5.0,
                    "max_achievable": "10 (value price=5 + strong steamer=5). 10 only with live data.",
                },
            },
        }

    analysis = {}
    for col in sub_cols:
        col_vals = [r[col] for r in rows_with_sub if r.get(col) is not None]
        if not col_vals:
            continue
        n = len(col_vals)
        ceiling = ceilings[col]
        thresh_list = thresholds.get(col, [])
        thresh_stats = {}
        for t in thresh_list:
            cnt = sum(1 for v in col_vals if v >= t)
            thresh_stats[str(t)] = {"count": cnt, "pct": round(cnt / n * 100, 1)}
        max_val = max(col_vals)
        mean_val = sum(col_vals) / n
        at_ceiling = sum(1 for v in col_vals if v >= ceiling)
        analysis[col] = {
            "name":           sub_names[col],
            "ceiling":        ceiling,
            "max_observed":   round(max_val, 2),
            "mean":           round(mean_val, 2),
            "utilisation_pct": round(mean_val / ceiling * 100, 1),
            "at_ceiling_pct": round(at_ceiling / n * 100, 1),
            "threshold_pcts": thresh_stats,
            "chronically_unclaimed": max_val < ceiling * 0.9,
        }

    chronically_unclaimed = [
        col for col, v in analysis.items() if v.get("chronically_unclaimed")
    ]

    return {
        "sub_scores_available": True,
        "analysis":             analysis,
        "chronically_unclaimed_components": chronically_unclaimed,
    }


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

SEP  = "=" * 72
SEP2 = "-" * 72


def _fmt_pct(v: Optional[float]) -> str:
    return f"{v:.1f}%" if v is not None else "  —   "


def _fmt_roi(v: Optional[float]) -> str:
    if v is None:
        return "     —   "
    return f"{v:+.1f}%"


def _fmt_n(v: int) -> str:
    return f"{v:>5}"


def build_report(
    csv_path: str,
    calib: list[dict],
    grade: dict,
    sweep: dict,
    corr: dict,
    interact: dict,
    nearmiss: dict,
    ceiling: dict,
    date_str: str,
    total_rows: int,
    rows_with_result: int,
) -> str:
    lines = [
        SEP,
        "  SCORE ATTRIBUTION & CALIBRATION ANALYSIS",
        f"  Source CSV:  {csv_path}",
        f"  Total rows:  {total_rows}  |  Rows with result: {rows_with_result}",
        f"  Generated:   {date_str}",
        SEP,
        "",
    ]

    # ---- Section 2: Calibration ----
    lines += [
        "SECTION 1: SCORE-BAND CALIBRATION",
        SEP2,
        "  Model is well-calibrated if win rate increases monotonically with score.",
        "  [!] = inversion (lower band beat higher band — miscalibration signal).",
        "",
        f"  {'Band':<10} {'N':>5} {'Wins':>5} {'Win%':>7} {'ROI%':>9}  {'Flag':<6}",
        "  " + "-" * 50,
    ]
    for row in calib:
        flag = "[!] INVERSION" if row["inversion"] else ""
        n_str = _fmt_n(row["n"])
        if row["n"] < 5:
            lines.append(f"  {row['band']:<10} {n_str}   {'<5 samples — skip':30}")
        else:
            lines.append(
                f"  {row['band']:<10} {n_str} {row['wins']:>5} {_fmt_pct(row['win_rate']):>7}"
                f" {_fmt_roi(row['roi']):>9}  {flag}"
            )
    inversions = [r for r in calib if r["inversion"] and r["n"] >= 5]
    if inversions:
        lines.append("")
        lines.append(f"  ► {len(inversions)} inversion(s) detected — these score bands may be miscalibrated:")
        for inv in inversions:
            lines.append(f"    Band {inv['band']}: {_fmt_pct(inv['win_rate'])} win rate")
    else:
        lines.append("")
        lines.append("  ► No inversions detected — score ordering appears monotonically calibrated.")
    lines.append("")

    # ---- Section 3: Grade analysis ----
    lines += [
        "SECTION 2: GRADE ANALYSIS",
        SEP2,
        "",
        f"  {'Grade':<8} {'N':>5} {'Wins':>5} {'Win%':>7} {'ROI%':>9}",
        "  " + "-" * 38,
    ]
    for grade_lbl in ("A", "B+", "B", "C", "D"):
        g = grade["by_grade"].get(grade_lbl, {})
        n = g.get("n", 0)
        if n < 5:
            lines.append(f"  {grade_lbl:<8} {n:>5}    <5 samples")
        else:
            lines.append(
                f"  {grade_lbl:<8} {n:>5} {g['wins']:>5} {_fmt_pct(g['win_rate']):>7}"
                f" {_fmt_roi(g['roi']):>9}"
            )
    a = grade["by_grade"].get("A", {})
    bp = grade["by_grade"].get("B+", {})
    if a.get("n", 0) >= 5 and bp.get("n", 0) >= 5:
        rel = "better" if a["win_rate"] > bp["win_rate"] else "NOT better"
        lines.append("")
        lines.append(
            f"  ► Grade A ({a['win_rate']}% WR) is {rel} than Grade B+ ({bp['win_rate']}% WR)"
            f" | ROI gap: {a['roi']:+.1f}% vs {bp['roi']:+.1f}%"
        )
    lines.append("")
    lines += [
        "  THRESHOLD GATE COMPARISON (cumulative: score >= threshold)",
        f"  {'Threshold':<12} {'N':>5} {'Wins':>5} {'Win%':>7} {'ROI%':>9}",
        "  " + "-" * 42,
    ]
    for thresh, t in sorted(grade["by_threshold"].items()):
        n = t["n"]
        if n < 5:
            lines.append(f"  {thresh:<12} {n:>5}    <5 samples")
        else:
            lines.append(
                f"  {thresh:<12} {n:>5} {t['wins']:>5} {_fmt_pct(t['win_rate']):>7}"
                f" {_fmt_roi(t['roi']):>9}"
            )
    lines.append("")

    # ---- Section 4: Threshold sweep ----
    lines += [
        "SECTION 3: OPTIMAL THRESHOLD SEARCH (score 55-80, step 1)",
        SEP2,
        f"  Min bets required for validity: {sweep['min_bets_required']}",
        "",
        f"  {'Score':>6} {'N':>5} {'Wins':>5} {'Win%':>7} {'ROI%':>9} {'Sharpe':>8}  {'Valid':>6}",
        "  " + "-" * 56,
    ]
    for entry in sweep["sweep"]:
        valid_mark = "  OK" if entry["valid"] else "  (low n)"
        sharpe_str = f"{entry['sharpe']:>7.3f}" if entry["sharpe"] is not None else "       —"
        lines.append(
            f"  {entry['threshold']:>6} {_fmt_n(entry['n'])} {entry['wins']:>5}"
            f" {_fmt_pct(entry['win_rate']):>7} {_fmt_roi(entry['roi']):>9} {sharpe_str} {valid_mark}"
        )
    lines.append("")
    best_roi = sweep.get("best_roi")
    best_sh  = sweep.get("best_sharpe")
    if best_roi:
        lines.append(
            f"  ► MAX ROI threshold:    score >= {best_roi['threshold']}"
            f"  ({best_roi['n']} bets, {best_roi['win_rate']}% WR, {best_roi['roi']:+.1f}% ROI)"
        )
    else:
        lines.append("  ► MAX ROI threshold:    insufficient data (need >= 30 bets in any band)")
    if best_sh:
        lines.append(
            f"  ► MAX SHARPE threshold: score >= {best_sh['threshold']}"
            f"  ({best_sh['n']} bets, {best_sh['win_rate']}% WR, Sharpe={best_sh['sharpe']:.3f})"
        )
    lines.append("")

    # ---- Section 5: Correlation ----
    lines += [
        "SECTION 4: SUB-SCORE CORRELATION ANALYSIS",
        SEP2,
    ]
    if corr["sub_scores_available"]:
        lines += [
            "",
            f"  {'Component':<26} {'Pearson r':>10} {'Avg(Win)':>9} {'Avg(Loss)':>10} {'Diff':>7} {'N':>5}",
            "  " + "-" * 68,
        ]
        sorted_corrs = sorted(
            corr["correlations"].items(),
            key=lambda kv: abs(kv[1].get("pearson") or 0),
            reverse=True,
        )
        for col, cv in sorted_corrs:
            r_val  = f"{cv['pearson']:>+.4f}" if cv.get("pearson") is not None else "        —"
            aw     = f"{cv['avg_win']:>8.2f}"  if cv.get("avg_win")  is not None else "        —"
            al     = f"{cv['avg_loss']:>9.2f}" if cv.get("avg_loss") is not None else "         —"
            diff   = f"{cv['diff']:>+6.2f}"    if cv.get("diff")     is not None else "      —"
            n_str  = f"{cv['n']:>5}"           if cv.get("n")        is not None else "    —"
            lines.append(
                f"  {cv['name']:<26} {r_val:>10} {aw:>9} {al:>10} {diff:>7} {n_str:>5}"
            )
        best = corr.get("best_discriminator")
        if best and best in corr["correlations"]:
            bc = corr["correlations"][best]
            lines.append("")
            lines.append(
                f"  ► Strongest predictor: {bc['name']} (r={bc['pearson']:+.4f})"
            )
        lines.append("")
        # Identify weakest
        weakest = min(
            sorted_corrs,
            key=lambda kv: abs(kv[1].get("pearson") or 0),
            default=None,
        )
        if weakest:
            wc = weakest[1]
            lines.append(
                f"  ► Weakest predictor:   {wc['name']} (r={wc.get('pearson', 0):+.4f}) — "
                "possible noise component"
            )
    else:
        lines.append("")
        lines.append("  Sub-scores not available in CSV — showing theoretical range analysis:")
        lines.append("")
        for col, cv in corr["correlations"].items():
            lines.append(f"  {cv['name']:<26}  {cv.get('note','')}")
    lines.append("")

    # ---- Section 6: Interactions ----
    lines += [
        "SECTION 5: GRADE x RACE TYPE x CLASS INTERACTION",
        SEP2,
        "",
        "  Grade × Race Type (top by ROI, min 5 bets):",
        f"  {'Combo':<30} {'N':>5} {'Wins':>5} {'Win%':>7} {'ROI%':>9}",
        "  " + "-" * 60,
    ]
    for entry in interact["grade_x_type"][:10]:
        lines.append(
            f"  {entry['combo']:<30} {entry['n']:>5} {entry['wins']:>5}"
            f" {_fmt_pct(entry['win_rate']):>7} {_fmt_roi(entry['roi']):>9}"
        )
    lines += [
        "",
        "  Grade × Race Class (top by ROI, min 5 bets):",
        f"  {'Combo':<36} {'N':>5} {'Wins':>5} {'Win%':>7} {'ROI%':>9}",
        "  " + "-" * 66,
    ]
    for entry in interact["grade_x_class"][:10]:
        lines.append(
            f"  {entry['combo']:<36} {entry['n']:>5} {entry['wins']:>5}"
            f" {_fmt_pct(entry['win_rate']):>7} {_fmt_roi(entry['roi']):>9}"
        )
    lines += [
        "",
        "  Grade A — Type × Class GOLDEN ZONE (min 5 bets):",
        f"  {'Combo':<36} {'N':>5} {'Wins':>5} {'Win%':>7} {'ROI%':>9}",
        "  " + "-" * 66,
    ]
    for entry in interact["grade_a_x_typexcls"][:10]:
        lines.append(
            f"  {entry['combo']:<36} {entry['n']:>5} {entry['wins']:>5}"
            f" {_fmt_pct(entry['win_rate']):>7} {_fmt_roi(entry['roi']):>9}"
        )
    gz = interact.get("golden_zone")
    if gz:
        lines.append("")
        lines.append(
            f"  ► GOLDEN ZONE: {gz['combo']}"
            f"  ({gz['n']} bets, {gz['win_rate']}% WR, ROI {gz['roi']:+.1f}%)"
        )
    lines.append("")

    # ---- Section 7: Near miss ----
    nm = nearmiss
    lines += [
        "SECTION 6: NEAR-MISS ANALYSIS",
        SEP2,
        "",
        f"  Days with result data:          {nm['total_days_with_results']}",
        f"  Days with winner in dataset:    {nm['days_winner_in_data']}  ({nm['coverage_pct']}% coverage)",
        f"  Days we picked the winner:      {nm['days_we_selected_winner']}  ({nm['selection_accuracy_pct']}% of covered days)",
        f"  Days we missed the winner:      {nm['days_we_missed_winner']}",
        "",
        f"  Of missed-winner days:",
        f"    Winner had HIGHER score:      {nm['miss_winner_had_higher_score']}  (our model ranked it correctly but odds/filter excluded it)",
        f"    Winner had LOWER score:       {nm['miss_winner_had_lower_score']}  (model failure — a lower-scored horse won)",
        "",
    ]
    if nm["miss_sample"]:
        lines.append("  Sample misses (our pick score vs winner score):")
        lines.append(f"  {'Date':<12} {'Our Score':>10} {'Winner Sc':>10} {'Gap':>8} {'Our Gr':>8} {'Win Gr':>8}")
        lines.append("  " + "-" * 56)
        for m in nm["miss_sample"][:15]:
            lines.append(
                f"  {m['date']:<12} {m['our_score']:>10.1f} {m['winner_score']:>10.1f}"
                f" {m['score_gap']:>+8.1f} {m['our_grade']:>8} {m['winner_grade']:>8}"
            )
    lines.append("")

    # ---- Section 8: Ceiling ----
    lines += [
        "SECTION 7: SCORE CEILING / COMPONENT UTILISATION",
        SEP2,
        "",
    ]
    if ceiling.get("sub_scores_available"):
        lines += [
            f"  {'Component':<20} {'Ceiling':>8} {'Max Obs':>9} {'Mean':>7} {'Util%':>7} {'@Ceil%':>8}",
            "  " + "-" * 62,
        ]
        for col, cv in ceiling.get("analysis", {}).items():
            uc_flag = " [UNCLAIMED]" if cv.get("chronically_unclaimed") else ""
            lines.append(
                f"  {cv['name']:<20} {cv['ceiling']:>8.1f} {cv['max_observed']:>9.2f}"
                f" {cv['mean']:>7.2f} {cv['utilisation_pct']:>6.1f}% {cv['at_ceiling_pct']:>7.1f}%"
                f"{uc_flag}"
            )
        lines.append("")
        uc = ceiling.get("chronically_unclaimed_components", [])
        if uc:
            uc_names = [ceiling["analysis"][c]["name"] for c in uc if c in ceiling.get("analysis", {})]
            lines.append(f"  ► Chronically unclaimed components: {', '.join(uc_names)}")
            lines.append("    These components never reach 90% of their ceiling — consider recalibrating range.")
        else:
            lines.append("  ► All components reach >= 90% of their ceiling. Ranges appear appropriate.")

        # Per-threshold breakdown
        lines.append("")
        for col, cv in ceiling.get("analysis", {}).items():
            thresh_str = "  ".join(
                f"{t}pts: {pv['pct']}%"
                for t, pv in cv.get("threshold_pcts", {}).items()
            )
            if thresh_str:
                lines.append(f"  {cv['name']:<20}  {thresh_str}")
    else:
        lines.append("  Sub-scores not in CSV.")
        for col, cv in ceiling.get("theoretical_analysis", {}).items():
            lines.append(f"  {cv['name']:<20}  Ceiling: {cv['ceiling']:.0f}  Max achievable: {cv['max_achievable']}")
    lines.append("")

    # ---- Summary ----
    lines += [
        SEP,
        "  EXECUTIVE SUMMARY",
        SEP2,
        "",
    ]
    best_roi = sweep.get("best_roi")
    best_sh  = sweep.get("best_sharpe")
    if best_roi:
        lines.append(
            f"  Optimal ROI threshold:   score >= {best_roi['threshold']}"
            f"  (ROI {best_roi['roi']:+.1f}%, {best_roi['n']} bets, {best_roi['win_rate']}% WR)"
        )
    else:
        lines.append("  Optimal ROI threshold:   insufficient data for valid recommendation")
    if best_sh:
        lines.append(
            f"  Optimal Sharpe threshold: score >= {best_sh['threshold']}"
            f"  (Sharpe {best_sh['sharpe']:.3f}, {best_sh['n']} bets)"
        )

    if corr.get("sub_scores_available") and corr.get("best_discriminator"):
        bc = corr["correlations"][corr["best_discriminator"]]
        lines.append(f"  Strongest sub-score:      {bc['name']} (Pearson r={bc['pearson']:+.4f})")
        sorted_c = sorted(
            corr["correlations"].items(),
            key=lambda kv: abs(kv[1].get("pearson") or 0),
        )
        if sorted_c:
            wname, wval = sorted_c[0]
            lines.append(f"  Weakest sub-score:        {wval['name']} (r={wval.get('pearson', 0):+.4f})")
    else:
        lines.append("  Sub-score signal:         Not computed (sub-scores not in CSV)")

    gz = interact.get("golden_zone")
    if gz:
        lines.append(
            f"  Best grade×class combo:   Grade A, {gz['combo']}"
            f"  (ROI {gz['roi']:+.1f}%, {gz['win_rate']}% WR, n={gz['n']})"
        )

    inv_count = sum(1 for r in calib if r["inversion"] and r["n"] >= 5)
    if inv_count:
        lines.append(
            f"  Calibration inversions:   {inv_count} band(s) — review score regions near these bands"
        )
    else:
        lines.append("  Calibration:              Monotonically ordered — no inversions detected")

    lines.append("")
    lines.append(SEP)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Score attribution and calibration analysis for NAP model backtest data"
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Path to backtest CSV (default: most recent data/backtest_*.csv)",
    )
    parser.add_argument(
        "--min-bets",
        type=int,
        default=30,
        dest="min_bets",
        help="Minimum bets required in threshold sweep for validity (default: 30)",
    )
    parser.add_argument(
        "--band-width",
        type=int,
        default=2,
        dest="band_width",
        help="Width of score bands in calibration table (default: 2)",
    )
    args = parser.parse_args()

    # Locate CSV
    csv_path = args.csv
    if not csv_path:
        csv_path = _find_latest_csv()
    if not csv_path or not os.path.exists(csv_path):
        print(
            "score_attribution_analysis: ERROR — no backtest CSV found.\n"
            "  Run historical_backtest.py first, or pass --csv <path>.",
            file=sys.stderr,
        )
        return 1

    print(f"score_attribution_analysis: loading {csv_path}")

    try:
        rows = _load_csv(csv_path)
    except (OSError, csv.Error) as exc:
        print(f"score_attribution_analysis: ERROR reading CSV — {exc}", file=sys.stderr)
        return 1

    if not rows:
        print("score_attribution_analysis: ERROR — CSV is empty.", file=sys.stderr)
        return 1

    total_rows = len(rows)
    rows_with_result = sum(1 for r in rows if r[COL_HAS_RESULT])
    print(f"  {total_rows} rows loaded, {rows_with_result} with result data")

    if rows_with_result < 10:
        print(
            "score_attribution_analysis: WARNING — fewer than 10 rows have result data. "
            "Analysis will be limited.",
            file=sys.stderr,
        )

    # Load results cache (for near-miss analysis enrichment)
    results_cache = _load_results_cache()
    print(f"  {len(results_cache)} days found in results cache")

    # Run analyses
    print("  Computing score-band calibration...")
    calib = calibration_table(rows, band_width=args.band_width)

    print("  Running grade analysis...")
    grade = grade_analysis(rows)

    print("  Running threshold sweep...")
    sweep = threshold_sweep(rows, min_bets=args.min_bets)

    print("  Computing sub-score correlations...")
    corr = subscore_correlation(rows)

    print("  Computing grade×type×class interactions...")
    interact = grade_racetype_class_interaction(rows)

    print("  Running near-miss analysis...")
    nearmiss = near_miss_analysis(rows, results_cache)

    print("  Computing ceiling utilisation...")
    ceiling = ceiling_analysis(rows)

    # Generate output paths
    date_str = date.today().isoformat()
    _ensure_dir(REPORTS_DIR)
    _ensure_dir(DATA_DIR)

    report_path_out = REPORTS_DIR / f"score_attribution_{date_str}.txt"
    json_path_out   = DATA_DIR / f"score_attribution_{date_str}.json"

    # Build text report
    report_text = build_report(
        csv_path     = csv_path,
        calib        = calib,
        grade        = grade,
        sweep        = sweep,
        corr         = corr,
        interact     = interact,
        nearmiss     = nearmiss,
        ceiling      = ceiling,
        date_str     = date_str,
        total_rows   = total_rows,
        rows_with_result = rows_with_result,
    )

    # Write text report
    try:
        with open(report_path_out, "w", encoding="utf-8") as fh:
            fh.write(report_text)
    except OSError as exc:
        print(f"score_attribution_analysis: ERROR writing report — {exc}", file=sys.stderr)
        return 1

    # Build JSON output
    json_out = {
        "generated_date":    date_str,
        "source_csv":        csv_path,
        "total_rows":        total_rows,
        "rows_with_result":  rows_with_result,
        "calibration_table": calib,
        "grade_analysis":    grade,
        "threshold_sweep":   sweep,
        "subscore_correlation": {
            "sub_scores_available": corr["sub_scores_available"],
            "best_discriminator":   corr["best_discriminator"],
            "correlations": {
                k: v for k, v in corr["correlations"].items()
            },
        },
        "grade_racetype_class": interact,
        "near_miss":         nearmiss,
        "ceiling_analysis":  ceiling,
        "summary": {
            "optimal_roi_threshold":    sweep.get("best_roi", {}).get("threshold") if sweep.get("best_roi") else None,
            "optimal_sharpe_threshold": sweep.get("best_sharpe", {}).get("threshold") if sweep.get("best_sharpe") else None,
            "best_discriminator_sub_score": corr.get("best_discriminator"),
            "golden_zone_combo":        interact.get("golden_zone", {}).get("combo") if interact.get("golden_zone") else None,
            "calibration_inversions":   [r["band"] for r in calib if r["inversion"] and r["n"] >= 5],
        },
    }

    try:
        with open(json_path_out, "w", encoding="utf-8") as fh:
            json.dump(json_out, fh, indent=2)
    except OSError as exc:
        print(f"score_attribution_analysis: WARNING — JSON write failed — {exc}", file=sys.stderr)
        # Non-fatal — text report already written

    # Print summary to console
    print("\n" + "=" * 72)
    print("  SCORE ATTRIBUTION ANALYSIS — SUMMARY")
    print("=" * 72)

    best_roi = sweep.get("best_roi")
    best_sh  = sweep.get("best_sharpe")
    if best_roi:
        print(
            f"  Optimal ROI threshold:    score >= {best_roi['threshold']}"
            f"  (ROI {best_roi['roi']:+.1f}%, {best_roi['n']} bets, {best_roi['win_rate']}% WR)"
        )
    else:
        print("  Optimal ROI threshold:    insufficient data (need >= 30 bets at any band)")

    if best_sh:
        print(
            f"  Optimal Sharpe threshold: score >= {best_sh['threshold']}"
            f"  (Sharpe {best_sh['sharpe']:.3f})"
        )

    if corr.get("sub_scores_available"):
        best_col = corr.get("best_discriminator")
        if best_col and best_col in corr["correlations"]:
            bc = corr["correlations"][best_col]
            print(f"  Strongest sub-score:      {bc['name']}  (r={bc['pearson']:+.4f})")
        sorted_c = sorted(
            corr["correlations"].items(),
            key=lambda kv: abs(kv[1].get("pearson") or 0),
        )
        if sorted_c:
            wname, wval = sorted_c[0]
            print(f"  Weakest sub-score:        {wval['name']}  (r={wval.get('pearson', 0):+.4f})")
    else:
        print("  Sub-scores:               Not available in CSV — theoretical analysis only")

    gz = interact.get("golden_zone")
    if gz:
        print(
            f"  Golden zone:              Grade A, {gz['combo']}"
            f"  (ROI {gz['roi']:+.1f}%, {gz['n']} bets)"
        )
    else:
        print("  Golden zone:              No qualifying combo found (need >= 5 bets)")

    inv_bands = [r["band"] for r in calib if r["inversion"] and r["n"] >= 5]
    if inv_bands:
        print(f"  Calibration inversions:   {', '.join(inv_bands)}")
    else:
        print("  Calibration:              No inversions — score ordering looks sound")

    print(f"\n  Report: {report_path_out}")
    print(f"  JSON:   {json_path_out}")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
