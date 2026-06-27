"""Tests for the honest measurement layer — CLV, season split, favourite benchmark."""

from __future__ import annotations

import sys
from datetime import date

from racing_edge.measurement.metrics import (
    TRUST_SAMPLE,
    by_season,
    summarise,
    verdict,
    vs_favourite,
)
from racing_edge.measurement.record import SettledPick


def _p(system: str, season: str, price: float | None, sp: float | None, pos: int | None,
       code: str = "jump") -> SettledPick:
    return SettledPick(date=date(2026, 1, 15), race_id="R", horse_id="H", horse="X",
                       system=system, season=season, code=code,
                       price_taken=price, sp=sp, position=pos)


def test_clv() -> None:
    assert _p("method", "nh_winter", 5.0, 4.0, 1).clv == 0.25     # took 5.0, closed 4.0
    assert _p("method", "nh_winter", 4.0, 5.0, 2).clv == -0.20    # took less than the close
    assert _p("method", "nh_winter", None, 4.0, 1).clv is None


def test_summarise_roi_and_clv() -> None:
    picks = [
        _p("method", "nh_winter", 4.0, 3.5, 1),    # won, +CLV
        _p("method", "nh_winter", 3.0, 3.2, 4),    # lost, -CLV
    ]
    s = summarise(picks)
    assert s.n == 2 and s.wins == 1 and s.win_pct == 50.0
    # ROI level stakes at price taken: (+3) + (-1) = +2 over 2 = +100%
    assert s.roi_pct == 100.0
    assert s.mean_clv_pct is not None
    assert s.trusted is False                       # 2 < TRUST_SAMPLE


def test_by_season_never_blends() -> None:
    picks = [_p("method", "nh_winter", 4.0, 4.0, 1), _p("method", "flat_summer", 4.0, 4.0, 4)]
    out = by_season(picks)
    assert set(out) == {"nh_winter", "flat_summer"}
    assert out["nh_winter"].wins == 1 and out["flat_summer"].wins == 0


def test_vs_favourite_benchmark() -> None:
    picks = [
        _p("method", "nh_winter", 5.0, 4.0, 1),     # method won
        _p("favourite", "nh_winter", 2.5, 2.5, 4),  # fav lost
    ]
    b = vs_favourite(picks)
    assert b.method.wins == 1 and b.favourite.wins == 0
    assert b.edge_roi > 0                            # method beat the favourite here


def test_verdict_sample_guard() -> None:
    small = summarise([_p("method", "nh_winter", 4.0, 4.0, 1)])
    assert "direction only" in verdict(small)
    assert TRUST_SAMPLE == 100


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
