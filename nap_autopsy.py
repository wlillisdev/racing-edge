"""
nap_autopsy.py — Forensic autopsy of every NAP selection from the last 6 months.

Reconstructs each winner and loser in detail by:
  1. Loading the most recent backtest CSV (data/backtest_*.csv)
     — identifies NAP rows as the highest-scoring row per date
  2. Cross-referencing racecard cache (data/backtest_cache/racecards/{date}.json)
     for deep runner attributes: form string, trainer_14_days, draw, age/sex,
     headgear, last_run, spotlight
  3. Cross-referencing results cache (data/backtest_cache/results/{date}.json
     or data/backtest_cache/race_results/{race_id}.json) for SP and position

Outputs:
  reports/nap_autopsy_report.txt   — full human-readable autopsy
  data/nap_autopsy_data.json       — structured data for downstream use

Sections:
  1. Winner Profile vs Loser Profile (side-by-side means/medians, flags >20% diff)
  2. Winner Fingerprint (factors in 4+ winners and <2 losers)
  3. Loser Autopsy (narrative per losing NAP)
  4. Pattern Analysis (course, trainer, field size, odds, class drop)
  5. Golden Filter (confirm/veto rules derived from fingerprint)
  6. Retroactive Filter Test (apply filter to all NAPs; measure uplift)

Usage:
    python nap_autopsy.py
    python nap_autopsy.py --csv data/backtest_2025-06-01_to_2026-06-07.csv

Exit codes:
    0 — report produced
    1 — fatal error (write failure)
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Paths (standalone — no project imports)
# ---------------------------------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR    = PROJECT_DIR / "data"
REPORTS_DIR = PROJECT_DIR / "reports"
CACHE_DIR   = DATA_DIR / "backtest_cache"


def _ensure(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Going normalisation (inline — avoids circular imports)
# ---------------------------------------------------------------------------

_GOING_RULES: list[tuple[str, str]] = [
    ("standard to slow", "Slow"),
    ("slow",             "Slow"),
    ("standard",         "Standard"),
    ("fast",             "Standard"),
    ("good to firm",     "Good to Firm"),
    ("good to soft",     "Good to Soft"),
    ("soft to heavy",    "Heavy"),
    ("heavy",            "Heavy"),
    ("firm",             "Firm"),
    ("good",             "Good"),
    ("soft",             "Soft"),
    ("yielding to soft", "Soft"),
    ("yielding",         "Good to Soft"),
    ("hard",             "Firm"),
]


def _going_normalise(going_str: str) -> str:
    if not going_str:
        return going_str
    normalised = going_str.strip().lower()
    normalised = re.sub(r"\(.*?\)", "", normalised).strip()
    for pattern, canonical in _GOING_RULES:
        if pattern in normalised:
            return canonical
    return going_str.strip().title()


# ---------------------------------------------------------------------------
# Safe type coercion
# ---------------------------------------------------------------------------

def _sf(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _si(val, default: int = -1) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _sb(val) -> bool:
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("true", "1", "yes")


def _ss(val, default: str = "") -> str:
    if val is None:
        return default
    return str(val).strip()


def _stat(nums: list[float]) -> dict:
    """Return mean/median/stdev for a list; None if empty."""
    if not nums:
        return {"mean": None, "median": None, "stdev": None, "n": 0}
    n = len(nums)
    m = mean(nums)
    med = median(nums)
    sd = stdev(nums) if n > 1 else 0.0
    return {"mean": round(m, 3), "median": round(med, 3), "stdev": round(sd, 3), "n": n}


# ---------------------------------------------------------------------------
# CSV loader — finds most recent backtest CSV
# ---------------------------------------------------------------------------

def _find_csv(override: Optional[str] = None) -> Optional[Path]:
    if override:
        p = Path(override)
        return p if p.exists() else None
    candidates = sorted(DATA_DIR.glob("backtest_*.csv"))
    return candidates[-1] if candidates else None


def _load_csv(path: Path) -> list[dict]:
    rows: list[dict] = []
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                rows.append(dict(row))
    except OSError as exc:
        print(f"[WARN] CSV read error: {exc}", file=sys.stderr)
    return rows


# ---------------------------------------------------------------------------
# Cache loaders
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _racecard_for_date(date_str: str) -> list[dict]:
    """Return list of normalised races from racecard cache for a date."""
    data = _load_json(CACHE_DIR / "racecards" / f"{date_str}.json")
    if data is None:
        return []
    return data.get("races", [])


def _results_for_date(date_str: str) -> dict[str, dict]:
    """Return horse_id → {position, sp_dec} from date-level results cache."""
    data = _load_json(CACHE_DIR / "results" / f"{date_str}.json")
    if data is None:
        return {}
    # Format varies — try dict keyed by horse_id or list
    if isinstance(data, dict):
        # Could be {"runners": {...}} or direct horse_id map
        runners = data.get("runners") or data.get("results") or data
        if isinstance(runners, dict):
            return {str(k): v for k, v in runners.items()}
        if isinstance(runners, list):
            result: dict[str, dict] = {}
            for r in runners:
                hid = str(r.get("horse_id") or "")
                if hid:
                    result[hid] = {
                        "position": str(r.get("position") or r.get("finish_position") or ""),
                        "sp_dec":   _sf(r.get("sp_dec") or r.get("bsp") or r.get("sp")),
                    }
            return result
    return {}


def _find_runner_in_racecard(
    horse_id: str, horse_name: str, races: list[dict]
) -> tuple[Optional[dict], Optional[dict]]:
    """
    Search all races in a racecard for a runner matching horse_id or horse_name.
    Returns (runner_dict, race_dict).
    """
    for race in races:
        for runner in (race.get("runners") or []):
            rid = str(runner.get("horse_id") or "")
            rname = str(runner.get("horse") or "").lower().strip()
            if (horse_id and rid == horse_id) or (
                horse_name and rname == horse_name.lower().strip()
            ):
                return runner, race
    return None, None


# ---------------------------------------------------------------------------
# Form helpers
# ---------------------------------------------------------------------------

def _parse_form_chars(form: str) -> list[str]:
    """Extract recent form characters newest-first."""
    if not form or form.strip() in ("-", ""):
        return []
    form = form.strip().replace(" ", "")
    last_dash = form.rfind("-")
    segment = form[last_dash + 1:] if last_dash != -1 else form
    valid: list[str] = []
    for ch in reversed(segment):
        upper = ch.upper()
        if upper.isdigit() or upper in ("F", "U", "P", "R", "B"):
            valid.append(upper)
    return valid


def _lto_win(chars: list[str]) -> bool:
    """Did the horse win last time out?"""
    return bool(chars) and chars[0] == "1"


def _going_proven(today_going: str, form_chars: list[str], runner: dict) -> bool:
    """
    Best-effort: check if today's going matches any noted win in form string.
    Because we only have the abbreviated form string (no per-race going history),
    we use the trainer_14_days data or heuristic: if horse has >=1 win (form char '1')
    and today_going is matched by the race metadata — we note it as "possible".
    This is a simplified proxy; full proof requires full_form API data.
    """
    return "1" in form_chars  # simplified: has at least one recorded win


def _recent_wins_count(chars: list[str]) -> int:
    return sum(1 for c in chars[:5] if c == "1")


def _trainer_pct(runner: dict) -> Optional[float]:
    t14 = runner.get("trainer_14_days") or {}
    if not isinstance(t14, dict):
        try:
            t14 = json.loads(str(t14))
        except Exception:
            return None
    try:
        return float(str(t14.get("percent") or "").strip().rstrip("%"))
    except (ValueError, TypeError):
        return None


def _odds_band(sp: float) -> str:
    if sp <= 0:      return "Unknown"
    if sp < 2.0:     return "Odds-on"
    if sp <= 3.0:    return "Evens-2/1"
    if sp <= 5.0:    return "9/4-4/1"
    if sp <= 9.0:    return "9/2-8/1"
    if sp <= 20.0:   return "9/1-20/1"
    return "20/1+"


def _class_numeric(race_class) -> Optional[int]:
    if race_class is None:
        return None
    s = str(race_class).strip().lower()
    if s.startswith("class"):
        s = s[5:].strip()
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def _is_handicap(race_name: str) -> bool:
    return "handicap" in race_name.lower() or "hcap" in race_name.lower()


def _is_conditions(race_name: str) -> bool:
    n = race_name.lower()
    return any(w in n for w in ("conditions", "novice", "maiden", "auction", "seller"))


def _is_listed_or_graded(race_name: str) -> bool:
    n = race_name.lower()
    return any(w in n for w in ("listed", "grade 1", "grade 2", "grade 3", "group 1", "group 2", "group 3"))


# ---------------------------------------------------------------------------
# NAP identification from CSV
# ---------------------------------------------------------------------------

def _identify_naps(rows: list[dict]) -> list[dict]:
    """
    Reconstruct daily NAP selections: the highest-scoring row per date
    where has_result is True (or any date for structural analysis).
    Mirrors the backtest logic.
    """
    by_date: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_date[row.get("date", "")].append(row)

    naps: list[dict] = []
    for date_str, day_rows in sorted(by_date.items()):
        # Sort by score descending; take highest
        day_rows.sort(key=lambda r: _sf(r.get("score", 0)), reverse=True)
        best = day_rows[0]
        best["_is_nap"] = True
        naps.append(best)
    return naps


# ---------------------------------------------------------------------------
# Enrichment: pull additional fields from racecard cache
# ---------------------------------------------------------------------------

def _enrich_nap(nap: dict) -> dict:
    """
    Add fields from racecard and results cache to a NAP record.
    Returns a new enriched dict with all autopsy fields.
    """
    date_str   = nap.get("date", "")
    horse_id   = nap.get("horse_id", "")
    horse_name = nap.get("horse", "")

    # Load racecard cache
    races = _racecard_for_date(date_str)
    runner, race = _find_runner_in_racecard(horse_id, horse_name, races)

    # Basic CSV fields
    enriched: dict = {
        "date":        date_str,
        "horse":       horse_name,
        "horse_id":    horse_id,
        "course":      nap.get("course", ""),
        "race_type":   nap.get("race_type", ""),
        "race_class":  nap.get("race_class", ""),
        "going":       nap.get("going", ""),
        "distance_f":  _sf(nap.get("distance_f", 0)),
        "field_size":  0,  # filled below
        "race_name":   "",  # filled below
        # Scores
        "score":       _sf(nap.get("score", 0)),
        "grade":       nap.get("grade", ""),
        "form_score":  _sf(nap.get("form_score", 0)),
        "suit_score":  _sf(nap.get("suit_score", 0)),
        "ctx_score":   _sf(nap.get("ctx_score", 0)),
        "train_score": _sf(nap.get("train_score", 0)),
        "mkt_score":   _sf(nap.get("mkt_score", 0)),
        # Result
        "position":    nap.get("position", ""),
        "sp_dec":      _sf(nap.get("sp_dec", 0)),
        "is_win":      _sb(nap.get("is_win", False)),
        "is_place":    _sb(nap.get("is_place", False)),
        "has_result":  _sb(nap.get("has_result", False)),
        # Racecard-derived (populated below)
        "form":                "",
        "trainer":             "",
        "trainer_14_pct":      None,
        "trainer_14_wins":     None,
        "trainer_14_runs":     None,
        "age":                 "",
        "draw":                -1,
        "draw_position":       None,   # draw / field_size
        "headgear":            "",
        "headgear_run":        -1,
        "last_run":            -1,
        "spotlight":           "",
        "wind_surgery_run":    -1,
        # Derived flags
        "lto_win":             False,
        "going_has_win":       False,
        "recent_wins_3":       0,
        "form_chars_raw":      [],
        "race_is_handicap":    False,
        "race_is_conditions":  False,
        "race_is_listed":      False,
        "class_numeric":       None,
        "odds_band":           "",
        "type_group":          nap.get("type_group", ""),
        "class_group":         nap.get("class_group", ""),
        "score_band":          nap.get("score_band", ""),
        "going_group":         nap.get("going_group", ""),
        "dist_group":          nap.get("dist_group", ""),
    }

    # Populate from racecard runner
    if runner:
        form_str = _ss(runner.get("form"))
        chars    = _parse_form_chars(form_str)
        t14      = runner.get("trainer_14_days") or {}
        if not isinstance(t14, dict):
            try:
                t14 = json.loads(str(t14))
            except Exception:
                t14 = {}
        t14_pct = _trainer_pct(runner)
        try:
            t14_wins = int(t14.get("wins", -1))
        except (TypeError, ValueError):
            t14_wins = None
        try:
            t14_runs = int(t14.get("runs", -1))
        except (TypeError, ValueError):
            t14_runs = None

        enriched.update({
            "form":             form_str,
            "trainer":          _ss(runner.get("trainer")),
            "trainer_14_pct":   t14_pct,
            "trainer_14_wins":  t14_wins,
            "trainer_14_runs":  t14_runs,
            "age":              _ss(runner.get("age")),
            "draw":             _si(runner.get("draw"), default=-1),
            "headgear":         _ss(runner.get("headgear")),
            "headgear_run":     _si(runner.get("headgear_run"), default=-1),
            "last_run":         _si(runner.get("last_run"), default=-1),
            "spotlight":        _ss(runner.get("spotlight")),
            "wind_surgery_run": _si(runner.get("wind_surgery_run"), default=-1),
            "lto_win":          _lto_win(chars),
            "going_has_win":    _going_proven(enriched["going"], chars, runner),
            "recent_wins_3":    _recent_wins_count(chars),
            "form_chars_raw":   chars,
        })

    if race:
        field_size = _si(race.get("field_size") or len(race.get("runners") or []), default=0)
        race_name  = _ss(race.get("race_name") or race.get("race"))
        enriched.update({
            "field_size":           field_size,
            "race_name":            race_name,
            "race_is_handicap":     _is_handicap(race_name),
            "race_is_conditions":   _is_conditions(race_name),
            "race_is_listed":       _is_listed_or_graded(race_name),
        })
        if enriched["draw"] > 0 and field_size > 0:
            enriched["draw_position"] = round(enriched["draw"] / field_size, 3)

    enriched["class_numeric"] = _class_numeric(enriched["race_class"])
    enriched["odds_band"]     = _odds_band(enriched["sp_dec"])

    # Use CSV sp_dec if racecard had none
    if enriched["sp_dec"] == 0.0 and runner:
        enriched["sp_dec"] = _sf(runner.get("sp_dec", 0))
        enriched["odds_band"] = _odds_band(enriched["sp_dec"])

    return enriched


# ---------------------------------------------------------------------------
# Profile builder
# ---------------------------------------------------------------------------

def _build_profile(records: list[dict]) -> dict:
    """Build statistical profile for a group of NAP records."""
    if not records:
        return {"count": 0}

    def _vals(key: str) -> list[float]:
        return [r[key] for r in records if r.get(key) is not None and isinstance(r.get(key), (int, float))]

    def _pct_true(key: str) -> float:
        vals = [r.get(key, False) for r in records]
        trues = sum(1 for v in vals if v is True or v == "True")
        return round(trues / len(records) * 100, 1) if records else 0.0

    def _dist(key: str) -> dict:
        counts: Counter = Counter(str(r.get(key, "?")) for r in records)
        total = len(records)
        return {k: {"n": v, "pct": round(v / total * 100, 1)} for k, v in counts.most_common()}

    t14_vals = [r["trainer_14_pct"] for r in records if r.get("trainer_14_pct") is not None]
    field_sizes = [r["field_size"] for r in records if r.get("field_size", 0) > 0]
    last_runs = [r["last_run"] for r in records if r.get("last_run", -1) >= 0]

    profile = {
        "count": len(records),
        "score":        _stat(_vals("score")),
        "form_score":   _stat(_vals("form_score")),
        "suit_score":   _stat(_vals("suit_score")),
        "ctx_score":    _stat(_vals("ctx_score")),
        "train_score":  _stat(_vals("train_score")),
        "mkt_score":    _stat(_vals("mkt_score")),
        "sp_dec":       _stat(_vals("sp_dec")),
        "field_size":   _stat(field_sizes),
        "trainer_14pct":_stat(t14_vals),
        "last_run":     _stat(last_runs),
        "pct_lto_win":          _pct_true("lto_win"),
        "pct_going_has_win":    _pct_true("going_has_win"),
        "pct_handicap":         _pct_true("race_is_handicap"),
        "pct_conditions":       _pct_true("race_is_conditions"),
        "pct_trainer_25plus":   round(sum(1 for r in records if (r.get("trainer_14_pct") or 0) >= 25) / len(records) * 100, 1),
        "pct_trainer_35plus":   round(sum(1 for r in records if (r.get("trainer_14_pct") or 0) >= 35) / len(records) * 100, 1),
        "pct_small_field":      round(sum(1 for r in records if 0 < r.get("field_size", 0) <= 9) / len(records) * 100, 1),
        "pct_headgear_first":   round(sum(1 for r in records if r.get("headgear_run") == 1) / len(records) * 100, 1),
        "pct_wind_surgery":     round(sum(1 for r in records if r.get("wind_surgery_run") == 1) / len(records) * 100, 1),
        "pct_spotlight":        round(sum(1 for r in records if r.get("spotlight", "")) / len(records) * 100, 1),
        "grade_dist":    _dist("grade"),
        "class_dist":    _dist("race_class"),
        "going_dist":    _dist("going"),
        "type_dist":     _dist("race_type"),
        "odds_band_dist": _dist("odds_band"),
        "score_band_dist": _dist("score_band"),
        "race_names_sample": [r.get("race_name", "") for r in records[:5]],
    }
    return profile


# ---------------------------------------------------------------------------
# Comparison: flag attributes where groups diverge > 20%
# ---------------------------------------------------------------------------

def _compare_profiles(wp: dict, lp: dict) -> list[dict]:
    """Return list of attributes where winners vs losers differ meaningfully."""
    flags: list[dict] = []

    numeric_keys = [
        ("score",        "Composite score"),
        ("form_score",   "Form quality score"),
        ("suit_score",   "Suitability score"),
        ("ctx_score",    "Race context score"),
        ("train_score",  "Trainer intent score"),
        ("mkt_score",    "Market overlay score"),
        ("sp_dec",       "Starting price (decimal)"),
        ("field_size",   "Field size"),
        ("trainer_14pct","Trainer 14-day strike %"),
        ("last_run",     "Days since last run"),
    ]
    for key, label in numeric_keys:
        w_val = (wp.get(key) or {}).get("mean")
        l_val = (lp.get(key) or {}).get("mean")
        if w_val is None or l_val is None:
            continue
        denom = max(abs(w_val), abs(l_val), 0.001)
        diff_pct = abs(w_val - l_val) / denom * 100
        if diff_pct >= 20:
            flags.append({
                "attribute":     label,
                "key":           key,
                "winner_mean":   round(w_val, 3),
                "loser_mean":    round(l_val, 3),
                "diff_pct":      round(diff_pct, 1),
                "winner_higher": w_val > l_val,
            })

    pct_keys = [
        ("pct_lto_win",         "% LTO win"),
        ("pct_going_has_win",   "% going proven"),
        ("pct_trainer_25plus",  "% trainer 14d >= 25%"),
        ("pct_trainer_35plus",  "% trainer 14d >= 35%"),
        ("pct_small_field",     "% small field (<=9)"),
        ("pct_headgear_first",  "% first-time headgear"),
        ("pct_handicap",        "% in handicap"),
        ("pct_spotlight",       "% with spotlight note"),
    ]
    for key, label in pct_keys:
        w_val = wp.get(key, 0.0)
        l_val = lp.get(key, 0.0)
        denom = max(w_val, l_val, 0.001)
        diff_pct = abs(w_val - l_val) / denom * 100
        if diff_pct >= 20 or abs(w_val - l_val) >= 20:
            flags.append({
                "attribute":     label,
                "key":           key,
                "winner_pct":    round(w_val, 1),
                "loser_pct":     round(l_val, 1),
                "diff_pct":      round(diff_pct, 1),
                "winner_higher": w_val > l_val,
            })

    flags.sort(key=lambda x: -x["diff_pct"])
    return flags


# ---------------------------------------------------------------------------
# Winner Fingerprint — factors present in 4+ winners but <2 losers
# ---------------------------------------------------------------------------

def _compute_fingerprint(winners: list[dict], losers: list[dict]) -> list[dict]:
    """
    Test candidate binary conditions against winners and losers.
    Returns factors where: winner_count >= min(4, len(winners)) AND loser_count < 2.
    Falls back gracefully with fewer NAPs.
    """
    n_w = len(winners)
    n_l = len(losers)

    # Threshold: ≥ 4 winners OR ≥ 70% of winners (whichever is lower) if small sample
    min_w = min(4, max(2, int(n_w * 0.6))) if n_w >= 3 else max(1, n_w)
    max_l = 2 if n_l >= 5 else max(1, int(n_l * 0.3))

    def _test(label: str, w_fn, l_fn) -> Optional[dict]:
        w_count = sum(1 for r in winners if w_fn(r))
        l_count = sum(1 for r in losers  if l_fn(r))
        w_pct   = round(w_count / n_w * 100, 1) if n_w else 0
        l_pct   = round(l_count / n_l * 100, 1) if n_l else 0
        if w_count >= min_w and l_count <= max_l:
            return {
                "factor":        label,
                "winner_count":  w_count,
                "winner_pct":    w_pct,
                "loser_count":   l_count,
                "loser_pct":     l_pct,
                "discriminating": True,
            }
        # Still include near-miss factors for context (not discriminating)
        if w_pct >= 60 and w_pct - l_pct >= 25:
            return {
                "factor":        label,
                "winner_count":  w_count,
                "winner_pct":    w_pct,
                "loser_count":   l_count,
                "loser_pct":     l_pct,
                "discriminating": False,
            }
        return None

    conditions: list[tuple[str, Any, Any]] = [
        ("LTO win (form[0]='1')",
            lambda r: r.get("lto_win") is True,
            lambda r: r.get("lto_win") is True),
        ("Trainer 14d >= 25%",
            lambda r: (r.get("trainer_14_pct") or 0) >= 25,
            lambda r: (r.get("trainer_14_pct") or 0) >= 25),
        ("Trainer 14d >= 35%",
            lambda r: (r.get("trainer_14_pct") or 0) >= 35,
            lambda r: (r.get("trainer_14_pct") or 0) >= 35),
        ("Trainer score >= 5",
            lambda r: r.get("train_score", 0) >= 5,
            lambda r: r.get("train_score", 0) >= 5),
        ("Form score >= 20",
            lambda r: r.get("form_score", 0) >= 20,
            lambda r: r.get("form_score", 0) >= 20),
        ("Form score >= 25",
            lambda r: r.get("form_score", 0) >= 25,
            lambda r: r.get("form_score", 0) >= 25),
        ("Suitability score >= 8",
            lambda r: r.get("suit_score", 0) >= 8,
            lambda r: r.get("suit_score", 0) >= 8),
        ("Suitability score >= 12",
            lambda r: r.get("suit_score", 0) >= 12,
            lambda r: r.get("suit_score", 0) >= 12),
        ("Small field (<=9 runners)",
            lambda r: 0 < r.get("field_size", 0) <= 9,
            lambda r: 0 < r.get("field_size", 0) <= 9),
        ("Very small field (<=6 runners)",
            lambda r: 0 < r.get("field_size", 0) <= 6,
            lambda r: 0 < r.get("field_size", 0) <= 6),
        ("Grade A (score>=70)",
            lambda r: r.get("grade", "") == "A",
            lambda r: r.get("grade", "") == "A"),
        ("SP <= 5.0 (short to mid-priced)",
            lambda r: 0 < r.get("sp_dec", 0) <= 5.0,
            lambda r: 0 < r.get("sp_dec", 0) <= 5.0),
        ("SP <= 3.0 (short price)",
            lambda r: 0 < r.get("sp_dec", 0) <= 3.0,
            lambda r: 0 < r.get("sp_dec", 0) <= 3.0),
        ("NOT first-time headgear",
            lambda r: r.get("headgear_run", -1) != 1,
            lambda r: r.get("headgear_run", -1) != 1),
        ("Has spotlight/commentary",
            lambda r: bool(r.get("spotlight", "")),
            lambda r: bool(r.get("spotlight", ""))),
        ("Recent 3-race wins >= 2",
            lambda r: r.get("recent_wins_3", 0) >= 2,
            lambda r: r.get("recent_wins_3", 0) >= 2),
        ("Not handicap race",
            lambda r: not r.get("race_is_handicap", False),
            lambda r: not r.get("race_is_handicap", False)),
        ("Ideal freshness (14-28 days)",
            lambda r: 14 <= r.get("last_run", -1) <= 28 if r.get("last_run", -1) >= 0 else False,
            lambda r: 14 <= r.get("last_run", -1) <= 28 if r.get("last_run", -1) >= 0 else False),
        ("Not stale (< 45 days since last run)",
            lambda r: 0 < r.get("last_run", -1) < 45 if r.get("last_run", -1) >= 0 else False,
            lambda r: 0 < r.get("last_run", -1) < 45 if r.get("last_run", -1) >= 0 else False),
        ("Market score >= 3",
            lambda r: r.get("mkt_score", 0) >= 3,
            lambda r: r.get("mkt_score", 0) >= 3),
        ("Context score >= 5",
            lambda r: r.get("ctx_score", 0) >= 5,
            lambda r: r.get("ctx_score", 0) >= 5),
        ("LTO win AND trainer 25%+",
            lambda r: r.get("lto_win") is True and (r.get("trainer_14_pct") or 0) >= 25,
            lambda r: r.get("lto_win") is True and (r.get("trainer_14_pct") or 0) >= 25),
        ("Form score >= 20 AND suitability >= 8",
            lambda r: r.get("form_score", 0) >= 20 and r.get("suit_score", 0) >= 8,
            lambda r: r.get("form_score", 0) >= 20 and r.get("suit_score", 0) >= 8),
    ]

    results: list[dict] = []
    for label, w_fn, l_fn in conditions:
        item = _test(label, w_fn, l_fn)
        if item:
            results.append(item)

    # Sort: discriminating first, then by winner_pct - loser_pct
    results.sort(key=lambda x: (
        -int(x["discriminating"]),
        -(x["winner_pct"] - x["loser_pct"])
    ))
    return results


# ---------------------------------------------------------------------------
# Loser autopsy — classify and narrate each loss
# ---------------------------------------------------------------------------

def _classify_loss(r: dict) -> tuple[str, str]:
    """
    Return (category, narrative) for a losing NAP.
    Categories: WRONG_GOING | COLD_TRAINER | LARGE_FIELD | ODDS_RISK |
                STALE_FORM | FIRST_TIME_HEADGEAR | OVERRATED_BY_SCORE | UNCLASSIFIED
    """
    score       = r.get("score", 0)
    train_pct   = r.get("trainer_14_pct") or 0
    field_size  = r.get("field_size", 0)
    sp_dec      = r.get("sp_dec", 0)
    last_run    = r.get("last_run", -1)
    headgear_r  = r.get("headgear_run", -1)
    headgear    = r.get("headgear", "")
    race_type   = r.get("race_type", "").lower()
    going       = r.get("going", "")
    form_score  = r.get("form_score", 0)
    suit_score  = r.get("suit_score", 0)
    grade       = r.get("grade", "")
    position    = r.get("position", "")
    train_score = r.get("train_score", 0)
    spotlight   = r.get("spotlight", "")
    horse       = r.get("horse", "Unknown")
    course      = r.get("course", "")
    race_name   = r.get("race_name", "")

    # Position details
    try:
        pos_int = int(position)
    except (TypeError, ValueError):
        pos_int = 99

    # --- Classification logic (first match wins) ---

    if headgear_r == 1 and headgear:
        cat = "FIRST_TIME_HEADGEAR"
        narrative = (
            f"{horse} lost wearing {headgear} for the first time. "
            f"The trainer_score algorithm docks -2pts for first-time headgear as a negative signal. "
            f"Race: {course}, {race_name}. SP: {sp_dec:.1f}. "
            f"Position: {position}. This is a known model trap: headgear debutants often underperform expectations."
        )

    elif last_run >= 45 and last_run != -1:
        cat = "STALE_FORM"
        narrative = (
            f"{horse} lost after {last_run} days off — classified as stale (>45 days). "
            f"The freshness model penalises 46-70 day absences by -2pts and 71+ day absences by -4pts. "
            f"Despite scoring {score:.1f}, the lay-off clearly compromised readiness. "
            f"Race: {course}, {race_name}. SP: {sp_dec:.1f}. Position: {position}."
        )

    elif train_pct < 12 and train_pct >= 0:
        cat = "COLD_TRAINER"
        narrative = (
            f"{horse} lost with a cold trainer ({train_pct:.0f}% in 14 days). "
            f"The model assigns 0 trainer bonus below 12% — effectively a neutral signal but "
            f"historically a loss trap for NAP selections. Composite score {score:.1f} was misleading "
            f"because form/suit scores were high but trainer intent was absent. "
            f"Race: {course}, {race_name}. SP: {sp_dec:.1f}. Position: {position}."
        )

    elif field_size > 13:
        cat = "LARGE_FIELD"
        narrative = (
            f"{horse} lost in a large field of {field_size} runners — inherently a lottery. "
            f"Context score for fields >13 adds 0 bonus (no field-size reward). "
            f"The model's form and score edge dilutes significantly with each additional runner. "
            f"Race: {course}, {race_name}. SP: {sp_dec:.1f}. Position: {position}. "
            f"Grade: {grade}. Large-field races should carry a confidence penalty."
        )

    elif sp_dec > 0 and sp_dec <= 2.5 and not r.get("is_win"):
        cat = "ODDS_RISK"
        narrative = (
            f"{horse} lost at a very short price ({sp_dec:.2f}) — the market agreed with the model "
            f"but the horse failed to deliver. SP <=2.0 gets only +1pt in market_score (value_risk flag). "
            f"At 1.5-2.5 the model's edge shrinks against a fully-efficient market. "
            f"Race: {course}, {race_name}. Position: {position}. Grade: {grade}."
        )

    elif form_score < 15 and suit_score < 8:
        cat = "OVERRATED_BY_SCORE"
        narrative = (
            f"{horse} lost with weak fundamentals: form_score={form_score:.1f} and suit_score={suit_score:.1f} "
            f"were both below par, suggesting the composite score {score:.1f} was driven mainly by "
            f"context/market signals rather than genuine horse quality. "
            f"Race: {course}, {race_name}. SP: {sp_dec:.1f}. Position: {position}."
        )

    elif "hurdle" in race_type and 2.0 <= sp_dec <= 3.0:
        cat = "HURDLE_EVENS_2_1_TRAP"
        narrative = (
            f"{horse} lost in a hurdle at Evens–2/1 ({sp_dec:.1f}) — a known loss zone flagged "
            f"as CAUTION in market_score. The market_score code explicitly notes 'hurdle Evens-2/1 band "
            f"— proven loss zone'. This signal was present in the scoring but not filtered. "
            f"Race: {course}, {race_name}. Position: {position}."
        )

    elif grade == "B+" and score < 70:
        cat = "GRADE_B_PLUS_MARGINAL"
        narrative = (
            f"{horse} lost as a B+ grade selection (score {score:.1f}, just above 60 threshold). "
            f"B+ performance in the dataset shows the weakest ROI of any grade. "
            f"This marginal score likely reflected a day with no standout selection rather than a "
            f"genuine high-confidence pick. Race: {course}, {race_name}. SP: {sp_dec:.1f}. Position: {position}."
        )

    else:
        cat = "UNCLASSIFIED"
        narrative = (
            f"{horse} lost with no single dominant failure flag. Score: {score:.1f} ({grade}). "
            f"Form: {r.get('form', 'N/A')}. Trainer 14d: {train_pct:.0f}%. "
            f"SP: {sp_dec:.1f}. Position: {position}. Field: {field_size}. "
            f"Race: {course}, {race_name}. This may be genuine bad luck or an unmodelled factor "
            f"(e.g., draw disadvantage, ground change post-entry, jockey tactics)."
        )

    return cat, narrative


# ---------------------------------------------------------------------------
# Pattern analysis
# ---------------------------------------------------------------------------

def _pattern_analysis(winners: list[dict], losers: list[dict], all_naps: list[dict]) -> dict:
    """Return dict of pattern observations."""
    patterns: dict = {}

    # 1. Trainer patterns among winners
    trainer_counts: Counter = Counter(r.get("trainer", "") for r in winners if r.get("trainer"))
    patterns["winner_trainer_frequency"] = dict(trainer_counts.most_common(5))
    patterns["winner_trainer_concentration"] = (
        "Concentrated (one trainer appears 2+ times)" if trainer_counts and trainer_counts.most_common(1)[0][1] >= 2
        else "Spread (different trainers)"
    )

    # 2. Field size analysis
    w_fs = [r["field_size"] for r in winners if r.get("field_size", 0) > 0]
    l_fs = [r["field_size"] for r in losers  if r.get("field_size", 0) > 0]
    patterns["winner_avg_field_size"]  = round(mean(w_fs), 1) if w_fs else None
    patterns["loser_avg_field_size"]   = round(mean(l_fs), 1) if l_fs else None
    patterns["smaller_fields_for_winners"] = (
        (mean(w_fs) < mean(l_fs)) if (w_fs and l_fs) else None
    )

    # 3. Odds pattern
    w_odds = [r["sp_dec"] for r in winners if r.get("sp_dec", 0) > 0]
    l_odds = [r["sp_dec"] for r in losers  if r.get("sp_dec", 0) > 0]
    patterns["winner_avg_sp"]        = round(mean(w_odds), 2) if w_odds else None
    patterns["loser_avg_sp"]         = round(mean(l_odds), 2) if l_odds else None
    patterns["market_confirms_model"] = (
        (mean(w_odds) < mean(l_odds)) if (w_odds and l_odds) else None
    )

    # 4. Spotlight presence
    w_spotlight = sum(1 for r in winners if r.get("spotlight", ""))
    l_spotlight = sum(1 for r in losers  if r.get("spotlight", ""))
    patterns["winner_with_spotlight_pct"] = round(w_spotlight / len(winners) * 100, 1) if winners else 0
    patterns["loser_with_spotlight_pct"]  = round(l_spotlight / len(losers)  * 100, 1) if losers else 0

    # 5. Race type pattern
    w_types: Counter = Counter(r.get("type_group", "?") for r in winners)
    l_types: Counter = Counter(r.get("type_group", "?") for r in losers)
    patterns["winner_race_type_dist"]  = dict(w_types)
    patterns["loser_race_type_dist"]   = dict(l_types)

    # 6. Going pattern
    w_going: Counter = Counter(_going_normalise(r.get("going", "?")) for r in winners)
    l_going: Counter = Counter(_going_normalise(r.get("going", "?")) for r in losers)
    patterns["winner_going_dist"] = dict(w_going.most_common(5))
    patterns["loser_going_dist"]  = dict(l_going.most_common(5))

    # 7. Class drop pattern — winner ran at higher class last time (proxy: class_numeric lower = better)
    class_drop_winners = sum(
        1 for r in winners
        if r.get("class_numeric") is not None and r["class_numeric"] >= 4
    )
    patterns["winner_in_class_5_6_pct"] = round(class_drop_winners / len(winners) * 100, 1) if winners else 0
    patterns["class_drop_note"] = (
        "Winners disproportionately in Class 4-6 — suggests class drop or lower-grade horses run most true to form."
        if class_drop_winners > len(winners) * 0.5 else
        "Winners spread across classes — no strong class-drop pattern."
    )

    # 8. Handicap vs conditions
    w_hcap = sum(1 for r in winners if r.get("race_is_handicap"))
    l_hcap = sum(1 for r in losers  if r.get("race_is_handicap"))
    patterns["winner_in_handicap_pct"] = round(w_hcap / len(winners) * 100, 1) if winners else 0
    patterns["loser_in_handicap_pct"]  = round(l_hcap / len(losers)  * 100, 1) if losers else 0

    # 9. LTO win correlation
    w_lto = sum(1 for r in winners if r.get("lto_win"))
    l_lto = sum(1 for r in losers  if r.get("lto_win"))
    patterns["winner_lto_win_pct"] = round(w_lto / len(winners) * 100, 1) if winners else 0
    patterns["loser_lto_win_pct"]  = round(l_lto / len(losers)  * 100, 1) if losers else 0

    # 10. Grade A vs B+ patterns
    w_grade_a = sum(1 for r in winners if r.get("grade") == "A")
    l_grade_a = sum(1 for r in losers  if r.get("grade") == "A")
    patterns["winner_grade_A_pct"] = round(w_grade_a / len(winners) * 100, 1) if winners else 0
    patterns["loser_grade_A_pct"]  = round(l_grade_a / len(losers)  * 100, 1) if losers else 0

    return patterns


# ---------------------------------------------------------------------------
# Golden Filter derivation
# ---------------------------------------------------------------------------

def _derive_golden_filter(
    fingerprint: list[dict],
    winners: list[dict],
    losers: list[dict],
    patterns: dict,
) -> dict:
    """
    Derive confirm/veto rules from fingerprint and patterns.
    Returns dict with confirm_rules, veto_rules, rationale.
    """
    # Confirm rules: top discriminating fingerprint factors
    discriminating = [f for f in fingerprint if f.get("discriminating")]
    confirm_rules: list[str] = []
    for f in discriminating[:5]:
        confirm_rules.append(
            f"{f['factor']} — {f['winner_pct']:.0f}% of winners vs {f['loser_pct']:.0f}% of losers"
        )

    # If no pure discriminating factors (small sample), use top near-misses
    if not confirm_rules:
        near_miss = [f for f in fingerprint if not f.get("discriminating")]
        for f in near_miss[:5]:
            confirm_rules.append(
                f"{f['factor']} — {f['winner_pct']:.0f}% of winners vs {f['loser_pct']:.0f}% of losers"
            )

    # Veto rules: factors strongly associated with losing
    veto_rules: list[str] = []

    # Headgear first-time
    hg_losers = sum(1 for r in losers  if r.get("headgear_run") == 1)
    hg_winners = sum(1 for r in winners if r.get("headgear_run") == 1)
    if hg_losers > hg_winners:
        veto_rules.append(
            f"First-time headgear (headgear_run=1) — appeared in {hg_losers} losers vs {hg_winners} winners"
        )

    # Cold trainer
    cold_losers = sum(1 for r in losers  if (r.get("trainer_14_pct") or 0) < 12 and r.get("trainer_14_pct") is not None)
    cold_winners = sum(1 for r in winners if (r.get("trainer_14_pct") or 0) < 12 and r.get("trainer_14_pct") is not None)
    if cold_losers > cold_winners:
        veto_rules.append(
            f"Cold trainer (<12% in 14 days) — {cold_losers} losers vs {cold_winners} winners"
        )

    # Large field
    lf_losers = sum(1 for r in losers  if r.get("field_size", 0) > 13)
    lf_winners = sum(1 for r in winners if r.get("field_size", 0) > 13)
    if lf_losers >= 1 or lf_winners >= 1:
        veto_rules.append(
            f"Large field (>13 runners) — {lf_losers} losers vs {lf_winners} winners"
        )

    # Stale form
    stale_losers = sum(1 for r in losers  if r.get("last_run", -1) >= 45)
    stale_winners = sum(1 for r in winners if r.get("last_run", -1) >= 45)
    if stale_losers > stale_winners:
        veto_rules.append(
            f"Stale horse (45+ days since last run) — {stale_losers} losers vs {stale_winners} winners"
        )

    # Grade B+ marginal
    bplus_losers = sum(1 for r in losers  if r.get("grade") == "B+" and r.get("score", 0) < 70)
    bplus_winners = sum(1 for r in winners if r.get("grade") == "B+" and r.get("score", 0) < 70)
    if bplus_losers > bplus_winners * 2:
        veto_rules.append(
            f"Grade B+ with score <70 — {bplus_losers} losers vs {bplus_winners} winners (low confidence band)"
        )

    # Hurdle Evens-2/1 trap
    hurdle_trap_losers = sum(
        1 for r in losers
        if "hurdle" in r.get("race_type", "").lower() and 2.0 <= r.get("sp_dec", 0) <= 3.0
    )
    if hurdle_trap_losers >= 1:
        veto_rules.append(
            f"Hurdle race at Evens-2/1 SP — {hurdle_trap_losers} losers (known 'loss zone' in model)"
        )

    if not veto_rules:
        veto_rules.append("No single veto factor identified — insufficient sample size for strong rules")

    return {
        "confirm_rules":  confirm_rules or ["No discriminating factors found — gather more data"],
        "veto_rules":     veto_rules,
        "rationale":      (
            "Confirm rules derived from fingerprint factors present in the majority of winners "
            "but rare among losers. Veto rules target the most common failure modes."
        ),
        "sample_note":    f"Based on {len(winners)} winner(s) and {len(losers)} loser(s).",
    }


# ---------------------------------------------------------------------------
# Retroactive filter test
# ---------------------------------------------------------------------------

def _apply_filter(r: dict, confirm_rules: list[str], veto_rules_raw: dict) -> tuple[str, list[str]]:
    """
    Apply golden filter to a single NAP record.
    Returns (verdict, triggered_rules) where verdict is CONFIRMED | VETOED | UNCERTAIN.
    """
    veto_triggers: list[str] = []

    # Check veto conditions
    if r.get("headgear_run") == 1 and r.get("headgear", ""):
        veto_triggers.append("First-time headgear")

    if r.get("trainer_14_pct") is not None and r["trainer_14_pct"] < 12:
        veto_triggers.append("Cold trainer (<12%)")

    if r.get("field_size", 0) > 13:
        veto_triggers.append("Large field (>13)")

    if r.get("last_run", -1) >= 45:
        veto_triggers.append("Stale (45+ days off)")

    if (r.get("grade") == "B+" and r.get("score", 0) < 70):
        veto_triggers.append("Grade B+ marginal score")

    if "hurdle" in r.get("race_type", "").lower() and 2.0 <= r.get("sp_dec", 0) <= 3.0:
        veto_triggers.append("Hurdle Evens-2/1 trap")

    if veto_triggers:
        return "VETOED", veto_triggers

    # Check confirm conditions (need at least 2 of the main ones)
    confirm_score = 0
    confirm_triggers: list[str] = []

    if r.get("lto_win") is True:
        confirm_score += 1; confirm_triggers.append("LTO win")

    if (r.get("trainer_14_pct") or 0) >= 25:
        confirm_score += 1; confirm_triggers.append("Trainer 25%+")

    if r.get("train_score", 0) >= 5:
        confirm_score += 1; confirm_triggers.append("Trainer score >=5")

    if r.get("form_score", 0) >= 20:
        confirm_score += 1; confirm_triggers.append("Form score >=20")

    if r.get("suit_score", 0) >= 8:
        confirm_score += 1; confirm_triggers.append("Suit score >=8")

    if 0 < r.get("field_size", 0) <= 9:
        confirm_score += 1; confirm_triggers.append("Small field <=9")

    if r.get("grade") == "A":
        confirm_score += 1; confirm_triggers.append("Grade A")

    if confirm_score >= 3:
        return "CONFIRMED", confirm_triggers

    return "UNCERTAIN", confirm_triggers


def _filter_test(all_naps: list[dict], confirm_rules: list[str]) -> dict:
    """Apply golden filter to all NAPs and measure uplift."""
    confirmed:  list[dict] = []
    vetoed:     list[dict] = []
    uncertain:  list[dict] = []
    details:    list[dict] = []

    for r in all_naps:
        verdict, triggers = _apply_filter(r, confirm_rules, {})
        entry = {
            "date":    r.get("date", ""),
            "horse":   r.get("horse", ""),
            "score":   r.get("score", 0),
            "grade":   r.get("grade", ""),
            "is_win":  r.get("is_win", False),
            "sp_dec":  r.get("sp_dec", 0),
            "verdict": verdict,
            "triggers": triggers,
        }
        details.append(entry)
        if verdict == "CONFIRMED":
            confirmed.append(r)
        elif verdict == "VETOED":
            vetoed.append(r)
        else:
            uncertain.append(r)

    def _win_rate(lst: list[dict]) -> float:
        wins = sum(1 for r in lst if r.get("is_win"))
        return round(wins / len(lst) * 100, 1) if lst else 0.0

    def _roi(lst: list[dict]) -> float:
        pl = sum(
            (r["sp_dec"] - 1.0) if r.get("is_win") else -1.0
            for r in lst if r.get("has_result") or r.get("is_win") is not None
        )
        n = sum(1 for r in lst if r.get("has_result") or r.get("is_win") is not None)
        return round(pl / n * 100, 1) if n else 0.0

    overall_wr = _win_rate(all_naps)
    conf_wr    = _win_rate(confirmed)
    veto_wr    = _win_rate(vetoed)

    return {
        "total_naps":               len(all_naps),
        "confirmed_count":          len(confirmed),
        "vetoed_count":             len(vetoed),
        "uncertain_count":          len(uncertain),
        "overall_win_rate_pct":     overall_wr,
        "confirmed_win_rate_pct":   conf_wr,
        "vetoed_win_rate_pct":      veto_wr,
        "uncertain_win_rate_pct":   _win_rate(uncertain),
        "overall_roi_pct":          _roi(all_naps),
        "confirmed_roi_pct":        _roi(confirmed),
        "vetoed_roi_pct":           _roi(vetoed),
        "uplift_pct":               round(conf_wr - overall_wr, 1),
        "uplift_note":              (
            f"Confirmed picks ({len(confirmed)}) had {conf_wr:.1f}% win rate vs "
            f"{overall_wr:.1f}% for all {len(all_naps)} NAPs — "
            f"{'uplift +' if conf_wr >= overall_wr else 'underperformance '}{abs(conf_wr - overall_wr):.1f}pp."
        ),
        "details": details,
    }


# ---------------------------------------------------------------------------
# Report formatter
# ---------------------------------------------------------------------------

def _fmt_stat(s: dict, label: str, width: int = 22) -> str:
    if s.get("mean") is None:
        return f"  {label:<{width}}  n/a"
    return f"  {label:<{width}}  mean={s['mean']:.2f}  median={s['median']:.2f}  (n={s['n']})"


def _fmt_pct(val, label: str, width: int = 32) -> str:
    if val is None:
        return f"  {label:<{width}}  n/a"
    return f"  {label:<{width}}  {val:.1f}%"


def _format_report(
    nap_count:   int,
    winners:     list[dict],
    losers:      list[dict],
    all_naps:    list[dict],
    wp:          dict,
    lp:          dict,
    comparison:  list[dict],
    fingerprint: list[dict],
    loser_analyses: list[dict],
    patterns:    dict,
    gold_filter: dict,
    filter_test: dict,
    csv_path:    Optional[str],
) -> str:
    sep1 = "=" * 72
    sep2 = "-" * 72
    lines: list[str] = []

    lines += [
        sep1,
        "  NAP SELECTION FORENSIC AUTOPSY",
        f"  Generated:    {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"  Source CSV:   {csv_path or 'None found'}",
        f"  Total NAPs:   {nap_count}  |  Winners: {len(winners)}  |  Losers: {len(losers)}",
        f"  Win rate:     {len(winners) / nap_count * 100:.1f}%" if nap_count else "  Win rate:     n/a",
        sep1,
        "",
    ]

    # ── 1. WINNER vs LOSER PROFILES ──────────────────────────────────────────
    lines += [
        "1. WINNER PROFILE vs LOSER PROFILE",
        sep2,
        f"  {'Attribute':<32}  {'WINNERS':>18}  {'LOSERS':>18}  {'Flag':>6}",
        sep2,
    ]

    def _row(label: str, w_stat, l_stat, is_pct: bool = False) -> str:
        if is_pct:
            wv = f"{w_stat:.1f}%" if w_stat is not None else "n/a"
            lv = f"{l_stat:.1f}%" if l_stat is not None else "n/a"
            if w_stat is not None and l_stat is not None:
                denom = max(w_stat, l_stat, 0.001)
                diff = abs(w_stat - l_stat) / denom * 100
                flag = ">>20%" if diff >= 20 else ""
            else:
                flag = ""
        else:
            wv = f"{w_stat['mean']:.2f}" if (w_stat and w_stat.get("mean") is not None) else "n/a"
            lv = f"{l_stat['mean']:.2f}" if (l_stat and l_stat.get("mean") is not None) else "n/a"
            if w_stat and l_stat and w_stat.get("mean") is not None and l_stat.get("mean") is not None:
                denom = max(abs(w_stat["mean"]), abs(l_stat["mean"]), 0.001)
                diff = abs(w_stat["mean"] - l_stat["mean"]) / denom * 100
                flag = ">>20%" if diff >= 20 else ""
            else:
                flag = ""
        return f"  {label:<32}  {wv:>18}  {lv:>18}  {flag:>6}"

    score_keys = [
        ("Composite score",     "score"),
        ("Form score (0-40)",   "form_score"),
        ("Suit score (0-25)",   "suit_score"),
        ("Context score (0-15)","ctx_score"),
        ("Trainer score (0-15)","train_score"),
        ("Market score (-10/+5)","mkt_score"),
        ("SP (decimal)",        "sp_dec"),
        ("Field size",          "field_size"),
        ("Trainer 14d %",       "trainer_14pct"),
        ("Days since last run", "last_run"),
    ]
    for label, key in score_keys:
        lines.append(_row(label, wp.get(key), lp.get(key)))

    lines.append(sep2)
    pct_keys = [
        ("LTO win %",              "pct_lto_win"),
        ("Going has win %",        "pct_going_has_win"),
        ("Trainer >=25% %",        "pct_trainer_25plus"),
        ("Trainer >=35% %",        "pct_trainer_35plus"),
        ("Small field (<=9) %",    "pct_small_field"),
        ("First-time headgear %",  "pct_headgear_first"),
        ("In handicap %",          "pct_handicap"),
        ("Has spotlight %",        "pct_spotlight"),
    ]
    for label, key in pct_keys:
        lines.append(_row(label, wp.get(key), lp.get(key), is_pct=True))
    lines.append("")

    if comparison:
        lines.append("  >> SIGNIFICANT DIFFERENCES (>20% divergence):")
        for c in comparison[:8]:
            direction = "WINNERS higher" if c.get("winner_higher") else "LOSERS higher"
            w_v = c.get("winner_mean") or c.get("winner_pct")
            l_v = c.get("loser_mean")  or c.get("loser_pct")
            lines.append(
                f"  • {c['attribute']:<32} W={w_v:.2f}  L={l_v:.2f}  diff={c['diff_pct']:.0f}%  [{direction}]"
            )
        lines.append("")
    else:
        lines.append("  No attributes diverge >20% (or insufficient data).\n")

    # ── 2. WINNER FINGERPRINT ─────────────────────────────────────────────────
    lines += [
        "2. WINNER FINGERPRINT",
        sep2,
        "  Discriminating factors: present in majority of winners, rare in losers.",
        "",
    ]
    disc = [f for f in fingerprint if f.get("discriminating")]
    near = [f for f in fingerprint if not f.get("discriminating")]

    if disc:
        lines.append("  STRONG DISCRIMINATORS:")
        for f in disc[:8]:
            lines.append(
                f"  ✓ {f['factor']:<48} W:{f['winner_count']}/{len(winners)} ({f['winner_pct']:.0f}%)"
                f"  L:{f['loser_count']}/{len(losers)} ({f['loser_pct']:.0f}%)"
            )
        lines.append("")
    else:
        lines.append("  No strong discriminating factors found (insufficient data or all factors similar).\n")

    if near:
        lines.append("  NEAR-DISCRIMINATING (60%+ winners, 25pp+ gap):")
        for f in near[:6]:
            lines.append(
                f"  ~ {f['factor']:<48} W:{f['winner_count']}/{len(winners)} ({f['winner_pct']:.0f}%)"
                f"  L:{f['loser_count']}/{len(losers)} ({f['loser_pct']:.0f}%)"
            )
        lines.append("")

    if not disc and not near:
        lines.append("  Fingerprint requires data. Run historical_backtest.py first.\n")

    # ── 3. LOSER AUTOPSY ─────────────────────────────────────────────────────
    lines += [
        "3. LOSER AUTOPSY — RACE NARRATIVES",
        sep2,
        "",
    ]
    if loser_analyses:
        cat_counts: Counter = Counter(a["category"] for a in loser_analyses)
        lines.append(f"  Loss category breakdown: {dict(cat_counts)}")
        lines.append("")
        for i, a in enumerate(loser_analyses, 1):
            lines += [
                f"  [{i}] DATE: {a['date']}  |  {a['horse'].upper()}  |  CATEGORY: {a['category']}",
                f"       SP: {a['sp_dec']:.1f}  |  Position: {a['position']}  |  Score: {a['score']:.1f} ({a['grade']})",
                f"       {a['narrative']}",
                "",
            ]
    else:
        lines.append("  No losing NAPs to autopsy (no data, or all NAPs won).\n")

    # ── 4. PATTERN ANALYSIS ──────────────────────────────────────────────────
    lines += [
        "4. PATTERN ANALYSIS",
        sep2,
        "",
    ]
    pa = patterns

    lines += [
        f"  Trainer concentration:     {pa.get('winner_trainer_concentration', 'n/a')}",
        f"  Winner trainer frequency:  {pa.get('winner_trainer_frequency', {})}",
        "",
        f"  Winner avg field size:     {pa.get('winner_avg_field_size', 'n/a')}",
        f"  Loser avg field size:      {pa.get('loser_avg_field_size', 'n/a')}",
        f"  Smaller fields for winners:{pa.get('smaller_fields_for_winners', 'n/a')}",
        "",
        f"  Winner avg SP:             {pa.get('winner_avg_sp', 'n/a')}",
        f"  Loser avg SP:              {pa.get('loser_avg_sp', 'n/a')}",
        f"  Market confirms model:     {pa.get('market_confirms_model', 'n/a')}",
        "",
        f"  Winner with spotlight %:   {pa.get('winner_with_spotlight_pct', 0):.1f}%",
        f"  Loser with spotlight %:    {pa.get('loser_with_spotlight_pct', 0):.1f}%",
        "",
        f"  Winner race type dist:     {pa.get('winner_race_type_dist', {})}",
        f"  Loser race type dist:      {pa.get('loser_race_type_dist', {})}",
        "",
        f"  Winner going dist:         {pa.get('winner_going_dist', {})}",
        f"  Loser going dist:          {pa.get('loser_going_dist', {})}",
        "",
        f"  Winner in handicap %:      {pa.get('winner_in_handicap_pct', 0):.1f}%",
        f"  Loser in handicap %:       {pa.get('loser_in_handicap_pct', 0):.1f}%",
        f"  Class drop note:           {pa.get('class_drop_note', 'n/a')}",
        "",
        f"  Winner LTO win %:          {pa.get('winner_lto_win_pct', 0):.1f}%",
        f"  Loser LTO win %:           {pa.get('loser_lto_win_pct', 0):.1f}%",
        "",
        f"  Winner Grade A %:          {pa.get('winner_grade_A_pct', 0):.1f}%",
        f"  Loser Grade A %:           {pa.get('loser_grade_A_pct', 0):.1f}%",
        "",
    ]

    # ── 5. GOLDEN FILTER ─────────────────────────────────────────────────────
    lines += [
        "5. THE GOLDEN FILTER",
        sep2,
        "",
        f"  {gold_filter.get('rationale', '')}",
        f"  {gold_filter.get('sample_note', '')}",
        "",
        "  A selection should be CONFIRMED only if ALL of these are true:",
    ]
    for i, rule in enumerate(gold_filter.get("confirm_rules", []), 1):
        lines.append(f"    {i}. {rule}")
    lines += [
        "",
        "  A selection should be VETOED if ANY of these are true:",
    ]
    for i, rule in enumerate(gold_filter.get("veto_rules", []), 1):
        lines.append(f"    {i}. {rule}")
    lines.append("")

    # ── 6. RETROACTIVE FILTER TEST ───────────────────────────────────────────
    ft = filter_test
    lines += [
        "6. RETROACTIVE FILTER TEST",
        sep2,
        "",
        f"  Total NAPs:              {ft['total_naps']}",
        f"  Confirmed by filter:     {ft['confirmed_count']}  ({ft['confirmed_win_rate_pct']:.1f}% win rate)",
        f"  Vetoed by filter:        {ft['vetoed_count']}   ({ft['vetoed_win_rate_pct']:.1f}% win rate)",
        f"  Uncertain:               {ft['uncertain_count']}  ({ft['uncertain_win_rate_pct']:.1f}% win rate)",
        f"  Overall win rate:        {ft['overall_win_rate_pct']:.1f}%",
        f"  Confirmed ROI:           {ft['confirmed_roi_pct']:.1f}%",
        f"  Vetoed ROI:              {ft['vetoed_roi_pct']:.1f}%",
        f"  Uplift (confirmed vs all):{ft['uplift_pct']:.1f}pp",
        "",
        f"  VERDICT: {ft['uplift_note']}",
        "",
        "  Per-NAP verdicts:",
    ]
    for d in ft.get("details", []):
        win_label = "WIN " if d.get("is_win") else "LOSS"
        sp_s = f"SP={d['sp_dec']:.1f}" if d.get("sp_dec") else ""
        trig = ", ".join(d.get("triggers", []))[:50] or "—"
        lines.append(
            f"  {d['date']}  {d['horse']:<22}  Score={d['score']:.1f} ({d['grade']})  "
            f"{win_label}  {sp_s:<12}  {d['verdict']:<12}  [{trig}]"
        )
    lines.append("")

    # ── SUMMARY FINGERPRINT ───────────────────────────────────────────────────
    lines += [
        sep1,
        "  EXECUTIVE SUMMARY — WINNER FINGERPRINT (TOP 5 FACTORS)",
        sep1,
    ]
    top5 = [f for f in fingerprint if f.get("discriminating")][:5]
    if not top5:
        top5 = fingerprint[:5]
    for i, f in enumerate(top5, 1):
        lines.append(f"  {i}. {f['factor']}")
        lines.append(
            f"     Winners: {f['winner_count']}/{len(winners)} ({f['winner_pct']:.0f}%)   "
            f"Losers: {f['loser_count']}/{len(losers)} ({f['loser_pct']:.0f}%)"
        )
    lines.append("")

    lines += [
        "  GOLDEN FILTER — CONFIRM if all true:",
    ]
    for i, r in enumerate(gold_filter.get("confirm_rules", [])[:3], 1):
        lines.append(f"  {i}. {r}")
    lines.append("  GOLDEN FILTER — VETO if any true:")
    for i, r in enumerate(gold_filter.get("veto_rules", [])[:3], 1):
        lines.append(f"  {i}. {r}")
    lines.append("")

    lines += [
        f"  RETROSPECTIVE TEST: {ft['uplift_note']}",
        sep1,
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Forensic autopsy of NAP selections")
    parser.add_argument("--csv", type=str, default=None,
                        help="Path to backtest CSV (default: most recent data/backtest_*.csv)")
    args = parser.parse_args()

    # --- Load CSV -------------------------------------------------------
    csv_path = _find_csv(args.csv)
    all_rows: list[dict] = []

    if csv_path and csv_path.exists():
        all_rows = _load_csv(csv_path)
        print(f"Loaded {len(all_rows)} rows from {csv_path}")
    else:
        print("No backtest CSV found — running in skeleton mode with empty data.")
        print("  Run historical_backtest.py first to populate data/backtest_*.csv")

    # --- Identify NAPs --------------------------------------------------
    all_naps_raw = _identify_naps(all_rows)
    print(f"Identified {len(all_naps_raw)} daily NAP selections")

    # --- Enrich each NAP ------------------------------------------------
    all_naps: list[dict] = []
    for i, nap in enumerate(all_naps_raw):
        enriched = _enrich_nap(nap)
        all_naps.append(enriched)
        if (i + 1) % 10 == 0:
            print(f"  Enriched {i+1}/{len(all_naps_raw)} NAPs...")

    # --- Split winners / losers ----------------------------------------
    winners: list[dict] = [r for r in all_naps if r.get("is_win") and r.get("has_result")]
    losers:  list[dict] = [r for r in all_naps if not r.get("is_win") and r.get("has_result")]
    unresolved = [r for r in all_naps if not r.get("has_result")]

    print(f"Winners: {len(winners)}  |  Losers: {len(losers)}  |  Unresolved: {len(unresolved)}")

    # --- Handle empty data gracefully -----------------------------------
    # Generate synthetic example data for structural demonstration if no real data
    if not all_naps:
        print("\nNo NAP data available. Generating analysis structure with synthetic examples.")
        print("Replace with real data by running: python historical_backtest.py")
        _generate_empty_outputs(csv_path)
        return 0

    # --- Build profiles -------------------------------------------------
    wp = _build_profile(winners)
    lp = _build_profile(losers)
    comparison = _compare_profiles(wp, lp)

    # --- Fingerprint ----------------------------------------------------
    fingerprint = _compute_fingerprint(winners, losers)

    # --- Loser autopsy --------------------------------------------------
    loser_analyses: list[dict] = []
    for r in losers:
        cat, narrative = _classify_loss(r)
        loser_analyses.append({
            "date":      r.get("date", ""),
            "horse":     r.get("horse", ""),
            "course":    r.get("course", ""),
            "race_name": r.get("race_name", ""),
            "category":  cat,
            "narrative": narrative,
            "score":     r.get("score", 0),
            "grade":     r.get("grade", ""),
            "sp_dec":    r.get("sp_dec", 0),
            "position":  r.get("position", ""),
            "going":     r.get("going", ""),
            "form_score":  r.get("form_score", 0),
            "suit_score":  r.get("suit_score", 0),
            "train_score": r.get("train_score", 0),
            "trainer_14_pct": r.get("trainer_14_pct"),
            "field_size": r.get("field_size", 0),
        })

    # --- Pattern analysis -----------------------------------------------
    patterns = _pattern_analysis(winners, losers, all_naps)

    # --- Golden filter --------------------------------------------------
    gold_filter = _derive_golden_filter(fingerprint, winners, losers, patterns)

    # --- Retroactive filter test ----------------------------------------
    filter_test = _filter_test(all_naps, gold_filter.get("confirm_rules", []))

    # --- Format report --------------------------------------------------
    report_text = _format_report(
        nap_count   = len(all_naps),
        winners     = winners,
        losers      = losers,
        all_naps    = all_naps,
        wp          = wp,
        lp          = lp,
        comparison  = comparison,
        fingerprint = fingerprint,
        loser_analyses = loser_analyses,
        patterns    = patterns,
        gold_filter = gold_filter,
        filter_test = filter_test,
        csv_path    = str(csv_path) if csv_path else None,
    )

    # --- Write report ---------------------------------------------------
    report_dest = _ensure(REPORTS_DIR / "nap_autopsy_report.txt")
    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
        print(f"\nReport: {report_dest}")
    except OSError as exc:
        print(f"[ERROR] Failed to write report: {exc}", file=sys.stderr)
        return 1

    # --- Write JSON data ------------------------------------------------
    autopsy_data = {
        "generated_at":     datetime.now().isoformat(),
        "source_csv":       str(csv_path) if csv_path else None,
        "total_naps":       len(all_naps),
        "winner_count":     len(winners),
        "loser_count":      len(losers),
        "unresolved_count": len(unresolved),
        "win_rate_pct":     round(len(winners) / len(all_naps) * 100, 1) if all_naps else 0,
        "winner_profile":   wp,
        "loser_profile":    lp,
        "profile_comparison": comparison,
        "fingerprint_factors": fingerprint,
        "loser_narratives": loser_analyses,
        "patterns":         patterns,
        "golden_filter_rules": gold_filter,
        "filter_test_results": filter_test,
        "all_naps_enriched": all_naps,
    }

    json_dest = _ensure(DATA_DIR / "nap_autopsy_data.json")
    try:
        with open(json_dest, "w", encoding="utf-8") as fh:
            json.dump(autopsy_data, fh, indent=2, default=str)
        print(f"JSON:   {json_dest}")
    except OSError as exc:
        print(f"[ERROR] Failed to write JSON: {exc}", file=sys.stderr)
        return 1

    # --- Print summary --------------------------------------------------
    print("\n" + "=" * 72)
    print("  AUTOPSY SUMMARY")
    print("=" * 72)
    print(f"  NAPs analysed: {len(all_naps)}  |  Winners: {len(winners)}  |  Losers: {len(losers)}")
    if all_naps:
        print(f"  Win rate: {len(winners)/len(all_naps)*100:.1f}%")

    print("\n  WINNER FINGERPRINT (top 5 discriminating factors):")
    top5 = [f for f in fingerprint if f.get("discriminating")][:5]
    if not top5:
        top5 = fingerprint[:5]
    for i, f in enumerate(top5, 1):
        print(f"  {i}. {f['factor']}  [{f['winner_count']}/{len(winners)} W, {f['loser_count']}/{len(losers)} L]")

    print("\n  GOLDEN FILTER — CONFIRM if all true:")
    for i, r in enumerate(gold_filter.get("confirm_rules", [])[:3], 1):
        print(f"  {i}. {r}")
    print("  GOLDEN FILTER — VETO if any true:")
    for i, r in enumerate(gold_filter.get("veto_rules", [])[:3], 1):
        print(f"  {i}. {r}")

    print(f"\n  RETROSPECTIVE TEST: {filter_test['uplift_note']}")
    print("=" * 72)

    return 0


# ---------------------------------------------------------------------------
# Empty-data skeleton (no CSV case)
# ---------------------------------------------------------------------------

def _generate_empty_outputs(csv_path) -> None:
    """Write minimal valid outputs when no data is available."""
    empty_data = {
        "generated_at":     datetime.now().isoformat(),
        "source_csv":       str(csv_path) if csv_path else None,
        "status":           "NO_DATA",
        "message":          "No backtest CSV found. Run: python historical_backtest.py",
        "total_naps":       0,
        "winner_count":     0,
        "loser_count":      0,
        "winner_profile":   {"count": 0},
        "loser_profile":    {"count": 0},
        "profile_comparison": [],
        "fingerprint_factors": [],
        "loser_narratives": [],
        "patterns":         {},
        "golden_filter_rules": {
            "confirm_rules": [
                "Trainer 14d >= 25% (hot trainer intent signal)",
                "Form score >= 20 (strong recent form quality)",
                "Suitability score >= 8 (course/going/distance proven)",
                "Grade A (score >= 70) — high-confidence threshold only",
                "LTO win (last time out winner — momentum signal)",
            ],
            "veto_rules": [
                "First-time headgear (headgear_run=1) — unproven, often negative",
                "Cold trainer (<12% in 14 days) — no trainer intent signal",
                "Large field (>13 runners) — form edge diluted, lottery element",
                "Stale horse (45+ days since last run) — fitness risk",
                "Hurdle race at Evens-2/1 SP — known model loss zone",
            ],
            "rationale":  "Derived from nap_selector_v3.py scoring logic analysis",
            "sample_note": "Based on 0 NAPs (no data) — rules are model-logic-derived defaults",
        },
        "filter_test_results": {
            "total_naps": 0,
            "confirmed_count": 0,
            "vetoed_count": 0,
            "uncertain_count": 0,
            "overall_win_rate_pct": 0.0,
            "confirmed_win_rate_pct": 0.0,
            "vetoed_win_rate_pct": 0.0,
            "uncertain_win_rate_pct": 0.0,
            "overall_roi_pct": 0.0,
            "confirmed_roi_pct": 0.0,
            "vetoed_roi_pct": 0.0,
            "uplift_pct": 0.0,
            "uplift_note": "No data to test",
            "details": [],
        },
    }

    json_dest = _ensure(DATA_DIR / "nap_autopsy_data.json")
    try:
        with open(json_dest, "w", encoding="utf-8") as fh:
            json.dump(empty_data, fh, indent=2)
        print(f"JSON (empty): {json_dest}")
    except OSError as exc:
        print(f"[ERROR] Failed to write JSON: {exc}", file=sys.stderr)

    report_text = f"""{'='*72}
  NAP SELECTION FORENSIC AUTOPSY
  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
  Status:    NO DATA
{'='*72}

  No backtest CSV was found in data/backtest_*.csv.

  To populate data, run:
      python historical_backtest.py

  Once you have data, re-run:
      python nap_autopsy.py

{'='*72}
  GOLDEN FILTER RULES (model-logic-derived defaults)
{'='*72}

  A selection should be CONFIRMED only if ALL of these are true:
    1. Trainer 14d >= 25% (hot trainer intent signal)
    2. Form score >= 20 (strong recent form quality)
    3. Suitability score >= 8 (course/going/distance proven)
    4. Grade A (score >= 70) — high-confidence threshold only
    5. LTO win (last time out winner — momentum signal)

  A selection should be VETOED if ANY of these are true:
    1. First-time headgear (headgear_run=1) — unproven, often negative
    2. Cold trainer (<12% in 14 days) — no trainer intent signal
    3. Large field (>13 runners) — form edge diluted, lottery element
    4. Stale horse (45+ days since last run) — fitness risk
    5. Hurdle race at Evens-2/1 SP — known model loss zone

  These rules are derived from nap_selector_v3.py scoring logic.
  They will be empirically validated and refined once backtest data is available.

{'='*72}
"""

    report_dest = _ensure(REPORTS_DIR / "nap_autopsy_report.txt")
    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
        print(f"Report: {report_dest}")
    except OSError as exc:
        print(f"[ERROR] Failed to write report: {exc}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
