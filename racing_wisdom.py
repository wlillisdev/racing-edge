"""
racing_wisdom.py — Professional Racing Intelligence Scoring Library

Codifies the patterns that separate serious punters from amateurs:
class drops, pace projection, seasonal targeting, proven course+distance,
form consistency, weight advantage, market confidence, narrative, freshness
profile, and field quality assessment.

Usage:
    from racing_wisdom import score_racing_wisdom

    delta, reasons = score_racing_wisdom(runner, race, all_runners, full_form)

Score range: -15 to +25 (additive overlay on top of main model).

Each pattern is implemented as a private function returning (pts, [reasons]).
All patterns degrade gracefully when data is missing.
"""

from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

WISDOM_MIN: float = -15.0
WISDOM_MAX: float = 25.0

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_int(v, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _safe_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _parse_form_chars(form: str) -> list[str]:
    """Return up to 8 most-recent form characters (digits + FUPBR)."""
    if not form or form.strip() in ("-", ""):
        return []
    form = form.strip().replace(" ", "")
    last_dash = form.rfind("-")
    segment = form[last_dash + 1:] if last_dash != -1 else form
    if not segment and last_dash != -1:
        # Trailing dash ("12345-"): all runs were last season — still form.
        segment = form[:last_dash]
    valid: list[str] = []
    for ch in reversed(segment):
        upper = ch.upper()
        if upper.isdigit() or upper in ("F", "U", "P", "R", "B"):
            valid.append(upper)
        if len(valid) >= 8:
            break
    return valid


def _normalise_class(class_str: str) -> Optional[int]:
    """Return integer 1-7 from a class string, or None if unparseable."""
    s = str(class_str or "").strip().lower()
    if s.startswith("class"):
        s = s[5:].strip()
    # Grade 1/2/3 (NH), Group 1/2/3 (flat) and Listed races are ALL Class 1
    # in the UK classification — a Grade 3 is NOT Class 3.
    if re.search(r"\b(?:grade|group)\s*\d\b", s) or "listed" in s:
        return 1
    try:
        c = int(s)
        if 1 <= c <= 7:
            return c
    except (TypeError, ValueError):
        pass
    return None


def _get_horse_history(horse_id: str, full_form: Optional[dict]) -> list[dict]:
    """Extract per-horse run list from the full_form blob."""
    if not full_form or not isinstance(full_form, dict):
        return []
    if not horse_id:
        return []
    horses = full_form.get("horses") or {}
    if horse_id in horses:
        h = horses[horse_id]
        return h if isinstance(h, list) else []
    # Some implementations store runs directly under horse_id
    h = full_form.get(horse_id)
    if isinstance(h, list):
        return h
    return []


def _dist_f(val) -> float:
    """Convert a raw distance value to furlongs (float)."""
    try:
        return float(val)
    except (TypeError, ValueError):
        pass
    # Minimal inline distance parsing (avoids circular import issues)
    s = str(val or "").strip().lower().replace(" ", "")
    if not s:
        return 0.0
    m = re.fullmatch(r"(?:(\d+)m)?(?:(\d+)f)?(?:(\d+)y)?", s)
    if m:
        miles = int(m.group(1) or 0)
        furlongs = int(m.group(2) or 0)
        yards = int(m.group(3) or 0)
        total = miles * 8.0 + furlongs + yards / 220.0
        if total > 0:
            return round(total, 4)
    return 0.0


def _rpr_value(runner: dict) -> Optional[int]:
    try:
        v = int(str(runner.get("rpr") or "").strip())
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# PATTERN 1: CLASS DROP / CLASS PROFILE
# ---------------------------------------------------------------------------

def _score_class_drop(
    runner: dict, race: dict, full_form: list[dict]
) -> tuple[float, list[str]]:
    """
    Win at higher class → bully in today's race (+4).
    Win at same class   → proven here (+2).
    Multiple losses below today's class → ceiling exposed (-3).
    """
    today_class = _normalise_class(race.get("class") or race.get("race_class") or "")
    if today_class is None:
        return 0.0, []

    if not full_form:
        return 0.0, []

    wins_at_class: list[int] = []
    losses_below: int = 0
    total_runs: int = 0

    for result in full_form:
        pos = str(result.get("position") or result.get("finish_position") or "")
        r_class = _normalise_class(
            result.get("class") or result.get("race_class") or ""
        )
        if r_class is None:
            continue
        total_runs += 1
        won = pos == "1"
        if won:
            wins_at_class.append(r_class)
        elif r_class >= today_class:  # same or lower class loss
            losses_below += 1

    if total_runs == 0:
        return 0.0, []

    if wins_at_class:
        best_win_class = min(wins_at_class)  # lower number = higher class
        if best_win_class < today_class:
            return 4.0, [
                f"Class drop: won at Class {best_win_class}, today's race Class {today_class} — bully in this field"
            ]
        elif best_win_class == today_class:
            return 2.0, [f"Proven at this class (Class {today_class} winner)"]
        # Won, but only at lower classes — no credit
        return 0.0, []

    # Never won — check persistent losing at lower class
    if losses_below >= 3 and total_runs >= 4:
        return -3.0, [
            f"Class ceiling: {losses_below} losses at Class {today_class} or below without a win"
        ]

    return 0.0, []


# ---------------------------------------------------------------------------
# PATTERN 2: RACE SHAPE / PACE PROJECTION
# ---------------------------------------------------------------------------

def _score_pace_projection(
    runner: dict, all_runners: list[dict]
) -> tuple[float, list[str]]:
    """
    Approximate pace scenario from recent form strings.
    A horse with 3+ recent wins is likely competitive / can dictate.
    Count likely front-runners (horses with wins in last 3 runs) across field.
    """
    def _recent_wins(r: dict) -> int:
        chars = _parse_form_chars(r.get("form") or "")
        return sum(1 for c in chars[:3] if c == "1")

    this_recent_wins = _recent_wins(runner)
    field_front_runners = sum(
        1 for r in all_runners if _recent_wins(r) >= 2
    )

    if this_recent_wins >= 3 and field_front_runners == 1:
        return 3.0, [
            "Pace advantage: likely sole pace-setter based on recent dominant form"
        ]
    # NOTE: no bonus for winless horses in "hot pace" fields — zero recent
    # wins is evidence of being out of form, not of being a hold-up runner.
    # The old +3 here handed a 5-point swing to worse horses in competitive
    # races. There is no running-style data in the inputs to gate it on.
    if this_recent_wins >= 2 and field_front_runners >= 3:
        return -2.0, [
            f"Contested pace: {field_front_runners} likely front-runners in field, pace war likely"
        ]

    return 0.0, []


# ---------------------------------------------------------------------------
# PATTERN 3: SEASONAL TIMING / TRAINER TARGETING
# ---------------------------------------------------------------------------

def _score_seasonal_targeting(
    runner: dict,
) -> tuple[float, list[str]]:
    """
    Absence of 60+ days + hot trainer = TARGETING THIS RACE.
    Absence of 60+ days + cold trainer = ticking over.
    """
    last_run: Optional[int] = runner.get("last_run")
    if last_run is None or last_run < 60:
        return 0.0, []

    t14 = runner.get("trainer_14_days") or {}
    try:
        pct = float(str(t14.get("percent") or "").strip().rstrip("%"))
    except (ValueError, TypeError):
        return 0.0, []

    wins = t14.get("wins", "?")
    runs = t14.get("runs", "?")

    if pct >= 20.0:
        return 4.0, [
            f"Seasonal target: {last_run} days off + hot trainer ({pct:.0f}% in 14 days, {wins}/{runs}) — targeting this race"
        ]
    if pct < 10.0:
        return -1.0, [
            f"Absence concern: {last_run} days off + cold trainer ({pct:.0f}%) — just ticking over"
        ]

    return 0.0, []


# ---------------------------------------------------------------------------
# PATTERN 4: PROVEN COURSE + DISTANCE COMBINATION
# ---------------------------------------------------------------------------

def _score_course_distance_combo(
    runner: dict, race: dict, full_form: list[dict]
) -> tuple[float, list[str]]:
    """
    Won at exact course AND within 0.5f today's distance → +6 (strongest signal).
    Placed at exact course+distance → +3.
    Won at course but different distance → +2.
    """
    today_course = (race.get("course") or "").strip().lower()
    today_dist = _dist_f(race.get("distance_f") or race.get("distance") or 0)

    if not today_course or not full_form:
        return 0.0, []

    best_cd_win = False
    best_cd_placed = False
    course_win_any_dist = False

    for result in full_form:
        pos = str(result.get("position") or result.get("finish_position") or "")
        won = pos == "1"
        placed = pos in ("1", "2", "3")
        r_course = (result.get("course") or "").strip().lower()
        r_dist = _dist_f(result.get("distance_f") or result.get("distance") or 0)

        if r_course != today_course:
            continue

        if won:
            course_win_any_dist = True

        if today_dist > 0 and r_dist > 0 and abs(today_dist - r_dist) <= 0.5:
            if won:
                best_cd_win = True
            elif placed:
                best_cd_placed = True

    if best_cd_win:
        return 6.0, [
            f"Course+Distance winner: won at {today_course.title()} over today's trip (strongest profile)"
        ]
    if best_cd_placed:
        return 3.0, [
            f"Course+Distance placed: placed at {today_course.title()} over today's trip"
        ]
    if course_win_any_dist:
        return 2.0, [
            f"Course winner: won at {today_course.title()} (different trip)"
        ]

    return 0.0, []


# ---------------------------------------------------------------------------
# PATTERN 5: CONSISTENT FORM RELEVANCE
# ---------------------------------------------------------------------------

def _score_form_consistency(
    runner: dict, full_form: list[dict]
) -> tuple[float, list[str]]:
    """
    Win% from last 8 runs in full form:
      >50%  → +4 (genuine winner)
      25-50% → +2 (competitive)
      10-25% → 0
      <10%  → -2 (perennial loser)
    If recent win% > career win%, add +2 (improving horse).
    """
    # Use full_form for career stats if available; else fall back to form string
    if full_form:
        runs = full_form[:8]
        if not runs:
            return 0.0, []
        wins_recent = sum(
            1 for r in runs
            if str(r.get("position") or r.get("finish_position") or "") == "1"
        )
        n_recent = len(runs)

        career_runs = full_form
        career_wins = sum(
            1 for r in career_runs
            if str(r.get("position") or r.get("finish_position") or "") == "1"
        )
        n_career = len(career_runs)
    else:
        # Fallback: parse form string (up to 8 chars)
        chars = _parse_form_chars(runner.get("form") or "")
        if not chars:
            return 0.0, []
        wins_recent = chars.count("1")
        n_recent = len(chars)
        career_wins = wins_recent
        n_career = n_recent

    if n_recent == 0:
        return 0.0, []

    recent_win_pct = wins_recent / n_recent
    career_win_pct = career_wins / n_career if n_career > 0 else recent_win_pct

    reasons: list[str] = []
    pts = 0.0

    if recent_win_pct > 0.50:
        pts += 4.0
        reasons.append(
            f"Genuine winner: {wins_recent}/{n_recent} from last 8 runs ({recent_win_pct:.0%} win rate)"
        )
    elif recent_win_pct >= 0.25:
        pts += 2.0
        reasons.append(
            f"Consistent: {wins_recent}/{n_recent} from last 8 runs ({recent_win_pct:.0%})"
        )
    elif recent_win_pct < 0.10 and n_recent >= 6:
        pts += -2.0
        reasons.append(
            f"Perennial loser: {wins_recent}/{n_recent} wins from last 8 runs ({recent_win_pct:.0%})"
        )

    # Improving signal: recent rate beats career rate by meaningful margin
    if n_career > n_recent and (recent_win_pct - career_win_pct) >= 0.10:
        pts += 2.0
        reasons.append(
            f"Improving form: recent win rate {recent_win_pct:.0%} vs career {career_win_pct:.0%}"
        )

    return pts, reasons


# ---------------------------------------------------------------------------
# PATTERN 6: WEIGHT ADVANTAGE
# ---------------------------------------------------------------------------

def _score_weight_advantage(
    runner: dict, full_form: list[dict]
) -> tuple[float, list[str]]:
    """
    Compare today's weight to weights carried in last 6 months of full form.
    Lowest weight in period → +3; highest → -2; 3+ lb drop vs last run → +2.
    Falls back to comparing lbs vs weight_lbs if full_form empty.
    """
    today_lbs = _safe_int(runner.get("lbs") or runner.get("weight_lbs"), 0)
    if today_lbs <= 0:
        return 0.0, []

    if not full_form:
        return 0.0, []

    recent_weights: list[int] = []
    for result in full_form[:12]:  # ~6 months assuming bi-weekly runs
        w = _safe_int(
            result.get("lbs") or result.get("weight_lbs") or result.get("weight"), 0
        )
        if w > 0:
            recent_weights.append(w)

    if not recent_weights:
        return 0.0, []

    min_w = min(recent_weights)
    max_w = max(recent_weights)
    last_w = recent_weights[0]  # most recent run

    reasons: list[str] = []
    pts = 0.0

    if today_lbs <= min_w:
        pts += 3.0
        reasons.append(
            f"Lowest weight in 6 months ({today_lbs} lbs) — running off career-low burden"
        )
    elif today_lbs >= max_w:
        pts -= 2.0
        reasons.append(
            f"Highest weight in 6 months ({today_lbs} lbs) — handicapper has horse at ceiling"
        )

    # Weight drop vs last run
    drop = last_w - today_lbs
    if drop >= 3:
        pts += 2.0
        reasons.append(
            f"Handicapper kindness: {drop} lbs lighter than last run ({last_w} → {today_lbs} lbs)"
        )

    return pts, reasons


# ---------------------------------------------------------------------------
# PATTERN 7: MARKET CONFIDENCE COMPOSITE
# ---------------------------------------------------------------------------

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


def _score_market_confidence(runner: dict) -> tuple[float, list[str]]:
    """
    Short price + recent win = market endorsing model.
    Forecast price (sp_dec) vs best morning price differential.
    """
    morning_price = _best_morning_price(runner)
    if morning_price is None:
        return 0.0, []

    # sp_dec on the runner is the last known SP estimate / forecast price
    sp_dec = _safe_float(runner.get("sp_dec"), 0.0)

    chars = _parse_form_chars(runner.get("form") or "")
    recent_win = "1" in chars[:3]

    reasons: list[str] = []
    pts = 0.0

    # Market endorsing a horse the model already likes
    if morning_price < 2.5 and recent_win:
        pts += 3.0
        reasons.append(
            f"Market+form alignment: short price ({morning_price:.2f}) with recent win — market endorsing selection"
        )
    elif morning_price < 2.5 and not recent_win:
        # Market confidence without form backing — mixed signal, no points
        pass

    # Price contraction: morning price materially shorter than SP forecast
    if sp_dec > 1.0 and morning_price > 1.0 and sp_dec > morning_price * 1.25:
        pts += 2.0
        reasons.append(
            f"Price contraction: forecast {sp_dec:.2f} vs morning {morning_price:.2f} — money coming in"
        )

    # Multiple bookmakers showing same short price (approximate: short price exists at all)
    if 0 < morning_price <= 4.0:
        # Could also add: count odds entries agreeing
        odds_list = runner.get("odds") or []
        short_books = sum(
            1 for o in odds_list
            if _safe_float(o.get("decimal"), 99) <= morning_price * 1.1
        )
        if short_books >= 3:
            pts += 1.0
            reasons.append(
                f"Market consensus: {short_books} books agree on short price ({morning_price:.2f})"
            )

    return pts, reasons


# ---------------------------------------------------------------------------
# PATTERN 8: NARRATIVE CHECK
# ---------------------------------------------------------------------------

_POSITIVE_KEYWORDS: list[str] = [
    "well", "improves", "progressive", "fit", "should", "interesting",
    "confidence", "targeting", "pleasing", "encouraging", "promising",
    "exciting", "unlucky", "capable", "win", "ready",
]

_NEGATIVE_KEYWORDS: list[str] = [
    "needs", "disappointing", "unsure", "doubt", "bounce", "tired",
    "weak", "struggling", "difficult", "poor", "below", "concern",
    "injured", "lame", "pulled up", "tailed off",
]

_STABLE_CONFIDENCE_KEYWORDS: list[str] = [
    "targeting", "win", "ready", "confident", "fit", "sure", "best",
]


def _score_narrative(runner: dict) -> tuple[float, list[str]]:
    """
    Scan spotlight / comment / quotes / stable_tour for positive/negative signals.
    """
    texts: list[str] = []
    for field in ("spotlight", "comment", "quotes", "stable_tour"):
        v = (runner.get(field) or "").lower().strip()
        if v:
            texts.append(v)

    if not texts:
        return 0.0, []

    combined = " ".join(texts)
    pos_hits = [kw for kw in _POSITIVE_KEYWORDS if kw in combined]
    neg_hits = [kw for kw in _NEGATIVE_KEYWORDS if kw in combined]

    # Stable tour confidence (highest-quality text signal)
    stable_text = (runner.get("stable_tour") or "").lower()
    stable_conf_hits = [kw for kw in _STABLE_CONFIDENCE_KEYWORDS if kw in stable_text]

    reasons: list[str] = []
    pts = 0.0

    if stable_conf_hits and stable_text:
        pts += 3.0
        reasons.append(
            f"Stable tour confidence: '{', '.join(stable_conf_hits[:3])}' — strong trainer signal"
        )
    elif len(pos_hits) >= 2 and len(pos_hits) > len(neg_hits):
        pts += 2.0
        reasons.append(
            f"Positive narrative: {len(pos_hits)} positive signals ({', '.join(pos_hits[:4])})"
        )
    elif len(neg_hits) >= 2 and len(neg_hits) > len(pos_hits):
        pts -= 2.0
        reasons.append(
            f"Negative narrative: {len(neg_hits)} negative signals ({', '.join(neg_hits[:4])})"
        )

    return pts, reasons


# ---------------------------------------------------------------------------
# PATTERN 9: FRESHNESS + PROFILE MATCH
# ---------------------------------------------------------------------------

def _score_freshness_profile(
    runner: dict, race: dict, full_form: list[dict]
) -> tuple[float, list[str]]:
    """
    45-90 day break (sweet spot) + trainer specialises in fresh horses:
      - Trainer win% 14-day 25%+ with similar horses → +3
      - Trainer has won in same scenario (same dist+class+going) → +4
    """
    last_run: Optional[int] = runner.get("last_run")
    if last_run is None or not (45 <= last_run <= 90):
        return 0.0, []

    t14 = runner.get("trainer_14_days") or {}
    try:
        pct = float(str(t14.get("percent") or "").strip().rstrip("%"))
    except (ValueError, TypeError):
        pct = None

    reasons: list[str] = []
    pts = 0.0

    if pct is not None and pct >= 25.0:
        pts += 3.0
        reasons.append(
            f"Freshness profile: {last_run} days off + trainer specialises in fresh horses ({pct:.0f}% win rate)"
        )

    # Check full_form for trainer winning in similar scenario
    if full_form:
        today_dist = _dist_f(race.get("distance_f") or race.get("distance") or 0)
        today_class = _normalise_class(race.get("class") or race.get("race_class") or "")
        today_going = (race.get("going") or "").strip().lower()

        for result in full_form:
            pos = str(result.get("position") or result.get("finish_position") or "")
            if pos != "1":
                continue
            r_dist = _dist_f(result.get("distance_f") or result.get("distance") or 0)
            r_class = _normalise_class(result.get("class") or result.get("race_class") or "")
            r_going = (result.get("going") or "").strip().lower()
            # Approximate break check — if we have a days_since field
            r_days = _safe_int(result.get("days_since_prev") or result.get("last_run"), 0)

            dist_match = today_dist > 0 and r_dist > 0 and abs(today_dist - r_dist) <= 1.0
            class_match = today_class is not None and r_class == today_class
            going_match = today_going and r_going and today_going[:4] in r_going
            break_match = 45 <= r_days <= 90

            if dist_match and class_match and going_match and break_match and pts < 4.0:
                pts = 4.0
                reasons = [
                    f"Scenario repeat: horse has WON after similar {r_days}-day break at this dist/class/going"
                ]
                break

    return pts, reasons


# ---------------------------------------------------------------------------
# PATTERN 10: FIELD QUALITY ASSESSMENT
# ---------------------------------------------------------------------------

def _score_field_quality(
    runner: dict, all_runners: list[dict]
) -> tuple[float, list[str]]:
    """
    RPR dominance:
      - RPR 10+ above field average → +4
      - Field is clustered (>3 runners within 5 RPR of top): flag as competitive
    """
    my_rpr = _rpr_value(runner)
    if my_rpr is None:
        return 0.0, []

    field_rprs: list[int] = []
    for r in all_runners:
        v = _rpr_value(r)
        if v is not None:
            field_rprs.append(v)

    if len(field_rprs) < 2:
        return 0.0, []

    field_avg = sum(field_rprs) / len(field_rprs)
    top_rpr = max(field_rprs)

    reasons: list[str] = []
    pts = 0.0

    if my_rpr >= field_avg + 10:
        pts += 4.0
        reasons.append(
            f"RPR dominance: {my_rpr} vs field avg {field_avg:.0f} — dominant quality edge"
        )
    elif my_rpr < field_avg:
        # Below average RPR — no positive signal, subtle negative
        reasons.append(
            f"Below field RPR average ({my_rpr} vs avg {field_avg:.0f})"
        )

    # Cluster check: how many runners within 5 RPR of top?
    close_to_top = sum(1 for r in field_rprs if top_rpr - r <= 5)
    if close_to_top >= 4:
        reasons.append(
            f"Cluster race: {close_to_top} runners within 5 RPR of top — competitive field"
        )

    return pts, reasons


# ---------------------------------------------------------------------------
# PATTERN 11: FORM FRANKING (race quality from subsequent results)
# ---------------------------------------------------------------------------

# Field share that must have won since for a race to count as "frankened".
_FRANK_STRONG_Q: float = 0.25
_FRANK_MIN_FIELD: int = 6  # below this, q=0 is too noisy to call a race weak

_quality_cache: Optional[dict] = None
_quality_cache_loaded: bool = False


def _get_quality_cache() -> Optional[dict]:
    """Lazy-load the race quality cache once per process. None when absent —
    the pattern then scores 0, same as every other data-missing case."""
    global _quality_cache, _quality_cache_loaded
    if not _quality_cache_loaded:
        _quality_cache_loaded = True
        try:
            from race_quality_builder import load_quality_lookup
            _quality_cache = load_quality_lookup()
        except Exception as exc:
            _quality_cache = None
            try:
                from src.helpers import log
                log(f"racing_wisdom: race quality cache unavailable — {exc}", "WARNING")
            except Exception:
                pass
    return _quality_cache


def _score_form_franking(
    runner: dict, full_form: list[dict]
) -> tuple[float, list[str]]:
    """
    Not all races are equal — judge a horse's recent runs by what the rest of
    that field did NEXT (race_quality_builder cache):

    Win/close placing in a frankened race (>=25% of field won since)  → +2/+3

    No penalty for q=0 races: the cache only sees races the system itself
    tracked, so "nobody from the field has won since" usually means "we
    didn't see the field's later runs" — not evidence the race was weak.
    Races too recent to judge, unmatched, or ambiguous score nothing.
    """
    if not full_form:
        return 0.0, []
    cache = _get_quality_cache()
    if not cache:
        return 0.0, []

    try:
        from race_quality_builder import quality_for_run
    except Exception:
        return 0.0, []

    pts = 0.0
    reasons: list[str] = []
    for run in full_form[:3]:  # most recent runs carry the live form
        meta = quality_for_run(run, cache)
        if not meta:
            continue
        pos = str(run.get("position") or run.get("finish_position") or "").strip()
        try:
            pos_int = int(pos)
        except (ValueError, TypeError):
            continue
        q = float(meta.get("q") or 0.0)
        subs = int(meta.get("subs_winners") or 0)
        field = int(meta.get("field") or 0)

        if q >= _FRANK_STRONG_Q:
            bl_raw = run.get("beaten_lengths")
            if bl_raw is None:
                bl_raw = run.get("btn")
            bl = _safe_float(bl_raw, -1.0) if bl_raw is not None else -1.0
            if pos_int == 1:
                pts += 3.0
                reasons.append(
                    f"Form franked: won a race where {subs}/{field} have won since"
                )
            elif pos_int <= 3 and 0.0 <= bl <= 1.5:
                pts += 3.0
                reasons.append(
                    f"Form franked: beaten {bl}L in a hot race — {subs}/{field} won since"
                )
            elif pos_int <= 3:
                pts += 2.0
                reasons.append(
                    f"Form franked: placed in a race where {subs}/{field} have won since"
                )

    return min(4.0, pts), reasons


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_racing_wisdom(
    runner: dict,
    race: dict,
    all_runners: list[dict],
    full_form: Optional[dict],
) -> tuple[float, list[str]]:
    """Apply professional racing intelligence patterns.

    Parameters
    ----------
    runner      : normalised runner dict (from run_daily._normalise_runner)
    race        : normalised race dict (from run_daily._normalise_racecard)
    all_runners : all runners in the same race (for pace/field analysis)
    full_form   : full_form blob (dict with 'horses' key or horse_id keys);
                  may be None — all patterns degrade gracefully.

    Returns
    -------
    (score_delta, reasons)
        score_delta : float in [-15, +25], additive overlay on main model
        reasons     : list of human-readable explanation strings
    """
    horse_id = str(runner.get("horse_id") or "")
    history = _get_horse_history(horse_id, full_form)

    all_reasons: list[str] = []
    total = 0.0

    def _apply(fn, *args):
        nonlocal total
        try:
            pts, reasons = fn(*args)
        except Exception as exc:
            # Degrade to 0 but say so — a silently broken pattern is
            # indistinguishable from "no signal" and stays broken forever.
            try:
                from src.helpers import log
                log(f"racing_wisdom: pattern {fn.__name__} failed — {exc}", "WARNING")
            except Exception:
                pass
            return
        total += pts
        all_reasons.extend(reasons)

    # Pattern 1 — Class drop / class profile
    _apply(_score_class_drop, runner, race, history)

    # Pattern 2 — Race shape / pace projection
    _apply(_score_pace_projection, runner, all_runners)

    # Pattern 3 — Seasonal timing / trainer targeting
    _apply(_score_seasonal_targeting, runner)

    # Pattern 4 — Proven course + distance combination
    _apply(_score_course_distance_combo, runner, race, history)

    # Pattern 5 — Form consistency
    _apply(_score_form_consistency, runner, history)

    # Pattern 6 — Weight advantage
    _apply(_score_weight_advantage, runner, history)

    # Pattern 7 — Market confidence composite
    _apply(_score_market_confidence, runner)

    # Pattern 8 — Narrative check
    _apply(_score_narrative, runner)

    # Pattern 9 — Freshness + profile match
    _apply(_score_freshness_profile, runner, race, history)

    # Pattern 10 — Field quality assessment
    _apply(_score_field_quality, runner, all_runners)

    # Pattern 11 — Form franking (subsequent-results race quality)
    _apply(_score_form_franking, runner, history)

    # Clamp to declared range
    clamped = round(max(WISDOM_MIN, min(WISDOM_MAX, total)), 2)
    return clamped, all_reasons


def _explain(runner: dict, race: dict, all_runners: list[dict], full_form: Optional[dict]) -> str:
    """Return a human-readable explanation of the wisdom scoring for a runner."""
    score, reasons = score_racing_wisdom(runner, race, all_runners, full_form)
    horse = runner.get("horse") or runner.get("horse_id") or "Unknown"
    course = race.get("course") or "?"
    distance = race.get("distance_f") or race.get("distance") or "?"
    race_class = race.get("class") or race.get("race_class") or "?"

    lines = [
        f"=== RACING WISDOM: {horse} ===",
        f"Race: {course} {distance}f  Class: {race_class}",
        f"Wisdom Score Delta: {score:+.1f}  (range {WISDOM_MIN} to +{WISDOM_MAX})",
        "",
        "Factors:",
    ]
    if reasons:
        for r in reasons:
            lines.append(f"  • {r}")
    else:
        lines.append("  (No wisdom signals triggered — data insufficient)")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    """Demonstrate scoring with a synthetic example covering all 10 patterns."""

    print("=" * 60)
    print("RACING WISDOM — TEST HARNESS")
    print("=" * 60)

    # ----------------------------------------------------------------
    # Synthetic race: 3 runners at Newmarket, 8f, Class 3, Good to Soft
    # ----------------------------------------------------------------
    race = {
        "race_id":    "TEST001",
        "course":     "Newmarket",
        "distance_f": 8.0,
        "class":      "3",
        "going":      "Good to Soft",
        "type":       "Flat",
        "field_size": 3,
    }

    # Horse A: Strong profile — class drop, course+dist winner, hot trainer, fresh
    runner_a = {
        "horse_id":         "A001",
        "horse":            "Silverwave",
        "form":             "11-211",        # won last 3
        "last_run":         70,              # 70 days off
        "rpr":              118,
        "lbs":              126,
        "weight_lbs":       126,
        "trainer_14_days":  {"wins": 8, "runs": 25, "percent": "32"},
        "spotlight":        "progressive horse who should improve and looks well for this",
        "comment":          "confidence boosted by last win, targeting this race",
        "quotes":           "",
        "stable_tour":      "trainer targeting this race, horse is fit and ready to win",
        "odds":             [{"decimal": 2.2}, {"decimal": 2.2}, {"decimal": 2.3}],
        "sp_dec":           3.5,
        "headgear":         "",
        "headgear_run":     "",
        "wind_surgery_run": "",
        "prev_trainers":    [],
    }

    # Synthetic full_form for horse A: won at Class 2 (higher), won at Newmarket 8f
    full_form_a: list[dict] = [
        {
            "position": "1", "course": "Newmarket", "distance_f": 8.0,
            "class": "2", "going": "Good to Soft", "lbs": 128, "days_since_prev": 14,
        },
        {
            "position": "1", "course": "Newmarket", "distance_f": 8.0,
            "class": "3", "going": "Good to Soft", "lbs": 127, "days_since_prev": 18,
        },
        {
            "position": "2", "course": "Ascot",     "distance_f": 8.0,
            "class": "2", "going": "Good",          "lbs": 130, "days_since_prev": 20,
        },
        {
            "position": "1", "course": "Ascot",     "distance_f": 7.0,
            "class": "3", "going": "Soft",          "lbs": 126, "days_since_prev": 72,
        },
        {
            "position": "3", "course": "Sandown",   "distance_f": 8.0,
            "class": "4", "going": "Good",          "lbs": 125, "days_since_prev": 21,
        },
    ]

    full_form_blob = {
        "horses": {
            "A001": full_form_a,
        }
    }

    # Horse B: Average profile — closer, competitive field
    runner_b = {
        "horse_id":         "B002",
        "horse":            "GrayMist",
        "form":             "3-32451",       # won once in last 8
        "last_run":         15,
        "rpr":              110,
        "lbs":              130,
        "weight_lbs":       130,
        "trainer_14_days":  {"wins": 2, "runs": 30, "percent": "7"},
        "spotlight":        "disappointing last time, needs to improve, doubt about stamina",
        "comment":          "tired late on, uncertain about today's conditions",
        "quotes":           "",
        "stable_tour":      "",
        "odds":             [{"decimal": 5.0}],
        "sp_dec":           5.0,
        "headgear":         "",
        "headgear_run":     "",
        "wind_surgery_run": "",
        "prev_trainers":    [],
    }

    # Horse C: Outsider with some pace — likely front runner
    runner_c = {
        "horse_id":         "C003",
        "horse":            "SwiftBreeze",
        "form":             "1-11143",
        "last_run":         10,
        "rpr":              105,
        "lbs":              124,
        "weight_lbs":       124,
        "trainer_14_days":  {"wins": 1, "runs": 20, "percent": "5"},
        "spotlight":        "",
        "comment":          "",
        "quotes":           "",
        "stable_tour":      "",
        "odds":             [{"decimal": 8.0}],
        "sp_dec":           8.0,
        "headgear":         "",
        "headgear_run":     "",
        "wind_surgery_run": "",
        "prev_trainers":    [],
    }

    all_runners = [runner_a, runner_b, runner_c]

    # Score all three
    for runner in all_runners:
        explanation = _explain(runner, race, all_runners, full_form_blob)
        print(explanation)

    # Verify import contract
    score, reasons = score_racing_wisdom(runner_a, race, all_runners, full_form_blob)
    assert isinstance(score, float), "score must be float"
    assert isinstance(reasons, list), "reasons must be list"
    assert WISDOM_MIN <= score <= WISDOM_MAX, f"score {score} out of range [{WISDOM_MIN}, {WISDOM_MAX}]"
    assert len(reasons) > 0, "strong profile should generate at least one reason"
    print(f"Contract assertions passed: score={score:+.1f}, {len(reasons)} reasons")

    # Test with zero data (graceful degradation)
    empty_runner = {"horse_id": "X999", "horse": "Ghost"}
    score_empty, reasons_empty = score_racing_wisdom(empty_runner, {}, [], None)
    assert isinstance(score_empty, float)
    assert WISDOM_MIN <= score_empty <= WISDOM_MAX
    print(f"Empty-data test passed: score={score_empty:+.1f} (should be 0.0)")

    # Test negative profile (persistent loser, bad narrative, cold trainer returning)
    runner_neg = {
        "horse_id":         "D004",
        "horse":            "NeverWins",
        "form":             "5-456677",
        "last_run":         90,
        "rpr":              95,
        "lbs":              135,
        "weight_lbs":       135,
        "trainer_14_days":  {"wins": 0, "runs": 20, "percent": "5"},
        "spotlight":        "disappointing and weak effort, needs better conditions",
        "comment":          "doubt about ability, tired and poor",
        "quotes":           "",
        "stable_tour":      "",
        "odds":             [{"decimal": 20.0}],
        "sp_dec":           20.0,
        "headgear":         "",
        "headgear_run":     "",
        "wind_surgery_run": "",
        "prev_trainers":    [],
    }
    full_form_neg: list[dict] = [
        {"position": "5", "course": "Lingfield",  "distance_f": 8.0, "class": "4", "going": "Good", "lbs": 132},
        {"position": "6", "course": "Kempton",    "distance_f": 8.0, "class": "4", "going": "Good", "lbs": 133},
        {"position": "4", "course": "Wolverhampton","distance_f": 8.0, "class": "4", "going": "Standard", "lbs": 134},
        {"position": "7", "course": "Lingfield",  "distance_f": 8.0, "class": "5", "going": "Good", "lbs": 134},
        {"position": "6", "course": "Lingfield",  "distance_f": 8.0, "class": "5", "going": "Good", "lbs": 133},
    ]
    full_form_blob_neg = {"horses": {"D004": full_form_neg}}
    score_neg, reasons_neg = score_racing_wisdom(
        runner_neg, race, [runner_a, runner_b, runner_c, runner_neg], full_form_blob_neg
    )
    print(f"\nNegative profile horse '{runner_neg['horse']}': score={score_neg:+.1f}")
    for r in reasons_neg:
        print(f"  • {r}")
    assert score_neg < 0, f"negative profile should score negative, got {score_neg}"
    print("\nAll tests passed.")


if __name__ == "__main__":
    _run_tests()
