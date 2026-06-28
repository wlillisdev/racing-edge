"""Tests for the heart — the handicapping signals. Pure, no env/network/DB.

Run: pytest, or `python tests/test_signals.py`.
"""

from __future__ import annotations

import sys
from datetime import date

from racing_edge.domain.form import bottler, improving
from racing_edge.domain.intent import (
    first_time_headgear,
    form_franked,
    jockey_intent,
    jockey_trainer_combo,
    market_move,
    stable_in_form,
)
from racing_edge.domain.models import Odds, PastRun, Race, Runner
from racing_edge.domain.profile import (
    claimer_allowance,
    class_ceiling,
    class_drop,
    course_proven,
    going_proven,
    quality_of_win,
    topped_out,
    trip_proven,
    weight_relief,
    well_in_and_proven,
)


def _race(cls: int = 3, going: str = "Soft", dist: float = 20.0, course: str = "Kelso") -> Race:
    return Race(race_id="R", course=course, off_time="14:40", date=date(2026, 1, 15),
                race_type="Handicap Chase", is_handicap=True, race_class=cls,
                distance_f=dist, going=going)


def _run(pos: int | None, cls: int | None = 3, going: str = "Soft",
         dist: float = 20.0, wt: int | None = None, course: str = "Kelso") -> PastRun:
    return PastRun(date=date(2025, 12, 1), position=pos, race_class=cls, going=going,
                   distance_f=dist, weight_lbs=wt, course=course)


# ---- form: improving / bottler ----
def test_improving() -> None:
    assert improving("5323") is not None          # trending up, placing, no win
    assert improving("113") is None               # already a winner
    assert improving("8787") is None              # no upward trend
    sig = improving("5323")
    assert sig is not None and sig.weight > 0


def test_bottler() -> None:
    sig = bottler("2232")
    assert sig is not None and sig.weight < 0 and sig.veto is True
    assert bottler("2212") is None                # has a win -> not a bottler
    assert bottler("32") is None                  # too short


# ---- well-in & proven (the strongest read) ----
def test_well_in_and_proven() -> None:
    race = _race(cls=3)
    hist = (_run(1, cls=3, wt=154),)              # won at the level, last carried 154
    runner = Runner(horse_id="H", horse="X", weight_lbs=150)  # 4lb lower today
    sig = well_in_and_proven(runner, race, hist)
    assert sig is not None and sig.name == "well_in_proven" and sig.weight == 5.0


def test_proven_but_not_well_in() -> None:
    race = _race(cls=3)
    hist = (_run(1, cls=3, wt=150),)
    runner = Runner(horse_id="H", horse="X", weight_lbs=152)  # higher, not well-in
    sig = well_in_and_proven(runner, race, hist)
    assert sig is not None and sig.name == "proven_at_level" and sig.weight == 3.0


def test_not_proven_returns_none() -> None:
    race = _race(cls=3)
    hist = (_run(4, cls=3),)                       # never won at the level
    runner = Runner(horse_id="H", horse="X", weight_lbs=150)
    assert well_in_and_proven(runner, race, hist) is None


# ---- class drop / ceiling / topped out ----
def test_class_drop() -> None:
    race = _race(cls=4)
    hist = (_run(1, cls=2),)                       # won in Class 2, drops to Class 4
    sig = class_drop(race, hist)
    assert sig is not None and "Class 2" in sig.reason


def test_class_ceiling_vetoes() -> None:
    race = _race(cls=3)
    hist = (_run(2, cls=3), _run(3, cls=2), _run(4, cls=3))  # 3 at level+, no win
    sig = class_ceiling(race, hist)
    assert sig is not None and sig.veto is True


def test_topped_out() -> None:
    race = _race(cls=3)
    hist = (_run(1, cls=5),)                       # only won in Class 5 (lower grade)
    sig = topped_out(race, hist)
    assert sig is not None and sig.weight < 0


# ---- ground / trip / course / weight ----
def test_going_proven_and_wrong() -> None:
    race = _race(going="Soft")
    assert going_proven(race, (_run(1, going="Soft"),)) is not None
    wrong = going_proven(race, tuple(_run(8, going="Soft") for _ in range(4)))
    assert wrong is not None and wrong.weight < 0


def test_trip_and_course() -> None:
    race = _race(dist=20.0, course="Kelso")
    assert trip_proven(race, (_run(1, dist=20.5),)) is not None    # within tolerance
    assert trip_proven(race, (_run(1, dist=12.0),)) is None        # wrong trip
    assert course_proven(race, (_run(1, course="Kelso"),)) is not None
    assert course_proven(race, (_run(1, course="Ayr"),)) is None


def test_well_handicapped() -> None:
    from racing_edge.domain.profile import well_handicapped
    h = _race(cls=3)  # is_handicap True
    assert well_handicapped(Runner(horse_id="H", horse="X", rpr=148, official_rating=138), h) is not None
    assert well_handicapped(Runner(horse_id="H", horse="X", rpr=141, official_rating=138), h) is None
    nonh = Race(race_id="R", course="Ayr", off_time="15:00", date=date(2026, 1, 15),
                race_type="Chase", is_handicap=False, race_class=3)
    assert well_handicapped(Runner(horse_id="H", horse="X", rpr=148, official_rating=138), nonh) is None


