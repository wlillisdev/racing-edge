"""Tests for the SQLite ledger + the record/settle loop — full round-trip,
real DB (temp file). Run: pytest or `python tests/test_store.py`.
"""

from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

from racing_edge.domain.models import Odds, Race, RaceResult, Runner, RunnerResult
from racing_edge.measurement.metrics import vs_favourite
from racing_edge.measurement.store import Ledger
from racing_edge.pipeline.ledger import record_day, settle_day
from racing_edge.report.card import CardPick, DayCard
from racing_edge.selection.case import Case


def _day_card() -> DayCard:
    fav = Runner(horse_id="JOLLY", horse="Jolly", odds=Odds(consensus=2.0))
    pick = Runner(horse_id="OURS", horse="Bishopton", odds=Odds(consensus=5.0))
    race = Race(race_id="R1", course="Kelso", off_time="14:40", date=date(2026, 1, 15),
                race_type="Chase", race_class=3, going="Soft", runners=(fav, pick))
    case = Case(runner=pick, signals=(), score=10.0, vetoed=False)
    return DayCard(day=date(2026, 1, 15), code="jump",
                   picks=(CardPick(race=race, case=case, price=5.0, bet=None),))


def test_round_trip_record_settle_clv() -> None:
    with tempfile.TemporaryDirectory() as d:
        ledger = Ledger(Path(d) / "ledger.db")

        # morning: record method pick + the favourite benchmark
        n = record_day(_day_card(), ledger)
        assert n == 2 and ledger.pending_count() == 2

        # idempotent — recording again writes nothing new
        record_day(_day_card(), ledger)
        assert ledger.pending_count() == 2

        # evening: our pick won at SP 4.0 (we took 5.0 -> +CLV); favourite lost
        results = [RaceResult(race_id="R1", date=date(2026, 1, 15), runners=(
            RunnerResult(horse_id="OURS", position=1, sp_dec=4.0),
            RunnerResult(horse_id="JOLLY", position=3, sp_dec=2.1),
        ))]
        settle_day(date(2026, 1, 15), results, ledger)
        assert ledger.pending_count() == 0

        picks = ledger.settled_picks()
        assert len(picks) == 2
        method = next(p for p in picks if p.system == "method")
        assert method.won is True
        assert method.clv == round(5.0 / 4.0 - 1, 4)      # took 5.0, closed 4.0 -> +0.25

        bench = vs_favourite(picks)
        assert bench.method.wins == 1 and bench.favourite.wins == 0
        assert bench.edge_roi > 0
        ledger.close()


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
