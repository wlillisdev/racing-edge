"""
race_shortlist_healthcheck.py — Quick health check specifically for the
shortlist (verifiable output).

Checks:
  1. At least 1 race is shortlisted (when racecards exist with valid fields)
  2. No race has 0 runners in its shortlisted_runners list
  3. All horse_ids in shortlist are valid (non-empty strings)
  4. Shortlist was created today (filename date matches)

Usage:
    python race_shortlist_healthcheck.py              # uses today's date
    python race_shortlist_healthcheck.py 2026-06-06   # override date

Exit codes:
    0 — PASS
    1 — FAIL
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.helpers import data_path, log, today_str


# ---------------------------------------------------------------------------
# Check helpers
# ---------------------------------------------------------------------------

class ShortlistCheckResults:
    def __init__(self, date_str: str) -> None:
        self.date_str = date_str
        self.lines: list[str] = []
        self.failures: int = 0
        self.warnings: int = 0

    def pass_line(self, label: str, detail: str = "") -> None:
        suffix = f" — {detail}" if detail else ""
        self.lines.append(f"  [PASS] {label}{suffix}")

    def fail_line(self, label: str, detail: str = "") -> None:
        suffix = f" — {detail}" if detail else ""
        self.lines.append(f"  [FAIL] {label}{suffix}")
        self.failures += 1

    def warn_line(self, label: str, detail: str = "") -> None:
        suffix = f" — {detail}" if detail else ""
        self.lines.append(f"  [WARN] {label}{suffix}")
        self.warnings += 1

    def info_line(self, line: str) -> None:
        self.lines.append(f"        {line}")


# ---------------------------------------------------------------------------
# Main check logic
# ---------------------------------------------------------------------------

def _run_checks(date_str: str, shortlist: dict) -> ShortlistCheckResults:
    r = ShortlistCheckResults(date_str)

    # ------------------------------------------------------------------
    # Extract the list of shortlisted races.
    # shortlist_YYYY-MM-DD.json may be structured as:
    #   {"races": [...], "shortlisted_races": [...], ...}  — dict style
    #   or a list of race dicts directly
    # ------------------------------------------------------------------
    if isinstance(shortlist, list):
        races = shortlist
    elif isinstance(shortlist, dict):
        races = (
            shortlist.get("shortlisted_races")
            or shortlist.get("races")
            or []
        )
    else:
        r.fail_line("Shortlist format", f"unexpected type: {type(shortlist).__name__}")
        return r

    # ------------------------------------------------------------------
    # Check 1: At least 1 race shortlisted
    # ------------------------------------------------------------------
    if len(races) >= 1:
        r.pass_line("Minimum race count", f"{len(races)} race(s) shortlisted")
    else:
        # Check if there's a racecard to determine whether 0 is expected
        racecard_path = data_path(f"racecards_{date_str}.json")
        racecard_exists = Path(racecard_path).exists()
        if racecard_exists:
            r.fail_line(
                "Minimum race count",
                f"0 races shortlisted but racecard exists — "
                "shortlist may not have run or all races were filtered out",
            )
        else:
            r.warn_line(
                "Minimum race count",
                "0 races shortlisted (no racecard found — may be a no-racing day)",
            )
        return r  # No point checking runners if no races

    # ------------------------------------------------------------------
    # Check 2: No race has 0 runners in shortlisted_runners
    # ------------------------------------------------------------------
    empty_runner_races: list[str] = []
    invalid_horse_ids: list[str] = []
    total_runner_count = 0

    for race in races:
        if not isinstance(race, dict):
            r.warn_line("Race entry", f"unexpected non-dict entry: {race!r}")
            continue

        race_id = str(race.get("race_id") or race.get("id") or "unknown")
        course = str(race.get("course") or "unknown")
        label = f"{course} ({race_id})"

        shortlisted_runners: list = (
            race.get("shortlisted_runners")
            or race.get("runners")
            or []
        )

        if len(shortlisted_runners) == 0:
            empty_runner_races.append(label)
        else:
            total_runner_count += len(shortlisted_runners)

            # ------------------------------------------------------------------
            # Check 3: All horse_ids are valid non-empty strings
            # ------------------------------------------------------------------
            for runner in shortlisted_runners:
                if not isinstance(runner, dict):
                    continue
                horse_id = runner.get("horse_id") or runner.get("id") or ""
                if not str(horse_id).strip():
                    horse_name = runner.get("horse") or runner.get("horse_name") or "unknown"
                    invalid_horse_ids.append(f"{horse_name} in {label}")

    if empty_runner_races:
        for race_label in empty_runner_races:
            r.fail_line("Empty runner list", f"race {race_label} has 0 shortlisted runners")
    else:
        r.pass_line(
            "No empty runner lists",
            f"all {len(races)} race(s) have at least 1 runner",
        )

    if invalid_horse_ids:
        for entry in invalid_horse_ids:
            r.fail_line("Invalid horse_id", entry)
    else:
        r.pass_line(
            "Horse IDs valid",
            f"all {total_runner_count} shortlisted runner(s) have valid horse_id",
        )

    # ------------------------------------------------------------------
    # Check 4: Shortlist was created today (filename date matches)
    # ------------------------------------------------------------------
    shortlist_path = Path(data_path(f"shortlist_{date_str}.json"))
    today = today_str()

    if date_str != today:
        r.warn_line(
            "Date freshness",
            f"checking non-today's shortlist ({date_str} vs today {today})",
        )
    else:
        if shortlist_path.exists():
            try:
                import os
                mtime = shortlist_path.stat().st_mtime
                mtime_dt = datetime.fromtimestamp(mtime)
                mtime_date = mtime_dt.strftime("%Y-%m-%d")
                if mtime_date == date_str:
                    r.pass_line(
                        "Shortlist date",
                        f"file date matches today ({date_str})",
                    )
                else:
                    r.warn_line(
                        "Shortlist date",
                        f"file mtime date {mtime_date!r} doesn't match today {date_str!r}",
                    )
            except OSError as exc:
                r.warn_line("Shortlist date", f"could not stat file — {exc}")
        else:
            # File not found but we loaded data (caller resolved the path)
            r.warn_line("Shortlist date", "could not verify file timestamp")

    return r


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    log("race_shortlist_healthcheck.py started")
    start_ts = time.time()

    date_str = sys.argv[1] if len(sys.argv) > 1 else today_str()
    log(f"race_shortlist_healthcheck: date={date_str}")

    # ------------------------------------------------------------------
    # Load shortlist
    # ------------------------------------------------------------------
    from src.helpers import safe_load_json

    shortlist_file = data_path(f"shortlist_{date_str}.json")
    shortlist = safe_load_json(shortlist_file)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"RACE SHORTLIST HEALTH CHECK")
    print(f"Date: {date_str} | Run: {now_str}")
    print(f"File: shortlist_{date_str}.json")
    print("")

    if shortlist is None:
        print(f"  [FAIL] Shortlist file not found — {shortlist_file}")
        print(f"         Run race_shortlist.py first.")
        print("")
        print(f"RESULT: FAIL — shortlist file missing")
        log("race_shortlist_healthcheck.py: FAIL — shortlist file missing")
        return 1

    # ------------------------------------------------------------------
    # Run checks
    # ------------------------------------------------------------------
    r = _run_checks(date_str, shortlist)

    for line in r.lines:
        print(line)

    print("")
    duration = round(time.time() - start_ts, 2)

    if r.failures == 0:
        verdict = "PASS"
        print(f"RESULT: PASS — {r.warnings} warning(s), 0 failures")
    else:
        verdict = "FAIL"
        print(f"RESULT: FAIL — {r.failures} failure(s), {r.warnings} warning(s)")

    log(
        f"race_shortlist_healthcheck.py finished in {duration}s — "
        f"{verdict} ({r.failures} failures, {r.warnings} warnings)"
    )
    return 0 if r.failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
