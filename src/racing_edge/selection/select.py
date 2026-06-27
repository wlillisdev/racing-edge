"""Pick a race — or pass. Pure.

The pick is the horse with the strongest stack of reasons that isn't vetoed.
Selection answers "which horse does the method like best"; it does NOT decide
whether the price is bettable — that's the betting layer's job, so a genuine
short-priced winner is never buried by a value penalty here. No-bet is a valid,
common answer (every runner vetoed, or nothing with a positive case).
"""

from __future__ import annotations

from dataclasses import dataclass

from racing_edge.domain.models import Race
from racing_edge.selection.case import Case, RunnerEvidence, assess


@dataclass(frozen=True)
class RacePick:
    race: Race
    pick: Case | None                 # None = the method passes this race
    ranked: tuple[Case, ...] = ()     # all live cases, strongest first (for transparency)

    @property
    def is_bet(self) -> bool:
        return self.pick is not None


def pick_race(race: Race, evidence: list[RunnerEvidence]) -> RacePick:
    cases = [assess(ev, race) for ev in evidence]
    live = sorted(
        (c for c in cases if not c.vetoed and c.score > 0),
        key=lambda c: -c.score,
    )
    return RacePick(race=race, pick=(live[0] if live else None), ranked=tuple(live))
