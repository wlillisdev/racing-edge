"""
non_runner_scan.py — Identify non-runners by inspecting today's racecard
and cross-referencing against morning market snapshot odds.

A runner is flagged as a probable non-runner when:
    - sp_dec is None, 0, or > 999, OR
    - Their late odds have exploded relative to morning odds (morning 4.0 → 1000+).

Inputs:
    data/racecards_YYYY-MM-DD.json
    data/market_snapshots/market_snapshot_YYYY-MM-DD_morning.json  (optional)
    data/market_snapshots/market_snapshot_YYYY-MM-DD_late.json     (optional)
    data/nap_candidates_YYYY-MM-DD.json                            (optional)

Outputs:
    data/non_runners_YYYY-MM-DD.json
    reports/non_runners_YYYY-MM-DD.txt

Exit codes:
    0  — success (even if no racecard found — report will say so)
    1  — write error
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.helpers import (
    data_path,
    log,
    report_path,
    safe_load_json,
    safe_write_json,
    today_str,
)

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# A runner with sp_dec above this is treated as effectively non-running.
ODDS_NON_RUNNER_THRESHOLD: float = 999.0

# If late_odds / morning_odds exceeds this ratio the runner is "odds explosion".
ODDS_EXPLOSION_RATIO: float = 10.0

# Minimum valid odds below which we cannot make a judgement.
MIN_VALID_ODDS: float = 1.01


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _odds_invalid(sp_dec: object) -> bool:
    """Return True if sp_dec indicates a non-runner / withdrawn status."""
    if sp_dec is None:
        return True
    try:
        val = float(sp_dec)
    except (TypeError, ValueError):
        return True
    return val <= 0 or val > ODDS_NON_RUNNER_THRESHOLD


def _load_optional_snapshot(date_str: str, snapshot_type: str) -> dict[str, float]:
    """Load a market snapshot and return a horse_id → odds_decimal index.

    Returns an empty dict if the file is absent.
    """
    path = os.path.join(
        data_path("market_snapshots"),
        f"market_snapshot_{date_str}_{snapshot_type}.json",
    )
    if not Path(path).exists():
        log(f"non_runner_scan: {snapshot_type} snapshot not found at {path}", "WARNING")
        return {}

    data = safe_load_json(path)
    if data is None:
        return {}

    return {
        h["horse_id"]: h.get("odds_decimal")
        for h in (data.get("horses") or [])
        if h.get("horse_id") and h.get("odds_decimal") is not None
    }


# ---------------------------------------------------------------------------
# Main scan logic
# ---------------------------------------------------------------------------

def _scan_runners(
    racecards: list[dict],
    morning_odds: dict[str, float],
    late_odds: dict[str, float],
) -> tuple[list[dict], list[dict]]:
    """Scan all runners and return (non_runners, safe_runners).

    Each non-runner entry: {horse_id, horse, race_id, course, off_time, reason}.
    Each safe-runner entry: {horse_id, horse, race_id, course, off_time, sp_dec}.
    """
    non_runners: list[dict] = []
    safe_runners: list[dict] = []

    for race in racecards:
        race_id = race.get("race_id", "")
        course = race.get("course", "")
        off_time = race.get("off_time", "")

        for runner in (race.get("runners") or []):
            horse_id = str(runner.get("horse_id") or "")
            horse = str(runner.get("horse") or "")
            sp_dec = runner.get("sp_dec")

            base = {
                "horse_id": horse_id,
                "horse": horse,
                "race_id": race_id,
                "course": course,
                "off_time": off_time,
            }

            # Primary check: racecard odds.
            if _odds_invalid(sp_dec):
                non_runners.append({**base, "reason": "No odds / withdrawn"})
                continue

            # Secondary check: odds explosion between morning and late.
            m_odds = morning_odds.get(horse_id)
            l_odds = late_odds.get(horse_id)

            if (
                m_odds and l_odds
                and m_odds >= MIN_VALID_ODDS
                and l_odds >= MIN_VALID_ODDS
                and (l_odds / m_odds) >= ODDS_EXPLOSION_RATIO
            ):
                non_runners.append(
                    {
                        **base,
                        "reason": f"Odds explosion ({m_odds:.1f} → {l_odds:.1f})",
                    }
                )
                continue

            safe_runners.append({**base, "sp_dec": float(sp_dec)})

    return non_runners, safe_runners


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def _format_text_report(
    date_str: str,
    non_runners: list[dict],
    safe_runners: list[dict],
    blocked_candidates: list[str],
    racecard_missing: bool,
) -> str:
    lines: list[str] = [
        "NON-RUNNER SCAN REPORT",
        f"Date: {date_str}",
        "",
    ]

    if racecard_missing:
        lines += [
            "STATUS: BLOCKED",
            "Racecard data not available — cannot perform non-runner scan.",
            "",
        ]
        return "\n".join(lines)

    lines.append("CONFIRMED / LIKELY NON-RUNNERS:")
    if non_runners:
        for nr in non_runners:
            lines.append(
                f"  - {nr['horse'].upper()} — {nr['course']} {nr['off_time']} "
                f"(Reason: {nr['reason']})"
            )
    else:
        lines.append("  (none identified)")

    lines.append("")
    lines.append(f"SAFE RUNNERS: {len(safe_runners)} horses confirmed with valid odds.")
    lines.append("")

    lines.append("BLOCKED CANDIDATES:")
    if blocked_candidates:
        for name in blocked_candidates:
            lines.append(f"  - {name}")
    else:
        lines.append("  (no NAP candidates are non-runners)")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Scan for non-runners, save reports. Returns exit code."""
    log("non_runner_scan.py started")

    date_str = today_str()

    # --- Load racecard ----------------------------------------------------------
    racecard_path = data_path(f"racecards_{date_str}.json")
    racecard_data = safe_load_json(racecard_path)
    racecard_missing = racecard_data is None

    if racecard_missing:
        log(
            f"non_runner_scan: racecard not found at {racecard_path} — "
            "writing blocked report",
            "ERROR",
        )

    racecards: list[dict] = []
    if racecard_data:
        racecards = racecard_data.get("racecards") or []

    # --- Load optional market snapshots ----------------------------------------
    morning_odds = _load_optional_snapshot(date_str, "morning")
    late_odds = _load_optional_snapshot(date_str, "late")

    # --- Load optional NAP candidates ------------------------------------------
    candidates_path = data_path(f"nap_candidates_{date_str}.json")
    candidates_data = safe_load_json(candidates_path)
    candidate_ids: set[str] = set()
    candidate_names: dict[str, str] = {}
    if candidates_data:
        for c in (candidates_data.get("candidates") or []):
            hid = str(c.get("horse_id") or "")
            if hid:
                candidate_ids.add(hid)
                candidate_names[hid] = str(c.get("horse") or hid)

    # --- Scan -------------------------------------------------------------------
    non_runners, safe_runners = _scan_runners(racecards, morning_odds, late_odds)

    nr_ids = {nr["horse_id"] for nr in non_runners}
    blocked_candidates = [
        candidate_names[hid]
        for hid in candidate_ids
        if hid in nr_ids
    ]

    log(
        f"non_runner_scan: {len(non_runners)} non-runners, "
        f"{len(safe_runners)} safe runners"
    )
    if blocked_candidates:
        log(
            f"non_runner_scan: BLOCKED CANDIDATES — {', '.join(blocked_candidates)}",
            "WARNING",
        )

    # --- Save JSON --------------------------------------------------------------
    json_doc = {
        "date": date_str,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "non_runners": non_runners,
        "safe_count": len(safe_runners),
    }

    json_dest = data_path(f"non_runners_{date_str}.json")
    if not safe_write_json(json_dest, json_doc):
        log(f"non_runner_scan: failed to write JSON to {json_dest}", "ERROR")
        return 1
    log(f"non_runner_scan: JSON saved to {json_dest}")

    # --- Save text report -------------------------------------------------------
    report_text = _format_text_report(
        date_str, non_runners, safe_runners, blocked_candidates, racecard_missing
    )
    report_dest = report_path(f"non_runners_{date_str}.txt")

    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
        log(f"non_runner_scan: text report saved to {report_dest}")
    except OSError as exc:
        log(f"non_runner_scan: failed to write text report — {exc}", "ERROR")
        return 1

    summary = (
        f"non_runner_scan: SUCCESS — {len(non_runners)} non-runners identified, "
        f"{len(safe_runners)} safe runners, "
        f"{len(blocked_candidates)} blocked candidates"
    )
    log(summary)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
