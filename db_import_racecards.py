"""
db_import_racecards.py — Import today's racecard data into the MySQL races
and runners tables.

Inputs:
    data/racecards_YYYY-MM-DD.json
    data/market_snapshots/market_snapshot_morning.json  (optional)

Outputs:
    Rows in races, runners, odds_snapshots tables.
    Row in system_runs audit log.

Usage:
    python db_import_racecards.py              # uses today's date
    python db_import_racecards.py 2026-06-06   # override date

Exit codes:
    0 — success (or partial success with warnings)
    1 — unrecoverable error (missing racecard, DB failure)
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.config import get_config
from src.db import get_db
from src.helpers import data_path, log, safe_load_json, today_str


# ---------------------------------------------------------------------------
# Weight conversion helpers
# ---------------------------------------------------------------------------

def _parse_weight_lbs(weight_str: Optional[str]) -> Optional[int]:
    """Convert weight string (e.g. '9-2', '9st 2lb', '128') to total pounds."""
    if not weight_str:
        return None
    ws = str(weight_str).strip()
    # Format: "9-2" (stones-pounds)
    if "-" in ws:
        parts = ws.split("-")
        try:
            stones = int(parts[0])
            lbs = int(parts[1])
            return stones * 14 + lbs
        except (ValueError, IndexError):
            pass
    # Format: "9st 2lb" or "9st2lb"
    import re
    m = re.match(r"(\d+)\s*st\s*(\d+)?", ws, re.IGNORECASE)
    if m:
        stones = int(m.group(1))
        lbs = int(m.group(2)) if m.group(2) else 0
        return stones * 14 + lbs
    # Plain integer — treat as raw pounds
    try:
        return int(float(ws))
    except ValueError:
        return None


def _parse_int_safe(val) -> Optional[int]:
    """Parse an integer from any value, returning None on failure."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _parse_float_safe(val) -> Optional[float]:
    """Parse a float from any value, returning None on failure."""
    if val is None:
        return None
    try:
        f = float(val)
        return f if f > 0 else None
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Race import
# ---------------------------------------------------------------------------

def _import_races(db, races: list[dict]) -> int:
    """INSERT IGNORE races into the races table. Returns count inserted."""
    sql = """
        INSERT IGNORE INTO races
            (race_id, race_date, off_time, course, region, race_name,
             race_class, race_type, distance_f, going, surface, field_size)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    rows: list[tuple] = []
    for race in races:
        race_id = str(race.get("race_id") or race.get("id") or "").strip()
        if not race_id:
            continue
        rows.append((
            race_id,
            race.get("date") or race.get("race_date") or "",
            race.get("off") or race.get("off_time") or None,
            race.get("course") or None,
            race.get("region") or None,
            race.get("race_name") or race.get("name") or None,
            race.get("race_class") or race.get("class") or None,
            race.get("type") or race.get("race_type") or None,
            _parse_float_safe(race.get("distance_f") or race.get("dist_f")),
            race.get("going") or None,
            race.get("surface") or None,
            _parse_int_safe(race.get("field_size") or race.get("num_runners")
                            or len(race.get("runners") or [])),
        ))
    if not rows:
        return 0
    try:
        affected = db.execute_many(sql, rows)
        return affected
    except Exception as exc:  # noqa: BLE001
        log(f"db_import_racecards: race insert error — {exc}", "ERROR")
        raise


# ---------------------------------------------------------------------------
# Runner import
# ---------------------------------------------------------------------------

def _import_runners(db, race_id: str, runners: list[dict]) -> int:
    """INSERT IGNORE runners into the runners table. Returns count inserted."""
    sql = """
        INSERT IGNORE INTO runners
            (race_id, horse_id, horse_name, trainer, jockey, age, sex,
             draw, weight_lbs, official_rating, rpr, ts_rating,
             sp_morning, form_string, last_run_days)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    rows: list[tuple] = []
    for runner in runners:
        horse_id = str(runner.get("horse_id") or runner.get("id") or "").strip()
        if not horse_id:
            continue
        rows.append((
            race_id,
            horse_id,
            runner.get("horse") or runner.get("horse_name") or None,
            runner.get("trainer") or None,
            runner.get("jockey") or None,
            str(runner.get("age") or "") or None,
            runner.get("sex") or None,
            _parse_int_safe(runner.get("draw")),
            _parse_weight_lbs(runner.get("weight") or runner.get("wgt")),
            _parse_int_safe(runner.get("ofr") or runner.get("official_rating")),
            _parse_int_safe(runner.get("rpr")),
            _parse_int_safe(runner.get("ts") or runner.get("ts_rating")),
            # sp_morning = sp_dec from racecard morning line
            _parse_float_safe(runner.get("sp_dec") or runner.get("sp_morning")),
            # form_string = form from racecard
            runner.get("form") or runner.get("form_string") or None,
            _parse_int_safe(runner.get("last_run") or runner.get("last_run_days")),
        ))
    if not rows:
        return 0
    try:
        affected = db.execute_many(sql, rows)
        return affected
    except Exception as exc:  # noqa: BLE001
        log(f"db_import_racecards: runner insert error (race {race_id}) — {exc}", "ERROR")
        raise


