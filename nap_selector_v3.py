"""
nap_selector_v3.py — Core NAP selection engine (model v4).

Scoring (100 pts total):
  Form Quality      0–40
  Suitability       0–25
  Race Context      0–15  (incl. draw bias for Chester/Catterick/Lingfield/Windsor sprints)
  Trainer Intent    0–15  (incl. NLP keyword scoring on stable commentary)
  Market Overlay  –10/+5

NAP gate: score 60–82, odds 2.0–7.0 (Evens to 6/1), no fatal flags.
  6-month backtest (178 days, 63 NAPs): 36.5% WR, +5.5% ROI, 77.8% place rate.
  Best going: AW (+23.8%), Heavy (-11.9%); excluded: Firm, Good-to-Firm.
  Sprints: +45.7% NAP ROI; Chases: -33.3% (excluded); Hurdles: -15.7%.
  8/1+ zone: -39.4% ROI (excluded by NAP_MAX_ODDS cap).
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

# Professional form-reading overlay (-15..+25). Self-contained, degrades to
# 0.0 if the module is unavailable so the core model never breaks.
try:
    from racing_wisdom import score_racing_wisdom
    _WISDOM_AVAILABLE = True
except Exception:  # pragma: no cover - defensive: never let an overlay break scoring
    _WISDOM_AVAILABLE = False

MODEL_VERSION: str = "v4"

GRADE_A_THRESHOLD: float = 70.0
GRADE_B_PLUS_THRESHOLD: float = 60.0
GRADE_B_THRESHOLD: float = 50.0
GRADE_C_THRESHOLD: float = 40.0

NAP_MIN_SCORE: float = 50.0   # floor — model must always output the best horse; confidence via label
NAP_MAX_SCORE: float = 100.0  # no upper cap — a high score is a strong signal, not a block
CLUSTER_SPREAD: float = 8.0
CLUSTER_MIN_SCORE: float = 50.0

NAP_EXCLUDED_RACE_TYPES: frozenset[str] = frozenset({"chase"})
NAP_MIN_ODDS: float = 2.0   # Evens minimum — need >50% WR to break even
NAP_MAX_ODDS: float = 7.0   # 6/1 cap — 8/1+ zone is -39.4% ROI over 524 selections (6-month backtest)
JUMP_ALTERNATIVE_MIN_SCORE: float = 55.0
JUMP_MAX_RUNNERS: int = 12
JUMP_EXCLUDED_GOING: frozenset[str] = frozenset({"Firm", "Good to Firm"})
FLAT_MAX_DIST_F: float = 16.0   # exclude flat staying trips (16f+)
FLAT_MIN_DIST_F: float = 0.0    # no sprint exclusion — 6-month backtest: sprints +45.7% NAP ROI (979 selections)
FLAT_EXCLUDED_GOING: frozenset[str] = frozenset({
    "Firm",   # concrete-hard turf — 0% WR in NAP data; no model edge on extremes
    "Heavy",  # waterlogged — high win% but odds below value threshold consistently
    # "Good to Firm" removed: only 5 NAP selections — too small to exclude an entire
    # summer going type. Monitor over next 50+ picks before re-adding.
})

_GOING_ADJACENCY: list[list[str]] = [
    ["Firm", "Good to Firm", "Good", "Good to Soft", "Soft", "Heavy"],
    ["Standard", "Slow"],
]

# Draw bias: (direction, threshold_fraction_of_field)
# "low" = low stall numbers favoured (near side/stands rail)
# "high" = high stall numbers favoured (far side/stands rail on right-to-left courses)
# Only applied for flat races ≤9f. Overridden by live stalls/rail data from pro racecard.
_DRAW_BIAS: dict[str, tuple[str, float]] = {
    # Confirmed strong biases (research-verified)
    "chester":    ("low",  0.25),  # extreme — stalls 1-2 win ~50%+ of sprint races; stall 10+ = 0 wins in studies
    "pontefract": ("low",  0.20),  # stall 1 wins 24% of 5f races; +91p/£1 long-run profit blind-backing stall 1
    "beverley":   ("low",  0.30),  # low-draw edge persists (weakened from historic levels but still significant)
    "lingfield":  ("low",  0.30),  # AW: stalls 1-2 win ~1/3 of 5f fields of 10+; one of clearest AW biases
    # Confirmed medium biases
    "haydock":    ("high", 0.35),  # stands-side (high) rail advantage in 5f-6f sprints; amplified on soft ground
    "ascot":      ("high", 0.35),  # stands-side (high) favoured straight 5f-6f in large fields
    "epsom":      ("high", 0.35),  # HIGH draw (far rail) has best camber downhill in sprints; note: 1m4f reversed
    "goodwood":   ("low",  0.30),  # far-rail (LOW draw = far side at Goodwood) advantage on straight 5f-6f
    "york":       ("low",  0.35),  # low draw clear advantage at 1m; slight low edge in 5f-6f on soft
    "catterick":  ("low",  0.35),  # right-hand, low draw slight edge in sprints
    "windsor":    ("high", 0.35),  # figure-8, far-side rail advantage in sprints
    "carlisle":   ("high", 0.35),  # high draw advantaged — stall 4 best, stall 2 worst in studies
    "hamilton":   ("high", 0.35),  # counterintuitive: HIGH draw advantage, esp on soft (impact factor 1.30 high vs 0.79 low)
    "salisbury":  ("low",  0.35),  # near-side (low) rail advantage in soft/testing ground
}

# Course ROI adjustments — 6-month forensic backtest (n >= 25 only; modest signal)
# Positive = model reads form well here; Negative = model consistently loses here
_COURSE_SCORE_ADJ: dict[str, float] = {
    # Good courses (n >= 50, ROI > +12%)
    "leopardstown": +2.0,   # n=89, +24.7% ROI
    "navan":        +2.0,   # n=61, +24.5% ROI
    "cork":         +2.0,   # n=62, +23.5% ROI
    "bath":         +2.0,   # n=70, +16.8% ROI
    "chelmsford":   +2.0,   # n=100, +15.9% ROI (AW — excluded from going filter; model reads it well)
    "hereford":     +1.0,   # n=83, +13.0% ROI
    "tramore":      +2.0,   # n=33, +26.9% ROI
    "kilbeggan":    +2.0,   # n=20, +50.5% ROI (small sample but strong)
    # Trap courses (ROI < -40%)
    "fairyhouse":   -3.0,   # n=81, -46.9% ROI — Irish track model struggles
    "newcastle":    -3.0,   # n=51, -46.4% ROI
    "yarmouth":     -3.0,   # n=46, -54.5% ROI — form often misleading here
    "chester":      -3.0,   # n=26, -47.2% ROI — extreme draw bias overrides form
}

_STRONG_POSITIVE_NLP: frozenset[str] = frozenset({
    "improves", "improve", "big run", "progressive", "exciting",
    "should win", "will win", "could be anything", "ready to win",
    "well ahead", "well handicapped", "ease to win", "unlucky",
    "unfortunate", "hampered", "denied", "failed to get a clear run",
    "bumped", "stumbled", "missed the break", "slowly away",
})
_BEATEN_FAV_NLP: frozenset[str] = frozenset({
    "beaten favourite", "odds-on", "short-priced", "strongly fancied",
    "well fancied", "evens", "favourite", "hot favourite",
})
_CLOSE_LOSER_NLP: frozenset[str] = frozenset({
    "short head", "neck", "head", "nose", "half a length",
    "just failed", "narrowly beaten", "touched off", "photo",
})
_NEGATIVE_NLP: frozenset[str] = frozenset({
    "disappointing", "struggling", "poor run", "below par", "tailed off", "well beaten",
    "never competitive", "never involved", "never dangerous",
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
                if best is None or dec > best:
                    best = dec
        except (TypeError, ValueError):
            continue
    return best


def _ts_rank_score(runner: dict, all_runners: list[dict]) -> tuple[float, list[str]]:
    """Topspeed (pace-adjusted time figure) rank within the field.
    Complementary to RPR: TS measures actual race speed, RPR measures assessor quality estimate."""
    try:
        my_ts = int(str(runner.get("ts") or "").strip())
        if my_ts <= 0: raise ValueError
    except (ValueError, TypeError):
        return 0.0, []
    field_ts: list[int] = []
    for r in all_runners:
        try:
            v = int(str(r.get("ts") or "").strip())
            if v > 0: field_ts.append(v)
        except (ValueError, TypeError):
            pass
    if len(field_ts) < 3: return 0.0, []  # need at least 3 data points
    field_ts_sorted = sorted(field_ts, reverse=True)
    n = len(field_ts_sorted)
    top_ts = field_ts_sorted[0]
    if my_ts >= top_ts:
        gap = top_ts - (field_ts_sorted[1] if n >= 2 else top_ts)
        if gap >= 5: return 5.0, [f"Top Topspeed in field (TS={my_ts}), {gap} clear"]
        return 3.0, [f"Joint-top Topspeed (TS={my_ts})"]
    top_third = max(1, n // 3)
    if my_ts in field_ts_sorted[:top_third]:
        return 2.0, [f"Top-third Topspeed (TS={my_ts})"]
    return 0.0, []


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


def _well_handicapped_pts(runner: dict, race_type_raw: str) -> tuple[float, list[str]]:
    """Well-handicapped: RPR significantly above Official Rating = lbs in hand.
    Applies in handicap races only. Classic pro punter angle — horse ahead of handicapper."""
    _is_handicap = "handicap" in race_type_raw or "hcap" in race_type_raw
    if not _is_handicap:
        return 0.0, []
    try:
        rpr_v = int(str(runner.get("rpr") or "").strip())
        ofr_v = int(str(runner.get("ofr") or "").strip())
        if rpr_v <= 0 or ofr_v <= 0:
            return 0.0, []
        gap = rpr_v - ofr_v
        if gap >= 10:
            return 5.0, [f"Strongly well handicapped: RPR {rpr_v} vs OR {ofr_v} (+{gap}lbs in hand)"]
        if gap >= 7:
            return 3.0, [f"Well handicapped: RPR {rpr_v} vs OR {ofr_v} (+{gap}lbs)"]
        if gap >= 5:
            return 1.0, [f"Slight RPR/OR edge: +{gap}lbs above OR"]
    except (ValueError, TypeError):
        pass
    return 0.0, []


def compute_form_score(runner: dict, all_runners: list[dict]) -> tuple[float, list[str]]:
    form: str = runner.get("form") or ""
    last_run: Optional[int] = runner.get("last_run")
    race_type_raw = (runner.get("_race_type") or "").lower()
    is_jump = "chase" in race_type_raw or "hurdle" in race_type_raw
    reasons: list[str] = []
    rpr_pts, rpr_reasons = _rpr_rank_score(runner, all_runners)
    ts_pts, ts_reasons   = _ts_rank_score(runner, all_runners)
    wh_pts, wh_reasons   = _well_handicapped_pts(runner, race_type_raw)
    reasons += rpr_reasons + ts_reasons + wh_reasons
    if not form or form.strip() in ("-", ""):
        reasons.append("No form data (debutant or missing)")
        return round(max(0.0, min(40.0, rpr_pts + ts_pts + wh_pts)), 2), reasons
    chars = _parse_form_chars(form)
    if not chars:
        return round(max(0.0, min(40.0, rpr_pts + ts_pts + wh_pts)), 2), reasons
    pos_pts, pos_reasons = _position_points(chars, is_jump=is_jump)
    trend_pts, trend_reasons = _trend_pts(chars)
    fresh_pts, fresh_reasons = _freshness_pts(last_run)
    reasons += pos_reasons + trend_reasons + fresh_reasons
    score = rpr_pts + ts_pts + wh_pts + pos_pts + trend_pts + fresh_pts
    return round(max(0.0, min(40.0, score)), 2), reasons


def compute_suitability_score(
    runner: dict, race: dict, full_form: Optional[dict],
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0
    # Prefer going_detailed (e.g. "Good to Firm (Good in places)") — strip parenthetical for normalisation
    _going_raw = race.get("going_detailed") or race.get("going") or ""
    _going_raw = _going_raw.split("(")[0].strip()  # "Good to Firm (Good in places)" → "Good to Firm"
    today_going = going_normalise(_going_raw)
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

        # Class drop signal: horse dropping from a consistently higher class level
        # Extract class from full_form results (if available)
        prev_classes: list[int] = []
        for result in horse_history[:5]:
            _rc = str(result.get("class") or result.get("race_class") or "").strip().lstrip("cC")
            try:
                _rc_int = int(_rc)
                prev_classes.append(_rc_int)
            except (ValueError, TypeError):
                pass
        today_class_raw = str(race.get("class") or race.get("race_class") or "").strip().lower()
        if today_class_raw.startswith("class"):
            today_class_raw = today_class_raw[5:].strip()
        try:
            today_class_int = int(today_class_raw)
            if prev_classes and len(prev_classes) >= 2:
                avg_prev_class = sum(prev_classes) / len(prev_classes)
                if today_class_int >= avg_prev_class + 2:
                    score += 4.0; reasons.append(
                        f"Class drop: previously Cls {avg_prev_class:.0f} avg, now Cls {today_class_int} — h'capper relenting"
                    )
                elif today_class_int >= avg_prev_class + 1:
                    score += 2.0; reasons.append(
                        f"Marginal class drop: Cls {avg_prev_class:.0f} → Cls {today_class_int}"
                    )
        except (ValueError, TypeError):
            pass
    else:
        form: str = runner.get("form") or ""
        chars = _parse_form_chars(form)
        wins = chars.count("1")
        places = sum(1 for c in chars if c in ("2", "3"))  # placed but not won
        if wins >= 1: score += 6.0; reasons.append("Has won — trip/ground compatibility assumed")
        elif places >= 2: score += 4.0; reasons.append("Consistent placed form")

    return round(max(0.0, min(25.0, score)), 2), reasons


def compute_draw_score(runner: dict, race: dict) -> tuple[float, list[str]]:
    race_type = str(race.get("type") or "").lower()
    if any(x in race_type for x in ("chase", "hurdle", "bumper")):
        return 0.0, []
    try: dist_f = float(str(runner.get("distance_f") or race.get("distance_f") or "0"))
    except (TypeError, ValueError): dist_f = 0.0
    if dist_f <= 0 or dist_f > 9.0:  # draw significant up to 9f on straight courses
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

    # Read rail and stall position from pro racecard — these override static bias
    rail = (race.get("rail_movements") or "").lower()
    stalls = (race.get("stalls") or "").lower()
    rail_uncertainty = any(kw in rail for kw in ("moved", "movement", "far side", "near side", "centre"))

    direction, frac = bias
    # If stalls are positioned on the opposite side to expected, reverse the bias
    if direction == "low" and any(kw in stalls for kw in ("far side", "stands side")):
        direction = "high"
        reasons_prefix = [f"Stalls: {race.get('stalls')} — draw bias reversed vs static model"]
    elif direction == "high" and any(kw in stalls for kw in ("near side", "inside")):
        direction = "low"
        reasons_prefix = [f"Stalls: {race.get('stalls')} — draw bias reversed vs static model"]
    else:
        reasons_prefix = []

    threshold = max(1, round(field_size * frac))
    score = 0.0; reasons: list[str] = list(reasons_prefix)
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

    # Rail has moved — reduce bias confidence by half
    if rail_uncertainty and score != 0.0:
        score *= 0.5
        reasons.append(f"Rail movements today — draw advantage reduced ({race.get('rail_movements')})")
    return score, reasons


def compute_context_score(race: dict, all_runners: list[dict]) -> tuple[float, list[str]]:
    reasons: list[str] = []; score = 0.0

    # --- Race type reliability flags ---
    _rtype = str(race.get("type") or "").lower()
    _rname = str(race.get("race_name") or "").lower()
    if any(x in _rtype for x in ("sell", "claim")):
        score -= 5.0; reasons.append("Selling/Claiming race — form unreliable, horses may be deteriorating")
    elif "bumper" in _rtype or "nhf" in _rtype or "national hunt flat" in _rtype:
        score -= 4.0; reasons.append("Bumper (NH Flat) — form-based model has no edge here")
    elif "maiden" in _rtype or "maiden" in _rname:
        score -= 2.0; reasons.append("Maiden race — unproven form, high variance")
    elif "novice" in _rtype or "novice" in _rname:
        score -= 2.0; reasons.append("Novice race — horses still learning, form unreliable")

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
        # Class 3/5 = ROI +195-213% in backtest. Class 1-2 = -49.7% ROI, Class 4 = -57.5% ROI.
        if race_class <= 2: score -= 2.0; reasons.append(f"Class {race_class} — top level, -49.7% ROI in backtest")
        elif race_class == 3: score += 5.0; reasons.append(f"Class {race_class} — sweet spot, form reliable")
        elif race_class == 4: score -= 3.0; reasons.append(f"Class {race_class} — negative ROI zone (-57.5%)")
        elif race_class == 5: score += 3.0; reasons.append(f"Class {race_class} — predictable pattern zone")
        elif race_class >= 6: score -= 3.0; reasons.append(f"Class {race_class} — low grade, noisy form")
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
    # Course edge/trap adjustment — 6-month backtest signal (n>=25, modest adjustment capped ±3)
    _course_key = str(race.get("course") or "").strip().lower()
    _course_adj = _COURSE_SCORE_ADJ.get(_course_key, 0.0)
    if _course_adj > 0:
        score += _course_adj; reasons.append(f"Course edge: {race.get('course','?')} (+{_course_adj:.0f}pts, model reads form well here)")
    elif _course_adj < 0:
        score += _course_adj; reasons.append(f"Course trap: {race.get('course','?')} ({_course_adj:.0f}pts, model historically loses here)")
    return round(max(0.0, min(15.0, score)), 2), reasons


def _ae_score(ae: float | None, runners: int, thresholds: tuple[float, float, float]) -> float:
    """Convert an A/E ratio to a score delta. Returns 0 if sample is too small."""
    if ae is None or runners < 5:
        return 0.0
    high, mid, low = thresholds
    if ae >= 1.5:   return high
    if ae >= 1.2:   return mid
    if ae < 0.6:    return low
    return 0.0


def compute_trainer_score(
    runner: dict,
    race: Optional[dict] = None,
    trainer_profiles: Optional[dict] = None,
) -> tuple[float, list[str]]:
    reasons: list[str] = []; score = 0.0
    t14 = runner.get("trainer_14_days") or {}
    try: pct = float(str(t14.get("percent") or "").strip().rstrip("%"))
    except (ValueError, TypeError): pct = None
    last_run: Optional[int] = runner.get("last_run")
    quick_return = last_run is not None and last_run < 7
    if pct is not None:
        wins = t14.get("wins", "?"); runs = t14.get("runs", "?")
        try: run_count = int(str(runs))
        except (ValueError, TypeError): run_count = 0
        # Weight score by sample size — 50% from 2 runs is noise; 50% from 20 runs is signal
        sample_factor = 1.0 if run_count >= 5 else (0.5 if run_count >= 2 else 0.0)
        _sample_tag = " [small sample]" if sample_factor < 1.0 else ""
        if quick_return:
            reasons.append(f"Trainer {pct:.0f}% 14-day but quick return — edge cancelled")
        elif sample_factor == 0.0:
            reasons.append(f"Trainer 14-day: {pct:.0f}% from 1 run — too small to score")
        elif pct >= 35:
            score += round(8.0 * sample_factor, 1)
            reasons.append(f"Hot trainer — {wins}/{runs} ({pct:.0f}%){_sample_tag}")
        elif pct >= 25:
            score += round(5.0 * sample_factor, 1)
            reasons.append(f"In-form trainer — {wins}/{runs} ({pct:.0f}%){_sample_tag}")
        elif pct >= 12:
            score += round(2.0 * sample_factor, 1)
            reasons.append(f"Trainer ticking over ({pct:.0f}%)")
        else:
            reasons.append(f"Cold trainer ({pct:.0f}%)")

    # Course-specific trainer & jockey analysis (requires trainer_profiles data)
    if trainer_profiles and race:
        trainer_id   = str(runner.get("trainer_id") or "").strip()
        jockey_id    = str(runner.get("jockey_id") or "").strip()
        today_course = str(race.get("course") or "").strip().lower()

        _trainers = trainer_profiles.get("trainers") or {}
        _jockeys  = trainer_profiles.get("jockeys") or {}
        t_data = _trainers.get(trainer_id) or {}

        # Trainer win record at today's course
        if today_course and t_data.get("courses"):
            t_course = t_data["courses"].get(today_course) or {}
            ae = t_course.get("ae"); n = t_course.get("runners", 0); w = t_course.get("wins", 0)
            delta = _ae_score(ae, n, (3.0, 2.0, -2.0))
            if delta > 0:   score += delta; reasons.append(f"Trainer excels at {race.get('course','?')}: {w}/{n} A/E={ae:.2f}")
            elif delta < 0: score += delta; reasons.append(f"Trainer poor at {race.get('course','?')}: {w}/{n} A/E={ae:.2f}")

        # Trainer×jockey combination record
        if jockey_id and t_data.get("jockeys"):
            combo = t_data["jockeys"].get(jockey_id) or {}
            ae = combo.get("ae"); n = combo.get("runners", 0); w = combo.get("wins", 0)
            jname = combo.get("jockey", jockey_id)
            delta = _ae_score(ae, n, (2.0, 1.0, -1.0))
            if delta > 0:   score += delta; reasons.append(f"Strong trainer/jockey combo ({jname}): {w}/{n} A/E={ae:.2f}")
            elif delta < 0: score += delta; reasons.append(f"Weak trainer/jockey combo ({jname}): {w}/{n} A/E={ae:.2f}")

        # Jockey win record at today's course
        if jockey_id and today_course:
            j_course = (_jockeys.get(jockey_id) or {}).get("courses", {}).get(today_course) or {}
            ae = j_course.get("ae"); n = j_course.get("runners", 0); w = j_course.get("wins", 0)
            delta = _ae_score(ae, n, (2.0, 1.0, -1.0))
            if delta > 0:   score += delta; reasons.append(f"Jockey excels at {race.get('course','?')}: {w}/{n} A/E={ae:.2f}")
            elif delta < 0: score += delta; reasons.append(f"Jockey poor at {race.get('course','?')}: {w}/{n} A/E={ae:.2f}")

    # trainer_rtf — "Runs To Form" %, how reliably this trainer's horses perform to rating
    try:
        rtf = float(str(runner.get("trainer_rtf") or "").strip().rstrip("%"))
        if rtf >= 80:   score += 2.0; reasons.append(f"High run-to-form rate: {rtf:.0f}% — reliable trainer")
        elif rtf < 50:  score -= 1.0; reasons.append(f"Low run-to-form rate: {rtf:.0f}% — inconsistent")
    except (ValueError, TypeError):
        pass

    # NH novice/beginner chase — specialist trainer bonus
    # Henderson 24.2%, Lavelle 27.1%, Skelton 23.0% first-time chaser strike rates
    if race:
        _rtl = str(race.get("type") or "").lower()
        _rname_l = str(race.get("race_name") or "").lower()
        _is_novice_chase = ("chase" in _rtl) and any(
            kw in _rname_l for kw in ("novice", "beginner", "maiden chase", "newcomers")
        )
        if _is_novice_chase:
            _tname = str(runner.get("trainer") or "").lower()
            _ftc_map = {
                "henderson": ("N Henderson", 24.2),
                "lavelle":   ("E Lavelle",   27.1),
                "skelton":   ("D Skelton",   23.0),
                "mullins":   ("W Mullins",   21.5),
            }
            for key, (label, sr) in _ftc_map.items():
                if key in _tname:
                    score += 3.0
                    reasons.append(f"FTC specialist trainer: {label} {sr:.1f}% novice chase SR")
                    break

    headgear_run = str(runner.get("headgear_run") or "").strip()
    headgear = (runner.get("headgear") or "").strip()
    if headgear_run == "1" and headgear:
        score -= 2.0; reasons.append(f"First-time {headgear} — negative signal (-2pts)")
    wind_run = str(runner.get("wind_surgery_run") or "").strip()
    wind_type = (runner.get("wind_surgery") or "").strip()
    if wind_run == "1":
        label = f" ({wind_type})" if wind_type else ""
        score += 2.0; reasons.append(f"First run after wind surgery{label}")
    _commentary = (
        (runner.get("stable_tour") or "") + " " + (runner.get("quotes") or "") +
        " " + (runner.get("spotlight") or "") + " " + (runner.get("comment") or "")
    ).lower().strip()
    if _commentary:
        _beaten_fav = any(kw in _commentary for kw in _BEATEN_FAV_NLP)
        _close_loss  = any(kw in _commentary for kw in _CLOSE_LOSER_NLP)
        if _beaten_fav and _close_loss:
            score += 4.0; reasons.append("Beaten favourite — close loser last time, likely value next run")
        elif any(kw in _commentary for kw in _STRONG_POSITIVE_NLP):
            score += 3.0; reasons.append("Strong positive commentary — win signal")
        if any(kw in _commentary for kw in _NEGATIVE_NLP):
            score -= 1.0; reasons.append("Negative commentary — caution")
    if runner.get("prev_trainers"):
        reasons.append("Recent trainer change — monitor")
    medical = runner.get("medical") or []
    if medical:
        types = ", ".join(str(m.get("type") or "?") for m in medical[:2])
        score -= 1.0; reasons.append(f"Medical record on file: {types} — monitor")
    return round(max(0.0, min(15.0, score)), 2), reasons


def compute_market_score(
    runner: dict, market_movers: Optional[dict],
) -> tuple[float, list[str], list[str]]:
    """Market score — penalties only. No positive scoring.
    This is a form-based model. Rewarding short prices picks likely winners at poor
    value, not genuine edge. Mkt score r=-0.12 with wins when positive scoring applied.
    We only act when the market clearly disagrees (big price) or actively moves against."""
    reasons: list[str] = []; fatal_flags: list[str] = []; score = 0.0
    horse_id = str(runner.get("horse_id") or "")
    morning_price = _best_morning_price(runner)

    if morning_price is not None:
        reasons.append(f"Morning price: {format_odds(morning_price)}")
        # No positive scoring for any price band.
        # Penalty only when market significantly disagrees with our form assessment.
        if morning_price > 20.0:
            score -= 3.0; reasons.append("Outsider — market significantly disagrees with form assessment")
        elif morning_price > 12.0:
            score -= 1.0; reasons.append("Double-figure price — market lukewarm on this runner")

    if market_movers and isinstance(market_movers, dict):
        for mover in (market_movers.get("movements") or []):
            if str(mover.get("horse_id") or "") != horse_id: continue
            movement = (mover.get("move_type") or "").lower().strip()
            if movement == "weak_drift":
                score -= 3.0; reasons.append("Market drifting — punters backing rivals")
            elif movement == "dangerous_drift":
                score -= 10.0; fatal_flags.append("dangerous_drift")
                reasons.append("DANGEROUS DRIFT — NAP blocked")
            break
    return round(max(-10.0, min(5.0, score)), 2), reasons, fatal_flags


def assign_confidence(score: float, clustered: bool = False) -> tuple[str, str]:
    """Return (confidence_label, stake_recommendation) based on score.
    Used in email output to guide stake sizing without hard blocks."""
    if clustered:
        return "LOW", "SMALL STAKE or PASS — tight field, no clear standout"
    if score >= 70:
        return "HIGH", "FULL STAKE"
    if score >= 60:
        return "MEDIUM-HIGH", "FULL STAKE"
    if score >= 55:
        return "MEDIUM", "HALF STAKE or EACH WAY"
    if score >= 50:
        return "LOW-MEDIUM", "SMALL STAKE / EACH WAY only"
    return "LOW", "SPECULATIVE — minimal stake or PASS"


def assign_grade(total_score: float) -> str:
    if total_score >= GRADE_A_THRESHOLD: return "A"
    if total_score >= GRADE_B_PLUS_THRESHOLD: return "B+"
    if total_score >= GRADE_B_THRESHOLD: return "B"
    if total_score >= GRADE_C_THRESHOLD: return "C"
    return "D"


def score_runner(
    runner: dict, race: dict, all_runners: list[dict],
    full_form: Optional[dict], market_movers: Optional[dict],
    trainer_profiles: Optional[dict] = None,
) -> dict:
    runner = dict(runner)
    runner["_race_type"] = str(race.get("type") or "")
    form_score, form_reasons = compute_form_score(runner, all_runners)
    suit_score, suit_reasons = compute_suitability_score(runner, race, full_form)
    ctx_score, ctx_reasons   = compute_context_score(race, all_runners)
    draw_score, draw_reasons = compute_draw_score(runner, race)
    trnr_score, trnr_reasons = compute_trainer_score(runner, race, trainer_profiles)
    mkt_score, mkt_reasons, fatal_flags = compute_market_score(runner, market_movers)
    # Professional form-reading overlay (-15..+25): class drops, pace shape,
    # proven course+distance, freshness, narrative. Lifts genuinely strong
    # horses out of the score-compression zone so the card yields real picks.
    wisdom_score: float = 0.0
    wisdom_reasons: list[str] = []
    if _WISDOM_AVAILABLE:
        try:
            wisdom_score, wisdom_reasons = score_racing_wisdom(
                runner, race, all_runners, full_form
            )
        except Exception:  # pragma: no cover - never let the overlay break scoring
            wisdom_score, wisdom_reasons = 0.0, []
    base = form_score + suit_score + ctx_score + draw_score + trnr_score + mkt_score
    total = max(0.0, min(100.0, base + wisdom_score))
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
        "context_score": ctx_score, "draw_score": round(draw_score, 2),
        "trainer_score": trnr_score, "market_score": mkt_score,
        "wisdom_score": round(wisdom_score, 2),
        "reasons": form_reasons + suit_reasons + ctx_reasons + draw_reasons + trnr_reasons + mkt_reasons + wisdom_reasons,
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

    trainer_profiles: Optional[dict] = safe_load_json(data_path(f"trainer_profiles_{date_str}.json"))
    if trainer_profiles is None:
        log("nap_selector_v3: trainer_profiles not available — course/combo signals skipped", "INFO")

    race_scores: dict[str, list[dict]] = {}
    for race in racecards:
        race_id = str(race.get("race_id") or "")
        runners: list[dict] = race.get("runners") or []
        if not runners: continue
        scored = [score_runner(r, race, runners, full_form, market_movers, trainer_profiles) for r in runners]
        scored.sort(key=lambda r: r["score"], reverse=True)
        race_scores[race_id] = scored

    total_runners = sum(len(v) for v in race_scores.values())
    log(f"nap_selector_v3: scored {total_runners} runners across {len(race_scores)} races")

    cluster_races: list[str] = []
    for race_id, scored in race_scores.items():
        if detect_race_cluster(scored):
            cluster_races.append(race_id)

    nap_candidates: list[dict] = []
    fallback_pool: list[dict] = []   # passed every STRUCTURAL gate but below the score floor
    no_bet_races: list[str] = []
    for race_id, scored in race_scores.items():
        if not scored: continue
        top = scored[0]
        # Hard exclusions — these are structural, not score-based. A horse failing
        # any of these can NEVER be the pick (not even as a thin-card fallback).
        if any(x in (top.get("race_type") or "").lower() for x in NAP_EXCLUDED_RACE_TYPES):
            no_bet_races.append(race_id); continue
        # dangerous_drift = only fatal market signal
        if "dangerous_drift" in (top.get("warnings") or []):
            no_bet_races.append(race_id); continue
        # Odds gates — no value at short prices; 8/1+ is -39.4% ROI
        if top.get("morning_price") is not None and top["morning_price"] < NAP_MIN_ODDS:
            no_bet_races.append(race_id); continue
        if top.get("morning_price") is not None and top["morning_price"] > NAP_MAX_ODDS:
            no_bet_races.append(race_id); continue
        # Flat going filter — Firm/Heavy excluded; G-F monitored but not excluded
        _is_flat = not any(x in (top.get("race_type") or "").lower() for x in ("chase", "hurdle", "bumper"))
        if _is_flat and going_normalise(top.get("going") or "") in FLAT_EXCLUDED_GOING:
            no_bet_races.append(race_id); continue
        # Cluster races get a warning flag on the pick, not a hard block.
        if race_id in cluster_races:
            top = dict(top)
            top["warnings"] = list(top.get("warnings") or []) + ["cluster_warning"]
        # Above the floor → a full-confidence candidate. Below the floor → kept in the
        # fallback pool so a structurally-sound card ALWAYS yields a best-available pick.
        if top["score"] >= NAP_MIN_SCORE:
            nap_candidates.append(top)
        else:
            fallback_pool.append(top)

    nap_candidates.sort(key=lambda r: r["score"], reverse=True)
    fallback_pool.sort(key=lambda r: r["score"], reverse=True)

    nap: Optional[dict] = None
    day_verdict: str
    if nap_candidates:
        best_candidate = nap_candidates[0]
        best_candidate["status"] = "NAP"
        is_clustered = "cluster_warning" in (best_candidate.get("warnings") or [])
        confidence, stake_rec = assign_confidence(best_candidate["score"], is_clustered)
        best_candidate["confidence"] = confidence
        best_candidate["stake_recommendation"] = stake_rec
        nap = best_candidate
        day_verdict = f"NAP_SELECTED ({confidence} CONFIDENCE)"
    elif fallback_pool:
        # No horse cleared the score floor, but racing exists and structurally-sound
        # options remain. Surface the single best one as the pick with honest LOW
        # confidence — the system always gives an option, never a blank day.
        best_candidate = fallback_pool[0]
        best_candidate["status"] = "NAP"
        best_candidate["confidence"] = "LOW"
        best_candidate["stake_recommendation"] = (
            "SPECULATIVE — best available on a thin card; minimal stake or watch only"
        )
        best_candidate["warnings"] = list(best_candidate.get("warnings") or []) + ["below_score_floor"]
        nap = best_candidate
        day_verdict = (
            f"BEST_AVAILABLE (LOW CONFIDENCE — top score {best_candidate['score']:.1f} "
            f"below floor {NAP_MIN_SCORE:.0f})"
        )
    else:
        day_verdict = "NO_BET — every card top was a chase, dangerous drift, or excluded going/odds"

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
        if best_of_card is None and grade == "A": r["status"] = "BEST_OF_CARD"; best_of_card = r
        elif grade in ("B+", "B"): r["status"] = "WATCHLIST"; watchlist.append(r)
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

    _field_cluster = bool(
        nap and "field_cluster_warning" in (nap.get("warnings") or [])
    )
    output: dict = {
        "date": date_str, "generated_at": generated_at_iso, "model_version": MODEL_VERSION,
        "nap": nap, "jump_nap": jump_nap, "best_of_card": best_of_card,
        "watchlist": watchlist[:10], "shadow": shadow[:10],
        "cluster_races": cluster_races, "no_bet_races": no_bet_races, "day_verdict": day_verdict,
        "field_cluster_warning": _field_cluster,
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
