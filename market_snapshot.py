"""
market_snapshot.py — Take a market odds snapshot (morning or late).

Usage:
    python market_snapshot.py morning
    python market_snapshot.py late

Saves:
    data/market_snapshots/market_snapshot_YYYY-MM-DD_{morning|late}.json
    archive/system_snapshots/market_snapshot_YYYY-MM-DD_{morning|late}.json

Exit codes:
    0  — success
    1  — failure (bad args, no racecard, write error)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.config import get_config
from src.helpers import data_path, log, safe_write_json, today_str
from racecard_loader import get_all_runners

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_SNAPSHOT_TYPES: frozenset[str] = frozenset({"morning", "late"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _market_snapshots_dir() -> str:
    directory = data_path("market_snapshots")
    Path(directory).mkdir(parents=True, exist_ok=True)
    return directory


def _system_snapshots_dir() -> str:
    try:
        cfg = get_config()
        project_dir = cfg.project_dir
    except Exception:
        project_dir = str(Path(__file__).resolve().parent)
    directory = os.path.join(project_dir, "archive", "system_snapshots")
    Path(directory).mkdir(parents=True, exist_ok=True)
    return directory


def _best_decimal_odds(runner: dict) -> float | None:
    """Return the tightest (lowest decimal) bookmaker price, falling back to sp_dec."""
    odds_list = runner.get("odds") or []
    best: float | None = None
    for entry in odds_list:
        try:
            dec = float(entry.get("decimal") or 0)
            if dec > 1.0:
                if best is None or dec < best:
                    best = dec
        except (TypeError, ValueError):
            continue
    if best is not None:
        return best
    sp = runner.get("sp_dec")
    if sp:
        try:
            f = float(sp)
            if f > 1.0:
                return f
        except (TypeError, ValueError):
            pass
    return None


def _build_snapshot(snapshot_type: str, date_str: str, runners: list[dict]) -> dict:
    horses: list[dict] = []
    for runner in runners:
        horses.append({
            "horse_id":     str(runner.get("horse_id") or ""),
            "horse":        str(runner.get("horse") or ""),
            "race_id":      str(runner.get("race_id") or ""),
            "course":       str(runner.get("course") or ""),
            "off_time":     str(runner.get("off_time") or ""),
            "odds_decimal": _best_decimal_odds(runner),
        })
    return {
        "date":          date_str,
        "snapshot_type": snapshot_type,
        "taken_at":      datetime.now(timezone.utc).isoformat(),
        "horses":        horses,
    }


def _write_snapshot(snapshot: dict, primary_path: str, backup_path: str) -> bool:
    primary_ok = safe_write_json(primary_path, snapshot)
    if not primary_ok:
        log(f"market_snapshot: failed to write primary file: {primary_path}", "ERROR")
        return False
    log(f"market_snapshot: saved primary snapshot to {primary_path}")
    backup_ok = safe_write_json(backup_path, snapshot)
    if not backup_ok:
        log(f"market_snapshot: WARNING — failed to write backup file: {backup_path}", "WARNING")
    else:
        log(f"market_snapshot: saved backup snapshot to {backup_path}")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    log("market_snapshot.py started")

    if len(sys.argv) < 2:
        print("Usage: python market_snapshot.py <morning|late>", file=sys.stderr)
        log("market_snapshot: no snapshot_type argument provided", "ERROR")
        return 1

    snapshot_type = sys.argv[1].strip().lower()
    if snapshot_type not in VALID_SNAPSHOT_TYPES:
        print(
            f"Invalid snapshot type '{snapshot_type}'. Must be one of: "
            + ", ".join(sorted(VALID_SNAPSHOT_TYPES)),
            file=sys.stderr,
        )
        log(f"market_snapshot: invalid snapshot_type '{snapshot_type}'", "ERROR")
        return 1

    date_str = today_str()
    log(f"market_snapshot: taking '{snapshot_type}' snapshot for {date_str}")

    runners = get_all_runners(date_str)
    if not runners:
        log(
            f"market_snapshot: no runner data available for {date_str} — "
            "ensure run_daily.py has been executed first",
            "ERROR",
        )
        return 1

    log(f"market_snapshot: loaded {len(runners)} runners from racecard")

    snapshot = _build_snapshot(snapshot_type, date_str, runners)

    filename = f"market_snapshot_{date_str}_{snapshot_type}.json"
    primary_path = os.path.join(_market_snapshots_dir(), filename)
    backup_path = os.path.join(_system_snapshots_dir(), filename)

    if not _write_snapshot(snapshot, primary_path, backup_path):
        return 1

    count = len(snapshot["horses"])
    summary = (
        f"market_snapshot: SUCCESS — {count} horses recorded, "
        f"snapshot_type='{snapshot_type}', date={date_str}"
    )
    log(summary)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
