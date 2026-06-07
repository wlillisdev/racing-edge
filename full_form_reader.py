"""
full_form_reader.py — Pull full historical form for every shortlisted horse
using the horse results API endpoint, then produce an enriched profile report.

Processing:
    1. Load data/shortlist_YYYY-MM-DD.json
    2. For each unique shortlisted horse, call
       get_client().get_horse_results(horse_id, limit=8)
    3. Enrich each horse's profile with:
          • best ground performance
          • best distance performance
          • course record at today's course
          • class wins (won at this class or higher)
          • career form summary
    4. Save data/full_form_YYYY-MM-DD.json
    5. Save reports/full_form_YYYY-MM-DD.txt

API calls are rate-limited to one every 0.5 seconds. Individual failures are
handled gracefully — a failed lookup produces a "NO DATA" profile rather than
aborting the whole run.

Exit codes:
    0  — success
    1  — failure (no shortlist, write error)
"""

from __future__ import annotations

import time
import sys
from datetime import datetime, timezone

from src.helpers import data_path, log, report_path, safe_load_json, safe_write_json, today_str
from src.api_client import get_client
from racecard_loader import get_race

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_DELAY_SECONDS: float = 0.5      # sleep between horse API calls
RESULT_LIMIT:      int   = 8        # results to fetch per horse

# Numeric class values for comparison — lower number = higher class.
# Non-numeric class labels (Novice, Maiden, etc.) are treated as mid-tier (4).
_CLASS_NUMERIC_MAP: dict[str, int] = {
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7,
}

# ---------------------------------------------------------------------------
# Result parsing helpers
# ---------------------------------------------------------------------------

def _to_float(value: object, default: float | None = None) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _to_int(value: object, default: int | None = None) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _class_to_int(cls: str | None) -> int:
    """Convert a class label to a comparable integer. Lower = higher class."""
    if cls is None:
        return 4  # mid-tier fallback
    return _CLASS_NUMERIC_MAP.get(str(cls).strip(), 4)


def _is_win(result: dict) -> bool:
    """Return True if the result represents a win."""
    position = str(result.get("position") or result.get("pos") or "").strip()
    return position == "1"


def _result_ground(result: dict) -> str:
    """Extract the going/ground from a result dict."""
    return str(result.get("going") or result.get("ground") or "Unknown").strip()


def _result_distance_f(result: dict) -> float | None:
    """Extract distance in furlongs from a result dict."""
    return _to_float(result.get("distance_f") or result.get("dist_f"))


def _result_course(result: dict) -> str:
    return str(result.get("course") or "").strip().lower()


def _result_class(result: dict) -> str:
    return str(result.get("class") or result.get("race_class") or "").strip()


# ---------------------------------------------------------------------------
# Profile enrichment
# ---------------------------------------------------------------------------

def _enrich_profile(
    horse_id: str,
    horse_name: str,
    results: list[dict],
    today_course: str,
    today_class: str,
) -> dict:
    """Build an enriched horse profile from historical results.

    Returns a dict with profile fields and a career_summary list.
    """
    if not results:
        return {
            "horse_id":              horse_id,
            "horse":                 horse_name,
            "status":                "NO DATA",
            "runs":                  0,
            "wins":                  0,
            "best_ground":           None,
            "best_distance_f":       None,
            "course_wins":           0,
            "course_runs":           0,
            "class_wins":            [],
            "career_form_summary":   "No historical results available",
            "results":               [],
        }

    wins: list[dict]        = []
    course_results: list[dict] = []
    today_course_lower      = today_course.strip().lower()
    today_class_int         = _class_to_int(today_class)

    for result in results:
        if _is_win(result):
            wins.append(result)
        if today_course_lower and _result_course(result) == today_course_lower:
            course_results.append(result)

    # Best ground: ground of most recent win (if any), else most recent run.
    best_ground: str | None = None
    if wins:
        best_ground = _result_ground(wins[0])  # results should already be recent-first
    elif results:
        best_ground = _result_ground(results[0])

    # Best distance: distance of the highest-class win, or most recent win.
    best_distance_f: float | None = None
    if wins:
        # Pick win at the highest class (lowest class int).
        best_win = min(wins, key=lambda r: _class_to_int(_result_class(r)))
        best_distance_f = _result_distance_f(best_win)

    # Course record.
    course_wins = sum(1 for r in course_results if _is_win(r))
    course_runs = len(course_results)

    # Class wins: results where horse won at today's class level or higher.
    class_wins: list[str] = []
    for r in wins:
        r_class_int = _class_to_int(_result_class(r))
        if r_class_int <= today_class_int:     # equal or higher class
            class_label = _result_class(r) or "?"
            course_label = r.get("course") or "?"
            date_label   = r.get("date") or r.get("race_date") or "?"
            class_wins.append(f"Class {class_label} win at {course_label} ({date_label})")

    # Career form summary string.
    total_runs  = len(results)
    total_wins  = len(wins)
    placed      = sum(
        1 for r in results
        if str(r.get("position") or r.get("pos") or "").strip() in ("2", "3")
    )
    win_pct     = (total_wins / total_runs * 100) if total_runs else 0
    career_summary = (
        f"{total_runs} runs, {total_wins} wins ({win_pct:.0f}%), {placed} placed"
    )
    if course_runs:
        course_pct = (course_wins / course_runs * 100)
        career_summary += (
            f" | {today_course}: {course_wins}/{course_runs} ({course_pct:.0f}%)"
        )

    return {
        "horse_id":            horse_id,
        "horse":               horse_name,
        "status":              "OK",
        "runs":                total_runs,
        "wins":                total_wins,
        "best_ground":         best_ground,
        "best_distance_f":     best_distance_f,
        "course_wins":         course_wins,
        "course_runs":         course_runs,
        "class_wins":          class_wins,
        "career_form_summary": career_summary,
        "results":             results,
    }


