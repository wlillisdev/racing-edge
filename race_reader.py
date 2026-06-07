"""
race_reader.py — Read race context for each shortlisted race and produce
narrative summaries.

For each race in today's shortlist, produces a narrative covering:
    • Race type and class description
    • Field size assessment
    • Going assessment
    • Pace shape (front-runner signals in form)
    • Standout candidate (clearly superior form score)
    • Cluster risk (multiple horses at similar form level)
    • Overall verdict: STANDOUT LIKELY | CLUSTERED | NEEDS FORM DEPTH | MESSY

Form scoring model (last 3 runs, most-recent = rightmost char):
    Win (1)          → 10 pts
    2nd (2)          → 7 pts
    3rd (3)          → 5 pts
    4th (4)          → 3 pts
    5th+ (5-9/0)     → 1 pt
    F/U/P (fell etc) → 0 pts
    Unknown char     → 0 pts (skipped)

Saves:
    reports/race_reader_YYYY-MM-DD.txt

Exit codes:
    0  — success
    1  — failure (no shortlist, write error)
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from src.helpers import data_path, log, report_path, safe_load_json, today_str
from racecard_loader import get_race

# ---------------------------------------------------------------------------
# Form parsing
# ---------------------------------------------------------------------------

# Chars treated as "front-runner signals" in older form strings aren't easily
# detectable from form figures alone; we use repeated wins as a proxy.

_FORM_SCORES: dict[str, int] = {
    "1": 10,
    "2": 7,
    "3": 5,
    "4": 3,
}
_FRONT_RUNNER_WIN_THRESHOLD: int = 2   # >= N wins in last 4 chars → front-runner signal


def _parse_form_chars(form: str) -> list[str]:
    """Return the individual form run-characters, most-recent last.

    Strips hyphens and slashes used as season separators.
    Characters that are decimal digits or F/U/P/B/R are retained.
    """
    cleaned = form.replace("-", "").replace("/", "").strip().upper()
    valid_chars: list[str] = []
    for ch in cleaned:
        if ch.isdigit() or ch in "FUPBR":
            valid_chars.append(ch)
    return valid_chars


def _score_char(ch: str) -> int:
    """Convert a single form character to its run score."""
    if ch in _FORM_SCORES:
        return _FORM_SCORES[ch]
    if ch.isdigit():        # 5, 6, 7, 8, 9, 0 → 5th or worse
        return 1
    # F, U, P, B, R → fell/unseated/pulled up/brought down/refused
    return 0


def _form_score(form: str | None) -> int | None:
    """Return the sum of the last-3-runs score, or None if no parseable form."""
    if not form:
        return None
    chars = _parse_form_chars(form)
    if not chars:
        return None
    last3 = chars[-3:]
    return sum(_score_char(c) for c in last3)


def _is_front_runner_profile(form: str | None) -> bool:
    """Heuristic: if the horse won twice in its last 4 outings, flag as potential
    front-runner (wins from the front is a common pattern)."""
    if not form:
        return False
    chars = _parse_form_chars(form)
    last4 = chars[-4:] if len(chars) >= 4 else chars
    return last4.count("1") >= _FRONT_RUNNER_WIN_THRESHOLD


# ---------------------------------------------------------------------------
# Race-level descriptions
# ---------------------------------------------------------------------------

_CLASS_DESCRIPTIONS: dict[str, str] = {
    "1": "Group/Grade 1 — elite",
    "2": "Group/Grade 2 — high-class",
    "3": "Group/Grade 3 — very competitive",
    "4": "Listed/Class 4 — competitive",
    "5": "Class 5 — moderate handicap",
    "6": "Class 6 — lower handicap",
    "7": "Class 7 — lowest tier",
}

_SURFACE_DESCRIPTIONS: dict[str, str] = {
    "turf":       "Turf track",
    "aw":         "All-Weather surface",
    "all-weather": "All-Weather surface",
}

_GOING_NOTES: dict[str, str] = {
    "firm":              "Very fast ground — suits nippy types",
    "good to firm":      "Fast ground — generally fair",
    "good":              "Ideal ground for most horses",
    "good to soft":      "Slightly testing — all-rounders cope",
    "soft":              "Testing — stamina premium",
    "heavy":             "Very testing — stamina essential",
    "standard":          "Standard All-Weather going",
    "standard to slow":  "Slightly slow All-Weather",
    "slow":              "Slow All-Weather — stamina premium",
}


def _describe_field_size(field_size: int) -> str:
    if field_size <= 4:
        return f"Tiny field of {field_size} — strongly favours decisive selector"
    if field_size <= 6:
        return f"Small field of {field_size} — may suit a short-priced selection"
    if field_size <= 10:
        return f"Manageable field of {field_size}"
    if field_size <= 16:
        return f"Medium-large field of {field_size} — pace likely to be strong"
    return f"Large field of {field_size} — messy, pace analysis critical"


def _describe_going(going: str) -> str:
    key = going.strip().lower()
    return _GOING_NOTES.get(key, f"Going: {going}")


def _describe_class(race_class: str, race_type: str) -> str:
    desc = _CLASS_DESCRIPTIONS.get(race_class.strip())
    if desc:
        return f"{race_type} — {desc}"
    return f"{race_type} — class {race_class}"


# ---------------------------------------------------------------------------
# Verdict logic
# ---------------------------------------------------------------------------

_STANDOUT_GAP: int = 5   # top scorer must be >= N pts clear of second for STANDOUT
_CLUSTER_GAP:  int = 3   # if multiple horses within N pts → CLUSTERED


def _compute_verdict(
    scored_runners: list[tuple[dict, int | None]],
    front_runner_count: int,
) -> str:
    """Derive a one-word verdict from the scored runner list."""
    # Filter to runners with a score.
    with_scores: list[tuple[dict, int]] = [
        (r, s) for r, s in scored_runners if s is not None
    ]

    if len(with_scores) < 2:
        return "NEEDS FORM DEPTH"

    sorted_scores = sorted(with_scores, key=lambda x: x[1], reverse=True)
    top_score     = sorted_scores[0][1]
    second_score  = sorted_scores[1][1]

    gap = top_score - second_score

    # Count runners within CLUSTER_GAP of the top score.
    cluster_members = sum(1 for _, s in sorted_scores if (top_score - s) <= _CLUSTER_GAP)

    if gap >= _STANDOUT_GAP:
        return "STANDOUT LIKELY"
    if cluster_members >= 3:
        return "MESSY"
    if cluster_members >= 2:
        return "CLUSTERED"
    return "NEEDS FORM DEPTH"


# ---------------------------------------------------------------------------
# Narrative builder
# ---------------------------------------------------------------------------

def _build_race_narrative(race: dict) -> str:
    """Return a multi-line narrative string for one race."""
    course    = race.get("course", "Unknown")
    off_time  = race.get("off_time", "")
    race_name = race.get("race_name", "")
    race_type = str(race.get("type") or "Unknown")
    race_cls  = str(race.get("class") or "?")
    field_sz  = int(race.get("field_size") or 0)
    going     = str(race.get("going") or "Unknown")
    surface   = str(race.get("surface") or "")
    runners   = race.get("runners") or []

    lines: list[str] = [
        f"--- {course.upper()} {off_time} — {race_name} ---",
        "",
        f"Type/Class : {_describe_class(race_cls, race_type)}",
        f"Surface    : {_SURFACE_DESCRIPTIONS.get(surface.lower(), surface or 'Unknown')}",
        f"Field      : {_describe_field_size(field_sz)}",
        f"Going      : {_describe_going(going)}",
        "",
    ]

    # Score all runners.
    scored: list[tuple[dict, int | None]] = []
    front_runner_count = 0

    for runner in runners:
        form = runner.get("form") or ""
        score = _form_score(form)
        scored.append((runner, score))
        if _is_front_runner_profile(form):
            front_runner_count += 1

    # Sort by score descending for display.
    scored_sorted = sorted(
        scored,
        key=lambda x: (x[1] is not None, x[1] or 0),
        reverse=True,
    )

    # Pace shape.
    if front_runner_count == 0:
        pace_note = "No clear front-runner evident from form — likely tactical"
    elif front_runner_count == 1:
        pace_note = "One likely front-runner — pace may be steady"
    else:
        pace_note = f"{front_runner_count} potential front-runners — contested pace expected"

    lines.append(f"Pace shape : {pace_note}")
    lines.append("")

    # Runner form scores table.
    lines.append("Form scores (last 3 runs):")
    for runner, score in scored_sorted:
        horse = runner.get("horse", "Unknown")
        form  = runner.get("form") or "-"
        score_str = str(score) if score is not None else "N/A"
        lines.append(f"  {horse:<30} form={form:<12} score={score_str}")

    lines.append("")

    # Standout / cluster analysis.
    with_scores = [(r, s) for r, s in scored_sorted if s is not None]
    if len(with_scores) >= 2:
        top_runner, top_score      = with_scores[0]
        second_runner, second_score = with_scores[1]
        gap = top_score - second_score
        if gap >= _STANDOUT_GAP:
            lines.append(
                f"Standout   : {top_runner.get('horse', '?')} "
                f"({top_score} pts, {gap} clear of {second_runner.get('horse', '?')})"
            )
        else:
            cluster = [r.get("horse", "?") for r, s in with_scores if top_score - s <= _CLUSTER_GAP]
            lines.append(f"Cluster    : {', '.join(cluster)} all within {_CLUSTER_GAP} pts")
    elif len(with_scores) == 1:
        lines.append(f"Standout   : {with_scores[0][0].get('horse', '?')} (only scored runner)")

    lines.append("")

    # Verdict.
    verdict = _compute_verdict(scored, front_runner_count)
    lines.append(f"Verdict    : {verdict}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Load shortlist, generate race narratives, save report. Returns exit code."""
    log("race_reader.py started")

    date_str = today_str()

    # --- Load shortlist -------------------------------------------------------
    shortlist_path = data_path(f"shortlist_{date_str}.json")
    shortlist = safe_load_json(shortlist_path)

    if shortlist is None:
        log(
            "race_reader: shortlist data unavailable — "
            "ensure race_shortlist.py has been executed first",
            "ERROR",
        )
        return 1

    shortlisted_races: list[dict] = shortlist.get("races") or []
    if not shortlisted_races:
        log("race_reader: no races in shortlist — nothing to process", "WARNING")
        # Write an empty report rather than failing hard.
        shortlisted_races = []

    log(f"race_reader: reading {len(shortlisted_races)} shortlisted races")

    # --- Build report ---------------------------------------------------------
    generated_at = datetime.now(timezone.utc).strftime("%H:%M")
    report_lines: list[str] = [
        "RACING INTELLIGENCE SYSTEM - RACE READER REPORT",
        f"Date: {date_str}",
        f"Generated: {generated_at}",
        f"Races analysed: {len(shortlisted_races)}",
        "",
        "=" * 70,
        "",
    ]

    for entry in shortlisted_races:
        race_id = entry.get("race_id", "")

        # Fetch the full race dict from the racecard (includes all runners).
        race = get_race(race_id, date_str)
        if race is None:
            log(f"race_reader: race_id '{race_id}' not found in racecard — skipping", "WARNING")
            report_lines.append(f"[SKIPPED] race_id={race_id} — not found in racecard\n")
            continue

        try:
            narrative = _build_race_narrative(race)
        except Exception as exc:
            log(f"race_reader: error building narrative for race_id '{race_id}' — {exc}", "WARNING")
            narrative = f"[ERROR] Could not generate narrative: {exc}\n"

        report_lines.append(narrative)
        report_lines.append("=" * 70)
        report_lines.append("")

    report_text = "\n".join(report_lines)
    report_dest = report_path(f"race_reader_{date_str}.txt")

    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
        log(f"race_reader: report saved to {report_dest}")
    except OSError as exc:
        log(f"race_reader: failed to write report — {exc}", "ERROR")
        return 1

    summary = (
        f"race_reader: SUCCESS — {len(shortlisted_races)} races analysed for {date_str}"
    )
    log(summary)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
