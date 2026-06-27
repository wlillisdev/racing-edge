"""The lean ML challenge — the Wilkens (2026) experiment on our own data.

    python -m racing_edge.cli.ml --start 2016-11-01 --end 2026-03-31

Assembles the leakage-free, race-grouped, priced dataset (cached once), then runs
the only build the best study of our exact market says is worth running:

  market-only  vs  fundamental clogit  vs  augmented (clogit + market)
        -> isotonic calibration on a held-out slice
        -> value threshold + fractional Kelly
        -> judged by log-loss vs the market AND closing-line value

No XGBoost, no LambdaRank, no LLM features — Wilkens showed they don't pay on
returns. The verdicts to read: (1) does the augmented model beat the market on
out-of-sample log-loss? (2) do the value bets beat the close (positive CLV)?
If neither, the honest answer is 'the market is hard to beat' — and we stop.
"""

from __future__ import annotations

import argparse
import pickle
from datetime import datetime
from pathlib import Path

import numpy as np

from racing_edge.config import get_config
from racing_edge.data.client import get_client
from racing_edge.ml.baseline import market_probs
from racing_edge.ml.calibrate import IsotonicCalibrator, calibrate_race
from racing_edge.ml.condlogit import ConditionalLogit
from racing_edge.ml.dataset import (
    TrainingRace,
    assemble,
    chronological_split,
)
from racing_edge.ml.evaluate import Scorecard, evaluate
from racing_edge.ml.features import FEATURE_NAMES
from racing_edge.ml.value import RaceObs, Thresholds, run_strategy


def _market_col(t: TrainingRace) -> np.ndarray:
    """Log de-vigged market probability as an extra covariate (Benter's blend)."""
    m = market_probs([p.taken for p in t.prices])
    return np.log(np.clip(np.asarray(m), 1e-9, 1.0)).reshape(-1, 1)


def _augment(t: TrainingRace) -> np.ndarray:
    return np.hstack([t.X, _market_col(t)])


def _pairs(races: list[TrainingRace], augmented: bool) -> list[tuple[np.ndarray, int]]:
    return [((_augment(t) if augmented else t.X), t.winner_idx)
            for t in races if t.has_winner]


def _fit_calibrator(model: ConditionalLogit, races: list[TrainingRace],
                    augmented: bool) -> IsotonicCalibrator:
    raws: list[float] = []
    wons: list[float] = []
    for t in races:
        if not t.has_winner:
            continue
        raw = model.predict_race(_augment(t) if augmented else t.X)
        for i, p in enumerate(raw):
            raws.append(float(p))
            wons.append(1.0 if i == t.winner_idx else 0.0)
    return IsotonicCalibrator().fit(np.asarray(raws), np.asarray(wons))


def _cal_probs(model: ConditionalLogit, cal: IsotonicCalibrator,
               races: list[TrainingRace], augmented: bool) -> list[np.ndarray]:
    out = []
    for t in races:
        raw = model.predict_race(_augment(t) if augmented else t.X)
        out.append(calibrate_race(cal, raw))
    return out


def _scored(test: list[TrainingRace], probs: list[np.ndarray]) -> Scorecard:
    from racing_edge.ml.dataset import to_scored_races
    return evaluate(to_scored_races(test, probs))


def _row(name: str, s: Scorecard) -> str:
    return (f"  {name:<22}{s.log_loss or 0:>8.4f}{s.brier or 0:>8.4f}"
            f"{(s.top1_strike or 0) * 100:>8.1f}%")


