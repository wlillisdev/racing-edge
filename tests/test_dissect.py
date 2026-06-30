"""Tests for the nightly dissection readout — the market move on every runner."""

from __future__ import annotations

import sys
from datetime import date

from racing_edge.domain.models import Race
from racing_edge.report.dissect import market_move, render_race_dissection
from racing_edge.study.postmortem import StudiedRunner


def test_market_move_reads_backed_drifted_steady_and_owed() -> None:
    assert market_move(StudiedRunner("A", 1, 2.25, morning_dec=4.0)).startswith("BACKED")
    assert market_move(StudiedRunner("B", 5, 10.0, morning_dec=6.0)).startswith("drifted")
    assert market_move(StudiedRunner("C", 2, 4.0, morning_dec=4.0)).startswith("steady")
    assert market_move(StudiedRunner("D", 3, None, morning_dec=4.0)) == "move OWED"


def test_render_orders_by_finish_and_flags_manner_owed() -> None:
    race = Race(race_id="r", course="Musselburgh", off_time="14:00", date=date(2026, 6, 30),
                race_type="Handicap", is_handicap=True,
                runners=tuple())
    runners = [
        StudiedRunner("Winner", 1, 2.25, morning_dec=4.0),          # backed in
        StudiedRunner("Beaten Fav", 4, 2.5, morning_dec=2.0),       # drifted
        StudiedRunner("Faller", None, 12.0, morning_dec=10.0),
    ]
    out = render_race_dissection(race, runners)
    # winner first, faller last; the move and the OWED manner both present
    assert out.index("Winner") < out.index("Beaten Fav") < out.index("Faller")
    assert "BACKED" in out and "OWED" in out and "#27" in out


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
