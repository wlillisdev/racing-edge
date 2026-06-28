"""My own nuance — the tells I learn from watching results, not the rules I was given.

The notebook holds the master's rules. THIS holds the patterns I earn myself: "a
horse like X, in a race like Y, did Z — so next time I see it, expect Z." Each tell
is a named pattern with a matcher over the data we have at pick time, so the card
flags it on a live runner. Earned from real results, dated to the race that taught it.

A tell is a lead, not a law. It carries the case it came from so it can be argued
with — and, in time, tested against how often it actually holds.

Pure: a runner + its race + its history in, the tells it matches out.
"""

from __future__ import annotations

from collections.abc import Callable

from racing_edge.domain.models import PastRun, Race, Runner
from racing_edge.domain.units import going_band


def _won(h: PastRun) -> bool:
    return h.position == 1


def _same_course(h: PastRun, race: Race) -> bool:
    return (bool(h.course and race.course)
            and h.course.strip().lower() == race.course.strip().lower())


def _same_going(h: PastRun, race: Race) -> bool:
    target = race.going_detailed or race.going
    return bool(h.going and target) and going_band(h.going) == going_band(target)


def _same_trip(h: PastRun, race: Race) -> bool:
    return bool(h.distance_f and race.distance_f) and abs(h.distance_f - race.distance_f) <= 1.0


# --------------------------------------------------------------------------- #
# the tells (each: runner, race, history -> a note if it fires, else None)
# --------------------------------------------------------------------------- #
def _cdg_winner_returning(runner: Runner, race: Race, history: tuple[PastRun, ...]) -> str | None:
    """Kingofthegame, 28 Jun: a course-AND-distance-AND-going winner, back at those
    exact conditions, beat a flashier 'improver' we'd wrongly preferred. When the
    proof is on the exact conditions, trust it over pretty recent figures."""
    if any(_won(h) and _same_course(h, race) and _same_going(h, race) and _same_trip(h, race)
           for h in history):
        return ("TELL — course/distance/going winner back at today's exact conditions "
                "(Kingofthegame, 28 Jun): prefer it to a flashier 'improver'")
    return None


def _hat_trick_trap(runner: Runner, race: Race, history: tuple[PastRun, ...]) -> str | None:
    """Halfway House Lad, 28 Jun: won its last two (so a RISING mark), sent off short,
    pulled up in a chase. Peak-form + no value + completion risk = a trap, not a NAP."""
    won_last_two = len(history) >= 2 and _won(history[0]) and _won(history[1])
    price = runner.odds.consensus
    if won_last_two and price and price <= 3.0:
        risk = " in a chase (completion risk)" if "chase" in race.race_type.lower() else ""
        return (f"TELL — won its last two off a rising mark at a short price{risk} "
                "(Halfway House Lad, 28 Jun): peak-form, no value — distrust as a banker")
    return None


def _headgear_key(runner: Runner, race: Race, history: tuple[PastRun, ...]) -> str | None:
    """King Of Earth, 28 Jun — and 10% of winners across the 101-race study DB: a
    first-time-headgear runner from a yard in form. The trainer has found the key and
    is making the change for a reason; respect it. (A real prior, not a one-day fluke.)"""
    runs = runner.trainer_14d_runs or 0
    wins = runner.trainer_14d_wins or 0
    in_form = runs >= 4 and (wins / runs) >= 0.15
    if runner.headgear_first_time and in_form:
        return ("TELL — first-time headgear from an in-form yard (King Of Earth, 28 Jun): "
                "the trainer's found the key — respect the change")
    return None


_TELLS: tuple[Callable[[Runner, Race, tuple[PastRun, ...]], str | None], ...] = (
    _cdg_winner_returning,
    _hat_trick_trap,
    _headgear_key,
)


def match_tells(runner: Runner, race: Race, history: tuple[PastRun, ...]) -> tuple[str, ...]:
    """The tells this runner trips, in the conditions of this race. Empty when none —
    the library is young; it grows as results teach me more."""
    return tuple(note for tell in _TELLS if (note := tell(runner, race, history)) is not None)
