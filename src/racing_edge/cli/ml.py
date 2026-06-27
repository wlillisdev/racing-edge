"""The ML challenge — does the conditional-logit form model beat the market OOS?

    python -m racing_edge.cli.ml --start 2023-11-01 --end 2026-03-31
    python -m racing_edge.cli.ml --start 2023-11-01 --end 2026-03-31 --flat

Assembles the leakage-free, race-grouped, priced dataset (cached to disk so you
only pay the API cost once), splits it walk-forward (earlier train / later test),
fits Model A (conditional logit), and scores it on the held-out LATER season
against two baselines it must beat: the de-vigged market and OR-only.

The verdict is the log-loss column: if Model A doesn't beat the market out of
sample, STOP — don't reach for XGBoost to rescue it. That's the overfitting trap.
"""

from __future__ import annotations

import argparse
import pickle
from datetime import date, datetime
from pathlib import Path

from racing_edge.config import get_config
from racing_edge.data.client import get_client
from racing_edge.ml.baseline import market_probs, softmax
from racing_edge.ml.condlogit import ConditionalLogit
from racing_edge.ml.dataset import (
    TrainingRace,
    assemble,
    chronological_split,
    fit_pairs,
    to_scored_races,
)
from racing_edge.ml.evaluate import Scorecard, evaluate
from racing_edge.ml.features import FEATURE_NAMES


def _fmt(v: float | None, pct: bool = False, dp: int = 3) -> str:
    if v is None:
        return "   —"
    return f"{v * 100:+.1f}%" if pct else f"{v:.{dp}f}"


def _row(name: str, s: Scorecard) -> str:
    return (f"  {name:<16}{s.log_loss or 0:>8.3f}{s.brier or 0:>8.3f}"
            f"{_fmt(s.top1_strike, pct=True):>9}{_fmt(s.mrr):>8}"
            f"{_fmt(s.roi_sp, pct=True):>9}{_fmt(s.clv, pct=True):>9}")


def _scorecards(test: list[TrainingRace], model: ConditionalLogit) -> str:
    cl = to_scored_races(test, [model.predict_race(t.X) for t in test])
    mk = to_scored_races(test, [market_probs([p.taken for p in t.prices]) for t in test])
    orc = to_scored_races(
        test,
        [softmax(list(t.X[:, FEATURE_NAMES.index("official_rating")]), temperature=8.0)
         for t in test],
    )
    lines = [
        f"  {'model':<16}{'logloss':>8}{'brier':>8}{'top1':>9}{'MRR':>8}{'ROI@SP':>9}{'CLV':>9}",
        "  " + "-" * 65,
        _row("market (de-vig)", evaluate(mk)),
        _row("OR-only", evaluate(orc)),
        _row("cond-logit (A)", evaluate(cl)),
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="ML challenge: cond-logit vs the market, OOS.")
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--flat", action="store_true", help="flat instead of jumps")
    ap.add_argument("--train-frac", type=float, default=0.7)
    ap.add_argument("--rebuild", action="store_true", help="re-assemble even if cached")
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

        def _p(d: date, n: int) -> None:
            print(f"    {d}  {n} races so far", flush=True)

        races = assemble(get_client(), start, end, code=code, progress=_p)
        cache.write_bytes(pickle.dumps(races))
        print(f"  cached {len(races)} races -> {cache.name}", flush=True)

    train, test = chronological_split(races, args.train_frac)
    pairs = fit_pairs(train)
    print(f"\n  {len(races)} races  |  train {len(train)} ({len(pairs)} with a winner)  "
          f"|  test {len(test)}\n", flush=True)
    if not pairs or not test:
        print("  not enough data to fit/evaluate — widen the date range.")
        return 1

    model = ConditionalLogit(l2=1.0).fit(pairs, feature_names=FEATURE_NAMES)
    print(f"  cond-logit fitted ({model.n_iter_} Newton steps, "
          f"{'converged' if model.converged_ else 'capped'})\n")
    print(_scorecards(test, model))

    print("\n  cond-logit coefficients (standardised, |largest| first):")
    for name, coef in model.coefficients()[:10]:
        print(f"    {name:<22}{coef:+.3f}")
    print("\n  VERDICT: read the logloss column. cond-logit must beat 'market' there,")
    print("  out of sample, or there's no selection edge — and no XGBoost will add one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
