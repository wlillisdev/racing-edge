"""
horse_tracker.py — Maintain the watchlist of horses flagged for future follow-up.

Two operational modes:
    flag mode   (default / --flag):
        Load today's results and nap_candidates, apply flagging rules,
        and persist matches to data/horse_tracker.json.

    review mode (--review):
        Load today's racecard. For each runner in the tracker, check
        whether they are running today AND conditions are met.
        Emit TRACKER ALERT lines and save a review report.

Design principles
-----------------
- The tracker is informational ONLY — it never auto-promotes a horse to a bet.
- A tracked horse is only "activated" when its NEXT conditions actually match
  the specific reason it was flagged (e.g., flagged for wrong going → only
  activated when today's going matches the required going).
- Maximum 50 active tracked horses (oldest dropped when limit exceeded).
- Entries older than 90 days are expired; follow_up_date is 60 days.

Tracker file: data/horse_tracker.json (persistent, not date-stamped).

Exit codes:
    0 — success (including graceful "no data" case)
    1 — unrecoverable write error
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from src.helpers import (
    data_path,
    log,
    report_path,
    safe_load_json,
    safe_write_json,
    today_str,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TRACKER_FILE = "horse_tracker.json"
MAX_ACTIVE = 50            # Maximum simultaneous active entries
EXPIRE_DAYS = 90           # Expire entries older than this
FOLLOW_UP_DAYS = 60        # follow_up_date window from flag date
NEAR_MISS_LENGTHS = 2.0    # Beaten within this many lengths = near miss
UNEXPOSED_MAX_RUNS = 5     # Career runs <= this qualifies as unexposed
UNEXPOSED_MIN_RUNS = 2     # Career runs >= this (to avoid debutants)
UNEXPOSED_MAX_AGE = 4      # Age <= this to be considered unexposed


# ---------------------------------------------------------------------------
# Going classification helpers
# ---------------------------------------------------------------------------

# Canonical going groups — anything in "fast" group is firm/good ground;
# "slow" group is soft/heavy.  Used to detect "wrong going" mismatches.
_FAST_GOING: frozenset[str] = frozenset(
    {"Firm", "Good to Firm", "Good", "Standard"}
)
_SLOW_GOING: frozenset[str] = frozenset(
    {"Good to Soft", "Soft", "Heavy", "Slow"}
)


def _going_is_fast(going: str) -> bool:
    return going.strip().title() in _FAST_GOING


def _going_is_slow(going: str) -> bool:
    return going.strip().title() in _SLOW_GOING


def _classify_going(going: str) -> str:
    """Return 'fast', 'slow', or 'unknown'."""
    g = going.strip().title()
    if g in _FAST_GOING:
        return "fast"
    if g in _SLOW_GOING:
        return "slow"
    return "unknown"


# ---------------------------------------------------------------------------
# Tracker persistence
# ---------------------------------------------------------------------------

def _load_tracker() -> dict:
    """Load the persistent horse_tracker.json. Returns a clean skeleton if missing."""
    path = data_path(TRACKER_FILE)
    data = safe_load_json(path)
    if data is None:
        log("horse_tracker: tracker file not found — starting fresh", "INFO")
        return {"last_updated": "", "tracked": []}
    return data


def _save_tracker(tracker: dict) -> bool:
    """Persist the tracker to horse_tracker.json."""
    tracker["last_updated"] = datetime.now(timezone.utc).isoformat()
    path = data_path(TRACKER_FILE)
    ok = safe_write_json(path, tracker)
    if ok:
        log(f"horse_tracker: saved tracker → {path}")
    else:
        log(f"horse_tracker: FAILED to save tracker → {path}", "ERROR")
    return ok


# ---------------------------------------------------------------------------
# Entry helpers
# ---------------------------------------------------------------------------

def _make_entry(
    horse_id: str,
    horse_name: str,
    flag_reason: str,
    required_conditions: str,
    today: str,
) -> dict:
    follow_up = (date.fromisoformat(today) + timedelta(days=FOLLOW_UP_DAYS)).isoformat()
    return {
        "horse_id":             horse_id,
        "horse_name":           horse_name,
        "flagged_date":         today,
        "flag_reason":          flag_reason,
        "required_conditions":  required_conditions,
        "status":               "watching",
        "follow_up_date":       follow_up,
        "result_when_watched":  None,
    }


def _expire_old(tracked: list[dict], today_date: date) -> list[dict]:
    """Set status = 'expired' for entries older than EXPIRE_DAYS."""
    cutoff = today_date - timedelta(days=EXPIRE_DAYS)
    for entry in tracked:
        if entry.get("status") == "watching":
            try:
                flagged = date.fromisoformat(entry["flagged_date"])
                if flagged < cutoff:
                    entry["status"] = "expired"
                    log(
                        f"horse_tracker: expired {entry['horse_name']} "
                        f"(flagged {entry['flagged_date']})",
                        "INFO",
                    )
            except (ValueError, KeyError):
                pass
    return tracked


def _trim_to_max(tracked: list[dict]) -> list[dict]:
    """If active entries exceed MAX_ACTIVE, drop the oldest by flagged_date."""
    active = [e for e in tracked if e.get("status") == "watching"]
    inactive = [e for e in tracked if e.get("status") != "watching"]

    if len(active) > MAX_ACTIVE:
        active_sorted = sorted(
            active,
            key=lambda e: e.get("flagged_date") or "",
        )
        dropped = active_sorted[: len(active) - MAX_ACTIVE]
        kept = active_sorted[len(active) - MAX_ACTIVE :]
        for d in dropped:
            log(
                f"horse_tracker: dropped {d['horse_name']} "
                f"(tracker full, oldest removed)",
                "WARNING",
            )
        return inactive + kept
    return tracked


def _upsert_entry(tracked: list[dict], new_entry: dict) -> list[dict]:
    """Add or update an entry by horse_id.

    If the horse is already tracked with status='watching', update the reason
    and conditions only if the new flag is different (don't overwrite with
    a duplicate).  If it was expired, re-activate it.
    """
    horse_id = new_entry["horse_id"]
    for existing in tracked:
        if existing.get("horse_id") == horse_id:
            if existing.get("status") in ("watching", "expired"):
                # Re-activate and update
                existing["status"]              = "watching"
                existing["flag_reason"]         = new_entry["flag_reason"]
                existing["required_conditions"] = new_entry["required_conditions"]
                existing["flagged_date"]        = new_entry["flagged_date"]
                existing["follow_up_date"]      = new_entry["follow_up_date"]
                existing["result_when_watched"] = None
                log(
                    f"horse_tracker: updated existing entry for "
                    f"{new_entry['horse_name']} ({horse_id})",
                    "INFO",
                )
            return tracked  # already present — no duplicate
    tracked.append(new_entry)
    log(
        f"horse_tracker: added new entry — {new_entry['horse_name']} "
        f"({horse_id}) | reason={new_entry['flag_reason']}",
        "INFO",
    )
    return tracked


# ---------------------------------------------------------------------------
# FLAG MODE — flagging logic
# ---------------------------------------------------------------------------

def _results_runners(results_doc: dict) -> list[dict]:
    """Flatten all runner records from a results document."""
    runners: list[dict] = []
    for key in ("official_results", "shadow_results", "watchlist_results"):
        for r in results_doc.get(key) or []:
            runners.append(r)
    return runners


def _candidates_runners(candidates_doc: dict) -> list[dict]:
    """Flatten all candidates from a nap_candidates document."""
    runners: list[dict] = []
    nap = candidates_doc.get("nap")
    if nap:
        runners.append(nap)
    best = candidates_doc.get("best_of_card")
    if best:
        runners.append(best)
    for section in ("watchlist", "shadow"):
        for r in candidates_doc.get(section) or []:
            runners.append(r)
    return runners


def _detect_draw_bias(going: str, race_course: str) -> bool:
    """Simple heuristic — flag draw-sensitive tracks.

    In production this would query historical draw stats from the DB.
    Conservative rule: known draw-biased courses are flagged.
    """
    draw_biased_courses = {
        "chester", "beverley", "windsor", "bath", "epsom",
        "catterick", "hamilton", "carlisle",
    }
    return race_course.strip().lower() in draw_biased_courses


def run_flag_mode(date_str: str) -> int:
    """Flag horses from today's data. Returns exit code."""
    log(f"horse_tracker [flag mode]: date={date_str}")

    today_date = date.fromisoformat(date_str)
    tracker = _load_tracker()
    tracked: list[dict] = tracker.get("tracked") or []

    # --- Expire old entries first ---
    tracked = _expire_old(tracked, today_date)

    # --- Load data sources ---
    results_path = data_path(f"results_{date_str}.json")
    results_doc = safe_load_json(results_path)

    candidates_path = data_path(f"nap_candidates_{date_str}.json")
    candidates_doc = safe_load_json(candidates_path)

    if results_doc is None and candidates_doc is None:
        log(
            f"horse_tracker [flag]: no results or candidates found for {date_str} "
            "— nothing to flag today",
            "WARNING",
        )
        # Still persist (to update last_updated and expiry changes)
        tracker["tracked"] = tracked
        _save_tracker(tracker)
        return 0

    # Flatten runner lists
    result_runners = _results_runners(results_doc) if results_doc else []
    candidate_runners = _candidates_runners(candidates_doc) if candidates_doc else []
    all_runners = result_runners + candidate_runners

    flags_added = 0

    for runner in all_runners:
        horse_id = str(runner.get("horse_id") or "").strip()
        horse_name = str(runner.get("horse") or runner.get("horse_name") or "").strip()

        if not horse_id or not horse_name:
            continue

        position = runner.get("position")
        beaten_lengths = runner.get("beaten_lengths")
        placed = runner.get("placed")
        won = runner.get("won")
        going = str(runner.get("going") or "").strip()
        course = str(runner.get("course") or "").strip()

        # Numeric position for comparisons
        try:
            pos_int = int(position) if position is not None else None
        except (ValueError, TypeError):
            pos_int = None

        # Numeric beaten lengths
        try:
            bl_float = float(beaten_lengths) if beaten_lengths is not None else None
        except (ValueError, TypeError):
            bl_float = None

        # Horse age and career runs from racecard candidate data
        age = runner.get("age")
        career_runs = runner.get("runs") or runner.get("career_runs")
        try:
            age_int = int(str(age).strip()) if age else None
        except (ValueError, TypeError):
            age_int = None
        try:
            runs_int = int(career_runs) if career_runs is not None else None
        except (ValueError, TypeError):
            runs_int = None

        new_entry: Optional[dict] = None

        # ---- Rule 1: Near miss (beaten within 2 lengths, didn't win) ----
        if (
            pos_int is not None
            and pos_int > 1
            and bl_float is not None
            and bl_float <= NEAR_MISS_LENGTHS
        ):
            new_entry = _make_entry(
                horse_id=horse_id,
                horse_name=horse_name,
                flag_reason="near_miss",
                required_conditions=(
                    f"Beaten {bl_float:.2f}L — watch for next run at similar level"
                ),
                today=date_str,
            )

        # ---- Rule 2: Wrong going (ran on going that may not suit) ----
        if new_entry is None and going:
            going_class = _classify_going(going)
            if going_class == "slow":
                # Ran on slow/soft/heavy — flag that it may prefer faster
                new_entry = _make_entry(
                    horse_id=horse_id,
                    horse_name=horse_name,
                    flag_reason="wrong_going",
                    required_conditions=(
                        "Needs Good to Firm or Firm ground — "
                        f"ran on {going} today"
                    ),
                    today=date_str,
                )
            elif going_class == "fast" and pos_int is not None and pos_int > 3:
                # Underperformed on fast ground — may prefer softer
                new_entry = _make_entry(
                    horse_id=horse_id,
                    horse_name=horse_name,
                    flag_reason="wrong_going",
                    required_conditions=(
                        "Consider Good to Soft or Soft — "
                        f"underperformed on {going} today"
                    ),
                    today=date_str,
                )

        # ---- Rule 3: Bad draw (draw-biased course and non-placed) ----
        if new_entry is None and course:
            if _detect_draw_bias(going, course):
                draw = runner.get("draw")
                try:
                    draw_int = int(draw) if draw is not None else None
                except (ValueError, TypeError):
                    draw_int = None

                if draw_int is not None and draw_int > 6 and pos_int is not None and pos_int > 3:
                    new_entry = _make_entry(
                        horse_id=horse_id,
                        horse_name=horse_name,
                        flag_reason="bad_draw",
                        required_conditions=(
                            f"Needs low draw (stall 1-5) at {course} — "
                            f"drawn {draw_int} today"
                        ),
                        today=date_str,
                    )

        # ---- Rule 4: Place profile (watchlist horse that placed but didn't win) ----
        if new_entry is None:
            is_watchlist = runner.get("candidate_type") == "watchlist"
            if is_watchlist and placed and not won:
                new_entry = _make_entry(
                    horse_id=horse_id,
                    horse_name=horse_name,
                    flag_reason="place_profile",
                    required_conditions=(
                        "Consistent placer — watch for each-way opportunities "
                        "at similar level and conditions"
                    ),
                    today=date_str,
                )

        # ---- Rule 5: Unexposed (young, few career runs) ----
        if new_entry is None:
            if (
                age_int is not None
                and runs_int is not None
                and age_int <= UNEXPOSED_MAX_AGE
                and UNEXPOSED_MIN_RUNS <= runs_int <= UNEXPOSED_MAX_RUNS
            ):
                new_entry = _make_entry(
                    horse_id=horse_id,
                    horse_name=horse_name,
                    flag_reason="unexposed",
                    required_conditions=(
                        f"Age {age_int}, {runs_int} career runs — watch for "
                        "improvement as handicapper adjusts"
                    ),
                    today=date_str,
                )

        if new_entry is not None:
            tracked = _upsert_entry(tracked, new_entry)
            flags_added += 1

    # --- Enforce size cap ---
    tracked = _trim_to_max(tracked)

    # --- Persist ---
    tracker["tracked"] = tracked
    ok = _save_tracker(tracker)

    active_count = sum(1 for e in tracked if e.get("status") == "watching")
    log(
        f"horse_tracker [flag]: {flags_added} flags added/updated, "
        f"{active_count} active entries total"
    )
    print(
        f"horse_tracker [flag]: COMPLETE — "
        f"flags_added={flags_added}, active_tracked={active_count}"
    )
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# REVIEW MODE — check today's racecard for tracked runners
# ---------------------------------------------------------------------------

