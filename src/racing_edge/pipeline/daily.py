"""The daily run — one in-process flow: fetch the card, apply the method, build
the day's picks. Jumps-first (winter focus). No subprocesses, no JSON hand-offs.
"""

from __future__ import annotations

from datetime import date

from racing_edge.betting.bet import make_bet
from racing_edge.betting.policy import BettingPolicy
from racing_edge.data.evidence import build_evidence
from racing_edge.data.normalise import racecards_from_raw
from racing_edge.report.card import CardPick, DayCard
from racing_edge.selection.select import pick_race


class _Client:
    def racecards(self, day: str = "today") -> dict: ...
    def horse_results(self, horse_id: str, limit: int = 12) -> list[dict]: ...
    def trainer_jockeys(self, trainer_id: str) -> list[dict]: ...


def run_day(client: _Client, policy: BettingPolicy | None = None,
            day: str = "today", code: str = "jump") -> DayCard:
    """Fetch the day's card, keep the chosen code (jumps by default), and produce
    one transparent pick per race the method stands up in."""
    policy = policy or BettingPolicy()
    races = [r for r in racecards_from_raw(client.racecards(day)) if r.code == code]

    picks: list[CardPick] = []
    for race in races:
        result = pick_race(race, build_evidence(race, client))
        if not result.is_bet or result.pick is None:
            continue
        case = result.pick
        price = case.runner.odds.consensus
        picks.append(CardPick(race=race, case=case, price=price,
                              bet=make_bet(case, price, policy)))

    card_date = races[0].date if races else date.today()
    return DayCard(day=card_date, code=code, picks=tuple(picks))
