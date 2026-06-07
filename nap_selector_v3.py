"""
nap_selector_v3.py — Core NAP selection engine.

Scores every runner across all races using a 100-point multi-factor model,
then selects the day's NAP (best win selection) subject to strict grade gates
and cluster-detection rules.

Scoring breakdown (100 points total):
  - Form Score       (0–40)
  - Suitability      (0–30)
  - Market Overlay   (-15 to +15)
  - Race Context     (0–15)

Design principles
-----------------
  - Fail-safe: missing racecard → BLOCKED output, never silent crash.
  - NAP must be a genuine standout — never forced.
  - Grade gate: NAP requires score >= 60 AND no fatal flags.
  - Cluster detection: top-2 within 8 pts of each other AND both >= 55 → blocked.
  - Market support is overlay confirmation only, never primary reason.
  - Watchlist/shadow horses are NOT promoted to NAP automatically.

Outputs:
  data/nap_candidates_YYYY-MM-DD.json
  reports/nap_candidates_YYYY-MM-DD.txt

Exit codes:
  0 — success (even if day_verdict is NO_BET/BLOCKED — that is a valid outcome)
  1 — unrecoverable error (write failure, etc.)
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
    format_odds,
    going_normalise,
    distance_to_furlongs,
)
from racecard_loader import load_racecard

# ---------------------------------------------------------------------------
# Configuration knobs
# ---------------------------------------------------------------------------

MODEL_VERSION: str = "v3"

# Grade thresholds
GRADE_A_THRESHOLD: float = 70.0
GRADE_B_PLUS_THRESHOLD: float = 60.0
GRADE_B_THRESHOLD: float = 50.0
GRADE_C_THRESHOLD: float = 40.0

# NAP minimum — Grade A or B+
NAP_MIN_SCORE: float = 60.0

# Cluster detection: if top-2 in same race are within this many points
# AND both >= CLUSTER_MIN_SCORE, the race is marked clustered.
CLUSTER_SPREAD: float = 8.0
CLUSTER_MIN_SCORE: float = 55.0

# Going adjacency groups (for "one step away" detection).
# Each inner list is a ladder; adjacent entries are one step apart.
_GOING_ADJACENCY: list[list[str]] = [
    ["Firm", "Good to Firm", "Good", "Good to Soft", "Soft", "Heavy"],
    ["Standard", "Slow"],
]


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _parse_form_chars(form: str) -> list[str]:
    """
    Parse a form string into an ordered list of finish characters,
    most-recent-first.

    Strategy: ignore the oldest segment before the last '-' separator
    (which represents an older season's form), then read right-to-left
    for recency.

    E.g. "211-132"  → segment after last '-' is "132"
                    → reversed → ['2', '3', '1'] (most recent = '2')
    If there is no '-', use the whole string.

    Valid result characters: digits, F (fell), U (unseated), P (pulled up),
    R (refused), B (brought down).
    """
    if not form or form.strip() in ("-", ""):
        return []

    form = form.strip().replace(" ", "")

    # Keep only the most recent season's segment (after last '-')
    last_dash = form.rfind("-")
    segment = form[last_dash + 1:] if last_dash != -1 else form

    valid: list[str] = []
    for ch in reversed(segment):   # right-to-left = most recent first
        upper = ch.upper()
        if upper.isdigit() or upper in ("F", "U", "P", "R", "B"):
            valid.append(upper)

    return valid


def _position_value(char: str, slot: int) -> float:
    """
    Return raw score points for a finish character at a given recency slot.

    slot 0 (most recent):  W=15, 2=9,  3=6,  4=3,  5+=1,  F/U/P=0
    slot 1 (2nd recent):   W=10, 2=6,  3=4,  4=2,  5+=0,  F/U/P=0
    slot 2 (3rd recent):   W=8,  2=5,  3=3,  4=1,  5+=0,  F/U/P=0
    """
    tables: list[dict[str, float]] = [
        {"1": 15.0, "2": 9.0, "3": 6.0, "4": 3.0},
        {"1": 10.0, "2": 6.0, "3": 4.0, "4": 2.0},
        {"1": 8.0,  "2": 5.0, "3": 3.0, "4": 1.0},
    ]
    if slot >= len(tables):
        return 0.0

    upper = char.upper()
    if upper in ("F", "U", "P", "R", "B"):
        return 0.0

    try:
        pos = int(upper)
    except ValueError:
        return 0.0

    table = tables[slot]
    key = str(pos)
    if key in table:
        return table[key]
    # 5th or worse
    return 1.0 if slot == 0 else 0.0


def _trend_bonus(chars: list[str]) -> float:
    """
    Evaluate improvement or deterioration across the three most recent runs.

    chars[0]=most recent, chars[1]=2nd, chars[2]=3rd.
    Improving (e.g. 3→2→1 meaning lower position number): +5
    Declining (e.g. 1→2→3): -5
    Mixed or non-numeric: 0
    """
    if len(chars) < 3:
        return 0.0

    positions: list[int] = []
    for ch in chars[:3]:
        try:
            positions.append(int(ch))
        except ValueError:
            return 0.0   # fall/unseated — can't determine trend

    # positions[0] = most recent; lower number = better
    if positions[0] < positions[1] < positions[2]:
        return 5.0
    if positions[0] > positions[1] > positions[2]:
        return -5.0
    return 0.0


def _freshness_bonus(last_run_days: Optional[int]) -> float:
    """
    Points based on days since last run.
      10–28: +3  (ideal freshness window)
      29–45:  0
      46–70: -2
      >70:   -5
      None:   0  (unknown)
    """
    if last_run_days is None:
        return 0.0
    if 10 <= last_run_days <= 28:
        return 3.0
    if last_run_days <= 45:
        return 0.0
    if last_run_days <= 70:
        return -2.0
    return -5.0


def compute_form_score(runner: dict) -> tuple[float, list[str]]:
    """
    Compute form score (0–40) for a runner.

    Returns (score, reasons).
    """
    form: str = runner.get("form") or ""
    last_run_days: Optional[int] = runner.get("days_since_run")
    career_runs: Optional[int] = runner.get("runs") or runner.get("career_runs")

    reasons: list[str] = []

    if not form or form.strip() in ("-", ""):
        reasons.append("No form data")
        return 0.0, reasons

    chars = _parse_form_chars(form)
    if not chars:
        reasons.append("Empty form after parsing")
        return 0.0, reasons

    score = 0.0

    # Position points for slots 0–2
    for slot, ch in enumerate(chars[:3]):
        pts = _position_value(ch, slot)
        score += pts
        if slot == 0:
            if ch == "1":
                reasons.append("Won last time out")
            elif ch == "2":
                reasons.append("2nd last time out")
            elif ch == "3":
                reasons.append("3rd last time out")

    # Trend
    trend = _trend_bonus(chars)
    score += trend
    if trend > 0:
        reasons.append("Improving form trend")
    elif trend < 0:
        reasons.append("Declining form trend")

    # Freshness
    fresh = _freshness_bonus(last_run_days)
    score += fresh
    if last_run_days is not None:
        if fresh > 0:
            reasons.append(f"Ideal freshness ({last_run_days} days since last run)")
        elif fresh < 0:
            reasons.append(f"Stale ({last_run_days} days since last run)")

    # Career runs penalty
    if career_runs is not None and career_runs < 5:
        score -= 3.0
        reasons.append(f"Limited career runs ({career_runs}) — unexposed")

    score = max(0.0, min(40.0, score))
    return round(score, 2), reasons


# ---------------------------------------------------------------------------
# Going adjacency helper
# ---------------------------------------------------------------------------

def _going_adjacent(going_a: str, going_b: str) -> bool:
    """Return True if the two normalised going strings are one step apart."""
    a = going_normalise(going_a)
    b = going_normalise(going_b)
    for ladder in _GOING_ADJACENCY:
        if a in ladder and b in ladder:
            return abs(ladder.index(a) - ladder.index(b)) == 1
    return False


# ---------------------------------------------------------------------------
# Suitability score
# ---------------------------------------------------------------------------

def compute_suitability_score(
    runner: dict,
    race: dict,
    full_form: Optional[dict],
) -> tuple[float, list[str]]:
    """
    Compute condition suitability score (0–30).

    Uses full_form data when available; falls back to conservative
    estimates derived from the form string alone.

    Returns (score, reasons).
    """
    reasons: list[str] = []
    score = 0.0

    today_going = going_normalise(race.get("going") or "")
    today_dist_raw = str(race.get("distance_f") or race.get("distance") or "")
    today_course = (race.get("course") or "").strip().lower()
    horse_id = str(runner.get("horse_id") or "")

    try:
        today_dist_f = float(today_dist_raw)
    except (ValueError, TypeError):
        today_dist_f = distance_to_furlongs(today_dist_raw)

    # --- Full form path ---
    horse_history: Optional[list[dict]] = None
    if full_form and isinstance(full_form, dict):
        if horse_id in full_form:
            horse_history = full_form[horse_id]
        elif "results" in full_form:
            horse_history = [
                r for r in (full_form["results"] or [])
                if str(r.get("horse_id") or "") == horse_id
            ]

    if horse_history:
        dist_win = False
        dist_placed = False
        going_win = False
        going_similar = False
        course_win = False

        for result in horse_history:
            pos = str(result.get("position") or result.get("finish_position") or "")
            win = pos == "1"
            placed = pos in ("1", "2", "3")

            r_dist_raw = str(result.get("distance_f") or result.get("distance") or "")
            try:
                r_dist_f = float(r_dist_raw)
            except (ValueError, TypeError):
                r_dist_f = distance_to_furlongs(r_dist_raw)

            r_going = going_normalise(result.get("going") or "")
            r_course = (result.get("course") or "").strip().lower()

            if today_dist_f > 0 and r_dist_f > 0:
                if abs(today_dist_f - r_dist_f) <= 0.5:
                    if win:
                        dist_win = True
                    if placed:
                        dist_placed = True

            if today_going and r_going and win:
                if today_going == r_going:
                    going_win = True
                elif _going_adjacent(today_going, r_going):
                    going_similar = True

            if today_course and r_course and today_course == r_course and win:
                course_win = True

        if dist_win:
            score += 12.0
            reasons.append("Distance proven (win at today's trip)")
        elif dist_placed:
            score += 7.0
            reasons.append("Distance placed at today's trip")

        if going_win:
            score += 10.0
            reasons.append("Going proven (win on today's ground)")
        elif going_similar:
            score += 5.0
            reasons.append("Going similar to previous win ground")

        if course_win:
            score += 5.0
            reasons.append("Course winner")

    else:
        # --- Conservative fallback from form string ---
        form: str = runner.get("form") or ""
        chars = _parse_form_chars(form)
        wins = chars.count("1")
        places = sum(1 for c in chars if c in ("1", "2", "3"))

        if wins >= 1:
            score += 8.0
            reasons.append("Has won — distance/going compatibility assumed")
        if places >= 2:
            score += 5.0
            reasons.append("Consistent placed form")

    score = max(0.0, min(30.0, score))
    return round(score, 2), reasons


# ---------------------------------------------------------------------------
# Market overlay score
# ---------------------------------------------------------------------------

def compute_market_score(
    runner: dict,
    market_movers: Optional[dict],
) -> tuple[float, list[str], list[str]]:
    """
    Compute market overlay score (-15 to +15) and detect fatal flags.

    Returns (score, reasons, fatal_flags).
    fatal_flags may contain 'dangerous_drift'.
    """
    reasons: list[str] = []
    fatal_flags: list[str] = []
    score = 0.0

    horse_id = str(runner.get("horse_id") or "")

    try:
        sp = float(runner.get("sp_dec") or 0)
    except (TypeError, ValueError):
        sp = 0.0

    # SP-based baseline
    if sp > 1.0:
        if sp < 3.0:
            score += 5.0
            reasons.append(f"Short price ({format_odds(sp)}) — market support")
        elif sp <= 6.0:
            score += 3.0
            reasons.append(f"Reasonable price ({format_odds(sp)})")
        elif sp <= 10.0:
            pass  # neutral
        elif sp <= 20.0:
            score -= 3.0
            reasons.append(f"Bigger price ({format_odds(sp)}) — limited market support")
        else:
            score -= 8.0
            reasons.append(f"Outsider ({format_odds(sp)}) — weak market support")

    # Market movers overlay (takes precedence if available)
    if market_movers and isinstance(market_movers, dict):
        movers: list[dict] = market_movers.get("movers") or []
        for mover in movers:
            if str(mover.get("horse_id") or "") != horse_id:
                continue
            movement = (mover.get("movement") or "").lower().strip()
            if movement == "strong_steamer":
                score += 12.0
                reasons.append("Strong steamer — heavy late market support")
            elif movement == "steamer":
                score += 8.0
                reasons.append("Steamer — market backing confirmed")
            elif movement == "late_support":
                score += 5.0
                reasons.append("Late market support")
            elif movement == "stable":
                pass
            elif movement == "weak_drift":
                score -= 5.0
                reasons.append("Weak drift — mild market concern")
            elif movement == "dangerous_drift":
                score -= 15.0
                fatal_flags.append("dangerous_drift")
                reasons.append("DANGEROUS DRIFT — fatal flag, NAP blocked")
            break   # only one mover entry per horse expected

    score = max(-15.0, min(15.0, score))
    return round(score, 2), reasons, fatal_flags


# ---------------------------------------------------------------------------
# Race context score
# ---------------------------------------------------------------------------

def compute_context_score(race: dict) -> tuple[float, list[str]]:
    """
    Compute race context score (0–15).

    Returns (score, reasons).
    """
    reasons: list[str] = []
    score = 0.0

    raw_field = race.get("field_size") or len(race.get("runners") or [])
    try:
        field_size = int(raw_field)
    except (TypeError, ValueError):
        field_size = 0

    if field_size > 0:
        if field_size <= 6:
            score += 10.0
            reasons.append(f"Small field ({field_size} runners) — cleaner form read")
        elif field_size <= 9:
            score += 7.0
            reasons.append(f"Medium-small field ({field_size} runners)")
        elif field_size <= 13:
            score += 3.0
            reasons.append(f"Medium field ({field_size} runners)")
        else:
            reasons.append(f"Large field ({field_size} runners) — increased uncertainty")

    raw_class = race.get("class")
    try:
        race_class = int(str(raw_class).strip())
    except (TypeError, ValueError):
        race_class = None

    if race_class is not None:
        if 1 <= race_class <= 3:
            score -= 3.0
            reasons.append(f"Class {race_class} — high-quality, hard to beat market")
        elif race_class >= 5:
            score += 3.0
            reasons.append(f"Class {race_class} — lower class, more predictable form")
    else:
        score += 3.0
        reasons.append("Unknown class — conservative bonus applied")

    score = max(0.0, min(15.0, score))
    return round(score, 2), reasons


# ---------------------------------------------------------------------------
# Grade assignment
# ---------------------------------------------------------------------------

def assign_grade(total_score: float) -> str:
    """Return letter grade for a total score."""
    if total_score >= GRADE_A_THRESHOLD:
        return "A"
    if total_score >= GRADE_B_PLUS_THRESHOLD:
        return "B+"
    if total_score >= GRADE_B_THRESHOLD:
        return "B"
    if total_score >= GRADE_C_THRESHOLD:
        return "C"
    return "D"


# ---------------------------------------------------------------------------
# Full runner scoring
# ---------------------------------------------------------------------------

def score_runner(
    runner: dict,
    race: dict,
    full_form: Optional[dict],
    market_movers: Optional[dict],
) -> dict:
    """Score a single runner across all four dimensions. Returns scoring dict."""
    form_score, form_reasons   = compute_form_score(runner)
    suit_score, suit_reasons   = compute_suitability_score(runner, race, full_form)
    mkt_score, mkt_reasons, fatal_flags = compute_market_score(runner, market_movers)
    ctx_score, ctx_reasons     = compute_context_score(race)

    total = max(0.0, min(100.0, form_score + suit_score + mkt_score + ctx_score))
    grade = assign_grade(total)

    all_reasons = form_reasons + suit_reasons + mkt_reasons + ctx_reasons

    try:
        sp_float: Optional[float] = float(runner.get("sp_dec") or 0) or None
        if sp_float is not None and sp_float <= 1.0:
            sp_float = None
    except (TypeError, ValueError):
        sp_float = None

    warnings: list[str] = list(fatal_flags)
    if sp_float is None:
        warnings.append("no_valid_odds")

    return {
        "horse_id":          str(runner.get("horse_id") or ""),
        "horse":             str(runner.get("horse") or ""),
        "race_id":           str(race.get("race_id") or ""),
        "course":            str(race.get("course") or ""),
        "off_time":          str(race.get("off_time") or ""),
        "score":             round(total, 2),
        "grade":             grade,
        "form_score":        form_score,
        "suitability_score": suit_score,
        "market_score":      mkt_score,
        "context_score":     ctx_score,
        "reasons":           all_reasons,
        "warnings":          warnings,
        "sp_dec":            sp_float,
        "form":              runner.get("form") or "",
        "status":            None,   # set downstream
    }


# ---------------------------------------------------------------------------
# Cluster detection (per-race)
# ---------------------------------------------------------------------------

def detect_race_cluster(scored_runners: list[dict]) -> bool:
    """
    Return True if the top-2 scorers are within CLUSTER_SPREAD points of
    each other AND both score >= CLUSTER_MIN_SCORE.
    """
    if len(scored_runners) < 2:
        return False
    top    = scored_runners[0]["score"]
    second = scored_runners[1]["score"]
    return (
        (top - second) <= CLUSTER_SPREAD
        and top    >= CLUSTER_MIN_SCORE
        and second >= CLUSTER_MIN_SCORE
    )


# ---------------------------------------------------------------------------
# NAP report formatter
# ---------------------------------------------------------------------------

def _format_text_report(date_str: str, generated_hm: str, result: dict) -> str:
    """Build the human-readable nap_candidates report string."""
    nap            = result.get("nap")
    best           = result.get("best_of_card")
    watchlist      = result.get("watchlist") or []
    shadow         = result.get("shadow") or []
    cluster_races  = result.get("cluster_races") or []
    day_verdict    = result.get("day_verdict") or "UNKNOWN"

    sep = "═" * 56
    lines: list[str] = [
        sep,
        "  NAP CANDIDATES — SCORING REPORT",
        f"  Date: {date_str}",
        f"  Generated: {generated_hm}  |  Model: {MODEL_VERSION}",
        sep,
        "",
    ]

    lines.append("■ OFFICIAL NAP CANDIDATE")
    if nap:
        sp_display = format_odds(nap.get("sp_dec") or 0)
        lines += [
            f"  {nap['horse'].upper()} — {nap['course']}, {nap['off_time']}",
            f"  Grade: {nap['grade']}  |  Score: {nap['score']:.1f}/100",
            f"  Form: {nap.get('form', 'N/A')}",
            f"  Odds: {sp_display} ({nap.get('sp_dec', 'N/A')})",
            f"  Scores: Form={nap['form_score']}  Suit={nap['suitability_score']}"
            f"  Market={nap['market_score']}  Context={nap['context_score']}",
        ]
        lines.append("  Reasons:")
        for r in nap["reasons"]:
            lines.append(f"    • {r}")
        if nap["warnings"]:
            lines.append(f"  Warnings: {', '.join(nap['warnings'])}")
        else:
            lines.append("  Warnings: None")
    else:
        lines.append("  No NAP selected — see day verdict below.")
    lines.append("")

    lines.append("■ BEST OF CARD")
    if best:
        lines += [
            f"  {best['horse'].upper()} — {best['course']}, {best['off_time']}",
            f"  Grade: {best['grade']}  |  Score: {best['score']:.1f}/100",
            "  (Strong form but not clear enough for official NAP.)",
        ]
    else:
        lines.append("  None identified.")
    lines.append("")

    lines.append("■ WATCHLIST")
    if watchlist:
        for h in watchlist:
            lines.append(
                f"  - {h['horse']} — {h['course']} {h['off_time']}"
                f"  (Score: {h['score']:.1f}, Grade: {h['grade']})"
            )
    else:
        lines.append("  Empty.")
    lines.append("")

    lines.append("■ SHADOW (learning only — not official bets)")
    if shadow:
        for h in shadow:
            lines.append(
                f"  - {h['horse']} — {h['course']} {h['off_time']}"
                f"  (Score: {h['score']:.1f}, Grade: {h['grade']})"
            )
    else:
        lines.append("  Empty.")
    lines.append("")

    if cluster_races:
        lines.append("■ CLUSTER RACES (no clean NAP from these races)")
        for race_id in cluster_races:
            lines.append(f"  - Race ID: {race_id}")
        lines.append("")

    lines.append(f"■ DAY VERDICT: {day_verdict}")
    lines.append("")
    lines.append(sep)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Run NAP selection pipeline. Returns exit code."""
    log("nap_selector_v3.py started")

    date_str = today_str()
    now = datetime.now(timezone.utc)
    generated_at_iso = now.isoformat()
    generated_hm     = now.strftime("%H:%M")

    # ------------------------------------------------------------------
    # 1. Load racecard — fail-safe: missing → BLOCKED output
    # ------------------------------------------------------------------
    racecard = load_racecard(date_str)

    if racecard is None:
        log("nap_selector_v3: racecard unavailable — producing BLOCKED output", "ERROR")
        blocked: dict = {
            "date":          date_str,
            "generated_at":  generated_at_iso,
            "model_version": MODEL_VERSION,
            "nap":           None,
            "best_of_card":  None,
            "watchlist":     [],
            "shadow":        [],
            "cluster_races": [],
            "no_bet_races":  [],
            "day_verdict":   "BLOCKED",
            "block_reason":  "Racecard data unavailable",
        }
        safe_write_json(data_path(f"nap_candidates_{date_str}.json"), blocked)
        try:
            with open(report_path(f"nap_candidates_{date_str}.txt"), "w",
                      encoding="utf-8") as fh:
                fh.write(f"BLOCKED — racecard data unavailable for {date_str}\n")
        except OSError as exc:
            log(f"nap_selector_v3: could not write BLOCKED report — {exc}", "ERROR")
        print(f"nap_selector_v3: BLOCKED — racecard unavailable for {date_str}")
        return 0   # BLOCKED is a valid (expected) outcome, not a crash

    racecards: list[dict] = racecard.get("racecards") or []
    if not racecards:
        log("nap_selector_v3: racecard list is empty", "WARNING")

    log(f"nap_selector_v3: loaded {len(racecards)} races")

    # ------------------------------------------------------------------
    # 2. Optional: full_form data
    # ------------------------------------------------------------------
    full_form: Optional[dict] = safe_load_json(
        data_path(f"full_form_{date_str}.json")
    )
    if full_form is None:
        log("nap_selector_v3: full_form not available — using form-string fallback",
            "INFO")

    # ------------------------------------------------------------------
    # 3. Optional: market_movers data
    # ------------------------------------------------------------------
    market_movers: Optional[dict] = safe_load_json(
        data_path(f"market_movers_{date_str}.json")
    )
    if market_movers is None:
        log("nap_selector_v3: market_movers not available — SP-based overlay only",
            "INFO")

    # ------------------------------------------------------------------
    # 4. Score every runner in every race
    # ------------------------------------------------------------------
    race_scores: dict[str, list[dict]] = {}   # race_id → scored runners (sorted)

    for race in racecards:
        race_id  = str(race.get("race_id") or "")
        runners: list[dict] = race.get("runners") or []
        if not runners:
            log(f"nap_selector_v3: race {race_id} has no runners — skipping", "INFO")
            continue

        scored = [score_runner(r, race, full_form, market_movers) for r in runners]
        scored.sort(key=lambda r: r["score"], reverse=True)
        race_scores[race_id] = scored

    total_runners = sum(len(v) for v in race_scores.values())
    log(f"nap_selector_v3: scored {total_runners} runners across "
        f"{len(race_scores)} races")

    # ------------------------------------------------------------------
    # 5. Detect per-race clusters
    # ------------------------------------------------------------------
    cluster_races: list[str] = []
    for race_id, scored in race_scores.items():
        if detect_race_cluster(scored):
            cluster_races.append(race_id)
            log(f"nap_selector_v3: cluster detected in race {race_id}", "INFO")

    # ------------------------------------------------------------------
    # 6. Gather NAP candidates (top runner from each non-clustered race)
    # ------------------------------------------------------------------
    nap_candidates: list[dict] = []
    no_bet_races:   list[str]  = []

    for race_id, scored in race_scores.items():
        if not scored:
            continue
        top = scored[0]

        # Clustered race — no NAP from here
        if race_id in cluster_races:
            no_bet_races.append(race_id)
            continue

        # Score below NAP threshold
        if top["score"] < NAP_MIN_SCORE:
            no_bet_races.append(race_id)
            continue

        # Fatal flags block NAP
        fatal = any(
            w in (top.get("warnings") or [])
            for w in ("dangerous_drift", "no_valid_odds")
        )
        if fatal:
            no_bet_races.append(race_id)
            log(f"nap_selector_v3: {top['horse']} in race {race_id} has fatal "
                f"warning — excluded: {top['warnings']}", "WARNING")
            continue

        nap_candidates.append(top)

    nap_candidates.sort(key=lambda r: r["score"], reverse=True)

    # ------------------------------------------------------------------
    # 7. Select overall NAP
    # ------------------------------------------------------------------
    nap: Optional[dict] = None
    day_verdict: str

    if nap_candidates:
        best_candidate = nap_candidates[0]
        best_candidate["status"] = "NAP"
        nap = best_candidate
        day_verdict = "NAP_SELECTED"

        # Secondary field-level cluster check (top-2 within 10% of each other)
        if len(nap_candidates) >= 2:
            second = nap_candidates[1]
            ten_pct = best_candidate["score"] * 0.10
            if (best_candidate["score"] - second["score"]) <= ten_pct:
                log(
                    f"nap_selector_v3: field-level cluster warning — "
                    f"{best_candidate['horse']} ({best_candidate['score']}) vs "
                    f"{second['horse']} ({second['score']})",
                    "WARNING",
                )
                nap["warnings"] = list(nap.get("warnings") or [])
                if "field_cluster_warning" not in nap["warnings"]:
                    nap["warnings"].append("field_cluster_warning")

    elif cluster_races:
        day_verdict = "NO_BET_CLUSTERED"
    else:
        day_verdict = "NO_BET_NO_STANDOUT"

    # ------------------------------------------------------------------
    # 8. Build best_of_card, watchlist, shadow
    # ------------------------------------------------------------------
    # All scored runners except the NAP, de-duplicated by horse_id
    nap_horse_id = nap["horse_id"] if nap else None

    seen_ids: dict[str, dict] = {}
    for scored_list in race_scores.values():
        for r in scored_list:
            if r["horse_id"] == nap_horse_id:
                continue
            hid = r["horse_id"]
            if hid not in seen_ids or r["score"] > seen_ids[hid]["score"]:
                seen_ids[hid] = r

    non_nap = sorted(seen_ids.values(), key=lambda r: r["score"], reverse=True)

    best_of_card: Optional[dict] = None
    watchlist:    list[dict]      = []
    shadow:       list[dict]      = []

    for r in non_nap:
        grade = r["grade"]
        if best_of_card is None and grade in ("A", "B+"):
            r["status"] = "BEST_OF_CARD"
            best_of_card = r
        elif grade == "B":
            r["status"] = "WATCHLIST"
            watchlist.append(r)
        elif grade == "C":
            r["status"] = "SHADOW"
            shadow.append(r)
        # Grade D: omit

    # ------------------------------------------------------------------
    # 9. Build output document
    # ------------------------------------------------------------------
    output: dict = {
        "date":          date_str,
        "generated_at":  generated_at_iso,
        "model_version": MODEL_VERSION,
        "nap":           nap,
        "best_of_card":  best_of_card,
        "watchlist":     watchlist[:10],
        "shadow":        shadow[:10],
        "cluster_races": cluster_races,
        "no_bet_races":  no_bet_races,
        "day_verdict":   day_verdict,
    }

    # ------------------------------------------------------------------
    # 10. Save JSON and text report
    # ------------------------------------------------------------------
    json_dest = data_path(f"nap_candidates_{date_str}.json")
    if not safe_write_json(json_dest, output):
        log(f"nap_selector_v3: failed to write JSON — {json_dest}", "ERROR")
        return 1
    log(f"nap_selector_v3: JSON saved → {json_dest}")

    report_text = _format_text_report(date_str, generated_hm, output)
    report_dest = report_path(f"nap_candidates_{date_str}.txt")
    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
        log(f"nap_selector_v3: text report saved → {report_dest}")
    except OSError as exc:
        log(f"nap_selector_v3: failed to write text report — {exc}", "ERROR")
        return 1

    # ------------------------------------------------------------------
    # 11. Print summary
    # ------------------------------------------------------------------
    if nap:
        print(
            f"nap_selector_v3: NAP SELECTED — {nap['horse']}"
            f" ({nap['course']} {nap['off_time']})"
            f" Score={nap['score']:.1f} Grade={nap['grade']}"
        )
    else:
        print(f"nap_selector_v3: {day_verdict} — no NAP for {date_str}")

    print(
        f"nap_selector_v3: clusters={len(cluster_races)}"
        f"  candidates={len(nap_candidates)}"
        f"  watchlist={len(watchlist)}"
        f"  shadow={len(shadow)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
