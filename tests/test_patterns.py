"""Tests for the pattern backcheck — least-raised recent winner, settled on results."""

from __future__ import annotations

import sys
from datetime import date

from racing_edge.domain.models import PastRun, Race, RaceResult, Runner, RunnerResult
from racing_edge.pipeline.restudy import Restudy
from racing_edge.study.patterns import least_raised_recent_winner, summarise


def _runner(hid: str, name: str, ofr: int) -> Runner:
    return Runner(horse_id=hid, horse=name, official_rating=ofr)


def _won_off(orr: int, d: date = date(2026, 6, 1)) -> PastRun:
    return PastRun(date=d, position=1, official_rating=orr, race_type="Flat")


def _st(runners, results, histories) -> Restudy:
    race = Race(race_id="r", course="Epsom", off_time="6:22", date=date(2026, 7, 1),
                race_type="Flat", is_handicap=True, runners=tuple(runners))
    res = RaceResult(race_id="r", date=date(2026, 7, 1), runners=tuple(results))
    return Restudy(race=race, result=res, histories=histories)


def test_picks_the_least_raised_of_the_recent_winners_and_settles() -> None:
    # three last-time-out winners raised +3 / +5 / +6 — pick the +3, who won at 8.5
    st = _st(
        [_runner("A", "Sir Garfield", 77), _runner("B", "Amazing Journey", 81),
         _runner("C", "Desert Cop", 80), _runner("D", "No Form", 70)],
        [RunnerResult(horse_id="A", position=1, sp_dec=8.5),
         RunnerResult(horse_id="B", position=2, sp_dec=2.5),
         RunnerResult(horse_id="C", position=4, sp_dec=6.0),
         RunnerResult(horse_id="D", position=5, sp_dec=34.0)],
        {"A": (_won_off(74),), "B": (_won_off(75),), "C": (_won_off(75),),
         "D": (PastRun(date=date(2026, 6, 1), position=7, official_rating=70),)},
    )
    h = least_raised_recent_winner(st)
    assert h is not None and h.horse == "Sir Garfield"
    assert h.delta == 3 and h.rivals == 3 and h.won and h.sp_dec == 8.5
    assert "1/1 won" in summarise([h]) and "+7.5pt" in summarise([h])


def test_no_bet_on_fewer_than_two_winners_or_a_tie() -> None:
    # only ONE recent winner -> nothing to compare -> no qualifying bet
    solo = _st([_runner("A", "Solo", 77), _runner("B", "Other", 70)],
               [RunnerResult(horse_id="A", position=1)],
               {"A": (_won_off(74),),
                "B": (PastRun(date=date(2026, 6, 1), position=5, official_rating=70),)})
    assert least_raised_recent_winner(solo) is None
    # two recent winners TIED on the rise -> ambiguous -> no bet
    tie = _st([_runner("A", "One", 77), _runner("B", "Two", 78)],
              [RunnerResult(horse_id="A", position=1)],
              {"A": (_won_off(74),), "B": (_won_off(75),)})
    assert least_raised_recent_winner(tie) is None


def test_most_recent_run_must_be_the_win() -> None:
    # A won two starts back then finished 4th — NOT a last-time-out winner
    st = _st([_runner("A", "Stale", 77), _runner("B", "Fresh", 78),
              _runner("C", "Fresh2", 80)],
             [RunnerResult(horse_id="B", position=1, sp_dec=4.0)],
             {"A": (PastRun(date=date(2026, 6, 20), position=4, official_rating=77),
                    _won_off(70, date(2026, 5, 1))),
              "B": (_won_off(75, date(2026, 6, 10)),),
              "C": (_won_off(74, date(2026, 6, 12)),)})
    h = least_raised_recent_winner(st)
    assert h is not None and h.horse == "Fresh"      # B: +3 vs C: +6; A excluded
    assert h.rivals == 2 and h.won


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
