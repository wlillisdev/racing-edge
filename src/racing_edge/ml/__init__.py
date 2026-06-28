"""The machine-learning challenger layer — built ALONGSIDE the owner's method,
never replacing it, and forced to prove itself by historical replay.

Design rules, straight from the research brief and our own hard lessons:
  • A race is a competition, not N independent rows. Every model here scores a
    runner RELATIVE to its rivals (softmax / rank within the race group), so the
    field's probabilities sum to 1 by construction. No per-horse leakage of the
    "every horse independent" kind.
  • The benchmark to beat is the MARKET, out of sample. baseline.market_probs is
    the de-vigged market probability; a form model that can't beat it OOS on
    log-loss has no edge — the same verdict as our CLV work, one layer earlier.
  • Start transparent. condlogit (conditional logistic regression, Benter/Bolton-
    Chapman style) is the baseline whose coefficients we can read for sanity and
    leakage. XGBoost / LambdaRank only earn their place if they beat it OOS.
  • Judge on calibration + CLV, NOT accuracy. evaluate.py reports log-loss,
    Brier, calibration-by-band, top-1 strike, MRR and ROI/CLV at real prices.

This package depends only on numpy + the pure domain contracts. It never picks
for the owner and never emits a black-box score into the live method.
"""
