"""The evaluation harness — the part that matters most.

A model is judged on whether its probabilities are CALIBRATED and whether they
beat the market OUT OF SAMPLE, not on accuracy. (A classifier that calls every
horse a loser scores ~88% accuracy and is worthless — the brief's key warning.)

Everything here is race-grouped and price-aware. Feed it the OOS predictions
from a walk-forward split; it returns the honest scorecard. Pure: no model, no
fitting, no I/O — just arithmetic over scored races.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ScoredRunner:
    """One runner with a model probability and the realised outcome/price."""

    prob: float                       # model's win probability (within-race, sums to 1)
    won: bool
    position: int | None = None       # finishing position; None = did not complete
    taken: float | None = None        # decimal price obtainable when bet (best available)
    sp: float | None = None           # starting price (decimal) — for ROI@SP and CLV
    bsp: float | None = None          # Betfair SP (decimal) — the truest obtainable close


@dataclass(frozen=True)
class ScoredRace:
    runners: tuple[ScoredRunner, ...]

    @property
    def winner_idx(self) -> int | None:
        for i, r in enumerate(self.runners):
            if r.won:
                return i
        return None


@dataclass(frozen=True)
class Scorecard:
    n_races: int
    n_runners: int
    log_loss: float | None            # mean -log p(winner) per race; lower better; beat the market
    brier: float | None               # mean (p - won)^2 per runner; lower better
    top1_strike: float | None         # fraction of races where the model's top pick won
    top3_cover: float | None          # fraction where the winner was in the model's top 3
    mrr: float | None                 # mean reciprocal rank of the actual winner
    roi_sp: float | None              # flat-stake ROI backing top pick at SP
    roi_taken: float | None           # ... at the obtainable (taken) price
    roi_bsp: float | None             # ... at Betfair SP
    clv: float | None                 # mean closing-line value of top picks: taken/sp - 1
    n_top_priced: int                 # top picks that actually had a price (ROI/CLV denominator)


_EPS = 1e-12


def _normalise(probs: list[float]) -> list[float]:
    s = sum(p for p in probs if p > 0)
    if s <= 0:
        n = len(probs)
        return [1.0 / n] * n if n else []
    return [max(p, 0.0) / s for p in probs]


def log_loss(races: list[ScoredRace]) -> float | None:
    """Mean negative log-prob assigned to the actual winner, per race. THE metric:
    a well-calibrated model that knows the field minimises it. Compare to the
    market baseline's log-loss — beating it OOS is the whole game."""
    vals = []
    for race in races:
        wi = race.winner_idx
        if wi is None:
            continue
        probs = _normalise([r.prob for r in race.runners])
        vals.append(-math.log(max(probs[wi], _EPS)))
    return sum(vals) / len(vals) if vals else None


def brier(races: list[ScoredRace]) -> float | None:
    """Mean squared error of the win probabilities (one-vs-field). Lower is
    better-calibrated; complements log-loss without its tail sensitivity."""
    sq = []
    for race in races:
        probs = _normalise([r.prob for r in race.runners])
        for p, r in zip(probs, race.runners, strict=True):
            sq.append((p - (1.0 if r.won else 0.0)) ** 2)
    return sum(sq) / len(sq) if sq else None


def _ranks(race: ScoredRace) -> list[int]:
    """1 = highest model prob. Ties broken by original order (stable)."""
    order = sorted(range(len(race.runners)), key=lambda i: -race.runners[i].prob)
    rank = [0] * len(race.runners)
    for pos, i in enumerate(order, start=1):
        rank[i] = pos
    return rank


def top1_strike(races: list[ScoredRace]) -> float | None:
    hits = tot = 0
    for race in races:
        if race.winner_idx is None:
            continue
        tot += 1
        if _ranks(race)[race.winner_idx] == 1:
            hits += 1
    return hits / tot if tot else None


