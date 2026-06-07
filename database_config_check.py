"""
database_config_check.py — Test MySQL connection and verify schema is correct.

Usage:
    python database_config_check.py

Exit codes:
    0 — connection OK and all required tables exist
    1 — connection failed or one or more tables missing
"""

from __future__ import annotations

import sys
from typing import Optional

from src.config import get_config
from src.helpers import log

# ---------------------------------------------------------------------------
# Required tables (matches sql/schema.sql)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Core check logic (callable from other scripts)
# ---------------------------------------------------------------------------

def run_check() -> tuple[bool, str]:
    """Run the full database config check.

    Returns:
        (all_ok: bool, summary_text: str)
    """
    lines: list[str] = []
    lines.append("DATABASE CONFIG CHECK")
    lines.append("═" * 23)

    # ------------------------------------------------------------------
    # 1. Connection
    # ------------------------------------------------------------------
    cfg = None
    db = None
    connection_ok = False
    connection_error: Optional[str] = None

    try:
        cfg = get_config()
    except KeyError as exc:
        connection_error = f"Missing config key: {exc}"

    if cfg is not None:
        try:
            from src.db import DatabaseManager
            db = DatabaseManager(
                host=cfg.db_host,
                port=cfg.db_port,
                database=cfg.db_name,
                user=cfg.db_user,
                password=cfg.db_pass,
            )
            connection_ok = True
        except Exception as exc:  # noqa: BLE001
            connection_error = str(exc)

    if connection_ok:
        lines.append("Connection: OK")
    else:
        lines.append(f"Connection: FAILED — {connection_error}")

    if cfg is not None:
        lines.append(f"Host:       {cfg.db_host}")
        lines.append(f"Database:   {cfg.db_name}")
    else:
        lines.append("Host:       (unknown — config load failed)")
        lines.append("Database:   (unknown)")

    lines.append("")
    lines.append("TABLE STATUS:")

    # ------------------------------------------------------------------
    # 2. Table checks
    # ------------------------------------------------------------------
    missing_tables: list[str] = []
    name_col_width = max(len(t) for t in REQUIRED_TABLES) + 2

    if not connection_ok or db is None:
        for table in REQUIRED_TABLES:
            label = f"{table}:".ljust(name_col_width)
            lines.append(f"  {label} UNKNOWN (no connection)")
            missing_tables.append(table)
    else:
        for table in REQUIRED_TABLES:
            label = f"{table}:".ljust(name_col_width)
            try:
                exists = db.table_exists(table)
                if exists:
                    row = db.fetch_one(f"SELECT COUNT(*) AS cnt FROM `{table}`")
                    n = row["cnt"] if row else 0
                    lines.append(f"  {label} OK ({n} rows)")
                else:
                    lines.append(
                        f"  {label} MISSING — run database_foundation.py"
                    )
                    missing_tables.append(table)
            except Exception as exc:  # noqa: BLE001
                lines.append(f"  {label} ERROR — {exc}")
                missing_tables.append(table)

    # ------------------------------------------------------------------
    # 3. Close connection
    # ------------------------------------------------------------------
    if db is not None:
        try:
            db.close()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # 4. Overall verdict
    # ------------------------------------------------------------------
    lines.append("")
    all_ok = connection_ok and len(missing_tables) == 0

    if all_ok:
        lines.append("OVERALL: PASS")
    else:
        n_missing = len(missing_tables)
        if not connection_ok:
            detail = "connection failed"
        elif n_missing:
            detail = f"{n_missing} table(s) missing"
        else:
            detail = "unknown error"
        lines.append(f"OVERALL: FAIL — {detail}")

    summary = "\n".join(lines)
    return all_ok, summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    log("database_config_check.py started")
    all_ok, summary = run_check()
    print(summary)
    log("database_config_check.py finished")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
