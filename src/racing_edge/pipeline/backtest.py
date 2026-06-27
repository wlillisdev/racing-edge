"""Backtest — run the method over a date range and settle it, honestly.

The moment of truth: does the method, in its real season, beat the favourite and
the closing line? Reuses the live machinery (same pick -> bet -> record ->
settle -> CLV), with ONE critical difference: evidence is built `as_of` each race
date, so a past race is judged ONLY on form that existed at the time. No
look-ahead — the single most common way a backtest lies.
"""

from __future__ import annotations

from collections.abc import Callable
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


class _CachingClient:
    """Memoise the per-horse and per-trainer lookups for the whole run. The same
    ~100 trainers recur every day, so caching trainer analysis alone cuts the
    call count enormously; horses rarely repeat within a month but it's free."""

    def __init__(self, client: _Client) -> None:
        self._c = client
        self._hr: dict[str, list[dict]] = {}
        self._tj: dict[str, list[dict]] = {}

    def racecards(self, day: str = "today") -> dict:
        return self._c.racecards(day)

    def results_by_date(self, date_str: str) -> dict:
        return self._c.results_by_date(date_str)

    def horse_results(self, horse_id: str, limit: int = 12) -> list[dict]:
        if horse_id not in self._hr:
            self._hr[horse_id] = self._c.horse_results(horse_id, limit)
        return self._hr[horse_id]

    def trainer_jockeys(self, trainer_id: str) -> list[dict]:
        if trainer_id not in self._tj:
            self._tj[trainer_id] = self._c.trainer_jockeys(trainer_id)
        return self._tj[trainer_id]


def backtest(client: _Client, start: date, end: date, ledger,
             code: str = "jump", policy: BettingPolicy | None = None,
             progress: Callable[[date, int, int], None] | None = None) -> tuple[int, int]:
    """Walk each day start..end: pick the method's runners (point-in-time),
    record them + the favourite benchmark, and settle against results. `progress`
    is called per day with (day, races, picks_so_far). Returns (days, picks).
    Read the verdict with report.render_ledger."""
    policy = policy or BettingPolicy()
    client = _CachingClient(client)
    done = ledger.recorded_dates()           # resume: skip days already processed
    day = start
    days = picks = 0
    while day <= end:
        ds = day.isoformat()
        if ds in done:                       # already in the ledger — don't re-fetch
            day += timedelta(days=1)
            continue
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
        if progress is not None:
            progress(day, len(races), picks)
        day += timedelta(days=1)
    return days, picks
