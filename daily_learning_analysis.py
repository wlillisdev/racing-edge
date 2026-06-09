"""
daily_learning_analysis.py — Stage 3 of the daily closed-loop learning machine.

THE NIGHTLY FORENSIC LEARNER.

This script is the "learner" half of the supervised auto-tuner. It reads the
cumulative, labelled dataset produced by Stage 2 (data/learning_dataset.csv —
one row per labelled runner), analyses the most recent ROLLING 90-DAY window,
detects calibration drift, and *PROPOSES* (never applies) changes to the
model's tunable parameters defined in src/model_params.py.

It is deliberately conservative and READ-ONLY with respect to the live model:
    - It NEVER writes model_params.json.
    - It NEVER makes network or DB calls (pure local file analysis).
    - It uses ONLY the Python stdlib (csv, statistics, json, ...) plus
      src.helpers — it does NOT import pandas, even though the repo pins it,
      so that the nightly learner stays robust on a minimal environment.

What it computes over the 90-day window (guarding tiny samples — every metric
is annotated with a sample size and a confidence label, and NO proposal is
emitted unless its supporting sample size >= MIN_SAMPLE):

    a. SCORE CALIBRATION — win rate + ROI (mean pnl_1pt) + n per 5-pt score
       band. The lowest band whose win rate AND ROI are reliably positive
       informs `nap_min_score`.
    b. GRADE performance — win rate + ROI + n per grade (A / B+ / B / C / D),
       informing which grades are NAP-worthy and the grade_thresholds.
    c. SUB-SCORE ATTRIBUTION — for each of form / suitability / context /
       trainer / market / wisdom / ai_rating / pace_fit: Pearson correlation
       with `won` plus the winners-mean vs losers-mean delta. Which signals
       actually predict winners NOW.
    d. ODDS bracket performance — win rate + ROI + n by morning_price band,
       informing the odds gates (nap_min_odds / nap_max_odds).
    e. DRIFT — compares the most-recent ~30 days vs the prior ~60 days within
       the window for score-calibration win rate, flagging if the profitable
       "sweet-spot" band has shifted materially.

PARAMETER PROPOSALS (PROPOSE-ONLY — do NOT apply):
    Each proposal is a dict:
        {
          "target":         dotted key into src.model_params PARAM_BOUNDS
                            (e.g. "nap_min_score", "grade_thresholds.A"),
          "current_value":  effective current value (from get_params()),
          "proposed_value": clamped + step-capped new value,
          "direction":      "increase" | "decrease",
          "sample_size":    supporting n,
          "rationale":      human-readable evidence string,
          "confidence":     "low" | "medium" | "high",
        }
    SAFETY CONTRACT (mirrors the Stage-5 tuner's own clamps so the proposals
    file can never request anything illegal):
        - Every proposed_value is clamped to PARAM_BOUNDS[target].
        - The move from current_value is capped to +/- PARAM_MAX_STEP[target].
        - A proposal is only emitted when its sample_size >= MIN_SAMPLE AND the
          signal is meaningful AND the clamped move is non-trivial.

OUTPUTS:
    reports/daily_learning_<date>.txt   — readable forensic report.
    data/proposed_params_<date>.json    — machine-readable proposals for the
                                          Stage-5 tuner to consume:
        {
          "date": ...,
          "window_days": 90,
          "sample_size": <result rows in window>,
          "dataset_rows_in_window": <all rows in window>,
          "proposals": [ ... ],
        }

Exit codes:
    0 — report produced (INCLUDING the "no data yet" case).
    1 — only on a write error.

Usage:
    python daily_learning_analysis.py                # window ends today
    python daily_learning_analysis.py 2026-06-09     # window ends on a date

---------------------------------------------------------------------------
INTEGRATION (documented here — NOT implemented by this script):
---------------------------------------------------------------------------
This learner belongs in evening_audit_pipeline.py's PIPELINE_STEPS list. The
dataset MUST be labelled with outcomes first, so it is inserted AFTER the
outcome-join step (daily_outcome_join — Stage 2, which builds/updates
data/learning_dataset.csv) and BEFORE the future supervised tuner (Stage 5,
not built yet). Proposed insertion:

    PIPELINE_STEPS = [
        ("results_auditor",       "results_auditor.py",        []),
        ("performance_tracker",   "performance_tracker.py",    []),
        ("loser_autopsy_ai",      "loser_autopsy_ai.py",       []),
        ("daily_outcome_join",    "daily_outcome_join.py",     []),  # Stage 2 (labels dataset)
        ("daily_learning",        "daily_learning_analysis.py",[]),  # Stage 3 (THIS script — proposes)
        # ("param_tuner",         "param_tuner.py",            []),  # Stage 5 (applies, gated) — NOT built
        ("profit_report",         "profit_report.py",          []),
        ("email_audit",           "email_audit.py",            []),
    ]

The Stage-5 tuner (not built yet) will READ data/proposed_params_<date>.json,
re-validate each proposal against PARAM_BOUNDS / PARAM_MAX_STEP, apply ONLY the
gated, bounded changes, and persist them via src.model_params.write_params()
(which appends a reversible history entry and bumps the version). This learner
NEVER calls write_params — propose-only by design.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from src.helpers import data_path, log, report_path, today_str
from src.model_params import (
    DEFAULTS,
    PARAM_BOUNDS,
    PARAM_MAX_STEP,
    get_params,
)

# ---------------------------------------------------------------------------
# Tunable analysis constants
# ---------------------------------------------------------------------------

DATASET_FILENAME = "learning_dataset.csv"
WINDOW_DAYS = 90
RECENT_DAYS = 30          # most-recent slice for drift detection
PRIOR_DAYS = 60           # prior slice for drift detection (RECENT + PRIOR = WINDOW)
MIN_SAMPLE = 30           # NO proposal below this supporting sample size
MIN_BAND_N = 15           # min n for a single band to be "reliable" in calibration
EPSILON = 0.05            # ignore trivially small clamped moves

# 5-point score bands for calibration (ordered ascending by floor).
SCORE_BANDS: list[tuple[float, float, str]] = [
    (float("-inf"), 45.0, "<45"),
    (45.0, 50.0, "45-50"),
    (50.0, 55.0, "50-55"),
    (55.0, 60.0, "55-60"),
    (60.0, 65.0, "60-65"),
    (65.0, 70.0, "65-70"),
    (70.0, 75.0, "70-75"),
    (75.0, 80.0, "75-80"),
    (80.0, float("inf"), "80+"),
]

GRADES = ["A", "B+", "B", "C", "D"]

# Sub-score columns to attribute against `won`.
SUBSCORE_COLS = [
    "form_score",
    "suitability_score",
    "context_score",
    "trainer_score",
    "market_score",
    "wisdom_score",
    "ai_rating",
    "pace_fit",
]

# Odds brackets by morning_price (decimal). (low, high_inclusive, label)
ODDS_BRACKETS: list[tuple[float, float, str]] = [
    (1.0, 2.0, "<2.0 (odds-on)"),
    (2.0, 3.0, "2.0-3.0"),
    (3.0, 5.0, "3.0-5.0"),
    (5.0, 7.0, "5.0-7.0"),
    (7.0, 11.0, "7.0-11.0"),
    (11.0, float("inf"), "11.0+"),
]


# ---------------------------------------------------------------------------
# Parse guards — every numeric/bool field may be blank for unmatched rows.
# ---------------------------------------------------------------------------

def _f(v) -> Optional[float]:
    """Parse a float, returning None for blank/invalid (NEVER raises)."""
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s.lower() in ("none", "nan", "null"):
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _b(v) -> Optional[bool]:
    """Parse a bool from 'True'/'False'/1/0/etc. None if blank/unknown."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "1", "yes", "t", "y"):
        return True
    if s in ("false", "0", "no", "f", "n"):
        return False
    return None


