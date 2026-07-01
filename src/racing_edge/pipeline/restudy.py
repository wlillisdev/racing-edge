"""Gather finished readable handicaps with their FULL form — shared by restudy + learn.

Pulls the racecard (form, OR, spotlight, headgear), the result (finish, SP), and every
runner's history WITH in-running comments, for the readable handicaps that have a result
and match the focus filters. Slow by design (one history fetch per runner), so `--time`
focuses one race. The reads consume this; it is where the window is opened, honestly.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from racing_edge.data.normalise import (
    past_runs_from_raw,
    racecards_from_raw,
    results_from_raw,
)
from racing_edge.domain.models import PastRun, Race, RaceResult


class _Client:
    def racecards(self, day: str = "today") -> dict: ...
    def results_by_date(self, date_str: str) -> dict: ...
    def horse_results(self, horse_id: str, limit: int = 12) -> list[dict]: ...


@dataclass(frozen=True)
class Restudy:
    race: Race
    result: RaceResult
    histories: dict[str, tuple[PastRun, ...]]

    @property
    def winner(self) -> str:
        w = next((rr for rr in self.result.runners if rr.position == 1), None)
        if not w:
            return "?"
        named = next((r.horse for r in self.race.runners if r.horse_id == w.horse_id), "")
        return named or w.horse or "?"


def gather(client: _Client, day_iso: str, course: str | None = None,
           time: str | None = None, progress: Callable[[str], None] | None = None) -> list[Restudy]:
    results = {r.race_id: r for r in results_from_raw(client.results_by_date(day_iso))}
    cards = racecards_from_raw(client.racecards(day_iso))

    def _match(c: Race) -> bool:
        if not c.is_readable_handicap or c.race_id not in results:
            return False
        if course and course.lower() not in c.course.lower():
            return False
        return not (time and time not in c.off_time)

    races = [c for c in cards if _match(c)]
    if progress:
        progress(f"  re-studying {len(races)} finished race(s) off the full form "
                 f"(one history fetch per runner; --time focuses one)…")
    out: list[Restudy] = []
    for race in races:
        if progress:
            progress(f"    · {race.course} {race.off_time} — pulling "
                     f"{race.field_size} runners' history")
        # NO LOOK-AHEAD: history stops STRICTLY BEFORE the race being studied. The API
        # returns the horse's runs INCLUDING today's — leave that in and the winner
        # always reads WELL-IN off its own win (the leak behind the binned nuance #1).
        # Re-study must read the form as it stood BEFORE the off.
        histories = {
            r.horse_id: tuple(
                h for h in past_runs_from_raw(client.horse_results(r.horse_id), r.horse_id)
                if h.date < race.date
            )
            for r in race.runners if r.horse_id
        }
        out.append(Restudy(race=race, result=results[race.race_id], histories=histories))
    return out
