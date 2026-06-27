"""A bet — a single, staked flat and small, at the price you can actually take.

Selection says which horse the method likes; betting decides whether the PRICE
is worth taking and how much. Singles only — the Yankee lesson (short-priced
multiples lose even on winning days). No bet is a valid, frequent answer.
"""

from __future__ import annotations

from dataclasses import dataclass

from racing_edge.betting.policy import BettingPolicy
from racing_edge.selection.case import Case


@dataclass(frozen=True)
class Bet:
    horse_id: str
    horse: str
    price: float          # the best/early price taken — NOT SP
    stake: float
    each_way: bool = False
    kind: str = "single"  # always a single — short multiples bleed


def value_read(price: float | None, policy: BettingPolicy) -> str:
    if price is None:
        return "no price"
    if price < policy.value_min:
        return "no value — odds-on"
    if price > policy.value_max:
        return "longshot — the bleed zone, pass"
    return "in the value range"


def is_bettable(price: float | None, policy: BettingPolicy) -> bool:
    return price is not None and policy.value_min <= price <= policy.value_max


def flat_stake(policy: BettingPolicy) -> float:
    """Flat fraction of bank. Kelly stays off until an edge is proven — sizing an
    unproven edge is the fastest way to give it back."""
    return round(policy.bank * policy.stake_pct, 2)


def make_bet(case: Case, price: float | None, policy: BettingPolicy) -> Bet | None:
    """A single bet on the pick IF the price is in the value range, else no bet."""
    if not is_bettable(price, policy):
        return None
    assert price is not None
    return Bet(
        horse_id=case.runner.horse_id,
        horse=case.runner.horse,
        price=round(price, 2),
        stake=flat_stake(policy),
        each_way=price >= policy.ew_min,
    )
