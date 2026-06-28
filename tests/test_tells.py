"""Tests for the tells — the nuances I learn myself from results.

Each tell is earned from a real race; these lock the pattern matchers so a similar
horse in a similar race trips the same recognition next time.
"""

from __future__ import annotations

import sys
from datetime import date

from racing_edge.domain.models import Odds, PastRun, Race, Runner
from racing_edge.domain.tells import match_tells


def _race(course="Cartmel", going="Good", dist=25.0, rtype="Handicap Chase") -> Race:
    return Race(race_id="r", course=course, off_time="16:55", date=date(2026, 6, 28),
                race_type=rtype, is_handicap=True, distance_f=dist, going=going)


def test_cdg_winner_returning_fires() -> None:
    # Kingofthegame: won over the same course, trip and going before
    hist = (PastRun(date=date(2026, 5, 28), position=1, course="Cartmel",
                    going="Good", distance_f=25.0),)
    runner = Runner(horse_id="k", horse="Kingofthegame", odds=Odds(consensus=3.0))
    tells = match_tells(runner, _race(), hist)
    assert any("course/distance/going winner" in t for t in tells)
    # a win at a DIFFERENT course must not fire it
    away = (PastRun(date=date(2026, 5, 28), position=1, course="Ayr",
                    going="Good", distance_f=25.0),)
    assert not match_tells(runner, _race(), away)


def test_hat_trick_trap_fires_on_short_priced_double_winner() -> None:
    hist = (PastRun(date=date(2026, 6, 1), position=1), PastRun(date=date(2026, 5, 1), position=1))
    short = Runner(horse_id="h", horse="Halfway House Lad", odds=Odds(consensus=2.25))
    tells = match_tells(short, _race(rtype="Handicap Chase"), hist)
    assert any("won its last two" in t and "chase" in t for t in tells)
    # same horse at a fair price -> not a trap (the price is the point)
    priced = Runner(horse_id="h", horse="Halfway House Lad", odds=Odds(consensus=6.0))
    assert not match_tells(priced, _race(), hist)
    # only one recent win -> not the pattern
    one = (PastRun(date=date(2026, 6, 1), position=1), PastRun(date=date(2026, 5, 1), position=3))
    assert not match_tells(short, _race(), one)


def test_headgear_key_needs_first_time_gear_and_an_in_form_yard() -> None:
    gear_inform = Runner(horse_id="e", horse="King Of Earth", odds=Odds(consensus=3.0),
                         headgear_first_time=True, trainer_14d_runs=6, trainer_14d_wins=2)
    assert any("first-time headgear" in t for t in match_tells(gear_inform, _race(), ()))
    # first-time gear but a COLD yard -> no tell (the yard's form is the point)
    gear_cold = Runner(horse_id="e", horse="X", odds=Odds(consensus=3.0),
                       headgear_first_time=True, trainer_14d_runs=8, trainer_14d_wins=0)
    assert not match_tells(gear_cold, _race(), ())
    # in-form yard but no headgear change -> no tell
    no_gear = Runner(horse_id="e", horse="Y", odds=Odds(consensus=3.0),
                     trainer_14d_runs=6, trainer_14d_wins=2)
    assert not match_tells(no_gear, _race(), ())


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