# ---------------------------------------------------------------------------
# Text report formatting
# ---------------------------------------------------------------------------

def _format_profile(profile: dict, race_info: dict) -> str:
    """Return a human-readable block for one horse profile."""
    horse      = profile.get("horse", "Unknown")
    status     = profile.get("status", "?")
    course     = race_info.get("course", "")
    off_time   = race_info.get("off_time", "")
    race_name  = race_info.get("race_name", "")

    lines: list[str] = [
        f"  {horse}",
        f"  Race: {course.upper()} {off_time} — {race_name}",
    ]

    if status == "NO DATA":
        lines.append("  [NO HISTORICAL DATA AVAILABLE]")
        lines.append("")
        return "\n".join(lines)

    career  = profile.get("career_form_summary", "-")
    ground  = profile.get("best_ground") or "-"
    dist_f  = profile.get("best_distance_f")
    dist_s  = f"{dist_f}f" if dist_f is not None else "-"
    c_wins  = profile.get("course_wins", 0)
    c_runs  = profile.get("course_runs", 0)
    c_str   = f"{c_wins} wins from {c_runs} runs" if c_runs else "Never run here"
    cls_wins: list[str] = profile.get("class_wins") or []

    lines.append(f"  Career      : {career}")
    lines.append(f"  Best ground : {ground}")
    lines.append(f"  Best dist   : {dist_s}")
    lines.append(f"  Course form : {c_str}")

    if cls_wins:
        lines.append(f"  Class wins  :")
        for cw in cls_wins[:5]:    # cap at 5 entries
            lines.append(f"    - {cw}")
    else:
        lines.append("  Class wins  : None at this class or higher")

    lines.append("")
    return "\n".join(lines)


