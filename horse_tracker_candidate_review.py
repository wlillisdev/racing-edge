"""
horse_tracker_candidate_review.py — Review shortlisted candidates against
the horse tracker.

Purpose:
    Load data/shortlist_YYYY-MM-DD.json and data/horse_tracker.json.
    For each shortlisted horse, check whether they are in the tracker,
    what the flag reason was, and whether today's conditions match.

Annotation values (written into each shortlisted runner):
    "TRACKER_MATCH_CONDITIONS_MET"   — in tracker + conditions match today
    "TRACKER_MATCH_CONDITIONS_UNMET" — in tracker + conditions don't match
    "TRACKER_NEW"                    — not in tracker

This is INFORMATIONAL ONLY — it annotates the shortlist with tracker context
and does NOT modify NAP scores or any bet decision.

Outputs:
    data/shortlist_YYYY-MM-DD.json  (updated with tracker_context field)
    reports/tracker_candidate_review_YYYY-MM-DD.txt

Exit codes:
    0 — success (including graceful "no data" case)
    1 — write error
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
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
# Going classification (mirrors horse_tracker.py — kept local to avoid
# circular imports; both modules are run as standalone scripts)
# ---------------------------------------------------------------------------

_FAST_GOING: frozenset[str] = frozenset(
    {"Firm", "Good to Firm", "Good", "Standard"}
)
_SLOW_GOING: frozenset[str] = frozenset(
    {"Good to Soft", "Soft", "Heavy", "Slow"}
)


def _classify_going(going: str) -> str:
    g = going.strip().title()
    if g in _FAST_GOING:
        return "fast"
    if g in _SLOW_GOING:
        return "slow"
    return "unknown"


# ---------------------------------------------------------------------------
# Condition-match logic
# ---------------------------------------------------------------------------

def _conditions_match(
    entry: dict,
    today_going: str,
    today_course: str,
) -> bool:
    """Return True if today's race conditions satisfy the tracked requirement.

    Same conservative logic as horse_tracker.py review mode — in doubt,
    return False to avoid false positives.
    """
    reason = entry.get("flag_reason", "")
    required = (entry.get("required_conditions") or "").lower()

    if reason == "near_miss":
        # Near miss: relevant for any subsequent run
        return True

    if reason == "wrong_going":
        if not today_going:
            return False
        going_class = _classify_going(today_going)
        if "good to firm" in required or "firm" in required:
            return going_class == "fast"
        if "soft" in required or "good to soft" in required:
            return going_class == "slow"
        return False

    if reason == "bad_draw":
        # Course must match (draw itself is on the racecard, not shortlist)
        return today_course.lower() in required

    if reason == "place_profile":
        return True

    if reason == "unexposed":
        return True

    return False


# ---------------------------------------------------------------------------
# Shortlist updater
# ---------------------------------------------------------------------------

def _annotate_shortlist(
    shortlist_doc: dict,
    tracker_index: dict,
    today_going_by_race: dict,
    today_course_by_race: dict,
) -> tuple[dict, list[dict]]:
    """
    Walk the shortlist and annotate each runner with tracker_context.

    Returns (updated_shortlist_doc, annotation_details_list).
    annotation_details_list is used to build the report.
    """
    annotation_details: list[dict] = []

    for race in shortlist_doc.get("races") or []:
        race_id = str(race.get("race_id") or "")
        race_course = str(race.get("course") or "").strip()
        # Going is on the racecard, not always in the shortlist.
        # Use the lookup built from racecard data if available; fall back to "".
        today_going = today_going_by_race.get(race_id, "")

        for runner in race.get("shortlisted_runners") or []:
            horse_id = str(runner.get("horse_id") or "").strip()
            horse_name = str(runner.get("horse") or "").strip()

            entry: Optional[dict] = tracker_index.get(horse_id)

            if entry is None:
                runner["tracker_context"] = "TRACKER_NEW"
                annotation_details.append(
                    {
                        "horse_id":        horse_id,
                        "horse_name":      horse_name,
                        "course":          race_course,
                        "race_id":         race_id,
                        "tracker_context": "TRACKER_NEW",
                        "flag_reason":     None,
                        "conditions_met":  None,
                        "required":        None,
                    }
                )
                continue

            # Horse is in tracker — check conditions
            cond_met = _conditions_match(entry, today_going, race_course)
            context = (
                "TRACKER_MATCH_CONDITIONS_MET"
                if cond_met
                else "TRACKER_MATCH_CONDITIONS_UNMET"
            )
            runner["tracker_context"] = context
            runner["tracker_flag_reason"] = entry.get("flag_reason")
            runner["tracker_required_conditions"] = entry.get("required_conditions")
            runner["tracker_flagged_date"] = entry.get("flagged_date")

            annotation_details.append(
                {
                    "horse_id":        horse_id,
                    "horse_name":      horse_name,
                    "course":          race_course,
                    "race_id":         race_id,
                    "tracker_context": context,
                    "flag_reason":     entry.get("flag_reason"),
                    "conditions_met":  cond_met,
                    "required":        entry.get("required_conditions"),
                    "flagged_date":    entry.get("flagged_date"),
                    "today_going":     today_going,
                }
            )

    return shortlist_doc, annotation_details


# ---------------------------------------------------------------------------
# Report formatter
# ---------------------------------------------------------------------------

def _build_report(
    date_str: str,
    annotation_details: list[dict],
    total_shortlisted: int,
) -> str:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    met = [a for a in annotation_details if a["tracker_context"] == "TRACKER_MATCH_CONDITIONS_MET"]
    unmet = [a for a in annotation_details if a["tracker_context"] == "TRACKER_MATCH_CONDITIONS_UNMET"]
    new = [a for a in annotation_details if a["tracker_context"] == "TRACKER_NEW"]

    lines: list[str] = [
        "HORSE TRACKER — CANDIDATE REVIEW",
        f"Date: {date_str}",
        f"Generated: {now_str}",
        "",
        f"Total shortlisted runners reviewed: {total_shortlisted}",
        f"  In tracker (conditions met):     {len(met)}",
        f"  In tracker (conditions NOT met): {len(unmet)}",
        f"  Not in tracker:                  {len(new)}",
        "",
        "NOTE: This is informational only. Tracker context does NOT change",
        "NAP scores or official bet decisions.",
        "",
    ]

    if met:
        lines.append("=" * 60)
        lines.append("TRACKER MATCH — CONDITIONS MET (upgrade interest)")
        lines.append("=" * 60)
        for a in met:
            lines += [
                f"  {a['horse_name']} [{a['course']}]",
                f"    Flag reason:   {a['flag_reason']}",
                f"    Required:      {a['required']}",
                f"    Going today:   {a.get('today_going', 'N/A')}",
                f"    Flagged on:    {a.get('flagged_date', 'N/A')}",
                "",
            ]

    if unmet:
        lines.append("=" * 60)
        lines.append("TRACKER MATCH — CONDITIONS NOT MET (downgrade interest)")
        lines.append("=" * 60)
        for a in unmet:
            lines += [
                f"  {a['horse_name']} [{a['course']}]",
                f"    Flag reason:   {a['flag_reason']}",
                f"    Required:      {a['required']}",
                f"    Going today:   {a.get('today_going', 'N/A')}",
                f"    Flagged on:    {a.get('flagged_date', 'N/A')}",
                "",
            ]

    if not met and not unmet:
        lines.append("No shortlisted runners found in the horse tracker today.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Run tracker candidate review. Returns exit code."""
    log("horse_tracker_candidate_review.py started")

    date_str = today_str()
    log(f"horse_tracker_candidate_review: date={date_str}")

    # ------------------------------------------------------------------
    # 1. Load shortlist
    # ------------------------------------------------------------------
    shortlist_path = data_path(f"shortlist_{date_str}.json")
    shortlist_doc = safe_load_json(shortlist_path)

    if shortlist_doc is None:
        log(
            f"horse_tracker_candidate_review: shortlist not found at {shortlist_path}. "
            "Run race_shortlist.py first.",
            "WARNING",
        )
        # Write a minimal report and exit gracefully
        report_dest = report_path(f"tracker_candidate_review_{date_str}.txt")
        try:
            with open(report_dest, "w", encoding="utf-8") as fh:
                fh.write(
                    f"HORSE TRACKER — CANDIDATE REVIEW\n"
                    f"Date: {date_str}\n\n"
                    f"No shortlist data available for {date_str}.\n"
                    f"Run race_shortlist.py first.\n"
                )
        except OSError as exc:
            log(
                f"horse_tracker_candidate_review: failed to write fallback report — {exc}",
                "ERROR",
            )
        return 0

    # ------------------------------------------------------------------
    # 2. Load tracker
    # ------------------------------------------------------------------
    tracker_path = data_path("horse_tracker.json")
    tracker_doc = safe_load_json(tracker_path)

    if tracker_doc is None:
        log(
            "horse_tracker_candidate_review: horse_tracker.json not found — "
            "all horses will be marked TRACKER_NEW",
            "WARNING",
        )
        tracker_doc = {"tracked": []}

    # Build an O(1) lookup: horse_id -> entry (watching entries only)
    tracker_index: dict[str, dict] = {
        entry["horse_id"]: entry
        for entry in (tracker_doc.get("tracked") or [])
        if entry.get("status") == "watching" and entry.get("horse_id")
    }
    log(
        f"horse_tracker_candidate_review: "
        f"{len(tracker_index)} active tracked horses"
    )

    # ------------------------------------------------------------------
    # 3. Load today's racecard to get going per race
    # ------------------------------------------------------------------
    racecard_path = data_path(f"racecards_{date_str}.json")
    racecard_doc = safe_load_json(racecard_path)

    today_going_by_race: dict[str, str] = {}
    today_course_by_race: dict[str, str] = {}
    if racecard_doc is not None:
        for race in (racecard_doc.get("racecards") or []):
            race_id = str(race.get("race_id") or "")
            if race_id:
                today_going_by_race[race_id] = str(race.get("going") or "").strip()
                today_course_by_race[race_id] = str(race.get("course") or "").strip()
    else:
        log(
            "horse_tracker_candidate_review: racecard not found — "
            "going conditions will be unavailable for wrong_going checks",
            "WARNING",
        )

    # ------------------------------------------------------------------
    # 4. Annotate the shortlist
    # ------------------------------------------------------------------
    # Count total runners before annotation
    total_shortlisted = sum(
        len(race.get("shortlisted_runners") or [])
        for race in (shortlist_doc.get("races") or [])
    )

    updated_shortlist, annotation_details = _annotate_shortlist(
        shortlist_doc,
        tracker_index,
        today_going_by_race,
        today_course_by_race,
    )

    # ------------------------------------------------------------------
    # 5. Save updated shortlist JSON
    # ------------------------------------------------------------------
    updated_shortlist["tracker_reviewed_at"] = datetime.now(timezone.utc).isoformat()

    if not safe_write_json(shortlist_path, updated_shortlist):
        log(
            f"horse_tracker_candidate_review: failed to write updated shortlist — {shortlist_path}",
            "ERROR",
        )
        return 1
    log(f"horse_tracker_candidate_review: updated shortlist saved → {shortlist_path}")

    # ------------------------------------------------------------------
    # 6. Build and save text report
    # ------------------------------------------------------------------
    report_text = _build_report(date_str, annotation_details, total_shortlisted)
    report_dest = report_path(f"tracker_candidate_review_{date_str}.txt")

    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
        log(f"horse_tracker_candidate_review: report saved → {report_dest}")
    except OSError as exc:
        log(
            f"horse_tracker_candidate_review: failed to write report — {exc}",
            "ERROR",
        )
        return 1

    # ------------------------------------------------------------------
    # 7. Console summary
    # ------------------------------------------------------------------
    met_count = sum(
        1 for a in annotation_details
        if a["tracker_context"] == "TRACKER_MATCH_CONDITIONS_MET"
    )
    unmet_count = sum(
        1 for a in annotation_details
        if a["tracker_context"] == "TRACKER_MATCH_CONDITIONS_UNMET"
    )

    print(
        f"horse_tracker_candidate_review: COMPLETE — "
        f"reviewed={total_shortlisted}, "
        f"conditions_met={met_count}, "
        f"conditions_unmet={unmet_count}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
