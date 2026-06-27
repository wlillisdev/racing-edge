"""Tests for the ML challenger layer — offline, no API. They prove the harness is
honest (a perfect model scores perfectly, a blind one doesn't) and that the
conditional-logit baseline actually learns a known signal out of sample.
"""

from __future__ import annotations

from datetime import date

import numpy as np

from racing_edge.domain.models import PastRun, Race, Runner
from racing_edge.ml.baseline import market_probs, or_softmax, softmax
from racing_edge.ml.condlogit import ConditionalLogit
from racing_edge.ml.evaluate import ScoredRace, ScoredRunner, evaluate
from racing_edge.ml.features import FEATURE_NAMES, design_matrix, point_in_time


# --------------------------------------------------------------------------- #
# baselines
# --------------------------------------------------------------------------- #
def test_market_probs_devigs_to_one() -> None:
    p = market_probs([2.0, 4.0, 5.0])          # de-vigged to sum to 1
    assert abs(sum(p) - 1.0) < 1e-9
    assert p[0] > p[1] > p[2]                  # shortest price = highest prob


def test_market_probs_handles_missing_price() -> None:
    p = market_probs([2.0, None, 6.0])
    assert abs(sum(p) - 1.0) < 1e-9
    assert all(x > 0 for x in p)               # nobody dropped to zero


def test_or_softmax_sums_to_one_and_orders() -> None:
    p = or_softmax([140, 130, None])           # None imputed to field mean (135)
    assert abs(sum(p) - 1.0) < 1e-9
    assert p[0] > p[1]


def test_softmax_uniform_on_equal() -> None:
    assert softmax([3.0, 3.0, 3.0]) == [1 / 3, 1 / 3, 1 / 3]


# --------------------------------------------------------------------------- #
# evaluation harness
# --------------------------------------------------------------------------- #
def _race(probs: list[float], winner: int, prices: list[float] | None = None) -> ScoredRace:
    prices = prices or [1.0 / p for p in probs]
    runners = tuple(
        ScoredRunner(prob=pr, won=(i == winner), position=(1 if i == winner else 2),
                     taken=prices[i], sp=prices[i], bsp=prices[i])
        for i, pr in enumerate(probs)
    )
    return ScoredRace(runners=runners)


def test_perfect_model_scores_perfectly() -> None:
    races = [_race([0.98, 0.01, 0.01], 0), _race([0.01, 0.98, 0.01], 1)]
    sc = evaluate(races)
    assert sc.top1_strike == 1.0
    assert sc.top3_cover == 1.0
    assert sc.mrr == 1.0
    assert sc.log_loss is not None and sc.log_loss < 0.1


def test_blind_model_is_not_rewarded() -> None:
    # always favours runner 0, but a different horse wins each time
    races = [_race([0.8, 0.1, 0.1], 1), _race([0.8, 0.1, 0.1], 2)]
    sc = evaluate(races)
    assert sc.top1_strike == 0.0
    assert sc.log_loss is not None and sc.log_loss > 1.0


def test_roi_and_clv_are_priced() -> None:
    # top pick wins at 3.0; taken better than sp -> positive CLV
    r = ScoredRace((ScoredRunner(prob=0.6, won=True, taken=3.2, sp=3.0, bsp=3.0),
                    ScoredRunner(prob=0.4, won=False, taken=2.0, sp=2.0)))
    sc = evaluate([r])
    assert sc.roi_sp is not None and sc.roi_sp > 1.0     # backed a 3.0 winner at 1pt
    assert sc.clv is not None and sc.clv > 0


# --------------------------------------------------------------------------- #
# conditional logit — learns a known signal out of sample
# --------------------------------------------------------------------------- #
def _synth(rng: np.random.Generator, beta: np.ndarray, n_races: int):
    races = []
    for _ in range(n_races):
        n = int(rng.integers(5, 12))
        X = rng.normal(size=(n, len(beta)))
        p = softmax(list(X @ beta))
        w = int(rng.choice(n, p=p))
        races.append((X, w))
    return races


def test_condlogit_recovers_signal_out_of_sample() -> None:
    rng = np.random.default_rng(0)
    beta_true = np.array([1.6, -1.1, 0.6, 0.0])
    train = _synth(rng, beta_true, 500)
    test = _synth(rng, beta_true, 200)

    model = ConditionalLogit(l2=1.0).fit(train, feature_names=["a", "b", "c", "d"])
    assert model.converged_
    # signs of the strong features recovered
    assert model.beta_ is not None
    assert model.beta_[0] > 0 and model.beta_[1] < 0

    # beats a uniform (no-information) model on out-of-sample log-loss
    model_ll = uniform_ll = 0.0
    for X, w in test:
        p = model.predict_race(X)
        model_ll += -np.log(max(p[w], 1e-12))
        uniform_ll += -np.log(1.0 / len(X))
    assert model_ll / len(test) < uniform_ll / len(test)

    # predictions are a valid within-race distribution
    p = model.predict_race(test[0][0])
    assert abs(p.sum() - 1.0) < 1e-9


def test_condlogit_top_feature_first_in_coefficients() -> None:
    rng = np.random.default_rng(1)
    beta_true = np.array([2.0, 0.1, 0.1])
    model = ConditionalLogit(l2=0.5).fit(_synth(rng, beta_true, 400),
                                         feature_names=["strong", "weak1", "weak2"])
    assert model.coefficients()[0][0] == "strong"


# --------------------------------------------------------------------------- #
# features — point-in-time + shape
# --------------------------------------------------------------------------- #
def _runner(hid: str, ofr: int) -> Runner:
    return Runner(horse_id=hid, horse=hid.upper(), official_rating=ofr, rpr=ofr + 5,
                  age=7, weight_lbs=150, days_since_run=21)


def test_point_in_time_drops_future_runs() -> None:
    hist = (PastRun(date=date(2026, 1, 1), position=1),
            PastRun(date=date(2026, 3, 1), position=2))
    kept = point_in_time(hist, as_of=date(2026, 2, 1))
    assert len(kept) == 1 and kept[0].date == date(2026, 1, 1)


def test_design_matrix_shape_and_centring() -> None:
    race = Race(race_id="r1", course="Kelso", off_time="14:00", date=date(2026, 2, 1),
                race_type="Chase", distance_f=20.0, going="Soft",
                runners=(_runner("a", 140), _runner("b", 130)))
    hist = {
        "a": (PastRun(date=date(2026, 1, 1), position=2, going="Soft", distance_f=20.0,
                      course="Kelso", field_size=10),),
        "b": (),
    }
    X = design_matrix(race, hist)
    assert X.shape == (2, len(FEATURE_NAMES))
    # or_minus_fieldmean is re-centred: with two present marks it sums to ~0
    j = FEATURE_NAMES.index("or_minus_fieldmean")
    assert abs(X[:, j].sum()) < 1e-9
    # horse 'a' placed on Soft over 20f at Kelso -> all three proven flags fire
    for name in ("going_proven", "trip_proven", "course_proven"):
        assert X[0, FEATURE_NAMES.index(name)] == 1.0
        assert X[1, FEATURE_NAMES.index(name)] == 0.0