def top3_cover(races: list[ScoredRace]) -> float | None:
    hits = tot = 0
    for race in races:
        if race.winner_idx is None:
            continue
        tot += 1
        if _ranks(race)[race.winner_idx] <= 3:
            hits += 1
    return hits / tot if tot else None


def mrr(races: list[ScoredRace]) -> float | None:
    """Mean reciprocal rank of the actual winner — rewards getting the winner
    high in the order even when it isn't the top pick."""
    vals = []
    for race in races:
        wi = race.winner_idx
        if wi is None:
            continue
        vals.append(1.0 / _ranks(race)[wi])
    return sum(vals) / len(vals) if vals else None


def _price(r: ScoredRunner, basis: str) -> float | None:
    return {"sp": r.sp, "taken": r.taken, "bsp": r.bsp}.get(basis)


def roi_top_pick(races: list[ScoredRace], basis: str = "sp") -> tuple[float | None, int]:
    """Flat 1pt stake on each race's top model pick, returned at `basis` price.
    Returns (roi, n_bets_with_a_price). ROI = (returns - stakes) / stakes."""
    stake = ret = 0.0
    n = 0
    for race in races:
        if not race.runners:
            continue
        top = max(range(len(race.runners)), key=lambda i: race.runners[i].prob)
        r = race.runners[top]
        dec = _price(r, basis)
        if dec is None or dec <= 1.0:
            continue
        n += 1
        stake += 1.0
        if r.won:
            ret += dec
    if stake <= 0:
        return None, 0
    return (ret - stake) / stake, n


def clv_top_pick(races: list[ScoredRace]) -> tuple[float | None, int]:
    """Mean closing-line value of the top picks: taken/sp - 1. Positive means we
    consistently took a better price than the close — the leading edge indicator."""
    vals = []
    for race in races:
        if not race.runners:
            continue
        top = max(range(len(race.runners)), key=lambda i: race.runners[i].prob)
        r = race.runners[top]
        if r.taken and r.sp and r.sp > 1.0:
            vals.append(r.taken / r.sp - 1.0)
    return (sum(vals) / len(vals) if vals else None), len(vals)


def calibration(races: list[ScoredRace], bins: int = 10) -> list[tuple[float, float, int]]:
    """Reliability curve: for each probability band, (mean predicted, empirical
    win rate, n). A calibrated model tracks the diagonal. Returns non-empty bins."""
    edges = [i / bins for i in range(bins + 1)]
    acc: list[list[float]] = [[] for _ in range(bins)]
    obs: list[list[float]] = [[] for _ in range(bins)]
    for race in races:
        probs = _normalise([r.prob for r in race.runners])
        for p, r in zip(probs, race.runners, strict=True):
            b = min(bins - 1, int(p * bins))
            acc[b].append(p)
            obs[b].append(1.0 if r.won else 0.0)
    out = []
    for b in range(bins):
        if acc[b]:
            out.append((sum(acc[b]) / len(acc[b]), sum(obs[b]) / len(obs[b]), len(acc[b])))
    del edges
    return out


def evaluate(races: list[ScoredRace]) -> Scorecard:
    """The full scorecard for one set of (out-of-sample) scored races."""
    races = [r for r in races if r.runners]
    roi_sp, n_sp = roi_top_pick(races, "sp")
    roi_tk, _ = roi_top_pick(races, "taken")
    roi_bsp, _ = roi_top_pick(races, "bsp")
    clv, n_clv = clv_top_pick(races)
    return Scorecard(
        n_races=len(races),
        n_runners=sum(len(r.runners) for r in races),
        log_loss=log_loss(races),
        brier=brier(races),
        top1_strike=top1_strike(races),
        top3_cover=top3_cover(races),
        mrr=mrr(races),
        roi_sp=roi_sp,
        roi_taken=roi_tk,
        roi_bsp=roi_bsp,
        clv=clv,
        n_top_priced=max(n_sp, n_clv),
    )
