"""The baselines every model must beat — the most important code in the package.

market_probs is THE benchmark: the de-vigged market probability. Benter's whole
lesson is that the public price is the strongest single predictor; an edge exists
only where a model beats it OUT OF SAMPLE. or_softmax is a second, dumber floor
(the official handicapper's opinion alone). If a form model can't beat these on
OOS log-loss, the complexity is decoration.

Pure functions over a single race's numbers. No fitting, no state.
"""

from __future__ import annotations

import math


def implied_probs(decimals: list[float | None]) -> list[float]:
    """Raw 1/decimal implied probabilities — these sum to >1 (the overround)."""
    return [1.0 / d if (d and d > 1.0) else 0.0 for d in decimals]


def market_probs(decimals: list[float | None]) -> list[float]:
    """De-vigged market win probabilities: normalise 1/decimal to sum to 1 across
    the field. The simple multiplicative overround removal — good enough as a
    benchmark; favourite-longshot bias is a known, small residual on top.

    Missing/invalid prices get the residual probability spread evenly, so the
    field always sums to 1 and the baseline never silently drops runners."""
    imp = implied_probs(decimals)
    total = sum(imp)
    n_missing = sum(1 for d in decimals if not (d and d > 1.0))
    n = len(decimals)
    if total <= 0:
        return [1.0 / n] * n if n else []
    if n_missing == 0:
        return [p / total for p in imp]
    # priced runners keep their share of (1 - reserved); unpriced split the rest
    reserved = min(0.5, 0.05 * n_missing)          # leave a little mass for unknowns
    priced_scale = (1.0 - reserved) / total
    out = []
    for p, d in zip(imp, decimals, strict=True):
        if d and d > 1.0:
            out.append(p * priced_scale)
        else:
            out.append(reserved / n_missing)
    s = sum(out)
    return [p / s for p in out] if s > 0 else [1.0 / n] * n


def softmax(values: list[float], temperature: float = 1.0) -> list[float]:
    """Numerically stable softmax — the within-race normaliser the whole package
    leans on (a race's probabilities must sum to 1)."""
    if not values:
        return []
    t = temperature if temperature > 0 else 1.0
    m = max(values)
    exps = [math.exp((v - m) / t) for v in values]
    s = sum(exps)
    return [e / s for e in exps] if s > 0 else [1.0 / len(values)] * len(values)


def or_softmax(ratings: list[int | None], temperature: float = 8.0) -> list[float]:
    """Official-Rating-only baseline: softmax over OR within the race. Temperature
    ~8 lb roughly matches the spread of a typical handicap; it is NOT tuned to
    results (that would be the overfitting trap) — just a sane second floor.
    Missing marks are imputed with the field mean so nobody is dropped."""
    present = [r for r in ratings if r is not None]
    fill = sum(present) / len(present) if present else 0.0
    vals = [float(r) if r is not None else fill for r in ratings]
    return softmax(vals, temperature)