def _format_report(date_str: str, generated_at: str, races: list[dict]) -> str:
    """Build the full human-readable full form report."""
    lines: list[str] = [
        "RACING INTELLIGENCE SYSTEM - FULL FORM READER REPORT",
        f"Date: {date_str}",
        f"Generated: {generated_at}",
        "",
    ]

    for race_block in races:
        course    = race_block.get("course", "")
        off_time  = race_block.get("off_time", "")
        race_name = race_block.get("race_name", "")

        lines.append(f"=== {course.upper()} {off_time} — {race_name} ===")

        profiles: list[dict] = race_block.get("profiles") or []
        if not profiles:
            lines.append("  (no profiles available)")
            lines.append("")
            continue

        for profile in profiles:
            lines.append(_format_profile(profile, race_block))

        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Load shortlist, fetch historical form, enrich profiles, save outputs."""
    log("full_form_reader.py started")

    date_str = today_str()

    # --- Load shortlist -------------------------------------------------------
    shortlist_path = data_path(f"shortlist_{date_str}.json")
    shortlist = safe_load_json(shortlist_path)

    if shortlist is None:
        log(
            "full_form_reader: shortlist data unavailable — "
            "ensure race_shortlist.py has been executed first",
            "ERROR",
        )
        return 1

    shortlisted_races: list[dict] = shortlist.get("races") or []
    if not shortlisted_races:
        log("full_form_reader: no races in shortlist — nothing to process", "WARNING")

    # --- Collect unique horses (horse_id → race_id mapping) ------------------
    # A horse may appear in multiple races (rare but possible); we process once.
    horse_to_race: dict[str, str]  = {}   # horse_id → race_id
    horse_names:   dict[str, str]  = {}   # horse_id → horse name

    for race in shortlisted_races:
        race_id = race.get("race_id", "")
        for runner in race.get("shortlisted_runners") or []:
            hid  = str(runner.get("horse_id") or "")
            name = str(runner.get("horse") or "")
            if hid and hid not in horse_to_race:
                horse_to_race[hid] = race_id
                horse_names[hid]   = name

    total_horses = len(horse_to_race)
    log(f"full_form_reader: fetching form for {total_horses} unique horse(s)")

    # --- Fetch form from API --------------------------------------------------
    try:
        client = get_client()
    except Exception as exc:
        log(f"full_form_reader: failed to initialise API client — {exc}", "ERROR")
        return 1

    all_profiles: dict[str, dict] = {}   # horse_id → profile

    for idx, (horse_id, race_id) in enumerate(horse_to_race.items()):
        horse_name  = horse_names.get(horse_id, horse_id)
        today_race  = get_race(race_id, date_str) or {}
        today_course = str(today_race.get("course") or "")
        today_class  = str(today_race.get("class") or "")

        log(
            f"full_form_reader: [{idx + 1}/{total_horses}] "
            f"fetching {horse_name} (id={horse_id})"
        )

        try:
            results: list[dict] = client.get_horse_results(horse_id, limit=RESULT_LIMIT)
            if not isinstance(results, list):
                log(
                    f"full_form_reader: unexpected result type for {horse_id} "
                    f"({type(results).__name__}) — treating as empty",
                    "WARNING",
                )
                results = []
        except Exception as exc:
            log(
                f"full_form_reader: API error for {horse_name} (id={horse_id}) — {exc}",
                "WARNING",
            )
            results = []

        profile = _enrich_profile(
            horse_id, horse_name, results, today_course, today_class
        )
        all_profiles[horse_id] = profile

        # Rate-limit: sleep between API calls (skip after the last horse).
        if idx < total_horses - 1:
            time.sleep(API_DELAY_SECONDS)

    # --- Assemble output structure (grouped by race) -------------------------
    output_races: list[dict] = []

    for race in shortlisted_races:
        race_id   = race.get("race_id", "")
        full_race = get_race(race_id, date_str) or {}

        profiles_for_race: list[dict] = []
        for runner in race.get("shortlisted_runners") or []:
            hid = str(runner.get("horse_id") or "")
            profile = all_profiles.get(hid)
            if profile:
                profiles_for_race.append(profile)

        output_races.append(
            {
                "race_id":   race_id,
                "course":    full_race.get("course") or race.get("course", ""),
                "off_time":  full_race.get("off_time") or race.get("off_time", ""),
                "race_name": full_race.get("race_name") or race.get("race_name", ""),
                "profiles":  profiles_for_race,
            }
        )

    generated_at_iso = datetime.now(timezone.utc).isoformat()
    generated_at_hm  = datetime.now(timezone.utc).strftime("%H:%M")

    json_payload: dict = {
        "date":         date_str,
        "generated_at": generated_at_iso,
        "horses_fetched": total_horses,
        "races":        output_races,
    }

    # --- Save JSON ------------------------------------------------------------
    json_dest = data_path(f"full_form_{date_str}.json")
    if not safe_write_json(json_dest, json_payload):
        log(f"full_form_reader: failed to write JSON to {json_dest}", "ERROR")
        return 1
    log(f"full_form_reader: JSON saved to {json_dest}")

    # --- Save text report -----------------------------------------------------
    report_text = _format_report(date_str, generated_at_hm, output_races)
    report_dest = report_path(f"full_form_{date_str}.txt")

    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
        log(f"full_form_reader: text report saved to {report_dest}")
    except OSError as exc:
        log(f"full_form_reader: failed to write text report — {exc}", "ERROR")
        return 1

    summary = (
        f"full_form_reader: SUCCESS — {total_horses} horses processed "
        f"across {len(output_races)} races for {date_str}"
    )
    log(summary)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
