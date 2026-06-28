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


_TELLS: tuple[Callable[[Runner, Race, tuple[PastRun, ...]], str | None], ...] = (
    _cdg_winner_returning,
    _hat_trick_trap,
)


def match_tells(runner: Runner, race: Race, history: tuple[PastRun, ...]) -> tuple[str, ...]:
    """The tells this runner trips, in the conditions of this race. Empty when none —
    the library is young; it grows as results teach me more."""
    return tuple(note for tell in _TELLS if (note := tell(runner, race, history)) is not None)
