"""Foundation tests — domain units, season, and the data contracts.

These run with no env, no network, no DB: the domain layer is import-side-effect
free by design (the audits flagged the old code needed os.environ hacks to even
import). Run: pytest, or `python tests/test_foundation.py`.
"""

from __future__ import annotations

import sys
from datetime import date

from racing_edge.domain.models import Odds, Race, RaceResult, Runner, RunnerResult
from racing_edge.domain.season import is_prime, prime_code, racing_season
from racing_edge.domain.units import (
    distance_to_furlongs,
    format_odds,
    going_band,
    is_jump,
    parse_form,
    race_code,
)


def test_race_code() -> None:
    assert race_code("Handicap Chase") == "jump"
    assert race_code("Maiden Hurdle") == "jump"
    assert race_code("NH Flat") == "jump"
    assert race_code("Class 4 Flat") == "flat"
    assert is_jump("Novices' Chase") is True


def test_going_band() -> None:
    assert going_band("Heavy") == "heavy"
    assert going_band("Good To Soft") == "soft"
    assert going_band("Soft (Heavy in places)") == "heavy"  # 'heavy' wins
    assert going_band("Good To Firm") == "firm"
    assert going_band("Standard") == "aw"
    assert going_band("") == "unknown"


def test_distance_to_furlongs() -> None:
    assert distance_to_furlongs("3m2f") == 26.0
    assert distance_to_furlongs("2m4f") == 20.0
    assert distance_to_furlongs("2m") == 16.0
    assert distance_to_furlongs("5f") == 5.0
    assert distance_to_furlongs("2m4½f") == 20.5
    assert distance_to_furlongs(16) == 16.0
    assert distance_to_furlongs(None) is None
    assert distance_to_furlongs("rubbish") is None


def test_parse_form() -> None:
    assert parse_form("213211") == [2, 1, 3, 2, 1, 1]
    assert parse_form("5323") == [5, 3, 2, 3]
    assert parse_form("70F2") == [7, 10, 2]          # '0' -> 10, 'F' skipped
    assert parse_form("") == []


def test_format_odds() -> None:
    assert format_odds(2.0) == "evens"
    assert format_odds(5.0) == "4/1"
    assert format_odds(3.5) == "5/2"
    assert format_odds(None) == "—"
    assert format_odds(1.0) == "—"


def test_season() -> None:
    assert racing_season(date(2026, 1, 15)) == "nh_winter"
    assert racing_season(date(2026, 7, 1)) == "flat_summer"
    assert racing_season(date(2026, 4, 10)) == "shoulder"


def test_season_label_is_code_aware() -> None:
    from racing_edge.domain.season import season_label
    # a summer JUMPS pick is its own (weak) season, never blended into flat_summer
    assert season_label(date(2026, 6, 28), "jump") == "summer_jumps"
    assert season_label(date(2026, 6, 28), "flat") == "flat_summer"
    # winter flat is mostly all-weather — kept apart from nh_winter jumps
    assert season_label(date(2026, 1, 15), "jump") == "nh_winter"
    assert season_label(date(2026, 1, 15), "flat") == "winter_flat"
    assert prime_code(date(2026, 1, 15)) == "jump"
    assert prime_code(date(2026, 7, 1)) == "flat"
    # winter: jumps are prime, flat is not; shoulder: both live
    assert is_prime("jump", date(2026, 1, 15)) is True
    assert is_prime("flat", date(2026, 1, 15)) is False
    assert is_prime("flat", date(2026, 4, 10)) is True


def test_schemas_and_derived() -> None:
    r = Runner(horse_id="H1", horse="Bishopton", odds=Odds(consensus=3.5, sp=3.0))
    race = Race(
        race_id="R1", course="Kelso", off_time="14:40", date=date(2026, 1, 15),
        race_type="Handicap Chase", is_handicap=True, race_class=3,
        distance_f=20.0, going="Soft", runners=(r,),
    )
    assert race.code == "jump"
    assert race.season == "nh_winter"
    assert race.going_band == "soft"
    assert race.field_size == 1


def test_result_favourite_and_outcomes() -> None:
    res = RaceResult(
        race_id="R1", date=date(2026, 1, 15),
        runners=(
            RunnerResult(horse_id="A", position=3, sp_dec=5.0),
            RunnerResult(horse_id="B", position=1, sp_dec=2.5),     # winner & favourite
            RunnerResult(horse_id="C", position=None, status="F", sp_dec=8.0),  # faller
        ),
    )
    assert res.favourite is not None and res.favourite.horse_id == "B"
    assert res.of("B") is not None and res.of("B").won is True
    assert res.of("A") is not None and res.of("A").placed(3) is True
    assert res.of("C") is not None and res.of("C").won is False


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
        passed += 1
    print(f"\nTOTAL {passed}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
