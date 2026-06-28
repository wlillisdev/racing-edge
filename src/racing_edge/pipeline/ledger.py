"""Record and settle — the CLV ledger loop.

record_day: write each method pick AND that race's favourite (the benchmark) as
pending rows. settle_day: fill them in from results so CLV can be computed. Both
in-process; the metrics layer reads the resulting settled picks.
"""

from __future__ import annotations

from datetime import date

from racing_edge.domain.market import favourite
from racing_edge.domain.models import RaceResult
from racing_edge.measurement.store import Ledger
from racing_edge.report.card import DayCard


def record_day(card: DayCard, ledger: Ledger) -> int:
    """Record the day's method picks and the favourite of each of those races."""
    n = 0
    for cp in card.picks:
        race, case = cp.race, cp.case
        ledger.record(day=card.day, race_id=race.race_id, horse_id=case.runner.horse_id,
                      horse=case.runner.horse, system="method", season=race.season,
                      code=race.code, price_taken=cp.price,
                      score=case.score, signals=",".join(s.name for s in case.signals))
        n += 1
        fav = favourite(race)
        if fav is not None and fav.horse_id != case.runner.horse_id:
            ledger.record(day=card.day, race_id=race.race_id, horse_id=fav.horse_id,
                          horse=fav.horse, system="favourite", season=race.season,
                          code=race.code, price_taken=fav.odds.consensus)
            n += 1
    return n


def settle_day(day: date, results: list[RaceResult], ledger: Ledger) -> int:
    """Fill in results for the day's pending picks (method + favourite)."""
    settled = 0
    for res in results:
        for r in res.runners:
            ledger.settle_runner(day=day, race_id=res.race_id, horse_id=r.horse_id,
                                 position=r.position, sp=r.sp_dec)
            settled += 1
    return settled
