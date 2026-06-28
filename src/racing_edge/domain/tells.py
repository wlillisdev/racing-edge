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

from racing_edge.domain.mark import mark_read
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
    exact conditions, beat a flashier 'improver'. Refined by the Friday miss
    (Caughtinyourtrance, 26 Jun): "won over c/d" is NOT a yes/no — DEPTH matters. A
    facile/repeat course winner beats a one-time one, and I read the tell on a raider
    that had merely got off the mark while a PROVEN course specialist beat us. Also
    weigh the MARK (well-in beats a penalty) — a check the data can't fully do yet."""
    cdg = any(_won(h) and _same_course(h, race) and _same_going(h, race) and _same_trip(h, race)
              for h in history)
    if not cdg:
        return None
    course_wins = sum(1 for h in history if _won(h) and _same_course(h, race))
    depth = "PROVEN/repeat" if course_wins >= 2 else "one-time"
    return (f"TELL — course/distance/going winner ({depth}) back at today's exact conditions "
            "(Kingofthegame): prefer it to an improver — weigh DEPTH of course form and the MARK")


def _hat_trick_trap(runner: Runner, race: Race, history: tuple[PastRun, ...]) -> str | None:
    """Halfway House Lad, 28 Jun: won its last two (so a RISING mark), sent off short,
    pulled up in a chase. Peak-form + no value + completion risk = a trap, not a NAP."""
    won_last_two = len(history) >= 2 and _won(history[0]) and _won(history[1])
    price = runner.odds.consensus
    if not (won_last_two and price and price <= 3.0):
        return None
    # the trap is an EXPOSED horse RAISED by the handicapper. If the mark shows it's
    # actually WELL-IN (won twice but still off no higher a mark), it's ahead of the
    # assessor, NOT a trap — spare it. (The Friday lesson, now with the data to apply it.)
    mr = mark_read(runner.official_rating, history)
    if mr.delta is not None and mr.delta <= 0:
        return None
    risk = " in a chase (completion risk)" if "chase" in race.race_type.lower() else ""
    up = f" (mark {mr.verdict})" if mr.delta is not None else ""
    return (f"TELL — won its last two off a rising mark{up} at a short price{risk} "
            "(Halfway House Lad, 28 Jun): peak-form, no value — distrust as a banker")


def _headgear_key(runner: Runner, race: Race, history: tuple[PastRun, ...]) -> str | None:
    """King Of Earth, 28 Jun — and 10% of winners across the 101-race study DB: a
    first-time-headgear runner from a yard in form. The trainer has found the key and
    is making the change for a reason; respect it. (A real prior, not a one-day fluke.)"""
    runs = runner.trainer_14d_runs or 0
    wins = runner.trainer_14d_wins or 0
    in_form = runs >= 4 and (wins / runs) >= 0.15
    if runner.headgear_first_time and in_form:
        return ("TELL — first-time headgear from an in-form yard (King Of Earth, 28 Jun): "
                "gear focuses a horse that raced too freely / hung / jumped right — "
                "expect it to settle, run straighter and find more")
    return None


# Course specialists — local masters who school at a quirky track and beat raiders'
# figures there (notebook #10). Seeded from results; grows as I learn each track's yard.
_COURSE_MASTERS: dict[str, tuple[str, ...]] = {
    "cartmel": ("moffatt",),   # James Moffatt — 7x Cartmel champion
}


def _local_course_master(runner: Runner, race: Race, history: tuple[PastRun, ...]) -> str | None:
    """Caughtinyourtrance / James Moffatt, Cartmel 26 Jun: I napped an Irish raider on
    course/distance figures and the LOCAL master (7x course champion) beat me at 7/4.
    Rule #10 — a yard that schools at a quirky track trumps a raider's figures. This
    OVERRULES the course/distance tell at the specialist track; raise the guard."""
    masters = _COURSE_MASTERS.get(race.course.strip().lower(), ())
    trainer = (runner.trainer or "").lower()
    if masters and any(m in trainer for m in masters):
        return ("TELL — the LOCAL MASTER at this quirky track (Caughtinyourtrance/Moffatt, "
                "Cartmel 26 Jun): a yard that schools here trumps a raider's figures (rule #10)")
    return None


def _well_in(runner: Runner, race: Race, history: tuple[PastRun, ...]) -> str | None:
    """Caughtinyourtrance, 26 Jun: "on a mark it's capable of winning off". A horse
    running off the SAME or a LOWER mark than when it last won is well-in — the
    handicapper hasn't caught it. The positive mirror of the rising-mark trap, and the
    decisive lens I failed to compare on Friday."""
    mr = mark_read(runner.official_rating, history)
    if mr.delta is not None and mr.delta <= 0:
        return (f"TELL — WELL-IN ({mr.verdict}): running off no higher a mark than when it last "
                "won — the handicapper hasn't caught it (Caughtinyourtrance, 26 Jun)")
    return None


_TELLS: tuple[Callable[[Runner, Race, tuple[PastRun, ...]], str | None], ...] = (
    _cdg_winner_returning,
    _hat_trick_trap,
    _headgear_key,
    _local_course_master,
    _well_in,
)


def match_tells(runner: Runner, race: Race, history: tuple[PastRun, ...]) -> tuple[str, ...]:
    """The tells this runner trips, in the conditions of this race. Empty when none —
    the library is young; it grows as results teach me more."""
    return tuple(note for tell in _TELLS if (note := tell(runner, race, history)) is not None)