# ---------------------------------------------------------------------------
# Morning odds snapshot import
# ---------------------------------------------------------------------------

def _import_morning_odds(db, snapshot: dict, date_str: str) -> int:
    """Import morning market snapshot into odds_snapshots. Returns count."""
    sql = """
        INSERT IGNORE INTO odds_snapshots
            (snapshot_date, horse_id, race_id, snapshot_type,
             odds_decimal, odds_fractional, snapshot_ts, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    from src.helpers import format_odds

    horses: list[dict] = snapshot.get("horses") or []
    snapshot_ts = snapshot.get("snapshot_ts") or snapshot.get("fetched_at") or datetime.now(timezone.utc).isoformat()

    rows: list[tuple] = []
    for horse in horses:
        horse_id = str(horse.get("horse_id") or "").strip()
        race_id = str(horse.get("race_id") or "").strip()
        if not horse_id or not race_id:
            continue
        odds_dec = _parse_float_safe(horse.get("odds_decimal") or horse.get("sp_dec"))
        odds_frac = horse.get("odds_fractional") or (format_odds(odds_dec) if odds_dec else None)
        rows.append((
            date_str,
            horse_id,
            race_id,
            "morning",
            odds_dec,
            odds_frac,
            snapshot_ts,
            horse.get("source") or "morning_snapshot",
        ))

    if not rows:
        return 0
    try:
        return db.execute_many(sql, rows)
    except Exception as exc:  # noqa: BLE001
        log(f"db_import_racecards: odds_snapshots insert error — {exc}", "WARNING")
        return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    log("db_import_racecards.py started")
    start_ts = time.time()

    # Allow optional date override via CLI arg
    date_str = sys.argv[1] if len(sys.argv) > 1 else today_str()
    log(f"db_import_racecards: date={date_str}")

    # ------------------------------------------------------------------
    # 1. Load racecard JSON
    # ------------------------------------------------------------------
    racecard_file = data_path(f"racecards_{date_str}.json")
    racecard = safe_load_json(racecard_file)

    if racecard is None:
        log(f"db_import_racecards: racecard file not found — {racecard_file}", "ERROR")
        _record_system_run("fail", "racecard file not found", 0, 0, round(time.time() - start_ts, 2))
        return 1

    # Normalise: run_daily.py writes the array under "racecards"; accept the
    # legacy 'races'/'results' keys and a bare list too.
    if isinstance(racecard, list):
        races_data: list[dict] = racecard
    elif isinstance(racecard, dict):
        races_data = (
            racecard.get("racecards")
            or racecard.get("races")
            or racecard.get("results")
            or []
        )
    else:
        log("db_import_racecards: unexpected racecard format", "ERROR")
        _record_system_run("fail", "unexpected racecard format", 0, 0, round(time.time() - start_ts, 2))
        return 1

    if not races_data:
        # A racecard file with zero races means the key layout changed or the
        # fetch failed upstream — importing nothing must be a loud failure,
        # not a "pass" (this exact bug silently imported 0 races for weeks).
        log("db_import_racecards: 0 races in racecard file — failing loudly", "ERROR")
        _record_system_run("fail", "0 races in racecard file", 0, 0, round(time.time() - start_ts, 2))
        return 1

    log(f"db_import_racecards: {len(races_data)} races found in racecard")

    # ------------------------------------------------------------------
    # 2. Connect to DB
    # ------------------------------------------------------------------
    try:
        db = get_db()
    except Exception as exc:  # noqa: BLE001
        log(f"db_import_racecards: DB connection failed — {exc}", "ERROR")
        return 1

    # ------------------------------------------------------------------
    # 3. Import races and runners
    # ------------------------------------------------------------------
    total_races = 0
    total_runners = 0
    errors: list[str] = []

    for race in races_data:
        race_id = str(race.get("race_id") or race.get("id") or "").strip()
        if not race_id:
            log("db_import_racecards: skipping race with no race_id", "WARNING")
            continue

        # Insert race row
        try:
            _import_races(db, [race])
            total_races += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"race {race_id}: {exc}")
            continue

        # Insert runner rows
        runners: list[dict] = race.get("runners") or []
        if runners:
            try:
                _import_runners(db, race_id, runners)
                total_runners += len(runners)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"runners for race {race_id}: {exc}")

    log(f"db_import_racecards: imported {total_races} races, {total_runners} runners")

    # ------------------------------------------------------------------
    # 4. Import morning odds snapshot (if available)
    # ------------------------------------------------------------------
    odds_count = 0
    morning_snapshot_path = data_path(f"market_snapshots/market_snapshot_{date_str}_morning.json")
    # Also check generic "market_snapshot_morning.json" fallback
    morning_snapshot_path_generic = data_path("market_snapshot_morning.json")

    for snap_path in (morning_snapshot_path, morning_snapshot_path_generic):
        if Path(snap_path).exists():
            snapshot = safe_load_json(snap_path)
            if snapshot:
                odds_count = _import_morning_odds(db, snapshot, date_str)
                log(f"db_import_racecards: imported {odds_count} morning odds snapshots from {snap_path}")
            break

    # ------------------------------------------------------------------
    # 5. Record system_run
    # ------------------------------------------------------------------
    duration = round(time.time() - start_ts, 2)
    status = "fail" if errors else "pass"
    reports_str = f"{total_races} races, {total_runners} runners imported"
    if odds_count:
        reports_str += f", {odds_count} morning odds"
    error_text = "; ".join(errors) if errors else None

    _record_system_run(status, error_text, total_races, total_runners, duration)

    if errors:
        log(f"db_import_racecards: completed with {len(errors)} error(s)", "WARNING")
        for err in errors:
            log(f"  - {err}", "WARNING")

    log(f"db_import_racecards.py finished in {duration}s — {reports_str}")
    print(f"db_import_racecards: {reports_str}")
    return 0 if not errors else 1


def _record_system_run(
    status: str,
    error_text: Optional[str],
    races: int,
    runners: int,
    duration: float,
) -> None:
    """Write a row to system_runs. Swallows any exception so it never blocks."""
    try:
        db = get_db()
        db.execute(
            """
            INSERT INTO system_runs
                (script, run_date, run_ts, status, reports_created, errors, duration_secs)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                "db_import_racecards.py",
                datetime.now().strftime("%Y-%m-%d"),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                status,
                f"{races} races, {runners} runners imported",
                error_text,
                duration,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        log(f"db_import_racecards: could not record system_runs — {exc}", "WARNING")


if __name__ == "__main__":
    sys.exit(main())
