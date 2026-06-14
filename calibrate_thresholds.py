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

    # --- 3. Proposed configs: prove the COMBINED filter end-to-end ------------
    # Two stacked configs, each reported two ways:
    #   per-pick  = every qualifying race top-scorer (raw edge of the filter)
    #   daily-NAP = ONE best qualifying pick per day (what the product actually
    #               bets) — the honest product-level ROI.
    def _evaluate(rows, floor, ex_class, ex_type, only_going):
        sel = [
            r for r in rows
            if _f(r.get("score")) >= floor
            and str(r.get("class_group") or "?") not in ex_class
            and str(r.get("type_group") or "?") not in ex_type
            and (only_going is None or str(r.get("going_group") or "?") in only_going)
        ]
        pick_n, pick_win, pick_roi, pick_pl = _roi(sel)
        # daily NAP: highest-scoring qualifier per day
        by_day: dict[str, dict] = {}
        for r in sel:
            d = str(r.get("date") or "?")
            if d not in by_day or _f(r.get("score")) > _f(by_day[d].get("score")):
                by_day[d] = r
        nap_n, nap_win, nap_roi, nap_pl = _roi(list(by_day.values()))
        return (pick_n, pick_win, pick_roi, pick_pl), (nap_n, nap_win, nap_roi, nap_pl)

    EX_CLASS = {"Class 3", "Class 6-7", "Unknown"}
    EX_TYPE  = {"Chase", "Hurdle"}
    configs = [
        ("A  floor38 + class/jumps filters (non-seasonal)",
         38, EX_CLASS, EX_TYPE, None),
        ("B  = A + Good-going-only (strongest, but seasonal)",
         38, EX_CLASS, EX_TYPE, {"Good"}),
        ("C  = A + floor 44 (tighter score)",
         44, EX_CLASS, EX_TYPE, None),
    ]
    print("PROPOSED CONFIGS — combined filters, validated on THIS window")
    print("-" * 70)
    print(f"  {'config':<48}{'n':>5}{'win%':>7}{'ROI%':>8}")
    for label, floor, exc, ext, og in configs:
        (pn, pw, pr, _ppl), (nn, nw, nr, _npl) = _evaluate(rows, floor, exc, ext, og)
        print(f"  {label:<48}")
        print(f"  {'   per-pick':<48}{pn:>5}{pw:>6.1f}%{pr:>7.1f}%")
        print(f"  {'   daily-NAP (the product)':<48}{nn:>5}{nw:>6.1f}%{nr:>7.1f}%")
    print()

    # --- 4. Recommendation ----------------------------------------------------
    print("=" * 70)
    if best:
        rr, X, nn = best
        print(f"Score sweep: edge turns positive around score>={X} and strengthens above.")
    print("Categories to exclude (ROI < -8%, n>=25): Class 3, Class 6-7, Unknown, "
          "Chase, Hurdle; surfaces Firm/Soft/AW (going) all bled vs Good.")
    print("NOTE: summer-flat sample — the GOING filter (config B) is seasonal; "
          "confirm on a winter/NH window before locking that one.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
