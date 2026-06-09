"""
run_daily.py — Pull today's racecards from the Racing API and save to disk.

Usage (PythonAnywhere scheduled task):
    python run_daily.py

Exit codes:
    0  — success
    1  — failure (API error, write error)
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from src.config import get_config
from src.helpers import data_path, log, safe_write_json, today_str
from src.api_client import get_client


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _safe_str(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalise_runner(raw: dict) -> dict:
    last_run_raw = raw.get("last_run")
    try:
        last_run: int | None = int(last_run_raw) if last_run_raw is not None else None
    except (TypeError, ValueError):
        last_run = None
    return {
        "horse_id":         _safe_str(raw.get("horse_id")),
        "horse":            _safe_str(raw.get("horse")),
        "trainer":          _safe_str(raw.get("trainer")),
        "trainer_id":       _safe_str(raw.get("trainer_id")),
        "jockey":           _safe_str(raw.get("jockey")),
        "jockey_id":        _safe_str(raw.get("jockey_id")),
        "age":              _safe_str(raw.get("age")),
        "sex":              _safe_str(raw.get("sex")),
        "number":           _safe_int(raw.get("number")),
        "draw":             _safe_int(raw.get("draw")),
        "weight_lbs":       _safe_int(raw.get("weight_lbs")),
        "lbs":              _safe_int(raw.get("lbs")),
        "ofr":              _safe_str(raw.get("ofr")),
        "rpr":              _safe_str(raw.get("rpr")),
        "ts":               _safe_str(raw.get("ts")),
        "sp_dec":           _safe_float(raw.get("sp_dec")),
        "form":             _safe_str(raw.get("form")),
        "last_run":         last_run,
        "odds":             raw.get("odds") or [],
        "headgear":         _safe_str(raw.get("headgear")),
        "headgear_run":     _safe_str(raw.get("headgear_run")),
        "wind_surgery_run": _safe_str(raw.get("wind_surgery_run")),
        "wind_surgery":     _safe_str(raw.get("wind_surgery")),
        "trainer_14_days":  raw.get("trainer_14_days") if isinstance(raw.get("trainer_14_days"), dict) else {},
        "trainer_rtf":      _safe_str(raw.get("trainer_rtf")),
        "spotlight":        _safe_str(raw.get("spotlight")),
        "comment":          _safe_str(raw.get("comment")),
        "quotes":           _safe_str(raw.get("quotes")),
        "stable_tour":      _safe_str(raw.get("stable_tour")),
        "prev_trainers":      raw.get("prev_trainers") or [],
        "past_results_flags": raw.get("past_results_flags") or [],
        "medical":            raw.get("medical") or [],
        # Note: jockey_14_days does NOT exist in the Racing API Pro racecard schema
    }


def _normalise_racecard(raw: dict) -> dict:
    runners_raw: list[dict] = raw.get("runners") or []
    runners = [_normalise_runner(r) for r in runners_raw]
    return {
        "race_id":          _safe_str(raw.get("race_id")),
        "course":           _safe_str(raw.get("course")),
        "off_time":         _safe_str(raw.get("off_time")),
        "race_name":        _safe_str(raw.get("title") or raw.get("race_name")),
        "class":            _safe_str(raw.get("class") or raw.get("race_class")),
        "distance_f":       _safe_float(raw.get("distance_f") or raw.get("dist_f")),
        "going":            _safe_str(raw.get("going")),
        "going_detailed":   _safe_str(raw.get("going_detailed")),
        "surface":          _safe_str(raw.get("surface")),
        "type":             _safe_str(raw.get("type")),
        "region":           _safe_str(raw.get("region")),
        "field_size":       _safe_int(raw.get("field_size") or len(runners)),
        "rail_movements":   _safe_str(raw.get("rail_movements")),
        "stalls":           _safe_str(raw.get("stalls")),
        "weather":          _safe_str(raw.get("weather")),
        "age_band":         _safe_str(raw.get("age_band")),
        "rating_band":      _safe_str(raw.get("rating_band")),
        "pattern":          _safe_str(raw.get("pattern")),
        "sex_restriction":  _safe_str(raw.get("sex_restriction")),
        "verdict":          _safe_str(raw.get("verdict")),
        "betting_forecast": _safe_str(raw.get("betting_forecast")),
        "runners":          runners,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    log("run_daily.py started")

    try:
        cfg = get_config()
    except KeyError as exc:
        log(f"Configuration error — missing env var: {exc}", "ERROR")
        return 1

    date_str = today_str()
    log(f"Fetching racecards for {date_str}, regions={cfg.regions}")

    try:
        client = get_client()
        raw_response = client.get_racecards(day="today", region_codes=cfg.regions)
    except Exception as exc:
        log(f"API call failed: {exc}", "ERROR")
        return 1

    if not raw_response:
        log("API returned empty response — aborting", "ERROR")
        return 1

    raw_racecards: list[dict] = raw_response.get("racecards") or []

    if not raw_racecards:
        log("No racecards found in API response — aborting", "ERROR")
        return 1

    racecards = [_normalise_racecard(rc) for rc in raw_racecards]
    total_runners = sum(len(rc["runners"]) for rc in racecards)

    payload: dict = {
        "date":       date_str,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "region":     cfg.regions,
        "race_count": len(racecards),
        "racecards":  racecards,
    }

    filename = f"racecards_{date_str}.json"
    dest = data_path(filename)

    if not safe_write_json(dest, payload):
        log(f"Failed to write racecard file to {dest}", "ERROR")
        return 1

    log(f"Saved {len(racecards)} races to {dest}")
    print(f"\nSummary: {len(racecards)} races, {total_runners} runners fetched for {date_str}")
    print(f"Saved to: {dest}")
    log("run_daily.py completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
