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


def test_render_does_the_grunt_reads_in_code_manner_and_market_rank() -> None:
    """The model shouldn't re-derive mechanical reads (where it slips): the readout now
    prints the manner verdict from comments and the market rank off SP."""
    race = Race(race_id="r1", course="Worcester", off_time="1:50", date=date(2026, 7, 1),
                race_type="Chase", is_handicap=True,
                runners=(_runner("H1", "Knightsbridge", 3.6, 90),
                         _runner("H2", "Culligran", 16.0, 85)))
    result = RaceResult(race_id="r1", date=date(2026, 7, 1), runners=(
        RunnerResult(horse_id="H1", position=1, sp_dec=2.9),
        RunnerResult(horse_id="H2", position=2, sp_dec=12.0, beaten_lengths=3.0),
    ))
    histories = {
        "H1": past_runs_from_raw([{"date": "2026-06-03", "runners": [
            {"horse_id": "H1", "position": "1", "or": "85",
             "comment": "challenged at the last - ran on well"}]}], "H1"),
        "H2": past_runs_from_raw([{"date": "2026-06-06", "runners": [
            {"horse_id": "H2", "position": "7", "or": "86",
             "comment": "under pressure and weakened 4 out"}]}], "H2"),
    }
    out = render_restudy(race, result, histories)
    assert "manner read (#1): win_positive" in out          # the finisher, read in code
    assert "manner read (#1): place_only" not in out         # one bad run isn't a placer
    assert "mkt 1/2" in out and "mkt 2/2" in out             # market rank off SP


def test_system_read_reports_what_the_rules_said_pre_race() -> None:
    from racing_edge.pipeline.restudy import Restudy
    race = Race(race_id="r1", course="Cartmel", off_time="3:00", date=date(2026, 7, 1),
                race_type="Chase", is_handicap=True,
                runners=(_runner("H1", "Gem", 3.0, 120),))
    result = RaceResult(race_id="r1", date=date(2026, 7, 1),
                        runners=(RunnerResult(horse_id="H1", position=1, sp_dec=3.0),))
    hist = {"H1": past_runs_from_raw([{"date": "2026-05-01", "course": "Cartmel",
                                       "runners": [{"horse_id": "H1", "position": "1",
                                                    "or": "120"}]}], "H1")}
    read = Restudy(race=race, result=result, histories=hist).system_read()
    assert "Gem" in read and "well-in" in read               # the conviction engine ran


def test_gather_excludes_todays_run_from_history_no_lookahead() -> None:
    """The leak behind binned nuance #1: the API returns the horse's runs INCLUDING the
    race being studied, so the winner read WELL-IN off its own win. gather() must cut
    history strictly BEFORE the race date."""
    from racing_edge.pipeline.restudy import gather

    class _FakeClient:
        def racecards(self, day="today"):
            return {"racecards": [{
                "race_id": "r1", "course": "Epsom", "off_time": "6:22",
                "date": "2026-07-01", "type": "Flat", "race_name": "H'cap",
                "runners": [{"horse_id": "H1", "horse": "Sir Garfield"}],
            }]}

        def results_by_date(self, ds):
            return {"results": [{"race_id": "r1", "date": "2026-07-01",
                                 "runners": [{"horse_id": "H1", "position": "1",
                                              "sp_dec": "8.5"}]}]}

        def horse_results(self, horse_id, limit=12):
            return [
                {"date": "2026-07-01", "race_id": "r1", "runners": [        # TODAY — leak
                    {"horse_id": "H1", "position": "1", "or": "77"}]},
                {"date": "2026-04-08", "race_id": "r0", "runners": [        # real past
                    {"horse_id": "H1", "position": "1", "or": "74"}]},
            ]

    studies = gather(_FakeClient(), "2026-07-01")
    hist = studies[0].histories["H1"]
    assert len(hist) == 1 and hist[0].date.isoformat() == "2026-04-08"
    # and the mark now reads truthfully: last won off 74, so today off 77 = +3lb raised
    from racing_edge.domain.mark import mark_read
    assert mark_read(77, hist).verdict == "+3lb"


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