def _parse_date(v) -> Optional[date]:
    if not v:
        return None
    s = str(v).strip()
    try:
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def _confidence(n: int) -> str:
    """Map a sample size to a coarse confidence label."""
    if n >= 100:
        return "high"
    if n >= MIN_SAMPLE:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Stats accumulator for a bucket of result rows.
# ---------------------------------------------------------------------------

class Bucket:
    """Win/ROI accumulator. Only rows with a usable `won` label are counted."""

    __slots__ = ("n", "wins", "places", "pnl", "n_pnl")

    def __init__(self) -> None:
        self.n = 0          # rows with a `won` label (the result-rows count)
        self.wins = 0
        self.places = 0
        self.pnl = 0.0      # sum of pnl_1pt where available
        self.n_pnl = 0      # rows that actually contributed pnl

    def record(self, won: Optional[bool], placed: Optional[bool],
               pnl: Optional[float]) -> None:
        if won is None:
            return
        self.n += 1
        if won:
            self.wins += 1
        if placed:
            self.places += 1
        if pnl is not None:
            self.pnl += pnl
            self.n_pnl += 1

    @property
    def win_pct(self) -> float:
        return (self.wins / self.n * 100.0) if self.n else 0.0

    @property
    def place_pct(self) -> float:
        return (self.places / self.n * 100.0) if self.n else 0.0

    @property
    def roi(self) -> float:
        """Mean pnl_1pt as a percentage (flat 1pt stakes)."""
        return (self.pnl / self.n_pnl * 100.0) if self.n_pnl else 0.0

    def as_dict(self) -> dict:
        return {
            "n": self.n,
            "wins": self.wins,
            "win_pct": round(self.win_pct, 2),
            "place_pct": round(self.place_pct, 2),
            "roi": round(self.roi, 2),
            "n_pnl": self.n_pnl,
        }


