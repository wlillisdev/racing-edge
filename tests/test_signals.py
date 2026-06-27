"""Tests for the heart — the handicapping signals. Pure, no env/network/DB.

Run: pytest, or `python tests/test_signals.py`.
"""

from __future__ import annotations

import sys
from datetime import date

from racing_edge.domain.form import bottler, improving
from racing_edge.domain.models import PastRun, Race, Runner
from racing_edge.domain.profile import (
    class_ceiling,
    class_drop,
    course_proven,
    going_proven,
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


def test_weight_relief() -> None:
    runner = Runner(horse_id="H", horse="X", weight_lbs=150)
    assert weight_relief(runner, (_run(5, wt=156),)) is not None   # 6lb relief
    assert weight_relief(runner, (_run(5, wt=151),)) is None       # only 1lb


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
