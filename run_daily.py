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
    """Coerce *value* to str, falling back to *default* for None/falsy."""
    if value is None:
        return default
    return str(value)


def _safe_float(value: object, default: float = 0.0) -> float:
    """Coerce *value* to float, returning *default* on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: object, default: int = 0) -> int:
    """Coerce *value* to int, returning *default* on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalise_runner(raw: dict) -> dict:
    """Map a raw runner dict from the Racing API into the canonical runner schema."""
    return {
        "horse_id":   _safe_str(raw.get("horse_id")),
        "horse":      _safe_str(raw.get("horse")),
        "trainer":    _safe_str(raw.get("trainer")),
        "jockey":     _safe_str(raw.get("jockey")),
        "age":        _safe_str(raw.get("age")),
        "sex":        _safe_str(raw.get("sex")),
        "number":     _safe_int(raw.get("number")),
        "draw":       _safe_int(raw.get("draw")),
        "weight_lbs": _safe_int(raw.get("weight_lbs")),
        "ofr":        _safe_str(raw.get("ofr")),
        "rpr":        _safe_str(raw.get("rpr")),
        "ts":         _safe_str(raw.get("ts")),
        "sp_dec":     _safe_float(raw.get("sp_dec")),
        "form":       _safe_str(raw.get("form")),
        "last_run":   _safe_int(raw.get("last_run"), default=-1),
    }


def _normalise_racecard(raw: dict) -> dict:
    """Map a raw racecard dict from the Racing API into the canonical racecard schema."""
    runners_raw: list[dict] = raw.get("runners") or []
    runners = [_normalise_runner(r) for r in runners_raw]

    return {
        "race_id":    _safe_str(raw.get("race_id")),
        "course":     _safe_str(raw.get("course")),
        "off_time":   _safe_str(raw.get("off_time")),
        "race_name":  _safe_str(raw.get("title") or raw.get("race_name")),
        "class":      _safe_str(raw.get("class")),
        "distance_f": _safe_float(raw.get("distance_f")),
        "going":      _safe_str(raw.get("going")),
        "surface":    _safe_str(raw.get("surface")),
        "type":       _safe_str(raw.get("type")),
        "region":     _safe_str(raw.get("region")),
        "field_size": _safe_int(raw.get("field_size") or len(runners)),
        "runners":    runners,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Fetch racecards, normalise, and persist. Returns exit code."""
    log("run_daily.py started")

    # --- Config ---------------------------------------------------------------
    try:
        cfg = get_config()
    except KeyError as exc:
        log(f"Configuration error — missing env var: {exc}", "ERROR")
        return 1

    date_str = today_str()
    log(f"Fetching racecards for {date_str}, regions={cfg.regions}")

    # --- API call -------------------------------------------------------------
    try:
        client = get_client()
        raw_response = client.get_racecards(day="today", region_codes=cfg.regions)
    except Exception as exc:
        log(f"API call failed: {exc}", "ERROR")
        return 1

    if not raw_response:
        log("API returned empty response — aborting", "ERROR")
        return 1

    # --- Normalise ------------------------------------------------------------
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

    # --- Persist --------------------------------------------------------------
    filename = f"racecards_{date_str}.json"
    dest = data_path(filename)

    if not safe_write_json(dest, payload):
        log(f"Failed to write racecard file to {dest}", "ERROR")
        return 1

    log(f"Saved {len(racecards)} races to {dest}")

    # --- Summary to stdout ----------------------------------------------------
    print(f"\nSummary: {len(racecards)} races, {total_runners} runners fetched for {date_str}")
    print(f"Saved to: {dest}")

    log("run_daily.py completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
