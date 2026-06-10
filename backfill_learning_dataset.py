"""
backfill_learning_dataset.py — jump-start the learning loop with real history.

The nightly learner (daily_learning_analysis.py) + supervised tuner
(model_param_tuner.py) only act once data/learning_dataset.csv holds enough
labelled rows (MIN_SAMPLE=30 to propose, MIN_SAMPLE_AUTO=50 to auto-apply).
Grown one evening at a time, that is weeks away. This script backfills months
of history in one run so the learner can start tonight.

It is deliberately built ON the existing, proven pieces so the backfilled rows
are byte-compatible with what the live loop writes every evening:

    - fetch historical cards + results : historical_backtest._fetch_racecard /
      _fetch_results_per_race (cached under data/backtest_cache/)
    - score every runner               : nap_selector_v3.score_runner (the SAME
      scorer the live model uses — full_form/market_movers/AI absent, exactly
      as historical_backtest replays it)
    - schema + outcome maths           : daily_outcome_join.CSV_COLUMNS,
      _parse_position, _parse_sp, _pnl_1pt, _append_csv (idempotent, de-duped
      by (date,race_id,horse_id) against the live file)

So running this is equivalent to having run the evening join every day across
the window — one row per runner per race, joined to its real result.

Usage:
    python backfill_learning_dataset.py                       # last 3 months
    python backfill_learning_dataset.py --months 6
    python backfill_learning_dataset.py --start 2025-09-01 --end 2026-06-01

Notes:
    - It fetches ~1 card call + ~1 result call PER RACE per day; with the 0.6s
      API delay a 3-month window is ~30-40 min the FIRST time, then near-instant
      (everything is cached). Start small (--months 2) to sanity-check.
    - Appends to the SAME data/learning_dataset.csv the live loop uses, and is
      idempotent — safe to re-run or to overlap with live evenings.

Exit codes:
    0 — completed (rows appended or already present)
    1 — fatal error (config, no client, write failure)
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta

from src.config import get_config
from src.helpers import data_path, log
from src.api_client import get_client
from nap_selector_v3 import score_runner
from historical_backtest import _fetch_racecard, _fetch_results_per_race
from daily_outcome_join import (
    CSV_COLUMNS,
    LARGE_FIELD_FOR_TOP3,
    _append_csv,
    _parse_position,
    _parse_sp,
    _pnl_1pt,
)

LEARNING_CSV = "learning_dataset.csv"


def _iter_dates(start: date, end: date):
    """Yield each date from start to end inclusive."""
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _outcome_for(horse_id: str, results_lookup: dict, field_size: int) -> dict:
    """Compute {finish_position, won, placed, sp_decimal, pnl_1pt} for a horse.

    Mirrors daily_outcome_join exactly: place cutoff is top-3 for fields >= 8,
    else top-2; pnl is a flat 1pt win stake at SP. Unresolved horses (no result
    row) get all-None outcomes, identical to the live join.
    """
    res = results_lookup.get(horse_id)
    if not res:
        return {
            "finish_position": None, "won": None, "placed": None,
            "sp_decimal": None, "pnl_1pt": None,
        }
    pos = _parse_position(res.get("position"))
    sp = _parse_sp(res.get("sp_dec"))
    won = pos == 1
    cutoff = 3 if field_size >= LARGE_FIELD_FOR_TOP3 else 2
    placed = pos is not None and pos <= cutoff
    return {
        "finish_position": pos,
        "won": won,
        "placed": placed,
        "sp_decimal": sp,
        "pnl_1pt": _pnl_1pt(won, sp),
    }


def _rows_for_day(date_str: str, races: list[dict], results_lookup: dict) -> list[dict]:
    """Score every runner in every race for one day and build CSV rows.

    Returns a list of dicts keyed by CSV_COLUMNS. is_nap flags the single
    highest-scoring runner across the whole day's card (the day's would-be NAP),
    a faithful proxy for the live one-NAP-per-day flag.
    """
    day_rows: list[dict] = []
    best_score = float("-inf")
    best_key = None  # (race_id, horse_id) of the day's top-scored runner

    for race in races:
        runners = race.get("runners") or []
        if not runners:
            continue
        field_size = len(runners)

        scored = []
        for runner in runners:
            try:
                s = score_runner(
                    runner=runner,
                    race=race,
                    all_runners=runners,
                    full_form=None,       # fallback suitability (as in backtest)
                    market_movers=None,   # no historical movement data
                )
                scored.append(s)
            except Exception as exc:
                log(f"backfill: score_runner error {date_str} {race.get('race_id')} — {exc}", "WARNING")
        if not scored:
            continue

        scored.sort(key=lambda x: -x["score"])
        race_id = race.get("race_id", "")
        race_type = race.get("type", "")
        going = race.get("going", "")
        course = race.get("course", "")
        distance_f = race.get("distance_f")

        for rank, s in enumerate(scored, start=1):
            horse_id = str(s.get("horse_id") or "")
            if not horse_id:
                continue
            if s["score"] > best_score:
                best_score = s["score"]
                best_key = (race_id, horse_id)
            outcome = _outcome_for(horse_id, results_lookup, field_size)
            day_rows.append({
                "date": date_str,
                "race_id": race_id,
                "course": course,
                "race_type": race_type,
                "going": going,
                "distance_f": distance_f,
                "horse_id": horse_id,
                "horse": s.get("horse"),
                "rank_in_race": rank,
                "score": s.get("score"),
                "grade": s.get("grade"),
                "form_score": s.get("form_score"),
                "suitability_score": s.get("suitability_score"),
                "context_score": s.get("context_score"),
                "draw_score": s.get("draw_score", 0.0),
                "trainer_score": s.get("trainer_score"),
                "market_score": s.get("market_score"),
                "wisdom_score": s.get("wisdom_score", 0.0),
                "ai_rating": None,   # no AI form-read in historical replay
                "pace_fit": None,    # no AI pace projection in historical replay
                "morning_price": s.get("morning_price"),
                "is_nap": 0,         # set below for the day's top-scored runner
                **outcome,
            })

    # Flag the day's single highest-scoring runner as the would-be NAP.
    if best_key is not None:
        for row in day_rows:
            if (row["race_id"], row["horse_id"]) == best_key:
                row["is_nap"] = 1
                break

    return day_rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill the learning dataset from history.")
    parser.add_argument("--months", type=int, default=3, help="Window size in months (default 3).")
    parser.add_argument("--start", type=str, default=None, help="Start date YYYY-MM-DD (overrides --months).")
    parser.add_argument("--end", type=str, default=None, help="End date YYYY-MM-DD (default yesterday).")
    args = parser.parse_args()

    log("backfill_learning_dataset.py started")

    try:
        cfg = get_config()
    except KeyError as exc:
        log(f"backfill: missing config key {exc}", "ERROR")
        return 1

    # Resolve the window. Results only exist for past days, so end defaults to
    # yesterday.
    end = (
        datetime.strptime(args.end, "%Y-%m-%d").date()
        if args.end else (date.today() - timedelta(days=1))
    )
    start = (
        datetime.strptime(args.start, "%Y-%m-%d").date()
        if args.start else (end - timedelta(days=args.months * 30))
    )
    if start > end:
        log(f"backfill: start {start} is after end {end} — nothing to do", "ERROR")
        return 1

    log(f"backfill: window {start} → {end} ({(end - start).days + 1} days), regions={cfg.regions}")

    try:
        client = get_client()
    except Exception as exc:
        log(f"backfill: could not build API client — {exc}", "ERROR")
        return 1

    csv_path = data_path(LEARNING_CSV)
    total_rows = 0
    total_appended = 0
    days_with_data = 0

    for d in _iter_dates(start, end):
        date_str = d.isoformat()
        races = _fetch_racecard(date_str, client, cfg)
        if not races:
            continue
        results_lookup = _fetch_results_per_race(races, client)
        rows = _rows_for_day(date_str, races, results_lookup)
        if not rows:
            continue
        days_with_data += 1
        total_rows += len(rows)
        ok, appended = _append_csv(csv_path, rows)
        if not ok:
            log(f"backfill: CSV append failed on {date_str} — aborting", "ERROR")
            return 1
        total_appended += appended
        log(f"backfill: {date_str} — {len(rows)} rows ({appended} new)")

    labelled = "see CSV"
    summary = (
        f"backfill: DONE — {days_with_data} race-days, {total_rows} rows built, "
        f"{total_appended} new rows appended to {csv_path}"
    )
    log(summary)
    print(summary)
    print("Next: run `python daily_learning_analysis.py` then "
          "`python learning_control.py status` to see proposals.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
