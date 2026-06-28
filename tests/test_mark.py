"""Tests for the handicap mark lens — well-in vs penalty, the decisive read."""

from __future__ import annotations

import sys
from datetime import date

from racing_edge.domain.mark import mark_read
from racing_edge.domain.models import Odds, PastRun, Race, Runner
from racing_edge.domain.tells import match_tells


def _hist(*pairs):
    # (position, official_rating) most-recent first
    return tuple(PastRun(date=date(2026, 1, i + 1), position=p, official_rating=o)
                 for i, (p, o) in enumerate(pairs))


def test_mark_read_well_in_and_penalty() -> None:
    # last won off 120, runs off 118 today -> WELL-IN (-2)
    wi = mark_read(118, _hist((3, 119), (1, 120)))
    assert wi.last_won == 120 and wi.delta == -2 and "WELL-IN" in wi.verdict
    # last won off 113, runs off 120 today -> +7lb, raised
    up = mark_read(120, _hist((1, 113)))
    assert up.delta == 7 and up.verdict == "+7lb"
    # never won -> can't judge
    none = mark_read(120, _hist((2, 110), (4, 108)))
    assert not none.known and none.verdict == ""
    # no mark on the card -> can't judge
    assert mark_read(None, _hist((1, 120))).delta is None


def test_well_in_tell_fires_only_when_not_raised() -> None:
    race = Race(race_id="r", course="Cartmel", off_time="15:50", date=date(2026, 6, 26),
                race_type="Handicap Chase", is_handicap=True)
    well_in = Runner(horse_id="w", horse="Gem", official_rating=118, odds=Odds(consensus=3.0))
    assert any("WELL-IN" in t for t in match_tells(well_in, race, _hist((3, 119), (1, 120))))
    # raised since its last win -> no well-in tell
    raised = Runner(horse_id="p", horse="Penalised", official_rating=125, odds=Odds(consensus=2.0))
    assert not any("WELL-IN" in t for t in match_tells(raised, race, _hist((1, 118))))


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
