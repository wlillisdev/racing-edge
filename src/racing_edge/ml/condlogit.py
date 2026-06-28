"""Conditional logistic regression — the transparent baseline (Benter / Bolton-
Chapman). The model EVERY heavier learner must out-perform out of sample before
it earns its complexity.

For race r with runner feature vectors x_i, the win probability is a softmax over
the field:  P(i wins) = exp(x_i·β) / Σ_j exp(x_j·β).  So probabilities are
competitive by construction (sum to 1 within the race), and β is a single, small,
readable vector — we can check the model learned sensible signs (higher OR → more
likely; longer layoff → less) and spot leakage by an implausibly huge coefficient.

Fit by Newton-Raphson on the L2-penalised negative log-likelihood (convex; a
dozen iterations). Pure numpy. No intercept: a constant feature cancels in the
within-race softmax, so conditional logit has none by design.
"""

from __future__ import annotations

import numpy as np


class ConditionalLogit:
    def __init__(self, l2: float = 1.0) -> None:
        self.l2 = l2
        self.beta_: np.ndarray | None = None
        self.mean_: np.ndarray | None = None
        self.std_: np.ndarray | None = None
        self.feature_names_: list[str] = []
        self.n_iter_ = 0
        self.converged_ = False

    # --- internals -------------------------------------------------------- #
    @staticmethod
    def _softmax(eta: np.ndarray) -> np.ndarray:
        e = np.exp(eta - eta.max())
        s = e.sum()
        return e / s if s > 0 else np.full_like(eta, 1.0 / len(eta))

    def _standardise(self, races: list[tuple[np.ndarray, int]]) -> list[tuple[np.ndarray, int]]:
        allrows = np.vstack([X for X, _ in races])
        self.mean_ = allrows.mean(axis=0)
        std = allrows.std(axis=0)
        std[std < 1e-8] = 1.0                      # don't blow up constant columns
        self.std_ = std
        return [((X - self.mean_) / self.std_, w) for X, w in races]

    # --- public ----------------------------------------------------------- #
    def fit(self, races: list[tuple[np.ndarray, int]],
            feature_names: list[str] | None = None,
            max_iter: int = 50, tol: float = 1e-6) -> ConditionalLogit:
        """`races`: one (X, winner_idx) per race, X shape (n_runners, n_features),
        winner_idx the row of the horse that won. Races without a recorded winner
        (winner_idx < 0) are skipped."""
        races = [(np.asarray(X, dtype=float), w) for X, w in races if w is not None and w >= 0]
        if not races:
            raise ValueError("no races with a recorded winner to fit on")
        d = races[0][0].shape[1]
        self.feature_names_ = feature_names or [f"f{i}" for i in range(d)]
        std_races = self._standardise(races)
        beta = np.zeros(d)
        eye = np.eye(d)
        self.converged_ = False
        for it in range(1, max_iter + 1):
            grad = np.zeros(d)
            hess = np.zeros((d, d))
            for X, w in std_races:
                eta = X @ beta
                p = self._softmax(eta)
                xbar = p @ X                       # E_p[x]
                grad -= (X[w] - xbar)              # -(x_winner - E_p[x])
                hess += (X * p[:, None]).T @ X - np.outer(xbar, xbar)
            grad += self.l2 * beta
            hess += self.l2 * eye
            step = np.linalg.solve(hess, grad)
            beta -= step
            self.n_iter_ = it
            if np.linalg.norm(step) < tol:
                self.converged_ = True
                break
        self.beta_ = beta
        return self

    def predict_race(self, X: np.ndarray) -> np.ndarray:
        """Win probabilities for one race's runners (rows), summing to 1."""
        if self.beta_ is None or self.mean_ is None or self.std_ is None:
            raise RuntimeError("model is not fitted")
        Xs = (np.asarray(X, dtype=float) - self.mean_) / self.std_
        return self._softmax(Xs @ self.beta_)

    def coefficients(self) -> list[tuple[str, float]]:
        """Standardised coefficients, largest magnitude first — read these to
        sanity-check signs and catch leakage (a freakishly large weight)."""
        if self.beta_ is None:
            raise RuntimeError("model is not fitted")
        pairs = list(zip(self.feature_names_, (float(b) for b in self.beta_), strict=True))
        return sorted(pairs, key=lambda kv: -abs(kv[1]))
