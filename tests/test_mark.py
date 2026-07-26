"""Tests for the handicap mark lens — well-in vs penalty, the decisive read."""

from __future__ import annotations

import sys
from datetime import date

from racing_edge.domain.mark import mark_read
from racing_edge.domain.models import Odds, PastRun, Race, Runner
from racing_edge.domain.tells import match_tells


def _hist(*pairs):
    # (position, official_rating) most-recent first — typed, like the live feed:
    # the sacred mark (and now the tells too) refuse a blank-typed win as anchor
    return tuple(PastRun(date=date(2026, 1, i + 1), position=p, official_rating=o,
                         race_type="Chase")
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


def test_the_anchor_win_carries_its_class_and_the_label_says_up_in_grade() -> None:
    """The master, 2026-07-26: 'well-in can mean nothing if he is up in grade' — the
    mark now remembers WHERE it was earned, and the well-in label says so out loud
    when today's race is a higher class than the win that set the anchor."""
    from racing_edge.domain.mark import mark_read
    from racing_edge.domain.models import Odds, Race, Runner
    from racing_edge.selection.conviction import conviction
    hist = (PastRun(date=date(2026, 6, 1), position=1, official_rating=70,
                    race_type="Flat", race_class=6),)
    mr = mark_read(68, hist, code="flat")
    assert mr.win_class == 6 and mr.delta == -2
    race = Race(race_id="r", course="Thirsk", off_time="3:00", date=date(2026, 7, 1),
                race_type="Flat", is_handicap=True, race_class=4)
    c = conviction(Runner(horse_id="a", horse="Climber", official_rating=68,
                          odds=Odds(consensus=5.0)), race, hist,
                   market_rank=2, field_size=8)
    assert any("UP IN GRADE — won in Cl6, today Cl4" in a for a in c.aligned)
    # same class or a drop stays clean
    race5 = Race(race_id="r", course="Thirsk", off_time="3:00", date=date(2026, 7, 1),
                 race_type="Flat", is_handicap=True, race_class=6)
    c2 = conviction(Runner(horse_id="a", horse="Climber", official_rating=68,
                           odds=Odds(consensus=5.0)), race5, hist,
                    market_rank=2, field_size=8)
    assert not any("UP IN GRADE" in a for a in c2.aligned)
