"""
database_foundation.py — Create all database tables from sql/schema.sql.

This is the one-time setup script that creates the evidence warehouse.
Safe to re-run: all CREATE statements use IF NOT EXISTS.

Usage:
    python database_foundation.py

Exit codes:
    0 — all tables created / verified successfully
    1 — error (connection failed, SQL error, etc.)
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

from src.config import get_config
from src.helpers import log

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_PATH = Path(__file__).parent / "sql" / "schema.sql"

REQUIRED_TABLES: list[str] = [
    "system_runs",
    "races",
    "runners",
    "model_candidates",
    "odds_snapshots",
    "market_moves",
    "results",
    "trainer_market_profiles",
    "form_strength_records",
    "horse_tracker_records",
    "angle_performance",
]

# Statements to skip (SET commands, comments, blanks)
_SKIP_PREFIXES = ("set ", "--", "/*")


# ---------------------------------------------------------------------------
# Schema loader
# ---------------------------------------------------------------------------

def _load_statements(schema_path: Path) -> list[str]:
    """Read the schema file and split into individual SQL statements.

    Returns a list of non-empty CREATE TABLE ... statements only.
    The splitter is semicolon-based; leading/trailing whitespace is stripped.
    """
    raw = schema_path.read_text(encoding="utf-8")
    raw_statements = raw.split(";")

    statements: list[str] = []
    for stmt in raw_statements:
        stmt = stmt.strip()
        if not stmt:
            continue
        lower = stmt.lower()
        # Only execute CREATE TABLE statements (skip SET, comments, etc.)
        # Use 'in' not 'startswith' — comment blocks precede each CREATE TABLE
        if "create table" in lower:
            statements.append(stmt)

    return statements


def _extract_table_name(stmt: str) -> str:
    """Extract the table name from a CREATE TABLE IF NOT EXISTS statement."""
    import re
    m = re.search(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(\w+)`?",
        stmt,
        re.IGNORECASE,
    )
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    log("database_foundation.py started")
    start_ts = time.time()

    # ------------------------------------------------------------------
    # 1. Load schema file
    # ------------------------------------------------------------------
    if not SCHEMA_PATH.exists():
        log(f"database_foundation: schema file not found at {SCHEMA_PATH}", "ERROR")
        return 1

    try:
        statements = _load_statements(SCHEMA_PATH)
    except OSError as exc:
        log(f"database_foundation: failed to read schema file — {exc}", "ERROR")
        return 1

    log(f"database_foundation: loaded {len(statements)} CREATE TABLE statement(s) from {SCHEMA_PATH}")

    # ------------------------------------------------------------------
    # 2. Connect
    # ------------------------------------------------------------------
    try:
        cfg = get_config()
    except KeyError as exc:
        log(f"database_foundation: missing config key — {exc}", "ERROR")
        return 1

    try:
        from src.db import DatabaseManager
        db = DatabaseManager(
            host=cfg.db_host,
            port=cfg.db_port,
            database=cfg.db_name,
            user=cfg.db_user,
            password=cfg.db_pass,
        )
    except Exception as exc:  # noqa: BLE001
        log(f"database_foundation: connection failed — {exc}", "ERROR")
        return 1

    # ------------------------------------------------------------------
    # 3. Execute each statement — check which tables existed before
    # ------------------------------------------------------------------
    created: list[str] = []
    already_existed: list[str] = []
    errors: list[str] = []

    # Snapshot which tables exist BEFORE we run
    pre_existing: set[str] = set()
    for table in REQUIRED_TABLES:
        try:
            if db.table_exists(table):
                pre_existing.add(table)
        except Exception:  # noqa: BLE001
            pass

    log(
        f"database_foundation: {len(pre_existing)} table(s) already exist before run"
    )

    for stmt in statements:
        # Extract table name for reporting
        table_name = _extract_table_name(stmt)
        try:
            db.execute(stmt)
            if table_name in pre_existing:
                already_existed.append(table_name or stmt[:40])
                log(f"database_foundation: table '{table_name}' already existed — skipped")
            else:
                created.append(table_name or stmt[:40])
                log(f"database_foundation: table '{table_name}' CREATED")
        except Exception as exc:  # noqa: BLE001
            msg = f"{table_name or 'unknown'}: {exc}"
            errors.append(msg)
            log(f"database_foundation: ERROR executing statement for '{table_name}' — {exc}", "ERROR")

    # ------------------------------------------------------------------
    # 4. Summary report
    # ------------------------------------------------------------------
    print("")
    print("DATABASE FOUNDATION REPORT")
    print("═" * 30)
    print(f"Schema file:     {SCHEMA_PATH}")
    print(f"Statements run:  {len(statements)}")
    print(f"Tables created:  {len(created)}")
    print(f"Already existed: {len(already_existed)}")
    print(f"Errors:          {len(errors)}")
    print("")

    if created:
        print("CREATED:")
        for t in created:
            print(f"  + {t}")
        print("")

    if already_existed:
        print("ALREADY EXISTED (no change):")
        for t in already_existed:
            print(f"  = {t}")
        print("")

    if errors:
        print("ERRORS:")
        for e in errors:
            print(f"  ! {e}")
        print("")

    # ------------------------------------------------------------------
    # 5. Run integrity check to verify
    # ------------------------------------------------------------------
    print("Running verification check...")
    print("")
    from database_config_check import run_check
    all_ok, check_summary = run_check()
    print(check_summary)

    # ------------------------------------------------------------------
    # 6. Record system_run
    # ------------------------------------------------------------------
    duration = round(time.time() - start_ts, 2)
    reports_str = (
        f"{len(created)} table(s) created, "
        f"{len(already_existed)} already existed"
    )
    status = "pass" if not errors else "fail"
    error_text = "; ".join(errors) if errors else None

    try:
        db.execute(
            """
            INSERT INTO system_runs
                (script, run_date, run_ts, status, reports_created, errors, duration_secs)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                "database_foundation.py",
                datetime.now().strftime("%Y-%m-%d"),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                status,
                reports_str,
                error_text,
                duration,
            ),
        )
        log("database_foundation: system_runs row recorded")
    except Exception as exc:  # noqa: BLE001
        log(f"database_foundation: could not record system_runs row — {exc}", "WARNING")

    db.close()
    log(f"database_foundation.py finished in {duration}s — status={status}")
    return 0 if (all_ok and not errors) else 1


if __name__ == "__main__":
    sys.exit(main())
