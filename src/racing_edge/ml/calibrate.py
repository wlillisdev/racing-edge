"""Isotonic probability calibration — the step Wilkens (2026) and Benter both lean
on, and the one our first build lacked.

A model can rank runners well yet be mis-scaled: it says 30% when such runners win
25% of the time. Calibration fixes the *scale* without touching the *order*. We fit
a monotonic (non-decreasing) map from raw probability to empirical win frequency by
the Pool-Adjacent-Violators algorithm, on a held-out slice the base model never
trained on (otherwise the calibration is itself overfit). Isotonic beats Platt when
there's enough data and the miscalibration isn't a clean sigmoid — the racing case.

Pure numpy. Fit on (raw_prob, won) pairs; apply, then renormalise within each race
so the field still sums to 1.
"""

from __future__ import annotations

import numpy as np


def _pav(y: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Pool-Adjacent-Violators: the monotonic non-decreasing least-squares fit to y
    (weights w), returned per input position. O(n)."""
    vals: list[float] = []
    wts: list[float] = []
    cnts: list[int] = []
    for yi, wi in zip(y, w, strict=True):
        vals.append(float(yi))
        wts.append(float(wi))
        cnts.append(1)
        while len(vals) > 1 and vals[-2] > vals[-1]:
            v2, w2, c2 = vals.pop(), wts.pop(), cnts.pop()
            v1, w1, c1 = vals.pop(), wts.pop(), cnts.pop()
            vals.append((v1 * w1 + v2 * w2) / (w1 + w2))
            wts.append(w1 + w2)
            cnts.append(c1 + c2)
    out = np.empty(len(y))
    i = 0
    for v, c in zip(vals, cnts, strict=True):
        out[i:i + c] = v
        i += c
    return out


class IsotonicCalibrator:
    def __init__(self) -> None:
        self.x_: np.ndarray | None = None   # sorted raw probs (interp knots)
        self.y_: np.ndarray | None = None   # calibrated values at those knots

    def fit(self, raw: np.ndarray, won: np.ndarray) -> IsotonicCalibrator:
        """Fit on HELD-OUT predictions (not used to train the base model)."""
        raw = np.asarray(raw, dtype=float)
        won = np.asarray(won, dtype=float)
        if len(raw) < 2:
            raise ValueError("need at least two points to calibrate")
        order = np.argsort(raw, kind="mergesort")
        xs = raw[order]
        ys = _pav(won[order], np.ones(len(won)))
        # collapse duplicate x to keep np.interp's knots strictly increasing
        uniq, idx = np.unique(xs, return_index=True)
        self.x_ = uniq
        self.y_ = ys[idx]
        return self

    def predict(self, raw: np.ndarray) -> np.ndarray:
        if self.x_ is None or self.y_ is None:
            raise RuntimeError("calibrator is not fitted")
        if len(self.x_) == 1:                       # degenerate: one knot
            return np.full(len(np.atleast_1d(raw)), self.y_[0])
        return np.interp(np.asarray(raw, dtype=float), self.x_, self.y_)


def calibrate_race(calibrator: IsotonicCalibrator, race_probs: np.ndarray) -> np.ndarray:
    """Apply calibration to one race's runners, then renormalise to sum to 1 so the
    field stays a valid distribution."""
    cal = np.clip(calibrator.predict(race_probs), 1e-9, 1.0)
    s = cal.sum()
    return cal / s if s > 0 else np.full(len(cal), 1.0 / len(cal))