def main() -> int:
    ap = argparse.ArgumentParser(description="Lean ML challenge: clogit+market vs the market, OOS.")
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--flat", action="store_true", help="flat instead of jumps")
    ap.add_argument("--rebuild", action="store_true", help="re-assemble even if cached")
    ap.add_argument("--ev-min", type=float, default=0.15)
    ap.add_argument("--edge-min", type=float, default=0.05)
    ap.add_argument("--kelly", type=float, default=0.10)
    args = ap.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()
    code = "flat" if args.flat else "jump"
    cache = Path(get_config().project_dir) / "data" / f"ml_dataset_{code}.pkl"
    cache.parent.mkdir(parents=True, exist_ok=True)

    if cache.exists() and not args.rebuild:
        print(f"  loading cached dataset {cache.name} ...", flush=True)
        races: list[TrainingRace] = pickle.loads(cache.read_bytes())
    else:
        print(f"  assembling {code} dataset {start} -> {end} (point-in-time) ...", flush=True)
        races = assemble(get_client(), start, end, code=code,
                         progress=lambda d, n: print(f"    {d}  {n} races", flush=True))
        cache.write_bytes(pickle.dumps(races))
        print(f"  cached {len(races)} races -> {cache.name}", flush=True)

    # walk-forward: train (fit) | calib (isotonic) | test (evaluate)
    train_all, test = chronological_split(races, 0.7)
    fit_races, calib_races = chronological_split(train_all, 0.75)
    if not _pairs(fit_races, False) or not calib_races or not test:
        print("  not enough data — widen the date range.")
        return 1
    print(f"\n  {len(races)} races | fit {len(fit_races)} | calib {len(calib_races)} "
          f"| test {len(test)}\n", flush=True)

    fund = ConditionalLogit(l2=1.0).fit(_pairs(fit_races, False), feature_names=FEATURE_NAMES)
    aug = ConditionalLogit(l2=1.0).fit(_pairs(fit_races, True),
                                       feature_names=[*FEATURE_NAMES, "market_logp"])
    cal_f = _fit_calibrator(fund, calib_races, False)
    cal_a = _fit_calibrator(aug, calib_races, True)

    mkt_probs = [np.asarray(market_probs([p.taken for p in t.prices])) for t in test]
    fund_probs = _cal_probs(fund, cal_f, test, False)
    aug_probs = _cal_probs(aug, cal_a, test, True)

    print("  PROBABILISTIC ACCURACY (out-of-sample, lower log-loss is better)")
    print(f"  {'variant':<22}{'logloss':>8}{'brier':>8}{'top1':>9}")
    print("  " + "-" * 47)
    print(_row("market-only", _scored(test, mkt_probs)))
    print(_row("fundamental (cal)", _scored(test, fund_probs)))
    print(_row("augmented (cal)", _scored(test, aug_probs)))

    thr = Thresholds(ev_min=args.ev_min, edge_min=args.edge_min)
    obs = [RaceObs(probs=aug_probs[k], taken=[p.taken for p in t.prices],
                   sp=[p.sp for p in t.prices], winner=t.winner_idx)
           for k, t in enumerate(test)]
    res = run_strategy(obs, thr, f=args.kelly)
    print(f"\n  VALUE STRATEGY (augmented model; EV>={thr.ev_min}, edge>={thr.edge_min}, "
          f"{thr.sp_min}<=SP<={thr.sp_max}, Kelly f={args.kelly})")
    flat = f"{(res.flat_roi or 0) * 100:+.1f}%"
    kel = f"{(res.kelly_roi or 0) * 100:+.1f}%"
    print(f"    bets {res.n_bets}/{res.n_races} races | win {res.win_pct or 0:.0f}% | "
          f"flat ROI {flat} | Kelly ROI {kel}")
    clv = f"{res.mean_clv * 100:+.1f}%" if res.mean_clv is not None else "—"
    print(f"    mean CLV {clv} | max drawdown {res.max_drawdown or 0:.1f} pt")

    print("\n  augmented coefficients (standardised, |largest| first):")
    for name, coef in aug.coefficients()[:8]:
        print(f"    {name:<22}{coef:+.3f}")
    print("\n  VERDICT: if augmented logloss <= market AND mean CLV > 0, there's a real,")
    print("  if marginal, edge. If not, the market wins — and per Wilkens, no extra")
    print("  model layer (XGBoost, LambdaRank, LLM) is expected to change that.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
