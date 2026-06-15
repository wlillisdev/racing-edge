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

# Fixed course coordinates (lat, lon) — geocoding course names is unreliable,
# and the set is finite. Covers GB + IRE. Obscure/abroad courses fall back to
# geocoding "<name> Racecourse".
COURSE_COORDS: dict[str, tuple] = {
    # GB
    "ascot": (51.41, -0.68), "aintree": (53.47, -2.94), "ayr": (55.46, -4.61),
    "bangor": (52.99, -2.92), "bath": (51.41, -2.42), "beverley": (53.85, -0.45),
    "brighton": (50.83, -0.10), "carlisle": (54.87, -2.96), "cartmel": (54.20, -2.95),
    "catterick": (54.37, -1.65), "chelmsford": (51.76, 0.45), "cheltenham": (51.92, -2.06),
    "chepstow": (51.65, -2.68), "chester": (53.18, -2.89), "doncaster": (53.51, -1.12),
    "epsom": (51.31, -0.26), "exeter": (50.69, -3.47), "fakenham": (52.83, 0.85),
    "ffos las": (51.75, -4.27), "fontwell": (50.85, -0.65), "goodwood": (50.90, -0.74),
    "hamilton": (55.79, -4.06), "haydock": (53.48, -2.63), "hereford": (52.07, -2.74),
    "hexham": (54.96, -2.13), "huntingdon": (52.34, -0.18), "kelso": (55.60, -2.43),
    "kempton": (51.41, -0.41), "leicester": (52.60, -1.10), "lingfield": (51.17, -0.01),
    "ludlow": (52.39, -2.70), "market rasen": (53.39, -0.32), "musselburgh": (55.94, -3.05),
    "newbury": (51.40, -1.30), "newcastle": (55.00, -1.65), "newmarket": (52.24, 0.40),
    "newton abbot": (50.53, -3.61), "nottingham": (52.95, -1.10), "perth": (56.43, -3.42),
    "plumpton": (50.92, -0.04), "pontefract": (53.69, -1.31), "redcar": (54.61, -1.07),
    "ripon": (54.13, -1.50), "salisbury": (51.05, -1.84), "sandown": (51.36, -0.36),
    "sedgefield": (54.65, -1.45), "southwell": (53.08, -0.95), "stratford": (52.18, -1.71),
    "taunton": (51.00, -3.10), "thirsk": (54.23, -1.34), "uttoxeter": (52.89, -1.86),
    "warwick": (52.27, -1.59), "wetherby": (53.94, -1.39), "wincanton": (51.05, -2.40),
    "windsor": (51.48, -0.61), "wolverhampton": (52.59, -2.13), "worcester": (52.19, -2.21),
    "yarmouth": (52.61, 1.71), "york": (53.99, -1.09),
    # IRE
    "ballinrobe": (53.62, -9.22), "bellewstown": (53.70, -6.43), "clonmel": (52.36, -7.71),
    "cork": (51.90, -8.42), "curragh": (53.16, -6.84), "down royal": (54.51, -6.11),
    "downpatrick": (54.33, -5.72), "dundalk": (53.97, -6.43), "fairyhouse": (53.51, -6.42),
    "galway": (53.25, -9.02), "gowran park": (52.63, -7.07), "kilbeggan": (53.36, -7.50),
    "killarney": (52.06, -9.51), "laytown": (53.68, -6.24), "leopardstown": (53.26, -6.17),
    "limerick": (52.60, -8.52), "listowel": (52.45, -9.48), "naas": (53.21, -6.66),
    "navan": (53.66, -6.68), "punchestown": (53.18, -6.62), "roscommon": (53.62, -8.18),
    "sligo": (54.27, -8.47), "thurles": (52.68, -7.81), "tipperary": (52.47, -8.14),
    "tramore": (52.16, -7.15), "wexford": (52.34, -6.47),
}


def _course_coord(name: str) -> Optional[tuple]:
    """Static course coords (strips '(AW)' etc.); geocode fallback for the rest."""
    norm = (name or "").lower().split("(")[0].strip()
    if norm in COURSE_COORDS:
        return COURSE_COORDS[norm]
    return geocode(f"{name} Racecourse")


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
    course_xy = {c: _course_coord(c) for c in courses}
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
