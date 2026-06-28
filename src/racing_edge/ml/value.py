"""Value selection + staking — turn calibrated probabilities into (rare) bets.

Straight from Wilkens (2026): back at most ONE runner per race, the highest
positive-EV one, and only when it clears strict thresholds — a minimum edge, a
minimum EV, a price floor (skip odds-on, where the market is sharpest and the
margin proportionally largest) and a price ceiling (skip longshots whose big price
manufactures a nominal EV from noise). Stake by FRACTIONAL Kelly, never full.

The expected outcome, per the paper, is a handful of bets a year and a marginal,
friction-sensitive edge — so NO BET (pick returns None) is the common, correct
output. Pure: numpy + the market baseline. No data layer, no model.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from racing_edge.ml.baseline import market_probs


@dataclass(frozen=True)
class Thresholds:
    """The value gate. Defaults echo Wilkens' grid (SP floor 2.0, real edge/EV)."""

    ev_min: float = 0.0          # minimum expected value  p*dec - 1
    edge_min: float = 0.0        # minimum probability edge  p_model - p_market
    sp_min: float = 2.0          # skip odds-on (market sharpest, margin largest)
    sp_max: float = 11.0         # skip longshots whose big price fakes EV from noise


@dataclass(frozen=True)
class RaceObs:
    """One race's calibrated model probs + obtainable/closing prices + outcome."""

    probs: np.ndarray            # calibrated win probs, sum ~1
    taken: list[float | None]    # best decimal available when bet
    sp: list[float | None]       # starting price (decimal) — for settle + CLV
    winner: int                  # index of winner; -1 if none completed


@dataclass(frozen=True)
class StrategyResult:
    n_races: int
    n_bets: int
    n_wins: int
    win_pct: float | None
    flat_roi: float | None       # (returns - stakes) / stakes, 1pt flat
    kelly_roi: float | None      # terminal/initial - 1 on a unit bankroll
    mean_clv: float | None       # mean taken/sp - 1 of the backed runners
    max_drawdown: float | None   # on the flat-staked equity curve


def expected_values(probs: np.ndarray, decimals: list[float | None]) -> np.ndarray:
    out = np.full(len(probs), -np.inf)
    for i, d in enumerate(decimals):
        if d and d > 1.0:
            out[i] = probs[i] * d - 1.0
    return out


def kelly_stake(p: float, dec: float, f: float) -> float:
    """Fractional-Kelly stake as a fraction of bankroll; never negative."""
    if dec <= 1.0:
        return 0.0
    edge = p * dec - 1.0
    return max(0.0, f * edge / (dec - 1.0))


def pick_value_bet(probs: np.ndarray, taken: list[float | None],
                   thr: Thresholds) -> int | None:
    """Index of the highest-EV runner clearing every gate, or None (NO BET)."""
    mkt = market_probs(taken)
    evs = expected_values(probs, taken)
    best: int | None = None
    best_ev = -np.inf
    for i, d in enumerate(taken):
        if not (d and thr.sp_min <= d <= thr.sp_max):
            continue
        if evs[i] < thr.ev_min:
            continue
        if probs[i] - mkt[i] < thr.edge_min:
            continue
        if evs[i] > best_ev:
            best_ev, best = evs[i], i
    return best


def run_strategy(races: list[RaceObs], thr: Thresholds, f: float = 0.10) -> StrategyResult:
    """Back one value runner per race (or none); settle flat and fractional-Kelly."""
    stake = ret = 0.0
    wins = bets = 0
    clvs: list[float] = []
    bankroll = 1.0
    equity = [0.0]                                   # cumulative flat P&L for drawdown
    for r in races:
        i = pick_value_bet(r.probs, r.taken, thr)
        if i is None:
            continue
        dec_t = r.taken[i]
        dec_s = r.sp[i]
        if not (dec_t and dec_t > 1.0):
            continue
        bets += 1
        won = (i == r.winner)
        # flat 1pt
        stake += 1.0
        ret += dec_t if won else 0.0
        equity.append(equity[-1] + ((dec_t - 1.0) if won else -1.0))
        # fractional Kelly on running bankroll
        frac = kelly_stake(float(r.probs[i]), dec_t, f)
        bankroll *= (1.0 + frac * (dec_t - 1.0)) if won else (1.0 - frac)
        if won:
            wins += 1
        if dec_t and dec_s and dec_s > 1.0:
            clvs.append(dec_t / dec_s - 1.0)
    peak = -np.inf
    dd = 0.0
    for e in equity:
        peak = max(peak, e)
        dd = max(dd, peak - e)
    return StrategyResult(
        n_races=len(races), n_bets=bets, n_wins=wins,
        win_pct=(100.0 * wins / bets if bets else None),
        flat_roi=((ret - stake) / stake if stake > 0 else None),
        kelly_roi=(bankroll - 1.0 if bets else None),
        mean_clv=(sum(clvs) / len(clvs) if clvs else None),
        max_drawdown=(dd if bets else None),
    )