def _conditions_met(entry: dict, runner_going: str, runner_course: str) -> bool:
    """Check whether today's conditions satisfy what was required for this entry.

    Logic is conservative — when in doubt, return False so we don't
    generate false positives.
    """
    reason = entry.get("flag_reason", "")
    required = (entry.get("required_conditions") or "").lower()

    if reason == "near_miss":
        # Near miss: flag any subsequent run — trainer likely targets a win
        return True

    if reason == "wrong_going":
        if not runner_going:
            return False
        going_class = _classify_going(runner_going)
        if "good to firm" in required or "firm" in required:
            # Needs fast going
            return going_class == "fast"
        if "soft" in required or "good to soft" in required:
            # Needs slow going
            return going_class == "slow"
        return False

    if reason == "bad_draw":
        # Needs low draw at this track — course match checked here;
        # draw number check happens in the caller where draw is available
        return runner_course.lower() in required

    if reason == "place_profile":
        # Place profile: always relevant when running
        return True

    if reason == "unexposed":
        # Unexposed: always worth monitoring
        return True

    return False


def run_review_mode(date_str: str) -> int:
    """Review today's racecard for tracked horses. Returns exit code."""
    log(f"horse_tracker [review mode]: date={date_str}")

    tracker = _load_tracker()
    tracked: list[dict] = tracker.get("tracked") or []

    active_tracked = {
        e["horse_id"]: e
        for e in tracked
        if e.get("status") == "watching" and e.get("horse_id")
    }

    if not active_tracked:
        log("horse_tracker [review]: no active tracked horses — nothing to check")
        _write_review_report(date_str, [])
        return 0

    # Load today's racecard
    racecard_path = data_path(f"racecards_{date_str}.json")
    racecard_doc = safe_load_json(racecard_path)

    if racecard_doc is None:
        log(
            f"horse_tracker [review]: racecard not found at {racecard_path}. "
            "Run run_daily.py first.",
            "WARNING",
        )
        _write_review_report(date_str, [])
        return 0

    racecards: list[dict] = racecard_doc.get("racecards") or []
    alerts: list[dict] = []

    for race in racecards:
        race_going = str(race.get("going") or "").strip()
        race_course = str(race.get("course") or "").strip()
        runners: list[dict] = race.get("runners") or []

        for runner in runners:
            horse_id = str(runner.get("horse_id") or "").strip()
            horse_name = str(runner.get("horse") or "").strip()

            if horse_id not in active_tracked:
                continue

            entry = active_tracked[horse_id]

            # Extract draw for bad_draw condition check
            draw = runner.get("draw")
            try:
                draw_int = int(draw) if draw is not None else None
            except (ValueError, TypeError):
                draw_int = None

            # Determine if the specific conditions are met today
            conditions_met = _conditions_met(entry, race_going, race_course)

            # For bad_draw: extra check that draw is low today
            if entry.get("flag_reason") == "bad_draw" and conditions_met:
                if draw_int is not None and draw_int > 5:
                    conditions_met = False  # Still in a high draw
                elif draw_int is None:
                    conditions_met = False  # Can't confirm

            alert = {
                "horse_id":             horse_id,
                "horse_name":           horse_name,
                "course":               race_course,
                "off_time":             str(race.get("off_time") or ""),
                "race_id":              str(race.get("race_id") or ""),
                "going":                race_going,
                "draw":                 draw_int,
                "flag_reason":          entry.get("flag_reason"),
                "required_conditions":  entry.get("required_conditions"),
                "flagged_date":         entry.get("flagged_date"),
                "conditions_met":       conditions_met,
            }
            alerts.append(alert)

    # Print console alerts
    for alert in alerts:
        if alert["conditions_met"]:
            print(
                f"TRACKER ALERT: {alert['horse_name']} running today — "
                f"conditions match. "
                f"Required: {alert['required_conditions']}. "
                f"Reason flagged: {alert['flag_reason']}. "
                f"Race: {alert['course']} {alert['off_time']}"
            )
        else:
            print(
                f"TRACKER WATCH: {alert['horse_name']} running today but "
                f"conditions NOT met ({alert['flag_reason']}). "
                f"Required: {alert['required_conditions']}"
            )

    _write_review_report(date_str, alerts)

    activated = sum(1 for a in alerts if a["conditions_met"])
    log(
        f"horse_tracker [review]: {len(alerts)} tracked horses running today, "
        f"{activated} with conditions met"
    )
    print(
        f"horse_tracker [review]: COMPLETE — "
        f"running_today={len(alerts)}, activated={activated}"
    )
    return 0


