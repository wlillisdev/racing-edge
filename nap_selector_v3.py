"""
nap_selector_v3.py — Core NAP selection engine (model v4).

Scoring (100 pts total):
  Form Quality      0–40
  Suitability       0–25
  Race Context      0–15  (incl. draw bias for Chester/Catterick/Lingfield/Windsor sprints)
  Trainer Intent    0–15  (incl. NLP keyword scoring on stable commentary)
  Market Overlay  –10/+5

NAP grade gate: score 62–78 AND no fatal flags.
  Sweet spot 62-78 after class scoring overhaul (distribution shifted down ~5-8pts).
  Class 3/5 golden zone (ROI +195-213% in backtest).
Fatal flags: dangerous_drift only.
NO BET is a valid correct outcome.

Outputs:
  data/nap_candidates_YYYY-MM-DD.json
  reports/nap_candidates_YYYY-MM-DD.txt

Exit codes:
  0 — success (including NO_BET / BLOCKED)
  1 — unrecoverable write error
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Optional

from src.helpers import (
    data_path, log, report_path, safe_load_json, safe_write_json,
    today_str, format_odds, going_normalise, distance_to_furlongs,
)
from racecard_loader import load_racecard

MODEL_VERSION: str = "v4"

GRADE_A_THRESHOLD: float = 70.0
GRADE_B_PLUS_THRESHOLD: float = 60.0
GRADE_B_THRESHOLD: float = 50.0
GRADE_C_THRESHOLD: float = 40.0

NAP_MIN_SCORE: float = 62.0   # class scoring overhaul shifted distribution down ~5-8pts; 60-69 = 50% WR
NAP_MAX_SCORE: float = 78.0   # cap keeps us in the sweet spot (scores >78 likely over-inflated)
CLUSTER_SPREAD: float = 8.0
CLUSTER_MIN_SCORE: float = 55.0

NAP_EXCLUDED_RACE_TYPES: frozenset[str] = frozenset({"chase"})
NAP_MIN_ODDS: float = 1.5
JUMP_ALTERNATIVE_MIN_SCORE: float = 55.0
JUMP_MAX_RUNNERS: int = 12
JUMP_EXCLUDED_GOING: frozenset[str] = frozenset({"Firm", "Good to Firm"})
FLAT_MAX_DIST_F: float = 14.0   # exclude flat stayers (14f+) — -21% ROI in backtest
FLAT_EXCLUDED_GOING: frozenset[str] = frozenset({"Good", "Good to Firm", "Firm", "Good to Soft", "Soft"})

_GOING_ADJACENCY: list[list[str]] = [
    ["Firm", "Good to Firm", "Good", "Good to Soft", "Soft", "Heavy"],
    ["Standard", "Slow"],
]

# Draw bias: (direction, threshold_fraction_of_field)
# "low" = low stall numbers favoured; "high" = high stall numbers favoured
_DRAW_BIAS: dict[str, tuple[str, float]] = {
    "chester": ("low", 0.30),    # very tight turns, inner rail dominates
    "catterick": ("low", 0.35),  # right-hand, low draw slight edge in sprints
    "lingfield": ("low", 0.30),  # AW inner rail advantage
    "windsor": ("high", 0.35),   # figure-8, far-side rail advantage in sprints
}

_STRONG_POSITIVE_NLP: frozenset[str] = frozenset({
    "improves", "improve", "big run", "progressive", "exciting",
    "should win", "will win", "could be anything", "ready to win",
    "well ahead", "well handicapped", "ease to win",
})
_NEGATIVE_NLP: frozenset[str] = frozenset({
    "disappointing", "struggling", "poor run", "below par", "tailed off", "well beaten",
})


def _parse_form_chars(form: str) -> list[str]:
    if not form or form.strip() in ("-", ""):
        return []
    form = form.strip().replace(" ", "")
    last_dash = form.rfind("-")
    segment = form[last_dash + 1:] if last_dash != -1 else form
    valid: list[str] = []
    for ch in reversed(segment):
        upper = ch.upper()
        if upper.isdigit() or upper in ("F", "U", "P", "R", "B"):
            valid.append(upper)
    return valid


def _going_adjacent(going_a: str, going_b: str) -> bool:
    a = going_normalise(going_a)
    b = going_normalise(going_b)
    for ladder in _GOING_ADJACENCY:
        if a in ladder and b in ladder:
            return abs(ladder.index(a) - ladder.index(b)) == 1
    return False


def _best_morning_price(runner: dict) -> Optional[float]:
    odds_list = runner.get("odds") or []
    best: Optional[float] = None
    for entry in odds_list:
        try:
            dec = float(entry.get("decimal") or 0)
            if dec > 1.0:
                if best is None or dec < best:
                    best = dec
        except (TypeError, ValueError):
            continue
    return best


def _rpr_rank_score(runner: dict, all_runners: list[dict]) -> tuple[float, list[str]]:
    try:
        my_rpr = int(str(runner.get("rpr") or "").strip())
        if my_rpr <= 0: raise ValueError
    except (ValueError, TypeError):
        return 0.0, []
    field_rprs: list[int] = []
    for r in all_runners:
        try:
            v = int(str(r.get("rpr") or "").strip())
            if v > 0: field_rprs.append(v)
        except (ValueError, TypeError):
            pass
    if not field_rprs: return 0.0, []
    field_rprs_sorted = sorted(field_rprs, reverse=True)
    n = len(field_rprs_sorted)
    top_rpr = field_rprs_sorted[0]
    second_rpr = field_rprs_sorted[1] if n >= 2 else top_rpr
    if my_rpr == top_rpr:
        gap = top_rpr - second_rpr
        if gap >= 5: return 15.0, [f"Top RPR in field ({my_rpr}), {gap} pts clear"]
        return 12.0, [f"Joint/near-top RPR ({my_rpr})"]
    top_third = n // 3 or 1
    if my_rpr in field_rprs_sorted[:top_third]:
        return 8.0, [f"Top-third RPR ({my_rpr})"]
    avg_rpr = sum(field_rprs) / n
    if my_rpr >= avg_rpr:
        return 4.0, [f"Above-average RPR ({my_rpr} vs field avg {avg_rpr:.0f})"]
    return 0.0, []


def _position_points(chars: list[str], is_jump: bool = False) -> tuple[float, list[str]]:
    _SLOT_TABLES: list[dict[str, float]] = [
        {"1": 12.0, "2": 7.0, "3": 5.0, "4": 3.0},
        {"1": 5.0, "2": 3.0, "3": 2.0, "4": 1.0},
        {"1": 3.0, "2": 2.0, "3": 1.0},
    ]
    _SLOT_LABELS = ["last time out", "2 runs ago", "3 runs ago"]
    _JUMP_PENALTIES: dict[str, list[float]] = {
        "F": [-5.0, -2.0],
        "U": [-4.0, -2.0],
        "P": [-3.0, -1.0],
    }
    # Flat PU is rare and almost always means a physical problem
    _FLAT_PENALTIES: dict[str, list[float]] = {
        "P": [-5.0, -2.0],
        "F": [-4.0, -2.0],
    }
    _PENALTY_LABELS = {"F": "Fell", "U": "Unseated", "P": "Pulled up"}
    pts = 0.0; reasons: list[str] = []
    for slot, ch in enumerate(chars[:3]):
        table = _SLOT_TABLES[slot]
        upper = ch.upper()
        if upper in ("F", "U", "P"):
            if is_jump and slot < 2 and upper in _JUMP_PENALTIES:
                pts += _JUMP_PENALTIES[upper][slot]
                reasons.append(f"⚠ {_PENALTY_LABELS[upper]} {_SLOT_LABELS[slot]}")
            elif not is_jump and slot < 2 and upper in _FLAT_PENALTIES:
                pts += _FLAT_PENALTIES[upper][slot]
                reasons.append(f"⚠ {_PENALTY_LABELS[upper]} {_SLOT_LABELS[slot]} (flat)")
            continue
        if upper in ("R", "B"):
            continue
        try: pos = int(upper)
        except ValueError: continue
        slot_pts = table.get(str(pos), 1.0 if slot == 0 and pos >= 5 else 0.0)
        pts += slot_pts
        if slot == 0 and pos <= 4:
            label = {1: "Won", 2: "2nd", 3: "3rd", 4: "4th"}.get(pos, f"{pos}th")
            reasons.append(f"{label} {_SLOT_LABELS[slot]}")
    return pts, reasons


def _trend_pts(chars: list[str]) -> tuple[float, list[str]]:
    if len(chars) < 3: return 0.0, []
    positions: list[int] = []
    for ch in chars[:3]:
        try: positions.append(int(ch))
        except ValueError: return 0.0, []
    if positions[0] < positions[1] < positions[2]: return 3.0, ["Improving form trend"]
    if positions[0] > positions[1] > positions[2]: return -3.0, ["Declining form trend"]
    return 0.0, []


def _freshness_pts(last_run_days: Optional[int]) -> tuple[float, list[str]]:
    if last_run_days is None: return 0.0, []
    if 10 <= last_run_days <= 13: return 1.0, [f"Quick reappearance ({last_run_days} days)"]
    if 14 <= last_run_days <= 28: return 2.0, [f"Ideal break ({last_run_days} days)"]
    if last_run_days <= 45: return 0.0, []
    if last_run_days <= 70: return -2.0, [f"Stale ({last_run_days} days since last run)"]
    return -4.0, [f"Long absence ({last_run_days} days)"]


def compute_form_score(runner: dict, all_runners: list[dict]) -> tuple[float, list[str]]:
    form: str = runner.get("form") or ""
    last_run: Optional[int] = runner.get("last_run")
    race_type_raw = (runner.get("_race_type") or "").lower()
    is_jump = "chase" in race_type_raw or "hurdle" in race_type_raw
    reasons: list[str] = []
    rpr_pts, rpr_reasons = _rpr_rank_score(runner, all_runners)
    reasons += rpr_reasons
    if not form or form.strip() in ("-", ""):
        reasons.append("No form data (debutant or missing)")
        return round(max(0.0, min(40.0, rpr_pts)), 2), reasons
    chars = _parse_form_chars(form)
    if not chars:
        return round(max(0.0, min(40.0, rpr_pts)), 2), reasons
    pos_pts, pos_reasons = _position_points(chars, is_jump=is_jump)
    trend_pts, trend_reasons = _trend_pts(chars)
    fresh_pts, fresh_reasons = _freshness_pts(last_run)
    reasons += pos_reasons + trend_reasons + fresh_reasons
    score = rpr_pts + pos_pts + trend_pts + fresh_pts
    return round(max(0.0, min(40.0, score)), 2), reasons


def compute_suitability_score(
    runner: dict, race: dict, full_form: Optional[dict],
) -> tuple[float, list[str]]:
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

    horse_history: Optional[list[dict]] = None
    if full_form and isinstance(full_form, dict):
        horses_lookup = full_form.get("horses") or {}
        if horse_id in horses_lookup:
            horse_history = horses_lookup[horse_id]
        elif horse_id in full_form:
            horse_history = full_form[horse_id]

    if horse_history:
        dist_win = dist_placed = False
        going_win = going_placed = going_similar = False
        course_win = course_placed = False
        for result in horse_history:
            pos = str(result.get("position") or result.get("finish_position") or "")
            win = pos == "1"
            placed = pos in ("1", "2", "3")
            r_dist_raw = str(result.get("distance_f") or result.get("distance") or "")
            try: r_dist_f = float(r_dist_raw)
            except (ValueError, TypeError): r_dist_f = distance_to_furlongs(r_dist_raw)
            r_going = going_normalise(result.get("going") or "")
            r_course = (result.get("course") or "").strip().lower()
            if today_dist_f > 0 and r_dist_f > 0 and abs(today_dist_f - r_dist_f) <= 0.5:
                if win: dist_win = True
                if placed: dist_placed = True
            if today_going and r_going:
                if today_going == r_going:
                    if win: going_win = True
                    elif placed: going_placed = True
                elif _going_adjacent(today_going, r_going) and win:
                    going_similar = True
            if today_course and r_course and today_course == r_course:
                if win: course_win = True
                elif placed: course_placed = True
        if dist_win: score += 10.0; reasons.append("Distance proven — won at today's trip")
        elif dist_placed: score += 6.0; reasons.append("Distance placed at today's trip")
        if going_win: score += 8.0; reasons.append("Going proven — won on today's ground")
        elif going_placed: score += 5.0; reasons.append("Going suited — placed on today's ground")
        elif going_similar: score += 2.0; reasons.append("Going similar to previous win ground")
        if course_win: score += 5.0; reasons.append("Course winner")
        elif course_placed: score += 3.0; reasons.append("Course placed — proven here")
    else:
        form: str = runner.get("form") or ""
        chars = _parse_form_chars(form)
        wins = chars.count("1")
        places = sum(1 for c in chars if c in ("1", "2", "3"))
        if wins >= 1: score += 6.0; reasons.append("Has won — trip/ground compatibility assumed")
        if places >= 2: score += 4.0; reasons.append("Consistent placed form")

    return round(max(0.0, min(25.0, score)), 2), reasons


def compute_draw_score(runner: dict, race: dict) -> tuple[float, list[str]]:
    race_type = str(race.get("type") or "").lower()
    if any(x in race_type for x in ("chase", "hurdle", "bumper")):
        return 0.0, []
    try: dist_f = float(str(runner.get("distance_f") or race.get("distance_f") or "0"))
    except (TypeError, ValueError): dist_f = 0.0
    if dist_f <= 0 or dist_f > 7.5:
        return 0.0, []
    course = (race.get("course") or "").lower().strip()
    bias = _DRAW_BIAS.get(course)
    if not bias:
        return 0.0, []
    try: draw = int(str(runner.get("draw") or "0"))
    except (TypeError, ValueError): draw = 0
    if draw <= 0:
        return 0.0, []
    try: field_size = int(race.get("field_size") or len(race.get("runners") or []))
    except (TypeError, ValueError): field_size = 0
    if field_size < 4:
        return 0.0, []
    direction, frac = bias
    threshold = max(1, round(field_size * frac))
    score = 0.0; reasons: list[str] = []
    if direction == "low":
        if draw <= threshold:
            score += 3.0; reasons.append(f"Favourable draw (stall {draw} at {course.title()} sprint)")
        elif draw >= field_size - threshold + 1:
            score -= 2.0; reasons.append(f"Wide draw disadvantage (stall {draw} at {course.title()})")
    else:
        if draw >= field_size - threshold + 1:
            score += 3.0; reasons.append(f"Favourable draw (stall {draw} at {course.title()} sprint)")
        elif draw <= threshold:
            score -= 2.0; reasons.append(f"Inside draw disadvantage (stall {draw} at {course.title()})")
    return score, reasons


def compute_context_score(race: dict, all_runners: list[dict]) -> tuple[float, list[str]]:
    reasons: list[str] = []; score = 0.0
    try: field_size = int(race.get("field_size") or len(all_runners))
    except (TypeError, ValueError): field_size = 0
    if field_size > 0:
        if field_size <= 6: score += 8.0; reasons.append(f"Small field ({field_size} runners)")
        elif field_size <= 9: score += 5.0; reasons.append(f"Medium-small field ({field_size} runners)")
        elif field_size <= 13: score += 3.0; reasons.append(f"Medium field ({field_size} runners)")
        else: reasons.append(f"Large field ({field_size} runners)")
    _cls_raw = str(race.get("class") or race.get("race_class") or "").strip().lower()
    if _cls_raw.startswith("class"):
        _cls_raw = _cls_raw[5:].strip()
    try: race_class = int(_cls_raw)
    except (TypeError, ValueError): race_class = None
    if race_class is not None:
        # Class 3/5 = ROI +195-213% in backtest. Class 1-2-4 = negative ROI (too competitive/noisy).
        if race_class <= 2: score += 0.0; reasons.append(f"Class {race_class} — top level, competitive field")
        elif race_class == 3: score += 5.0; reasons.append(f"Class {race_class} — sweet spot, form reliable")
        elif race_class == 4: score -= 1.0; reasons.append(f"Class {race_class} — negative ROI zone")
        elif race_class == 5: score += 3.0; reasons.append(f"Class {race_class} — predictable pattern zone")
        else: score -= 3.0; reasons.append(f"Class {race_class} — low grade, noisy form")
    elif "grade 1" in _cls_raw or _cls_raw == "g1":
        score += 3.0; reasons.append("Grade 1 — top NH, competitive (use form lines carefully)")
    elif "grade 2" in _cls_raw or _cls_raw == "g2":
        score += 4.0; reasons.append("Grade 2 — high NH quality")
    elif "grade 3" in _cls_raw or _cls_raw == "g3":
        score += 2.0; reasons.append("Grade 3 — good NH quality")
    elif "listed" in _cls_raw:
        score += 1.0; reasons.append("Listed race — decent quality")
    else:
        reasons.append("Race class unknown")
    going_norm = going_normalise(race.get("going") or "")
    race_type_raw = str(race.get("type") or "").lower()
    is_jump_race = "chase" in race_type_raw or "hurdle" in race_type_raw
    if is_jump_race:
        if going_norm in JUMP_EXCLUDED_GOING:
            score -= 5.0; reasons.append(f"Firm/Good-Firm in jump race — unsuitable ground")
        elif going_norm == "Good":
            score -= 2.0; reasons.append("Good going for jump race — historically below par")
        if field_size > JUMP_MAX_RUNNERS:
            score -= 4.0; reasons.append(f"Crowded jump field ({field_size} runners) — chaotic")
    return round(max(0.0, min(15.0, score)), 2), reasons


def compute_trainer_score(runner: dict) -> tuple[float, list[str]]:
    reasons: list[str] = []; score = 0.0
    t14 = runner.get("trainer_14_days") or {}
    try: pct = float(str(t14.get("percent") or "").strip().rstrip("%"))
    except (ValueError, TypeError): pct = None
    last_run: Optional[int] = runner.get("last_run")
    quick_return = last_run is not None and last_run < 7
    if pct is not None:
        wins = t14.get("wins", "?"); runs = t14.get("runs", "?")
        if quick_return: reasons.append(f"Hot trainer ({pct:.0f}%) but quick return — edge cancelled")
        elif pct >= 35: score += 8.0; reasons.append(f"Hot trainer — {wins}/{runs} ({pct:.0f}%)")
        elif pct >= 25: score += 5.0; reasons.append(f"In-form trainer — {wins}/{runs} ({pct:.0f}%)")
        elif pct >= 12: score += 2.0; reasons.append(f"Trainer ticking over ({pct:.0f}%)")
        else: reasons.append(f"Cold trainer ({pct:.0f}%)")
    headgear_run = str(runner.get("headgear_run") or "").strip()
    headgear = (runner.get("headgear") or "").strip()
    if headgear_run == "1" and headgear:
        score -= 2.0; reasons.append(f"First-time {headgear} — negative signal (-2pts)")
    wind_run = str(runner.get("wind_surgery_run") or "").strip()
    if wind_run == "1": score += 2.0; reasons.append("First run after wind surgery")
    _commentary = (
        (runner.get("stable_tour") or "") + " " + (runner.get("quotes") or "")
    ).lower().strip()
    if _commentary:
        if any(kw in _commentary for kw in _STRONG_POSITIVE_NLP):
            score += 3.0; reasons.append("Strong positive commentary — win signal")
        elif any(kw in _commentary for kw in _NEGATIVE_NLP):
            score -= 1.0; reasons.append("Negative commentary — caution")
        else:
            score += 2.0; reasons.append("Stable/trainer commentary present")
    if runner.get("prev_trainers") or []:
        reasons.append("Recent trainer change — monitor")
    return round(max(0.0, min(15.0, score)), 2), reasons


def compute_market_score(
    runner: dict, market_movers: Optional[dict],
) -> tuple[float, list[str], list[str]]:
    reasons: list[str] = []; fatal_flags: list[str] = []; score = 0.0
    horse_id = str(runner.get("horse_id") or "")
    morning_price = _best_morning_price(runner)
    race_type = str(runner.get("_race_type") or "").lower()
    if morning_price is not None and "hurdle" in race_type and 2.0 <= morning_price <= 3.0:
        reasons.append(f"CAUTION: hurdle Evens–2/1 band — proven loss zone")
    if morning_price is not None:
        if morning_price < 2.0:
            score += 1.0; reasons.append(f"Very short price ({format_odds(morning_price)}) — value risk")
        elif morning_price < 3.0:
            score += 4.0; reasons.append(f"Short price ({format_odds(morning_price)})")
        elif morning_price <= 6.0:
            score += 4.0; reasons.append(f"Value price ({format_odds(morning_price)})")
        elif morning_price <= 12.0:
            score += 2.0; reasons.append(f"Each-way territory ({format_odds(morning_price)})")
        elif morning_price <= 20.0:
            score -= 2.0; reasons.append(f"Bigger price ({format_odds(morning_price)})")
        else:
            score -= 6.0; reasons.append(f"Outsider ({format_odds(morning_price)})")
    if market_movers and isinstance(market_movers, dict):
        for mover in (market_movers.get("movements") or []):
            if str(mover.get("horse_id") or "") != horse_id: continue
            movement = (mover.get("move_type") or "").lower().strip()
            if movement == "strong_steamer": score += 5.0; reasons.append("Strong steamer")
            elif movement == "steamer": score += 3.0; reasons.append("Market steamer")
            elif movement == "weak_drift": score -= 3.0; reasons.append("Market drifting")
            elif movement == "dangerous_drift":
                score -= 10.0; fatal_flags.append("dangerous_drift")
                reasons.append("DANGEROUS DRIFT — NAP blocked")
            break
    return round(max(-10.0, min(5.0, score)), 2), reasons, fatal_flags


def assign_grade(total_score: float) -> str:
    if total_score >= GRADE_A_THRESHOLD: return "A"
    if total_score >= GRADE_B_PLUS_THRESHOLD: return "B+"
    if total_score >= GRADE_B_THRESHOLD: return "B"
    if total_score >= GRADE_C_THRESHOLD: return "C"
    return "D"


def score_runner(
    runner: dict, race: dict, all_runners: list[dict],
    full_form: Optional[dict], market_movers: Optional[dict],
) -> dict:
    runner = dict(runner)
    runner["_race_type"] = str(race.get("type") or "")
    form_score, form_reasons = compute_form_score(runner, all_runners)
    suit_score, suit_reasons = compute_suitability_score(runner, race, full_form)
    ctx_score, ctx_reasons   = compute_context_score(race, all_runners)
    draw_score, draw_reasons = compute_draw_score(runner, race)
    trnr_score, trnr_reasons = compute_trainer_score(runner)
    mkt_score, mkt_reasons, fatal_flags = compute_market_score(runner, market_movers)
    total = max(0.0, min(100.0, form_score + suit_score + ctx_score + draw_score + trnr_score + mkt_score))
    grade = assign_grade(total)
    morning_price = _best_morning_price(runner)
    return {
        "horse_id": str(runner.get("horse_id") or ""),
        "horse": str(runner.get("horse") or ""),
        "race_id": str(race.get("race_id") or ""),
        "course": str(race.get("course") or ""),
        "off_time": str(race.get("off_time") or ""),
        "score": round(total, 2), "grade": grade,
        "form_score": form_score, "suitability_score": suit_score,
        "context_score": ctx_score, "trainer_score": trnr_score, "market_score": mkt_score,
        "reasons": form_reasons + suit_reasons + ctx_reasons + draw_reasons + trnr_reasons + mkt_reasons,
        "warnings": list(fatal_flags),
        "morning_price": morning_price,
        "form": runner.get("form") or "",
        "trainer": str(runner.get("trainer") or ""),
        "jockey": str(runner.get("jockey") or ""),
        "rpr": runner.get("rpr"), "ofr": runner.get("ofr"), "status": None,
        "race_type": str(race.get("type") or ""),
        "going": str(race.get("going") or ""),
        "distance_f": float(race.get("distance_f") or 0.0),
    }


def detect_race_cluster(scored_runners: list[dict]) -> bool:
    if len(scored_runners) < 2: return False
    top = scored_runners[0]["score"]; second = scored_runners[1]["score"]
    return (top - second) <= CLUSTER_SPREAD and top >= CLUSTER_MIN_SCORE and second >= CLUSTER_MIN_SCORE


def _format_text_report(date_str: str, generated_hm: str, result: dict) -> str:
    nap = result.get("nap"); best = result.get("best_of_card")
    watchlist = result.get("watchlist") or []; shadow = result.get("shadow") or []
    cluster_races = result.get("cluster_races") or []; day_verdict = result.get("day_verdict") or "UNKNOWN"
    sep = "═" * 60
    lines: list[str] = [sep, "  NAP CANDIDATES — INTELLIGENCE REPORT",
                        f"  Date: {date_str}", f"  Generated: {generated_hm}  |  Model: {MODEL_VERSION}", sep, ""]
    lines.append("■ OFFICIAL NAP CANDIDATE")
    if nap:
        price = nap.get("morning_price")
        price_s = f"{format_odds(price)} ({price:.1f})" if price else "Not priced yet"
        lines += [
            f"  {nap['horse'].upper()} — {nap['course']}, {nap['off_time']}",
            f"  Grade: {nap['grade']}  |  Score: {nap['score']:.1f}/100",
            f"  Form: {nap.get('form','N/A')}  |  RPR: {nap.get('rpr','N/A')}  |  OR: {nap.get('ofr','N/A')}",
            f"  Morning price: {price_s}",
            f"  Scores: Form={nap['form_score']} Suit={nap['suitability_score']} Context={nap['context_score']} Trainer={nap['trainer_score']} Market={nap['market_score']}",
            "  Intelligence:",
        ]
        for r in nap["reasons"]: lines.append(f"    • {r}")
        lines.append(f"  Warnings: {', '.join(nap['warnings']) if nap['warnings'] else 'None'}")
    else:
        lines.append("  No NAP selected — see day verdict below.")
    lines.append("")
    lines.append("■ BEST OF CARD")
    if best:
        price = best.get("morning_price")
        price_s = format_odds(price) if price else "—"
        lines += [f"  {best['horse'].upper()} — {best['course']}, {best['off_time']}",
                  f"  Grade: {best['grade']}  |  Score: {best['score']:.1f}/100  |  Price: {price_s}"]
    else:
        lines.append("  None identified.")
    lines.append("")
    lines.append("■ JUMP ALTERNATIVE (best chase/hurdle — secondary option)")
    jump_nap = result.get("jump_nap")
    if jump_nap:
        price = jump_nap.get("morning_price")
        price_s = f"{format_odds(price)} ({price:.1f})" if price else "Not priced yet"
        lines += [
            f"  {jump_nap['horse'].upper()} — {jump_nap['course']}, {jump_nap['off_time']}",
            f"  Grade: {jump_nap['grade']}  |  Score: {jump_nap['score']:.1f}/100  |  Type: {jump_nap.get('race_type', '?')}",
            f"  Morning price: {price_s}",
            f"  Scores: Form={jump_nap['form_score']} Suit={jump_nap['suitability_score']} Context={jump_nap['context_score']} Trainer={jump_nap['trainer_score']} Market={jump_nap['market_score']}",
        ]
        for r in jump_nap["reasons"][:4]:
            lines.append(f"    • {r}")
    else:
        lines.append("  None qualifying today (no chase/hurdle scored 55+).")
    lines.append("")
    lines.append("■ WATCHLIST")
    if watchlist:
        for h in watchlist:
            price = h.get("morning_price")
            price_s = format_odds(price) if price else "—"
            lines.append(f"  - {h['horse']} | {h['course']} {h['off_time']} | Score: {h['score']:.1f} ({h['grade']}) | {price_s}")
    else:
        lines.append("  Empty.")
    lines.append("")
    lines.append("■ SHADOW LIST")
    if shadow:
        for h in shadow:
            lines.append(f"  - {h['horse']} | {h['course']} {h['off_time']} | Score: {h['score']:.1f} ({h['grade']})")
    else:
        lines.append("  Empty.")
    lines.append("")
    lines.append(f"■ DAY VERDICT: {day_verdict}")
    lines.append("")
    lines.append(sep)
    return "\n".join(lines)


def main() -> int:
    log("nap_selector_v3.py started (model v4)")
    date_str = today_str()
    now = datetime.now(timezone.utc)
    generated_at_iso = now.isoformat()
    generated_hm = now.strftime("%H:%M")

    racecard = load_racecard(date_str)
    if racecard is None:
        log("nap_selector_v3: racecard unavailable — producing BLOCKED output", "ERROR")
        blocked: dict = {
            "date": date_str, "generated_at": generated_at_iso, "model_version": MODEL_VERSION,
            "nap": None, "best_of_card": None, "watchlist": [], "shadow": [],
            "cluster_races": [], "no_bet_races": [], "day_verdict": "BLOCKED",
            "block_reason": "Racecard data unavailable",
        }
        safe_write_json(data_path(f"nap_candidates_{date_str}.json"), blocked)
        print(f"nap_selector_v3: BLOCKED — racecard unavailable for {date_str}")
        return 0

    racecards: list[dict] = racecard.get("racecards") or []
    log(f"nap_selector_v3: loaded {len(racecards)} races")

    full_form: Optional[dict] = safe_load_json(data_path(f"full_form_{date_str}.json"))
    if full_form is None:
        log("nap_selector_v3: full_form not available — suitability uses fallback", "INFO")

    market_movers: Optional[dict] = safe_load_json(data_path(f"market_movers_{date_str}.json"))
    if market_movers is None:
        log("nap_selector_v3: market_movers not available — morning price only", "INFO")

    race_scores: dict[str, list[dict]] = {}
    for race in racecards:
        race_id = str(race.get("race_id") or "")
        runners: list[dict] = race.get("runners") or []
        if not runners: continue
        scored = [score_runner(r, race, runners, full_form, market_movers) for r in runners]
        scored.sort(key=lambda r: r["score"], reverse=True)
        race_scores[race_id] = scored

    total_runners = sum(len(v) for v in race_scores.values())
    log(f"nap_selector_v3: scored {total_runners} runners across {len(race_scores)} races")

    cluster_races: list[str] = []
    for race_id, scored in race_scores.items():
        if detect_race_cluster(scored):
            cluster_races.append(race_id)

    nap_candidates: list[dict] = []
    no_bet_races: list[str] = []
    for race_id, scored in race_scores.items():
        if not scored: continue
        top = scored[0]
        # Exclude configured race types (e.g. chase — poor ROI historically)
        if any(x in (top.get("race_type") or "").lower() for x in NAP_EXCLUDED_RACE_TYPES):
            no_bet_races.append(race_id); continue
        # Minimum odds gate — no value at very short prices
        if top.get("morning_price") is not None and top["morning_price"] < NAP_MIN_ODDS:
            no_bet_races.append(race_id); continue
        # Flat distance filter — stayers (14f+) consistently lose in backtest
        _is_flat = not any(x in (top.get("race_type") or "").lower() for x in ("chase", "hurdle", "bumper"))
        if _is_flat and (top.get("distance_f") or 0.0) >= FLAT_MAX_DIST_F:
            no_bet_races.append(race_id); continue
        # Flat going filter — turf ground with poor ROI (-30% to -100% in backtest)
        if _is_flat and going_normalise(top.get("going") or "") in FLAT_EXCLUDED_GOING:
            no_bet_races.append(race_id); continue
        if race_id in cluster_races: no_bet_races.append(race_id); continue
        if top["score"] < NAP_MIN_SCORE: no_bet_races.append(race_id); continue
        if top["score"] > NAP_MAX_SCORE: no_bet_races.append(race_id); continue  # 83-85 band = 0% WR
        if "dangerous_drift" in (top.get("warnings") or []):
            no_bet_races.append(race_id); continue
        nap_candidates.append(top)

    nap_candidates.sort(key=lambda r: r["score"], reverse=True)

    nap: Optional[dict] = None
    day_verdict: str
    if nap_candidates:
        best_candidate = nap_candidates[0]
        best_candidate["status"] = "NAP"
        nap = best_candidate
        day_verdict = "NAP_SELECTED"
        if len(nap_candidates) >= 2:
            second = nap_candidates[1]
            if (best_candidate["score"] - second["score"]) <= best_candidate["score"] * 0.10:
                nap["warnings"] = list(nap.get("warnings") or [])
                if "field_cluster_warning" not in nap["warnings"]:
                    nap["warnings"].append("field_cluster_warning")
    elif cluster_races:
        day_verdict = "NO_BET_CLUSTERED"
    else:
        day_verdict = "NO_BET_NO_STANDOUT"

    nap_horse_id = nap["horse_id"] if nap else None
    seen_ids: dict[str, dict] = {}
    for scored_list in race_scores.values():
        for r in scored_list:
            if r["horse_id"] == nap_horse_id: continue
            hid = r["horse_id"]
            if hid not in seen_ids or r["score"] > seen_ids[hid]["score"]:
                seen_ids[hid] = r

    non_nap = sorted(seen_ids.values(), key=lambda r: r["score"], reverse=True)
    best_of_card: Optional[dict] = None
    watchlist: list[dict] = []
    shadow: list[dict] = []
    for r in non_nap:
        grade = r["grade"]
        if best_of_card is None and grade in ("A", "B+"): r["status"] = "BEST_OF_CARD"; best_of_card = r
        elif grade == "B": r["status"] = "WATCHLIST"; watchlist.append(r)
        elif grade == "C": r["status"] = "SHADOW"; shadow.append(r)

    # Jump alternative: best excluded-type pick (chase/hurdle) as secondary option.
    # Shown in reports for days when punter wants a jump selection.
    jump_nap: Optional[dict] = None
    for race_id, scored in race_scores.items():
        if not scored: continue
        top = scored[0]
        race_type_raw = (top.get("race_type") or "").lower()
        if not any(x in race_type_raw for x in NAP_EXCLUDED_RACE_TYPES):
            continue
        if top["score"] < JUMP_ALTERNATIVE_MIN_SCORE:
            continue
        if "dangerous_drift" in (top.get("warnings") or []):
            continue
        if jump_nap is None or top["score"] > jump_nap["score"]:
            jump_nap = dict(top)
            jump_nap["status"] = "JUMP_ALTERNATIVE"

    output: dict = {
        "date": date_str, "generated_at": generated_at_iso, "model_version": MODEL_VERSION,
        "nap": nap, "jump_nap": jump_nap, "best_of_card": best_of_card,
        "watchlist": watchlist[:10], "shadow": shadow[:10],
        "cluster_races": cluster_races, "no_bet_races": no_bet_races, "day_verdict": day_verdict,
    }

    json_dest = data_path(f"nap_candidates_{date_str}.json")
    if not safe_write_json(json_dest, output):
        log(f"nap_selector_v3: failed to write JSON — {json_dest}", "ERROR"); return 1
    log(f"nap_selector_v3: JSON saved → {json_dest}")

    report_text = _format_text_report(date_str, generated_hm, output)
    report_dest = report_path(f"nap_candidates_{date_str}.txt")
    try:
        with open(report_dest, "w", encoding="utf-8") as fh: fh.write(report_text)
        log(f"nap_selector_v3: text report saved → {report_dest}")
    except OSError as exc:
        log(f"nap_selector_v3: failed to write text report — {exc}", "ERROR"); return 1

    if nap:
        price = nap.get("morning_price")
        price_s = format_odds(price) if price else "no price"
        print(f"nap_selector_v3: NAP SELECTED — {nap['horse']} ({nap['course']} {nap['off_time']}) Score={nap['score']:.1f} Grade={nap['grade']} Price={price_s}")
    else:
        print(f"nap_selector_v3: {day_verdict} — no NAP for {date_str}")
    if jump_nap:
        jp = jump_nap.get("morning_price")
        jp_s = format_odds(jp) if jp else "no price"
        print(f"nap_selector_v3: JUMP ALT — {jump_nap['horse']} ({jump_nap['course']} {jump_nap['off_time']}) Score={jump_nap['score']:.1f} Type={jump_nap.get('race_type','?')} Price={jp_s}")
    print(f"nap_selector_v3: model={MODEL_VERSION} clusters={len(cluster_races)} candidates={len(nap_candidates)} watchlist={len(watchlist)} shadow={len(shadow)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
