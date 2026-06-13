"""
db_import_results.py — Import evening results into the results table and
update trainer_market_profiles.

Inputs:
    data/results_YYYY-MM-DD.json

Outputs:
    Rows in results table.
    Updated rows in trainer_market_profiles (aggregate).
    Row in system_runs audit log.

Usage:
    python db_import_results.py              # uses today's date
    python db_import_results.py 2026-06-06   # override date

Exit codes:
    0 — success
    1 — unrecoverable error (missing input, DB failure)
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from typing import Optional

from src.db import get_db
from src.helpers import data_path, log, safe_load_json, today_str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_float_safe(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_int_safe(val) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _bool_to_tinyint(val) -> int:
    if val is None:
        return 0
    return 1 if val else 0


# ---------------------------------------------------------------------------
# Results insert
# ---------------------------------------------------------------------------

RESULTS_SQL = """
    INSERT INTO results
        (race_id, horse_id, horse_name, result_date, position, beaten_lengths,
         sp_decimal, won, placed, was_nap, was_value_ew, official_stake, official_pl)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        position        = VALUES(position),
        beaten_lengths  = VALUES(beaten_lengths),
        sp_decimal      = VALUES(sp_decimal),
        won             = VALUES(won),
        placed          = VALUES(placed),
        was_nap         = VALUES(was_nap),
        was_value_ew    = VALUES(was_value_ew),
        official_stake  = VALUES(official_stake),
        official_pl     = VALUES(official_pl)
"""


def _build_result_row(date_str: str, result: dict, ctype: str) -> Optional[tuple]:
    horse_id = str(result.get("horse_id") or "").strip()
    race_id = str(result.get("race_id") or "").strip()
    if not horse_id or not race_id:
        return None

    was_nap = 1 if ctype == "nap" else 0
    was_value_ew = 1 if ctype == "value_ew" else 0

    return (
        race_id,
        horse_id,
        result.get("horse") or result.get("horse_name") or None,
        date_str,
        _parse_int_safe(result.get("position")),
        _parse_float_safe(result.get("beaten_lengths")),
        _parse_float_safe(result.get("sp_decimal")),
        _bool_to_tinyint(result.get("won")),
        _bool_to_tinyint(result.get("placed")),
        was_nap,
        was_value_ew,
        _parse_float_safe(result.get("official_stake") or 0.0) or 0.0,
        _parse_float_safe(result.get("official_pl") or 0.0) or 0.0,
    )


# ---------------------------------------------------------------------------
# Trainer market profiles update
# ---------------------------------------------------------------------------

TRAINER_UPSERT_SQL = """
    INSERT INTO trainer_market_profiles
        (trainer, move_type, sample_size, wins, places, win_pct, place_pct, roi)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        sample_size = sample_size + VALUES(sample_size),
        wins        = wins + VALUES(wins),
        places      = places + VALUES(places),
        win_pct     = ROUND(
                        (wins + VALUES(wins)) / NULLIF(sample_size + VALUES(sample_size), 0) * 100,
                        2),
        place_pct   = ROUND(
                        (places + VALUES(places)) / NULLIF(sample_size + VALUES(sample_size), 0) * 100,
                        2),
        last_updated = NOW()
