"""History-based handicapping reads — the heart of the method. Pure.

Each read takes the runner, today's race, and the horse's past runs, and returns
a Signal with a plain-English reason. Together these are the owner's eye:

  • well_in_and_proven  — carrying less than last time AND has won at the level
                          ("well in and ahead of his mark") — the strongest read
  • class_drop          — won at a higher grade than today (proven better)
  • class_ceiling       — exposed at the level, no win (a leave-it, unless dropping)
  • topped_out          — only won below today's class (up in grade)
  • going_proven        — handles today's ground (won on it) / wrong on it
  • trip_proven         — stays today's trip (won around it)
  • course_proven       — a winner at the track
  • weight_relief       — the handicapper has been kind vs last run
"""

from __future__ import annotations

from racing_edge.domain.models import PastRun, Race, Runner
from racing_edge.domain.signal import Signal
from racing_edge.domain.units import going_band


def _last_weight(history: tuple[PastRun, ...]) -> int | None:
    for h in sorted(history, key=lambda r: r.date, reverse=True):
        if h.weight_lbs is not None:
            return h.weight_lbs
    return None


def _won_at_level(race: Race, history: tuple[PastRun, ...]) -> bool:
    """Won at today's class or a HIGHER grade (lower class number = higher grade)."""
    return any(
        h.won and h.race_class is not None and race.race_class is not None
        and h.race_class <= race.race_class
        for h in history
    )


def well_in_and_proven(runner: Runner, race: Race, history: tuple[PastRun, ...]) -> Signal | None:
    if not history or race.race_class is None or not _won_at_level(race, history):
        return None
    last = _last_weight(history)
    if runner.weight_lbs is not None and last is not None:
        wv = runner.weight_lbs - last
        if wv <= -2:
            return Signal("well_in_proven", 5.0,
                          f"{abs(wv)}lb lower than last time AND won at this level — "
                          f"well in and ahead of the mark")
    return Signal("proven_at_level", 3.0, "Has won at this class or higher")


def class_drop(race: Race, history: tuple[PastRun, ...]) -> Signal | None:
    if race.race_class is None:
        return None
    higher_wins = [h.race_class for h in history
                   if h.won and h.race_class is not None and h.race_class < race.race_class]
    if higher_wins:
        return Signal("class_drop", 4.0,
                      f"Won in Class {min(higher_wins)} — drops to Class {race.race_class}, "
                      f"proven better than these")
    return None


def class_ceiling(race: Race, history: tuple[PastRun, ...]) -> Signal | None:
    if race.race_class is None:
        return None
    at_level = [h for h in history
                if h.race_class is not None and h.race_class <= race.race_class]
    if len(at_level) >= 3 and not any(h.won for h in at_level):
        return Signal("class_ceiling", -4.0,
                      f"{len(at_level)} runs at this level or higher, no win — class ceiling",
                      veto=True)
    return None


def topped_out(race: Race, history: tuple[PastRun, ...]) -> Signal | None:
    if race.race_class is None:
        return None
    wins = [h for h in history if h.won and h.race_class is not None]
    if wins and all(h.race_class > race.race_class for h in wins):
        return Signal("topped_out", -4.0, "Only won below today's class — up in grade")
    return None


def going_proven(race: Race, history: tuple[PastRun, ...]) -> Signal | None:
    band = race.going_band
    if band == "unknown" or not history:
        return None
    on_band = [h for h in history if going_band(h.going) == band]
    wins = sum(1 for h in on_band if h.won)
    if wins >= 1:
        return Signal("ground_proven", 4.0,
                      f"Won on {band} ({wins} from {len(on_band)}) — handles the ground")
    if len(on_band) >= 4 and not any(h.placed or h.won for h in on_band):
        return Signal("ground_wrong", -4.0,
                      f"0 from {len(on_band)} on {band}, unplaced — ground looks wrong")
    return None


def trip_proven(race: Race, history: tuple[PastRun, ...], tol_f: float = 1.5) -> Signal | None:
    if race.distance_f is None or not history:
        return None
    near = [h for h in history
            if h.distance_f is not None and abs(h.distance_f - race.distance_f) <= tol_f]
    if any(h.won for h in near):
        return Signal("trip_proven", 3.0, f"Won around {race.distance_f:.0f}f — stays the trip")
    return None


def course_proven(race: Race, history: tuple[PastRun, ...]) -> Signal | None:
    if not race.course or not history:
        return None
    if any(h.won and h.course.lower() == race.course.lower() for h in history):
        return Signal("course_proven", 2.0, f"Course winner at {race.course}")
    return None


def quality_of_win(history: tuple[PastRun, ...]) -> Signal | None:
    """How good was the race it won? A win in a competitive, decent-class race is
    far stronger form than a soft win in a small weak field."""
    quality = [
        h for h in history
        if h.won and h.race_class is not None and h.race_class <= 4
        and (h.field_size or 0) >= 8
    ]
    if quality:
        best = min(quality, key=lambda h: h.race_class or 99)
        return Signal("quality_win", 2.0,
                      f"Won a competitive Class {best.race_class} ({best.field_size} ran) — strong form")
    return None


def claimer_allowance(runner: Runner) -> Signal | None:
    """A claiming/conditional jockey takes weight off the horse's back — a real
    edge on a well-handicapped horse where every pound counts (and often the
    yard getting in light on purpose)."""
    c = runner.claim_lbs
    if c and c >= 3:
        weight = 2.5 if c >= 5 else 1.5
        return Signal("claimer", weight,
                      f"{c}lb claimer — takes {c}lb off the back, in light at the weights")
    return None


def weight_relief(runner: Runner, history: tuple[PastRun, ...]) -> Signal | None:
    last = _last_weight(history)
    if runner.weight_lbs is None or last is None:
        return None
    wv = runner.weight_lbs - last
    if wv <= -3:
        return Signal("weight_relief", 2.0,
                      f"{abs(wv)}lb relief vs last run — the handicapper's been kind")
    return None
