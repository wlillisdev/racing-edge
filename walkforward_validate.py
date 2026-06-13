"""
walkforward_validate.py — out-of-sample validation of NAP model thresholds.

The model's analysis layer computes "optimal" thresholds (e.g.
intelligence_rules.OPTIMAL_NAP_MIN_SCORE = 73.0) but the live model uses
NAP_MIN_SCORE = 60.0, and those optima were fitted on a single 6-month
backtest. This tool asks the honest question: does a threshold that looks
best *in-sample* still win *out-of-sample*, or is it overfitting?

It reads the per-race backtest records written by historical_backtest.py
(data/backtest_*.csv — one row per race: the top scorer, pre-gate, with
score, sp_dec, going, race_type, distance_f and the settled result), then:

  1. Sweeps NAP_MIN_SCORE in-sample and shows ROI/strike per threshold.
  2. Splits the timeline into chronological folds and shows ROI stability
     of the live (60), recommended (73), and in-sample-best thresholds.
  3. Runs an expanding-window walk-forward: pick the best threshold on
     past folds, bet the next (unseen) fold, accumulate realised OOS ROI,
     and compare against fixed 60 and fixed 73.

Pure stdlib — no API, no DB, no project imports. Run it where the CSVs are:

    python walkforward_validate.py                      # auto: largest backtest_*.csv
    python walkforward_validate.py data/backtest_2025-12-08_to_2026-06-06.csv
    python walkforward_validate.py --folds 6 a.csv b.csv   # combine + dedup

ROI is level-stakes at Starting Price (win pays sp-1, loss pays -1) — the
same basis historical_backtest.py and the calibration used.
"""

from __future__ import annotations

import argparse
import csv
import glob
import sys
from collections import defaultdict

# --- Live model constants (mirror nap_selector_v3.py) -----------------------
NAP_MAX_SCORE = 82.0
NAP_MIN_ODDS = 2.0
NAP_MAX_ODDS = 7.0
NAP_EXCLUDED_RACE_TYPES = ("chase",)
FLAT_MAX_DIST_F = 16.0
FLAT_EXCLUDED_GOING = frozenset({"Firm", "Good to Firm", "Heavy"})

LIVE_MIN_SCORE = 60.0          # what the live model uses today
RECOMMENDED_MIN_SCORE = 73.0   # what intelligence_rules.py recommends

SWEEP = [float(x) for x in range(55, 81)]   # candidate NAP_MIN_SCORE values
MIN_N_FOR_PICK = 20            # don't trust a threshold chosen on < this many bets

# --- Going normalisation (faithful copy of src/helpers._GOING_RULES) --------
_GOING_RULES = [
    ("standard to slow", "Slow"), ("slow", "Slow"), ("standard", "Standard"),
    ("fast", "Standard"), ("good to firm", "Good to Firm"),
    ("good to soft", "Good to Soft"), ("soft to heavy", "Heavy"),
    ("heavy", "Heavy"), ("firm", "Firm"), ("good", "Good"), ("soft", "Soft"),
    ("yielding to soft", "Soft"), ("yielding", "Good to Soft"), ("hard", "Firm"),
]


def going_normalise(going_str: str) -> str:
    if not going_str:
        return going_str
    norm = going_str.strip().lower()
    norm = norm.split("(")[0].strip()
    for pattern, canonical in _GOING_RULES:
        if pattern in norm:
            return canonical
    return going_str.strip().title()


# --- Loading ----------------------------------------------------------------
def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes")


