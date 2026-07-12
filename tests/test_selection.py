"""Tests for the selection assembler — case stacking, veto + let-off, race pick.

Run: pytest, or `python tests/test_selection.py`.
"""

from __future__ import annotations

import sys
from datetime import date

from racing_edge.domain.models import Odds, PastRun, Race, Runner
from racing_edge.selection.case import RunnerEvidence, assess


def _race(cls: int = 3) -> Race:
    return Race(race_id="R", course="Kelso", off_time="14:40", date=date(2026, 1, 15),
                race_type="Handicap Chase", is_handicap=True, race_class=cls,
                distance_f=20.0, going="Soft")


def _won_at_level() -> tuple[PastRun, ...]:
    return (PastRun(date=date(2025, 12, 1), position=1, race_class=3, going="Soft",
                    distance_f=20.0, weight_lbs=154, course="Kelso"),)


def test_case_stacks_reasons_and_score() -> None:
    runner = Runner(horse_id="H", horse="Bishopton", weight_lbs=150, form="2311",
                    odds=Odds(consensus=3.5))
    ev = RunnerEvidence(runner=runner, history=_won_at_level(), stable_runs=20, stable_wins=6)
    case = assess(ev, _race())
    names = {s.name for s in case.signals}
    assert "well_in_proven" in names         # 4lb lower + won at level
    assert "ground_proven" in names          # won on soft
    assert "stable_hot" in names             # 30% yard
    assert case.score > 0 and not case.vetoed
    assert len(case.reasons) == len(case.signals)


def test_veto_exposed_non_winner() -> None:
    # 2-2-3-2 form, never won at the level -> bottler veto, no let-off
    runner = Runner(horse_id="H", horse="Nearly", form="2232", weight_lbs=150)
    ev = RunnerEvidence(runner=runner, history=(PastRun(date=date(2025, 12, 1),
                        position=2, race_class=3),))
    case = assess(ev, _race())
    assert case.vetoed is True


def test_class_drop_forgives_the_veto() -> None:
    # same bottler form, but it won in Class 2 (drops to 3) -> let-off, not vetoed
    runner = Runner(horse_id="H", horse="Dropper", form="2232", weight_lbs=150)
    hist = (PastRun(date=date(2025, 11, 1), position=1, race_class=2),
            PastRun(date=date(2025, 12, 1), position=2, race_class=3))
    case = assess(RunnerEvidence(runner=runner, history=hist), _race(cls=3))
    assert case.vetoed is False
    assert any(s.name == "class_drop" for s in case.signals)


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
