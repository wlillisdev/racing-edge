"""
winner_dna_analysis.py — Reverse-engineer what winning NAP selections share.

Loads the backtest CSV and optional cache files produced by historical_backtest.py,
then produces a structured DNA report covering:

  1. Winner vs Loser profiles (score, sub-scores, grade, class, going, odds)
  2. Winning reason frequency — which reasons appear more in winners
  3. Multi-factor winning combinations — top 2-factor combos by win rate
  4. Loser pattern classification (7 categories)
  5. Near-miss intelligence — did we score the actual winner?
  6. Optimal selection criteria — filter checklist with win rates
  7. Grade x Factor matrix
  8. Time-trend analysis — is the model improving?
  9. Decision tree / Race card

Inputs:
    data/backtest_*.csv                   (written by historical_backtest.py)
    data/backtest_cache/racecards/*.json  (optional — for reasons mining)

Outputs:
    reports/winner_dna_YYYY-MM-DD.txt
    data/winner_dna_YYYY-MM-DD.json

Exit codes:
    0 — report produced (may be sparse if no data yet)
    1 — fatal write error
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from itertools import combinations
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants — mirror thresholds from nap_selector_v3 without importing it
# ---------------------------------------------------------------------------

GRADE_A_THRESHOLD: float = 70.0
GRADE_B_PLUS_THRESHOLD: float = 60.0
NAP_MIN_SCORE: float = 60.0

# Loser categories (applied in order; first match wins)
CAT_SCORE_LOW    = "SCORE_TOO_LOW"
CAT_WRONG_GOING  = "WRONG_GOING"
CAT_TRAINER_COLD = "TRAINER_COLD"
CAT_ODDS_SHORT   = "ODDS_TOO_SHORT"
CAT_LARGE_FIELD  = "LARGE_FIELD_LOTTERY"
CAT_UNLUCKY      = "UNLUCKY"
CAT_FORM_FLAT    = "FORM_FLATTERED"
CAT_UNCLASSIFIED = "UNCLASSIFIED"

MIN_SAMPLES = 5   # minimum n before reporting any pattern as significant


# ---------------------------------------------------------------------------
# Path helpers (stdlib only — no import from src)
# ---------------------------------------------------------------------------

def _project_dir() -> Path:
    """Return the directory this script lives in (project root)."""
    return Path(__file__).resolve().parent


def _data_dir() -> Path:
    d = _project_dir() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _reports_dir() -> Path:
    d = _project_dir() / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_dir() -> Path:
    return _data_dir() / "backtest_cache"


# ---------------------------------------------------------------------------
# Safe type helpers
# ---------------------------------------------------------------------------

def _sf(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _si(val, default: int = -1) -> int:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


def _sb(val) -> bool:
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("true", "1", "yes")


# ---------------------------------------------------------------------------
# Load backtest CSV
# ---------------------------------------------------------------------------

def _find_latest_backtest_csv() -> Optional[Path]:
    """Return the most-recently-modified backtest CSV, or None."""
    candidates = sorted(
        _data_dir().glob("backtest_*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def load_backtest_csv(csv_path: Optional[Path] = None) -> list[dict]:
    """Load all rows from the backtest CSV into a list of dicts.

    CSV columns (from historical_backtest.py):
        date, race_type, race_class, distance_f, going, course,
        horse, horse_id, score, grade,
        form_score, suit_score, ctx_score, train_score, mkt_score,
        position, sp_dec, has_result, is_win, is_place,
        type_group, class_group, score_band, going_group, dist_group
    """
    if csv_path is None:
        csv_path = _find_latest_backtest_csv()
    if csv_path is None or not csv_path.exists():
        return []

    rows = []
    try:
        with open(csv_path, "r", newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for raw in reader:
                row = dict(raw)
                # Coerce numeric fields
                row["score"]       = _sf(row.get("score"))
                row["form_score"]  = _sf(row.get("form_score"))
                row["suit_score"]  = _sf(row.get("suit_score"))
                row["ctx_score"]   = _sf(row.get("ctx_score"))
                row["train_score"] = _sf(row.get("train_score"))
                row["mkt_score"]   = _sf(row.get("mkt_score"))
                row["sp_dec"]      = _sf(row.get("sp_dec"))
                row["distance_f"]  = _sf(row.get("distance_f"))
                row["is_win"]      = _sb(row.get("is_win"))
                row["is_place"]    = _sb(row.get("is_place"))
                row["has_result"]  = _sb(row.get("has_result"))
                rows.append(row)
    except OSError:
        pass
    return rows


# ---------------------------------------------------------------------------
# Load racecard cache (for reasons mining)
# ---------------------------------------------------------------------------

def _load_racecard_cache(date_str: str) -> Optional[dict]:
    """Load data/backtest_cache/racecards/YYYY-MM-DD.json."""
    p = _cache_dir() / "racecards" / f"{date_str}.json"
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _load_nap_candidates_cache(date_str: str) -> Optional[dict]:
    """Load data/nap_candidates_YYYY-MM-DD.json (written by live nap_selector_v3)."""
    p = _data_dir() / f"nap_candidates_{date_str}.json"
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# Going group helper (same logic as historical_backtest.py)
# ---------------------------------------------------------------------------

def _going_group(going: str) -> str:
    g = (going or "").lower()
    if "firm" in g:                        return "Firm/Good-Firm"
    if "heavy" in g:                       return "Heavy"
    if "soft" in g:                        return "Soft/Good-Soft"
    if "good" in g:                        return "Good"
    if "standard" in g or "slow" in g:    return "All-Weather"
    return "Unknown"


def _class_group(race_class) -> str:
    if race_class is None:
        return "Unknown"
    s = str(race_class).strip().lower()
    if not s or s == "none":
        return "Unknown"
    if s.startswith("class"):
        s = s[5:].strip()
    if "grade 1" in s or "listed" in s:
        return "Grade 1/Listed"
    if "grade 2" in s:
        return "Grade 2"
    if "grade 3" in s:
        return "Grade 3"
    if "grade" in s:
        return "Graded"
    try:
        c = int(s)
        if c <= 2:  return "Class 1-2"
        if c == 3:  return "Class 3"
        if c == 4:  return "Class 4"
        if c == 5:  return "Class 5"
        return      "Class 6-7"
    except (TypeError, ValueError):
        return "Unknown"


def _odds_band(sp_dec: float) -> str:
    if sp_dec <= 0:                 return "Unknown"
    if sp_dec < 2.0:                return "Odds-on (<Evs)"
    if sp_dec < 3.0:                return "Evs-2/1"
    if sp_dec < 5.0:                return "2/1-4/1"
    if sp_dec < 8.0:                return "4/1-7/1"
    if sp_dec < 13.0:               return "7/1-12/1"
    return                           "12/1+"


# ---------------------------------------------------------------------------
# Section 1: Winner / Loser Profile
# ---------------------------------------------------------------------------

def _mean(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def _median(values: list[float]) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 0:
        return (s[mid - 1] + s[mid]) / 2.0
    return s[mid]


def _pct_counter(items: list) -> dict:
    """Return {value: pct_of_total} sorted by pct desc."""
    if not items:
        return {}
    c = Counter(items)
    total = len(items)
    return {k: round(v / total * 100, 1) for k, v in c.most_common()}


def build_profiles(records: list[dict]) -> tuple[dict, dict]:
    """Split records into winner/loser profiles.

    Only considers rows that have a result (has_result=True).
    Returns (winner_profile, loser_profile).
    Each profile is a dict of {field: {mean, median, distribution}}.
    """
    with_result = [r for r in records if r["has_result"]]
    winners = [r for r in with_result if r["is_win"]]
    losers  = [r for r in with_result if not r["is_win"]]

    def _profile(rows: list[dict]) -> dict:
        def nums(field: str) -> list[float]:
            return [_sf(r.get(field)) for r in rows if _sf(r.get(field)) > 0]

        return {
            "count":        len(rows),
            "score":        {"mean": _mean(nums("score")), "median": _median(nums("score"))},
            "form_score":   {"mean": _mean(nums("form_score")),  "median": _median(nums("form_score"))},
            "suit_score":   {"mean": _mean(nums("suit_score")),  "median": _median(nums("suit_score"))},
            "ctx_score":    {"mean": _mean(nums("ctx_score")),   "median": _median(nums("ctx_score"))},
            "train_score":  {"mean": _mean(nums("train_score")), "median": _median(nums("train_score"))},
            "mkt_score":    {"mean": _mean(nums("mkt_score")),   "median": _median(nums("mkt_score"))},
            "sp_dec":       {"mean": _mean(nums("sp_dec")),      "median": _median(nums("sp_dec"))},
            "grade_dist":   _pct_counter([r.get("grade", "?") for r in rows]),
            "class_dist":   _pct_counter([r.get("class_group") or _class_group(r.get("race_class")) for r in rows]),
            "going_dist":   _pct_counter([r.get("going_group") or _going_group(r.get("going", "")) for r in rows]),
            "type_dist":    _pct_counter([r.get("type_group", "?") for r in rows]),
            "odds_dist":    _pct_counter([_odds_band(_sf(r.get("sp_dec"))) for r in rows]),
            "score_band":   _pct_counter([r.get("score_band", "?") for r in rows]),
        }

    return _profile(winners), _profile(losers)


def compare_profiles(wp: dict, lp: dict) -> list[dict]:
    """For each numeric attribute, show winner vs loser mean and the gap."""
    fields = [
        ("score",       "Composite score"),
        ("form_score",  "Form sub-score"),
        ("suit_score",  "Suitability sub-score"),
        ("ctx_score",   "Context sub-score"),
        ("train_score", "Trainer sub-score"),
        ("mkt_score",   "Market sub-score"),
        ("sp_dec",      "SP decimal (lower = shorter price)"),
    ]
    results = []
    for field, label in fields:
        wm = (wp.get(field) or {}).get("mean")
        lm = (lp.get(field) or {}).get("mean")
        if wm is None or lm is None:
            continue
        results.append({
            "field":        field,
            "label":        label,
            "winner_mean":  round(wm, 2),
            "loser_mean":   round(lm, 2),
            "gap":          round(wm - lm, 2),
            "winner_edge":  wm > lm if field != "sp_dec" else wm < lm,
        })
    return results


# ---------------------------------------------------------------------------
# Section 2: Reason frequency mining
# ---------------------------------------------------------------------------

# Map reason text fragments to canonical signal names
_REASON_SIGNALS: list[tuple[str, str]] = [
    ("Won last time out",           "LTO_win"),
    ("Won",                         "recent_win"),          # catches "Won 2 runs ago" etc.
    ("Going proven",                "going_win"),
    ("Going suited",                "going_placed"),
    ("Hot trainer",                 "trainer_hot"),
    ("In-form trainer",             "trainer_inform"),
    ("Course winner",               "course_win"),
    ("Course placed",               "course_placed"),
    ("Strong steamer",              "strong_steamer"),
    ("Market steamer",              "steamer"),
    ("Improving form trend",        "improving_trend"),
    ("Declining form trend",        "declining_trend"),
    ("Small field",                 "small_field"),
    ("First run after wind surgery","wind_surgery"),
    ("Top RPR in field",            "top_rpr"),
    ("Joint/near-top RPR",          "top_rpr"),
    ("Top-third RPR",               "top3_rpr"),
    ("Distance proven",             "dist_win"),
    ("Distance placed",             "dist_placed"),
    ("Ideal break",                 "ideal_break"),
    ("Quick reappearance",          "quick_return"),
    ("Stale",                       "stale_horse"),
    ("Long absence",                "long_absence"),
    ("DANGEROUS DRIFT",             "dangerous_drift"),
    ("Class 1",                     "class_elite"),
    ("Class 2",                     "class_elite"),
    ("Class 3",                     "class_good"),
]


def _extract_signals(reasons_list: list[str]) -> set[str]:
    """Convert a raw reasons list into a set of canonical signal names."""
    signals: set[str] = set()
    text = " | ".join(reasons_list or [])
    for fragment, signal in _REASON_SIGNALS:
        if fragment in text:
            signals.add(signal)
    return signals


def mine_reason_frequencies(
    records: list[dict],
    racecard_cache_loader=None,
) -> dict:
    """
    Mine reasons from nap_candidates cache files if available.

    For each record that has a result, attempt to load the daily nap_candidates
    JSON.  If reasons are present, extract signals and count by outcome.

    Returns {signal: {winner_pct, loser_pct, winner_count, loser_count,
                      total_winner, total_loser, lift}} sorted by lift desc.
    """
    with_result = [r for r in records if r["has_result"]]
    total_winners = sum(1 for r in with_result if r["is_win"])
    total_losers  = sum(1 for r in with_result if not r["is_win"])

    if total_winners == 0 or total_losers == 0:
        return {}

    signal_wins:   Counter = Counter()
    signal_losses: Counter = Counter()

    for row in with_result:
        date_str = row.get("date", "")
        if not date_str:
            continue
        nap_doc = _load_nap_candidates_cache(date_str)
        if nap_doc is None:
            continue
        nap = nap_doc.get("nap") or {}
        reasons = nap.get("reasons") or []
        if not reasons:
            continue
        signals = _extract_signals(reasons)
        if row["is_win"]:
            for s in signals:
                signal_wins[s] += 1
        else:
            for s in signals:
                signal_losses[s] += 1

    all_signals = set(signal_wins.keys()) | set(signal_losses.keys())
    result = {}
    for sig in all_signals:
        wc = signal_wins[sig]
        lc = signal_losses[sig]
        wp = wc / total_winners * 100
        lp = lc / total_losers  * 100
        lift = wp - lp  # positive = appears more in winners
        result[sig] = {
            "winner_count":  wc,
            "loser_count":   lc,
            "total_winners": total_winners,
            "total_losers":  total_losers,
            "winner_pct":    round(wp, 1),
            "loser_pct":     round(lp, 1),
            "lift":          round(lift, 1),
        }

    return dict(sorted(result.items(), key=lambda kv: -kv[1]["lift"]))


# ---------------------------------------------------------------------------
# Section 3: Multi-factor winning conditions
# ---------------------------------------------------------------------------

# Boolean flag extractors — each returns True/False for a record
_FACTOR_DEFS: list[tuple[str, callable]] = [
    ("score_70plus",   lambda r: r["score"] >= 70.0),
    ("score_65plus",   lambda r: r["score"] >= 65.0),
    ("grade_A",        lambda r: (r.get("grade") or "") == "A"),
    ("grade_B+",       lambda r: (r.get("grade") or "") in ("A", "B+")),
    ("suit_8plus",     lambda r: r["suit_score"] >= 8.0),
    ("suit_12plus",    lambda r: r["suit_score"] >= 12.0),
    ("train_5plus",    lambda r: r["train_score"] >= 5.0),
    ("form_20plus",    lambda r: r["form_score"] >= 20.0),
    ("class_1_2",      lambda r: (r.get("class_group") or _class_group(r.get("race_class"))) in ("Class 1-2", "Grade 1/Listed")),
    ("class_1_3",      lambda r: (r.get("class_group") or _class_group(r.get("race_class"))) in ("Class 1-2", "Class 3", "Grade 1/Listed", "Grade 2", "Grade 3")),
    ("good_going",     lambda r: "Good" in (r.get("going_group") or _going_group(r.get("going", "")))),
    ("aw_going",       lambda r: "All-Weather" in (r.get("going_group") or _going_group(r.get("going", "")))),
    ("soft_going",     lambda r: "Soft" in (r.get("going_group") or _going_group(r.get("going", "")))),
    ("value_odds",     lambda r: 2.0 <= r["sp_dec"] <= 7.0 and r["sp_dec"] > 0),
    ("short_odds",     lambda r: 0 < r["sp_dec"] < 2.5),
    ("flat_race",      lambda r: (r.get("type_group", "") or "").lower() in ("flat", "")),
    ("hurdle",         lambda r: "hurdle" in (r.get("type_group", "") or "").lower()),
]


def _apply_factors(row: dict) -> dict[str, bool]:
    return {name: fn(row) for name, fn in _FACTOR_DEFS}


def find_two_factor_combos(records: list[dict]) -> list[dict]:
    """
    Test all 2-factor combinations.  For each combo, compute:
        - n (sample size)
        - win_rate (%)
        - baseline_win_rate (all records with result)
        - lift over baseline
    Only report combos with n >= MIN_SAMPLES.
    Returns list sorted by win_rate desc.
    """
    with_result = [r for r in records if r["has_result"]]
    if not with_result:
        return []

    baseline_wins = sum(1 for r in with_result if r["is_win"])
    baseline_n    = len(with_result)
    baseline_wr   = baseline_wins / baseline_n * 100 if baseline_n else 0.0

    # Pre-compute factors for each row
    row_factors = [(r, _apply_factors(r)) for r in with_result]

    factor_names = [name for name, _ in _FACTOR_DEFS]
    results = []

    for f1, f2 in combinations(factor_names, 2):
        subset = [(r, fv) for r, fv in row_factors if fv[f1] and fv[f2]]
        n = len(subset)
        if n < MIN_SAMPLES:
            continue
        wins = sum(1 for r, _ in subset if r["is_win"])
        wr   = wins / n * 100
        pl   = sum((r["sp_dec"] - 1.0) if r["is_win"] else -1.0 for r, _ in subset)
        roi  = pl / n * 100
        results.append({
            "factor1":         f1,
            "factor2":         f2,
            "combo":           f"{f1} AND {f2}",
            "n":               n,
            "wins":            wins,
            "win_rate":        round(wr, 1),
            "baseline_wr":     round(baseline_wr, 1),
            "lift":            round(wr - baseline_wr, 1),
            "pl":              round(pl, 2),
            "roi":             round(roi, 1),
        })

    return sorted(results, key=lambda x: -x["win_rate"])


# ---------------------------------------------------------------------------
# Section 4: Loser pattern classification
# ---------------------------------------------------------------------------

def classify_loser(row: dict) -> str:
    """Assign a loss category.  Applied in priority order — first match wins."""
    score      = row["score"]
    suit_score = row["suit_score"]
    train_score= row["train_score"]
    sp_dec     = row["sp_dec"]
    field_size = _si(row.get("field_size"), default=-1)
    position   = row.get("position", "")
    going_grp  = row.get("going_group") or _going_group(row.get("going", ""))
    form_score = row["form_score"]

    # 1 — Score too low (marginal confidence)
    if score < 65.0:
        return CAT_SCORE_LOW

    # 2 — Wrong going: suitability score low while going is known
    if suit_score < 6.0 and going_grp not in ("Unknown", "All-Weather"):
        return CAT_WRONG_GOING

    # 3 — Trainer cold: trainer sub-score suggests no form
    if train_score < 2.0:
        return CAT_TRAINER_COLD

    # 4 — Odds too short: heavy favourite that lost
    if 0 < sp_dec < 2.5:
        return CAT_ODDS_SHORT

    # 5 — Large field lottery
    if field_size > 15:
        return CAT_LARGE_FIELD

    # 6 — Unlucky: position 2nd or 3rd (within touching distance)
    try:
        pos_int = int(position)
        if pos_int == 2:
            return CAT_UNLUCKY
    except (TypeError, ValueError):
        pass

    # 7 — Form flattered: strong form score but low suit / going unknown
    if form_score >= 20.0 and suit_score < 5.0:
        return CAT_FORM_FLAT

    return CAT_UNCLASSIFIED


def analyse_losses(records: list[dict]) -> dict:
    """Classify every loss and return category breakdown."""
    with_result = [r for r in records if r["has_result"]]
    losers = [r for r in with_result if not r["is_win"]]

    if not losers:
        return {"total_losses": 0, "breakdown": {}, "most_common": None}

    cat_counts: Counter = Counter()
    for row in losers:
        cat = classify_loser(row)
        cat_counts[cat] += 1

    total = len(losers)
    breakdown = {
        cat: {
            "count": cnt,
            "pct":   round(cnt / total * 100, 1),
        }
        for cat, cnt in cat_counts.most_common()
    }

    return {
        "total_losses": total,
        "breakdown":    breakdown,
        "most_common":  cat_counts.most_common(1)[0][0] if cat_counts else None,
    }


# ---------------------------------------------------------------------------
# Section 5: Near-miss intelligence
# ---------------------------------------------------------------------------

def near_miss_analysis(records: list[dict]) -> dict:
    """
    Group records by date.  For each losing day:
    - Did the actual winner appear in the scoring?  (We can tell if the winner
      scored ≥ NAP_MIN_SCORE — if another horse in the SAME RACE was picked
      instead, that is a wrong-horse miss.)
    - Was there a higher-scored horse in a different race on the same day?

    Note: backtest CSV only contains the TOP SCORER per race.  So if the actual
    winner was not the top scorer, it won't appear in the CSV at all.  The best
    we can do is identify days where the top-scorer of a different race scored
    higher than our NAP.

    Returns {
        "losing_days": N,
        "same_race_miss": N,      — top scorer of the same race was not winner
        "other_race_miss": N,     — a higher scorer existed in another race
        "summary_pct": {...}
    }
    """
    with_result = [r for r in records if r["has_result"]]

    # Group by date
    by_date: dict[str, list[dict]] = defaultdict(list)
    for r in with_result:
        by_date[r.get("date", "unknown")].append(r)

    # Identify NAP per day (highest scorer on that day, mirrors daily_naps logic)
    losing_days = 0
    winner_in_top3 = 0    # actual winner had score >= NAP_MIN_SCORE
    higher_other_race = 0 # there was a higher-scored horse in another race

    for date_str, day_rows in by_date.items():
        # Sort by score to find the NAP
        sorted_day = sorted(day_rows, key=lambda x: -x["score"])
        # NAP = highest scorer on the day that meets threshold
        nap_row = next((r for r in sorted_day if r["score"] >= NAP_MIN_SCORE), None)
        if nap_row is None:
            continue

        if nap_row["is_win"]:
            continue  # NAP won — not a losing day

        losing_days += 1

        # Did any other row on the day have a higher score?
        nap_score = nap_row["score"]
        others = [r for r in day_rows if r is not nap_row and r["score"] >= NAP_MIN_SCORE]
        if any(r["score"] > nap_score for r in others):
            higher_other_race += 1

        # Did any row on the day represent a winner with a decent score?
        winners_scored = [r for r in day_rows if r["is_win"] and r["score"] >= NAP_MIN_SCORE]
        if winners_scored:
            winner_in_top3 += 1

    ld = max(losing_days, 1)
    return {
        "losing_days":       losing_days,
        "winner_scored_pct": round(winner_in_top3 / ld * 100, 1),
        "higher_other_race_pct": round(higher_other_race / ld * 100, 1),
        "winner_in_scored_count": winner_in_top3,
        "higher_other_race_count": higher_other_race,
        "interpretation": (
            "On {w}% of losing days a scored race winner existed — "
            "model scored the horse but it wasn't the NAP pick. "
            "On {h}% of losing days there was a higher-scored horse in a different race.".format(
                w=round(winner_in_top3 / ld * 100, 1),
                h=round(higher_other_race / ld * 100, 1),
            )
        ),
    }


# ---------------------------------------------------------------------------
# Section 6: Optimal selection criteria
# ---------------------------------------------------------------------------

def derive_optimal_criteria(records: list[dict], top_combos: list[dict]) -> dict:
    """
    Derive a Grade-A checklist: which combination of conditions produces the
    highest win rate, and how many historical selections meet it.

    We test the multi-step filter: score >= 70 + top contributing boolean factors.
    """
    with_result = [r for r in records if r["has_result"]]
    if not with_result:
        return {}

    overall_wr = sum(1 for r in with_result if r["is_win"]) / len(with_result) * 100

    # Start with score_70plus and add each factor greedily
    base_mask = [r["score"] >= 70.0 for r in with_result]

    criteria_tests = [
        ("score >= 70",       lambda r: r["score"] >= 70.0),
        ("suit_score >= 8",   lambda r: r["suit_score"] >= 8.0),
        ("train_score >= 5",  lambda r: r["train_score"] >= 5.0),
        ("form_score >= 20",  lambda r: r["form_score"] >= 20.0),
        ("class 1-3",         lambda r: (r.get("class_group") or _class_group(r.get("race_class")))
                                         in ("Class 1-2", "Class 3", "Grade 1/Listed", "Grade 2", "Grade 3")),
        ("value odds 2-7",    lambda r: 2.0 <= r["sp_dec"] <= 7.0),
        ("not large field",   lambda r: True),  # placeholder — field_size not in CSV
    ]

    # Test each criterion alone and in combination with score_70plus
    criterion_results = []
    for label, fn in criteria_tests:
        subset = [r for r in with_result if fn(r)]
        n = len(subset)
        if n < MIN_SAMPLES:
            continue
        wins = sum(1 for r in subset if r["is_win"])
        wr   = wins / n * 100
        pl   = sum((r["sp_dec"] - 1.0) if r["is_win"] else -1.0 for r in subset)
        roi  = pl / n * 100
        criterion_results.append({
            "criterion": label,
            "n":         n,
            "wins":      wins,
            "win_rate":  round(wr, 1),
            "roi":       round(roi, 1),
        })

    criterion_results.sort(key=lambda x: -x["win_rate"])

    # Build the "MUST HAVE" set: apply all criteria simultaneously
    def _all_criteria(r: dict) -> bool:
        return (
            r["score"] >= 70.0
            and r["suit_score"] >= 8.0
            and r["train_score"] >= 5.0
        )

    gold_subset = [r for r in with_result if _all_criteria(r)]
    gold_n    = len(gold_subset)
    gold_wins = sum(1 for r in gold_subset if r["is_win"])
    gold_wr   = gold_wins / gold_n * 100 if gold_n else 0.0
    gold_pl   = sum((r["sp_dec"] - 1.0) if r["is_win"] else -1.0 for r in gold_subset)
    gold_roi  = gold_pl / gold_n * 100 if gold_n else 0.0

    return {
        "overall_win_rate":  round(overall_wr, 1),
        "total_with_result": len(with_result),
        "criterion_breakdown": criterion_results,
        "gold_standard": {
            "description": "score>=70 AND suit>=8 AND train>=5",
            "n":           gold_n,
            "wins":        gold_wins,
            "win_rate":    round(gold_wr, 1),
            "pl":          round(gold_pl, 2),
            "roi":         round(gold_roi, 1),
        },
    }


# ---------------------------------------------------------------------------
# Section 7: Grade x Factor matrix
# ---------------------------------------------------------------------------

def grade_factor_matrix(records: list[dict]) -> dict:
    """Build win rate grid: Grade × (going_proven, form_strong, class_elite, train_hot)."""
    with_result = [r for r in records if r["has_result"]]

    grades = ["A", "B+"]
    factors = {
        "suit_8plus":   lambda r: r["suit_score"] >= 8.0,
        "form_20plus":  lambda r: r["form_score"] >= 20.0,
        "class_1_3":    lambda r: (r.get("class_group") or _class_group(r.get("race_class")))
                                    in ("Class 1-2", "Class 3", "Grade 1/Listed", "Grade 2", "Grade 3"),
        "train_5plus":  lambda r: r["train_score"] >= 5.0,
    }

    matrix = {}
    for grade in grades:
        grade_rows = [r for r in with_result if (r.get("grade") or "") == grade]
        matrix[grade] = {
            "_total": {
                "n":        len(grade_rows),
                "wins":     sum(1 for r in grade_rows if r["is_win"]),
                "win_rate": round(sum(1 for r in grade_rows if r["is_win"]) / max(len(grade_rows), 1) * 100, 1),
            }
        }
        for fname, fn in factors.items():
            subset = [r for r in grade_rows if fn(r)]
            n      = len(subset)
            wins   = sum(1 for r in subset if r["is_win"])
            wr     = wins / n * 100 if n else 0.0
            matrix[grade][fname] = {
                "n":        n,
                "wins":     wins,
                "win_rate": round(wr, 1) if n >= MIN_SAMPLES else None,
            }

    return matrix


# ---------------------------------------------------------------------------
# Section 8: Time-trend analysis
# ---------------------------------------------------------------------------

def time_trend_analysis(records: list[dict]) -> dict:
    """Compare win rates in first vs last third of the date range.

    Also identifies which calendar months perform best/worst.
    """
    with_result = [r for r in records if r["has_result"]]
    if not with_result:
        return {}

    # Sort by date
    try:
        sorted_rows = sorted(with_result, key=lambda r: r.get("date", ""))
    except Exception:
        return {}

    n = len(sorted_rows)
    third = max(n // 3, 1)

    def _stats(rows: list[dict]) -> dict:
        total = len(rows)
        wins  = sum(1 for r in rows if r["is_win"])
        pl    = sum((r["sp_dec"] - 1.0) if r["is_win"] else -1.0 for r in rows)
        wr    = wins / total * 100 if total else 0.0
        roi   = pl / total * 100   if total else 0.0
        return {
            "n":        total,
            "wins":     wins,
            "win_rate": round(wr, 1),
            "pl":       round(pl, 2),
            "roi":      round(roi, 1),
        }

    first_third  = _stats(sorted_rows[:third])
    last_third   = _stats(sorted_rows[n - third:])
    middle_third = _stats(sorted_rows[third: n - third])

    # Monthly breakdown
    month_groups: dict[str, list[dict]] = defaultdict(list)
    for r in sorted_rows:
        month = (r.get("date") or "")[:7]  # YYYY-MM
        if month:
            month_groups[month].append(r)

    monthly: list[dict] = []
    for month, rows in sorted(month_groups.items()):
        s = _stats(rows)
        s["month"] = month
        monthly.append(s)

    # Identify best/worst months
    valid_months = [m for m in monthly if m["n"] >= MIN_SAMPLES]
    best_month  = max(valid_months, key=lambda m: m["win_rate"]) if valid_months else None
    worst_month = min(valid_months, key=lambda m: m["win_rate"]) if valid_months else None

    # Trend: is win_rate going up?
    first_wr = first_third["win_rate"]
    last_wr  = last_third["win_rate"]
    trend_direction = "IMPROVING" if last_wr > first_wr + 2 else ("DECLINING" if last_wr < first_wr - 2 else "STABLE")

    return {
        "first_third":       first_third,
        "middle_third":      middle_third,
        "last_third":        last_third,
        "trend_direction":   trend_direction,
        "monthly":           monthly,
        "best_month":        best_month,
        "worst_month":       worst_month,
        "improvement_pts":   round(last_wr - first_wr, 1),
        "date_range":        {
            "start": sorted_rows[0].get("date", ""),
            "end":   sorted_rows[-1].get("date", ""),
        },
    }


# ---------------------------------------------------------------------------
# Section 9: Decision tree / Race card
# ---------------------------------------------------------------------------

def build_decision_tree(
    optimal: dict,
    combos: list[dict],
    loser_analysis: dict,
    trend: dict,
) -> list[str]:
    """Return a list of human-readable decision rule strings."""
    lines: list[str] = []
    wr = optimal.get("overall_win_rate", 0.0)
    gold = optimal.get("gold_standard", {})

    lines.append("PRIMARY FILTER (Grade A NAP confidence = HIGH):")
    lines.append(f"  IF score >= 70")
    lines.append(f"  AND suitability_score >= 8  (going/distance proven)")
    lines.append(f"  AND trainer_score >= 5      (trainer in-form)")
    lines.append(f"  THEN: Grade A+ NAP. Use this selection with confidence.")
    if gold.get("n", 0) >= MIN_SAMPLES:
        lines.append(f"  Historical: {gold['wins']}/{gold['n']} "
                     f"({gold['win_rate']}% win rate, ROI {gold['roi']:+.1f}%) "
                     f"vs {wr:.1f}% baseline")
    lines.append("")

    lines.append("SECONDARY FILTER (Grade B+ NAP confidence = MEDIUM):")
    lines.append(f"  IF score >= 65")
    lines.append(f"  AND (suitability_score >= 6 OR form_score >= 22)")
    lines.append(f"  AND trainer_score >= 2")
    lines.append(f"  THEN: B+ NAP. Acceptable — proceed but note risks.")
    lines.append("")

    lines.append("VETO RULES (override any positive signal):")
    lines.append(f"  IF dangerous_drift warning present  → NO BET")
    lines.append(f"  IF score < 60                       → NO BET (insufficient confidence)")
    lines.append(f"  IF going_group = Unknown            → CAUTION (no going assessment possible)")

    # Add worst loss category as a veto hint
    worst = loser_analysis.get("most_common")
    if worst:
        lines.append(f"  IF category {worst} detected       → reduce stake or skip")

    lines.append("")
    lines.append("GOLDEN COMBOS (add confidence if score 65-70 borderline):")
    for combo in (combos or [])[:5]:
        lines.append(f"  {combo['combo']}: {combo['win_rate']}% win rate "
                     f"(n={combo['n']}, ROI={combo['roi']:+.1f}%)")

    lines.append("")
    trend_dir = trend.get("trend_direction", "UNKNOWN")
    lines.append(f"MODEL TREND: {trend_dir}")
    bm = trend.get("best_month")
    wm = trend.get("worst_month")
    if bm:
        lines.append(f"  Best month:  {bm['month']} ({bm['win_rate']}% win rate)")
    if wm:
        lines.append(f"  Worst month: {wm['month']} ({wm['win_rate']}% win rate)")

    return lines


# ---------------------------------------------------------------------------
# Report formatter
# ---------------------------------------------------------------------------

SEP   = "=" * 72
HSEP  = "-" * 72


def _fmt_table(
    rows: list[dict],
    columns: list[tuple[str, str, int]],  # (key, header, width)
    sort_key: Optional[str] = None,
    sort_reverse: bool = True,
) -> list[str]:
    """Generic table formatter.  columns = list of (key, header, width)."""
    if sort_key:
        rows = sorted(rows, key=lambda r: (r.get(sort_key) or 0), reverse=sort_reverse)

    header = "  " + "  ".join(
        f"{hdr:>{w}}" if isinstance(hdr, str) else str(hdr)
        for _, hdr, w in columns
    )
    sep_line = "  " + "  ".join("-" * w for _, _, w in columns)

    lines = [header, sep_line]
    for r in rows:
        parts = []
        for key, _, w in columns:
            val = r.get(key)
            if val is None:
                parts.append(f"{'—':>{w}}")
            elif isinstance(val, float):
                parts.append(f"{val:>{w}.1f}")
            else:
                parts.append(f"{str(val):>{w}}")
        lines.append("  " + "  ".join(parts))
    return lines


def _fmt_pct_dist(dist: dict, label: str) -> list[str]:
    """Render a {value: pct} distribution as a table."""
    lines = [f"  {label}:"]
    for k, pct in dist.items():
        bar = "#" * int(pct / 2)
        lines.append(f"    {k:<22} {pct:>5.1f}%  {bar}")
    return lines


def format_report(
    date_str: str,
    csv_path: Optional[Path],
    records: list[dict],
    winner_profile: dict,
    loser_profile: dict,
    profile_comparison: list[dict],
    reason_freq: dict,
    top_combos: list[dict],
    loser_analysis: dict,
    near_miss: dict,
    optimal: dict,
    grade_matrix: dict,
    trend: dict,
    decision_tree: list[str],
) -> str:

    with_result = [r for r in records if r["has_result"]]
    total_w = winner_profile.get("count", 0)
    total_l = loser_profile.get("count", 0)
    total_n = total_w + total_l
    overall_wr = total_w / total_n * 100 if total_n else 0.0

    lines: list[str] = [
        SEP,
        "  WINNER DNA ANALYSIS — NAP MODEL REVERSE ENGINEERING",
        f"  Generated:  {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"  Source CSV: {csv_path or 'not found'}",
        f"  Records:    {len(records)} total | {total_n} with result",
        f"  Baseline:   {total_w}/{total_n} wins = {overall_wr:.1f}% win rate",
        SEP,
        "",
    ]

    if not records:
        lines += [
            "  NO DATA AVAILABLE",
            "  Run historical_backtest.py first to generate the backtest CSV.",
            "  This report structure is produced but all analysis sections are empty.",
            "",
            SEP,
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 1. Winner vs Loser Profiles
    # ------------------------------------------------------------------
    lines += [
        "1. WINNER vs LOSER PROFILES",
        HSEP,
        f"  Winners: {total_w}  |  Losers: {total_l}  |  Overall win rate: {overall_wr:.1f}%",
        "",
        "  NUMERIC COMPARISON (winner mean vs loser mean):",
        f"  {'Attribute':<30} {'Winner':>8} {'Loser':>8} {'Gap':>8} {'Edge?':>8}",
        "  " + "-" * 58,
    ]
    for row in profile_comparison:
        edge = "Winner" if row["winner_edge"] else "Loser"
        lines.append(
            f"  {row['label']:<30} "
            f"{row['winner_mean']:>8.2f} "
            f"{row['loser_mean']:>8.2f} "
            f"{row['gap']:>+8.2f} "
            f"  {edge}"
        )
    lines.append("")

    # Grade distribution
    wp_grade = winner_profile.get("grade_dist", {})
    lp_grade = loser_profile.get("grade_dist", {})
    if wp_grade or lp_grade:
        all_grades = sorted(set(list(wp_grade.keys()) + list(lp_grade.keys())))
        lines.append(f"  GRADE DISTRIBUTION:")
        lines.append(f"  {'Grade':<12} {'Winners%':>10} {'Losers%':>10}")
        lines.append("  " + "-" * 34)
        for g in all_grades:
            lines.append(
                f"  {g:<12} {wp_grade.get(g, 0.0):>10.1f} {lp_grade.get(g, 0.0):>10.1f}"
            )
        lines.append("")

    # Odds distribution
    wp_odds = winner_profile.get("odds_dist", {})
    lp_odds = loser_profile.get("odds_dist", {})
    if wp_odds or lp_odds:
        all_odds = list(dict.fromkeys(list(wp_odds.keys()) + list(lp_odds.keys())))
        lines.append(f"  ODDS BAND (SP):")
        lines.append(f"  {'Band':<16} {'Winners%':>10} {'Losers%':>10} {'Edge':>10}")
        lines.append("  " + "-" * 48)
        for b in all_odds:
            wp = wp_odds.get(b, 0.0)
            lp = lp_odds.get(b, 0.0)
            edge = "Winner" if wp > lp else ("Loser" if lp > wp else "—")
            lines.append(f"  {b:<16} {wp:>10.1f} {lp:>10.1f} {edge:>10}")
        lines.append("")

    # ------------------------------------------------------------------
    # 2. Reason frequency
    # ------------------------------------------------------------------
    lines += ["2. WINNING REASON FREQUENCY", HSEP]

    if not reason_freq:
        lines += [
            "  No reasons data available.",
            "  (nap_candidates_YYYY-MM-DD.json files not found in data/)",
            "  Run the live nap_selector_v3.py pipeline to build this cache.",
            "",
        ]
    else:
        lines.append(f"  {'Signal':<24} {'Win%':>7} {'Loss%':>7} {'Lift':>7}  Interpretation")
        lines.append("  " + "-" * 70)
        for sig, stats in reason_freq.items():
            lift = stats["lift"]
            interp = "POSITIVE SIGNAL" if lift > 5 else ("FALSE SIGNAL" if lift < -5 else "neutral")
            lines.append(
                f"  {sig:<24} {stats['winner_pct']:>7.1f} "
                f"{stats['loser_pct']:>7.1f} "
                f"{lift:>+7.1f}  {interp}"
            )
        lines.append("")

    # ------------------------------------------------------------------
    # 3. Multi-factor combinations
    # ------------------------------------------------------------------
    lines += ["3. MULTI-FACTOR WINNING CONDITIONS (top 10 by win rate)", HSEP]

    if not top_combos:
        lines += [
            f"  No combinations with >= {MIN_SAMPLES} samples found.",
            "  More backtest data needed.",
            "",
        ]
    else:
        lines.append(
            f"  {'Factor Combination':<42} {'N':>5} {'Wins':>5} {'WR%':>6} {'Baseline%':>9} {'Lift':>6} {'ROI%':>7}"
        )
        lines.append("  " + "-" * 80)
        for combo in top_combos[:10]:
            lines.append(
                f"  {combo['combo']:<42} "
                f"{combo['n']:>5} "
                f"{combo['wins']:>5} "
                f"{combo['win_rate']:>6.1f} "
                f"{combo['baseline_wr']:>9.1f} "
                f"{combo['lift']:>+6.1f} "
                f"{combo['roi']:>+7.1f}"
            )
        lines.append("")

    # ------------------------------------------------------------------
    # 4. Loser pattern analysis
    # ------------------------------------------------------------------
    lines += ["4. LOSER PATTERN ANALYSIS", HSEP]
    lb = loser_analysis.get("breakdown", {})
    total_losses = loser_analysis.get("total_losses", 0)
    most_common  = loser_analysis.get("most_common")

    if not lb:
        lines += ["  No loss data available.", ""]
    else:
        lines.append(f"  Total classified losses: {total_losses}")
        lines.append(f"  Most common failure category: {most_common}")
        lines.append("")
        lines.append(f"  {'Category':<26} {'Count':>7} {'Pct':>7}  Description")
        lines.append("  " + "-" * 70)
        cat_descriptions = {
            CAT_SCORE_LOW:    "Model barely above threshold (60-65) — low confidence",
            CAT_WRONG_GOING:  "Low suitability score — horse unsuited to today's going",
            CAT_TRAINER_COLD: "Trainer not in form (train_score < 2)",
            CAT_ODDS_SHORT:   "Heavy favourite (<6/4) that lost — value risk",
            CAT_LARGE_FIELD:  "Field > 15 runners — lottery element overwhelmed model",
            CAT_UNLUCKY:      "Finished 2nd — beaten within a length or two",
            CAT_FORM_FLAT:    "High form score but low suitability — form may flatter",
            CAT_UNCLASSIFIED: "No single clear cause identified",
        }
        for cat, stats in lb.items():
            desc = cat_descriptions.get(cat, "")
            lines.append(
                f"  {cat:<26} {stats['count']:>7} {stats['pct']:>6.1f}%  {desc}"
            )
        lines.append("")
        lines.append("  WEAKEST LINK: The most common loss category reveals the model's")
        lines.append(f"  primary failure mode: [{most_common}]")
        lines.append("")

    # ------------------------------------------------------------------
    # 5. Near-miss intelligence
    # ------------------------------------------------------------------
    lines += ["5. NEAR-MISS INTELLIGENCE", HSEP]
    nm = near_miss

    if not nm or nm.get("losing_days", 0) == 0:
        lines += ["  Insufficient data for near-miss analysis.", ""]
    else:
        lines += [
            f"  Losing days analysed: {nm['losing_days']}",
            f"  Days where a scored winner existed:      {nm['winner_in_scored_count']} "
            f"({nm['winner_scored_pct']}%)",
            f"  Days where a higher-scorer was in another race: {nm['higher_other_race_count']} "
            f"({nm['higher_other_race_pct']}%)",
            "",
            "  INTERPRETATION:",
        ]
        wsp = nm["winner_scored_pct"]
        horp = nm["higher_other_race_pct"]
        if wsp > 30:
            lines.append("  ► The actual winner was often scored — we may be picking the")
            lines.append("    wrong horse FROM a correctly-identified race.")
        if horp > 40:
            lines.append("  ► On many losing days a higher-scored horse existed in another")
            lines.append("    race — consider whether the NAP selection criteria should")
            lines.append("    look harder at cross-race comparison.")
        if wsp <= 30 and horp <= 40:
            lines.append("  ► Losses appear to be genuine misses — the winner was not well")
            lines.append("    represented in our scoring on those days.")
        lines.append("")

    # ------------------------------------------------------------------
    # 6. Optimal selection criteria
    # ------------------------------------------------------------------
    lines += ["6. OPTIMAL SELECTION CRITERIA", HSEP]
    crit = optimal.get("criterion_breakdown", [])
    gold = optimal.get("gold_standard", {})
    ow   = optimal.get("overall_win_rate", 0.0)

    if not crit:
        lines += ["  Insufficient data.", ""]
    else:
        lines.append(
            f"  Baseline win rate across all records with result: {ow:.1f}%"
        )
        lines.append("")
        lines.append(
            f"  {'Criterion':<28} {'N':>6} {'Wins':>5} {'WR%':>7} {'ROI%':>7}"
        )
        lines.append("  " + "-" * 58)
        for c in crit:
            lines.append(
                f"  {c['criterion']:<28} {c['n']:>6} {c['wins']:>5} "
                f"{c['win_rate']:>7.1f} {c['roi']:>+7.1f}"
            )
        lines.append("")
        if gold.get("n", 0) >= MIN_SAMPLES:
            lines += [
                f"  GOLD STANDARD FILTER ({gold['description']}):",
                f"  {gold['wins']}/{gold['n']} wins  →  {gold['win_rate']}% win rate  "
                f"(baseline {ow:.1f}%)  ROI {gold['roi']:+.1f}%",
                "",
            ]
        else:
            lines.append(
                f"  Gold standard filter has < {MIN_SAMPLES} samples — not yet reportable."
            )
        lines.append("")

    # ------------------------------------------------------------------
    # 7. Grade x Factor matrix
    # ------------------------------------------------------------------
    lines += ["7. GRADE x FACTOR MATRIX", HSEP]
    factor_labels = {
        "suit_8plus":  "Suit>=8",
        "form_20plus": "Form>=20",
        "class_1_3":   "Class1-3",
        "train_5plus": "Train>=5",
    }

    if not grade_matrix:
        lines += ["  No data.", ""]
    else:
        header_cells = ["Grade", "BaseWR%"] + [factor_labels.get(k, k) for k in factor_labels]
        lines.append("  " + "  ".join(f"{h:>10}" for h in header_cells))
        lines.append("  " + "-" * (len(header_cells) * 12))
        for grade, cells in grade_matrix.items():
            base = cells.get("_total", {})
            row_cells = [grade, f"{base.get('win_rate', 0.0):.1f}"]
            for fname in factor_labels:
                cell = cells.get(fname, {})
                wr   = cell.get("win_rate")
                n    = cell.get("n", 0)
                if wr is None:
                    row_cells.append(f"<{MIN_SAMPLES}samp")
                else:
                    row_cells.append(f"{wr:.1f}%({n})")
            lines.append("  " + "  ".join(f"{c:>10}" for c in row_cells))
        lines.append("")

    # ------------------------------------------------------------------
    # 8. Time-trend analysis
    # ------------------------------------------------------------------
    lines += ["8. TIME-TREND ANALYSIS", HSEP]

    if not trend:
        lines += ["  No time-series data available.", ""]
    else:
        dr = trend.get("date_range", {})
        ft = trend.get("first_third", {})
        mt = trend.get("middle_third", {})
        lt = trend.get("last_third", {})
        td = trend.get("trend_direction", "UNKNOWN")
        imp= trend.get("improvement_pts", 0.0)
        lines += [
            f"  Period: {dr.get('start','?')}  to  {dr.get('end','?')}",
            f"  Trend direction: {td}  (first third {ft.get('win_rate','?')}% → "
            f"last third {lt.get('win_rate','?')}%,  {imp:+.1f} pts)",
            "",
            f"  {'Period':<14} {'N':>5} {'Wins':>5} {'WR%':>7} {'P/L':>8} {'ROI%':>7}",
            "  " + "-" * 48,
            f"  {'First third':<14} {ft.get('n',0):>5} {ft.get('wins',0):>5} "
            f"{ft.get('win_rate',0.0):>7.1f} {ft.get('pl',0.0):>+8.2f} {ft.get('roi',0.0):>+7.1f}",
            f"  {'Middle third':<14} {mt.get('n',0):>5} {mt.get('wins',0):>5} "
            f"{mt.get('win_rate',0.0):>7.1f} {mt.get('pl',0.0):>+8.2f} {mt.get('roi',0.0):>+7.1f}",
            f"  {'Last third':<14} {lt.get('n',0):>5} {lt.get('wins',0):>5} "
            f"{lt.get('win_rate',0.0):>7.1f} {lt.get('pl',0.0):>+8.2f} {lt.get('roi',0.0):>+7.1f}",
            "",
        ]
        monthly = trend.get("monthly", [])
        if monthly:
            lines.append(f"  MONTHLY BREAKDOWN:")
            lines.append(f"  {'Month':<10} {'N':>5} {'Wins':>5} {'WR%':>7} {'ROI%':>7}")
            lines.append("  " + "-" * 40)
            for m in monthly:
                lines.append(
                    f"  {m['month']:<10} {m['n']:>5} {m['wins']:>5} "
                    f"{m['win_rate']:>7.1f} {m['roi']:>+7.1f}"
                )
            lines.append("")
        bm = trend.get("best_month")
        wm = trend.get("worst_month")
        if bm:
            lines.append(f"  Best month:  {bm['month']}  —  {bm['win_rate']}% win rate, ROI {bm['roi']:+.1f}%")
        if wm:
            lines.append(f"  Worst month: {wm['month']}  —  {wm['win_rate']}% win rate, ROI {wm['roi']:+.1f}%")
        lines.append("")

    # ------------------------------------------------------------------
    # 9. Decision tree / Race card
    # ------------------------------------------------------------------
    lines += ["9. RACE CARD — DECISION TREE", HSEP]
    for rule_line in decision_tree:
        lines.append(f"  {rule_line}")
    lines.append("")

    lines.append(SEP)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Console summary (golden rules + danger patterns)
# ---------------------------------------------------------------------------

def print_console_summary(
    top_combos: list[dict],
    loser_analysis: dict,
    trend: dict,
    overall_wr: float,
) -> None:
    print("\n" + "=" * 60)
    print("  WINNER DNA — TOP FINDINGS")
    print("=" * 60)

    print(f"\n  Overall NAP win rate: {overall_wr:.1f}%\n")

    print("  TOP 5 GOLDEN RULES (factor combos with highest win rate):")
    if top_combos:
        for i, combo in enumerate(top_combos[:5], 1):
            print(f"    {i}. {combo['combo']}")
            print(f"       {combo['win_rate']}% win rate  (n={combo['n']}, "
                  f"ROI {combo['roi']:+.1f}%, lift {combo['lift']:+.1f} over baseline)")
    else:
        print(f"    Insufficient data (need {MIN_SAMPLES}+ samples per combination).")

    print("\n  TOP 3 DANGER PATTERNS (most common loss categories):")
    lb = loser_analysis.get("breakdown", {})
    danger_items = list(lb.items())[:3]
    if danger_items:
        for i, (cat, stats) in enumerate(danger_items, 1):
            print(f"    {i}. [{cat}] — {stats['count']} losses ({stats['pct']}%)")
    else:
        print("    No loss data available.")

    td = trend.get("trend_direction", "UNKNOWN")
    imp = trend.get("improvement_pts", 0.0)
    print(f"\n  MODEL TREND: {td}  ({imp:+.1f} win-rate pts first→last third)")
    print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# Build JSON output
# ---------------------------------------------------------------------------

def build_json_output(
    date_str: str,
    csv_path: Optional[Path],
    records: list[dict],
    winner_profile: dict,
    loser_profile: dict,
    profile_comparison: list[dict],
    reason_freq: dict,
    top_combos: list[dict],
    loser_analysis: dict,
    near_miss: dict,
    optimal: dict,
    grade_matrix: dict,
    trend: dict,
) -> dict:
    return {
        "generated_at":      datetime.now().isoformat(),
        "analysis_date":     date_str,
        "source_csv":        str(csv_path) if csv_path else None,
        "total_records":     len(records),
        "records_with_result": sum(1 for r in records if r.get("has_result")),
        "winner_count":      winner_profile.get("count", 0),
        "loser_count":       loser_profile.get("count", 0),
        "winner_profile":    winner_profile,
        "loser_profile":     loser_profile,
        "profile_comparison": profile_comparison,
        "reason_frequency":  reason_freq,
        "top_combos":        top_combos[:20],
        "loser_analysis":    loser_analysis,
        "near_miss":         near_miss,
        "optimal_criteria":  optimal,
        "grade_factor_matrix": grade_matrix,
        "time_trend":        trend,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Winner DNA — reverse-engineer what winning NAPs share."
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Path to backtest CSV.  If omitted, uses latest data/backtest_*.csv",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=date.today().isoformat(),
        help="Date label for output files (YYYY-MM-DD, default today)",
    )
    args = parser.parse_args()

    date_str = args.date
    print(f"winner_dna_analysis: date={date_str}")

    # --- Resolve CSV ---------------------------------------------------------
    csv_path: Optional[Path] = Path(args.csv) if args.csv else None
    if csv_path is None:
        csv_path = _find_latest_backtest_csv()

    if csv_path is None:
        print("winner_dna_analysis: no backtest CSV found — producing empty-structure report.")
    else:
        print(f"winner_dna_analysis: loading CSV: {csv_path}")

    records = load_backtest_csv(csv_path)
    print(f"winner_dna_analysis: loaded {len(records)} records "
          f"({sum(1 for r in records if r.get('has_result'))} with result)")

    # --- Run all analysis sections ------------------------------------------
    print("winner_dna_analysis: building winner/loser profiles...")
    winner_profile, loser_profile = build_profiles(records)

    profile_comparison = compare_profiles(winner_profile, loser_profile)

    print("winner_dna_analysis: mining reason frequencies...")
    reason_freq = mine_reason_frequencies(records)

    print("winner_dna_analysis: computing 2-factor combinations...")
    all_combos  = find_two_factor_combos(records)
    top_combos  = all_combos[:10]

    print("winner_dna_analysis: classifying losses...")
    loser_analysis = analyse_losses(records)

    print("winner_dna_analysis: near-miss analysis...")
    near_miss = near_miss_analysis(records)

    print("winner_dna_analysis: deriving optimal criteria...")
    optimal = derive_optimal_criteria(records, top_combos)

    print("winner_dna_analysis: building grade-factor matrix...")
    grade_matrix = grade_factor_matrix(records)

    print("winner_dna_analysis: time-trend analysis...")
    trend = time_trend_analysis(records)

    print("winner_dna_analysis: building decision tree...")
    decision_tree = build_decision_tree(optimal, all_combos, loser_analysis, trend)

    # --- Format outputs ------------------------------------------------------
    report_text = format_report(
        date_str     = date_str,
        csv_path     = csv_path,
        records      = records,
        winner_profile     = winner_profile,
        loser_profile      = loser_profile,
        profile_comparison = profile_comparison,
        reason_freq        = reason_freq,
        top_combos         = top_combos,
        loser_analysis     = loser_analysis,
        near_miss          = near_miss,
        optimal            = optimal,
        grade_matrix       = grade_matrix,
        trend              = trend,
        decision_tree      = decision_tree,
    )

    json_data = build_json_output(
        date_str           = date_str,
        csv_path           = csv_path,
        records            = records,
        winner_profile     = winner_profile,
        loser_profile      = loser_profile,
        profile_comparison = profile_comparison,
        reason_freq        = reason_freq,
        top_combos         = all_combos[:20],
        loser_analysis     = loser_analysis,
        near_miss          = near_miss,
        optimal            = optimal,
        grade_matrix       = grade_matrix,
        trend              = trend,
    )

    # --- Write outputs -------------------------------------------------------
    report_dest = _reports_dir() / f"winner_dna_{date_str}.txt"
    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
    except OSError as exc:
        print(f"winner_dna_analysis: FATAL — could not write report: {exc}", file=sys.stderr)
        return 1

    json_dest = _data_dir() / f"winner_dna_{date_str}.json"
    try:
        with open(json_dest, "w", encoding="utf-8") as fh:
            json.dump(json_data, fh, indent=2, ensure_ascii=False)
    except (OSError, TypeError, ValueError) as exc:
        print(f"winner_dna_analysis: FATAL — could not write JSON: {exc}", file=sys.stderr)
        return 1

    # --- Console summary -----------------------------------------------------
    total_n = winner_profile.get("count", 0) + loser_profile.get("count", 0)
    total_w = winner_profile.get("count", 0)
    overall_wr = total_w / total_n * 100 if total_n else 0.0
    print_console_summary(all_combos, loser_analysis, trend, overall_wr)

    print(f"winner_dna_analysis: COMPLETE")
    print(f"  Report: {report_dest}")
    print(f"  JSON:   {json_dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
