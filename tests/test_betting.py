"""Tests for the betting layer — value range, flat staking, singles only."""

from __future__ import annotations

import sys
from datetime import date

from racing_edge.betting.bet import flat_stake, is_bettable, make_bet, value_read
from racing_edge.betting.policy import BettingPolicy
from racing_edge.domain.models import Runner
from racing_edge.selection.case import Case

_POLICY = BettingPolicy(bank=1000.0, stake_pct=0.005, value_min=2.0, value_max=10.0, ew_min=5.0)


def _case() -> Case:
    return Case(runner=Runner(horse_id="H", horse="Bishopton"), signals=(), score=12.0, vetoed=False)


def test_value_read() -> None:
    assert value_read(1.8, _POLICY) == "no value — odds-on"
    assert value_read(4.0, _POLICY) == "in the value range"
    assert value_read(15.0, _POLICY).startswith("longshot")
    assert value_read(None, _POLICY) == "no price"


def test_is_bettable() -> None:
    assert is_bettable(4.0, _POLICY) is True
    assert is_bettable(1.5, _POLICY) is False     # odds-on
    assert is_bettable(20.0, _POLICY) is False    # longshot
    assert is_bettable(None, _POLICY) is False


def test_flat_stake() -> None:
    assert flat_stake(_POLICY) == 5.0             # 0.5% of 1000


def test_make_bet_single_in_band() -> None:
    bet = make_bet(_case(), 4.0, _POLICY)
    assert bet is not None
    assert bet.kind == "single" and bet.stake == 5.0 and bet.each_way is False


def test_make_bet_each_way_at_bigger_price() -> None:
    bet = make_bet(_case(), 6.0, _POLICY)
    assert bet is not None and bet.each_way is True


def test_make_bet_passes_out_of_band() -> None:
    assert make_bet(_case(), 1.5, _POLICY) is None     # odds-on
    assert make_bet(_case(), 25.0, _POLICY) is None    # longshot
    assert make_bet(_case(), None, _POLICY) is None


def test_kelly_off_by_default() -> None:
    assert BettingPolicy().kelly_enabled is False
    _ = date  # keep import tidy


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