def _pearson(xs: list[float], ys: list[float]) -> Optional[float]:
    """Pearson correlation; None if undefined (n<2 or zero variance)."""
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0.0 or dy == 0.0:
        return None
    return num / (dx * dy)


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

def _load_dataset(path: str) -> list[dict]:
    rows: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                rows.append(row)
    except FileNotFoundError:
        return []
    except OSError as exc:
        log(f"daily_learning_analysis: cannot read {path} — {exc}", "WARNING")
        return []
    return rows


# ---------------------------------------------------------------------------
# Band helpers
# ---------------------------------------------------------------------------

def _score_band(score: Optional[float]) -> Optional[str]:
    if score is None:
        return None
    for lo, hi, label in SCORE_BANDS:
        if lo <= score < hi:
            return label
    return None


def _odds_band(price: Optional[float]) -> Optional[str]:
    if price is None or price <= 1.0:
        return None
    for lo, hi, label in ODDS_BRACKETS:
        if lo <= price < hi:
            return label
    return None


# ---------------------------------------------------------------------------
# Analyses (each returns (text_lines, structured_dict))
# ---------------------------------------------------------------------------

def analyse_score_calibration(rows: list[dict]) -> tuple[list[str], dict]:
    """Win rate + ROI per 5-pt band. Find lowest reliably-positive band."""
    buckets: dict[str, Bucket] = {b[2]: Bucket() for b in SCORE_BANDS}
    for r in rows:
        band = _score_band(_f(r.get("score")))
        if band is None:
            continue
        buckets[band].record(_b(r.get("won")), _b(r.get("placed")),
                             _f(r.get("pnl_1pt")))

    lines = [
        "=" * 78,
        "A. SCORE CALIBRATION (5-point bands, 90-day window)",
        "   Win rate + ROI (mean pnl_1pt) per band. Informs nap_min_score.",
        "=" * 78,
        f"  {'Band':<8} {'N':>5} {'Wins':>5} {'Win%':>7} {'ROI%':>8}  {'Confidence':<10}",
        "  " + "-" * 56,
    ]
    ordered = [b[2] for b in SCORE_BANDS]
    for label in ordered:
        bk = buckets[label]
        if bk.n == 0:
            continue
        if bk.n < MIN_BAND_N:
            lines.append(f"  {label:<8} {bk.n:>5} {bk.wins:>5} "
                         f"{bk.win_pct:>6.1f}% {bk.roi:>+7.1f}%  [!small]")
        else:
            lines.append(f"  {label:<8} {bk.n:>5} {bk.wins:>5} "
                         f"{bk.win_pct:>6.1f}% {bk.roi:>+7.1f}%  {_confidence(bk.n):<10}")

    # Lowest band whose win rate AND ROI are reliably positive (n>=MIN_BAND_N,
    # win_pct > 0, roi > 0). Its lower edge informs nap_min_score.
    lowest_good: Optional[tuple[float, str, Bucket]] = None
    for lo, hi, label in SCORE_BANDS:
        bk = buckets[label]
        if bk.n >= MIN_BAND_N and bk.win_pct > 0 and bk.roi > 0 and lo != float("-inf"):
            lowest_good = (lo, label, bk)
            break

    if lowest_good:
        lo, label, bk = lowest_good
        lines.append("")
        lines.append(f"  ► Lowest reliably-positive band: {label} "
                     f"(win {bk.win_pct:.1f}%, ROI {bk.roi:+.1f}%, n={bk.n})")
        lines.append(f"    → suggests nap_min_score near {lo:.0f}")
    else:
        lines.append("")
        lines.append("  ► No reliably-positive score band (insufficient data or no edge).")

    data = {
        "bands": {label: buckets[label].as_dict() for label in ordered
                  if buckets[label].n > 0},
        "lowest_positive_band_floor": lowest_good[0] if lowest_good else None,
        "lowest_positive_band_label": lowest_good[1] if lowest_good else None,
        "lowest_positive_band_n": lowest_good[2].n if lowest_good else 0,
    }
    return lines, data


