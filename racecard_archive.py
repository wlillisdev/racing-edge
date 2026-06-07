"""
racecard_archive.py — Archive today's racecard JSON for disaster recovery.

Usage (PythonAnywhere scheduled task, run after run_daily.py):
    python racecard_archive.py

Archives:
    data/racecards_YYYY-MM-DD.json
        -> archive/system_snapshots/racecards_YYYY-MM-DD.json

Also maintains:
    archive/system_snapshots/archive_index.json

Exit codes:
    0  — success
    1  — failure (source file missing, write error)
"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.helpers import (
    data_path,
    log,
    safe_load_json,
    safe_write_json,
    snapshot_path,
    today_str,
)


# ---------------------------------------------------------------------------
# Archive helpers
# ---------------------------------------------------------------------------

def _archive_racecard(date_str: str) -> bool:
    """Copy today's racecard JSON into the system_snapshots directory.

    Returns True on success, False on any failure.
    """
    source_file = data_path(f"racecards_{date_str}.json")
    dest_file   = snapshot_path(f"racecards_{date_str}.json")

    if not Path(source_file).exists():
        log(f"Source racecard not found: {source_file}", "ERROR")
        return False

    try:
        shutil.copy2(source_file, dest_file)
        log(f"Archived racecard to {dest_file}")
        return True
    except (OSError, shutil.Error) as exc:
        log(f"Failed to copy racecard to archive: {exc}", "ERROR")
        return False


def _update_index(date_str: str, archived_at: str, success: bool) -> bool:
    """Append an entry to archive_index.json.

    Creates the index file if it does not yet exist.
    Returns True on success, False on write failure.
    """
    index_file = snapshot_path("archive_index.json")

    existing = safe_load_json(index_file)
    if existing is None:
        # First run or corrupted index — start fresh.
        existing = {"archived_dates": []}

    # Ensure the list key exists even if the JSON was missing it.
    if "archived_dates" not in existing:
        existing["archived_dates"] = []

    # Remove any prior entry for the same date so we don't accumulate duplicates.
    existing["archived_dates"] = [
        entry for entry in existing["archived_dates"]
        if entry.get("date") != date_str
    ]

    existing["archived_dates"].append(
        {
            "date":        date_str,
            "archived_at": archived_at,
            "success":     success,
            "snapshot":    f"racecards_{date_str}.json",
        }
    )

    # Keep entries sorted chronologically.
    existing["archived_dates"].sort(key=lambda e: e.get("date", ""))

    existing["last_updated"] = archived_at

    return safe_write_json(index_file, existing)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Archive today's racecard and update the archive index. Returns exit code."""
    log("racecard_archive.py started")

    date_str    = today_str()
    archived_at = datetime.now(timezone.utc).isoformat()

    # --- Archive the file -----------------------------------------------------
    archive_ok = _archive_racecard(date_str)

    # --- Update the index regardless of success so failures are tracked -------
    index_ok = _update_index(date_str, archived_at, success=archive_ok)

    if not index_ok:
        log("Failed to update archive index", "ERROR")
        # Non-fatal for the overall process — the file was still copied.

    if not archive_ok:
        log("racecard_archive.py finished with errors", "ERROR")
        return 1

    log("racecard_archive.py completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