def _write_review_report(date_str: str, alerts: list[dict]) -> None:
    """Write the tracker review report file."""
    lines: list[str] = [
        "HORSE TRACKER REVIEW",
        f"Date: {date_str}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    activated = [a for a in alerts if a["conditions_met"]]
    watching = [a for a in alerts if not a["conditions_met"]]

    if activated:
        lines.append("=== ACTIVATED ALERTS (conditions met) ===")
        for a in activated:
            lines += [
                f"TRACKER ALERT: {a['horse_name']}",
                f"  Race:       {a['course']} {a['off_time']}",
                f"  Going:      {a['going']}",
                f"  Reason:     {a['flag_reason']}",
                f"  Required:   {a['required_conditions']}",
                f"  Flagged on: {a['flagged_date']}",
                "",
            ]
    else:
        lines.append("No activated alerts today (no tracked horses with conditions met).")
        lines.append("")

    if watching:
        lines.append("=== WATCHING (running but conditions not met) ===")
        for a in watching:
            lines.append(
                f"  {a['horse_name']} — {a['course']} {a['off_time']} "
                f"| {a['flag_reason']} | Needs: {a['required_conditions']}"
            )
        lines.append("")

    if not alerts:
        lines.append("No tracked horses are running today.")

    report_dest = report_path(f"horse_tracker_review_{date_str}.txt")
    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        log(f"horse_tracker [review]: report saved → {report_dest}")
    except OSError as exc:
        log(f"horse_tracker [review]: failed to write report — {exc}", "ERROR")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    mode = "flag"
    if "--review" in sys.argv:
        mode = "review"
    elif "--flag" in sys.argv:
        mode = "flag"

    date_str = today_str()
    log(f"horse_tracker.py started — mode={mode}, date={date_str}")

    if mode == "review":
        return run_review_mode(date_str)
    else:
        return run_flag_mode(date_str)


if __name__ == "__main__":
    sys.exit(main())
