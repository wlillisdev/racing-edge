"""Tests for the full-form re-study loop — the comment door + the readout (#27/#29)."""

from __future__ import annotations

import sys
from datetime import date

from racing_edge.data.normalise import past_runs_from_raw
from racing_edge.domain.models import Odds, Race, RaceResult, Runner, RunnerResult
from racing_edge.report.restudy import render_restudy


def test_past_runs_capture_the_in_running_comment() -> None:
    """The old normaliser dropped the comment — the richest 'how it ran' signal. It
    must now come through from the horse's own nested row, and a blank stays blank."""
    rows = [
        {"date": "2026-06-01", "course": "Thirsk", "type": "Flat", "class": "4",
         "dist_f": "8", "going": "Good", "race_id": "r1", "ran": 10,
         "runners": [
             {"horse_id": "H1", "position": "1", "or": "82", "lbs": "133",
              "comment": "led 2f out, stayed on strongly"},
             {"horse_id": "H2", "position": "3", "or": "80"},   # no comment -> OWED
         ]},
    ]
    h1 = past_runs_from_raw(rows, "H1")
    h2 = past_runs_from_raw(rows, "H2")
    assert h1[0].comment == "led 2f out, stayed on strongly"
    assert h1[0].won and h1[0].official_rating == 82
    assert h2[0].comment == ""            # blank, not invented


def _runner(hid: str, name: str, morning: float, ofr: int,
            form: str = "", spot: str = "") -> Runner:
    return Runner(horse_id=hid, horse=name, official_rating=ofr, form=form, spotlight=spot,
                  odds=Odds(morning=morning, consensus=morning))


def test_render_orders_by_finish_stars_winner_and_marks_owed() -> None:
    race = Race(race_id="r1", course="Thirsk", off_time="16:10", date=date(2026, 7, 1),
                race_type="Flat", is_handicap=True, race_class=5,
                runners=(
                    _runner("H1", "Indian Run", 6.2, 78, form="321", spot="travels well"),
                    _runner("H2", "Mister Sox", 6.0, 80),
                ))
    result = RaceResult(race_id="r1", date=date(2026, 7, 1), runners=(
        RunnerResult(horse_id="H1", position=1, sp_dec=5.5, horse="Indian Run"),
        RunnerResult(horse_id="H2", position=2, sp_dec=5.5, horse="Mister Sox", beaten_lengths=1.0),
    ))
    # H1 last won off OR 70 -> today 78 is +8lb (raised); give it a winning history line
    histories = {
        "H1": past_runs_from_raw([{"date": "2026-05-01", "runners": [
            {"horse_id": "H1", "position": "1", "or": "70", "comment": "readily"}]}], "H1"),
        "H2": (),   # no history -> past runs OWED
    }
    out = render_restudy(race, result, histories)
    assert out.index("Indian Run") < out.index("Mister Sox")   # winner first
    assert "★WON" in out
    assert "BACKED" in out                                      # 6.2 -> 5.5
    assert "+8lb" in out                                        # the mark read fired
    assert "spotlight: travels well" in out
    assert "OWED" in out                                        # H2 history / comment owed
    assert "readily" in out                                     # H1 past comment surfaced


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
