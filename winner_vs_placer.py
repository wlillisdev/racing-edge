"""
winner_vs_placer.py — find what actually separates WINNERS from PLACERS.

The model places well but doesn't win enough. That means its high-scoring
factors may predict "competitive" (top-3) rather than "first". This tool
isolates the difference: within the NAP selection pool, it splits runners into
WON / PLACED-not-won / UNPLACED and compares each score component across the
groups, ranking factors by how much they separate winners from mere placers.

A factor where winners score much higher than placers is win-predictive →
upweight it. A factor that's the same for winners and placers is only
predicting "places" → it's diluting win-finding.

Run on the backtest CSV from historical_backtest.py (use the --deep CSV once
available — its scores match the live model):

    python winner_vs_placer.py                       # newest backtest_*.csv
    python winner_vs_placer.py data/backtest_..._deep.csv
    python winner_vs_placer.py --min-score 60 file.csv

Pure stdlib. ROI is level-stakes at SP. Not financial advice; a tool to guide
factor reweighting that must then be validated out-of-sample (walkforward).
"""

from __future__ import annotations

import argparse
import csv
import glob
import statistics
from typing import Optional

# Live gates (mirror nap_selector_v3.py) — only score components vary in study.
NAP_MAX_SCORE = 82.0
NAP_MIN_ODDS = 2.0
NAP_MAX_ODDS = 7.0
DEFAULT_MIN_SCORE = 60.0

# Score components present in the backtest CSV.
COMPONENTS = ["form_score", "suit_score", "ctx_score", "draw_score",
              "train_score", "mkt_score", "score", "sp_dec"]

_GOING_RULES = [
    ("standard to slow", "Slow"), ("slow", "Slow"), ("standard", "Standard"),
    ("fast", "Standard"), ("good to firm", "Good to Firm"),
    ("good to soft", "Good to Soft"), ("soft to heavy", "Heavy"),
    ("heavy", "Heavy"), ("firm", "Firm"), ("good", "Good"), ("soft", "Soft"),
    ("yielding to soft", "Soft"), ("yielding", "Good to Soft"), ("hard", "Firm"),
]
FLAT_EXCLUDED_GOING = {"Firm", "Good to Firm", "Heavy"}


def _going(s: str) -> str:
    n = (s or "").strip().lower().split("(")[0].strip()
    for pat, canon in _GOING_RULES:
        if pat in n:
            return canon
    return (s or "").strip().title()


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes")


def load(paths: list[str], min_score: float) -> list[dict]:
    seen, rows = set(), []
    for p in paths:
        with open(p, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if not _truthy(r.get("has_result")):
                    continue
                key = (r.get("date", ""), r.get("horse_id", ""))
                if key in seen:
                    continue
                seen.add(key)
                score, sp = _f(r.get("score")), _f(r.get("sp_dec"))
                rt = (r.get("race_type") or "").lower()
                # NAP-pool gates (same basis as the live selector / walkforward)
                if not (min_score <= score <= NAP_MAX_SCORE):
                    continue
                if sp <= 0 or sp < NAP_MIN_ODDS or sp > NAP_MAX_ODDS:
                    continue
                if "chase" in rt:
                    continue
                is_flat = not any(x in rt for x in ("chase", "hurdle", "bumper"))
                if is_flat and _f(r.get("distance_f")) >= 16.0:
                    continue
                if is_flat and _going(r.get("going")) in FLAT_EXCLUDED_GOING:
                    continue
                row = {c: _f(r.get(c)) for c in COMPONENTS}
                row["is_win"] = _truthy(r.get("is_win"))
                row["is_place"] = _truthy(r.get("is_place"))
                rows.append(row)
    return rows


def _mean(rows, c):
    vals = [r[c] for r in rows]
    return statistics.mean(vals) if vals else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    args = ap.parse_args()

    paths = args.paths
    if not paths:
        cands = glob.glob("data/backtest_*.csv")
        if not cands:
            print("No data/backtest_*.csv found. Pass a path.")
            return 1
        paths = [max(cands, key=lambda p: sum(1 for _ in open(p)))]

    rows = load(paths, args.min_score)
    if not rows:
        print("No selections in the NAP pool for these files/threshold.")
        return 1

    won = [r for r in rows if r["is_win"]]
    placed = [r for r in rows if r["is_place"] and not r["is_win"]]
    out = [r for r in rows if not r["is_place"]]
    n = len(rows)
    deep = "deep" in " ".join(paths)

    print("=" * 70)
    print("WINNER vs PLACER — factor separation analysis")
    print("=" * 70)
    print(f"Files: {', '.join(paths)}")
    print(f"Score scale: {'DEEP (live-equivalent)' if deep else 'shallow (form-string fallback — directional only)'}")
    print(f"NAP pool (score {args.min_score:.0f}-82, odds {NAP_MIN_ODDS}-{NAP_MAX_ODDS}): {n} selections")
    print(f"  WON:    {len(won):>4}  ({len(won)/n*100:4.1f}%)")
    print(f"  PLACED (not won): {len(placed):>4}  ({len(placed)/n*100:4.1f}%)")
    print(f"  UNPLACED: {len(out):>4}  ({len(out)/n*100:4.1f}%)")
    print()

    if not won or not placed:
        print("Need both winners and placers to compare. Widen the data.")
        return 0

    print("Mean score-component by outcome — and WINNER minus PLACER gap:")
    print(f"  {'component':<12} {'WON':>8} {'PLACED':>8} {'UNPL':>8} {'win-plc':>9}")
    deltas = []
    for c in COMPONENTS:
        mw, mp, mo = _mean(won, c), _mean(placed, c), _mean(out, c)
        d = mw - mp
        deltas.append((c, d, mw, mp))
        print(f"  {c:<12} {mw:>8.2f} {mp:>8.2f} {mo:>8.2f} {d:>+9.2f}")
    print()

    print("RANKED — what separates winners from placers (act on the extremes):")
    scoreable = [t for t in deltas if t[0] not in ("score",)]
    for c, d, mw, mp in sorted(scoreable, key=lambda t: -abs(t[1])):
        if c == "sp_dec":
            hint = ("winners go off SHORTER — model's value floor may be excluding "
                    "likely winners" if d < 0 else
                    "winners go off LONGER — value is paying off")
        elif d > 0.3:
            hint = "winners score HIGHER → win-predictive, consider UPWEIGHT"
        elif d < -0.3:
            hint = "winners score LOWER → this factor favours placers, consider DOWNWEIGHT"
        else:
            hint = "~same for winners and placers → only predicts 'places', diluting win-finding"
        print(f"  {c:<12} gap {d:>+6.2f}  {hint}")
    print("=" * 70)
    print("Next: reweight toward the win-predictive factors, then validate the new")
    print("weighting OUT-OF-SAMPLE with walkforward_validate.py before going live.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
