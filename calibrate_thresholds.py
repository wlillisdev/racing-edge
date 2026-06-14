"""
calibrate_thresholds.py — derive the NAP score threshold + category filters
from a DEEP backtest CSV, using real results (not a guess off one card).

The deep backtest writes one row per race top-scorer with the model's true-scale
score and the actual finishing position / SP. This reads that CSV and answers:

  1. Where does the edge start?  ROI for "score >= X" swept across the scale, so
     we can pick the LOWEST threshold whose selections are profitable on an
     adequate sample — that's the NAP floor.
  2. Which categories bleed money?  ROI by class / race-type / going / distance,
     so the genuinely negative buckets can be excluded.

Level-stakes to SP: stake 1pt; return = sp_dec on a win, else 0; profit = return-1.
Only rows with a result and a usable SP are counted.

Usage:
    python calibrate_thresholds.py [path/to/backtest_*_deep.csv]
If no path is given, the newest data/backtest_*_deep.csv is used.
"""

from __future__ import annotations

import csv
import glob
import sys

from src.helpers import data_path


def _f(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _truthy(x) -> bool:
    return str(x).strip().lower() in ("true", "1", "yes")


def _roi(rows):
    """(n, win%, ROI%) over rows that have a result and a usable SP."""
    n = wins = 0
    profit = 0.0
    for r in rows:
        sp = _f(r.get("sp_dec"))
        if not _truthy(r.get("has_result")) or sp <= 1.0:
            continue
        n += 1
        if _truthy(r.get("is_win")):
            wins += 1
            profit += sp - 1.0
        else:
            profit -= 1.0
    if n == 0:
        return 0, 0.0, 0.0, 0.0
    return n, 100.0 * wins / n, 100.0 * profit / n, profit


def _table(title, key, rows):
    print(title)
    print("-" * 70)
    print(f"  {'bucket':<18}{'n':>6}{'win%':>8}{'ROI%':>9}{'P/L pts':>10}")
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(str(r.get(key) or "?"), []).append(r)
    # sort by ROI descending
    out = []
    for g, grp in groups.items():
        n, win, roi, pl = _roi(grp)
        if n:
            out.append((roi, g, n, win, pl))
    for roi, g, n, win, pl in sorted(out, reverse=True):
        flag = "  <<< exclude" if (roi < -8.0 and n >= 25) else ""
        print(f"  {g:<18}{n:>6}{win:>7.1f}%{roi:>8.1f}%{pl:>+10.1f}{flag}")
    print()


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        cands = sorted(glob.glob(data_path("backtest_*_deep.csv")))
        if not cands:
            print("No data/backtest_*_deep.csv found — run the deep backtest first.")
            return 1
        path = cands[-1]
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    print("=" * 70)
    print(f"THRESHOLD CALIBRATION — {path}")
    print(f"rows={len(rows)}")
    print("=" * 70)

    n, win, roi, pl = _roi(rows)
    print(f"ALL top-scorers: n={n}  win={win:.1f}%  ROI={roi:+.1f}%  P/L={pl:+.1f}\n")

    # --- 1. Cumulative ROI for score >= X (the NAP floor sweep) ----------------
    scores = [_f(r.get("score")) for r in rows if _truthy(r.get("has_result"))]
    lo, hi = (int(min(scores)) if scores else 0), (int(max(scores)) + 1 if scores else 1)
    print("EDGE BY THRESHOLD — selections with score >= X")
    print("-" * 70)
    print(f"  {'score>=':<10}{'n':>6}{'win%':>8}{'ROI%':>9}{'P/L pts':>10}")
    best = None  # (roi, X, n) — lowest X that is profitable on an adequate sample
    for X in range(lo, hi + 1):
        sub = [r for r in rows if _f(r.get("score")) >= X]
        nn, ww, rr, pp = _roi(sub)
        if nn < 5:
            continue
        mark = ""
        if rr > 0 and nn >= 30 and best is None:
            best = (rr, X, nn); mark = "  <-- lowest profitable floor (n>=30)"
        print(f"  {X:<10}{nn:>6}{ww:>7.1f}%{rr:>8.1f}%{pp:>+10.1f}{mark}")
    print()

    # --- 2. Where each category stands (exclusion candidates) ------------------
    _table("BY RACE CLASS", "class_group", rows)
    _table("BY RACE TYPE", "type_group", rows)
    _table("BY GOING", "going_group", rows)
    _table("BY DISTANCE", "dist_group", rows)

    # --- 3. Recommendation ----------------------------------------------------
    print("=" * 70)
    if best:
        rr, X, nn = best
        print(f"RECOMMENDATION: NAP floor (nap_min_score) ~ {X}  "
              f"(score>={X}: {nn} picks, ROI {rr:+.1f}%)")
    else:
        print("RECOMMENDATION: no score threshold reaches positive ROI on n>=30 in "
              "this window — widen the sample (more days/season) before committing.")
    print("Exclude any category flagged '<<< exclude' above (ROI < -8% on n>=25).")
    print("NOTE: summer-flat sample — confirm NH/winter separately before locking.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
