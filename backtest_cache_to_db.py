"""
backtest_cache_to_db.py — hydrate the MySQL warehouse from the backtest cache.

historical_backtest.py writes deep history to disk only
(data/backtest_cache/{racecards,race_results}/), never to the database. This
importer loads that cache and upserts it into the `races`, `runners` and
`results` tables so the full history is queryable in SQL for the learning loop
(joining selections to outcomes, running angles, etc.).

It is idempotent — every write is INSERT … ON DUPLICATE KEY UPDATE on the
tables' unique keys (races.race_id, runners(race_id,horse_id),
results(race_id,horse_id)) — so re-running only refreshes, never duplicates.

Run it on PythonAnywhere (where the DB is reachable), after or during a pull:

    python backtest_cache_to_db.py --dry-run     # count only, no writes
    python backtest_cache_to_db.py               # import everything in the cache
    python backtest_cache_to_db.py --since 2025-01-01

Reads only the cache; it does not call the Racing API.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path
from typing import Optional

from src.db import get_db
from src.helpers import data_path, going_normalise, log

CACHE = Path(data_path("backtest_cache"))
CHUNK = 500  # rows per executemany batch


# --- parsing helpers --------------------------------------------------------
def _i(v) -> Optional[int]:
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        return None
    return None if n < 0 else n   # cache uses -1 as "missing"


def _pos_i(v) -> Optional[int]:
    """Finishing position — '1','2',… ; non-numeric (F/P/U/'') → None."""
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _f(v) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x > 0 else None


def _s(v) -> Optional[str]:
    s = str(v).strip() if v is not None else ""
    return s or None


def _load(p: str) -> dict:
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


# --- collection -------------------------------------------------------------
def collect(since: Optional[str]):
    """Return (races, runners, results) row lists plus maps for joining."""
    races: list[tuple] = []
    runners: list[tuple] = []
    race_date: dict[str, str] = {}
    horse_name: dict[tuple, str] = {}

    for p in sorted(glob.glob(str(CACHE / "racecards" / "*.json"))):
        date = Path(p).stem
        if since and date < since:
            continue
        for race in _load(p).get("races", []):
            rid = _s(race.get("race_id"))
            if not rid:
                continue
            race_date[rid] = date
            races.append((
                rid, date, _s(race.get("course")), _s(race.get("region")),
                _s(race.get("race_name")), _s(race.get("class")),
                _s(race.get("type")), _f(race.get("distance_f")),
                going_normalise(race.get("going") or "") or None,
                _s(race.get("surface")), _i(race.get("field_size")) or 0,
            ))
            for r in race.get("runners", []):
                hid = _s(r.get("horse_id"))
                if not hid:
                    continue
                horse_name[(rid, hid)] = _s(r.get("horse"))
                runners.append((
                    rid, hid, _s(r.get("horse")), _s(r.get("trainer")),
                    _s(r.get("jockey")), _s(r.get("age")), _i(r.get("draw")),
                    _i(r.get("ofr")), _i(r.get("rpr")), _i(r.get("ts")),
                    _f(r.get("sp_dec")), _s(r.get("form")), _i(r.get("last_run")),
                ))

    results: list[tuple] = []
    for p in sorted(glob.glob(str(CACHE / "race_results" / "*.json"))):
        rid = Path(p).stem
        date = race_date.get(rid)
        if not date or (since and date < since):
            continue
        for hid, res in (_load(p).get("runners") or {}).items():
            pos = _pos_i(res.get("position"))
            results.append((
                rid, hid, horse_name.get((rid, hid)), date, pos,
                _f(res.get("sp_dec")),
                1 if pos == 1 else 0,
                1 if pos in (1, 2, 3) else 0,
            ))
    return races, runners, results


# --- SQL --------------------------------------------------------------------
SQL_RACES = """
INSERT INTO races
  (race_id, race_date, course, region, race_name, race_class, race_type,
   distance_f, going, surface, field_size)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE
  race_date=VALUES(race_date), course=VALUES(course), region=VALUES(region),
  race_name=VALUES(race_name), race_class=VALUES(race_class),
  race_type=VALUES(race_type), distance_f=VALUES(distance_f),
  going=VALUES(going), surface=VALUES(surface), field_size=VALUES(field_size)
"""

SQL_RUNNERS = """
INSERT INTO runners
  (race_id, horse_id, horse_name, trainer, jockey, age, draw,
   official_rating, rpr, ts_rating, sp_morning, form_string, last_run_days)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE
  horse_name=VALUES(horse_name), trainer=VALUES(trainer), jockey=VALUES(jockey),
  age=VALUES(age), draw=VALUES(draw), official_rating=VALUES(official_rating),
  rpr=VALUES(rpr), ts_rating=VALUES(ts_rating), sp_morning=VALUES(sp_morning),
  form_string=VALUES(form_string), last_run_days=VALUES(last_run_days)
"""

SQL_RESULTS = """
INSERT INTO results
  (race_id, horse_id, horse_name, result_date, position, sp_decimal, won, placed)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE
  horse_name=VALUES(horse_name), result_date=VALUES(result_date),
  position=VALUES(position), sp_decimal=VALUES(sp_decimal),
  won=VALUES(won), placed=VALUES(placed)
"""


def _upsert(db, sql: str, rows: list[tuple], label: str) -> None:
    for i in range(0, len(rows), CHUNK):
        db.execute_many(sql, rows[i:i + CHUNK])
    print(f"  {label}: {len(rows)} rows upserted")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="Only import dates >= YYYY-MM-DD")
    ap.add_argument("--dry-run", action="store_true", help="Count only; no DB writes")
    args = ap.parse_args()

    if not CACHE.exists():
        print(f"No cache at {CACHE} — run historical_backtest.py first.")
        return 1

    races, runners, results = collect(args.since)
    print(f"Cache scan{' (since ' + args.since + ')' if args.since else ''}: "
          f"{len(races)} races, {len(runners)} runners, {len(results)} results")

    if args.dry_run:
        print("Dry run — no DB writes.")
        return 0

    log("backtest_cache_to_db: importing into races/runners/results")
    db = get_db()
    _upsert(db, SQL_RACES, races, "races")
    _upsert(db, SQL_RUNNERS, runners, "runners")
    _upsert(db, SQL_RESULTS, results, "results")
    print("Done — warehouse hydrated from cache.")
    log("backtest_cache_to_db: complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
