"""Backtest — run the method over a date range and settle it, honestly.

The moment of truth: does the method, in its real season, beat the favourite and
the closing line? Reuses the live machinery (same pick -> bet -> record ->
settle -> CLV), with ONE critical difference: evidence is built `as_of` each race
date, so a past race is judged ONLY on form that existed at the time. No
look-ahead — the single most common way a backtest lies.
"""

from __future__ import annotations

from datetime import date, timedelta

from racing_edge.betting.bet import make_bet
from racing_edge.betting.policy import BettingPolicy
from racing_edge.data.evidence import build_evidence
from racing_edge.data.normalise import racecards_from_raw, results_from_raw
from racing_edge.pipeline.ledger import record_day, settle_day
from racing_edge.report.card import CardPick, DayCard
from racing_edge.selection.select import pick_race


class _Client:
    def racecards(self, day: str = "today") -> dict: ...
    def results_by_date(self, date_str: str) -> dict: ...
    def horse_results(self, horse_id: str, limit: int = 12) -> list[dict]: ...
    def trainer_jockeys(self, trainer_id: str) -> list[dict]: ...


def backtest(client: _Client, start: date, end: date, ledger,
             code: str = "jump", policy: BettingPolicy | None = None) -> tuple[int, int]:
    """Walk each day start..end: pick the method's runners (point-in-time),
    record them + the favourite benchmark, and settle against results. Returns
    (days_processed, picks_made). Read the verdict with report.render_ledger."""
    policy = policy or BettingPolicy()
    day = start
    days = picks = 0
    while day <= end:
        ds = day.isoformat()
        races = [r for r in racecards_from_raw(client.racecards(ds)) if r.code == code]
        card_picks: list[CardPick] = []
        for race in races:
            result = pick_race(race, build_evidence(race, client, as_of=race.date))
            if not result.is_bet or result.pick is None:
                continue
            case = result.pick
            price = case.runner.odds.consensus
            card_picks.append(CardPick(race=race, case=case, price=price,
                                       bet=make_bet(case, price, policy)))
        record_day(DayCard(day=day, code=code, picks=tuple(card_picks)), ledger)
        settle_day(day, results_from_raw(client.results_by_date(ds)), ledger)
        picks += len(card_picks)
        days += 1
        day += timedelta(days=1)
    return days, picks
