"""Tests for the daily card renderer — pure presentation."""

from __future__ import annotations

import sys
from datetime import date

from racing_edge.betting.bet import Bet
from racing_edge.domain.models import Race, Runner
from racing_edge.report.card import CardPick, DayCard, render_card
from racing_edge.selection.case import Case
from racing_edge.domain.signal import Signal


def _card_with_pick() -> DayCard:
    race = Race(race_id="r1", course="Kelso", off_time="14:40", date=date(2026, 1, 15),
                race_type="Chase", is_handicap=True, race_class=3, going="Soft")
    case = Case(runner=Runner(horse_id="H", horse="Bishopton"),
                signals=(Signal("well_in_proven", 5.0, "well in and ahead of the mark"),),
                score=5.0, vetoed=False)
    bet = Bet(horse_id="H", horse="Bishopton", price=3.5, stake=5.0)
    return DayCard(day=date(2026, 1, 15), code="jump",
                   picks=(CardPick(race=race, case=case, price=3.5, bet=bet),))


def test_render_shows_pick_reason_and_bet() -> None:
    out = render_card(_card_with_pick())
    assert "winter jumps" in out
    assert "BISHOPTON" in out
    assert "VALUE BET" in out and "£5.00" in out
    assert "well in and ahead of the mark" in out
    assert "Your eye, your call" in out


def test_render_no_picks() -> None:
    out = render_card(DayCard(day=date(2026, 1, 15), code="jump", picks=()))
    assert "No picks today" in out


def test_render_pick_out_of_value_range() -> None:
    race = Race(race_id="r", course="Ayr", off_time="15:00", date=date(2026, 1, 15),
                race_type="Hurdle", race_class=4, going="Heavy")
    case = Case(runner=Runner(horse_id="H", horse="Longshot"), signals=(), score=8.0, vetoed=False)
    card = DayCard(day=date(2026, 1, 15), code="jump",
                   picks=(CardPick(race=race, case=case, price=18.0, bet=None),))
    out = render_card(card)
    assert "out of the value range" in out and "VALUE BET" not in out


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
