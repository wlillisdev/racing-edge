"""Assemble one runner's case from every signal in the method. Pure.

`RunnerEvidence` is the bundle the data layer assembles per runner (the racecard
runner, its past runs, and the external bits — stable form, stable jockeys,
combo record, franked count). `assess()` runs the whole method over it and
returns a transparent Case: the named signals, a ranking score (sum of weights),
and the veto decision (an exposed non-winner is left UNLESS it's dropping class).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from racing_edge.domain.form import bottler, improving
from racing_edge.domain.intent import (
    first_time_headgear,
    form_franked,
    jockey_intent,
    jockey_trainer_combo,
    market_move,
    stable_in_form,
    stable_value,
)
from racing_edge.domain.market import market_stance
from racing_edge.domain.models import PastRun, Race, Runner
from racing_edge.domain.profile import (
    claimer_allowance,
    class_ceiling,
    class_drop,
    course_proven,
    going_proven,
    quality_of_win,
    topped_out,
    trip_proven,
    weight_relief,
    well_in_and_proven,
)
from racing_edge.domain.signal import Signal

# Signals whose presence forgives a veto (the owner's one let-off: a genuine drop).
_LET_OFFS = frozenset({"class_drop"})


@dataclass(frozen=True)
class RunnerEvidence:
    runner: Runner
    history: tuple[PastRun, ...] = ()
    stable_runs: int = 0
    stable_wins: int = 0
    stable_ae: float | None = None       # the yard's Actual/Expected — value, not just form
    stable_ae_runs: int = 0
    stable_jockey_ids: frozenset[str] = field(default_factory=frozenset)
    combo_rides: int = 0
    combo_wins: int = 0
    franked_count: int = 0


@dataclass(frozen=True)
class Case:
    runner: Runner
    signals: tuple[Signal, ...]
    score: float
    vetoed: bool
    stance: str = ""        # Benter: are we WITH or AGAINST the market here?

    @property
    def reasons(self) -> list[str]:
        return [s.reason for s in self.signals]


def assess(ev: RunnerEvidence, race: Race) -> Case:
    r, h = ev.runner, ev.history
    candidates: list[Signal | None] = [
        # horse form
        improving(r.form), bottler(r.form),
        # class / proven at the level
        well_in_and_proven(r, race, h), class_drop(race, h), class_ceiling(race, h),
        topped_out(race, h), quality_of_win(h),
        # suitability
        going_proven(race, h), trip_proven(race, h), course_proven(race, h),
        # weight
        weight_relief(r, h), claimer_allowance(r),
        # intent
        stable_in_form(ev.stable_runs, ev.stable_wins),
        stable_value(ev.stable_ae, ev.stable_ae_runs), first_time_headgear(r),
        form_franked(ev.franked_count), jockey_intent(r, race, ev.stable_jockey_ids),
        jockey_trainer_combo(ev.combo_rides, ev.combo_wins), market_move(r.odds),
    ]
    signals = tuple(s for s in candidates if s is not None)
    has_let_off = any(s.name in _LET_OFFS for s in signals)
    vetoed = any(s.veto for s in signals) and not has_let_off
    score = round(sum(s.weight for s in signals), 1)
    return Case(runner=r, signals=signals, score=score, vetoed=vetoed,
                stance=market_stance(r, race))
