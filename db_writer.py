"""
db_writer.py — Write today's NAP selections to the MySQL database.

Reads nap_candidates_YYYY-MM-DD.json and writes every selection
(NAP, best_of_card, watchlist, shadow) into the model_candidates table.
Also records morning prices into odds_snapshots.

Run automatically after nap_selector_v3.py in the daily pipeline,
or standalone: python db_writer.py

Exit codes:
    0 — success (including NO_BET day — that is recorded too)
    1 — DB connection failed or write error
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from typing import Optional

from src.db import get_db
from src.helpers import data_path, format_odds, log, safe_load_json, today_str

MODEL_VERSION = "v4"


def _off_time_to_mysql(off_time: str) -> Optional[str]:
    if not off_time:
        return None
    try:
        parts = off_time.strip().split(":")
        hh = int(parts[0])
        mm = int(parts[1]) if len(parts) > 1 else 0
        return f"{hh:02d}:{mm:02d}:00"
    except (ValueError, IndexError):
        return None


def _reasons_to_str(reasons: list) -> str:
    if not reasons:
        return ""
    return " | ".join(str(r) for r in reasons)


def _warnings_to_str(warnings: list) -> str:
    if not warnings:
        return ""
    return " | ".join(str(w) for w in warnings)


def _clear_today_candidates(db, date_str: str) -> None:
    db.execute(
        "DELETE FROM model_candidates WHERE candidate_date = %s",
        (date_str,),
    )
    log(f"db_writer: cleared existing model_candidates rows for {date_str}")


def _insert_candidate(db, date_str: str, entry: dict, candidate_type: str) -> bool:
    try:
        db.execute(
            """
            INSERT INTO model_candidates
                (candidate_date, horse_id, horse_name, race_id, course,
                 off_time, candidate_type, grade, score, model_version,
                 reasons, warnings)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                date_str,
                str(entry.get("horse_id") or ""),
                str(entry.get("horse") or ""),
                str(entry.get("race_id") or ""),
                str(entry.get("course") or ""),
                _off_time_to_mysql(str(entry.get("off_time") or "")),
                candidate_type,
                str(entry.get("grade") or ""),
                float(entry.get("score") or 0),
                MODEL_VERSION,
                _reasons_to_str(entry.get("reasons") or []),
                _warnings_to_str(entry.get("warnings") or []),
            ),
        )
        return True
    except Exception as exc:
        log(f"db_writer: failed to insert {candidate_type} {entry.get('horse')} — {exc}", "ERROR")
        return False


def _insert_odds_snapshot(db, date_str: str, entry: dict) -> None:
    price = entry.get("morning_price")
    if not price:
        return
    try:
        db.execute(
            """
            INSERT INTO odds_snapshots
                (snapshot_date, horse_id, race_id, snapshot_type,
                 odds_decimal, odds_fractional, snapshot_ts, source)
            VALUES (%s, %s, %s, 'morning', %s, %s, %s, 'racecard_odds_array')
            """,
            (
                date_str,
                str(entry.get("horse_id") or ""),
                str(entry.get("race_id") or ""),
                float(price),
                format_odds(float(price)),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
    except Exception as exc:
        log(f"db_writer: odds_snapshots insert skipped for {entry.get('horse')} — {exc}", "WARNING")


def _record_no_bet(db, date_str: str, day_verdict: str) -> None:
    try:
        db.execute(
            """
            INSERT INTO model_candidates
                (candidate_date, horse_id, horse_name, race_id, course,
                 candidate_type, grade, score, model_version, reasons, warnings)
            VALUES (%s, '', 'NO_BET', '', '', 'no_bet', '', 0, %s, %s, '')
            """,
            (date_str, MODEL_VERSION, day_verdict),
        )
    except Exception as exc:
        log(f"db_writer: could not record no_bet row — {exc}", "WARNING")


def _record_system_run(db, date_str: str, status: str, rows: int, duration: float, errors: str) -> None:
    try:
        db.execute(
            """
            INSERT INTO system_runs
                (script, run_date, run_ts, status, reports_created, errors, duration_secs)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                "db_writer.py",
                date_str,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                status,
                f"{rows} model_candidates row(s) written",
                errors or None,
                round(duration, 2),
            ),
        )
    except Exception as exc:
        log(f"db_writer: could not record system_runs row — {exc}", "WARNING")


def main() -> int:
    log("db_writer.py started")
    start_ts = time.time()
    date_str = today_str()
    errors: list[str] = []

    candidates = safe_load_json(data_path(f"nap_candidates_{date_str}.json"))
    if candidates is None:
        log("db_writer: nap_candidates JSON not found — nothing to write", "ERROR")
        return 1

    day_verdict = candidates.get("day_verdict") or "UNKNOWN"
    log(f"db_writer: day_verdict={day_verdict}, date={date_str}")

    try:
        db = get_db()
    except Exception as exc:
        log(f"db_writer: DB connection failed — {exc}", "ERROR")
        return 1

    try:
        _clear_today_candidates(db, date_str)
    except Exception as exc:
        log(f"db_writer: could not clear today's rows — {exc}", "ERROR")
        errors.append(str(exc))

    rows_written = 0

    nap = candidates.get("nap")
    if nap:
        ok = _insert_candidate(db, date_str, nap, "nap")
        if ok:
            rows_written += 1
            _insert_odds_snapshot(db, date_str, nap)
            log(f"db_writer: NAP written — {nap.get('horse')} score={nap.get('score')}")
        else:
            errors.append(f"NAP insert failed: {nap.get('horse')}")

    best = candidates.get("best_of_card")
    if best:
        ok = _insert_candidate(db, date_str, best, "best_of_card")
        if ok:
            rows_written += 1
            _insert_odds_snapshot(db, date_str, best)
            log(f"db_writer: best_of_card written — {best.get('horse')}")

    for entry in (candidates.get("watchlist") or []):
        ok = _insert_candidate(db, date_str, entry, "watchlist")
        if ok:
            rows_written += 1
            _insert_odds_snapshot(db, date_str, entry)

    for entry in (candidates.get("shadow") or []):
        ok = _insert_candidate(db, date_str, entry, "shadow")
        if ok:
            rows_written += 1

    if not nap:
        _record_no_bet(db, date_str, day_verdict)
        rows_written += 1
        log(f"db_writer: no_bet row written — {day_verdict}")

    duration = time.time() - start_ts
    status = "pass" if not errors else "fail"
    _record_system_run(db, date_str, status, rows_written, duration, "; ".join(errors))
    log(f"db_writer: done — {rows_written} row(s) written, status={status}, duration={duration:.1f}s")

    if nap:
        print(f"db_writer: NAP recorded — {nap.get('horse')} ({nap.get('course')} {nap.get('off_time')}) score={nap.get('score')}")
    else:
        print(f"db_writer: {day_verdict} — no_bet recorded for {date_str}")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