def test_weight_relief() -> None:
    runner = Runner(horse_id="H", horse="X", weight_lbs=150)
    assert weight_relief(runner, (_run(5, wt=156),)) is not None   # 6lb relief
    assert weight_relief(runner, (_run(5, wt=151),)) is None       # only 1lb


def test_claimer_allowance() -> None:
    assert claimer_allowance(Runner(horse_id="H", horse="X", claim_lbs=7)).weight == 2.5
    assert claimer_allowance(Runner(horse_id="H", horse="X", claim_lbs=3)).weight == 1.5
    assert claimer_allowance(Runner(horse_id="H", horse="X", claim_lbs=0)) is None
    assert claimer_allowance(Runner(horse_id="H", horse="X")) is None


def test_consistency_prb() -> None:
    from racing_edge.domain.profile import consistency_prb
    strong = tuple(PastRun(date=date(2025, 12, i), position=p, field_size=f)
                   for i, (p, f) in enumerate([(5, 24), (3, 20), (2, 16), (6, 18)], 1))
    assert consistency_prb(strong).name == "consistent"          # ~0.84
    weak = tuple(PastRun(date=date(2025, 12, i), position=p, field_size=f)
                 for i, (p, f) in enumerate([(9, 10), (7, 8), (8, 9), (6, 7)], 1))
    assert consistency_prb(weak).name == "modest_merit"          # ~0.14
    assert consistency_prb((PastRun(date=date(2025, 12, 1), position=2, field_size=10),)) is None  # too few


def test_quality_of_win() -> None:
    good = (_run(1, cls=3, dist=20.0),)
    # field_size needs setting on the PastRun
    good = (PastRun(date=date(2025, 12, 1), position=1, race_class=3, field_size=12),)
    assert quality_of_win(good) is not None
    weak = (PastRun(date=date(2025, 12, 1), position=1, race_class=6, field_size=4),)
    assert quality_of_win(weak) is None


def test_stable_in_form() -> None:
    assert stable_in_form(20, 6).name == "stable_hot"      # 30%
    assert stable_in_form(20, 4).name == "stable_form"     # 20%
    assert stable_in_form(30, 1).name == "stable_cold"     # ~3%
    assert stable_in_form(5, 3) is None                    # too few runs


def test_stable_value_ae() -> None:
    from racing_edge.domain.intent import stable_value
    assert stable_value(1.20, 50).name == "stable_value"      # beats its odds
    assert stable_value(0.80, 60).name == "stable_overbet"    # underperforms odds, big sample
    assert stable_value(1.20, 10) is None                     # too few runs
    assert stable_value(None, 50) is None                     # no A/E supplied


def test_first_time_headgear() -> None:
    on = Runner(horse_id="H", horse="X", headgear="b", headgear_first_time=True)
    assert first_time_headgear(on) is not None
    off = Runner(horse_id="H", horse="X", headgear="b", headgear_first_time=False)
    assert first_time_headgear(off) is None


def test_form_franked() -> None:
    assert form_franked(2) is not None
    assert form_franked(0) is None


def _yard_race(*runners: Runner) -> Race:
    return Race(race_id="R", course="Naas", off_time="15:00", date=date(2026, 1, 15),
                race_type="Handicap Hurdle", race_class=3, runners=runners)


def test_jockey_intent_second_string() -> None:
    # Trainer T1 runs two; stable jockey A is on the LONGER one (the message).
    fav = Runner(horse_id="F", horse="Fav", trainer_id="T1", jockey_id="B",
                 odds=Odds(consensus=2.5))
    second = Runner(horse_id="S", horse="Second", trainer_id="T1", jockey_id="A",
                    odds=Odds(consensus=6.0))
    race = _yard_race(fav, second)
    sig = jockey_intent(second, race, frozenset({"A"}))
    assert sig is not None and sig.name == "jockey_intent" and sig.weight == 4.0
    # the favourite ridden by the lesser jockey is flagged the lesser
    lesser = jockey_intent(fav, race, frozenset({"A"}))
    assert lesser is not None and lesser.weight < 0


def test_jockey_single_runner_no_intent() -> None:
    only = Runner(horse_id="H", horse="X", trainer_id="T1", jockey_id="A", odds=Odds(consensus=4.0))
    assert jockey_intent(only, _yard_race(only), frozenset({"A"})) is None


def test_jockey_trainer_combo() -> None:
    assert jockey_trainer_combo(50, 12) is not None    # 24%
    assert jockey_trainer_combo(50, 4) is None         # 8%
    assert jockey_trainer_combo(10, 5) is None         # too few


def test_market_stance() -> None:
    from racing_edge.domain.market import is_favourite, market_stance
    fav = Runner(horse_id="F", horse="Fav", odds=Odds(consensus=2.5))
    other = Runner(horse_id="O", horse="Other", odds=Odds(consensus=6.0))
    race = _yard_race(fav, other)
    assert is_favourite(fav, race) is True
    assert "WITH the market" in market_stance(fav, race)
    assert "AGAINST the market" in market_stance(other, race)


def test_market_move() -> None:
    assert market_move(Odds(morning=6.0, late=4.0)).name == "steamer"
    assert market_move(Odds(morning=4.0, late=6.0)).name == "drifter"
    assert market_move(Odds(morning=4.0, late=4.1)) is None     # no real move
    assert market_move(Odds(morning=None, late=4.0)) is None


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
