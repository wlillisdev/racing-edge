"""
market_movers.py — Compare morning vs late market snapshots and classify
each runner's price movement.

Inputs:
    data/market_snapshots/market_snapshot_YYYY-MM-DD_morning.json
    data/market_snapshots/market_snapshot_YYYY-MM-DD_late.json

Outputs:
    data/market_movers_YYYY-MM-DD.json
    reports/market_movers_YYYY-MM-DD.txt

Exit codes:
    0  — success
    1  — failure (missing snapshots, write error)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.config import get_config
from src.helpers import (
    data_path,
    format_odds,
    log,
    report_path,
    safe_load_json,
    safe_write_json,
    today_str,
)


# ---------------------------------------------------------------------------
# Movement classification thresholds
# ---------------------------------------------------------------------------

def _classify_movement(pct_change: float) -> tuple[str, str]:
    """Return (move_type, display_label) for a given percentage change.

    pct_change is positive when the price shortens (market support) and
    negative when the price drifts (market warning).
    """
    if pct_change >= 40:
        return "strong_steamer", "Strong Steamer"
    if pct_change >= 20:
        return "steamer", "Steamer"
    if pct_change >= 10:
        return "late_support", "Late Support"
    if pct_change <= -30:
        return "dangerous_drift", "Dangerous Drift"
    if pct_change <= -10:
        return "weak_drift", "Weak Drift"
    return "stable", "Stable"


def _arrow(move_type: str) -> str:
    if move_type == "strong_steamer":
        return "↑↑"
    if move_type in ("steamer", "late_support"):
        return "↑"
    if move_type == "dangerous_drift":
        return "↓↓"
    if move_type == "weak_drift":
        return "↓"
    return "—"


# ---------------------------------------------------------------------------
# Safe-block report helpers
# ---------------------------------------------------------------------------

def _write_blocked_report(date_str: str, reason: str) -> None:
    """Write a BLOCKED marker to both JSON and TXT outputs."""
    blocked_json = {
        "date": date_str,
        "status": "BLOCKED",
        "reason": reason,
        "movements": [],
        "steamers": [],
        "drifters": [],
        "stable": [],
    }
    safe_write_json(data_path(f"market_movers_{date_str}.json"), blocked_json)

    txt_path = report_path(f"market_movers_{date_str}.txt")
    try:
        with open(txt_path, "w", encoding="utf-8") as fh:
            fh.write(
                f"MARKET MOVERS REPORT\n"
                f"Date: {date_str}\n\n"
                f"STATUS: BLOCKED\n"
                f"Reason: {reason}\n"
            )
    except OSError as exc:
        log(f"market_movers: could not write blocked report — {exc}", "ERROR")


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _index_snapshot(snapshot: dict) -> dict[str, dict]:
    """Build a horse_id → horse_record index from a snapshot document."""
    return {
        h["horse_id"]: h
        for h in (snapshot.get("horses") or [])
        if h.get("horse_id")
    }


def _compute_movements(
    morning_index: dict[str, dict],
    late_index: dict[str, dict],
) -> list[dict]:
    """Return a list of movement records for horses present in both snapshots."""
    movements: list[dict] = []

    for horse_id, morning_rec in morning_index.items():
        late_rec = late_index.get(horse_id)
        if late_rec is None:
            continue  # horse not in late snapshot — may be a non-runner

        morning_odds = morning_rec.get("odds_decimal")
        late_odds = late_rec.get("odds_decimal")

        # Skip horses where either odds value is invalid.
        if not morning_odds or not late_odds:
            continue
        if morning_odds <= 1.0 or late_odds <= 1.0:
            continue

        pct_change = (morning_odds - late_odds) / morning_odds * 100
        move_type, move_label = _classify_movement(pct_change)
        arrow = _arrow(move_type)

        morning_frac = format_odds(morning_odds)
        late_frac = format_odds(late_odds)

        warning = " (⚠ DANGEROUS DRIFT)" if move_type == "dangerous_drift" else ""
        label = f"{arrow} {move_label} ({morning_frac} → {late_frac}){warning}"

        movements.append(
            {
                "horse_id": horse_id,
                "horse": morning_rec.get("horse", ""),
                "race_id": morning_rec.get("race_id", ""),
                "course": morning_rec.get("course", ""),
                "off_time": morning_rec.get("off_time", ""),
                "morning_odds": morning_odds,
                "late_odds": late_odds,
                "pct_change": round(pct_change, 2),
                "move_type": move_type,
                "label": label,
            }
        )

    # Sort: steamers first (highest pct_change), then drifters, stable last.
    movements.sort(key=lambda x: -x["pct_change"])
    return movements


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def _format_text_report(date_str: str, movements: list[dict]) -> str:
    """Build the human-readable market movers report."""
    steamers = [m for m in movements if m["move_type"] in ("strong_steamer", "steamer", "late_support")]
    drifters = [m for m in movements if m["move_type"] in ("weak_drift", "dangerous_drift")]
    stable = [m for m in movements if m["move_type"] == "stable"]

    lines: list[str] = [
        "MARKET MOVERS REPORT",
        f"Date: {date_str} | Snapshot: Morning vs Late",
        "",
        "SUMMARY",
        "-" * 40,
        f"Runners compared:        {len(movements)}",
        f"Steamers / with support: {len(steamers)}",
        f"Drifters:                {len(drifters)}",
        f"Stable:                  {len(stable)}",
        "",
    ]

    # Steamers
    lines.append("STEAMERS (Market Support):")
    if steamers:
        for m in steamers:
            morning_frac = format_odds(m["morning_odds"])
            late_frac = format_odds(m["late_odds"])
            move_label = m["move_type"].replace("_", " ").title()
            lines.append(
                f"  ↑ {m['horse'].upper()} — {m['course']} {m['off_time']}: "
                f"{morning_frac} → {late_frac} ({move_label})"
            )
    else:
        lines.append("  (no steamers today)")

    lines.append("")

    # Drifters
    lines.append("DRIFTERS (Market Warning):")
    if drifters:
        for m in sorted(drifters, key=lambda x: x["pct_change"]):
            morning_frac = format_odds(m["morning_odds"])
            late_frac = format_odds(m["late_odds"])
            if m["move_type"] == "dangerous_drift":
                arrow = "↓↓"
                suffix = " (⚠ DANGEROUS DRIFT)"
            else:
                arrow = "↓"
                suffix = ""
            lines.append(
                f"  {arrow} {m['horse'].upper()} — {m['course']} {m['off_time']}: "
                f"{morning_frac} → {late_frac} (Weak Drift){suffix}"
            )
    else:
        lines.append("  (no significant drifters today)")

    lines.append("")

    # Stable
    lines.append("STABLE:")
    lines.append(f"  ({len(stable)} horses showed minimal movement)")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Load snapshots, compute movements, save outputs. Returns exit code."""
    log("market_movers.py started")

    date_str = today_str()

    # Build snapshot paths.
    snapshots_dir = data_path("market_snapshots")
    morning_file = os.path.join(snapshots_dir, f"market_snapshot_{date_str}_morning.json")
    late_file = os.path.join(snapshots_dir, f"market_snapshot_{date_str}_late.json")

    missing: list[str] = []
    if not Path(morning_file).exists():
        missing.append(f"morning snapshot ({morning_file})")
    if not Path(late_file).exists():
        missing.append(f"late snapshot ({late_file})")

    if missing:
        reason = "Missing files: " + "; ".join(missing)
        log(f"market_movers: {reason}", "ERROR")
        _write_blocked_report(date_str, reason)
        return 1

    morning_snapshot = safe_load_json(morning_file)
    late_snapshot = safe_load_json(late_file)

    if morning_snapshot is None or late_snapshot is None:
        reason = "Could not parse one or both snapshot files"
        log(f"market_movers: {reason}", "ERROR")
        _write_blocked_report(date_str, reason)
        return 1

    morning_index = _index_snapshot(morning_snapshot)
    late_index = _index_snapshot(late_snapshot)

    log(
        f"market_movers: {len(morning_index)} morning horses, "
        f"{len(late_index)} late horses"
    )

    movements = _compute_movements(morning_index, late_index)

    steamers = [m for m in movements if m["move_type"] in ("strong_steamer", "steamer", "late_support")]
    drifters = [m for m in movements if m["move_type"] in ("weak_drift", "dangerous_drift")]
    stable = [m for m in movements if m["move_type"] == "stable"]

    log(
        f"market_movers: {len(steamers)} steamers, "
        f"{len(drifters)} drifters, "
        f"{len(stable)} stable"
    )

    # --- Save JSON output -------------------------------------------------------
    json_doc = {
        "date": date_str,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "movements": movements,
        "steamers": steamers,
        "drifters": drifters,
        "stable": stable,
    }

    json_dest = data_path(f"market_movers_{date_str}.json")
    if not safe_write_json(json_dest, json_doc):
        log(f"market_movers: failed to write JSON to {json_dest}", "ERROR")
        return 1
    log(f"market_movers: JSON saved to {json_dest}")

    # --- Save text report -------------------------------------------------------
    report_text = _format_text_report(date_str, movements)
    report_dest = report_path(f"market_movers_{date_str}.txt")

    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
        log(f"market_movers: text report saved to {report_dest}")
    except OSError as exc:
        log(f"market_movers: failed to write text report — {exc}", "ERROR")
        return 1

    summary = (
        f"market_movers: SUCCESS — {len(movements)} horses compared, "
        f"{len(steamers)} steamers, {len(drifters)} drifters"
    )
    log(summary)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