def analyse_grades(rows: list[dict]) -> tuple[list[str], dict]:
    buckets: dict[str, Bucket] = {g: Bucket() for g in GRADES}
    for r in rows:
        g = (r.get("grade") or "").strip()
        if g not in buckets:
            continue
        buckets[g].record(_b(r.get("won")), _b(r.get("placed")),
                          _f(r.get("pnl_1pt")))

    lines = [
        "",
        "=" * 78,
        "B. GRADE PERFORMANCE (90-day window)",
        "   Which grades are NAP-worthy NOW. Informs grade_thresholds.",
        "=" * 78,
        f"  {'Grade':<6} {'N':>5} {'Wins':>5} {'Win%':>7} {'ROI%':>8}  {'Confidence':<10}",
        "  " + "-" * 54,
    ]
    for g in GRADES:
        bk = buckets[g]
        if bk.n == 0:
            lines.append(f"  {g:<6} {'0':>5}    —      —        —   no data")
            continue
        conf = _confidence(bk.n) if bk.n >= MIN_BAND_N else "[!small]"
        lines.append(f"  {g:<6} {bk.n:>5} {bk.wins:>5} "
                     f"{bk.win_pct:>6.1f}% {bk.roi:>+7.1f}%  {conf:<10}")

    data = {g: buckets[g].as_dict() for g in GRADES}
    return lines, {"grades": data}


def analyse_subscore_attribution(rows: list[dict]) -> tuple[list[str], dict]:
    """Pearson(sub-score, won) + winners-mean vs losers-mean delta."""
    result_rows = [r for r in rows if _b(r.get("won")) is not None]

    lines = [
        "",
        "=" * 78,
        "C. SUB-SCORE ATTRIBUTION — which signals predict winners NOW",
        "   Pearson r with `won` + winners-mean vs losers-mean delta.",
        "=" * 78,
        f"  {'Sub-score':<20} {'Pearson r':>10} {'Win avg':>9} {'Loss avg':>9} "
        f"{'Delta':>8} {'N':>6}",
        "  " + "-" * 66,
    ]

    attribution: dict[str, dict] = {}
    ranked: list[tuple[float, str]] = []
    for col in SUBSCORE_COLS:
        xs: list[float] = []
        ys: list[float] = []
        win_vals: list[float] = []
        loss_vals: list[float] = []
        for r in result_rows:
            v = _f(r.get(col))
            won = _b(r.get("won"))
            if v is None or won is None:
                continue
            xs.append(v)
            ys.append(1.0 if won else 0.0)
            (win_vals if won else loss_vals).append(v)

        n = len(xs)
        corr = _pearson(xs, ys) if n >= 2 else None
        w_avg = statistics.mean(win_vals) if win_vals else None
        l_avg = statistics.mean(loss_vals) if loss_vals else None
        delta = (w_avg - l_avg) if (w_avg is not None and l_avg is not None) else None

        attribution[col] = {
            "pearson": round(corr, 4) if corr is not None else None,
            "winners_avg": round(w_avg, 3) if w_avg is not None else None,
            "losers_avg": round(l_avg, 3) if l_avg is not None else None,
            "delta": round(delta, 3) if delta is not None else None,
            "n": n,
        }
        if corr is not None and n >= MIN_BAND_N:
            ranked.append((abs(corr), col))

        r_s = f"{corr:>+10.4f}" if corr is not None else f"{'—':>10}"
        wa = f"{w_avg:>9.2f}" if w_avg is not None else f"{'—':>9}"
        la = f"{l_avg:>9.2f}" if l_avg is not None else f"{'—':>9}"
        de = f"{delta:>+8.2f}" if delta is not None else f"{'—':>8}"
        lines.append(f"  {col:<20} {r_s} {wa} {la} {de} {n:>6}")

    ranked.sort(reverse=True)
    if ranked:
        lines.append("")
        lines.append(f"  ► Strongest current predictor: {ranked[0][1]} "
                     f"(|r|={ranked[0][0]:.4f})")
        if len(ranked) > 1:
            lines.append(f"  ► Weakest meaningful predictor: {ranked[-1][1]} "
                         f"(|r|={ranked[-1][0]:.4f})")

    return lines, {
        "subscore_attribution": attribution,
        "strongest_predictor": ranked[0][1] if ranked else None,
    }


