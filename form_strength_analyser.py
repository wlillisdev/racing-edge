"""
form_strength_analyser.py — Assess the strength and relevance of each
candidate's form independently.

For each candidate, assess:
  1. Form strength:    Quality of wins/places based on RPR/TS ratings.
  2. Form relevance:   Wins/places over today's distance and going.
  3. Around-horse form: Have horses that ran near this candidate won since?
  4. Flattered risk:   Won from a pace advantage or against very weak rivals.
  5. Hidden positive:  Ran well despite a disadvantage.

Inputs:
    data/nap_candidates_YYYY-MM-DD.json   (required)
    data/full_form_YYYY-MM-DD.json        (optional — enriches analysis)

Outputs:
    data/form_strength_YYYY-MM-DD.json
    reports/form_strength_YYYY-MM-DD.txt

Exit codes:
    0  — success
    1  — unrecoverable error (write failure)
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Optional

from src.helpers import (
    data_path,
    distance_to_furlongs,
    going_normalise,
    log,
    report_path,
    safe_load_json,
    safe_write_json,
    today_str,
)


# ---------------------------------------------------------------------------
# Configuration thresholds
# ---------------------------------------------------------------------------

# Minimum RPR/TS to consider a race "competitive" (form counts for quality).
COMPETITIVE_RATING_THRESHOLD: float = 90.0

# If RPR/TS data is present and above this, award quality bonus.
HIGH_QUALITY_RATING: float = 105.0

# Form string characters considered winning/placing positions.
WIN_CHARS: frozenset[str] = frozenset({"1"})
PLACE_CHARS: frozenset[str] = frozenset({"1", "2", "3"})
FAIL_CHARS: frozenset[str] = frozenset({"F", "U", "P", "R", "B"})

# Distance tolerance for "same trip" (furlongs).
DISTANCE_TOLERANCE_F: float = 0.5

# Beaten by less than this (lengths) = "close second" / "hidden positive" candidate.
CLOSE_SECOND_THRESHOLD: float = 1.0

# Won by more than this = "easy win".
DOMINANT_WIN_THRESHOLD: float = 5.0

# Large field size for hidden positive context.
LARGE_FIELD_THRESHOLD: int = 12


# ---------------------------------------------------------------------------
# Form string parser
# ---------------------------------------------------------------------------

def _parse_form(form: str) -> list[str]:
    """Parse form string into a list of most-recent-first characters.

    Same logic as nap_selector_v3 — keeps only the most recent season segment.
    """
    if not form or form.strip() in ("-", ""):
        return []
    form = form.strip().replace(" ", "")
    last_dash = form.rfind("-")
    segment = form[last_dash + 1:] if last_dash != -1 else form
    valid: list[str] = []
    for ch in reversed(segment):
        upper = ch.upper()
        if upper.isdigit() or upper in FAIL_CHARS:
            valid.append(upper)
    return valid


# ---------------------------------------------------------------------------
# Basic (form-string-only) analysis
# ---------------------------------------------------------------------------

def _basic_form_strength(form: str) -> tuple[float, str]:
    """Estimate form strength as a percentage from last 6 chars of form string.

    Returns (strength_pct, description).
    """
    chars = _parse_form(form)
    if not chars:
        return 0.0, "No form data"

    recent = chars[:6]
    win_place_count = sum(1 for c in recent if c in PLACE_CHARS)
    strength = round(win_place_count / len(recent) * 100, 1)
    desc = f"{win_place_count}/{len(recent)} win/place finishes in last {len(recent)} runs"
    return strength, desc


def _check_flattered_risk(form: str, full_form_runs: Optional[list[dict]]) -> tuple[bool, str]:
    """Flag if horse won but only beat non-completers (F/U/P runners).

    Returns (flagged, reason).
    """
    if full_form_runs:
        for run in full_form_runs[:3]:   # check 3 most recent
            pos = str(run.get("position") or run.get("finish_position") or "").strip()
            if pos != "1":
                continue
            # Look at runner details if available.
            beaten_rivals = run.get("runners") or run.get("field") or []
            if beaten_rivals:
                completers = [
                    r for r in beaten_rivals
                    if str(r.get("position") or "").strip().upper()
                    not in ("F", "U", "P", "R", "B", "0", "")
                ]
                if len(completers) <= 2:
                    return True, "Won but most rivals failed to complete — may be flattering"
        return False, ""

    # Basic form-string heuristic: won "1" and the surrounding chars are all failures.
    chars = _parse_form(form)
    if not chars:
        return False, ""
    if chars[0] == "1" and len(chars) >= 3:
        others = chars[1:4]
        if all(c in FAIL_CHARS for c in others):
            return True, "Recent win surrounded by F/U/P results — possible flattered win"
    return False, ""


def _check_hidden_positive(
    form: str,
    field_size: Optional[int],
    full_form_runs: Optional[list[dict]],
) -> tuple[bool, str]:
    """Flag if the horse ran a notable race despite a disadvantage.

    Returns (flagged, reason).
    """
    # Full form path.
    if full_form_runs:
        for run in full_form_runs[:2]:
            pos = str(run.get("position") or run.get("finish_position") or "").strip()
            try:
                pos_int = int(pos)
            except (ValueError, TypeError):
                continue

            if pos_int not in (3, 4):
                continue

            # High runner count = harder to win.
            field = run.get("field_size") or run.get("runners_count")
            try:
                field_int = int(field) if field else 0
            except (TypeError, ValueError):
                field_int = 0

            if field_int >= LARGE_FIELD_THRESHOLD:
                return (
                    True,
                    f"Placed {pos_int}/{field_int} runners — solid effort in large field",
                )

            # Beaten lengths close to leader.
            bl = run.get("beaten_lengths") or run.get("btn")
            try:
                bl_float = float(bl) if bl else None
            except (TypeError, ValueError):
                bl_float = None

            if bl_float is not None and bl_float <= CLOSE_SECOND_THRESHOLD:
                return (
                    True,
                    f"Only {bl_float}L off the winner despite finishing {pos_int} — hidden positive",
                )

        return False, ""

    # Basic heuristic from form string + field size.
    chars = _parse_form(form)
    if not chars:
        return False, ""

    recent = chars[0]
    if recent in ("3", "4"):
        fs = field_size or 0
        if fs >= LARGE_FIELD_THRESHOLD:
            return (
                True,
                f"Last run {recent} in large field ({fs} runners) — could be better than it looks",
            )
    return False, ""


# ---------------------------------------------------------------------------
# Full-form path analysis
# ---------------------------------------------------------------------------

def _assess_form_strength_full(
    horse_id: str,
    full_form_runs: list[dict],
) -> tuple[float, str]:
    """Estimate form strength using RPR/TS data from full form."""
    if not full_form_runs:
        return 0.0, "No full form runs available"

    recent = full_form_runs[:6]
    high_quality_wins: int = 0
    competitive_places: int = 0
    total_considered: int = 0

    for run in recent:
        pos = str(run.get("position") or run.get("finish_position") or "").strip()
        try:
            pos_int = int(pos)
        except (ValueError, TypeError):
            pos_int = None

        rpr = run.get("rpr") or run.get("rating") or run.get("official_rating")
        ts  = run.get("ts")  or run.get("topspeed")
        try:
            rating = float(rpr or ts or 0)
        except (TypeError, ValueError):
            rating = 0.0

        if pos_int is not None:
            total_considered += 1
            if pos_int == 1 and rating >= HIGH_QUALITY_RATING:
                high_quality_wins += 1
            elif pos_int in (1, 2, 3) and rating >= COMPETITIVE_RATING_THRESHOLD:
                competitive_places += 1

    if total_considered == 0:
        return 0.0, "No position data in full form"

    raw_pct = (high_quality_wins * 2 + competitive_places) / (total_considered * 2) * 100
    strength = min(100.0, round(raw_pct, 1))
    desc = (
        f"{high_quality_wins} high-quality wins, "
        f"{competitive_places} competitive places from {total_considered} recent runs"
    )
    return strength, desc


def _assess_form_relevance_full(
    full_form_runs: list[dict],
    today_dist_f: float,
    today_going: str,
) -> tuple[str, str]:
    """Assess relevance of form to today's conditions from full form data.

    Returns (level: "high" | "medium" | "low", description).
    """
    if not full_form_runs:
        return "medium", "No full form data — defaulting to medium relevance"

    dist_win = False
    going_win = False
    going_placed = False
    dist_placed = False
    going_similar = False

    for run in full_form_runs:
        pos = str(run.get("position") or run.get("finish_position") or "").strip()
        try:
            pos_int = int(pos)
        except (ValueError, TypeError):
            pos_int = None

        if pos_int is None:
            continue

        win = pos_int == 1
        placed = pos_int <= 3

        # Distance check.
        raw_dist = str(run.get("distance_f") or run.get("distance") or "")
        try:
            run_dist = float(raw_dist)
        except (ValueError, TypeError):
            run_dist = distance_to_furlongs(raw_dist)

        if today_dist_f > 0 and run_dist > 0:
            if abs(today_dist_f - run_dist) <= DISTANCE_TOLERANCE_F:
                if win:
                    dist_win = True
                elif placed:
                    dist_placed = True

        # Going check — credit placed runs on same going, not just wins.
        run_going = going_normalise(run.get("going") or "")
        if today_going and run_going:
            if today_going == run_going:
                if win: going_win = True
                elif placed: going_placed = True
            elif _going_adjacent(today_going, run_going) and win:
                going_similar = True

    if dist_win and going_win:
        return "high", "Won at today's trip and going — very strong relevance"
    if dist_win or (dist_placed and going_win):
        return "high", "Proven at today's trip and/or going"
    if dist_placed or going_win or going_placed or going_similar:
        return "medium", "Some relevant form at today's conditions"
    return "low", "No obvious distance/going match in recent form"


_GOING_LADDER = [
    ["Firm", "Good to Firm", "Good", "Good to Soft", "Soft", "Heavy"],
    ["Standard", "Slow"],
]


def _going_adjacent(a: str, b: str) -> bool:
    for ladder in _GOING_LADDER:
        if a in ladder and b in ladder:
            return abs(ladder.index(a) - ladder.index(b)) == 1
    return False


# ---------------------------------------------------------------------------
# Around-horse form (form franking)
# ---------------------------------------------------------------------------

def _assess_around_horse_form(
    full_form_runs: list[dict],
) -> tuple[Optional[bool], str]:
    """Assess whether the candidate's recent races have been franked by
    subsequent results. Returns (franked: True/False/None, description).

    None means the cache is unavailable or no recent race could be matched.
    """
    try:
        from race_quality_builder import load_quality_lookup, quality_for_run
        cache = load_quality_lookup()
    except Exception:
        cache = None
    if not cache:
        return None, "Around-horse form: race quality cache unavailable"

    franked_races = 0
    weak_races = 0
    assessed = 0
    details: list[str] = []
    for run in full_form_runs[:4]:
        meta = quality_for_run(run, cache)
        if not meta:
            continue
        assessed += 1
        q = float(meta.get("q") or 0.0)
        subs = int(meta.get("subs_winners") or 0)
        field = int(meta.get("field") or 0)
        if q >= 0.25:
            franked_races += 1
            details.append(f"{run.get('course', '?')} {run.get('date', '?')}: {subs}/{field} won since")
        elif q == 0.0 and field >= 6:
            weak_races += 1

    if assessed == 0:
        return None, "Around-horse form: no recent races matched in quality cache"
    if franked_races:
        return True, (
            f"Around-horse form FRANKED — {franked_races}/{assessed} recent races "
            f"produced subsequent winners ({'; '.join(details)})"
        )
    if weak_races == assessed:
        return False, (
            f"Around-horse form WEAK — no runner from {weak_races} assessed "
            "recent race(s) has won since"
        )
    return None, f"Around-horse form: neutral ({assessed} race(s) assessed, no strong signal)"


# ---------------------------------------------------------------------------
# Per-candidate assessment
# ---------------------------------------------------------------------------

def _assess_candidate(
    candidate: dict,
    full_form: Optional[dict],
    race_context: Optional[dict],
) -> dict:
    """Build a complete form-strength assessment for a single candidate."""
    horse_id   = str(candidate.get("horse_id") or "")
    horse_name = str(candidate.get("horse") or "")
    form_str   = str(candidate.get("form") or "")
    score      = candidate.get("score", 0)
    grade      = candidate.get("grade", "")
    course     = candidate.get("course", "")
    off_time   = candidate.get("off_time", "")
    ctype      = candidate.get("candidate_type", "")

    # Attempt to pull full form runs for this horse. full_form_reader.py
    # stores runs under full_form["horses"][horse_id] — check there first
    # (same lookup as racing_wisdom._get_horse_history).
    full_form_runs: Optional[list[dict]] = None
    if full_form and isinstance(full_form, dict):
        entry = (full_form.get("horses") or {}).get(horse_id) or full_form.get(horse_id)
        if isinstance(entry, list):
            full_form_runs = entry
        elif isinstance(entry, dict):
            full_form_runs = entry.get("results") or entry.get("runs")
        elif "results" in full_form:
            full_form_runs = [
                r for r in (full_form["results"] or [])
                if str(r.get("horse_id") or "") == horse_id
            ]

    # --- 1. Form strength ---
    if full_form_runs:
        strength_pct, strength_desc = _assess_form_strength_full(horse_id, full_form_runs)
    else:
        strength_pct, strength_desc = _basic_form_strength(form_str)

    # --- 2. Form relevance ---
    today_going  = going_normalise(race_context.get("going") or "") if race_context else ""
    today_dist_f = 0.0
    if race_context:
        raw_dist = str(race_context.get("distance_f") or race_context.get("distance") or "")
        try:
            today_dist_f = float(raw_dist)
        except (ValueError, TypeError):
            today_dist_f = distance_to_furlongs(raw_dist)

    if full_form_runs and today_dist_f > 0:
        relevance_level, relevance_desc = _assess_form_relevance_full(
            full_form_runs, today_dist_f, today_going
        )
    else:
        relevance_level = "medium"
        relevance_desc = "Insufficient data for full relevance check — defaulting to medium"

    # --- 3. Around-horse form (race quality cache) ---
    # "Have horses that ran near this candidate won since?" — answered from
    # race_quality_builder's subsequent-results cache when available.
    around_horse_desc: Optional[str] = None
    around_horse_franked: Optional[bool] = None
    if full_form_runs:
        around_horse_franked, around_horse_desc = _assess_around_horse_form(full_form_runs)

    # --- 4. Flattered risk ---
    flattered, flattered_desc = _check_flattered_risk(form_str, full_form_runs)

    # --- 5. Hidden positive ---
    field_size: Optional[int] = None
    if race_context:
        try:
            field_size = int(race_context.get("field_size") or 0) or None
        except (TypeError, ValueError):
            field_size = None

    hidden_pos, hidden_desc = _check_hidden_positive(form_str, field_size, full_form_runs)

    # --- Composite flags ---
    flags: list[str] = []
    if flattered:
        flags.append("flattered_risk")
    if hidden_pos:
        flags.append("hidden_positive")
    if strength_pct >= 60:
        flags.append("strong_form")
    elif strength_pct < 30:
        flags.append("weak_form")
    if relevance_level == "high":
        flags.append("high_relevance")
    elif relevance_level == "low":
        flags.append("low_relevance")
    if around_horse_franked is True:
        flags.append("form_franked")
    elif around_horse_franked is False:
        flags.append("form_unfranked")

    return {
        "horse_id":          horse_id,
        "horse":             horse_name,
        "course":            course,
        "off_time":          off_time,
        "candidate_type":    ctype,
        "grade":             grade,
        "score":             score,
        "form":              form_str,
        "form_strength_pct": strength_pct,
        "form_strength_desc": strength_desc,
        "form_relevance":    relevance_level,
        "form_relevance_desc": relevance_desc,
        "around_horse_form": around_horse_desc,
        "flattered_risk":    flattered,
        "flattered_desc":    flattered_desc or None,
        "hidden_positive":   hidden_pos,
        "hidden_desc":       hidden_desc or None,
        "flags":             flags,
        "full_form_available": full_form_runs is not None,
    }


# ---------------------------------------------------------------------------
# Report formatter
# ---------------------------------------------------------------------------

def _format_text_report(date_str: str, generated_hm: str, assessments: list[dict]) -> str:
    sep = "=" * 56
    lines: list[str] = [
        sep,
        "  FORM STRENGTH ANALYSIS",
        f"  Date: {date_str}  |  Generated: {generated_hm}",
        sep,
        "",
    ]

    if not assessments:
        lines.append("  No candidates to assess.")
        return "\n".join(lines)

    for a in assessments:
        ctype = a.get("candidate_type", "").upper()
        horse = a.get("horse", "Unknown")
        course = a.get("course", "")
        off_time = a.get("off_time", "")
        grade = a.get("grade", "")
        score = a.get("score", 0)
        form = a.get("form", "")
        strength = a.get("form_strength_pct", 0)
        strength_desc = a.get("form_strength_desc", "")
        relevance = a.get("form_relevance", "medium").upper()
        relevance_desc = a.get("form_relevance_desc", "")
        flattered = a.get("flattered_risk", False)
        hidden = a.get("hidden_positive", False)
        flags = a.get("flags", [])

        lines += [
            f"  [{ctype}] {horse.upper()} — {course} {off_time}",
            f"  Grade: {grade}  |  Score: {score:.1f}  |  Form: {form}",
            f"  Form Strength: {strength:.1f}%  — {strength_desc}",
            f"  Form Relevance: {relevance}  — {relevance_desc}",
        ]

        if flattered:
            lines.append(f"  [!] FLATTERED RISK: {a.get('flattered_desc', '')}")
        if hidden:
            lines.append(f"  [+] HIDDEN POSITIVE: {a.get('hidden_desc', '')}")
        if flags:
            lines.append(f"  Flags: {', '.join(flags)}")
        if a.get("around_horse_form"):
            lines.append(f"  {a['around_horse_form']}")

        lines.append("")

    lines.append(sep)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Run form strength analysis. Returns exit code."""
    log("form_strength_analyser.py started")

    date_str: str = today_str()
    now = datetime.now(timezone.utc)
    generated_hm = now.strftime("%H:%M")
    log(f"form_strength_analyser: date={date_str}")

    # ------------------------------------------------------------------
    # 1. Load nap_candidates (required)
    # ------------------------------------------------------------------
    candidates_path = data_path(f"nap_candidates_{date_str}.json")
    candidates_doc: Optional[dict] = safe_load_json(candidates_path)
    if candidates_doc is None:
        log(
            f"form_strength_analyser: nap_candidates not found at {candidates_path}. "
            "Ensure nap_selector_v3.py has run.",
            "ERROR",
        )
        return 1

    # ------------------------------------------------------------------
    # 2. Load full_form (optional)
    # ------------------------------------------------------------------
    full_form_path = data_path(f"full_form_{date_str}.json")
    full_form: Optional[dict] = safe_load_json(full_form_path)
    if full_form is None:
        log("form_strength_analyser: full_form not available — using form-string fallback", "INFO")

    # ------------------------------------------------------------------
    # 3. Flatten candidates
    # ------------------------------------------------------------------
    all_candidates: list[dict] = []

    nap = candidates_doc.get("nap")
    if nap:
        c = dict(nap)
        c["candidate_type"] = "nap"
        all_candidates.append(c)

    jump_nap = candidates_doc.get("jump_nap")
    if jump_nap:
        c = dict(jump_nap)
        c["candidate_type"] = "jump_nap"
        all_candidates.append(c)

    best = candidates_doc.get("best_of_card")
    if best:
        c = dict(best)
        c["candidate_type"] = "value_ew"
        all_candidates.append(c)

    for h in (candidates_doc.get("watchlist") or []):
        c = dict(h)
        c["candidate_type"] = "watchlist"
        all_candidates.append(c)

    for h in (candidates_doc.get("shadow") or []):
        c = dict(h)
        c["candidate_type"] = "shadow"
        all_candidates.append(c)

    log(f"form_strength_analyser: assessing {len(all_candidates)} candidate(s)")

    # ------------------------------------------------------------------
    # 4. Assess each candidate
    # ------------------------------------------------------------------
    # Build a lightweight race context map from candidates_doc structure.
    # The candidates themselves carry course/off_time etc., and the going/
    # distance may be available in a racecard or shortlist file if present.
    racecard_doc: Optional[dict] = safe_load_json(data_path(f"racecards_{date_str}.json"))
    race_context_map: dict[str, dict] = {}
    if racecard_doc:
        for race in (racecard_doc.get("racecards") or []):
            rid = str(race.get("race_id") or "")
            if rid:
                race_context_map[rid] = race

    assessments: list[dict] = []
    for candidate in all_candidates:
        rid = str(candidate.get("race_id") or "")
        race_context = race_context_map.get(rid)
        assessment = _assess_candidate(candidate, full_form, race_context)
        assessments.append(assessment)

    # ------------------------------------------------------------------
    # 5. Save JSON
    # ------------------------------------------------------------------
    output: dict = {
        "date":         date_str,
        "generated_at": now.isoformat(),
        "assessments":  assessments,
        "total":        len(assessments),
    }

    json_dest = data_path(f"form_strength_{date_str}.json")
    if not safe_write_json(json_dest, output):
        log(f"form_strength_analyser: failed to write JSON — {json_dest}", "ERROR")
        return 1
    log(f"form_strength_analyser: JSON saved → {json_dest}")

    # ------------------------------------------------------------------
    # 6. Save text report
    # ------------------------------------------------------------------
    report_text = _format_text_report(date_str, generated_hm, assessments)
    report_dest = report_path(f"form_strength_{date_str}.txt")
    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
        log(f"form_strength_analyser: text report saved → {report_dest}")
    except OSError as exc:
        log(f"form_strength_analyser: failed to write text report — {exc}", "ERROR")
        return 1

    flagged_count = sum(1 for a in assessments if a.get("flags"))
    print(
        f"form_strength_analyser: COMPLETE — "
        f"{len(assessments)} assessed, {flagged_count} with flags"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
