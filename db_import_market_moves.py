"""
db_import_market_moves.py — Import market movement data into the market_moves
and odds_snapshots tables.

Inputs:
    data/market_movers_YYYY-MM-DD.json

Outputs:
    Rows in market_moves table.
    Rows in odds_snapshots table (late snapshot).
    Row in system_runs audit log.

Usage:
    python db_import_market_moves.py              # uses today's date
    python db_import_market_moves.py 2026-06-06   # override date

Exit codes:
    0 — success
    1 — unrecoverable error (missing input, DB failure)
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from typing import Optional

from src.db import get_db
from src.helpers import data_path, format_odds, log, safe_load_json, today_str


# ---------------------------------------------------------------------------
# Valid move types (must match schema ENUM)
# ---------------------------------------------------------------------------

VALID_MOVE_TYPES = frozenset({
    "strong_steamer",
    "steamer",
    "late_support",
    "stable",
    "weak_drift",
    "dangerous_drift",
    "false_gamble",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_float_safe(val) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        return f if f > 0 else None
    except (ValueError, TypeError):
        return None


def _normalise_move_type(raw: str) -> str:
    """Map raw move_type to a valid ENUM value, defaulting to 'stable'."""
    cleaned = str(raw or "").strip().lower().replace(" ", "_")
    return cleaned if cleaned in VALID_MOVE_TYPES else "stable"


# ---------------------------------------------------------------------------
# Market moves insert
# ---------------------------------------------------------------------------

MOVES_SQL = """
    INSERT IGNORE INTO market_moves
        (move_date, horse_id, race_id, horse_name,
         morning_odds, late_odds, pct_change, move_type)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""


def _build_move_row(date_str: str, entry: dict) -> Optional[tuple]:
    horse_id = str(entry.get("horse_id") or "").strip()
    race_id = str(entry.get("race_id") or "").strip()
    if not horse_id or not race_id:
        return None

    morning_odds = _parse_float_safe(entry.get("morning_odds"))
    late_odds = _parse_float_safe(entry.get("late_odds"))
    pct_change = entry.get("pct_change")
    try:
        pct_change = float(pct_change) if pct_change is not None else None
    except (ValueError, TypeError):
        pct_change = None

    move_type = _normalise_move_type(entry.get("move_type") or "")

    return (
        date_str,
        horse_id,
        race_id,
        entry.get("horse") or entry.get("horse_name") or None,
        morning_odds,
        late_odds,
        round(pct_change, 4) if pct_change is not None else None,
        move_type,
    )


# ---------------------------------------------------------------------------
# Late odds snapshot insert
# ---------------------------------------------------------------------------

ODDS_SQL = """
    INSERT IGNORE INTO odds_snapshots
        (snapshot_date, horse_id, race_id, snapshot_type,
         odds_decimal, odds_fractional, snapshot_ts, source)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""


def _build_odds_row(date_str: str, entry: dict, snapshot_ts: str) -> Optional[tuple]:
    horse_id = str(entry.get("horse_id") or "").strip()
    race_id = str(entry.get("race_id") or "").strip()
    if not horse_id or not race_id:
        return None

    late_odds = _parse_float_safe(entry.get("late_odds"))
    late_frac = format_odds(late_odds) if late_odds else None

    return (
        date_str,
        horse_id,
        race_id,
        "late",
        late_odds,
        late_frac,
        snapshot_ts,
        "market_movers",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    log("db_import_market_moves.py started")
    start_ts = time.time()

    date_str = sys.argv[1] if len(sys.argv) > 1 else today_str()
    log(f"db_import_market_moves: date={date_str}")

    # ------------------------------------------------------------------
    # 1. Load market movers JSON
    # ------------------------------------------------------------------
    movers_file = data_path(f"market_movers_{date_str}.json")
    movers_doc = safe_load_json(movers_file)

    if movers_doc is None:
        log(f"db_import_market_moves: movers file not found — {movers_file}", "ERROR")
        _record_system_run("fail", "movers file not found", 0, 0, round(time.time() - start_ts, 2))
        return 1

    # Check for BLOCKED status (market_movers.py writes this when snapshots missing)
    if movers_doc.get("status") == "BLOCKED":
        reason = movers_doc.get("reason", "unknown")
        log(f"db_import_market_moves: movers file is BLOCKED — {reason}", "WARNING")
        _record_system_run("fail", f"movers blocked: {reason}", 0, 0, round(time.time() - start_ts, 2))
        return 1

    # The movements list may appear at top level or nested
    movements: list[dict] = movers_doc.get("movements") or []
    log(f"db_import_market_moves: {len(movements)} movement entries found")

    if not movements:
        log("db_import_market_moves: no movements to import", "WARNING")
        _record_system_run("pass", "no movements", 0, 0, round(time.time() - start_ts, 2))
        return 0

    # ------------------------------------------------------------------
    # 2. Connect
    # ------------------------------------------------------------------
    try:
        db = get_db()
    except Exception as exc:  # noqa: BLE001
        log(f"db_import_market_moves: DB connection failed — {exc}", "ERROR")
        return 1

    # ------------------------------------------------------------------
    # 3. Build and insert market_moves rows
    # ------------------------------------------------------------------
    move_rows: list[tuple] = []
    skipped_moves = 0

    for entry in movements:
        row = _build_move_row(date_str, entry)
        if row:
            move_rows.append(row)
        else:
            skipped_moves += 1

    moves_imported = 0
    errors: list[str] = []

    if move_rows:
        try:
            moves_imported = db.execute_many(MOVES_SQL, move_rows)
            log(f"db_import_market_moves: {moves_imported} market_moves rows inserted")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"market_moves: {exc}")
            log(f"db_import_market_moves: market_moves insert failed — {exc}", "ERROR")

    # ------------------------------------------------------------------
    # 4. Build and insert late odds_snapshots rows
    # ------------------------------------------------------------------
    snapshot_ts = movers_doc.get("generated_at") or datetime.now(timezone.utc).isoformat()
    odds_rows: list[tuple] = []

    for entry in movements:
        row = _build_odds_row(date_str, entry, snapshot_ts)
        if row:
            odds_rows.append(row)

    odds_imported = 0
    if odds_rows:
        try:
            odds_imported = db.execute_many(ODDS_SQL, odds_rows)
            log(f"db_import_market_moves: {odds_imported} late odds_snapshot rows inserted")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"odds_snapshots: {exc}")
            log(f"db_import_market_moves: odds_snapshots insert failed — {exc}", "WARNING")

    # ------------------------------------------------------------------
    # 5. Record system_run
    # ------------------------------------------------------------------
    duration = round(time.time() - start_ts, 2)
    status = "fail" if errors else "pass"
    reports_str = f"{moves_imported} market_moves, {odds_imported} late odds snapshots"
    error_text = "; ".join(errors) if errors else None

    _record_system_run(status, error_text, moves_imported, odds_imported, duration)

    log(f"db_import_market_moves.py finished in {duration}s — {reports_str}")
    print(f"db_import_market_moves: {reports_str}")
    return 0 if not errors else 1


def _record_system_run(
    status: str,
    error_text: Optional[str],
    moves: int,
    odds: int,
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
                "db_import_market_moves.py",
                datetime.now().strftime("%Y-%m-%d"),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                status,
                f"{moves} market_moves, {odds} late odds snapshots",
                error_text,
                duration,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        log(f"db_import_market_moves: could not record system_runs — {exc}", "WARNING")


if __name__ == "__main__":
    sys.exit(main())
