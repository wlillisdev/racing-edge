"""Raw Racing API JSON -> typed contracts. ONE home for normalisation.

The audit's biggest data finding: racecards had a normaliser but RESULTS had
none, so ~20 consumers each re-derived position / won / sp from raw dicts. Here
both are normalised once. Jumps non-finisher codes (F, PU, UR, RO, BD...) are
parsed to position=None + a status, never a crashing int().

Pure: dict in, dataclass out. No network, no DB.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from racing_edge.domain.models import Odds, PastRun, Race, RaceResult, Runner, RunnerResult

_CLASS_RE = re.compile(r"class\s*(\d)", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# coercions — one set, replacing the 3-5 drifted copies the audit found
# --------------------------------------------------------------------------- #
def _str(v: Any, default: str = "") -> str:
    return str(v).strip() if v is not None else default


def _class(raw: dict) -> int | None:
    """Race class, robust to the shapes the API actually sends: a plain number, a
    'Class 4' / 'C4' string, or — failing that — dug out of the race name. The old
    `_int(raw.get('class'))` returned None on 'Class 4', so the card showed 'Class ?'."""
    for key in ("class", "race_class"):
        v = raw.get(key)
        n = _int(v)
        if n:
            return n
        if isinstance(v, str):
            m = re.search(r"\d+", v)
            if m:
                return int(m.group())
    m = _CLASS_RE.search(_str(raw.get("race_name")))
    return int(m.group(1)) if m else None


def _int(v: Any) -> int | None:
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None


def _float(v: Any) -> float | None:
    try:
        f = float(str(v).strip())
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _date(v: Any) -> date | None:
    s = _str(v)[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# position: "1" -> 1 ; "F"/"PU"/"UR" -> (None, "F"/"PU"/"UR")
# --------------------------------------------------------------------------- #
def _position(raw: Any) -> tuple[int | None, str]:
    s = _str(raw).upper()
    if s.isdigit():
        return int(s), ""
    return None, s  # faller / pulled-up / unseated / refused / brought-down / void


# --------------------------------------------------------------------------- #
# odds
# --------------------------------------------------------------------------- #
def _odds(raw_odds: Any) -> Odds:
    decs: list[float] = []
    for o in raw_odds or []:
        d = _float(o.get("decimal") if isinstance(o, dict) else o)
        if d and d > 1.0:
            decs.append(d)
    # The price a punter actually TAKES is the BEST available, not the median —
    # recording the median understated every pick's price and biased CLV down.
    best = round(max(decs), 2) if decs else None
    return Odds(morning=best, consensus=best)


def _headgear_first_time(raw: dict) -> bool:
    # Only headgear_run == "1" is genuinely first-time; "0"/"" mean not-wearing /
    # unknown and must NOT fire (the old check over-fired on every blank).
    return bool(_str(raw.get("headgear"))) and _str(raw.get("headgear_run")) == "1"


# --------------------------------------------------------------------------- #
# runner / race
# --------------------------------------------------------------------------- #
def runner_from_raw(raw: dict) -> Runner:
    tw = raw.get("trainer_14_days") if isinstance(raw.get("trainer_14_days"), dict) else {}
    return Runner(
        trainer_14d_runs=_int(tw.get("runs")),
        trainer_14d_wins=_int(tw.get("wins")),
        horse_id=_str(raw.get("horse_id")),
        horse=_str(raw.get("horse")),
        trainer=_str(raw.get("trainer")),
        trainer_id=_str(raw.get("trainer_id")),
        trainer_location=_str(raw.get("trainer_location")),
        jockey=_str(raw.get("jockey")),
        jockey_id=_str(raw.get("jockey_id")),
        claim_lbs=_int(raw.get("claim")),
        age=_int(raw.get("age")),
        sex=_str(raw.get("sex")),
        weight_lbs=_int(raw.get("lbs")),
        official_rating=_int(raw.get("ofr")),
        rpr=_int(raw.get("rpr")),
        form=_str(raw.get("form")),
        days_since_run=_int(raw.get("last_run")),
        headgear=_str(raw.get("headgear")),
        headgear_first_time=_headgear_first_time(raw),
        wind_surgery=_str(raw.get("wind_surgery")),
        draw=_int(raw.get("draw")),
        sire=_str(raw.get("sire")), sire_id=_str(raw.get("sire_id")),
        dam=_str(raw.get("dam")), dam_id=_str(raw.get("dam_id")),
        damsire=_str(raw.get("damsire")), damsire_id=_str(raw.get("damsire_id")),
        odds=_odds(raw.get("odds")),
        spotlight=_str(raw.get("spotlight")),
    )


def race_from_raw(raw: dict, race_date: date) -> Race:
    name = f"{raw.get('race_name', '')} {raw.get('type', '')}".lower()
    surface = f"{_str(raw.get('surface'))} {_str(raw.get('going'))}".lower()
    _aw = ("polytrack", "tapeta", "fibresand", "all weather", "all-weather", "standard")
    all_weather = any(k in surface for k in _aw)
    return Race(
        race_id=_str(raw.get("race_id")),
        course=_str(raw.get("course")),
        off_time=_str(raw.get("off_time")),
        date=race_date,
        race_type=_str(raw.get("type")),
        is_handicap=any(k in name for k in ("handicap", "hcap", "h'cap", "nursery")),
        is_novice=any(k in name for k in ("novice", "maiden", "nh flat", "bumper", "junior")),
        is_amateur="amateur" in name,   # inexperienced riders — anything can happen, avoid
        is_all_weather=all_weather,
        race_class=_class(raw),
        distance_f=_float(raw.get("distance_f") or raw.get("dist_f")),
        going=_str(raw.get("going")),
        going_detailed=_str(raw.get("going_detailed")),
        region=_str(raw.get("region")),
        runners=tuple(runner_from_raw(r) for r in (raw.get("runners") or [])),
    )


def racecards_from_raw(doc: dict) -> list[Race]:
    races = doc.get("racecards") or doc.get("races") or []
    out: list[Race] = []
    for raw in races:
        d = _date(raw.get("date")) or date.today()
        out.append(race_from_raw(raw, d))
    return out


# --------------------------------------------------------------------------- #
# results — the normaliser the old code never had
# --------------------------------------------------------------------------- #
def runner_result_from_raw(raw: dict) -> RunnerResult:
    pos, status = _position(raw.get("position"))
    return RunnerResult(
        horse_id=_str(raw.get("horse_id")),
        position=pos,
        status=status,
        sp_dec=_float(raw.get("sp_dec") or raw.get("sp")),
        bsp=_float(raw.get("bsp")),
        # ovr_btn = total lengths behind the WINNER (cumulative); btn = to the horse
        # in front (incremental). For "how close was the finish" we want cumulative.
        beaten_lengths=_float(raw.get("ovr_btn") or raw.get("btn") or raw.get("beaten_lengths")),
        horse=_str(raw.get("horse")),
        comment=_str(raw.get("comment") or raw.get("in_running_comment")),
    )


def results_from_raw(doc: dict) -> list[RaceResult]:
    out: list[RaceResult] = []
    for race in doc.get("results") or []:
        rd = _date(race.get("date")) or date.today()
        out.append(RaceResult(
            race_id=_str(race.get("race_id")),
            date=rd,
            runners=tuple(runner_result_from_raw(r) for r in (race.get("runners") or [])),
        ))
    return out


# --------------------------------------------------------------------------- #
# a horse's past runs (from get_horse_results) -> PastRun, for the proven reads
# --------------------------------------------------------------------------- #
def _dist_f(r: dict) -> float | None:
    """Distance in furlongs, robust to BOTH results doors (2026-08-01): the Pro
    endpoint sends a number, the racecards door sends '5f' strings — which
    _float rejected, silently blinding the trip lens. Falls back to yards/220."""
    v = r.get("dist_f") or r.get("distance_f")
    f = _float(v)
    if f:
        return f
    if isinstance(v, str):
        m = re.match(r"(\d+(?:\.\d+)?)f", v.strip())
        if m:
            return float(m.group(1))
    y = _float(r.get("dist_y"))
    return round(y / 220.0, 1) if y else None


def past_runs_from_raw(rows: list[dict], horse_id: str = "") -> tuple[PastRun, ...]:
    """horse_results rows are RACE objects with a nested `runners` list — the
    horse's own position/weight live in there, keyed by horse_id. Pass horse_id to
    dig them out. (Falls back to flat top-level fields when there's no runners list,
    so older/test shapes still parse.)"""
    out: list[PastRun] = []
    for r in rows or []:
        runners = r.get("runners")
        me = next((x for x in runners if _str(x.get("horse_id")) == horse_id), {}) \
            if (horse_id and isinstance(runners, list)) else r
        pos, _status = _position(me.get("position"))
        out.append(PastRun(
            date=_date(r.get("date")) or date.today(),
            position=pos,
            race_class=_class(r),
            going=_str(r.get("going")),
            distance_f=_dist_f(r),
            weight_lbs=_int(me.get("weight_lbs") or me.get("lbs")),
            official_rating=_int(me.get("or") or me.get("ofr") or me.get("official_rating")),
            course=_str(r.get("course")),
            race_type=_str(r.get("type")),
            field_size=_int(r.get("ran") or r.get("field_size"))
            or (len(runners) if isinstance(runners, list) else None),
            race_id=_str(r.get("race_id")),
            # HOW it ran — the in-running comment lives on the horse's own row (nested
            # runners) or the race row. The single richest 'what did I miss' signal;
            # the old normaliser dropped it. Empty stays empty (OWED), never invented.
            comment=_str(me.get("comment") or me.get("in_running_comment")
                         or r.get("comment")),
        ))
    return tuple(out)
