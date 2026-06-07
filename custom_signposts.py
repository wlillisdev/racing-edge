"""
custom_signposts.py — Generate signpost intelligence for today's runners.

A "signpost" is a notable characteristic worth highlighting when assessing
a race, e.g. "Consistent recent form", "Ideal break (21 days)",
"Potentially well-handicapped".

Saves:
    reports/signposts_YYYY-MM-DD.txt  — human-readable report
    data/signposts_YYYY-MM-DD.json    — structured data

Exit codes:
    0  — success
    1  — failure (no racecard, write error)
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from src.helpers import data_path, log, report_path, safe_write_json, today_str
from racecard_loader import load_racecard

# ---------------------------------------------------------------------------
# Signpost detection
# ---------------------------------------------------------------------------

_RECENT_FORM_CHARS: frozenset[str] = frozenset("123")

# Rating threshold for "potentially well-handicapped" detection.
_WELL_HANDICAPPED_OR_THRESHOLD: int = 90
_WELL_HANDICAPPED_CLASSES: frozenset[str] = frozenset({"5", "6"})

# Field-size thresholds.
_SMALL_FIELD_MAX: int = 6
_LARGE_FIELD_MIN: int = 14

# Last-run thresholds (days).
_QUICK_REAPPEARANCE_MAX: int = 10
_IDEAL_BREAK_MIN: int = 14
_IDEAL_BREAK_MAX: int = 28
_LONG_ABSENCE_MIN: int = 61   # >60 days


def _parse_form_chars(form: str) -> str:
    """Return the form figures stripped of dashes/hyphens, most-recent first.

    E.g. "211-132" → "211132" (right side = most recent).
    """
    return form.replace("-", "").replace("/", "")


def _detect_signposts(runner: dict, race: dict) -> list[str]:
    """Return a list of human-readable signpost strings for *runner*."""
    signposts: list[str] = []

    form_raw: str = (runner.get("form") or "").strip()
    last_run: int | None = runner.get("last_run")  # days since last run
    field_size: int | None = race.get("field_size")
    race_class: str = str(race.get("class") or "").strip()

    # --- OFR rating (may be a numeric string) ---------------------------------
    ofr_val: int | None = None
    try:
        ofr_val = int(str(runner.get("ofr") or "").strip())
    except (ValueError, TypeError):
        pass

    # ---- Form-based signposts ------------------------------------------------
    if form_raw and form_raw != "-":
        chars = _parse_form_chars(form_raw)

        # Last 3 form characters all in {1, 2, 3}.
        recent = chars[-3:] if len(chars) >= 3 else chars
        if recent and all(c in _RECENT_FORM_CHARS for c in recent):
            signposts.append("Consistent recent form")

        # Won most-recently (rightmost non-separator character is "1").
        if chars and chars[-1] == "1":
            signposts.append("Won last time out")

    # ---- Break / absence signposts -------------------------------------------
    if last_run is not None and last_run >= 0:
        if last_run < _QUICK_REAPPEARANCE_MAX:
            signposts.append(f"Quick reappearance ({last_run} days)")
        elif _IDEAL_BREAK_MIN <= last_run <= _IDEAL_BREAK_MAX:
            signposts.append(f"Ideal break ({last_run} days)")
        elif last_run > _LONG_ABSENCE_MIN:
            signposts.append(f"Long absence ({last_run} days)")

    # ---- Field-size signposts ------------------------------------------------
    if field_size is not None:
        if field_size <= _SMALL_FIELD_MAX:
            signposts.append("Small field opportunity")
        elif field_size >= _LARGE_FIELD_MIN:
            signposts.append("Large field — harder")

    # ---- Handicap class / rating signpost ------------------------------------
    if (
        race_class in _WELL_HANDICAPPED_CLASSES
        and ofr_val is not None
        and ofr_val > _WELL_HANDICAPPED_OR_THRESHOLD
    ):
        signposts.append(f"Potentially well-handicapped (OR {ofr_val}, class {race_class})")

    return signposts


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def _format_report(date_str: str, generated_at: str, races: list[dict]) -> str:
    """Build the human-readable signposts report string."""
    lines: list[str] = [
        "RACING INTELLIGENCE SYSTEM - SIGNPOSTS REPORT",
        f"Date: {date_str}",
        f"Generated: {generated_at}",
        "",
    ]

    for race_idx, race_block in enumerate(races, start=1):
        course     = race_block.get("course", "")
        off_time   = race_block.get("off_time", "")
        race_name  = race_block.get("race_name", "")
        flagged    = race_block.get("flagged_runners", [])

        header = (
            f"=== RACE {race_idx}: {course.upper()} - {off_time} - {race_name} ==="
        )
        lines.append(header)

        if not flagged:
            lines.append("  (no signposts detected)")
        else:
            for entry in flagged:
                horse_name = entry.get("horse", "Unknown")
                trainer    = entry.get("trainer", "Unknown")
                signals    = entry.get("signposts", [])
                lines.append(f"  {horse_name} ({trainer}):")
                for signal in signals:
                    lines.append(f"    ⚑ {signal}")

        lines.append("")  # blank line between races

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Load racecard, detect signposts, save reports. Returns exit code."""
    log("custom_signposts.py started")

    date_str = today_str()

    # --- Load racecard --------------------------------------------------------
    racecard = load_racecard(date_str)
    if racecard is None:
        log(
            "custom_signposts: racecard data unavailable — "
            "ensure run_daily.py has been executed first",
            "ERROR",
        )
        return 1

    racecards: list[dict] = racecard.get("racecards") or []
    if not racecards:
        log("custom_signposts: racecard list is empty — nothing to process", "ERROR")
        return 1

    log(f"custom_signposts: processing {len(racecards)} races")

    # --- Detect signposts for every runner ------------------------------------
    races_output: list[dict] = []
    total_signposts = 0

    for race in racecards:
        runners: list[dict] = race.get("runners") or []
        flagged_runners: list[dict] = []

        for runner in runners:
            signals = _detect_signposts(runner, race)
            if signals:
                flagged_runners.append(
                    {
                        "horse_id":  runner.get("horse_id", ""),
                        "horse":     runner.get("horse", ""),
                        "trainer":   runner.get("trainer", ""),
                        "jockey":    runner.get("jockey", ""),
                        "signposts": signals,
                    }
                )
                total_signposts += len(signals)

        races_output.append(
            {
                "race_id":        race.get("race_id", ""),
                "course":         race.get("course", ""),
                "off_time":       race.get("off_time", ""),
                "race_name":      race.get("race_name", ""),
                "flagged_runners": flagged_runners,
            }
        )

    generated_at = datetime.now(timezone.utc).strftime("%H:%M")

    # --- Build and save JSON output -------------------------------------------
    json_payload: dict = {
        "date":             date_str,
        "generated_at":     datetime.now(timezone.utc).isoformat(),
        "total_signposts":  total_signposts,
        "races":            races_output,
    }

    json_dest = data_path(f"signposts_{date_str}.json")
    if not safe_write_json(json_dest, json_payload):
        log(f"custom_signposts: failed to write JSON to {json_dest}", "ERROR")
        return 1
    log(f"custom_signposts: JSON saved to {json_dest}")

    # --- Build and save text report -------------------------------------------
    report_text = _format_report(date_str, generated_at, races_output)
    report_dest = report_path(f"signposts_{date_str}.txt")

    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
        log(f"custom_signposts: text report saved to {report_dest}")
    except OSError as exc:
        log(f"custom_signposts: failed to write text report — {exc}", "ERROR")
        return 1

    summary = (
        f"custom_signposts: SUCCESS — {len(racecards)} races processed, "
        f"{total_signposts} total signposts detected"
    )
    log(summary)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
