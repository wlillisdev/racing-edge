"""Conviction — how many of the LEARNED lenses align on a runner, mark-aware.

This session's hard lessons in one score. It REWARDS a well-in mark, proven course
form, the market sweet spot and the positive tells; it FLAGS the rising-mark penalty,
the unexposed improver-favourite (Loch Cuan / Who's Lope — beaten at short prices) and
the all-weather / big-field lottery. A nap is only CONFIDENT when the decisive lens —
the mark — was actually readable and nothing red-flags it. Otherwise it's a reasoned
lean, not a nap (a bad nap you don't eat). Pure.
"""

from __future__ import annotations

from dataclasses import dataclass

from racing_edge.domain.mark import mark_read
from racing_edge.domain.models import PastRun, Race, Runner
from racing_edge.domain.tells import match_tells


@dataclass(frozen=True)
class Conviction:
    aligned: tuple[str, ...]    # learned lenses that fired FOR it
    flags: tuple[str, ...]      # red flags AGAINST it
    mark_known: bool            # was the decisive lens (the mark) actually readable?

    @property
    def score(self) -> int:
        return len(self.aligned)

    @property
    def confident(self) -> bool:
        """A real nap: at least three lenses align, the MARK was read, nothing flags it."""
        return self.score >= 3 and self.mark_known and not self.flags


def _same_course(h: PastRun, race: Race) -> bool:
    return (bool(h.course and race.course)
            and h.course.strip().lower() == race.course.strip().lower())


def conviction(runner: Runner, race: Race, history: tuple[PastRun, ...],
               market_rank: int, field_size: int = 0) -> Conviction:
    aligned: list[str] = []
    flags: list[str] = []

    mr = mark_read(runner.official_rating, history)
    if mr.delta is not None:
        if mr.delta <= 0:
            aligned.append(f"well-in ({mr.verdict})")
        else:
            flags.append(f"raised {mr.verdict} since last win")

    course_wins = sum(1 for h in history if h.position == 1 and _same_course(h, race))
    if course_wins >= 2:
        aligned.append("proven course winner (depth)")
    elif course_wins == 1:
        aligned.append("course winner")

    if market_rank in (2, 3):
        aligned.append("market sweet spot (2nd/3rd fav)")

    for t in match_tells(runner, race, history):
        if "LOCAL MASTER" in t:
            aligned.append("local course master")
        elif "headgear" in t.lower():
            aligned.append("headgear key")
        elif "distrust" in t:
            flags.append("rising-mark trap")

    price = runner.odds.consensus
    # the profile that beat me twice — lightly raced, market leader, short price
    if len(history) <= 4 and market_rank == 1 and price and price <= 3.0:
        flags.append("improver-favourite (unexposed, short price)")
    if race.is_all_weather:
        flags.append("all-weather caution (#14)")
    if field_size >= 16:
        flags.append("big-field lottery")

    return Conviction(tuple(dict.fromkeys(aligned)), tuple(dict.fromkeys(flags)), mr.known)