def analyse_odds_brackets(rows: list[dict]) -> tuple[list[str], dict]:
    buckets: dict[str, Bucket] = {b[2]: Bucket() for b in ODDS_BRACKETS}
    for r in rows:
        band = _odds_band(_f(r.get("morning_price")))
        if band is None:
            continue
        buckets[band].record(_b(r.get("won")), _b(r.get("placed")),
                             _f(r.get("pnl_1pt")))

    lines = [
        "",
        "=" * 78,
        "D. ODDS BRACKET PERFORMANCE (by morning_price)",
        "   Identify value zones. Informs nap_min_odds / nap_max_odds gates.",
        "=" * 78,
        f"  {'Bracket':<16} {'N':>5} {'Wins':>5} {'Win%':>7} {'ROI%':>8}  {'Confidence':<10}",
        "  " + "-" * 60,
    ]
    ordered = [b[2] for b in ODDS_BRACKETS]
    for label in ordered:
        bk = buckets[label]
        if bk.n == 0:
            continue
        conf = _confidence(bk.n) if bk.n >= MIN_BAND_N else "[!small]"
        lines.append(f"  {label:<16} {bk.n:>5} {bk.wins:>5} "
                     f"{bk.win_pct:>6.1f}% {bk.roi:>+7.1f}%  {conf:<10}")

    value_zones = [label for label in ordered
                   if buckets[label].n >= MIN_BAND_N and buckets[label].roi > 0]
    loss_zones = [label for label in ordered
                  if buckets[label].n >= MIN_BAND_N and buckets[label].roi < -20]
    if value_zones:
        lines.append("")
        lines.append(f"  ► Value zones (ROI>0): {', '.join(value_zones)}")
    if loss_zones:
        lines.append(f"  ► Loss zones (ROI<-20%): {', '.join(loss_zones)}")

    data = {label: buckets[label].as_dict() for label in ordered
            if buckets[label].n > 0}
    return lines, {"odds_brackets": data, "value_zones": value_zones,
                   "loss_zones": loss_zones}


def _sweet_spot(rows: list[dict]) -> Optional[tuple[str, float]]:
    """Return (band_label, win_pct) of the band with the best win rate
    among bands with n>=MIN_BAND_N. None if none qualify."""
    buckets: dict[str, Bucket] = {b[2]: Bucket() for b in SCORE_BANDS}
    for r in rows:
        band = _score_band(_f(r.get("score")))
        if band is None:
            continue
        buckets[band].record(_b(r.get("won")), _b(r.get("placed")),
                             _f(r.get("pnl_1pt")))
    qualified = [(label, bk) for label, bk in buckets.items()
                 if bk.n >= MIN_BAND_N]
    if not qualified:
        return None
    best = max(qualified, key=lambda kv: kv[1].win_pct)
    return best[0], best[1].win_pct


def analyse_drift(recent_rows: list[dict],
                  prior_rows: list[dict]) -> tuple[list[str], dict]:
    """Compare recent ~30d vs prior ~60d sweet-spot band win rate."""
    lines = [
        "",
        "=" * 78,
        f"E. CALIBRATION DRIFT (recent {RECENT_DAYS}d vs prior {PRIOR_DAYS}d)",
        "   Has the profitable score sweet-spot shifted materially?",
        "=" * 78,
    ]

    recent = _sweet_spot(recent_rows)
    prior = _sweet_spot(prior_rows)

    data: dict = {
        "recent_days": RECENT_DAYS,
        "prior_days": PRIOR_DAYS,
        "recent_sweet_spot": recent[0] if recent else None,
        "recent_sweet_spot_win_pct": round(recent[1], 2) if recent else None,
        "prior_sweet_spot": prior[0] if prior else None,
        "prior_sweet_spot_win_pct": round(prior[1], 2) if prior else None,
        "shifted": False,
    }

    if recent is None or prior is None:
        lines.append("  Insufficient data in one or both slices to assess drift.")
        if recent:
            lines.append(f"  Recent sweet-spot band: {recent[0]} ({recent[1]:.1f}% win)")
        if prior:
            lines.append(f"  Prior  sweet-spot band: {prior[0]} ({prior[1]:.1f}% win)")
        return lines, {"drift": data}

    lines.append(f"  Recent ({RECENT_DAYS}d) sweet-spot band: {recent[0]} "
                 f"({recent[1]:.1f}% win)")
    lines.append(f"  Prior  ({PRIOR_DAYS}d) sweet-spot band: {prior[0]} "
                 f"({prior[1]:.1f}% win)")

    shifted = recent[0] != prior[0]
    data["shifted"] = shifted
    if shifted:
        lines.append("")
        lines.append(f"  ► DRIFT FLAGGED: sweet-spot moved from {prior[0]} → "
                     f"{recent[0]}. Calibration may be shifting; treat "
                     f"proposals with extra caution.")
    else:
        lines.append("")
        lines.append("  ► No material sweet-spot shift detected.")

    return lines, {"drift": data}


# ---------------------------------------------------------------------------
# Proposal engine — PROPOSE ONLY, clamped to PARAM_BOUNDS & PARAM_MAX_STEP.
# ---------------------------------------------------------------------------

