"""
historical_backtest.py — Retrospective backtest of the NAP selection model.

Fetches historical racecards and results from the Racing API, replays the
nap_selector_v3 scoring logic for each day, and reports strike rate and P/L
broken down by race type, class, score band, going, and distance.

Suitability scoring uses the form-string fallback (no per-horse full_form
API calls). Market score uses racecard bookmaker odds only (no movement
data). Composite max is ~95 pts (vs 100 with live market).

Usage:
    python historical_backtest.py                          # last 6 months
    python historical_backtest.py --months 12              # last 12 months
    python historical_backtest.py --start 2025-06-01 --end 2026-06-07
    python historical_backtest.py --min-score 55           # lower threshold

Outputs:
    data/backtest_cache/racecards/YYYY-MM-DD.json          # cached API data
    data/backtest_cache/results/YYYY-MM-DD.json
    reports/backtest_YYYY-MM-DD_to_YYYY-MM-DD.txt
    data/backtest_YYYY-MM-DD_to_YYYY-MM-DD.csv

Exit codes:
    0  — report produced
    1  — fatal error (config, no data, write failure)
"""

from __future__ import annotations
import argparse, csv, json, os, sys, time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from src.config import get_config
from src.helpers import data_path, going_normalise, log, report_path
from src.api_client import get_client, RacingAPIError
from nap_selector_v3 import (
    score_runner, NAP_MIN_SCORE, NAP_MAX_SCORE, GRADE_A_THRESHOLD,
    NAP_EXCLUDED_RACE_TYPES, NAP_MIN_ODDS, NAP_MAX_ODDS, FLAT_MAX_DIST_F, FLAT_MIN_DIST_F,
    FLAT_EXCLUDED_GOING, CLUSTER_SPREAD, CLUSTER_MIN_SCORE, RANK_PROMOTION_MIN_SCORE,
    detect_race_cluster,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_DELAY_S = 0.6
MAX_DAYS = 900  # ~30 months; cached days are free on subsequent runs
HORSE_FORM_LIMIT = 50  # per-horse career results to fetch in --deep mode;
                       # generous so point-in-time filtering still leaves history
                       # for races early in the window

# Module-level counter so the long deep pull shows progress.
_horse_fetch_count = 0

# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_dir() -> Path:
    p = Path(data_path("backtest_cache"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cache_path(subdir: str, date_str: str) -> Path:
    d = _cache_dir() / subdir
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{date_str}.json"


def _load_cache(subdir: str, date_str: str) -> Optional[dict]:
    p = _cache_path(subdir, date_str)
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _save_cache(subdir: str, date_str: str, data: dict) -> None:
    p = _cache_path(subdir, date_str)
    try:
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except OSError as exc:
        log(f"backtest: cache write failed ({p}) — {exc}", "WARNING")


# ---------------------------------------------------------------------------
# Deep (full-fidelity) form fetch — gives score_runner the same per-horse form
# it has live, so historical scores live on the same 0-100 scale as production.
# ---------------------------------------------------------------------------

def _get_horse_form(client, horse_id: str) -> list[dict]:
    """Return a horse's career results, cached once per horse_id.

    The full career is cached; point-in-time filtering (results strictly before
    a given race date) happens per-race in _build_full_form, so one fetch serves
    every race the horse appears in across the whole window.
    """
    global _horse_fetch_count
    if not horse_id:
        return []
    cached = _load_cache("horse_form", horse_id)
    if cached is not None:
        return cached.get("results", [])
    try:
        results = client.get_horse_results(horse_id, limit=HORSE_FORM_LIMIT) or []
    except Exception as exc:  # noqa: BLE001 — never let one horse abort the pull
        log(f"backtest: horse_results error {horse_id} — {exc}", "WARNING")
        results = []
    _save_cache("horse_form", horse_id, {"results": results})
    _horse_fetch_count += 1
    if _horse_fetch_count % 200 == 0:
        print(f"    [deep] fetched form for {_horse_fetch_count} new horses…")
    time.sleep(API_DELAY_S)
    return results


def _build_full_form(client, runners: list[dict], race_date: str) -> dict:
    """Build a point-in-time full_form dict for a race's runners.

    Only counts each horse's runs strictly before race_date (ISO dates compare
    lexically), so there is no lookahead from results after the race.
    """
    horses: dict[str, list[dict]] = {}
    for runner in runners:
        hid = str(runner.get("horse_id") or "")
        if not hid:
            continue
        prior = [
            r for r in _get_horse_form(client, hid)
            if str(r.get("date") or r.get("race_date") or "") < race_date
        ]
        horses[hid] = prior
    return {"horses": horses}

# ---------------------------------------------------------------------------
# Runner / racecard normalisation helpers
# ---------------------------------------------------------------------------

def _safe_str(val, default: str = "") -> str:
    if val is None:
        return default
    return str(val).strip()


def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _safe_int(val, default: int = -1) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _normalise_runner(raw: dict) -> dict:
    return {
        "horse_id":          _safe_str(raw.get("horse_id")),
        "horse":             _safe_str(raw.get("horse")),
        "trainer":           _safe_str(raw.get("trainer")),
        "trainer_id":        _safe_str(raw.get("trainer_id")),
        "jockey":            _safe_str(raw.get("jockey")),
        "jockey_id":         _safe_str(raw.get("jockey_id")),
        "age":               _safe_str(raw.get("age")),
        "form":              _safe_str(raw.get("form")),
        "draw":              _safe_int(raw.get("draw"), default=-1),
        "ofr":               _safe_str(raw.get("ofr")),
        "rpr":               _safe_str(raw.get("rpr")),
        "ts":                _safe_str(raw.get("ts")),
        "sp_dec":            _safe_float(raw.get("sp_dec"), default=0.0),
        "last_run":          _safe_int(raw.get("last_run"), default=-1),
        "position":          _safe_str(raw.get("position") or raw.get("finish_position")),
        "odds":              raw.get("odds") if isinstance(raw.get("odds"), list) else [],
        "headgear":          _safe_str(raw.get("headgear")),
        "headgear_run":      _safe_int(raw.get("headgear_run"), default=-1),
        "wind_surgery_run":  _safe_int(raw.get("wind_surgery_run"), default=-1),
        "trainer_14_days":   raw.get("trainer_14_days") if isinstance(raw.get("trainer_14_days"), dict) else {},
        "spotlight":         _safe_str(raw.get("spotlight")),
        "comment":           _safe_str(raw.get("comment")),
        "quotes":            _safe_str(raw.get("quotes")),
        "stable_tour":       _safe_str(raw.get("stable_tour")),
        "prev_trainers":     raw.get("prev_trainers") if isinstance(raw.get("prev_trainers"), list) else [],
        "trainer_rtf":       _safe_str(raw.get("trainer_rtf")),
        "wind_surgery":      _safe_str(raw.get("wind_surgery")),
        "medical":           raw.get("medical") if isinstance(raw.get("medical"), list) else [],
    }


def _normalise_racecard(raw: dict) -> dict:
    runners_raw = raw.get("runners") or []
    runners = [_normalise_runner(r) for r in runners_raw]
    return {
        "race_id":     _safe_str(raw.get("race_id")),
        "course":      _safe_str(raw.get("course")),
        "off_time":    _safe_str(raw.get("off_time") or raw.get("off")),
        "race_name":   _safe_str(raw.get("race_name") or raw.get("race")),
        "class":       next((raw.get(k) for k in ("class", "race_class", "pattern", "race_group") if raw.get(k) is not None), None),
        "distance_f":  _safe_float(raw.get("distance_f") or raw.get("dist_f")),
        "going":       _safe_str(raw.get("going")),
        "surface":     _safe_str(raw.get("surface")),
        "type":        _safe_str(raw.get("type")),
        "region":      _safe_str(raw.get("region")),
        "field_size":  _safe_int(raw.get("field_size") or len(runners_raw), default=0),
        "runners":     runners,
    }

# ---------------------------------------------------------------------------
# API fetchers (with caching)
# ---------------------------------------------------------------------------

def _fetch_racecard(date_str: str, client, cfg) -> list[dict]:
    cached = _load_cache("racecards", date_str)
    if cached is not None:
        return cached.get("races", [])

    try:
        raw = client.get_racecards(day=date_str, region_codes=cfg.regions)
        time.sleep(API_DELAY_S)
        races_raw = raw.get("racecards") or raw.get("races") or []
        if not races_raw:
            _save_cache("racecards", date_str, {"races": []})
            return []
        races = [_normalise_racecard(r) for r in races_raw]
        _save_cache("racecards", date_str, {"races": races})
        return races
    except RacingAPIError as exc:
        log(f"backtest: racecard API error {date_str} — {exc}", "WARNING")
        _save_cache("racecards", date_str, {"races": []})
        return []


def _fetch_results_per_race(races: list[dict], client) -> dict[str, dict]:
    """Fetch results for each race via /results/{race_id} and cache per-race.

    Uses the same endpoint as results_auditor.py — known to work.  Each race
    result is cached in data/backtest_cache/race_results/<race_id>.json so
    subsequent backtest runs skip all API calls.
    """
    lookup: dict[str, dict] = {}
    for race in races:
        race_id = race.get("race_id", "")
        if not race_id:
            continue

        cached = _load_cache("race_results", race_id)
        if cached is not None:
            lookup.update(cached.get("runners", {}))
            continue

        try:
            result = client.get_race_results(race_id)
            time.sleep(API_DELAY_S)
        except RacingAPIError as exc:
            log(f"backtest: race result error {race_id} — {exc}", "WARNING")
            _save_cache("race_results", race_id, {"runners": {}})
            continue

        if not result:
            _save_cache("race_results", race_id, {"runners": {}})
            continue

        runners_raw = result.get("runners") or result.get("results") or []
        race_lookup: dict[str, dict] = {}
        for runner in runners_raw:
            hid = str(runner.get("horse_id") or "")
            if not hid:
                continue
            pos = str(
                runner.get("position")
                or runner.get("finish_position")
                or ""
            )
            sp = _safe_float(
                runner.get("sp_dec") or runner.get("bsp") or runner.get("sp")
            )
            race_lookup[hid] = {"position": pos, "sp_dec": sp}

        _save_cache("race_results", race_id, {"runners": race_lookup})
        lookup.update(race_lookup)

    return lookup

# ---------------------------------------------------------------------------
# Category helpers
# ---------------------------------------------------------------------------

def _type_group(race_type: str) -> str:
    rt = (race_type or "").lower()
    if "chase" in rt:  return "Chase"
    if "hurdle" in rt: return "Hurdle"
    if "bumper" in rt or "nhf" in rt or "national hunt flat" in rt: return "Bumper/NHF"
    if "flat" in rt or not rt: return "Flat"
    return "Other"


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


def _score_band(s: float) -> str:
    if s >= 80: return "80+"
    if s >= 70: return "70-79"
    if s >= 60: return "60-69"
    if s >= 50: return "50-59"
    return "<50"


def _going_group(going: str) -> str:
    g = going_normalise(going or "").lower()
    if "firm" in g:     return "Firm/Good-Firm"
    if "heavy" in g:    return "Heavy"
    if "soft" in g:     return "Soft/Good-Soft"
    if "good" in g:     return "Good"
    if "standard" in g or "slow" in g: return "All-Weather"
    return "Unknown"


def _dist_group(f: float) -> str:
    if f <= 0:    return "Unknown"
    if f < 7.0:   return "Sprint (<7f)"
    if f < 10.5:  return "Mile (7-10.5f)"
    if f < 14.0:  return "Middle (10.5-14f)"
    return        "Staying (14f+)"

# ---------------------------------------------------------------------------
# Stats accumulator
# ---------------------------------------------------------------------------

class _Stats:
    def __init__(self):
        self.total = 0      # all records (shows score distribution even without results)
        self.n = 0          # records with result data
        self.wins = 0
        self.places = 0     # top 3
        self.pl = 0.0       # level-stakes P/L at SP

    def record(self, is_win: bool, is_place: bool, sp_dec: float, has_result: bool):
        self.total += 1
        if not has_result:
            return
        self.n += 1
        if is_win:
            self.wins += 1
            self.pl += max(0.0, sp_dec - 1.0)
        else:
            self.pl -= 1.0
        if is_place:
            self.places += 1

    @property
    def win_pct(self): return self.wins / self.n * 100 if self.n else 0.0
    @property
    def place_pct(self): return self.places / self.n * 100 if self.n else 0.0
    @property
    def roi(self): return self.pl / self.n * 100 if self.n else 0.0

# ---------------------------------------------------------------------------
# Report formatting helper
# ---------------------------------------------------------------------------

def _render_table(breakdown: dict[str, _Stats]) -> list[str]:
    """Return lines for a breakdown table sorted by win_pct (where known), then total."""
    header = f"  {'Category':<26} {'Total':>6} {'w/Res':>6} {'Wins':>5} {'Win%':>6} {'Plc%':>6} {'P/L':>8} {'ROI%':>7}"
    sep    = "  " + "-" * 70
    rows   = [header, sep]
    items  = sorted(
        [(k, v) for k, v in breakdown.items() if v.total > 0],
        key=lambda kv: (-kv[1].win_pct if kv[1].n >= 3 else 0, -kv[1].total),
    )
    for name, s in items:
        if s.n >= 3:
            rows.append(
                f"  {name:<26} {s.total:>6} {s.n:>6} {s.wins:>5} "
                f"{s.win_pct:>5.1f}% {s.place_pct:>5.1f}% "
                f"{s.pl:>+8.1f} {s.roi:>+6.1f}%"
            )
        else:
            rows.append(
                f"  {name:<26} {s.total:>6} {s.n:>6}    —      —      —         —       —"
            )
    return rows

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    global HORSE_FORM_LIMIT
    parser = argparse.ArgumentParser()
    parser.add_argument("--months",    type=int,   default=6)
    parser.add_argument("--start",     type=str,   default=None)
    parser.add_argument("--end",       type=str,   default=None)
    parser.add_argument("--min-score", type=float, default=NAP_MIN_SCORE,
                        dest="min_score")
    parser.add_argument("--include-jumps", action="store_true", default=False,
                        dest="include_jumps",
                        help="Include excluded race types (chases etc) in daily NAP pool")
    parser.add_argument("--max-flat-dist", type=float, default=FLAT_MAX_DIST_F,
                        dest="max_flat_dist",
                        help="Max distance in furlongs for flat NAP selection (default 16f)")
    parser.add_argument("--clear-margin", type=float, default=3.0,
                        dest="clear_margin",
                        help="Rank-promotion margin over 2nd (default 3.0 = live "
                             "nap_clear_margin default). The A/B section shows what "
                             "the new rank-promotion rule would have added.")
    parser.add_argument("--deep", action="store_true", default=False,
                        help="Full-fidelity: fetch per-horse form so scores match "
                             "the live model (one cached API call per horse).")
    parser.add_argument("--form-limit", type=int, default=HORSE_FORM_LIMIT,
                        dest="form_limit",
                        help="Per-horse results to fetch in --deep mode (default 50). "
                             "Lower (e.g. 20) shrinks the cache ~3x — enough for a "
                             "12-month window's point-in-time history.")
    args = parser.parse_args()
    HORSE_FORM_LIMIT = args.form_limit

    # Date range
    end_date   = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=args.months * 30)
    if args.end:
        try: end_date = date.fromisoformat(args.end)
        except ValueError: print(f"Bad --end: {args.end}"); return 1
    if args.start:
        try: start_date = date.fromisoformat(args.start)
        except ValueError: print(f"Bad --start: {args.start}"); return 1

    date_range = []
    d = start_date
    while d <= end_date:
        date_range.append(d.isoformat())
        d += timedelta(days=1)

    if len(date_range) > MAX_DAYS:
        print(f"Range too large ({len(date_range)} days, max {MAX_DAYS})"); return 1

    start_str = start_date.isoformat()
    end_str   = end_date.isoformat()

    print(f"Backtesting {len(date_range)} days: {start_str} → {end_str}")
    print(f"Min score threshold: {args.min_score}  |  Include jumps: {args.include_jumps}  |  Max flat dist: {args.max_flat_dist}f  |  (cached days skip API call)")

    try:
        cfg    = get_config()
        client = get_client()
    except Exception as exc:
        log(f"backtest: config error — {exc}", "ERROR"); return 1

    # --- Collect records -------------------------------------------------------
    all_records:  list[dict] = []
    daily_naps:   list[dict] = []
    promoted_naps: list[dict] = []   # B-only picks: rank-promoted on floor-blank days
    days_data     = 0
    days_no_data  = 0
    days_with_nap = 0

    for idx, date_str in enumerate(date_range, 1):
        if idx % 10 == 0:
            print(f"  Processing day {idx}/{len(date_range)}: {date_str}")

        races = _fetch_racecard(date_str, client, cfg)
        if not races:
            days_no_data += 1
            continue

        days_data += 1

        # Always fetch results via /results/{race_id} — the only reliable source.
        # Do NOT attempt to read "position" from racecard runners: that field is the
        # draw/stall number, not the finishing position, so it corrupts W/P/L figures.
        results_lookup = _fetch_results_per_race(races, client)

        best_day_score  = -1.0
        best_day_record: Optional[dict] = None
        best_promoted_score  = -1.0
        best_promoted_record: Optional[dict] = None

        for race in races:
            runners = race.get("runners") or []
            if not runners:
                continue

            race_type  = race.get("type", "")
            race_class = race.get("class", "")
            dist_f     = _safe_float(race.get("distance_f"))
            going      = race.get("going", "")
            course     = race.get("course", "")

            # In --deep mode, build point-in-time full form so suitability
            # scoring matches the live model; otherwise use the fallback.
            race_full_form = (
                _build_full_form(client, runners, date_str) if args.deep else None
            )

            # Score every runner
            scored = []
            for runner in runners:
                try:
                    s = score_runner(
                        runner=runner,
                        race=race,
                        all_runners=runners,
                        full_form=race_full_form,  # deep: real form; else fallback
                        market_movers=None,        # no historical movement data
                    )
                    scored.append(s)
                except Exception as exc:
                    log(f"backtest: score_runner error {date_str} — {exc}", "WARNING")
                    continue

            if not scored:
                continue

            scored.sort(key=lambda x: -x["score"])
            top = scored[0]
            horse_id = top["horse_id"]
            composite = top["score"]
            # Margin over 2nd — the live selector's rank-promotion signal.
            margin = composite - scored[1]["score"] if len(scored) > 1 else 0.0

            result     = results_lookup.get(horse_id, {})
            has_result = bool(result)
            position   = result.get("position", "")
            sp_dec     = result.get("sp_dec", 0.0)

            try:   pos_int = int(position)
            except (TypeError, ValueError): pos_int = 99

            is_win   = pos_int == 1
            is_place = pos_int <= 3

            record = {
                "date":           date_str,
                "race_type":      race_type,
                "race_class":     race_class,
                "distance_f":     dist_f,
                "going":          going,
                "course":         course,
                "horse":          top["horse"],
                "horse_id":       horse_id,
                "score":          composite,
                "grade":          top["grade"],
                "form_score":     top["form_score"],
                "suit_score":     top["suitability_score"],
                "ctx_score":      top["context_score"],
                "draw_score":     top.get("draw_score", 0.0),
                "train_score":    top["trainer_score"],
                "mkt_score":      top["market_score"],
                "position":       position,
                "sp_dec":         sp_dec,
                "has_result":     has_result,
                "is_win":         is_win,
                "is_place":       is_place,
                # group labels for aggregation
                "type_group":     _type_group(race_type),
                "class_group":    _class_group(race_class),
                "score_band":     _score_band(composite),
                "going_group":    _going_group(going),
                "dist_group":     _dist_group(dist_f),
                "margin":         round(margin, 2),
                "n_scored":       len(scored),
            }
            all_records.append(record)

            # Track best qualifying pick for the day — apply same filters as live model
            _excluded = (
                not args.include_jumps
                and any(x in (race_type or "").lower() for x in NAP_EXCLUDED_RACE_TYPES)
            )
            _too_short = (
                top.get("morning_price") is not None
                and top["morning_price"] < NAP_MIN_ODDS
            )
            _too_big = (
                top.get("morning_price") is not None
                and top["morning_price"] > NAP_MAX_ODDS
            )
            _is_flat = not any(x in (race_type or "").lower() for x in ("chase", "hurdle", "bumper"))
            _dist_filtered = _is_flat and dist_f >= args.max_flat_dist
            _sprint_filtered = _is_flat and 0.0 < dist_f < FLAT_MIN_DIST_F
            _going_filtered = _is_flat and going_normalise(top.get("going") or "") in FLAT_EXCLUDED_GOING
            _clustered = detect_race_cluster(scored)
            _dangerous = "dangerous_drift" in (top.get("warnings") or [])
            if (composite >= args.min_score and composite <= NAP_MAX_SCORE
                    and composite > best_day_score
                    and not _excluded and not _too_short and not _too_big and not _dist_filtered
                    and not _sprint_filtered and not _going_filtered
                    and not _clustered and not _dangerous):
                best_day_score  = composite
                best_day_record = record

            # Rank-promotion candidate (the NEW live rule): below the floor but
            # the clear leader of a competitive race, passing every structural
            # gate AND priced (live diverts unpriced horses to fallback only).
            _structurally_ok = (
                not _excluded and not _too_big and not _too_short
                and not _dist_filtered and not _sprint_filtered
                and not _going_filtered and not _dangerous
                and top.get("morning_price") is not None
            )
            if (_structurally_ok
                    and len(scored) >= 2
                    and composite < args.min_score
                    and composite >= RANK_PROMOTION_MIN_SCORE
                    and margin >= args.clear_margin
                    and composite > best_promoted_score):
                best_promoted_score  = composite
                best_promoted_record = record

        if best_day_record:
            daily_naps.append(best_day_record)
            days_with_nap += 1
        elif best_promoted_record:
            # In live selection a promoted pick only becomes NAP when no horse
            # cleared the floor — so B-only picks occur exactly on A-blank days.
            promoted_naps.append(best_promoted_record)

    if not all_records:
        print("No records collected — check API credentials and date range.")
        return 1

    print(f"\nDays with data: {days_data}  |  Days with NAP: {days_with_nap}  |  No data: {days_no_data}")

    # --- Aggregate ----------------------------------------------------------------
    def _breakdown(records: list[dict], key: str) -> dict[str, _Stats]:
        bd: dict[str, _Stats] = defaultdict(_Stats)
        for r in records:
            bd[r.get(key, "?")].record(r["is_win"], r["is_place"], r["sp_dec"], r["has_result"])
        return dict(bd)

    # Selections = top scorer per race where score >= min_score
    selections = [r for r in all_records if r["score"] >= args.min_score]

    bd_type  = _breakdown(selections, "type_group")
    bd_class = _breakdown(selections, "class_group")
    bd_going = _breakdown(selections, "going_group")
    bd_dist  = _breakdown(selections, "dist_group")
    bd_score = _breakdown(all_records, "score_band")  # all scores — shows where value lies

    nap_stats = _Stats()
    for r in daily_naps:
        nap_stats.record(r["is_win"], r["is_place"], r["sp_dec"], r["has_result"])

    # Rank-promotion A/B: what the new live rule would have added on days the
    # floor-only model went blank, plus a margin-band split to tune the margin.
    promoted_stats = _Stats()
    promoted_by_margin: dict[str, _Stats] = defaultdict(_Stats)
    for r in promoted_naps:
        promoted_stats.record(r["is_win"], r["is_place"], r["sp_dec"], r["has_result"])
        m = r.get("margin", 0.0)
        band = (f"+{args.clear_margin:.1f}-{args.clear_margin * 1.5:.1f}" if m < args.clear_margin * 1.5
                else f"+{args.clear_margin * 1.5:.1f}-{args.clear_margin * 2:.1f}" if m < args.clear_margin * 2
                else f"+{args.clear_margin * 2:.1f}+")
        promoted_by_margin[band].record(r["is_win"], r["is_place"], r["sp_dec"], r["has_result"])
    combined_stats = _Stats()
    for r in daily_naps + promoted_naps:
        combined_stats.record(r["is_win"], r["is_place"], r["sp_dec"], r["has_result"])

    # --- Findings (auto-identify best/worst) ----------------------------------------
    def _best_worst(bd: dict[str, _Stats], min_n: int = 5):
        valid = [(k, v) for k, v in bd.items() if v.n >= min_n]
        if not valid: return None, None
        best = max(valid, key=lambda kv: kv[1].win_pct)
        worst = min(valid, key=lambda kv: kv[1].win_pct)
        return best, worst

    type_best,  type_worst  = _best_worst(bd_type)
    class_best, class_worst = _best_worst(bd_class)
    score_best, score_worst = _best_worst(bd_score, min_n=3)

    # --- Format report -----------------------------------------------------------
    sep = "=" * 70
    lines = [
        sep,
        "  NAP MODEL BACKTEST REPORT",
        f"  Period:     {start_str}  to  {end_str}",
        f"  Days:       {days_data} with race data  /  {days_no_data} no data",
        f"  Threshold:  score >= {args.min_score}",
        f"  Generated:  {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        sep,
        "",
        ("  NOTE: DEEP mode — suitability uses real per-horse form (point-in-time),"
         if args.deep else
         "  NOTE: Suitability = form-string fallback (no full_form fetch)."),
        ("  so scores match the live 0-100 scale. Market = racecard odds only."
         if args.deep else
         "  Market = racecard odds only, no movement data."),
        "  Composite max ≈ 95 pts in backtest vs 100 in live model.",
        "",
    ]

    # Daily NAP block
    lines += [
        "DAILY NAP (1 selection per day — highest scorer across all races)",
        "-" * 70,
        f"  Days with NAP pick:  {days_with_nap} of {days_data}  "
        f"({days_with_nap/max(days_data,1)*100:.0f}% selection rate)",
        f"  NAPs with result:    {nap_stats.n}",
        f"  Wins:                {nap_stats.wins}  ({nap_stats.win_pct:.1f}%)",
        f"  Places (top 3):      {nap_stats.places}  ({nap_stats.place_pct:.1f}%)",
        f"  Level-stakes P/L:    {nap_stats.pl:+.1f} pts",
        f"  ROI:                 {nap_stats.roi:+.1f}%",
        "",
    ]

    # Rank-promotion A/B block
    lines += [
        f"RANK-PROMOTION A/B  (new live rule: leader by >= {args.clear_margin:.1f} pts, "
        f"score >= {RANK_PROMOTION_MIN_SCORE:.0f}, on floor-blank days)",
        "-" * 70,
        f"  A — floor-only (above):       {nap_stats.n} picks, "
        f"{nap_stats.win_pct:.1f}% win, ROI {nap_stats.roi:+.1f}%",
        f"  Promoted picks ADDED by B:    {promoted_stats.n} "
        f"(on {len(promoted_naps)} previously-blank days)",
    ]
    if promoted_stats.n:
        lines += [
            f"    Wins:              {promoted_stats.wins}  ({promoted_stats.win_pct:.1f}%)",
            f"    Places (top 3):    {promoted_stats.places}  ({promoted_stats.place_pct:.1f}%)",
            f"    Level-stakes P/L:  {promoted_stats.pl:+.1f} pts",
            f"    ROI:               {promoted_stats.roi:+.1f}%",
            f"  B — combined:                 {combined_stats.n} picks, "
            f"{combined_stats.win_pct:.1f}% win, ROI {combined_stats.roi:+.1f}%",
            "",
            "  Promoted picks by margin over 2nd (tunes nap_clear_margin):",
        ]
        lines += _render_table(dict(promoted_by_margin))
        verdict = ("KEEP — promoted picks add profit"
                   if promoted_stats.roi > 0 else
                   "ACCEPTABLE — adds coverage at small cost; consider a higher --clear-margin"
                   if promoted_stats.roi > -15 else
                   "RECONSIDER — promoted picks lose heavily; raise nap_clear_margin or "
                   "RANK_PROMOTION_MIN_SCORE")
        lines.append(f"  ► Verdict: {verdict}")
    else:
        lines.append("  (no promoted picks in this window — rule never fired)")
    lines.append("")

    # Per-category tables
    lines.append(f"RACE TYPE BREAKDOWN  (top scorer per race, score >= {args.min_score})")
    lines.append("-" * 70)
    lines += _render_table(bd_type)
    lines.append("")

    lines.append("RACE CLASS BREAKDOWN")
    lines.append("-" * 70)
    lines += _render_table(bd_class)
    lines.append("")

    lines.append("SCORE BAND BREAKDOWN  (top scorer per race, ALL scores — find threshold)")
    lines.append("-" * 70)
    lines += _render_table(bd_score)
    lines.append("")

    lines.append("GOING BREAKDOWN")
    lines.append("-" * 70)
    lines += _render_table(bd_going)
    lines.append("")

    lines.append("DISTANCE BREAKDOWN")
    lines.append("-" * 70)
    lines += _render_table(bd_dist)
    lines.append("")

    # Findings block
    lines.append("FINDINGS & TUNING SUGGESTIONS")
    lines.append("-" * 70)

    if type_best and type_worst:
        tb_name, tb_s = type_best
        tw_name, tw_s = type_worst
        lines.append(f"  Race type:  Best  → {tb_name} ({tb_s.win_pct:.1f}% strike, {tb_s.roi:+.1f}% ROI)")
        lines.append(f"              Worst → {tw_name} ({tw_s.win_pct:.1f}% strike, {tw_s.roi:+.1f}% ROI)")
        if tw_s.roi < -15:
            lines.append(f"  ► Consider filtering OUT {tw_name} races from NAP selection.")

    if class_best and class_worst:
        cb_name, cb_s = class_best
        cw_name, cw_s = class_worst
        lines.append(f"  Race class: Best  → {cb_name} ({cb_s.win_pct:.1f}%, ROI {cb_s.roi:+.1f}%)")
        lines.append(f"              Worst → {cw_name} ({cw_s.win_pct:.1f}%, ROI {cw_s.roi:+.1f}%)")
        if cw_s.roi < -15:
            lines.append(f"  ► Consider excluding {cw_name} from NAP pool.")

    if score_best:
        sb_name, sb_s = score_best
        lines.append(f"  Score band: Best performing band → {sb_name} ({sb_s.win_pct:.1f}% win, ROI {sb_s.roi:+.1f}%)")
        # Find lowest profitable band
        profitable = [
            (k, v) for k, v in bd_score.items()
            if v.n >= 3 and v.roi > -5
        ]
        if profitable:
            lowest = min(profitable, key=lambda kv: kv[0])
            lines.append(f"  ► Suggested minimum threshold band: {lowest[0]}")

    lines.append("")
    lines.append(sep)

    report_text = "\n".join(lines)

    # --- Write outputs -----------------------------------------------------------
    tag = f"{start_str}_to_{end_str}" + ("_deep" if args.deep else "")

    report_dest = report_path(f"backtest_{tag}.txt")
    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
    except OSError as exc:
        log(f"backtest: write report failed — {exc}", "ERROR"); return 1

    csv_dest = data_path(f"backtest_{tag}.csv")
    try:
        if all_records:
            with open(csv_dest, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(all_records[0].keys()))
                writer.writeheader()
                writer.writerows(all_records)
    except OSError as exc:
        log(f"backtest: write CSV failed — {exc}", "WARNING")

    print("\n" + report_text)
    print(f"\nReport: {report_dest}")
    print(f"CSV:    {csv_dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
