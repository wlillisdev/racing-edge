"""Tests for the optimisation analysis — conviction, signal, walk-forward (pure)."""

from __future__ import annotations

import sys
from datetime import date, timedelta

from racing_edge.measurement.analyse import by_conviction, by_signal, walk_forward
from racing_edge.measurement.record import SettledPick
from racing_edge.report.analysis import render_analysis


def _p(i: int, score: float, signals: str, price: float, sp: float, pos: int) -> SettledPick:
    return SettledPick(date=date(2026, 1, 1) + timedelta(days=i), race_id=f"R{i}",
                       horse_id=f"H{i}", horse="X", system="method", season="nh_winter",
                       code="jump", price_taken=price, sp=sp, position=pos,
                       score=score, signals=signals)


def _sample() -> list[SettledPick]:
    # high-score picks beat the close; low-score ones don't
    picks = []
    for i in range(10):
        picks.append(_p(i, 12.0, "well_in_proven,ground_proven", 5.0, 4.0, 1))   # +CLV winners
    for i in range(10, 20):
        picks.append(_p(i, 3.0, "market_stance", 4.0, 5.0, 5))                    # -CLV losers
    return picks


def test_by_conviction_separates_strong() -> None:
    rows = dict(by_conviction(_sample()))
    assert "all picks" in rows
    # the highest threshold bucket should be the high-score winners (positive CLV)
    strong = [s for label, s in by_conviction(_sample()) if "score >=" in label][-1]
    assert strong.mean_clv_pct is not None and strong.mean_clv_pct > 0


def test_by_signal_associates() -> None:
    rows = {name: (f, nf) for name, f, nf in by_signal(_sample())}
    # well_in_proven only fired on the winners -> its 'fired' CLV is high
    f, nf = rows["well_in_proven"]
    assert f.mean_clv_pct is not None and f.mean_clv_pct > 0
    # market_stance only on losers -> its 'fired' CLV is negative
    f2, _ = rows["market_stance"]
    assert f2.mean_clv_pct is not None and f2.mean_clv_pct < 0


def test_walk_forward_splits_in_time() -> None:
    wf = walk_forward(_sample())
    assert len(wf) == 2
    assert wf[0][0].startswith("first") and wf[1][0].startswith("second")


def test_render_runs() -> None:
    out = render_analysis(_sample())
    assert "OPTIMISATION ANALYSIS" in out and "by CONVICTION" in out and "WALK-FORWARD" in out
    assert render_analysis([]).startswith("No method picks")


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