def _clamp_and_step(target: str, current: float,
                    desired: float) -> Optional[float]:
    """Clamp `desired` into PARAM_BOUNDS[target] then cap the move from
    `current` to +/- PARAM_MAX_STEP[target]. Returns the final value, or
    None if the target has no registered bounds (must never be proposed)."""
    if target not in PARAM_BOUNDS:
        return None
    lo, hi = PARAM_BOUNDS[target]
    step = PARAM_MAX_STEP.get(target)
    # 1. clamp desired into hard bounds
    val = max(lo, min(hi, float(desired)))
    # 2. cap the move to one step
    if step is not None:
        if val > current + step:
            val = current + step
        elif val < current - step:
            val = current - step
    # 3. re-clamp into bounds (a capped move could still be fine, but be safe)
    val = max(lo, min(hi, val))
    return val


def _make_proposal(target: str, current: float, desired: float,
                   sample_size: int, rationale: str,
                   confidence: str) -> Optional[dict]:
    """Build a single clamped/step-capped proposal, or None if it should be
    omitted (no bounds, too-small sample, or trivial move)."""
    if sample_size < MIN_SAMPLE:
        return None
    final = _clamp_and_step(target, current, desired)
    if final is None:
        return None
    if abs(final - current) < EPSILON:
        return None
    return {
        "target": target,
        "current_value": round(current, 4),
        "proposed_value": round(final, 4),
        "direction": "increase" if final > current else "decrease",
        "sample_size": sample_size,
        "rationale": rationale,
        "confidence": confidence,
        "bounds": list(PARAM_BOUNDS[target]),
        "max_step": PARAM_MAX_STEP.get(target),
    }


def build_proposals(params: dict, calib: dict, grades: dict,
                    odds: dict, drift: dict) -> list[dict]:
    """Derive bounded, sample-gated proposals from the calibration evidence.

    Conservative by design: each proposal nudges toward the data-implied
    target by at most PARAM_MAX_STEP, never beyond PARAM_BOUNDS, and only when
    backed by MIN_SAMPLE observations. Drift downgrades confidence.
    """
    proposals: list[dict] = []
    drift_flagged = bool(drift.get("drift", {}).get("shifted"))

    def conf(n: int) -> str:
        c = _confidence(n)
        # Drift means the regime is unstable — never claim "high".
        if drift_flagged and c == "high":
            return "medium"
        if drift_flagged and c == "medium":
            return "low"
        return c

    # --- nap_min_score: move toward the lowest reliably-positive band floor.
    floor = calib.get("lowest_positive_band_floor")
    floor_n = calib.get("lowest_positive_band_n", 0)
    cur_min = float(params.get("nap_min_score", DEFAULTS["nap_min_score"]))
    if floor is not None and floor_n >= MIN_SAMPLE:
        # If the lowest profitable band starts well above the current gate we
        # can tighten; if it sits below we can (cautiously) loosen.
        desired = float(floor)
        if abs(desired - cur_min) >= 1.0:
            direction = "tighten" if desired > cur_min else "loosen"
            p = _make_proposal(
                "nap_min_score", cur_min, desired, floor_n,
                rationale=(f"Lowest reliably-positive score band is "
                           f"{calib.get('lowest_positive_band_label')} "
                           f"(n={floor_n}); {direction} nap_min_score toward "
                           f"its floor {desired:.0f}."),
                confidence=conf(floor_n),
            )
            if p:
                proposals.append(p)

    # --- grade_thresholds.A: if Grade A underperforms Grade B+ on ROI, raise
    #     the A bar so fewer marginal horses earn the top grade; if A strongly
    #     outperforms, we may relax it slightly. Sample-gated on Grade A n.
    g = grades.get("grades", {})
    ga, gbp = g.get("A", {}), g.get("B+", {})
    a_n = ga.get("n", 0)
    if a_n >= MIN_SAMPLE and ga.get("roi") is not None and gbp.get("roi") is not None:
        cur_a = float(params.get("grade_thresholds", {}).get(
            "A", DEFAULTS["grade_thresholds"]["A"]))
        a_roi, bp_roi = ga["roi"], gbp["roi"]
        if a_roi < bp_roi - 10 and a_roi < 0:
            # Grade A is leaking money vs B+ → make A harder to earn (raise bar).
            p = _make_proposal(
                "grade_thresholds.A", cur_a, cur_a + PARAM_MAX_STEP["grade_thresholds.A"],
                a_n,
                rationale=(f"Grade A ROI {a_roi:+.1f}% lags Grade B+ "
                           f"{bp_roi:+.1f}% (n_A={a_n}); raise the A threshold "
                           f"so only stronger horses qualify."),
                confidence=conf(a_n),
            )
            if p:
                proposals.append(p)
        elif a_roi > bp_roi + 15 and a_roi > 0:
            # Grade A clearly best → modestly relax so more horses reach A.
            p = _make_proposal(
                "grade_thresholds.A", cur_a, cur_a - PARAM_MAX_STEP["grade_thresholds.A"],
                a_n,
                rationale=(f"Grade A ROI {a_roi:+.1f}% strongly beats B+ "
                           f"{bp_roi:+.1f}% (n_A={a_n}); modestly relax the A "
                           f"threshold to capture more A-grade winners."),
                confidence=conf(a_n),
            )
            if p:
                proposals.append(p)

    # --- nap_min_odds / nap_max_odds: nudge gates away from loss zones at the
    #     extremes. Only act on the boundary brackets so we tighten the gate.
    brackets = odds.get("odds_brackets", {})
    loss_zones = set(odds.get("loss_zones", []))
    cur_min_odds = float(params.get("nap_min_odds", DEFAULTS["nap_min_odds"]))
    cur_max_odds = float(params.get("nap_max_odds", DEFAULTS["nap_max_odds"]))

    # Tighten the floor if the odds-on bracket is a loss zone.
    onb = brackets.get("<2.0 (odds-on)", {})
    if "<2.0 (odds-on)" in loss_zones and onb.get("n", 0) >= MIN_SAMPLE:
        p = _make_proposal(
            "nap_min_odds", cur_min_odds, cur_min_odds + PARAM_MAX_STEP["nap_min_odds"],
            onb["n"],
            rationale=(f"Odds-on bracket is a loss zone "
                       f"(ROI {onb.get('roi')}%, n={onb['n']}); raise "
                       f"nap_min_odds to exclude unprofitable short prices."),
            confidence=conf(onb["n"]),
        )
        if p:
            proposals.append(p)

    # Tighten the ceiling if the longest bracket is a loss zone.
    longb = brackets.get("11.0+", {})
    if "11.0+" in loss_zones and longb.get("n", 0) >= MIN_SAMPLE:
        p = _make_proposal(
            "nap_max_odds", cur_max_odds, cur_max_odds - PARAM_MAX_STEP["nap_max_odds"],
            longb["n"],
            rationale=(f"11.0+ bracket is a loss zone "
                       f"(ROI {longb.get('roi')}%, n={longb['n']}); lower "
                       f"nap_max_odds to exclude unprofitable long shots."),
            confidence=conf(longb["n"]),
        )
        if p:
            proposals.append(p)

    return proposals


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------

