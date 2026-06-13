"""
price_basis_diagnostic.py — quantify the live-vs-backtest price mismatch.

The live selector (nap_selector_v3._best_morning_price) gates and penalises
runners on the *maximum* decimal across all bookmakers ("best available =
longest decimal"). The backtest, however, calibrated NAP_MIN_ODDS /
NAP_MAX_ODDS and the outsider penalties on SP (starting price).

Taking the max across ~15-25 books is biased *longer* than a consensus
price, so the SP-tuned 7.0 cap rejects horses whose consensus price sits
comfortably inside the profitable band. This script measures, on real
saved racecards, how big that bias is and how many runners flip across the
odds window when you gate on the consensus (median) price instead of max.

It is read-only: it changes nothing, just reports. Run it in the
environment that has the saved racecard JSON:

    python price_basis_diagnostic.py                 # newest data/racecards_*.json
    python price_basis_diagnostic.py data/racecards_2026-06-13.json
"""

from __future__ import annotations

import glob
import json
import statistics
import sys
from pathlib import Path

# Mirror the live selector's gate/penalty thresholds (nap_selector_v3.py).
NAP_MIN_ODDS = 2.0
NAP_MAX_ODDS = 7.0
PENALTY_DOUBLE_FIG = 12.0   # > this: market_score -1
PENALTY_OUTSIDER = 20.0     # > this: market_score -3


def _decimals(runner: dict) -> list[float]:
    """Every valid bookmaker decimal for a runner (same filter as _best_morning_price)."""
    out: list[float] = []
    for entry in runner.get("odds") or []:
        try:
            dec = float(entry.get("decimal") or 0)
        except (TypeError, ValueError):
            continue
        if dec > 1.0:
            out.append(dec)
    return out


def _load_racecards(path: Path) -> list[dict]:
    doc = json.loads(path.read_text())
    if isinstance(doc, dict):
        return doc.get("racecards") or doc.get("races") or []
    return doc if isinstance(doc, list) else []


def main() -> int:
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        files = sorted(glob.glob("data/racecards_*.json"))
        if not files:
            print("No data/racecards_*.json found. Pass a path explicitly.")
            return 1
        path = Path(files[-1])

    racecards = _load_racecards(path)
    print(f"Source: {path}  |  races: {len(racecards)}\n")

    max_over_med: list[float] = []   # max / median ratio
    max_over_sp: list[float] = []    # max / racecard sp_dec ratio
    n_books: list[int] = []
    examples: list[tuple] = []       # (spread, horse, course, mn, md, mx, sp)

    # Gate flip counters across the [MIN, MAX] window.
    pass_max = pass_med = 0
    excluded_by_max_only = 0   # max>MAX (rejected now) but median in-window (would pass)
    excluded_by_med_only = 0   # reverse
    # Penalty flips: max trips a penalty the median would not.
    pen_max_only = 0

    runners_with_odds = 0

    for race in racecards:
        course = race.get("course", "?")
        for r in race.get("runners") or []:
            decs = _decimals(r)
            if not decs:
                continue
            runners_with_odds += 1
            mx = max(decs)
            md = statistics.median(decs)
            mn = min(decs)
            n_books.append(len(decs))
            max_over_med.append(mx / md if md else 0)

            try:
                sp = float(r.get("sp_dec") or 0)
            except (TypeError, ValueError):
                sp = 0.0
            if sp > 1.0:
                max_over_sp.append(mx / sp)

            in_win_max = NAP_MIN_ODDS <= mx <= NAP_MAX_ODDS
            in_win_med = NAP_MIN_ODDS <= md <= NAP_MAX_ODDS
            pass_max += in_win_max
            pass_med += in_win_med
            if (not in_win_max) and in_win_med and mx > NAP_MAX_ODDS:
                excluded_by_max_only += 1
            if in_win_max and (not in_win_med):
                excluded_by_med_only += 1

            if mx > PENALTY_DOUBLE_FIG and md <= PENALTY_DOUBLE_FIG:
                pen_max_only += 1

            examples.append((mx / md if md else 0, r.get("horse", "?"),
                             course, mn, md, mx, sp))

    if not max_over_med:
        print("No runners with bookmaker odds in this file.")
        return 0

    def pct(x):
        return f"{x:.1%}"

    print("=" * 64)
    print("PRICE-BASIS DIAGNOSTIC — max(best-available) vs median(consensus)")
    print("=" * 64)
    print(f"Runners with odds:        {runners_with_odds}")
    print(f"Books per runner (median):{int(statistics.median(n_books))}")
    print()
    print("Best-available (max) inflation vs consensus (median):")
    print(f"  mean   max/median ratio: {statistics.mean(max_over_med):.3f}")
    print(f"  median max/median ratio: {statistics.median(max_over_med):.3f}")
    print(f"  90th pct max/median:     {sorted(max_over_med)[int(len(max_over_med)*0.9)]:.3f}")
    if max_over_sp:
        print(f"  mean   max/sp_dec ratio: {statistics.mean(max_over_sp):.3f}  "
              f"(sp_dec = racecard forecast/early SP)")
    print()
    print(f"Odds window [{NAP_MIN_ODDS}, {NAP_MAX_ODDS}]:")
    print(f"  pass under MAX logic (current): {pass_max}")
    print(f"  pass under MEDIAN logic:        {pass_med}")
    print(f"  >>> wrongly EXCLUDED by max-only (in-window on median, "
          f"but max>{NAP_MAX_ODDS}): {excluded_by_max_only}")
    print(f"      (these are horses the SP-tuned cap was NOT meant to cut)")
    print(f"  excluded by median-only (reverse case): {excluded_by_med_only}")
    print(f"  outsider penalty (>{PENALTY_DOUBLE_FIG}) tripped by max but not "
          f"median: {pen_max_only}")
    print()
    print("Biggest max/median spreads (potential mis-gated runners):")
    for spread, horse, course, mn, md, mx, sp in sorted(examples, reverse=True)[:12]:
        flag = "  <-- max>cap, median in-window" if (
            mx > NAP_MAX_ODDS and NAP_MIN_ODDS <= md <= NAP_MAX_ODDS) else ""
        print(f"  {horse[:22]:<22} {course[:12]:<12} "
              f"min={mn:5.2f} med={md:5.2f} max={mx:5.2f} sp={sp:5.2f}"
              f"  (x{spread:.2f}){flag}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