def load_rows(paths: list[str]) -> list[dict]:
    seen: set[tuple] = set()
    rows: list[dict] = []
    for p in paths:
        with open(p, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if not _truthy(r.get("has_result")):
                    continue
                key = (r.get("date", ""), r.get("horse_id", ""))
                if key in seen:
                    continue
                seen.add(key)
                rows.append({
                    "date": r.get("date", ""),
                    "score": _f(r.get("score")),
                    "sp_dec": _f(r.get("sp_dec")),
                    "is_win": _truthy(r.get("is_win")),
                    "is_place": _truthy(r.get("is_place")),
                    "race_type": (r.get("race_type") or "").lower(),
                    "going": r.get("going") or "",
                    "distance_f": _f(r.get("distance_f")),
                })
    rows.sort(key=lambda x: x["date"])
    return rows


# --- Selection logic (all gates fixed; only score threshold varies) ---------
def passes(row: dict, score_min: float) -> bool:
    if not (score_min <= row["score"] <= NAP_MAX_SCORE):
        return False
    sp = row["sp_dec"]
    if sp <= 0 or sp < NAP_MIN_ODDS or sp > NAP_MAX_ODDS:   # odds window at SP
        return False
    rt = row["race_type"]
    if any(x in rt for x in NAP_EXCLUDED_RACE_TYPES):
        return False
    is_flat = not any(x in rt for x in ("chase", "hurdle", "bumper"))
    if is_flat and row["distance_f"] >= FLAT_MAX_DIST_F:
        return False
    if is_flat and going_normalise(row["going"]) in FLAT_EXCLUDED_GOING:
        return False
    return True


class Stats:
    __slots__ = ("n", "wins", "places", "pl", "sp_sum")

    def __init__(self):
        self.n = self.wins = self.places = 0
        self.pl = self.sp_sum = 0.0

    def add(self, row: dict):
        self.n += 1
        self.sp_sum += row["sp_dec"]
        if row["is_win"]:
            self.wins += 1
            self.pl += row["sp_dec"] - 1.0
        else:
            self.pl -= 1.0
        if row["is_place"]:
            self.places += 1

    @property
    def wr(self): return self.wins / self.n * 100 if self.n else 0.0
    @property
    def plc(self): return self.places / self.n * 100 if self.n else 0.0
    @property
    def roi(self): return self.pl / self.n * 100 if self.n else 0.0
    @property
    def avg_sp(self): return self.sp_sum / self.n if self.n else 0.0


def stats_for(rows: list[dict], score_min: float) -> Stats:
    s = Stats()
    for r in rows:
        if passes(r, score_min):
            s.add(r)
    return s


def best_threshold(rows: list[dict], min_n: int = MIN_N_FOR_PICK) -> float | None:
    """In-sample ROI-maximising threshold with a sample-size floor."""
    best_t, best_roi = None, float("-inf")
    for t in SWEEP:
        s = stats_for(rows, t)
        if s.n >= min_n and s.roi > best_roi:
            best_roi, best_t = s.roi, t
    return best_t


# --- Reporting --------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", help="backtest_*.csv file(s)")
    ap.add_argument("--folds", type=int, default=6)
    args = ap.parse_args()

    paths = args.paths
    if not paths:
        cands = glob.glob("data/backtest_*.csv")
        if not cands:
            print("No data/backtest_*.csv found. Pass a path explicitly.")
            return 1
        # default: the file with the most rows (widest history)
        paths = [max(cands, key=lambda p: sum(1 for _ in open(p)))]

    rows = load_rows(paths)
    if not rows:
        print("No settled rows loaded.")
        return 1

    d0, d1 = rows[0]["date"], rows[-1]["date"]
    print("=" * 74)
    print("WALK-FORWARD THRESHOLD VALIDATION — NAP_MIN_SCORE")
    print("=" * 74)
    print(f"Source rows (settled, deduped): {len(rows)}   Period: {d0} → {d1}")
    print(f"Files: {', '.join(paths)}")
    print("Selection = top scorer/race clearing the live gates (odds 2.0-7.0 at SP,")
    print("no chase, flat<16f, Firm/G-F/Heavy excluded); only NAP_MIN_SCORE varies.\n")

    # 1) In-sample sweep -----------------------------------------------------
    print("1) IN-SAMPLE SWEEP (whole period)")
    print(f"   {'min':>4} {'N':>5} {'Wins':>5} {'WR%':>6} {'Plc%':>6} {'AvgSP':>6} {'P/L':>8} {'ROI%':>7}")
    is_best = best_threshold(rows)
    for t in SWEEP:
        s = stats_for(rows, t)
        if s.n == 0:
            continue
        tag = ""
        if t == LIVE_MIN_SCORE: tag += " <-LIVE"
        if t == RECOMMENDED_MIN_SCORE: tag += " <-REC"
        if t == is_best: tag += " <-BEST(in-sample)"
        print(f"   {t:>4.0f} {s.n:>5} {s.wins:>5} {s.wr:>6.1f} {s.plc:>6.1f} "
              f"{s.avg_sp:>6.2f} {s.pl:>+8.1f} {s.roi:>+6.1f}%{tag}")
    print()

    # 2) Per-fold stability --------------------------------------------------
    K = max(2, args.folds)
    n = len(rows)
    folds = [rows[i * n // K:(i + 1) * n // K] for i in range(K)]
    print(f"2) PER-FOLD STABILITY ({K} chronological folds) — ROI% at each fixed threshold")
    print(f"   {'fold':>4} {'dates':>23} {'N':>4} | "
          f"{'ROI@60':>8} {'ROI@73':>8} {'ROI@best':>9}")
    for i, fr in enumerate(folds):
        if not fr:
            continue
        s60, s73, sb = (stats_for(fr, LIVE_MIN_SCORE),
                        stats_for(fr, RECOMMENDED_MIN_SCORE),
                        stats_for(fr, is_best) if is_best else Stats())
        dr = f"{fr[0]['date']}..{fr[-1]['date']}"
        print(f"   {i:>4} {dr:>23} {len(fr):>4} | "
              f"{s60.roi:>+7.1f}% {s73.roi:>+7.1f}% {sb.roi:>+8.1f}%")
    print()

    # 3) Expanding-window walk-forward --------------------------------------
    print(f"3) WALK-FORWARD (expanding window; pick best threshold on past folds,")
    print(f"   bet next unseen fold). Realised OUT-OF-SAMPLE results:")
    adapt, fix60, fix73 = Stats(), Stats(), Stats()
    chosen: list[float] = []
    for i in range(1, K):
        train = [r for f in folds[:i] for r in f]
        test = folds[i]
        if not test:
            continue
        t = best_threshold(train)
        if t is None:
            t = LIVE_MIN_SCORE   # fall back if training too thin
        chosen.append(t)
        for r in test:
            if passes(r, t): adapt.add(r)
            if passes(r, LIVE_MIN_SCORE): fix60.add(r)
            if passes(r, RECOMMENDED_MIN_SCORE): fix73.add(r)

    def line(name, s: Stats):
        print(f"   {name:<22} N={s.n:>4}  WR={s.wr:>5.1f}%  "
              f"ROI={s.roi:>+6.1f}%  P/L={s.pl:>+7.1f}")

    line("adaptive (best-of-past)", adapt)
    line("fixed 60 (LIVE)", fix60)
    line("fixed 73 (RECOMMENDED)", fix73)
    print(f"   thresholds chosen per fold: {[f'{c:.0f}' for c in chosen]}")
    print()

    # 4) Verdict -------------------------------------------------------------
    print("4) VERDICT")
    s60_all, s73_all = stats_for(rows, LIVE_MIN_SCORE), stats_for(rows, RECOMMENDED_MIN_SCORE)
    print(f"   In-sample: best threshold = {is_best} "
          f"(ROI {stats_for(rows, is_best).roi:+.1f}% / N {stats_for(rows, is_best).n}) "
          f"vs LIVE 60 (ROI {s60_all.roi:+.1f}%) vs REC 73 (ROI {s73_all.roi:+.1f}%)")
    oos = [("60", fix60), ("73", fix73), ("adaptive", adapt)]
    oos_best = max(oos, key=lambda kv: kv[1].roi if kv[1].n >= MIN_N_FOR_PICK else float("-inf"))
    print(f"   Out-of-sample winner: {oos_best[0]} "
          f"(ROI {oos_best[1].roi:+.1f}% over N {oos_best[1].n})")
    # Overfitting gauge: does the in-sample-best hold up OOS?
    if is_best is not None:
        oos_isbest = Stats()
        for i in range(1, K):
            for r in folds[i]:
                if passes(r, is_best):
                    oos_isbest.add(r)
        gap = stats_for(rows, is_best).roi - oos_isbest.roi
        print(f"   Overfit gauge: in-sample-best {is_best:.0f} ROI {stats_for(rows, is_best).roi:+.1f}% "
              f"-> same threshold OOS {oos_isbest.roi:+.1f}%  (drop {gap:+.1f} pts)")
        print("   A large positive drop = the 'optimum' was overfit; trust the OOS number.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
