"""
db_import_model_candidates.py — Import today's NAP candidates into the
model_candidates table.

Inputs:
    data/nap_candidates_YYYY-MM-DD.json
    data/final_nap_decision_YYYY-MM-DD.json  (optional)

Outputs:
    Rows in model_candidates table.
    Row in system_runs audit log.

Usage:
    python db_import_model_candidates.py              # uses today's date
    python db_import_model_candidates.py 2026-06-06   # override date

Exit codes:
    0 — success
    1 — unrecoverable error (missing input, DB failure)
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from typing import Optional

from src.db import get_db
from src.helpers import data_path, log, safe_load_json, today_str


# ---------------------------------------------------------------------------
# Candidate types supported
# ---------------------------------------------------------------------------

CANDIDATE_TYPES: tuple[str, ...] = (
    "nap",
    "value_ew",
    "best_of_card",
    "watchlist",
    "shadow",
)


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


def _to_json_str(val) -> Optional[str]:
    """Serialise a list/dict to a compact JSON string, or None if empty."""
    if not val:
        return None
    if isinstance(val, str):
        return val
    try:
        return json.dumps(val, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(val)


def _extract_candidates_from_doc(doc: dict) -> list[tuple[str, dict]]:
    """Return a flat list of (candidate_type, candidate_dict) from the
    nap_candidates document.

    Handles both dict-style (nap, best_of_card) and list-style (watchlist,
    shadow) keys.
    """
    results: list[tuple[str, dict]] = []

    for ctype in CANDIDATE_TYPES:
        raw = doc.get(ctype)
        if raw is None:
            continue
        if isinstance(raw, dict):
            results.append((ctype, raw))
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    results.append((ctype, item))

    return results


# ---------------------------------------------------------------------------
# DB insert
# ---------------------------------------------------------------------------

INSERT_SQL = """
    INSERT IGNORE INTO model_candidates
        (candidate_date, horse_id, horse_name, race_id, course, off_time,
         candidate_type, grade, score, model_version, reasons, warnings)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def _build_row(
    date_str: str,
    ctype: str,
    candidate: dict,
    model_version: str,
) -> Optional[tuple]:
    """Build a parameter tuple for the INSERT statement."""
    horse_id = str(candidate.get("horse_id") or "").strip()
    race_id = str(candidate.get("race_id") or "").strip()
    if not horse_id or not race_id:
        return None

    # off_time normalisation — ensure HH:MM:SS format for TIME column
    off_time_raw = candidate.get("off_time") or candidate.get("off") or None
    if off_time_raw:
        off_time_str = str(off_time_raw).strip()
        # Pad to HH:MM:SS if only HH:MM supplied
        if len(off_time_str) == 5:
            off_time_str = off_time_str + ":00"
    else:
        off_time_str = None

    return (
        date_str,
        horse_id,
        candidate.get("horse") or candidate.get("horse_name") or None,
        race_id,
        candidate.get("course") or None,
        off_time_str,
        ctype,
        candidate.get("grade") or None,
        _parse_float_safe(candidate.get("score")),
        candidate.get("model_version") or model_version,
        _to_json_str(candidate.get("reasons")),
        _to_json_str(candidate.get("warnings")),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    log("db_import_model_candidates.py started")
    start_ts = time.time()

    date_str = sys.argv[1] if len(sys.argv) > 1 else today_str()
    log(f"db_import_model_candidates: date={date_str}")

    # ------------------------------------------------------------------
    # 1. Load nap_candidates
    # ------------------------------------------------------------------
    candidates_file = data_path(f"nap_candidates_{date_str}.json")
    candidates_doc = safe_load_json(candidates_file)

    if candidates_doc is None:
        log(f"db_import_model_candidates: candidates file not found — {candidates_file}", "ERROR")
        _record_system_run("fail", "candidates file not found", 0, round(time.time() - start_ts, 2))
        return 1

    # ------------------------------------------------------------------
    # 2. Determine model version
    # ------------------------------------------------------------------
    try:
        from src.config import get_config
        model_version = get_config().model_version
    except Exception:  # noqa: BLE001
        model_version = "v3"

    # ------------------------------------------------------------------
    # 3. Connect
    # ------------------------------------------------------------------
    try:
        db = get_db()
    except Exception as exc:  # noqa: BLE001
        log(f"db_import_model_candidates: DB connection failed — {exc}", "ERROR")
        return 1

    # ------------------------------------------------------------------
    # 4. Build rows and insert
    # ------------------------------------------------------------------
    all_candidates = _extract_candidates_from_doc(candidates_doc)
    log(f"db_import_model_candidates: {len(all_candidates)} candidates extracted")

    rows: list[tuple] = []
    skipped = 0
    for ctype, candidate in all_candidates:
        row = _build_row(date_str, ctype, candidate, model_version)
        if row:
            rows.append(row)
        else:
            skipped += 1
            log(
                f"db_import_model_candidates: skipping candidate with missing horse_id/race_id — {candidate}",
                "WARNING",
            )

    imported = 0
    errors: list[str] = []

    if rows:
        try:
            imported = db.execute_many(INSERT_SQL, rows)
            log(f"db_import_model_candidates: {imported} candidate rows inserted/ignored")
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
            log(f"db_import_model_candidates: batch insert failed — {exc}", "ERROR")

    # ------------------------------------------------------------------
    # 5. Also import final_nap_decision if it exists and wasn't in candidates
    # ------------------------------------------------------------------
    decision_file = data_path(f"final_nap_decision_{date_str}.json")
    decision_doc = safe_load_json(decision_file)
    decision_imported = 0

    if decision_doc is not None:
        # final_nap_decision may contain a 'selection' key with the final NAP
        selection = decision_doc.get("selection") or decision_doc.get("final_selection") or {}
        if selection and isinstance(selection, dict):
            # Use 'no_bet' type if the decision was a no-bet; otherwise 'nap'
            decision_type = decision_doc.get("decision") or "nap"
            if decision_type == "NO_BET":
                final_ctype = "no_bet"
            else:
                final_ctype = "nap"

            final_row = _build_row(date_str, final_ctype, selection, model_version)
            if final_row:
                try:
                    db.execute(INSERT_SQL, final_row)
                    decision_imported = 1
                    log(f"db_import_model_candidates: final_nap_decision candidate imported")
                except Exception as exc:  # noqa: BLE001
                    # Duplicate key (already imported via candidates) is fine
                    log(
                        f"db_import_model_candidates: final_nap_decision insert note — {exc}",
                        "WARNING",
                    )

    # ------------------------------------------------------------------
    # 6. Record system_run
    # ------------------------------------------------------------------
    duration = round(time.time() - start_ts, 2)
    status = "fail" if errors else "pass"
    reports_str = (
        f"{imported} candidates imported, {skipped} skipped"
        + (f", {decision_imported} from final_decision" if decision_imported else "")
    )
    error_text = "; ".join(errors) if errors else None

    _record_system_run(status, error_text, imported, duration)

    log(f"db_import_model_candidates.py finished in {duration}s — {reports_str}")
    print(f"db_import_model_candidates: {reports_str}")
    return 0 if not errors else 1


def _record_system_run(
    status: str,
    error_text: Optional[str],
    imported: int,
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
                "db_import_model_candidates.py",
                datetime.now().strftime("%Y-%m-%d"),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                status,
                f"{imported} candidates imported",
                error_text,
                duration,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        log(f"db_import_model_candidates: could not record system_runs — {exc}", "WARNING")


if __name__ == "__main__":
    sys.exit(main())
