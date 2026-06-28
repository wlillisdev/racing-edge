"""Tests for the backtester — NO look-ahead, and a full record/settle round-trip."""

from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

from racing_edge.data.evidence import build_evidence
from racing_edge.domain.models import Race, Runner
from racing_edge.measurement.store import Ledger
from racing_edge.pipeline.backtest import backtest
from racing_edge.report.ledger import render_ledger


def test_no_lookahead_filters_future_runs() -> None:
    """A past race must only see form from BEFORE it — the cardinal backtest rule."""
    race = Race(race_id="R", course="Kelso", off_time="14:00", date=date(2026, 1, 15),
                race_type="Chase", race_class=3, runners=(Runner(horse_id="H", horse="X"),))

    class C:
        def horse_results(self, hid: str, limit: int = 12) -> list[dict]:
            return [
                {"date": "2025-12-01", "position": "1", "class": "3"},   # before -> kept
                {"date": "2026-02-01", "position": "1", "class": "3"},   # AFTER race -> dropped
            ]
        def trainer_jockeys(self, tid: str) -> list[dict]:
            return []

    ev = build_evidence(race, C(), as_of=race.date)
    assert len(ev[0].history) == 1
    assert ev[0].history[0].date == date(2025, 12, 1)


class _StubClient:
    def racecards(self, day: str = "today") -> dict:
        return {"racecards": [{
            "race_id": f"R_{day}", "course": "Kelso", "off_time": "14:40",
            "race_name": "Handicap Chase", "type": "Chase", "class": "3",
            "distance_f": "20.0", "going": "Soft", "date": day, "runners": [
                {"horse_id": "FAV", "horse": "Jolly", "trainer_id": "T2", "jockey_id": "Z",
                 "lbs": "160", "form": "11", "odds": [{"decimal": "2.0"}]},
                {"horse_id": "OURS", "horse": "Bishopton", "trainer_id": "T1", "jockey_id": "A",
                 "lbs": "150", "form": "2311", "odds": [{"decimal": "5.0"}]},
            ]}]}

    def results_by_date(self, ds: str) -> dict:
        return {"results": [{"race_id": f"R_{ds}", "date": ds, "runners": [
            {"horse_id": "OURS", "position": "1", "sp_dec": "4.0"},
            {"horse_id": "FAV", "position": "3", "sp_dec": "2.1"},
        ]}]}

    def horse_results(self, hid: str, limit: int = 12) -> list[dict]:
        if hid == "OURS":
            return [{"date": "2025-12-01", "position": "1", "class": "3", "going": "Soft",
                     "dist_f": "20.0", "lbs": "154", "course": "Kelso", "ran": "12"}]
        return []

    def trainer_jockeys(self, tid: str) -> list[dict]:
        return []


def test_backtest_round_trip() -> None:
    with tempfile.TemporaryDirectory() as d:
        ledger = Ledger(Path(d) / "bt.db")
        days, picks = backtest(_StubClient(), date(2026, 1, 15), date(2026, 1, 16),
                               ledger, code="jump")
        assert days == 2 and picks == 2            # one method pick each day (the proven OURS)
        out = render_ledger(ledger.settled_picks())
        assert "METHOD" in out and "FAVOURITE" in out
        # method took 5.0 and OURS closed at 4.0 -> positive CLV in the ledger
        method = [p for p in ledger.settled_picks() if p.system == "method"]
        assert all(p.clv == round(5.0 / 4.0 - 1, 4) for p in method)


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
