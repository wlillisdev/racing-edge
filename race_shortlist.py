"""
race_shortlist.py — Shortlist races and horses worth deeper analysis.

Filters:
    Race:   field_size between 4 and 16 (inclusive)
            race type is not "Bumper" (unless ALLOW_BUMPERS=True below)
            at least one runner has form data

    Runner: has a non-empty form string (not "" or "-")
            valid odds (sp_dec > 1.0 and sp_dec <= 50.0)
            not the sole extreme outsider (highest odds AND gap > OUTSIDER_GAP_RATIO
            from the second-highest) unless the runner has "interesting" form
            (consistent recent form or won last time out)

Saves:
    data/shortlist_YYYY-MM-DD.json
    reports/shortlist_YYYY-MM-DD.txt

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
# Configuration knobs
# ---------------------------------------------------------------------------

ALLOW_BUMPERS:     bool  = False    # set True to include Bumper races
MIN_FIELD_SIZE:    int   = 4
MAX_FIELD_SIZE:    int   = 16
MIN_ODDS:          float = 1.0
MAX_ODDS:          float = 50.0
OUTSIDER_GAP_RATIO: float = 2.0    # odds of top outsider must be > 2× second-highest
                                    # for the outsider-exclusion rule to apply

# ---------------------------------------------------------------------------
# Form helpers
# ---------------------------------------------------------------------------

_RECENT_WIN_CHARS: frozenset[str] = frozenset("123")


def _has_form(form: str | None) -> bool:
    """Return True if *form* contains meaningful figures."""
    if not form:
        return False
    stripped = form.strip().replace("-", "").replace("/", "")
    return bool(stripped)


def _interesting_form(form: str | None) -> bool:
    """Return True if the form figures indicate consistent or recent-win form."""
    if not form:
        return False
    chars = form.strip().replace("-", "").replace("/", "")
    if not chars:
        return False
    # Won last time out.
    if chars[-1] == "1":
        return True
    # Last 3 runs all in {1, 2, 3}.
    recent = chars[-3:] if len(chars) >= 3 else chars
    return all(c in _RECENT_WIN_CHARS for c in recent)


# ---------------------------------------------------------------------------
# Shortlist logic
# ---------------------------------------------------------------------------

def _shortlist_runner(runner: dict, outsider_horse_id: str | None) -> tuple[bool, list[str]]:
    """Decide whether *runner* is shortlistable.

    Returns (is_shortlisted, reasons).
    """
    reasons: list[str] = []
    form    = runner.get("form") or ""
    sp_dec  = runner.get("sp_dec")
    horse_id = str(runner.get("horse_id") or "")

    # Must have form data.
    if not _has_form(form):
        return False, []

    # Must have valid odds.
    try:
        odds = float(sp_dec)
    except (TypeError, ValueError):
        return False, []

    if not (MIN_ODDS < odds <= MAX_ODDS):
        return False, []

    reasons.append(f"Odds {odds:.1f} within range")

    # Outsider exclusion: skip if this is the extreme outsider AND form is dull.
    if horse_id == outsider_horse_id and not _interesting_form(form):
        return False, []

    # Form is present.
    reasons.append(f"Form: {form}")

    if _interesting_form(form):
        reasons.append("Interesting recent form")

    return True, reasons


def _identify_outsider(runners: list[dict]) -> str | None:
    """Return the horse_id of the extreme outsider if they are significantly
    detached from the rest of the field, or None if there is no outlier."""
    valid: list[tuple[float, str]] = []
    for r in runners:
        try:
            odds = float(r.get("sp_dec") or 0)
            if odds > 1.0:
                valid.append((odds, str(r.get("horse_id") or "")))
        except (TypeError, ValueError):
            continue

    if len(valid) < 2:
        return None

    sorted_odds = sorted(valid, key=lambda x: x[0], reverse=True)
    top_odds, top_id   = sorted_odds[0]
    second_odds, _     = sorted_odds[1]

    # Only flag the outsider if they are at least OUTSIDER_GAP_RATIO times
    # longer than the second-longest price.
    if second_odds > 0 and (top_odds / second_odds) >= OUTSIDER_GAP_RATIO:
        return top_id
    return None


def _shortlist_race(race: dict) -> tuple[bool, list[dict]]:
    """Decide whether *race* is shortlistable and return eligible runners.

    Returns (race_is_shortlisted, shortlisted_runner_entries).
    """
    field_size  = race.get("field_size") or 0
    race_type   = str(race.get("type") or "").strip()
    runners     = race.get("runners") or []

    # Field-size filter.
    if not (MIN_FIELD_SIZE <= field_size <= MAX_FIELD_SIZE):
        return False, []

    # Bumper filter.
    if not ALLOW_BUMPERS and race_type == "Bumper":
        return False, []

    # At least one runner must have form data.
    if not any(_has_form(r.get("form")) for r in runners):
        return False, []

    # Identify detached outsider.
    outsider_id = _identify_outsider(runners)

    shortlisted: list[dict] = []
    for runner in runners:
        ok, reasons = _shortlist_runner(runner, outsider_id)
        if ok:
            shortlisted.append(
                {
                    "horse_id": str(runner.get("horse_id") or ""),
                    "horse":    str(runner.get("horse") or ""),
                    "reasons":  reasons,
                }
            )

    # A race is shortlisted only if at least one runner passes the filters.
    return bool(shortlisted), shortlisted


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def _format_text_report(date_str: str, generated_at: str, shortlist: dict) -> str:
    """Build the human-readable shortlist report string."""
    races: list[dict] = shortlist.get("races") or []
    lines: list[str] = [
        "RACING INTELLIGENCE SYSTEM - SHORTLIST REPORT",
        f"Date: {date_str}",
        f"Generated: {generated_at}",
        f"Shortlisted races: {len(races)}",
        "",
    ]

    for idx, race in enumerate(races, start=1):
        course    = race.get("course", "")
        off_time  = race.get("off_time", "")
        race_name = race.get("race_name", "")
        s_runners = race.get("shortlisted_runners") or []

        lines.append(
            f"=== RACE {idx}: {course.upper()} - {off_time} - {race_name} ==="
        )
        if not s_runners:
            lines.append("  (no runners shortlisted)")
        else:
            for entry in s_runners:
                horse   = entry.get("horse", "Unknown")
                reasons = entry.get("reasons") or []
                lines.append(f"  • {horse}")
                for r in reasons:
                    lines.append(f"      - {r}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Load racecard, apply shortlist filters, save outputs. Returns exit code."""
    log("race_shortlist.py started")

    date_str = today_str()

    # --- Load racecard --------------------------------------------------------
    racecard = load_racecard(date_str)
    if racecard is None:
        log(
            "race_shortlist: racecard data unavailable — "
            "ensure run_daily.py has been executed first",
            "ERROR",
        )
        return 1

    racecards: list[dict] = racecard.get("racecards") or []
    if not racecards:
        log("race_shortlist: racecard list is empty — nothing to process", "ERROR")
        return 1

    log(f"race_shortlist: evaluating {len(racecards)} races")

    # --- Apply shortlist logic ------------------------------------------------
    shortlisted_races: list[dict] = []

    for race in racecards:
        is_ok, s_runners = _shortlist_race(race)
        if is_ok:
            shortlisted_races.append(
                {
                    "race_id":             race.get("race_id", ""),
                    "course":              race.get("course", ""),
                    "off_time":            race.get("off_time", ""),
                    "race_name":           race.get("race_name", ""),
                    "shortlisted_runners": s_runners,
                }
            )

    generated_at_iso = datetime.now(timezone.utc).isoformat()
    generated_at_hm  = datetime.now(timezone.utc).strftime("%H:%M")

    shortlist_doc: dict = {
        "date":         date_str,
        "generated_at": generated_at_iso,
        "race_count":   len(shortlisted_races),
        "races":        shortlisted_races,
    }

    # --- Save JSON ------------------------------------------------------------
    json_dest = data_path(f"shortlist_{date_str}.json")
    if not safe_write_json(json_dest, shortlist_doc):
        log(f"race_shortlist: failed to write JSON to {json_dest}", "ERROR")
        return 1
    log(f"race_shortlist: JSON saved to {json_dest}")

    # --- Save text report -----------------------------------------------------
    report_text = _format_text_report(date_str, generated_at_hm, shortlist_doc)
    report_dest = report_path(f"shortlist_{date_str}.txt")

    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
        log(f"race_shortlist: text report saved to {report_dest}")
    except OSError as exc:
        log(f"race_shortlist: failed to write text report — {exc}", "ERROR")
        return 1

    summary = (
        f"race_shortlist: SUCCESS — {len(shortlisted_races)} of {len(racecards)} "
        f"races shortlisted for {date_str}"
    )
    log(summary)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
