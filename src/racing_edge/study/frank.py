"""Frank the form — the grunt work nobody does, done bounded.

Take a horse's most recent prior race, fetch that race's field, and check how many
of the rivals it ran against have WON or PLACED since. If several have, the form
line was solid — the horse beat (or was beaten by) animals that turned out useful.
That's franking, and it's the tiebreaker because it's pure legwork.

Bounded hard so it isn't a fetch-storm: only the most recent prior race, only the
first `cap` rivals, only run for the winner and our pick (the caller decides). The
counting is pure; the fetching is isolated behind the client protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from racing_edge.data.normalise import past_runs_from_raw, results_from_raw
from racing_edge.domain.models import PastRun


class _Fetcher(Protocol):
    def results_by_date(self, date_str: str) -> dict: ...
    def horse_results(self, horse_id: str, limit: int = 12) -> list[dict]: ...


@dataclass(frozen=True)
class Franking:
    last_race_date: date | None
    rivals_checked: int
    rivals_franked: int          # won or placed since that race
    note: str

    @property
    def is_franked(self) -> bool:
        return self.rivals_checked > 0 and self.rivals_franked >= 2


def _scored_since(runs: tuple[PastRun, ...], after: date) -> bool:
    """Did the horse win or place (top 3) in any run AFTER `after`?"""
    return any(r.date > after and r.position is not None and r.position <= 3 for r in runs)


def frank_form(client: _Fetcher, horse_id: str, history: tuple[PastRun, ...],
               cap: int = 6) -> Franking:
    """Frank `horse_id`'s most recent prior race. Returns a Franking summary."""
    if not history:
        return Franking(None, 0, 0, "no prior form to frank")
    last = history[0]                                # most recent prior run
    if not (last.race_id and last.date):
        return Franking(last.date, 0, 0, "no race id on the last run — can't frank")
    field = next((r for r in results_from_raw(client.results_by_date(last.date.isoformat()))
                  if r.race_id == last.race_id), None)
    if field is None:
        return Franking(last.date, 0, 0, "last race not found in results")
    rivals = [rr.horse_id for rr in field.runners if rr.horse_id and rr.horse_id != horse_id][:cap]
    franked = sum(1 for rid in rivals
                  if _scored_since(past_runs_from_raw(client.horse_results(rid), rid), last.date))
    if not rivals:
        return Franking(last.date, 0, 0, "no rivals to check")
    verdict = "FRANKED" if franked >= 2 else "thin"
    return Franking(last.date, len(rivals), franked,
                    f"last race {verdict}: {franked}/{len(rivals)} rivals won/placed since")
