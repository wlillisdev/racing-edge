"""
race_quality_builder.py — Form franking: score the strength of past races by
what their runners did NEXT.

Not all races are equal. A horse that wins a weak race easily (no other runner
from the field wins anything afterwards) holds less form value than a horse
beaten half a length in a race that later produces multiple winners — a
"frankened" race. This builder quantifies that.

For every race in data/learning_dataset.csv it counts how many of the field
won ANY race within FRANK_WINDOW_DAYS afterwards:

    quality = subsequent_winners / field_size

The cache is consumed by:
    - racing_wisdom._score_form_franking   (live NAP scoring overlay)
    - form_strength_analyser               (around-horse form assessment)

Form entries from the API carry no race_id — only (date, course, distance) —
so the cache is double-keyed:

    races : race_id -> {q, subs_winners, field, date}
    by_key: "date|course|dist_round" -> race_id   (None when two races share
            the key — ambiguous, lookup must skip rather than guess)

Output:
    data/race_quality_cache.json

Usage:
    python race_quality_builder.py            # full rebuild (idempotent, fast)

Exit codes:
    0 — success (including empty dataset — writes an empty cache)
    1 — unrecoverable error (write failure)
"""

from __future__ import annotations

import csv
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from src.helpers import data_path, log, safe_write_json

LEARNING_CSV = "learning_dataset.csv"
CACHE_FILE = "race_quality_cache.json"

# How long after a race we look for subsequent wins by its runners.
FRANK_WINDOW_DAYS: int = 90

# A race younger than this hasn't had a fair chance to be franked yet —
# consumers should treat q=0 on young races as "unknown", not "weak".
MIN_AGE_DAYS: int = 28


def _norm_course(raw: str) -> str:
    """Normalise course for cross-source matching: lowercase, strip
    parentheticals like "Newmarket (July)" and "(AW)" suffixes."""
    s = str(raw or "").strip().lower()
    s = re.sub(r"\(.*?\)", "", s)
    return s.strip()


def _parse_date(raw: str) -> Optional[datetime]:
    s = str(raw or "").strip()[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        return None


def _dist_round(raw) -> Optional[int]:
    try:
        d = float(raw)
        return int(round(d)) if d > 0 else None
    except (TypeError, ValueError):
        return None


def composite_key(date_str: str, course: str, distance_f) -> Optional[str]:
    """Build the secondary lookup key used to match form entries (which have
    no race_id) to cached races. Returns None if any part is missing."""
    d = _parse_date(date_str)
    c = _norm_course(course)
    df = _dist_round(distance_f)
    if d is None or not c or df is None:
        return None
    return f"{d.date().isoformat()}|{c}|{df}"


def _is_win(row: dict) -> bool:
    if str(row.get("finish_position") or "").strip() == "1":
        return True
    return str(row.get("won") or "").strip().lower() in ("true", "1")


def build_cache(csv_path: str) -> dict:
    """Build the full quality cache from the learning dataset."""
    races: dict[str, dict] = {}      # race_id -> meta
    fields: dict[str, set] = {}      # race_id -> set of horse_ids
    horse_wins: dict[str, list] = {} # horse_id -> [win datetimes]

    p = Path(csv_path)
    if not p.exists():
        log(f"race_quality_builder: {csv_path} not found — writing empty cache", "WARNING")
        return {"races": {}, "by_key": {}}

    with open(p, "r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            race_id = str(row.get("race_id") or "").strip()
            horse_id = str(row.get("horse_id") or "").strip()
            dt = _parse_date(row.get("date") or "")
            if not race_id or not horse_id or dt is None:
                continue
            if race_id not in races:
                races[race_id] = {
                    "date": dt.date().isoformat(),
                    "course": str(row.get("course") or ""),
                    "distance_f": row.get("distance_f"),
                }
                fields[race_id] = set()
            fields[race_id].add(horse_id)
            if _is_win(row):
                horse_wins.setdefault(horse_id, []).append(dt)

    # Quality per race: runners (winner included — a winner winning again
    # franks the form just as a beaten horse does) with a win inside the
    # window AFTER the race date.
    out_races: dict[str, dict] = {}
    by_key: dict[str, Optional[str]] = {}
    window = timedelta(days=FRANK_WINDOW_DAYS)

    for race_id, meta in races.items():
        race_dt = _parse_date(meta["date"])
        field = fields[race_id]
        subs = 0
        for horse_id in field:
            for win_dt in horse_wins.get(horse_id, ()):
                if race_dt < win_dt <= race_dt + window:
                    subs += 1
                    break
        n = len(field)
        out_races[race_id] = {
            "q": round(subs / n, 3) if n else 0.0,
            "subs_winners": subs,
            "field": n,
            "date": meta["date"],
        }
        key = composite_key(meta["date"], meta["course"], meta["distance_f"])
        if key:
            # Two races sharing date+course+distance are indistinguishable
            # from a form entry — mark ambiguous so lookups skip them.
            by_key[key] = None if key in by_key else race_id

    return {"races": out_races, "by_key": by_key}


# ---------------------------------------------------------------------------
# Consumer API — import these rather than re-parsing the cache shape.
# ---------------------------------------------------------------------------

def load_quality_lookup() -> Optional[dict]:
    """Load the cache for consumers. Returns None when absent/unreadable."""
    from src.helpers import safe_load_json
    cache = safe_load_json(data_path(CACHE_FILE))
    if not cache or not isinstance(cache, dict) or "races" not in cache:
        return None
    return cache


def quality_for_run(run: dict, cache: Optional[dict],
                    today: Optional[datetime] = None) -> Optional[dict]:
    """Look up race quality for one form entry (a past run of a horse).

    Returns the race meta dict {"q", "subs_winners", "field", "date"} or None
    when the race can't be identified, is ambiguous, or is too recent for its
    q=0 to mean anything (younger than MIN_AGE_DAYS with no franking yet).
    """
    if not cache:
        return None
    key = composite_key(
        run.get("date") or run.get("race_date") or "",
        run.get("course") or "",
        run.get("distance_f") or run.get("distance"),
    )
    if not key:
        return None
    race_id = (cache.get("by_key") or {}).get(key)
    if not race_id:
        return None
    meta = (cache.get("races") or {}).get(race_id)
    if not meta:
        return None
    # A young race with q=0 simply hasn't had time to be franked — unknown.
    if meta.get("q", 0.0) == 0.0:
        race_dt = _parse_date(meta.get("date") or "")
        now = today or datetime.now(timezone.utc).replace(tzinfo=None)
        if race_dt is None or (now - race_dt).days < MIN_AGE_DAYS:
            return None
    return meta


def main() -> int:
    log("race_quality_builder.py started")
    cache = build_cache(data_path(LEARNING_CSV))
    cache["built_at"] = datetime.now(timezone.utc).isoformat()
    cache["window_days"] = FRANK_WINDOW_DAYS

    dest = data_path(CACHE_FILE)
    if not safe_write_json(dest, cache):
        log(f"race_quality_builder: failed to write {dest}", "ERROR")
        return 1

    n_races = len(cache["races"])
    n_ambiguous = sum(1 for v in cache["by_key"].values() if v is None)
    frankened = sum(1 for m in cache["races"].values() if m["q"] >= 0.25)
    summary = (
        f"race_quality_builder: DONE — {n_races} races scored, "
        f"{frankened} frankened (q>=0.25), {n_ambiguous} ambiguous keys skipped → {dest}"
    )
    log(summary)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
