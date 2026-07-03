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

BASELINE = 15.0  # so a mid-pack dog lands mid-scale, not near zero

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


def _score_early_pace(scores: list[RunnerScore]) -> None:
    """Rank best recent split within the field. First to the bend wins races."""
    best_splits = {s.trap: _best([r.get("split") for r in s.runs]) for s in scores}
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


def _score_time_form(scores: list[RunnerScore], distance: float | None) -> None:
    """Best recent calc time at tonight's distance, relative to field best.

    Roughly 0.08s per length; a dog 5+ lengths slower than the field's best
    recent time scores zero here.
    """
    zero_beyond = 0.40  # seconds
    best_times = {}
    for s in scores:
        at_trip = [
            r.get("calc_time")
            for r in s.runs
            if distance is None or r.get("distance") == distance
        ]
        best_times[s.trap] = _best(at_trip)
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


def _score_consistency(scores: list[RunnerScore]) -> None:
    for s in scores:
        recent = s.runs[:6]
        placed = sum(1 for r in recent if isinstance(r.get("pos"), int) and r["pos"] <= 2)
        s.components["consistency"] = round(W_CONSISTENCY * placed / max(len(recent), 1), 1)


def _pace_map(scores: list[RunnerScore]) -> dict:
    """Predicted order to the first bend + crowding flag."""
    splits = []
    for s in scores:
        b = _best([r.get("split") for r in s.runs])
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


def score_race(race: dict) -> dict:
    scores = [RunnerScore(r) for r in race.get("runners", [])]
    distance = race.get("distance")
    _score_early_pace(scores)
    _score_time_form(scores, distance)
    _score_trap_style(scores)
    _score_grade_edge(scores, race.get("grade"))
    _score_recency(scores)
    _score_consistency(scores)
    ranked = sorted(scores, key=lambda s: s.total, reverse=True)
    pace = _pace_map(scores)
    return {
        "race_no": race.get("race_no"),
        "time": race.get("time"),
        "grade": race.get("grade"),
        "distance": distance,
        "pace_map": pace,
        "no_bet": pace["crowding_risk"],
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
    return {
        "meeting": card.get("meeting", {}),
        "engine": "greyhound-v0-uncalibrated",
        "races": [score_race(r) for r in card["races"]],
    }


def _print_report(result: dict) -> None:
    meeting = result["meeting"]
    print(f"\n=== {meeting.get('track', '?')} — {meeting.get('date', '?')} ===")
    print(f"engine: {result['engine']} (bands NOT calibrated — log, don't stake)\n")
    for race in result["races"]:
        header = f"Race {race['race_no']} {race.get('time', '')} {race.get('grade', '')} {race.get('distance', '')}"
        print(header.strip())
        if race["no_bet"]:
            print("  ⚠ CROWDED EARLY PACE — treat as NO BET")
        for r in race["runners"]:
            flags = f"  [{'; '.join(r['flags'])}]" if r["flags"] else ""
            print(
                f"  {r['rank']}. T{r['trap']} {r['name']:<22} {r['score']:5.1f}"
                f"  (pace {r['components'].get('early_pace', 0):.0f}"
                f" time {r['components'].get('time_form', 0):.0f}"
                f" trap {r['components'].get('trap_style', 0):+.0f}"
                f" grade {r['components'].get('grade_edge', 0):+.0f}){flags}"
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
