"""
racecard_loader.py — Importable utility module for loading and querying racecard data.

All functions are safe to call even when data files are missing:
    - load_racecard()          returns None
    - get_all_runners()        returns []
    - get_race()               returns None
    - get_runners_for_race()   returns []

Typical usage:
    from racecard_loader import get_all_runners, get_race, get_runners_for_race
"""

from __future__ import annotations

from src.helpers import data_path, log, safe_load_json, today_str


# ---------------------------------------------------------------------------
# Internal cache — avoid re-reading the same file repeatedly within one run.
# ---------------------------------------------------------------------------
_cache: dict[str, dict | None] = {}


def _cache_key(date_str: str | None) -> str:
    return date_str or today_str()


def _load_raw(date_str: str | None) -> dict | None:
    """Internal: load and cache the raw racecard JSON for *date_str*."""
    key = _cache_key(date_str)
    if key not in _cache:
        path = data_path(f"racecards_{key}.json")
        _cache[key] = safe_load_json(path)
        if _cache[key] is None:
            log(f"racecard_loader: no racecard data available for {key}", "WARNING")
    return _cache[key]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_racecard(date_str: str | None = None) -> dict | None:
    """Load racecards for a given date (defaults to today).

    Returns the full racecard dict (with 'racecards' list) or None if the
    file is missing or corrupt.
    """
    return _load_raw(date_str)


def get_all_runners(date_str: str | None = None) -> list[dict]:
    """Return a flat list of every runner for *date_str*, enriched with race context.

    Each runner dict contains all runner fields plus the following race-level
    fields merged in:
        race_id, course, off_time, race_name, class, distance_f, going,
        surface, type, region, field_size

    Returns an empty list if data is unavailable.
    """
    data = _load_raw(date_str)
    if data is None:
        return []

    racecards: list[dict] = data.get("racecards") or []
    flat: list[dict] = []

    # Race-level fields to merge into every runner record.
    race_context_keys = (
        "race_id", "course", "off_time", "race_name", "class",
        "distance_f", "going", "surface", "type", "region", "field_size",
    )

    for race in racecards:
        context = {k: race.get(k) for k in race_context_keys}
        runners: list[dict] = race.get("runners") or []
        for runner in runners:
            merged = {**runner, **context}
            flat.append(merged)

    return flat


def get_race(race_id: str, date_str: str | None = None) -> dict | None:
    """Return a single race dict by race_id, or None if not found."""
    data = _load_raw(date_str)
    if data is None:
        return None

    racecards: list[dict] = data.get("racecards") or []
    for race in racecards:
        if race.get("race_id") == race_id:
            return race

    log(f"racecard_loader.get_race: race_id '{race_id}' not found for "
        f"{_cache_key(date_str)}", "WARNING")
    return None


def get_runners_for_race(race_id: str, date_str: str | None = None) -> list[dict]:
    """Return the runners list for a specific race_id.

    Returns an empty list if the race or data cannot be found.
    """
    race = get_race(race_id, date_str)
    if race is None:
        return []
    return race.get("runners") or []