def _proposals_lines(proposals: list[dict], window_n: int) -> list[str]:
    lines = [
        "",
        "=" * 78,
        "PROPOSED PARAMETER CHANGES (PROPOSE-ONLY — NOT APPLIED)",
        "  Every value is clamped to PARAM_BOUNDS and capped by PARAM_MAX_STEP.",
        f"  No proposal is emitted below MIN_SAMPLE={MIN_SAMPLE} observations.",
        "=" * 78,
    ]
    if not proposals:
        lines.append("  No proposals — insufficient evidence or no actionable signal.")
        return lines
    for i, p in enumerate(proposals, 1):
        lines.append("")
        lines.append(f"  {i}. {p['target']}: {p['current_value']} → "
                     f"{p['proposed_value']}  ({p['direction']}, "
                     f"confidence={p['confidence']}, n={p['sample_size']})")
        lines.append(f"     bounds={p['bounds']} max_step={p['max_step']}")
        lines.append(f"     rationale: {p['rationale']}")
    return lines


def _no_data_report(date_str: str, reason: str) -> int:
    """Write a 'no data yet' report and the empty proposals JSON. Return 0/1."""
    lines = [
        "=" * 78,
        "  DAILY FORENSIC LEARNER — NO DATA YET",
        f"  Date: {date_str}",
        f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 78,
        "",
        f"  {reason}",
        "",
        f"  The learner needs data/{DATASET_FILENAME} (Stage 2 output) with",
        f"  labelled rows in the rolling {WINDOW_DAYS}-day window before it can",
        "  analyse calibration or propose parameter changes.",
        "",
        "  No proposals emitted.",
    ]
    rc = 0
    txt = report_path(f"daily_learning_{date_str}.txt")
    try:
        with open(txt, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        log(f"daily_learning_analysis: wrote no-data report → {txt}")
    except OSError as exc:
        log(f"daily_learning_analysis: failed to write report — {exc}", "ERROR")
        rc = 1

    doc = {
        "date": date_str,
        "window_days": WINDOW_DAYS,
        "sample_size": 0,
        "dataset_rows_in_window": 0,
        "proposals": [],
        "note": reason,
    }
    jpath = data_path(f"proposed_params_{date_str}.json")
    try:
        with open(jpath, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False)
        log(f"daily_learning_analysis: wrote empty proposals → {jpath}")
    except (OSError, TypeError, ValueError) as exc:
        log(f"daily_learning_analysis: failed to write proposals JSON — {exc}", "ERROR")
        rc = 1
    return rc


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    # Optional positional date arg (window end). Default: today.
    end_date_str = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1].strip() else today_str()
    end_date = _parse_date(end_date_str)
    if end_date is None:
        log(f"daily_learning_analysis: bad date arg '{end_date_str}' — using today", "WARNING")
        end_date = date.today()
        end_date_str = end_date.isoformat()

    log(f"daily_learning_analysis: window ends {end_date_str} ({WINDOW_DAYS}d rolling)")

    path = data_path(DATASET_FILENAME)
    all_rows = _load_dataset(path)
    if not all_rows:
        log("daily_learning_analysis: dataset absent or empty — writing no-data report")
        return _no_data_report(end_date_str,
                               f"Dataset {DATASET_FILENAME} is absent or empty.")

    # --- Window filter -------------------------------------------------------
    window_start = end_date - timedelta(days=WINDOW_DAYS - 1)
    recent_start = end_date - timedelta(days=RECENT_DAYS - 1)

    window_rows: list[dict] = []
    recent_rows: list[dict] = []
    prior_rows: list[dict] = []
    for r in all_rows:
        d = _parse_date(r.get("date"))
        if d is None or d < window_start or d > end_date:
            continue
        window_rows.append(r)
        if d >= recent_start:
            recent_rows.append(r)
        else:
            prior_rows.append(r)

    # Result rows = rows with a usable outcome label.
    result_rows = [r for r in window_rows if _b(r.get("won")) is not None]
    n_result = len(result_rows)

    if not window_rows:
        return _no_data_report(
            end_date_str,
            f"No rows fall inside the {WINDOW_DAYS}-day window "
            f"({window_start} … {end_date}).")

    # --- Run analyses --------------------------------------------------------
    calib_lines, calib_data = analyse_score_calibration(window_rows)
    grade_lines, grade_data = analyse_grades(window_rows)
    attr_lines, attr_data = analyse_subscore_attribution(window_rows)
    odds_lines, odds_data = analyse_odds_brackets(window_rows)
    drift_lines, drift_data = analyse_drift(recent_rows, prior_rows)

    # --- Proposals (gated on the overall result-row sample) ------------------
    params = get_params()
    if n_result >= MIN_SAMPLE:
        proposals = build_proposals(params, calib_data, grade_data,
                                    odds_data, drift_data)
    else:
        proposals = []

    # --- Assemble report -----------------------------------------------------
    header = [
        "=" * 78,
        "  DAILY FORENSIC LEARNER — ROLLING 90-DAY CALIBRATION",
        f"  Window:      {window_start} … {end_date}  ({WINDOW_DAYS} days)",
        f"  Rows in window: {len(window_rows)}  |  With outcome labels: {n_result}",
        f"  All-time rows:  {len(all_rows)}",
        f"  Generated:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"  MIN_SAMPLE for any proposal: {MIN_SAMPLE}",
        "=" * 78,
    ]
    if n_result < MIN_SAMPLE:
        header.append(
            f"  NOTE: only {n_result} labelled rows (< {MIN_SAMPLE}) — "
            "metrics are LOW confidence and NO proposals will be emitted.")

    all_lines = header + calib_lines + grade_lines + attr_lines + odds_lines + drift_lines
    all_lines += _proposals_lines(proposals, n_result)

    rc = 0
    txt = report_path(f"daily_learning_{end_date_str}.txt")
    try:
        with open(txt, "w", encoding="utf-8") as fh:
            fh.write("\n".join(all_lines))
        log(f"daily_learning_analysis: report → {txt}")
    except OSError as exc:
        log(f"daily_learning_analysis: failed to write report — {exc}", "ERROR")
        rc = 1

    # --- Proposals JSON for the Stage-5 tuner --------------------------------
    doc = {
        "date": end_date_str,
        "window_days": WINDOW_DAYS,
        "window_start": window_start.isoformat(),
        "window_end": end_date.isoformat(),
        "sample_size": n_result,
        "dataset_rows_in_window": len(window_rows),
        "all_time_rows": len(all_rows),
        "current_params": {k: params.get(k) for k in DEFAULTS},
        "analysis": {
            "score_calibration": calib_data,
            **grade_data,
            **attr_data,
            **odds_data,
            **drift_data,
        },
        "proposals": proposals,
    }
    jpath = data_path(f"proposed_params_{end_date_str}.json")
    try:
        with open(jpath, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False)
        log(f"daily_learning_analysis: proposals → {jpath} "
            f"({len(proposals)} proposal(s))")
    except (OSError, TypeError, ValueError) as exc:
        log(f"daily_learning_analysis: failed to write proposals JSON — {exc}", "ERROR")
        rc = 1

    log(f"daily_learning_analysis: done (rc={rc}, "
        f"{len(proposals)} proposals, n={n_result})")
    return rc


if __name__ == "__main__":
    sys.exit(main())
