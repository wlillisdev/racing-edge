"""Assemble the training table — the leakage-free, race-grouped, priced dataset
the models fit on. This is the bridge from the live API to ml.features; it's the
one ML module that touches the data layer (the rest stay pure domain + numpy).

For each race it builds the point-in-time design matrix (history filtered to
strictly BEFORE the race), reads the winner and the obtainable prices from the
result, and emits a TrainingRace. Horse history is cached across the run exactly
as the backtester does — the API returns a horse's full career, and
features.point_in_time trims it per race, so caching is point-in-time safe.

The split helper is chronological ONLY (walk-forward): train on the earlier
period, test on the strictly later one. Never a random split — that leaks the
future into the past.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

import numpy as np

from racing_edge.data.client import RacingAPIError
from racing_edge.data.normalise import (
    past_runs_from_raw,
    racecards_from_raw,
    results_from_raw,
)
from racing_edge.domain.models import PastRun
from racing_edge.ml.evaluate import ScoredRace, ScoredRunner
from racing_edge.ml.features import design_matrix, point_in_time


@dataclass(frozen=True)
class Price:
    taken: float | None              # best available when the card was read (our consensus = best)
    sp: float | None                 # starting price
    bsp: float | None                # Betfair SP


@dataclass(frozen=True)
class TrainingRace:
    race_id: str
    date: date
    X: np.ndarray                    # (n_runners, n_features) point-in-time design matrix
    winner_idx: int                  # row of the winner; -1 if no completed winner in the result
    horse_ids: tuple[str, ...]
    prices: tuple[Price, ...]

    @property
    def has_winner(self) -> bool:
        return self.winner_idx >= 0


class _Fetcher(Protocol):
    def racecards(self, day: str = "today") -> dict: ...
    def results_by_date(self, date_str: str) -> dict: ...
    def horse_results(self, horse_id: str, limit: int = 12) -> list[dict]: ...


def assemble(client: _Fetcher, start: date, end: date, code: str = "jump",
             progress: Callable[[date, int], None] | None = None) -> list[TrainingRace]:
    """Walk start..end, emit one TrainingRace per race that has a result. History
    is cached per horse and trimmed point-in-time per race. `progress(day, n_so_far)`
    is called per day. Runnable on the deployment where the API creds live.

    NOTE: The Racing API's /results endpoint only serves the trailing ~12 months
    (older dates 422). Days outside that window are skipped (no labels available),
    so a multi-year range silently yields only the last ~12 months unless results
    are sourced elsewhere — the caller should clamp and warn."""
    cache: dict[str, tuple[PastRun, ...]] = {}
    out: list[TrainingRace] = []
    day = start
    while day <= end:
        ds = day.isoformat()
        races = [r for r in racecards_from_raw(client.racecards(ds)) if r.code == code]
        try:
            results = {res.race_id: res
                       for res in results_from_raw(client.results_by_date(ds))}
        except RacingAPIError as exc:
            if getattr(exc, "status_code", None) == 422:   # outside the result window
                results = {}                               # races this day go unlabelled
            else:
                raise
        for race in races:
            res = results.get(race.race_id)
            if res is None or not race.runners:
                continue
            hist_by_horse: dict[str, tuple[PastRun, ...]] = {}
            for r in race.runners:
                if r.horse_id not in cache:
                    rows = client.horse_results(r.horse_id)
                    cache[r.horse_id] = past_runs_from_raw(rows, r.horse_id)
                hist_by_horse[r.horse_id] = point_in_time(cache[r.horse_id], race.date)
            X = design_matrix(race, hist_by_horse)
            winner_idx = -1
            prices: list[Price] = []
            for i, r in enumerate(race.runners):
                rr = res.of(r.horse_id)
                if rr is not None and rr.won:
                    winner_idx = i
                prices.append(Price(taken=r.odds.consensus,
                                    sp=rr.sp_dec if rr else None,
                                    bsp=rr.bsp if rr else None))
            out.append(TrainingRace(
                race_id=race.race_id, date=race.date, X=X, winner_idx=winner_idx,
                horse_ids=tuple(r.horse_id for r in race.runners), prices=tuple(prices),
            ))
        if progress is not None:
            progress(day, len(out))
        day += timedelta(days=1)
    return out


def chronological_split(races: list[TrainingRace],
                        train_frac: float = 0.7) -> tuple[list[TrainingRace], list[TrainingRace]]:
    """Walk-forward split: earliest `train_frac` of races to train, the strictly
    later remainder to test. The only honest split for a time series."""
    ordered = sorted(races, key=lambda t: t.date)
    cut = int(len(ordered) * train_frac)
    return ordered[:cut], ordered[cut:]


def fit_pairs(races: list[TrainingRace]) -> list[tuple[np.ndarray, int]]:
    """(X, winner_idx) pairs for ConditionalLogit.fit — winnerless races dropped."""
    return [(t.X, t.winner_idx) for t in races if t.has_winner]


def to_scored_races(races: list[TrainingRace],
                    probs_per_race: list[np.ndarray]) -> list[ScoredRace]:
    """Pair model probabilities with outcomes + prices, ready for evaluate.evaluate.
    `probs_per_race[k]` is the model's within-race probability vector for races[k]."""
    out: list[ScoredRace] = []
    for t, probs in zip(races, probs_per_race, strict=True):
        runners = tuple(
            ScoredRunner(prob=float(probs[i]), won=(i == t.winner_idx),
                         taken=t.prices[i].taken, sp=t.prices[i].sp, bsp=t.prices[i].bsp)
            for i in range(len(t.horse_ids))
        )
        out.append(ScoredRace(runners=runners))
    return out
