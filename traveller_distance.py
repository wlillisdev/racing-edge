"""
traveller_distance.py — compute every runner's travel (trainer yard -> course)
NATIVELY from the Standard card's `trainer_location`. No scraping, full coverage,
every meeting. 'Longest traveller' becomes our own signal.

Geocoding: OpenStreetMap Nominatim, cached to data/geo_cache.json — every town
and course resolves ONCE, then it's free. Distance is great-circle miles with a
1.2x road factor (rough), which is plenty for RANKING who travelled furthest.

Writes data/longest_travellers_DATE.json in the SAME shape the matcher/checker
already read, so it drops in for the freebets scrape. Each runner carries:
  miles, longest_in_race, longest_in_meeting, long_haul (>= LONG_HAUL_MILES)

Usage:  python traveller_distance.py [YYYY-MM-DD]
"""

from __future__ import annotations

import math
import sys
import time
from typing import Optional

from src.helpers import data_path, log, safe_load_json, safe_write_json, today_str

_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_UA = {"User-Agent": "racing-edge/1.0 (longest-traveller signal)"}
_ROAD_FACTOR = 1.2                 # straight-line -> approx road miles
LONG_HAUL_MILES = 150.0            # "came a long way" threshold (guide)

_cache: Optional[dict] = None


def _load_cache() -> dict:
    global _cache
    if _cache is None:
        _cache = safe_load_json(data_path("geo_cache.json")) or {}
    return _cache


def geocode(query: str) -> Optional[tuple]:
    """(lat, lon) for a place, cached forever. None if unresolved/unreachable."""
    if not query or not query.strip():
        return None
    cache = _load_cache()
    key = query.strip().lower()
    if key in cache:                      # includes cached misses (None)
        v = cache[key]
        return tuple(v) if v else None

    import requests
    coord = None
    try:
        r = requests.get(_NOMINATIM,
                         params={"q": f"{query}, UK", "format": "json", "limit": 1},
                         headers=_UA, timeout=15)
        time.sleep(1.0)                   # Nominatim politeness (1 req/sec)
        if r.status_code == 200 and r.json():
            d = r.json()[0]
            coord = (float(d["lat"]), float(d["lon"]))
        else:
            log(f"traveller_distance: no geocode for '{query}' (HTTP {r.status_code})", "INFO")
    except Exception as exc:              # noqa: BLE001 — network/blocked: cache the miss
        log(f"traveller_distance: geocode error for '{query}' — {exc}", "WARNING")

    cache[key] = list(coord) if coord else None
    safe_write_json(data_path("geo_cache.json"), cache)
    return coord


def haversine_miles(a: tuple, b: tuple) -> float:
    (la1, lo1), (la2, lo2) = a, b
    R = 3958.8
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = math.radians(la2 - la1), math.radians(lo2 - lo1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def compute(date_str: Optional[str] = None) -> dict:
    date_str = date_str or today_str()
    rc = safe_load_json(data_path(f"racecards_{date_str}.json")) or {}
    races = rc.get("racecards") or []

    # Dedupe geocode targets first (one network call per unique place, ever).
    courses = {r.get("course") for r in races if r.get("course")}
    locs = {run.get("trainer_location")
            for r in races for run in (r.get("runners") or [])
            if run.get("trainer_location")}
    course_xy = {c: geocode(f"{c} Racecourse") for c in courses}
    loc_xy = {l: geocode(l) for l in locs}

    travellers: list[dict] = []
    by_course_max: dict[str, float] = {}
    for race in races:
        course = race.get("course") or ""
        cc = course_xy.get(course)
        if not cc:
            continue
        race_runs: list[dict] = []
        for run in (race.get("runners") or []):
            loc = run.get("trainer_location")
            tc = loc_xy.get(loc)
            if not tc:
                continue
            miles = round(haversine_miles(tc, cc) * _ROAD_FACTOR)
            rec = {"horse": run.get("horse"), "horse_id": run.get("horse_id"),
                   "trainer": run.get("trainer"), "base": loc,
                   "course": course, "off_time": race.get("off_time"),
                   "miles": miles, "longest_in_race": False,
                   "longest_in_meeting": False,
                   "long_haul": miles >= LONG_HAUL_MILES}
            race_runs.append(rec)
            by_course_max[course] = max(by_course_max.get(course, 0), miles)
        if race_runs:
            top = max(race_runs, key=lambda x: x["miles"])
            top["longest_in_race"] = True
            travellers.extend(race_runs)

    for t in travellers:
        if t["miles"] == by_course_max.get(t["course"]):
            t["longest_in_meeting"] = True

    travellers.sort(key=lambda x: -x["miles"])
    doc = {"date": date_str, "source": "native(trainer_location)", "travellers": travellers}
    safe_write_json(data_path(f"longest_travellers_{date_str}.json"), doc)
    n_geo = sum(1 for v in {**course_xy, **loc_xy}.values() if v)
    log(f"traveller_distance: {len(travellers)} runners over {len(course_xy)} courses "
        f"({n_geo} places geocoded)")
    return doc


def main() -> int:
    doc = compute(sys.argv[1] if len(sys.argv) > 1 else None)
    ts = doc["travellers"]
    if not ts:
        print("No travellers computed — geocoding may be blocked (check geo_cache.json) "
              "or no racecard for the date.")
        return 1
    print(f"NATIVE LONGEST TRAVELLERS — {doc['date']} — {len(ts)} runners")
    print("-" * 70)
    for t in ts[:20]:
        tags = []
        if t["longest_in_meeting"]:
            tags.append("◀ furthest to meeting")
        elif t["longest_in_race"]:
            tags.append("◀ furthest in race")
        if t["long_haul"]:
            tags.append("long haul")
        print(f"  {t['miles']:>4} mi  {t['horse']:<22} {t['trainer']:<18} "
              f"-> {t['course']:<11} {' · '.join(tags)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
