"""
standalone_filter.py — Gate-based NAP selection system, independent of the
100-point composite model.

Architecture: 6 hard gates — a horse must pass ALL to qualify. If it fails
any gate it is rejected regardless of other factors. This is fundamentally
different from the additive score model in nap_selector_v3.py.

Gate definitions (all must pass):
  G1  FORM GATE         — recent top-3 finish OR at least 1 win in last 3 runs
  G2  CONDITIONS GATE   — has performed at today's distance in past form
  G3  QUALITY GATE      — RPR top-2 in field OR score indicates class pedigree
  G4  TRAINER SIGNAL    — trainer_14_day_percent >= 20% OR won last time out
  G5  MARKET GATE       — morning price between 1.5 and 10.0 decimal
  G6  CONFIDENCE GATE   — composite model score >= 65 (sanity check agreement)

Usage:
    python standalone_filter.py                      # auto-find latest CSV
    python standalone_filter.py --csv path/to.csv
    python standalone_filter.py --generate-demo      # use synthetic data

Outputs:
    reports/standalone_filter_YYYY-MM-DD.txt
    data/standalone_filter_YYYY-MM-DD.json

Exit codes:
    0 — report produced
    1 — fatal error
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"

DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

TODAY = date.today().isoformat()

# ---------------------------------------------------------------------------
# Gate thresholds (standalone — not imported from nap_selector_v3)
# ---------------------------------------------------------------------------

GATE6_CONFIDENCE_THRESHOLD = 65.0   # default; also tested at 68, 70
SYSTEM_A_MIN_SCORE = 63.0           # matches NAP_MIN_SCORE in nap_selector_v3

# ---------------------------------------------------------------------------
# Safe converters
# ---------------------------------------------------------------------------

def _sf(v, d=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _si(v, d=-1) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return d


def _ss(v, d="") -> str:
    if v is None:
        return d
    return str(v).strip()


# ---------------------------------------------------------------------------
# Form string parser (replicated from nap_selector_v3 — NO import)
# ---------------------------------------------------------------------------

def _parse_form_chars(form: str) -> list:
    """Parse form string into list of recent result chars, most-recent first."""
    if not form or form.strip() in ("-", ""):
        return []
    form = form.strip().replace(" ", "")
    last_dash = form.rfind("-")
    segment = form[last_dash + 1:] if last_dash != -1 else form
    valid: list = []
    for ch in reversed(segment):
        upper = ch.upper()
        if upper.isdigit() or upper in ("F", "U", "P", "R", "B"):
            valid.append(upper)
    return valid


def _is_top3(ch: str) -> bool:
    try:
        return int(ch) <= 3
    except (ValueError, TypeError):
        return False


def _is_win(ch: str) -> bool:
    try:
        return int(ch) == 1
    except (ValueError, TypeError):
        return False


def _is_dnf(ch: str) -> bool:
    return ch.upper() in ("F", "U", "P")


# ---------------------------------------------------------------------------
# Gate implementations
# Each gate returns (passed: bool, reason: str)
# ---------------------------------------------------------------------------

def gate1_form(row: dict) -> tuple:
    """
    FORM GATE: last run was top-3 finish OR last 3 runs contain at least 1 win.
    FAIL if: no wins in last 5 chars OR last run was F/U/P.
    Falls back to form_score if raw form field is empty.
    """
    form = _ss(row.get("form"))
    chars = _parse_form_chars(form)

    if chars:
        last = chars[0]
        # Hard fail: last run DNF
        if _is_dnf(last):
            return False, f"G1-FAIL: last run was {last} (DNF-type)"

        # Pass: last run top-3
        if _is_top3(last):
            return True, f"G1-PASS: last run top-3 ({last})"

        # Pass: any win in last 3 runs
        last3 = chars[:3]
        if any(_is_win(c) for c in last3):
            return True, f"G1-PASS: win in last 3 runs (form: {''.join(chars[:5])})"

        # Fail: no wins in last 5 runs
        last5 = chars[:5]
        if not any(_is_win(c) for c in last5):
            return False, f"G1-FAIL: no wins in last 5 runs (form: {''.join(last5)})"

        return True, f"G1-PASS: form acceptable ({''.join(chars[:5])})"

    # No raw form — fall back to form_score sub-component
    form_score = _sf(row.get("form_score"))
    if form_score >= 14.0:
        return True, f"G1-PASS: form_score fallback ({form_score:.1f} >= 14)"
    if form_score < 8.0:
        return False, f"G1-FAIL: form_score fallback ({form_score:.1f} < 8, no form data)"
    return True, f"G1-PASS: form_score borderline ({form_score:.1f})"


def gate2_conditions(row: dict) -> tuple:
    """
    CONDITIONS GATE: has performed at today's distance in past form.
    Uses suitability sub-score as proxy when full_form not available.
    Pass: suit_score >= 6 (implies some distance/going match).
    Fail: suit_score == 0 AND distance_f > 14 (stayer with no form proof).
    """
    suit_score = _sf(row.get("suit_score"))
    dist_f = _sf(row.get("distance_f"))

    if suit_score >= 8.0:
        return True, f"G2-PASS: conditions suit (suit_score={suit_score:.1f})"
    if suit_score >= 6.0:
        return True, f"G2-PASS: conditions borderline suit (suit_score={suit_score:.1f})"
    if suit_score < 2.0 and dist_f > 14.0:
        return False, f"G2-FAIL: stayer with no distance evidence (suit={suit_score:.1f}, dist={dist_f:.1f}f)"
    if suit_score < 3.0:
        return False, f"G2-FAIL: no conditions evidence (suit_score={suit_score:.1f})"
    return True, f"G2-PASS: minimal conditions evidence (suit_score={suit_score:.1f})"


def gate3_quality(row: dict) -> tuple:
    """
    QUALITY GATE: RPR top-2 in field OR composite score indicates class.
    Proxy: score >= 70 (Grade A) strongly indicates RPR quality.
    form_score >= 12 (RPR rank score component) also signals quality.
    """
    score = _sf(row.get("score"))
    form_score = _sf(row.get("form_score"))
    grade = _ss(row.get("grade"))

    # Grade A is definitionally quality
    if grade == "A" or score >= 70.0:
        return True, f"G3-PASS: Grade A quality (score={score:.1f})"

    # High form_score implies RPR rank score contribution
    if form_score >= 12.0:
        return True, f"G3-PASS: strong RPR-linked form_score ({form_score:.1f})"

    # Grade B+ is borderline — accept
    if grade == "B+" or score >= 60.0:
        return True, f"G3-PASS: Grade B+ (score={score:.1f})"

    # Explicit bottom-quality rejection
    if score < 55.0 and form_score < 8.0:
        return False, f"G3-FAIL: low quality (score={score:.1f}, form_score={form_score:.1f})"

    return True, f"G3-PASS: acceptable quality (score={score:.1f})"


def gate4_trainer(row: dict) -> tuple:
    """
    TRAINER SIGNAL GATE.
    Pass: train_score >= 5 (implies ~20%+ trainer pct in model scoring).
    Fail: train_score < 2 AND form doesn't show recent win.
    Falls back to train_score proxy.
    """
    train_score = _sf(row.get("train_score"))
    form = _ss(row.get("form"))
    chars = _parse_form_chars(form)

    # Won last time out overrides cold trainer
    if chars and _is_win(chars[0]):
        return True, f"G4-PASS: won last time out (form={form[:6] if form else '?'})"

    # train_score >= 5 => trainer_pct roughly >= 20% (from compute_trainer_score)
    if train_score >= 5.0:
        return True, f"G4-PASS: in-form trainer (train_score={train_score:.1f})"
    if train_score >= 2.0:
        return True, f"G4-PASS: trainer ticking over (train_score={train_score:.1f})"

    # Cold trainer + no recent win = fail
    if train_score < 2.0:
        # Check if won in last 2 runs
        last2 = chars[:2] if chars else []
        if any(_is_win(c) for c in last2):
            return True, f"G4-PASS: recent win overrides cold trainer"
        return False, f"G4-FAIL: cold trainer signal (train_score={train_score:.1f})"

    return True, f"G4-PASS: trainer neutral (train_score={train_score:.1f})"


def gate5_market(row: dict) -> tuple:
    """
    MARKET GATE: morning price between 1.5 and 10.0 decimal.
    Removes longshots (>10) AND very short prices with no value.
    Uses sp_dec as proxy if morning price not available.
    Also inferred from mkt_score: very negative mkt_score implies longshot.
    """
    sp_dec = _sf(row.get("sp_dec"))
    mkt_score = _sf(row.get("mkt_score"))

    # mkt_score < -6 means outsider (>20 decimal in compute_market_score)
    if mkt_score <= -6.0:
        return False, f"G5-FAIL: outsider (mkt_score={mkt_score:.1f} implies very long price)"

    # mkt_score < -2 means bigger price territory (>12 decimal)
    if mkt_score < -2.0:
        return False, f"G5-FAIL: too big a price (mkt_score={mkt_score:.1f})"

    # sp_dec available — use directly
    if sp_dec > 0.0:
        if sp_dec > 10.0:
            return False, f"G5-FAIL: sp_dec too high ({sp_dec:.1f} > 10.0)"
        if sp_dec < 1.5:
            return False, f"G5-FAIL: sp_dec too short ({sp_dec:.1f} < 1.5, no value)"
        return True, f"G5-PASS: price in range ({sp_dec:.1f})"

    # mkt_score-only inference
    if mkt_score >= 1.0:
        return True, f"G5-PASS: market score indicates acceptable price ({mkt_score:.1f})"
    if mkt_score >= -1.0:
        return True, f"G5-PASS: market neutral ({mkt_score:.1f})"

    return True, f"G5-PASS: market acceptable (score={mkt_score:.1f})"


def gate6_confidence(row: dict, threshold: float = GATE6_CONFIDENCE_THRESHOLD) -> tuple:
    """
    CONFIDENCE GATE: composite model score >= threshold (default 65).
    Both systems must agree — the gate model uses the composite as a sanity check.
    """
    score = _sf(row.get("score"))
    if score >= threshold:
        return True, f"G6-PASS: composite score {score:.1f} >= {threshold:.0f}"
    return False, f"G6-FAIL: composite score {score:.1f} < {threshold:.0f}"


# ---------------------------------------------------------------------------
# Apply all 6 gates to a record
# ---------------------------------------------------------------------------

def apply_gates(row: dict, g6_threshold: float = GATE6_CONFIDENCE_THRESHOLD) -> dict:
    """
    Apply all 6 gates.  Returns dict with:
      passed_all: bool
      gate_results: list of (gate_num, passed, reason)
      first_fail: gate number or None
    """
    gate_fns = [
        (1, lambda r: gate1_form(r)),
        (2, lambda r: gate2_conditions(r)),
        (3, lambda r: gate3_quality(r)),
        (4, lambda r: gate4_trainer(r)),
        (5, lambda r: gate5_market(r)),
        (6, lambda r: gate6_confidence(r, g6_threshold)),
    ]

    gate_results = []
    first_fail = None
    for gnum, fn in gate_fns:
        passed, reason = fn(row)
        gate_results.append((gnum, passed, reason))
        if not passed and first_fail is None:
            first_fail = gnum

    return {
        "passed_all": first_fail is None,
        "gate_results": gate_results,
        "first_fail": first_fail,
    }


# ---------------------------------------------------------------------------
# CSV loader
# ---------------------------------------------------------------------------

def load_backtest_csv(csv_path: Path) -> list:
    """Load backtest CSV, return list of row dicts."""
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            # Normalise boolean fields
            for bool_col in ("has_result", "is_win", "is_place"):
                val = row.get(bool_col, "")
                row[bool_col] = str(val).lower() in ("true", "1", "yes")
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Synthetic data generator (when no real CSV is available)
# Calibrated to match known stats from score_attribution JSON.
# ---------------------------------------------------------------------------

def generate_synthetic_data(seed: int = 42) -> list:
    """
    Generate 180 representative records across 6 months (roughly 1 per day).
    Calibrated to match the known backtest stats:
    - Grade A: 30% WR, +94% ROI
    - Grade B+: 8.3% WR, -62% ROI
    - Grade B: 22.2% WR, +9% ROI
    - Threshold 63: ~27% WR, ~70% ROI
    - Known winning race types: Hurdle A-grade dominant
    """
    rng = random.Random(seed)

    race_types = ["Flat", "Flat", "Flat", "Hurdle", "Hurdle", "Chase", "Chase", "Bumper/NHF"]
    race_classes_by_type = {
        "Flat": ["Class 3", "Class 4", "Class 5", "Class 5", "Class 6-7"],
        "Hurdle": ["Class 3", "Class 4", "Class 5", "Class 5", "Grade 3"],
        "Chase": ["Class 1-2", "Class 3", "Class 4", "Class 5", "Grade 3"],
        "Bumper/NHF": ["Class 4", "Class 5", "Class 5"],
    }
    courses = [
        "Ascot", "Cheltenham", "Newmarket", "Haydock", "Sandown",
        "Goodwood", "Kempton", "Lingfield", "Wolverhampton", "Uttoxeter",
        "Newbury", "York", "Doncaster", "Chester", "Leicester",
    ]
    goings = ["Good", "Good to Soft", "Soft", "Heavy", "Standard", "Good to Firm"]
    going_groups = {
        "Good": "Good", "Good to Soft": "Soft/Good-Soft", "Soft": "Soft/Good-Soft",
        "Heavy": "Heavy", "Standard": "All-Weather", "Good to Firm": "Firm/Good-Firm",
    }

    # Build score distribution matching the threshold sweep data
    # 60 records total in original, we scale to 180
    # Grade A: 30/60 records, Grade B+: 12/60, Grade B: 18/60
    # We'll use ratios: A=50%, B+=20%, B=30%
    grade_configs = [
        # (grade, weight, score_range, win_prob, sp_range)
        ("A", 50, (70.0, 90.0), 0.30, (2.5, 8.0)),
        ("B+", 20, (60.0, 70.0), 0.083, (2.0, 12.0)),
        ("B", 30, (50.0, 60.0), 0.222, (2.0, 10.0)),
    ]

    # Sub-score calibration from known averages
    # form_score: avg_win=20.11, avg_loss=18.95
    # suit_score: avg_win=10.24, avg_loss=8.68
    # ctx_score: avg_win=4.91, avg_loss=5.46
    # train_score: avg_win=7.29, avg_loss=5.10
    # mkt_score: avg_win=0.14, avg_loss=0.70

    # Form strings representing different scenarios
    form_strings = {
        "winner": ["1214", "1113", "2112", "11213", "1123", "211", "12134"],
        "placed": ["2341", "3212", "2231", "3221", "23143"],
        "poor":   ["5674", "4556", "67843", "0546", "7654"],
        "dnf":    ["P214", "F312", "U543", "P112", "F234"],
    }

    months = [
        "2025-12", "2025-11", "2025-10", "2025-09",
        "2025-08", "2025-07", "2025-06", "2025-05",
        "2025-04", "2025-03", "2025-02", "2026-01",
    ]

    records = []
    record_idx = 0

    # Distribute across 6 months (180 days approx)
    for month_idx, month in enumerate(months[:6]):
        n_days = 30
        for day in range(1, n_days + 1):
            date_str = f"{month}-{day:02d}"
            # Validate date
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                continue

            # Decide grade for this record
            roll = rng.random() * 100
            if roll < 50:
                grade, score_range, win_prob, sp_range = "A", (70.0, 90.0), 0.30, (2.5, 8.0)
            elif roll < 70:
                grade, score_range, win_prob, sp_range = "B+", (60.0, 70.0), 0.083, (2.0, 12.0)
            else:
                grade, score_range, win_prob, sp_range = "B", (50.0, 60.0), 0.222, (2.0, 10.0)

            # Score
            composite = round(rng.uniform(*score_range), 1)

            # Race type
            rt = rng.choice(race_types)
            rc = rng.choice(race_classes_by_type[rt])
            course = rng.choice(courses)
            going_raw = rng.choice(goings)
            dist_f = round(rng.uniform(5.0, 16.0), 1)

            # Win probability (slightly boosted for higher scores)
            score_boost = max(0, (composite - 63) / 100)
            effective_win_prob = min(0.45, win_prob + score_boost)
            is_win = rng.random() < effective_win_prob

            # SP
            if is_win:
                sp_dec = round(rng.uniform(sp_range[0], min(sp_range[1], 8.0)), 2)
            else:
                sp_dec = round(rng.uniform(sp_range[0], sp_range[1] * 1.2), 2)

            is_place = is_win or rng.random() < 0.25

            # Sub-scores (calibrated to known averages)
            if is_win:
                form_score = round(min(40, rng.gauss(20.11, 6)), 2)
                suit_score = round(min(25, max(0, rng.gauss(10.24, 4))), 2)
                ctx_score = round(min(15, max(0, rng.gauss(4.91, 3))), 2)
                train_score = round(min(15, max(0, rng.gauss(7.29, 3))), 2)
                mkt_score = round(min(5, max(-10, rng.gauss(0.14, 1.5))), 2)
            else:
                form_score = round(min(40, rng.gauss(18.95, 6)), 2)
                suit_score = round(min(25, max(0, rng.gauss(8.68, 4))), 2)
                ctx_score = round(min(15, max(0, rng.gauss(5.46, 3))), 2)
                train_score = round(min(15, max(0, rng.gauss(5.10, 3))), 2)
                mkt_score = round(min(5, max(-10, rng.gauss(0.70, 1.5))), 2)

            # Ensure composite is plausible given sub-scores
            implied = form_score + suit_score + ctx_score + train_score + mkt_score
            composite = round(min(100, max(0, implied * (composite / max(1, implied)))), 1)

            # Form string
            if is_win and rng.random() < 0.7:
                form_str = rng.choice(form_strings["winner"])
            elif is_place and not is_win:
                form_str = rng.choice(form_strings["placed"])
            elif rng.random() < 0.15:
                form_str = rng.choice(form_strings["dnf"])
            else:
                form_str = rng.choice(form_strings["poor"])

            # Position
            if is_win:
                position = "1"
            elif is_place:
                position = str(rng.randint(2, 3))
            else:
                position = str(rng.randint(4, 12))

            # Score band
            if composite >= 80:
                score_band = "80+"
            elif composite >= 70:
                score_band = "70-79"
            elif composite >= 60:
                score_band = "60-69"
            elif composite >= 50:
                score_band = "50-59"
            else:
                score_band = "<50"

            # Type/class/going/dist groups
            rt_lower = rt.lower()
            if "chase" in rt_lower:
                type_group = "Chase"
            elif "hurdle" in rt_lower:
                type_group = "Hurdle"
            elif "bumper" in rt_lower or "nhf" in rt_lower:
                type_group = "Bumper/NHF"
            else:
                type_group = "Flat"

            records.append({
                "date": date_str,
                "race_type": rt,
                "race_class": rc,
                "distance_f": str(dist_f),
                "going": going_raw,
                "course": course,
                "horse": f"Horse_{record_idx:04d}",
                "horse_id": f"h{record_idx:04d}",
                "score": str(composite),
                "grade": grade,
                "form_score": str(form_score),
                "suit_score": str(suit_score),
                "ctx_score": str(ctx_score),
                "train_score": str(train_score),
                "mkt_score": str(mkt_score),
                "position": position,
                "sp_dec": str(sp_dec),
                "has_result": "True",
                "is_win": str(is_win),
                "is_place": str(is_place),
                "type_group": type_group,
                "class_group": rc,
                "score_band": score_band,
                "going_group": going_groups.get(going_raw, "Unknown"),
                "dist_group": (
                    "Sprint (<7f)" if dist_f < 7 else
                    "Mile (7-10.5f)" if dist_f < 10.5 else
                    "Middle (10.5-14f)" if dist_f < 14 else
                    "Staying (14f+)"
                ),
                # Extra field for form string (not in standard CSV but used by gates)
                "form": form_str,
            })
            record_idx += 1

    return records


# ---------------------------------------------------------------------------
# Normalise loaded rows (ensure bool fields and numeric conversions)
# ---------------------------------------------------------------------------

def normalise_rows(rows: list) -> list:
    for r in rows:
        for bool_col in ("has_result", "is_win", "is_place"):
            val = r.get(bool_col, "")
            r[bool_col] = str(val).lower() in ("true", "1", "yes")
        # Ensure form field exists (may not be in CSV)
        if "form" not in r:
            r["form"] = ""
    return rows


# ---------------------------------------------------------------------------
# SYSTEM A: Current model (top scorer per race, score >= threshold)
# ---------------------------------------------------------------------------

def run_system_a(daily_records: dict, threshold: float = SYSTEM_A_MIN_SCORE) -> dict:
    """
    System A — current model.
    For each day: picks the record with highest composite score that exceeds threshold.
    Returns dict keyed by date with selection or None.
    """
    selections = {}
    for date_str, records in daily_records.items():
        qualifying = [r for r in records if _sf(r.get("score")) >= threshold]
        if qualifying:
            best = max(qualifying, key=lambda r: _sf(r.get("score")))
            selections[date_str] = best
        else:
            selections[date_str] = None
    return selections


# ---------------------------------------------------------------------------
# SYSTEM B: Standalone filter (gate-based)
# ---------------------------------------------------------------------------

def run_system_b(
    daily_records: dict, g6_threshold: float = GATE6_CONFIDENCE_THRESHOLD
) -> dict:
    """
    System B — gate-based standalone filter.
    For each day: find all horses passing all 6 gates across all races.
    Selection rule: pick the one with most recent win (form chars[0] == '1')
    then by composite score.
    Returns dict keyed by date with selection dict or None.
    """
    selections = {}
    gate_log = {}  # date -> list of horse gate analyses

    for date_str, records in daily_records.items():
        day_log = []
        passed_horses = []

        for row in records:
            gate_result = apply_gates(row, g6_threshold)
            day_log.append({
                "horse": row.get("horse", "?"),
                "score": _sf(row.get("score")),
                "gate_result": gate_result,
            })

            if gate_result["passed_all"]:
                passed_horses.append(row)

        gate_log[date_str] = day_log

        if not passed_horses:
            selections[date_str] = None
        elif len(passed_horses) == 1:
            selections[date_str] = passed_horses[0]
        else:
            # Multiple qualifiers — pick best: recent win first, then by score
            def _sort_key(r):
                chars = _parse_form_chars(_ss(r.get("form", "")))
                recent_win = 1 if (chars and _is_win(chars[0])) else 0
                return (recent_win, _sf(r.get("score")))
            selections[date_str] = max(passed_horses, key=_sort_key)

    return selections, gate_log


# ---------------------------------------------------------------------------
# SYSTEM C: Combined — only bet if A and B agree on same horse
# ---------------------------------------------------------------------------

def run_system_c(sys_a: dict, sys_b_sel: dict) -> dict:
    """
    System C — combined.
    Only bets if System A and System B select the same horse on the same day.
    'Same horse' = same horse_id OR same horse name (for synthetic data).
    """
    selections = {}
    for date_str in sys_a:
        a_sel = sys_a.get(date_str)
        b_sel = sys_b_sel.get(date_str)
        if a_sel is None or b_sel is None:
            selections[date_str] = None
            continue
        # Check agreement: same horse_id or same horse name
        a_id = _ss(a_sel.get("horse_id")) or _ss(a_sel.get("horse"))
        b_id = _ss(b_sel.get("horse_id")) or _ss(b_sel.get("horse"))
        if a_id and b_id and a_id == b_id:
            selections[date_str] = a_sel
        else:
            selections[date_str] = None
    return selections


# ---------------------------------------------------------------------------
# Performance stats
# ---------------------------------------------------------------------------

def calc_stats(selections: dict) -> dict:
    """Calculate performance statistics from a selections dict."""
    total = 0
    bets = 0
    wins = 0
    pl = 0.0
    monthly: dict = defaultdict(lambda: {"bets": 0, "wins": 0, "pl": 0.0})

    for date_str, sel in selections.items():
        total += 1
        if sel is None:
            continue

        has_result = sel.get("has_result", True)
        if not has_result:
            continue

        bets += 1
        is_win = sel.get("is_win", False)
        sp = _sf(sel.get("sp_dec", 0.0))

        month = date_str[:7]
        monthly[month]["bets"] += 1

        if is_win:
            wins += 1
            profit = max(0.0, sp - 1.0)
            pl += profit
            monthly[month]["wins"] += 1
            monthly[month]["pl"] += profit
        else:
            pl -= 1.0
            monthly[month]["pl"] -= 1.0

    win_rate = wins / bets * 100 if bets else 0.0
    roi = pl / bets * 100 if bets else 0.0
    sel_rate = bets / total * 100 if total else 0.0
    months_sorted = sorted(monthly.keys())
    months_by_roi = sorted(monthly.items(), key=lambda kv: kv[1]["pl"] / max(1, kv[1]["bets"]))

    return {
        "total_days": total,
        "selections": bets,
        "wins": wins,
        "win_rate": round(win_rate, 1),
        "roi": round(roi, 1),
        "pl": round(pl, 2),
        "selection_rate": round(sel_rate, 1),
        "monthly": dict(monthly),
        "best_month": months_by_roi[-1][0] if months_by_roi else None,
        "worst_month": months_by_roi[0][0] if months_by_roi else None,
        "best_month_roi": round(
            months_by_roi[-1][1]["pl"] / max(1, months_by_roi[-1][1]["bets"]) * 100, 1
        ) if months_by_roi else 0.0,
        "worst_month_roi": round(
            months_by_roi[0][1]["pl"] / max(1, months_by_roi[0][1]["bets"]) * 100, 1
        ) if months_by_roi else 0.0,
    }


# ---------------------------------------------------------------------------
# Disagreement analysis
# ---------------------------------------------------------------------------

def disagreement_analysis(sys_a: dict, sys_b_sel: dict) -> dict:
    """
    On days where A and B disagreed: who was right more often?
    """
    a_right = 0
    b_right = 0
    both_wrong = 0
    disagree_days = 0

    for date_str in sys_a:
        a_sel = sys_a.get(date_str)
        b_sel = sys_b_sel.get(date_str)

        # Count as disagreement if both selected but different horses,
        # OR one selected and the other didn't
        a_id = _ss(a_sel.get("horse_id", "")) if a_sel else None
        b_id = _ss(b_sel.get("horse_id", "")) if b_sel else None

        if a_id == b_id:
            continue  # agreement (including both None)

        disagree_days += 1

        a_won = a_sel.get("is_win", False) if a_sel else False
        b_won = b_sel.get("is_win", False) if b_sel else False

        if a_won and not b_won:
            a_right += 1
        elif b_won and not a_won:
            b_right += 1
        elif not a_won and not b_won:
            both_wrong += 1
        # both won would be counted in agreement

    return {
        "disagree_days": disagree_days,
        "a_right": a_right,
        "b_right": b_right,
        "both_wrong": both_wrong,
        "a_accuracy": round(a_right / disagree_days * 100, 1) if disagree_days else 0.0,
        "b_accuracy": round(b_right / disagree_days * 100, 1) if disagree_days else 0.0,
    }


# ---------------------------------------------------------------------------
# Gate effectiveness analysis (Task 3)
# ---------------------------------------------------------------------------

def gate_effectiveness(rows: list) -> list:
    """
    For each gate (1-6):
    - How many horses did it reject?
    - Of rejected: what % would have won?
    - Of passed: what's the win rate?
    - Net contribution
    """
    gate_data = {i: {"rejected": 0, "rejected_wins": 0, "passed": 0, "passed_wins": 0}
                 for i in range(1, 7)}

    for row in rows:
        for gnum in range(1, 7):
            # Apply gates 1 through gnum-1 first, then check gate gnum in isolation
            passed, _ = [
                gate1_form,
                gate2_conditions,
                gate3_quality,
                gate4_trainer,
                gate5_market,
                lambda r: gate6_confidence(r, GATE6_CONFIDENCE_THRESHOLD),
            ][gnum - 1](row)

            is_win = row.get("is_win", False)
            if passed:
                gate_data[gnum]["passed"] += 1
                if is_win:
                    gate_data[gnum]["passed_wins"] += 1
            else:
                gate_data[gnum]["rejected"] += 1
                if is_win:
                    gate_data[gnum]["rejected_wins"] += 1

    results = []
    for gnum in range(1, 7):
        gd = gate_data[gnum]
        rejected = gd["rejected"]
        passed = gd["passed"]
        rej_wins = gd["rejected_wins"]
        pass_wins = gd["passed_wins"]

        pass_wr = pass_wins / passed * 100 if passed else 0.0
        rej_cost = rej_wins / rejected * 100 if rejected else 0.0

        # Net contribution: positive if passing improves win rate vs baseline
        total = rejected + passed
        baseline_wr = (rej_wins + pass_wins) / total * 100 if total else 0.0
        net = pass_wr - baseline_wr

        results.append({
            "gate": gnum,
            "total": total,
            "rejected": rejected,
            "rejected_wins": rej_wins,
            "rejected_win_pct": round(rej_cost, 1),
            "passed": passed,
            "passed_wins": pass_wins,
            "passed_win_pct": round(pass_wr, 1),
            "baseline_wr": round(baseline_wr, 1),
            "net_contribution": round(net, 1),
            "verdict": "HELPING" if net > 2 else ("HURTING" if net < -2 else "NEUTRAL"),
        })
    return results


# ---------------------------------------------------------------------------
# Optimal gate combination (Task 4)
# ---------------------------------------------------------------------------

def optimal_gate_combinations(daily_records: dict) -> dict:
    """
    Test removing each gate one at a time.
    Also test Gate 6 thresholds: 65, 68, 70.
    Returns dict with analysis.
    """
    gate_names = {
        1: "Form Gate",
        2: "Conditions Gate",
        3: "Quality Gate",
        4: "Trainer Signal",
        5: "Market Gate",
        6: "Confidence Gate",
    }

    gate_fns_all = [
        gate1_form,
        gate2_conditions,
        gate3_quality,
        gate4_trainer,
        gate5_market,
        lambda r: gate6_confidence(r, GATE6_CONFIDENCE_THRESHOLD),
    ]

    def _run_gates(records_daily, active_gates, g6_thresh=GATE6_CONFIDENCE_THRESHOLD):
        """Run a subset of gates and return stats."""
        gate_fn_map = {
            1: gate1_form,
            2: gate2_conditions,
            3: gate3_quality,
            4: gate4_trainer,
            5: gate5_market,
            6: lambda r: gate6_confidence(r, g6_thresh),
        }

        sels = {}
        for date_str, recs in records_daily.items():
            passed = []
            for row in recs:
                all_passed = True
                for g in active_gates:
                    p, _ = gate_fn_map[g](row)
                    if not p:
                        all_passed = False
                        break
                if all_passed:
                    passed.append(row)

            if not passed:
                sels[date_str] = None
            else:
                sels[date_str] = max(passed, key=lambda r: _sf(r.get("score")))

        return calc_stats(sels)

    results = {}

    # Test all 6 gates (baseline)
    results["all_6_gates"] = _run_gates(daily_records, list(range(1, 7)))

    # Remove each gate one at a time
    for skip_gate in range(1, 7):
        active = [g for g in range(1, 7) if g != skip_gate]
        key = f"without_gate_{skip_gate}_{gate_names[skip_gate].replace(' ', '_')}"
        results[key] = _run_gates(daily_records, active)

    # Test Gate 6 thresholds
    for g6_t in (65.0, 68.0, 70.0):
        active_all = list(range(1, 7))
        key = f"gate6_threshold_{int(g6_t)}"
        results[key] = _run_gates(daily_records, active_all, g6_thresh=g6_t)

    return results


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def _fmt_row(label, n, wins, win_pct, roi, sel_rate="", extra=""):
    parts = [
        f"  {label:<32}",
        f"  {n:>6}",
        f"  {wins:>5}",
        f"  {win_pct:>6.1f}%",
        f"  {roi:>+8.1f}%",
    ]
    if sel_rate:
        parts.append(f"  {sel_rate:>8}")
    if extra:
        parts.append(f"  {extra}")
    return "".join(parts)


def build_report(
    data_source: str,
    sys_a_stats: dict,
    sys_b_stats: dict,
    sys_c_stats: dict,
    disagree: dict,
    gate_eff: list,
    optimal: dict,
    gate_log_sample: dict,
    g6_threshold: float,
) -> str:
    sep = "=" * 74
    thin = "-" * 74
    lines = []

    lines += [
        sep,
        "  STANDALONE FILTER vs CURRENT MODEL — HEAD-TO-HEAD COMPARISON",
        f"  Generated:   {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"  Data source: {data_source}",
        f"  Gate 6 confidence threshold: {g6_threshold:.0f}",
        sep,
        "",
        "  DESIGN PHILOSOPHY:",
        "  System A = Current 100-pt additive composite model (score >= 63)",
        "  System B = Standalone gate filter (6 hard gates, all must pass)",
        "  System C = Combined: only bet when A and B agree on same horse",
        "",
    ]

    # Summary comparison table
    lines += [
        "SECTION 1: HEAD-TO-HEAD COMPARISON",
        thin,
        f"  {'System':<32}  {'Bets':>6}  {'Wins':>5}  {'Win%':>6}  {'ROI':>9}  {'Sel/mo':>8}",
        f"  {thin[2:]}",
    ]

    for label, stats in [
        ("System A — Current Model (>=63)", sys_a_stats),
        ("System B — Standalone Gate Filter", sys_b_stats),
        ("System C — Combined (A+B agree)", sys_c_stats),
    ]:
        n = stats["selections"]
        wins = stats["wins"]
        wr = stats["win_rate"]
        roi = stats["roi"]
        sel_mo = round(n / max(1, stats["total_days"]) * 30, 1)
        lines.append(
            f"  {label:<32}  {n:>6}  {wins:>5}  {wr:>6.1f}%  {roi:>+9.1f}%  {sel_mo:>7.1f}"
        )

    lines += [
        "",
        f"  {'System':<32}  {'Best Mo ROI':>11}  {'Worst Mo ROI':>12}  {'Best Month':>12}  {'Worst Month':>12}",
        f"  {thin[2:]}",
    ]
    for label, stats in [
        ("System A — Current Model (>=63)", sys_a_stats),
        ("System B — Standalone Gate Filter", sys_b_stats),
        ("System C — Combined (A+B agree)", sys_c_stats),
    ]:
        bm = stats.get("best_month") or "—"
        wm = stats.get("worst_month") or "—"
        bm_roi = stats.get("best_month_roi", 0.0)
        wm_roi = stats.get("worst_month_roi", 0.0)
        lines.append(
            f"  {label:<32}  {bm_roi:>+11.1f}%  {wm_roi:>+12.1f}%  {bm:>12}  {wm:>12}"
        )

    lines += ["", ""]

    # Disagreement analysis
    lines += [
        "SECTION 2: DISAGREEMENT ANALYSIS",
        thin,
        f"  Days A and B disagreed:       {disagree['disagree_days']}",
        f"  Days A was right (B wrong):   {disagree['a_right']}  "
        f"({disagree['a_accuracy']:.1f}% of disagreements)",
        f"  Days B was right (A wrong):   {disagree['b_right']}  "
        f"({disagree['b_accuracy']:.1f}% of disagreements)",
        f"  Both wrong:                   {disagree['both_wrong']}",
        "",
    ]

    # Gate effectiveness
    gate_names = {
        1: "Form Gate",
        2: "Conditions Gate",
        3: "Quality Gate",
        4: "Trainer Signal Gate",
        5: "Market Gate",
        6: f"Confidence Gate (>={g6_threshold:.0f})",
    }
    lines += [
        "SECTION 3: GATE EFFECTIVENESS ANALYSIS",
        thin,
        f"  {'Gate':<30}  {'Rejected':>8}  {'Rej.Win%':>9}  {'Passed':>7}  "
        f"{'Pass.Win%':>9}  {'Net':>7}  {'Verdict':>10}",
        f"  {thin[2:]}",
    ]
    for gd in gate_eff:
        gname = gate_names.get(gd["gate"], f"Gate {gd['gate']}")
        lines.append(
            f"  {gname:<30}  {gd['rejected']:>8}  {gd['rejected_win_pct']:>8.1f}%"
            f"  {gd['passed']:>7}  {gd['passed_win_pct']:>8.1f}%"
            f"  {gd['net_contribution']:>+6.1f}%  {gd['verdict']:>10}"
        )

    lines += [
        "",
        "  Net contribution = pass_win_rate - baseline_win_rate",
        "  HELPING: gate improves win rate by >2pp | HURTING: reduces by >2pp",
        "",
    ]

    # Optimal gate combination
    lines += [
        "SECTION 4: OPTIMAL GATE COMBINATION",
        thin,
        f"  {'Config':<40}  {'Bets':>6}  {'Wins':>5}  {'Win%':>6}  {'ROI':>9}",
        f"  {thin[2:]}",
    ]
    for config_key, stats in optimal.items():
        n = stats["selections"]
        wins = stats["wins"]
        wr = stats["win_rate"]
        roi = stats["roi"]
        label = config_key.replace("_", " ").replace("without gate", "No Gate").title()
        label = label[:40]
        lines.append(f"  {label:<40}  {n:>6}  {wins:>5}  {wr:>6.1f}%  {roi:>+9.1f}%")

    lines += ["", ""]

    # Gate 6 threshold sweep
    lines += [
        "  Gate 6 Confidence Threshold Sweep:",
        f"  {'Threshold':<40}  {'Bets':>6}  {'Wins':>5}  {'Win%':>6}  {'ROI':>9}",
        f"  {thin[2:]}",
    ]
    for k in ("gate6_threshold_65", "gate6_threshold_68", "gate6_threshold_70"):
        if k not in optimal:
            continue
        stats = optimal[k]
        thresh = k.split("_")[-1]
        label = f"Gate 6 threshold >= {thresh}"
        lines.append(
            f"  {label:<40}  {stats['selections']:>6}  {stats['wins']:>5}"
            f"  {stats['win_rate']:>6.1f}%  {stats['roi']:>+9.1f}%"
        )

    lines += ["", ""]

    # Recommendation
    lines += [
        "SECTION 5: RECOMMENDATION",
        thin,
    ]
    # Auto-recommendation logic
    roi_a = sys_a_stats["roi"]
    roi_b = sys_b_stats["roi"]
    roi_c = sys_c_stats["roi"]
    wins_c = sys_c_stats["wins"]
    wins_b = sys_b_stats["wins"]
    wins_a = sys_a_stats["wins"]

    best_roi = max(roi_a, roi_b, roi_c)
    if roi_c == best_roi and wins_c >= 3:
        rec = "SYSTEM C (Combined)"
        reason = (
            f"Combined system delivers best ROI ({roi_c:+.1f}%) with "
            f"{wins_c} wins. Both models agreeing is a strong confirmation filter."
        )
    elif roi_b > roi_a and wins_b >= 3:
        rec = "SYSTEM B (Standalone Gate Filter)"
        reason = (
            f"Gate filter outperforms current model (ROI: {roi_b:+.1f}% vs {roi_a:+.1f}%). "
            f"Gate logic is more interpretable and avoids score noise."
        )
    else:
        rec = "SYSTEM A (Current Model) with threshold raised to 70+"
        reason = (
            f"Current model ROI ({roi_a:+.1f}%) leads or is comparable. "
            f"Raising threshold to 70+ (Grade A only) improves precision further."
        )

    lines += [
        f"  Recommended system: {rec}",
        f"  Rationale: {reason}",
        "",
        "  Additional notes:",
    ]

    # Auto-insights from gate effectiveness
    helping_gates = [gd for gd in gate_eff if gd["verdict"] == "HELPING"]
    hurting_gates = [gd for gd in gate_eff if gd["verdict"] == "HURTING"]

    if helping_gates:
        gnames = ", ".join(gate_names.get(g["gate"], f"Gate {g['gate']}") for g in helping_gates)
        lines.append(f"  - Most valuable gates: {gnames}")
    if hurting_gates:
        gnames = ", ".join(gate_names.get(g["gate"], f"Gate {g['gate']}") for g in hurting_gates)
        lines.append(f"  - Consider loosening or removing: {gnames}")

    lines += ["", sep]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Build JSON output
# ---------------------------------------------------------------------------

def build_json_output(
    data_source: str,
    sys_a_stats: dict,
    sys_b_stats: dict,
    sys_c_stats: dict,
    disagree: dict,
    gate_eff: list,
    optimal: dict,
    g6_threshold: float,
    is_synthetic: bool,
) -> dict:
    return {
        "generated": TODAY,
        "data_source": str(data_source),
        "is_synthetic_data": is_synthetic,
        "gate6_confidence_threshold": g6_threshold,
        "system_a": sys_a_stats,
        "system_b": sys_b_stats,
        "system_c": sys_c_stats,
        "disagreement_analysis": disagree,
        "gate_effectiveness": gate_eff,
        "optimal_gate_combinations": optimal,
        "recommendation": {
            "systems": {
                "A": {"roi": sys_a_stats["roi"], "win_rate": sys_a_stats["win_rate"],
                      "selections": sys_a_stats["selections"]},
                "B": {"roi": sys_b_stats["roi"], "win_rate": sys_b_stats["win_rate"],
                      "selections": sys_b_stats["selections"]},
                "C": {"roi": sys_c_stats["roi"], "win_rate": sys_c_stats["win_rate"],
                      "selections": sys_c_stats["selections"]},
            }
        },
    }


# ---------------------------------------------------------------------------
# Find latest backtest CSV
# ---------------------------------------------------------------------------

def find_latest_csv() -> Optional[Path]:
    """Search for the most recent backtest CSV in the data directory."""
    candidates = sorted(DATA_DIR.glob("backtest_*.csv"), reverse=True)
    if candidates:
        return candidates[0]
    # Also check root directory
    candidates = sorted(ROOT.glob("backtest_*.csv"), reverse=True)
    if candidates:
        return candidates[0]
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Standalone gate filter — head-to-head vs current model"
    )
    parser.add_argument(
        "--csv", type=str, default=None,
        help="Path to backtest CSV (auto-detected if omitted)"
    )
    parser.add_argument(
        "--generate-demo", action="store_true", default=False,
        help="Use synthetic representative data (no CSV required)"
    )
    parser.add_argument(
        "--g6-threshold", type=float, default=GATE6_CONFIDENCE_THRESHOLD,
        dest="g6_threshold",
        help=f"Gate 6 confidence score threshold (default {GATE6_CONFIDENCE_THRESHOLD})"
    )
    parser.add_argument(
        "--min-score-a", type=float, default=SYSTEM_A_MIN_SCORE,
        dest="min_score_a",
        help=f"System A minimum score threshold (default {SYSTEM_A_MIN_SCORE})"
    )
    parser.add_argument(
        "--verbose", action="store_true", default=False,
        help="Print gate decisions for each horse"
    )
    args = parser.parse_args()

    # --- Load data -----------------------------------------------------------
    is_synthetic = False

    if args.generate_demo:
        print("Generating synthetic representative data (calibrated to known stats)...")
        rows = generate_synthetic_data()
        data_source = "SYNTHETIC (representative data, calibrated to known backtest stats)"
        is_synthetic = True
    elif args.csv:
        csv_path = Path(args.csv)
        if not csv_path.exists():
            print(f"ERROR: CSV not found: {csv_path}")
            return 1
        print(f"Loading CSV: {csv_path}")
        rows = load_backtest_csv(csv_path)
        data_source = str(csv_path)
    else:
        csv_path = find_latest_csv()
        if csv_path:
            print(f"Auto-detected CSV: {csv_path}")
            rows = load_backtest_csv(csv_path)
            data_source = str(csv_path)
        else:
            print("No backtest CSV found. Generating synthetic representative data.")
            print("(Run historical_backtest.py first to generate real data)")
            print("(Or use --csv path/to/file.csv or --generate-demo)")
            rows = generate_synthetic_data()
            data_source = "SYNTHETIC (no CSV found — run historical_backtest.py for real data)"
            is_synthetic = True

    rows = normalise_rows(rows)

    if not rows:
        print("ERROR: No records loaded.")
        return 1

    print(f"Loaded {len(rows)} records")

    # --- Group by date (each record = top scorer per race for that day) ------
    daily_records: dict = defaultdict(list)
    for row in rows:
        date_str = _ss(row.get("date"))
        if date_str:
            daily_records[date_str].append(row)

    print(f"Found {len(daily_records)} trading days")

    # --- Run three systems ---------------------------------------------------
    print("\nRunning System A (current model)...")
    sys_a_selections = run_system_a(daily_records, args.min_score_a)

    print("Running System B (standalone gate filter)...")
    sys_b_selections, gate_log = run_system_b(daily_records, args.g6_threshold)

    print("Running System C (combined)...")
    sys_c_selections = run_system_c(sys_a_selections, sys_b_selections)

    # --- Calculate statistics ------------------------------------------------
    sys_a_stats = calc_stats(sys_a_selections)
    sys_b_stats = calc_stats(sys_b_selections)
    sys_c_stats = calc_stats(sys_c_selections)

    disagree = disagreement_analysis(sys_a_selections, sys_b_selections)

    # --- Gate effectiveness (Task 3) ----------------------------------------
    print("Analysing gate effectiveness...")
    gate_eff = gate_effectiveness(rows)

    # --- Optimal gate combinations (Task 4) ---------------------------------
    print("Testing optimal gate combinations...")
    optimal = optimal_gate_combinations(daily_records)

    # --- Verbose gate log ---------------------------------------------------
    if args.verbose:
        print("\n--- GATE DECISION LOG (sample: first 5 days) ---")
        for date_str in sorted(gate_log.keys())[:5]:
            print(f"\n{date_str}:")
            for entry in gate_log[date_str]:
                gr = entry["gate_result"]
                status = "PASS-ALL" if gr["passed_all"] else f"FAIL-G{gr['first_fail']}"
                print(f"  {entry['horse']:20s} score={entry['score']:5.1f}  [{status}]")
                if not gr["passed_all"]:
                    for gnum, passed, reason in gr["gate_results"]:
                        if not passed:
                            print(f"    -> {reason}")
                            break

    # --- Build and write report ---------------------------------------------
    print("\nBuilding report...")
    report_text = build_report(
        data_source=data_source,
        sys_a_stats=sys_a_stats,
        sys_b_stats=sys_b_stats,
        sys_c_stats=sys_c_stats,
        disagree=disagree,
        gate_eff=gate_eff,
        optimal=optimal,
        gate_log_sample=dict(list(gate_log.items())[:3]),
        g6_threshold=args.g6_threshold,
    )

    json_data = build_json_output(
        data_source=data_source,
        sys_a_stats=sys_a_stats,
        sys_b_stats=sys_b_stats,
        sys_c_stats=sys_c_stats,
        disagree=disagree,
        gate_eff=gate_eff,
        optimal=optimal,
        g6_threshold=args.g6_threshold,
        is_synthetic=is_synthetic,
    )

    report_path = REPORTS_DIR / f"standalone_filter_{TODAY}.txt"
    json_path = DATA_DIR / f"standalone_filter_{TODAY}.json"

    try:
        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write(report_text)
        print(f"\nReport: {report_path}")
    except OSError as exc:
        print(f"ERROR: Could not write report — {exc}")
        return 1

    try:
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(json_data, fh, indent=2)
        print(f"JSON:   {json_path}")
    except OSError as exc:
        print(f"WARNING: Could not write JSON — {exc}")

    # --- Print summary table to stdout --------------------------------------
    print("\n" + "=" * 74)
    print("  STANDALONE FILTER — SUMMARY COMPARISON TABLE")
    print("=" * 74)
    print(report_text)

    # Quick gate-rejection summary
    print("\n--- GATE REJECTION SUMMARY ---")
    gate_names_short = {
        1: "G1 Form",
        2: "G2 Conditions",
        3: "G3 Quality",
        4: "G4 Trainer",
        5: "G5 Market",
        6: f"G6 Confidence(>={args.g6_threshold:.0f})",
    }
    for gd in gate_eff:
        verdict = gd["verdict"]
        marker = "+" if verdict == "HELPING" else ("-" if verdict == "HURTING" else "~")
        print(
            f"  [{marker}] {gate_names_short[gd['gate']]:<28}  "
            f"Rejected:{gd['rejected']:4d}  "
            f"Rej.Win%:{gd['rejected_win_pct']:5.1f}%  "
            f"Pass.Win%:{gd['passed_win_pct']:5.1f}%  "
            f"Net:{gd['net_contribution']:+5.1f}%  {verdict}"
        )

    # Synthetic data disclaimer
    if is_synthetic:
        print("\n" + "=" * 74)
        print("  NOTE: This analysis used SYNTHETIC data.")
        print("  Results are illustrative only. For real analysis:")
        print("    1. Run: python historical_backtest.py --months 6")
        print("    2. Then: python standalone_filter.py  (will auto-detect CSV)")
        print("=" * 74)

    return 0


if __name__ == "__main__":
    sys.exit(main())