"""


def _update_trainer_profiles(db, results_with_meta: list[dict], date_str: str) -> int:
    """Update trainer_market_profiles for each result where we know the trainer
    and move_type.

    Looks up the trainer from runners table and the move_type from market_moves.
    Returns count of upserted rows.
    """
    if not results_with_meta:
        return 0

    upsert_count = 0
    lookup_errors = 0

    for result in results_with_meta:
        horse_id = str(result.get("horse_id") or "").strip()
        race_id = str(result.get("race_id") or "").strip()
        if not horse_id or not race_id:
            continue

        # Look up trainer from runners table
        try:
            runner_row = db.fetch_one(
                "SELECT trainer FROM runners WHERE race_id = %s AND horse_id = %s LIMIT 1",
                (race_id, horse_id),
            )
        except Exception as exc:  # noqa: BLE001
            lookup_errors += 1
            if lookup_errors <= 3:  # log first few, don't spam a dead-DB loop
                log(f"db_import_results: trainer lookup failed ({race_id}/{horse_id}) — {exc}", "WARNING")
            continue

        trainer = (runner_row or {}).get("trainer")
        if not trainer:
            continue

        # Look up move_type from market_moves
        try:
            move_row = db.fetch_one(
                "SELECT move_type FROM market_moves "
                "WHERE race_id = %s AND horse_id = %s AND move_date = %s LIMIT 1",
                (race_id, horse_id, date_str),
            )
        except Exception as exc:  # noqa: BLE001
            lookup_errors += 1
            if lookup_errors <= 3:
                log(f"db_import_results: move_type lookup failed ({race_id}/{horse_id}) — {exc}", "WARNING")
            continue

        move_type = (move_row or {}).get("move_type")
        if not move_type:
            move_type = "stable"  # default if no market move recorded

        won = _bool_to_tinyint(result.get("won"))
        placed = _bool_to_tinyint(result.get("placed"))

        win_pct = won * 100.0
        place_pct = placed * 100.0

        try:
            db.execute(
                TRAINER_UPSERT_SQL,
                (trainer, move_type, 1, won, placed, win_pct, place_pct, 0.0),
            )
            upsert_count += 1
        except Exception as exc:  # noqa: BLE001
            log(
                f"db_import_results: trainer profile upsert failed "
                f"({trainer}/{move_type}) — {exc}",
                "WARNING",
            )

    if lookup_errors:
        log(
            f"db_import_results: {lookup_errors} DB lookup error(s) during trainer "
            "profile update — profiles may be incomplete for this date",
            "ERROR" if lookup_errors >= len(results_with_meta) else "WARNING",
        )

    return upsert_count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    log("db_import_results.py started")
    start_ts = time.time()

    date_str = sys.argv[1] if len(sys.argv) > 1 else today_str()
    log(f"db_import_results: date={date_str}")

    # ------------------------------------------------------------------
    # 1. Load results JSON
    # ------------------------------------------------------------------
    results_file = data_path(f"results_{date_str}.json")
    results_doc = safe_load_json(results_file)

    if results_doc is None:
        log(f"db_import_results: results file not found — {results_file}", "ERROR")
        _record_system_run("fail", "results file not found", 0, 0, round(time.time() - start_ts, 2))
        return 1

    # ------------------------------------------------------------------
    # 2. Flatten all result types
    # ------------------------------------------------------------------
    # results_auditor.py writes: official_results, shadow_results, watchlist_results
    all_results: list[tuple[str, dict]] = []

    for ctype, key in (
        ("nap", "official_results"),
        ("value_ew", "official_results"),   # handle within loop by checking candidate_type
        ("shadow", "shadow_results"),
        ("watchlist", "watchlist_results"),
    ):
        pass  # processed below with candidate_type-aware logic

    for result in results_doc.get("official_results") or []:
        ctype = result.get("candidate_type") or "nap"
        all_results.append((ctype, result))

    for result in results_doc.get("shadow_results") or []:
        all_results.append(("shadow", result))

    for result in results_doc.get("watchlist_results") or []:
        all_results.append(("watchlist", result))

    log(f"db_import_results: {len(all_results)} result entries to import")

    # ------------------------------------------------------------------
    # 3. Connect
    # ------------------------------------------------------------------
    try:
        db = get_db()
    except Exception as exc:  # noqa: BLE001
        log(f"db_import_results: DB connection failed — {exc}", "ERROR")
        return 1

    # ------------------------------------------------------------------
    # 4. Build and insert result rows
    # ------------------------------------------------------------------
    rows: list[tuple] = []
    skipped = 0

    for ctype, result in all_results:
        row = _build_result_row(date_str, result, ctype)
        if row:
            rows.append(row)
        else:
            skipped += 1

    results_imported = 0
    errors: list[str] = []

    if rows:
        try:
            results_imported = db.execute_many(RESULTS_SQL, rows)
            log(f"db_import_results: {results_imported} result rows inserted/updated")
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
            log(f"db_import_results: results insert failed — {exc}", "ERROR")

    # ------------------------------------------------------------------
    # 5. Update trainer_market_profiles
    # ------------------------------------------------------------------
    trainer_updates = 0
    if not errors:
        all_result_dicts = [r for _, r in all_results]
        try:
            trainer_updates = _update_trainer_profiles(db, all_result_dicts, date_str)
            log(f"db_import_results: {trainer_updates} trainer profile rows upserted")
        except Exception as exc:  # noqa: BLE001
            log(f"db_import_results: trainer profile update failed — {exc}", "WARNING")

    # ------------------------------------------------------------------
    # 6. Record system_run
    # ------------------------------------------------------------------
    duration = round(time.time() - start_ts, 2)
    status = "fail" if errors else "pass"
    reports_str = (
        f"{results_imported} results imported, "
        f"{trainer_updates} trainer profiles updated"
    )
    error_text = "; ".join(errors) if errors else None

    _record_system_run(status, error_text, results_imported, trainer_updates, duration)

    log(f"db_import_results.py finished in {duration}s — {reports_str}")
    print(f"db_import_results: {reports_str}")
    return 0 if not errors else 1


def _record_system_run(
    status: str,
    error_text: Optional[str],
    results: int,
    trainer_updates: int,
    duration: float,
) -> None:
    try:
        db = get_db()
        db.execute(
            """
            INSERT INTO system_runs
                (script, run_date, run_ts, status, reports_created, errors, duration_secs)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                "db_import_results.py",
                datetime.now().strftime("%Y-%m-%d"),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                status,
                f"{results} results, {trainer_updates} trainer profiles",
                error_text,
                duration,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        log(f"db_import_results: could not record system_runs — {exc}", "WARNING")


if __name__ == "__main__":
    sys.exit(main())
