"""Race-grouped, point-in-time feature engineering — the leakage-critical 80%.

The cardinal rule (the brief's `.shift(1)` discipline): a runner's features may use
ONLY information that existed before the race went off. History is filtered with
`point_in_time(history, as_of=race.date)` BEFORE features are built; nothing here
reads the result of the race being predicted. The market price is deliberately
NOT a form feature — it's the benchmark (see baseline.market_probs), and folding
it in turns the form model into a dressed-up favourite-picker.

design_matrix turns a Race + each horse's prior runs into an (n_runners, D) array
aligned to race.runners, ready for ConditionalLogit (and later XGBoost/LambdaRank,
which consume the very same matrix — one feature definition, every model).
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np

from racing_edge.domain.models import PastRun, Race, Runner
from racing_edge.domain.units import going_band

FEATURE_NAMES: list[str] = [
    "official_rating", "rpr", "or_minus_fieldmean", "log1p_days_since", "age",
    "weight_lbs", "claim_lbs", "headgear_first_time", "wind_op", "trainer_sr14",
    "hist_runs", "hist_win_rate", "hist_place_rate", "hist_mean_prb",
    "last_pos_inv", "going_proven", "trip_proven", "course_proven",
]


def point_in_time(history: tuple[PastRun, ...], as_of: date) -> tuple[PastRun, ...]:
    """Keep only runs STRICTLY before `as_of` — the single guard against the most
    common backtest lie. Call this before building features, always."""
    return tuple(h for h in history if h.date < as_of)


def _prb(history: tuple[PastRun, ...]) -> float:
    runs = [(h.position, h.field_size) for h in history if h.field_size and h.field_size >= 2]
    if not runs:
        return 0.5
    vals = [0.0 if pos is None else max(0.0, min(1.0, (fs - pos) / (fs - 1))) for pos, fs in runs]
    return sum(vals) / len(vals)


def _proven(history: tuple[PastRun, ...], race: Race) -> tuple[float, float, float]:
    """(going_proven, trip_proven, course_proven) — placed (top 3) under matching
    conditions before. Point-in-time; uses only past runs."""
    band = race.going_band
    going = trip = course = 0.0
    for h in history:
        placed = h.position is not None and h.position <= 3
        if not placed:
            continue
        if band and h.going and going_band(h.going) == band:
            going = 1.0
        if race.distance_f and h.distance_f and abs(h.distance_f - race.distance_f) <= 1.0:
            trip = 1.0
        if race.course and h.course and h.course == race.course:
            course = 1.0
    return going, trip, course


def _runner_row(runner: Runner, history: tuple[PastRun, ...],
                race: Race) -> dict[str, float | None]:
    """Raw per-runner features; OR/RPR/weight left as None when missing so the
    race-level imputer can fill them with the field mean (not a global constant)."""
    runs = len(history)
    wins = sum(1 for h in history if h.won)
    places = sum(1 for h in history if h.placed)
    sr14 = ((runner.trainer_14d_wins or 0) / runner.trainer_14d_runs
            if runner.trainer_14d_runs else 0.0)
    last_pos = history[0].position if history and history[0].position else None
    return {
        "official_rating": float(runner.official_rating) if runner.official_rating else None,
        "rpr": float(runner.rpr) if runner.rpr else None,
        "or_minus_fieldmean": float(runner.official_rating) if runner.official_rating else None,
        "log1p_days_since": math.log1p(runner.days_since_run) if runner.days_since_run else 0.0,
        "age": float(runner.age) if runner.age else None,
        "weight_lbs": float(runner.weight_lbs) if runner.weight_lbs else None,
        "claim_lbs": float(runner.claim_lbs or 0),
        "headgear_first_time": 1.0 if runner.headgear_first_time else 0.0,
        "wind_op": 1.0 if runner.wind_surgery else 0.0,
        "trainer_sr14": float(sr14),
        "hist_runs": float(min(runs, 20)),
        "hist_win_rate": wins / runs if runs else 0.0,
        "hist_place_rate": places / runs if runs else 0.0,
        "hist_mean_prb": _prb(history),
        "last_pos_inv": 1.0 / last_pos if last_pos else 0.0,
        "going_proven": _proven(history, race)[0],
        "trip_proven": _proven(history, race)[1],
        "course_proven": _proven(history, race)[2],
    }


def _field_mean(rows: list[dict[str, float | None]], key: str) -> float:
    vals = [r[key] for r in rows if r[key] is not None]
    return float(sum(vals) / len(vals)) if vals else 0.0  # type: ignore[arg-type]


def design_matrix(race: Race,
                  history_by_horse: dict[str, tuple[PastRun, ...]]) -> np.ndarray:
    """(n_runners, D) feature matrix aligned to race.runners. `history_by_horse`
    must already be point-in-time (filter with point_in_time first). Missing
    OR/RPR/age/weight are imputed with the field mean; `or_minus_fieldmean` is
    re-centred so the model sees each horse's mark RELATIVE to today's field."""
    rows = [_runner_row(r, history_by_horse.get(r.horse_id, ()), race) for r in race.runners]
    impute = {k: _field_mean(rows, k) for k in ("official_rating", "rpr", "age", "weight_lbs",
                                                "or_minus_fieldmean")}
    or_mean = impute["or_minus_fieldmean"]
    out = np.zeros((len(rows), len(FEATURE_NAMES)))
    for i, row in enumerate(rows):
        for j, name in enumerate(FEATURE_NAMES):
            v = row[name]
            if v is None:
                v = impute.get(name, 0.0)
            if name == "or_minus_fieldmean":
                mark = row["official_rating"]
                v = (mark if mark is not None else or_mean) - or_mean
            out[i, j] = v
    return out
