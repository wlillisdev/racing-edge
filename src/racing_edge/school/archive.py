"""THE FULL-FIELD ARCHIVE — every result with draw, weight, mark, age, going.

The master, 2026-09-27: "u can test it properly from today, u can get all the
information needed n implement it". The old corpus kept thirteen columns on
scattered days; the favourite model needs every runner's draw, weight,
official rating, age, trainer and jockey, on every day, to know a horse's
past exactly as it learned it.

Two layers, read as one:
  data/archive/results_2026.csv.gz   tracked: 1 Jan - 26 Sep 2026, 9,600 races
  data/archive/live/YYYY-MM-DD.csv   the box's own nightly top-ups (untracked,
                                     box-local, so its pull can never collide)

`update()` runs in the 22:00 night and fills every day from the last one held
up to today — a missed night heals itself the next.

Usage:  PYTHONPATH=src python -m racing_edge.school.archive --update
"""
from __future__ import annotations

import argparse
import csv
import gzip
import sys
from datetime import date, timedelta
from pathlib import Path

ARCHIVE = Path("data/archive/results_2026.csv.gz")
LIVE_DIR = Path("data/archive/live")
RACE_COLS = ["date", "race_id", "course", "region", "type", "class", "pattern",
             "going", "surface", "dist_f"]
RUNNER_COLS = ["horse_id", "position", "sp_dec", "ovr_btn", "draw", "weight_lbs",
               "or", "age", "headgear", "jockey_id", "trainer_id"]
MAX_CATCHUP_DAYS = 14


def _read(fh, races: dict) -> None:
    for row in csv.DictReader(fh):
        r = races.get(row["race_id"])
        if r is None:
            r = races[row["race_id"]] = {k: row.get(k, "") for k in RACE_COLS}
            r["runners"] = []
        elif any(x["horse_id"] == row["horse_id"] for x in r["runners"]):
            continue
        r["runners"].append({k: row.get(k, "") for k in RUNNER_COLS})


def load(archive: Path = ARCHIVE, live_dir: Path = LIVE_DIR) -> list[dict]:
    """Every race held, oldest first, each with its runners. A race in both
    layers is read once."""
    races: dict = {}
    if Path(archive).exists():
        with gzip.open(archive, "rt", newline="") as fh:
            _read(fh, races)
    if Path(live_dir).exists():
        for f in sorted(Path(live_dir).glob("*.csv")):
            with open(f, newline="", encoding="utf-8") as fh:
                _read(fh, races)
    return sorted(races.values(), key=lambda r: (r["date"], r["race_id"]))


def rows_from_results(doc: dict) -> list[list]:
    """The results door's races, flattened to archive rows."""
    out = []
    for r in (doc or {}).get("results") or []:
        for x in r.get("runners") or []:
            out.append([r.get(c, "") or "" for c in RACE_COLS]
                       + [x.get(c, "") or "" for c in RUNNER_COLS])
    return out


def last_day_held(archive: Path = ARCHIVE, live_dir: Path = LIVE_DIR) -> str:
    days = [f.stem for f in Path(live_dir).glob("*.csv")] if Path(live_dir).exists() else []
    if days:
        return max(days)
    races = load(archive, live_dir)
    return races[-1]["date"] if races else "2026-09-26"


def update(client, today: date, live_dir: Path = LIVE_DIR,
           archive: Path = ARCHIVE) -> list[str]:
    """Fetch and write every day after the last held, up to today. A day the
    door answers with no races is still written (header only) so a blank day
    is never refetched forever; an outage raises (the client fails loud)."""
    start = date.fromisoformat(last_day_held(archive, live_dir)) + timedelta(days=1)
    start = max(start, today - timedelta(days=MAX_CATCHUP_DAYS))
    Path(live_dir).mkdir(parents=True, exist_ok=True)
    wrote = []
    d = start
    while d <= today:
        rows = rows_from_results(client.results_by_date(d.isoformat()))
        with open(Path(live_dir) / f"{d.isoformat()}.csv", "w", newline="",
                  encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(RACE_COLS + RUNNER_COLS)
            w.writerows(rows)
        wrote.append(f"{d.isoformat()}: {len(rows)} runners")
        d += timedelta(days=1)
    return wrote


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Keep the full-field archive current")
    ap.add_argument("--update", action="store_true")
    a = ap.parse_args(argv)
    if a.update:
        from racing_edge.data.client import get_client
        from racing_edge.domain.units import uk_today
        for line in update(get_client(), uk_today()) or ["archive already current"]:
            print(f"archive: {line}")
    races = load()
    print(f"archive: {len(races)} races held, {races[0]['date'] if races else '-'} .. "
          f"{races[-1]['date'] if races else '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
