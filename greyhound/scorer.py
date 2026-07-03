#!/usr/bin/env python3
"""Greyhound race scorer v0.

Scores a hand-entered racecard (see card_template.json) on a 0-100 scale.

The weights are UNCALIBRATED placeholders. The point of v0 is to produce
consistent, loggable scores so a real backtest can calibrate the bands
later — the same discipline that found the profitable 70-79 band on the
horse side. Do not derive stake rules from these numbers yet.

Usage:
    python greyhound/scorer.py path/to/card.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Component ranges (documented in README.md)
W_EARLY_PACE = 30.0
W_TIME_FORM = 30.0
W_TRAP_STYLE = 10.0   # -10 .. +10
W_GRADE_MAX = 15.0    # -10 .. +15
W_RECENCY_MAX = 5.0   # -10 .. +5
W_CONSISTENCY = 10.0
W_REMARKS = 8.0       # -8 .. +8, from race comments
W_RUN_LINE = 8.0      # 0 .. +8, from in-race positions
W_DRAW_BIAS = 5.0     # -5 .. +5, learned per track+distance from results log
W_TRIP = 6.0          # -6 .. +6, distance change read with the remarks
W_TRACK_AFF = 6.0     # 0 .. +6, record at tonight's track / raider intent
W_DRAW_RECORD = 5.0   # -5 .. +5, the dog's own record from draws like tonight's
W_NEAR_MISS = 6.0     # 0 .. +6, beaten a short distance = close to winning

# Draw zones for the per-dog draw record: inside, middle, wide
_ZONE = {1: "in", 2: "in", 3: "mid", 4: "mid", 5: "wide", 6: "wide"}

# Race-comment tokens (lowercased, spaces stripped before matching)
_TROUBLE = ("crd", "blk", "bmp", "ck", "imp")          # trouble = excuse
_FINISH_STRONG = ("stywl", "finwl", "rnon", "strfin", "drclr", "styon")
_FADED = ("fd", "wknd")
_QUICK_AWAY = ("qaw", "faw")
_SLOW_AWAY = ("slaw", "msdbrk")

# Recency weighting for per-run evidence: newest run counts most.
_RUN_WEIGHTS = (1.0, 0.8, 0.6, 0.4, 0.2)

# GRI conversion: one length ≈ 0.07s. EstTm on the card is
# win_time + 0.07 * lengths_beaten + printed going allowance (signed:
# "+.20 Fast" adds, "-.30 Slow" subtracts).
SECS_PER_LENGTH = 0.07


def _estimate_time(run: dict) -> float | None:
    """The card's EstTm formula, for when a card doesn't print it."""
    win = run.get("win_time")
    if not isinstance(win, (int, float)) or win <= 0:
        return None
    beaten = run.get("beaten_by") or 0.0
    allowance = run.get("going_allowance") or 0.0
    return round(win + SECS_PER_LENGTH * float(beaten) + float(allowance), 2)


def _calc_time(run: dict) -> float | None:
    """Prefer the printed estimated time; derive it if absent."""
    t = run.get("calc_time")
    if isinstance(t, (int, float)) and t > 0:
        return t
    return _estimate_time(run)

BASELINE = 15.0  # so a mid-pack dog lands mid-scale, not near zero

# Splits and times are only comparable at the same trip on the same track,
# and stale form is not current ability.
MAX_RUN_AGE_DAYS = 365

_GRADE_RE = re.compile(r"^([A-Za-z]+)\s*(\d+)$")


def _parse_grade(grade: str | None) -> tuple[str, int] | None:
    if not grade:
        return None
    m = _GRADE_RE.match(grade.strip())
    if not m:
        return None
    return m.group(1).upper(), int(m.group(2))


def _best(values: list[float]) -> float | None:
    vals = [v for v in values if isinstance(v, (int, float)) and v > 0]
    return min(vals) if vals else None


def _comparable(runs: list[dict], distance, track) -> list[dict]:
    """Runs whose split/time can be compared to tonight's race: same
    distance, same track (when both sides are known), not older than
    MAX_RUN_AGE_DAYS."""
    out = []
    for r in runs:
        age = r.get("days_ago")
        if isinstance(age, (int, float)) and age > MAX_RUN_AGE_DAYS:
            continue
        if distance is not None and r.get("distance") not in (None, distance):
            continue
        run_track = r.get("track")
        if track and run_track and str(run_track).upper() != str(track).upper():
            continue
        out.append(r)
    return out


class RunnerScore:
    def __init__(self, runner: dict):
        self.trap = runner.get("trap")
        self.name = runner.get("name", f"Trap {self.trap}")
        self.style = (runner.get("style") or "M").upper()[:1]
        self.runs = runner.get("recent_runs") or []
        self.components: dict[str, float] = {}
        self.flags: list[str] = []

    @property
    def total(self) -> float:
        raw = BASELINE + sum(self.components.values())
        return round(max(0.0, min(100.0, raw)), 1)


def _validate(card: dict) -> list[str]:
    """Refuse to score garbage — missing critical fields fail loudly."""
    problems = []
    races = card.get("races")
    if not isinstance(races, list) or not races:
        return ["card has no races[]"]
    for race in races:
        rno = race.get("race_no", "?")
        runners = race.get("runners")
        if not isinstance(runners, list) or len(runners) < 2:
            problems.append(f"race {rno}: fewer than 2 runners")
            continue
        for r in runners:
            if not r.get("trap"):
                problems.append(f"race {rno}: runner missing trap")
            if not r.get("recent_runs"):
                problems.append(
                    f"race {rno} trap {r.get('trap')}: no recent_runs — "
                    "cannot score a dog with no form"
                )
    return problems


def _score_early_pace(scores: list[RunnerScore], distance, track) -> None:
    """Rank best recent split within the field. First to the bend wins races."""
    best_splits = {
        s.trap: _best([r.get("split") for r in _comparable(s.runs, distance, track)])
        for s in scores
    }
    known = sorted(v for v in best_splits.values() if v is not None)
    for s in scores:
        split = best_splits[s.trap]
        if split is None or not known:
            s.components["early_pace"] = W_EARLY_PACE * 0.3  # unknown ≠ slow
            s.flags.append("no split data")
            continue
        # Linear on rank: field-fastest gets full marks.
        rank = known.index(split)
        span = max(len(known) - 1, 1)
        s.components["early_pace"] = round(W_EARLY_PACE * (1 - rank / span), 1)


def _score_time_form(scores: list[RunnerScore], distance, track) -> None:
    """Best recent calc time at tonight's distance/track, relative to field
    best.

    Roughly 0.08s per length; a dog 5+ lengths slower than the field's best
    recent time scores zero here.
    """
    zero_beyond = 0.40  # seconds
    best_times = {}
    for s in scores:
        at_trip = [_calc_time(r) for r in _comparable(s.runs, distance, track)]
        best_times[s.trap] = _best([t for t in at_trip if t is not None])
    field_best = _best([v for v in best_times.values() if v is not None])
    for s in scores:
        t = best_times[s.trap]
        if t is None or field_best is None:
            s.components["time_form"] = W_TIME_FORM * 0.3
            s.flags.append("no time at trip")
            continue
        deficit = t - field_best
        frac = max(0.0, 1.0 - deficit / zero_beyond)
        s.components["time_form"] = round(W_TIME_FORM * frac, 1)


# style -> trap -> modifier
_STYLE_TRAP = {
    "R": {1: 10, 2: 7, 3: 2, 4: -2, 5: -6, 6: -10},
    "M": {1: 2, 2: 3, 3: 4, 4: 4, 5: 3, 6: 2},
    "W": {1: -10, 2: -7, 3: -3, 4: 2, 5: 6, 6: 10},
}


def _score_trap_style(scores: list[RunnerScore]) -> None:
    for s in scores:
        table = _STYLE_TRAP.get(s.style, _STYLE_TRAP["M"])
        s.components["trap_style"] = float(table.get(s.trap, 0))


def _score_grade_edge(scores: list[RunnerScore], race_grade: str | None) -> None:
    """Dropping in grade meets weaker opposition; rising meets stronger."""
    tonight = _parse_grade(race_grade)
    for s in scores:
        if tonight is None:
            s.components["grade_edge"] = 0.0
            continue
        letter, num = tonight
        recents = [_parse_grade(r.get("grade")) for r in s.runs[:4]]
        same_code = [g for g in recents if g and g[0] == letter]
        if not same_code:
            s.components["grade_edge"] = 0.0
            s.flags.append("no comparable grade history")
            continue
        # positive = last runs were in HIGHER grade (lower number) than tonight
        diff = sum(num - g[1] for g in same_code) / len(same_code)
        s.components["grade_edge"] = round(max(-10.0, min(W_GRADE_MAX, diff * 7.5)), 1)


def _score_recency(scores: list[RunnerScore]) -> None:
    for s in scores:
        days = [r.get("days_ago") for r in s.runs if isinstance(r.get("days_ago"), (int, float))]
        if not days:
            s.components["recency"] = 0.0
            continue
        last = min(days)
        if 4 <= last <= 14:
            val = W_RECENCY_MAX
        elif last < 4:
            val = 2.0  # quick back-up: fit but slight bounce risk
        elif last <= 28:
            val = 0.0
        else:
            val = -10.0
            s.flags.append(f"absent {int(last)} days")
        s.components["recency"] = float(val)


def _score_remarks(scores: list[RunnerScore]) -> None:
    """Read the race comments the way a form student does.

    Trouble in running (Crd/Blk/Bmp/Ck) in a beaten run is an EXCUSE — the
    bare finishing position lies about the dog. Strong-finish comments
    (StyWl/FinWl/RnOn/DrClr) mark a dog that keeps finding; Fd marks one
    that empties. QAw/FAw is trap speed the splits sometimes miss.
    """
    for s in scores:
        val = 0.0
        for run, w in zip(s.runs, _RUN_WEIGHTS):
            comment = (run.get("comment") or "").lower().replace(" ", "")
            if not comment:
                continue
            pos = run.get("pos")
            if any(t in comment for t in _TROUBLE) and isinstance(pos, int) and pos >= 3:
                val += 1.5 * w  # beaten with an excuse — forgive the run
            if any(t in comment for t in _FINISH_STRONG):
                val += 1.5 * w
            if any(t in comment for t in _FADED):
                val -= 1.5 * w
            if any(t in comment for t in _QUICK_AWAY):
                val += 1.0 * w
            if any(t in comment for t in _SLOW_AWAY):
                val -= 1.0 * w
        s.components["remarks"] = round(max(-W_REMARKS, min(W_REMARKS, val)), 1)


def _score_run_line(scores: list[RunnerScore]) -> None:
    """In-race positions (e.g. '6544' finishing 2nd): half for early
    position taken, half for ground made through the race. A dog that
    passes dogs late is gold in a race with a messy first bend."""
    for s in scores:
        firsts, gains = [], []
        for run in s.runs[: len(_RUN_WEIGHTS)]:
            line = str(run.get("positions") or "").strip()
            if not line or not line[0].isdigit():
                continue
            first = int(line[0])
            firsts.append(first)
            pos = run.get("pos")
            if isinstance(pos, int):
                gains.append(first - pos)
        if not firsts:
            s.components["run_line"] = 0.0
            s.flags.append("no running lines")
            continue
        avg_first = sum(firsts) / len(firsts)
        early_pts = max(0.0, min(4.0, (3.5 - avg_first) / 2.5 * 4))
        avg_gain = sum(gains) / len(gains) if gains else 0.0
        gain_pts = max(0.0, min(4.0, avg_gain / 2.0 * 4))
        s.components["run_line"] = round(early_pts + gain_pts, 1)


def _score_trip_change(scores: list[RunnerScore], distance) -> None:
    """Distance move read together with the remarks.

    Dropping back in trip: a dog with genuine early dash gets first run
    and no longer has to get home — especially one that was FADING at the
    longer trip. But a dog that was staying on at the longer trip may find
    the shorter race over before it warms up.

    Stepping up in trip: strong finishers (RnOn/StyWl/Strfin) are bred
    for it; dogs already fading at the shorter trip are not.
    """
    if distance is None:
        for s in scores:
            s.components["trip_change"] = 0.0
        return
    for s in scores:
        recent = s.runs[: len(_RUN_WEIGHTS)]
        with_dist = [r for r in recent if isinstance(r.get("distance"), (int, float))]
        if not with_dist:
            s.components["trip_change"] = 0.0
            continue
        longer = [r for r in with_dist if r["distance"] > distance]
        shorter = [r for r in with_dist if r["distance"] < distance]

        def _has(runs, tokens):
            return any(
                t in (r.get("comment") or "").lower().replace(" ", "")
                for r in runs for t in tokens
            )

        def _good_early(runs):
            firsts = [
                int(str(r.get("positions"))[0])
                for r in runs
                if str(r.get("positions") or "")[:1].isdigit()
            ]
            quick = _has(runs, _QUICK_AWAY)
            return quick or (firsts and sum(firsts) / len(firsts) <= 2.5)

        val = 0.0
        if len(longer) >= len(with_dist) / 2 and longer:
            # dropping back in trip
            if _good_early(longer):
                val += 3.0  # early dash + shorter trip = gets home easily
            if _has(longer, _FADED):
                val += 2.0  # wasn't lasting the longer trip; this helps
            elif _has(longer, _FINISH_STRONG) and not _good_early(longer):
                val -= 2.0  # a stayer being pulled back to a speed test
        elif len(shorter) >= len(with_dist) / 2 and shorter:
            # stepping up in trip
            if _has(shorter, _FINISH_STRONG):
                val += 3.0  # was finishing best at the shorter trip
            if _has(shorter, _FADED):
                val -= 4.0  # couldn't even last the shorter trip
        s.components["trip_change"] = round(max(-W_TRIP, min(W_TRIP, val)), 1)


def _score_track_affinity(scores: list[RunnerScore], track) -> None:
    """The Trk column tells two stories.

    Track lovers: some dogs just go at this track — score their wins and
    places HERE, not anywhere.

    Raiders: a dog whose recent lines are all at an away track (e.g. a
    Kerry dog shipped up to Cork) has been travelled on purpose. Nobody
    puts a dog in the van for a day out — small credit and a loud flag.
    """
    for s in scores:
        if not track:
            s.components["track_aff"] = 0.0
            continue
        tonight = str(track).upper()
        here = [r for r in s.runs if str(r.get("track") or "").upper() == tonight]
        away = [r for r in s.runs if r.get("track") and str(r["track"]).upper() != tonight]
        if not here and away:
            s.components["track_aff"] = 2.0
            codes = "/".join(sorted({str(r["track"]).upper() for r in away}))
            s.flags.append(f"RAIDER from {codes} — travelled with intent")
            continue
        wins = sum(1 for r in here if r.get("pos") == 1)
        places = sum(1 for r in here if r.get("pos") == 2)
        s.components["track_aff"] = round(min(W_TRACK_AFF, 2.0 * wins + 1.0 * places), 1)


def _score_near_miss(scores: list[RunnerScore]) -> None:
    """The By column: how far was he beaten?

    A dog touched off by a head or half a length was a stride from
    winning. Extra credit when the near-miss came from a slow start
    (SlAw or back of the pack at the first bend) — he conceded the break
    and still nearly won; a level break today turns it around.
    """
    for s in scores:
        val = 0.0
        for run, w in zip(s.runs, _RUN_WEIGHTS):
            pos = run.get("pos")
            beaten = run.get("beaten_by")
            if not isinstance(pos, int) or pos < 2:
                continue
            if not isinstance(beaten, (int, float)):
                continue
            if beaten <= 0.5:
                credit = 2.5
            elif beaten <= 1.5:
                credit = 1.5
            elif beaten <= 3.0:
                credit = 0.5
            else:
                continue
            comment = (run.get("comment") or "").lower().replace(" ", "")
            line = str(run.get("positions") or "")
            slow_start = any(t in comment for t in _SLOW_AWAY) or (
                line[:1].isdigit() and int(line[0]) >= 4
            )
            if credit >= 1.5 and slow_start:
                credit += 1.0  # nearly won despite conceding the break
            val += credit * w
        s.components["near_miss"] = round(min(W_NEAR_MISS, val), 1)
        if s.components["near_miss"] >= 3:
            s.flags.append("near-misser — a better break wins")


def _score_draw_record(scores: list[RunnerScore]) -> None:
    """The Tp column: where was he drawn when he ran well?

    Independent of the printed seeding — a dog seeded M may have all his
    best runs from an inside draw. Compare the dog's record from
    tonight's draw zone (inside 1-2 / middle 3-4 / wide 5-6) against his
    record from elsewhere. Needs at least 2 runs in tonight's zone AND
    2 elsewhere, otherwise stays silent — no evidence, no opinion.
    """
    for s in scores:
        zone_tonight = _ZONE.get(s.trap)
        if zone_tonight is None:
            s.components["draw_record"] = 0.0
            continue
        in_zone, out_zone = [], []
        for run in s.runs:
            trap = run.get("trap")
            pos = run.get("pos")
            if not isinstance(trap, int) or not isinstance(pos, int):
                continue
            perf = 1.0 if pos <= 2 else (0.4 if pos <= 4 else 0.0)
            (in_zone if _ZONE.get(trap) == zone_tonight else out_zone).append(perf)
        if len(in_zone) < 2 or len(out_zone) < 2:
            s.components["draw_record"] = 0.0
            continue
        edge = sum(in_zone) / len(in_zone) - sum(out_zone) / len(out_zone)
        val = round(max(-W_DRAW_RECORD, min(W_DRAW_RECORD, edge * 8)), 1)
        s.components["draw_record"] = val
        if val >= 3:
            s.flags.append(f"runs well from {zone_tonight} draws")
        elif val <= -3:
            s.flags.append(f"poor record from {zone_tonight} draws")


def _load_track_bias() -> dict:
    path = Path(__file__).parent / "track_bias.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _score_draw_bias(scores: list[RunnerScore], distance, track, bias: dict) -> None:
    """Learned trap bias per track+distance from the results log. Silent
    (zero) until at least 30 logged races — never guess a bias."""
    stats = (bias.get(str(track or "").upper()) or {}).get(str(distance)) if bias else None
    n = (stats or {}).get("races", 0)
    if not stats or n < 30:
        for s in scores:
            s.components["draw_bias"] = 0.0
        return
    for s in scores:
        wins = stats.get(str(s.trap), 0)
        edge = wins / n - 1.0 / 6.0
        s.components["draw_bias"] = round(max(-W_DRAW_BIAS, min(W_DRAW_BIAS, edge * 30)), 1)


def _score_consistency(scores: list[RunnerScore]) -> None:
    for s in scores:
        recent = s.runs[:6]
        placed = sum(1 for r in recent if isinstance(r.get("pos"), int) and r["pos"] <= 2)
        s.components["consistency"] = round(W_CONSISTENCY * placed / max(len(recent), 1), 1)


def _pace_map(scores: list[RunnerScore], distance, track) -> dict:
    """Predicted order to the first bend + crowding flag."""
    splits = []
    for s in scores:
        b = _best([r.get("split") for r in _comparable(s.runs, distance, track)])
        if b is not None:
            splits.append((b, s.trap, s.name))
    splits.sort()
    order = [{"trap": t, "name": n, "best_split": sp} for sp, t, n in splits]
    # crowding: 3+ dogs within 0.10s of the fastest split, drawn adjacent
    if len(splits) >= 3:
        fast = splits[0][0]
        hot_traps = sorted(t for sp, t, _ in splits if sp - fast <= 0.10)
        adjacent = (
            len(hot_traps) >= 3
            and max(hot_traps) - min(hot_traps) <= len(hot_traps)
        )
    else:
        adjacent = False
    return {"bend_order": order, "crowding_risk": adjacent}


def _confidence(ranked: list[RunnerScore], crowded: bool) -> str:
    """Every race gets a call; this grades how much to trust it."""
    margin = ranked[0].total - ranked[1].total if len(ranked) > 1 else 99.0
    if margin >= 10:
        level = 2  # HIGH
    elif margin >= 4:
        level = 1  # MEDIUM
    else:
        level = 0  # LOW
    if crowded:
        level = max(0, level - 1)
    return ["LOW", "MEDIUM", "HIGH"][level]


def score_race(race: dict, track=None, bias: dict | None = None) -> dict:
    scores = [RunnerScore(r) for r in race.get("runners", [])]
    distance = race.get("distance")
    _score_early_pace(scores, distance, track)
    _score_time_form(scores, distance, track)
    _score_trap_style(scores)
    _score_grade_edge(scores, race.get("grade"))
    _score_recency(scores)
    _score_consistency(scores)
    _score_remarks(scores)
    _score_run_line(scores)
    _score_trip_change(scores, distance)
    _score_track_affinity(scores, track)
    _score_draw_record(scores)
    _score_near_miss(scores)
    _score_draw_bias(scores, distance, track, bias if bias is not None else _load_track_bias())
    # Tiebreak on the most predictive components, in order.
    ranked = sorted(
        scores,
        key=lambda s: (
            s.total,
            s.components.get("time_form", 0),
            s.components.get("early_pace", 0),
            s.components.get("consistency", 0),
        ),
        reverse=True,
    )
    pace = _pace_map(scores, distance, track)
    top = ranked[0]
    return {
        "race_no": race.get("race_no"),
        "time": race.get("time"),
        "grade": race.get("grade"),
        "distance": distance,
        "pace_map": pace,
        "selection": {
            "trap": top.trap,
            "name": top.name,
            "score": top.total,
            "confidence": _confidence(ranked, pace["crowding_risk"]),
        },
        "runners": [
            {
                "rank": i + 1,
                "trap": s.trap,
                "name": s.name,
                "style": s.style,
                "score": s.total,
                "components": s.components,
                "flags": s.flags,
            }
            for i, s in enumerate(ranked)
        ],
    }


def score_card(card: dict) -> dict:
    problems = _validate(card)
    if problems:
        raise ValueError("card failed validation:\n  " + "\n  ".join(problems))
    track = card.get("meeting", {}).get("track_code")
    bias = _load_track_bias()
    return {
        "meeting": card.get("meeting", {}),
        "engine": "greyhound-v0-uncalibrated",
        "races": [score_race(r, track, bias) for r in card["races"]],
    }


def _print_report(result: dict) -> None:
    meeting = result["meeting"]
    print(f"\n=== {meeting.get('track', '?')} — {meeting.get('date', '?')} ===")
    print(f"engine: {result['engine']} (bands NOT calibrated — log, don't stake)\n")
    for race in result["races"]:
        header = f"Race {race['race_no']} {race.get('time', '')} {race.get('grade', '')} {race.get('distance', '')}"
        print(header.strip())
        sel = race["selection"]
        print(f"  ★ SELECTION: T{sel['trap']} {sel['name']} ({sel['score']}) — confidence {sel['confidence']}")
        if race["pace_map"]["crowding_risk"]:
            print("  ⚠ crowded early pace — confidence downgraded, expect trouble at the bend")
        for r in race["runners"]:
            flags = f"  [{'; '.join(r['flags'])}]" if r["flags"] else ""
            print(
                f"  {r['rank']}. T{r['trap']} {r['name']:<22} {r['score']:5.1f}"
                f"  (pace {r['components'].get('early_pace', 0):.0f}"
                f" time {r['components'].get('time_form', 0):.0f}"
                f" trap {r['components'].get('trap_style', 0):+.0f}"
                f" grade {r['components'].get('grade_edge', 0):+.0f}"
                f" cmnt {r['components'].get('remarks', 0):+.1f}"
                f" line {r['components'].get('run_line', 0):+.1f}"
                f" trip {r['components'].get('trip_change', 0):+.1f}"
                f" trk {r['components'].get('track_aff', 0):+.1f}"
                f" drw {r['components'].get('draw_record', 0):+.1f}"
                f" miss {r['components'].get('near_miss', 0):+.1f}){flags}"
            )
        bend = ", ".join(f"T{o['trap']}" for o in race["pace_map"]["bend_order"][:3])
        if bend:
            print(f"  to the bend: {bend}")
        print()


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    path = Path(sys.argv[1])
    card = json.loads(path.read_text())
    try:
        result = score_card(card)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    out_path = path.with_name(path.stem + "_scored.json")
    out_path.write_text(json.dumps(result, indent=2))
    _print_report(result)
    print(f"written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
