# ML challenger layer — roadmap

The machine-learning work runs **alongside** the owner's method, never replacing
it, and has to **prove itself by historical replay** before it influences a thing.
This file is the plan and the discipline that keeps it from becoming "a more
elaborate way to overfit."

## The one rule that decides everything

**A race is a competition, not N independent rows.** Every model scores a runner
*relative to its rivals* (softmax / rank within the race group) so the field's
probabilities sum to 1. The naive "every horse is its own row, predict win=0/1"
design — which most public repos use — is the mistake we do **not** repeat.

## The benchmark to beat: the market, out of sample

`ml/baseline.market_probs` is the de-vigged market probability. Benter's lesson,
and the thread that ties this back to all our CLV work: **the public price is the
strongest single predictor.** A form model that can't beat market-only on
out-of-sample **log-loss** has no edge — that's the same verdict as the CLV work,
measured one layer earlier (at the probability, before the price). `or_softmax`
is a second, dumber floor (the handicapper's mark alone).

## Build order (deliberate — simplest first)

This is the order *because* of the rule "if a complex model can't beat the
transparent baseline OOS, the complexity isn't helping," not despite it.

1. **Market-only baseline** — `ml/baseline.market_probs`. ✅ built + tested
2. **OR-only baseline** — `ml/baseline.or_softmax`. ✅ built + tested
3. **Conditional logit (Model A)** — `ml/condlogit.ConditionalLogit`. ✅ built +
   tested. Benter / Bolton–Chapman style; readable coefficients so we can check
   signs and catch leakage. **This is the baseline B and C must beat.**
4. **XGBoost calibrated (Model B)** — *not yet.* Earns its place only if it beats
   A out of sample. Needs `xgboost` + isotonic/Platt calibration. Consumes the
   **same** `features.design_matrix`, then normalise scores within race.
5. **LightGBM LambdaRank (Model C)** — *not yet.* Race = one group; finishing
   position = relevance. Excellent ranking, but its raw scores are **not**
   probabilities — needs a separate calibration stage before any value/edge read.
6. **Market-movement model** — *much later, separate.* Betfair price-path features
   (steamer vs drift, volume). Kept apart from the form model on purpose, or the
   price overwhelms every racing feature and we've just rebuilt a favourite-picker.

## How it's judged — `ml/evaluate.py`

Never accuracy (a model that calls everything a loser scores ~88% and is
worthless). The scorecard, on a **walk-forward OOS split**:

- **log-loss, Brier** — calibration (vs the market baseline)
- **calibration-by-band** — does predicted 30% win ~30% of the time?
- **top-1 strike, top-3 cover, MRR** — ranking quality
- **ROI at SP / taken / BSP, CLV** — money at *obtainable* prices

## The leakage discipline — `ml/features.py`

`point_in_time(history, as_of=race.date)` is called **before** features are built;
no feature reads the race being predicted. The market price is deliberately **not**
a form feature. Walk-forward only: train on the past, test on the strictly later
period, roll forward — never a random split.

## The binding constraint: data (the hard 80%)

The models are easy; assembling a leakage-free, race-grouped historical dataset
**with obtainable prices** (SP from results, BSP ideally) is the real work. The
Racing API `/results` carries `sp_dec` and `bsp`, so the price join is feasible;
the cost is the API budget to walk several seasons of cards + each runner's prior
form, point-in-time. **Decision still open:** how much history, and which price
basis (SP now; BSP needs a Betfair historical join later).

## Running it (on the deployment, where `.env` + API live)

The package is offline-tested here; the real fit happens where the data is.
`pip install -e '.[ml]'`, assemble the dataset with point-in-time features +
results, then fit `ConditionalLogit`, score the held-out later season, and read
`evaluate.evaluate(...)` against `baseline.market_probs`. If A doesn't beat the
market OOS, **stop** — don't reach for B and C to rescue it. That's the trap.
