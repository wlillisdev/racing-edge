"""
loser_patterns.py — read every bet at once, find where the money leaks.

This is the one thing the machine can do that the eye can't: hold hundreds of
your picks in its head at once and slice them by every angle simultaneously —
price, field size, going, class, distance, handicap-or-not, with-or-against the
market, how short the favourite was — and show you exactly which buckets bleed
and which ones pay. Not a tip. A pattern.

It rebuilds every method pick over a window, joins the race context and the
result, and reports win% / level-stakes ROI for each slice, then names the
BIGGEST LEAKS (worst buckets) and BEST POCKETS (best buckets) so you can see —
in one screen — where to stop betting and where the real edge concentrates.

No tuning, no persistence — a re-runnable X-ray.

Usage:
  python loser_patterns.py --backfill 21
  python loser_patterns.py --backfill 30 --min 20
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from ground_breeding_signal import going_band
from edge_tracker import _race_outcomes, _to_float
from method_pick import build as method_build
from racecard_loader import load_racecard
from src.api_client import get_client
from src.helpers import log, today_str

DIMENSIONS = [
    ("price band (your pick)", "price_band"),
    ("field size", "field"),
    ("going", "going"),
    ("race class", "race_class"),
    ("race type", "race_type"),
    ("distance", "dist"),
    ("handicap?", "handicap"),
    ("vs the market", "contrarian"),
    ("how short the favourite", "fav_band"),
]


# --------------------------------------------------------------------------- #
# pure banding helpers
# --------------------------------------------------------------------------- #
def band_price(p: Optional[float]) -> str:
    if p is None:
        return "?"
    if p <= 2.0:
        return "<=2.0 (odds-on)"
    if p <= 3.0:
        return "2.0-3.0"
    if p <= 4.0:
        return "3.0-4.0"
    if p <= 6.0:
        return "4.0-6.0"
    return "6.0+"


def band_field(n: Optional[int]) -> str:
    if not n:
        return "?"
    if n <= 7:
        return "small (<=7)"
    if n <= 12:
        return "medium (8-12)"
    return "big (13+)"


def band_dist(f: Optional[float]) -> str:
    if not f:
        return "?"
    if f <= 6.0:
        return "sprint (<=6f)"
    if f <= 9.5:
        return "mile (6-9.5f)"
    if f <= 12.0:
        return "middle (9.5-12f)"
    return "staying (12f+)"


def seg_stats(records: list[dict], key: str) -> list[tuple]:
    """(bucket, n, win%, ROI%) for each value of `key`, most-bet first."""
    g: dict = defaultdict(list)
    for r in records:
        g[r.get(key, "?")].append(r)
    rows = []
    for bucket, rs in g.items():
        n = len(rs)
        wins = sum(int(r["won"]) for r in rs)
        pl = sum((r["sp"] - 1) if r["won"] else -1 for r in rs)
        rows.append((bucket, n, 100 * wins / n, 100 * pl / n))
    return sorted(rows, key=lambda x: -x[1])


# --------------------------------------------------------------------------- #
# data collection
# --------------------------------------------------------------------------- #
def _race_ctx(rc: dict) -> dict:
    """horse_id -> race context (going, class, type, distance, field, handicap)."""
    out: dict = {}
    for race in (rc.get("racecards") or []):
        runners = race.get("runners") or []
        name = f"{race.get('race_name', '')} {race.get('type', '')}".lower()
        ctx = {
            "going": str(race.get("going_detailed") or race.get("going") or ""),
            "race_class": f"Class {race.get('class')}" if race.get("class") else "?",
            "race_type": str(race.get("type") or "?"),
            "dist": _to_float(race.get("distance_f")),
            "field": len(runners),
            "handicap": any(k in name for k in ("handicap", "hcap", "h'cap", "nursery")),
        }
        for r in runners:
            out[str(r.get("horse_id") or "")] = ctx
    return out


def collect(dates: list[str]) -> list[dict]:
    recs: list[dict] = []
    for d in sorted(dates):
        method = method_build(d) or {}
        picks = [p for p in (method.get("race_picks") or []) if p.get("price")]
        if not picks:
            continue
        ctx = _race_ctx(load_racecard(d) or {})
        try:
            doc = get_client().get_results_by_date(d) or {}
        except Exception as exc:  # noqa: BLE001
            log(f"loser_patterns: results fetch failed {d} — {exc}", "WARNING")
            continue
        horse, fav = _race_outcomes(doc)
        if not horse:
            continue
        for p in picks:
            hid = str(p.get("horse_id") or "")
            o = horse.get(hid)
            if not o or o["sp"] is None:
                continue
            c = ctx.get(hid, {})
            f = fav.get(o["race_id"], {})
            price = _to_float(p.get("price") or p.get("consensus_price") or p.get("morning_price"))
            recs.append({
                "won": o["pos"] == 1, "sp": o["sp"],
                "price_band": band_price(price),
                "field": band_field(c.get("field")),
                "going": going_band(c.get("going", "")),
                "race_class": c.get("race_class", "?"),
                "race_type": c.get("race_type", "?"),
                "dist": band_dist(c.get("dist")),
                "handicap": "handicap" if c.get("handicap") else "non-handicap",
                "contrarian": "against market" if hid != str(f.get("horse_id") or "") else "with favourite",
                "fav_band": band_price(f.get("sp")),
            })
    return recs


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def report(records: list[dict], min_n: int = 15) -> None:
    n = len(records)
    if not n:
        print("No picks collected — check the backfill window / saved data.")
        return
    wins = sum(int(r["won"]) for r in records)
    pl = sum((r["sp"] - 1) if r["won"] else -1 for r in records)
    print("=" * 66)
    print(f"LOSER PATTERNS — {n} method picks   overall: "
          f"{100*wins/n:.0f}% win   {100*pl/n:+.1f}% ROI")
    print("=" * 66)

    leaks: list[tuple] = []
    pockets: list[tuple] = []
    for label, key in DIMENSIONS:
        print(f"\n  by {label}:")
        for bucket, bn, bw, br in seg_stats(records, key):
            tag = "" if bn >= min_n else "   (thin)"
            print(f"    {str(bucket):<22}{bn:>5}{bw:>6.0f}%{br:>8.1f}%{tag}")
            if bn >= min_n:
                (pockets if br > 0 else leaks).append((label, bucket, bn, bw, br))

    print("\n" + "=" * 66)
    print(f"  BIGGEST LEAKS  (where the money goes — n>={min_n})")
    print("=" * 66)
    for label, bucket, bn, bw, br in sorted(leaks, key=lambda x: x[4])[:5]:
        print(f"    {br:>7.1f}%  {label}: {bucket}   ({bn} picks, {bw:.0f}% win)")
    if not leaks:
        print("    none meeting the sample bar")

    print("\n" + "=" * 66)
    print(f"  BEST POCKETS  (where the edge concentrates — n>={min_n})")
    print("=" * 66)
    for label, bucket, bn, bw, br in sorted(pockets, key=lambda x: -x[4])[:5]:
        print(f"    {br:>+7.1f}%  {label}: {bucket}   ({bn} picks, {bw:.0f}% win)")
    if not pockets:
        print("    none profitable at the sample bar — the leak is broad, not a pocket")

    print("\n  Read: kill the leaks, lean into the pockets — IF they survive a")
    print("  second look on fresh days. One window can still flatter a slice.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=today_str())
    ap.add_argument("--backfill", type=int, default=21)
    ap.add_argument("--min", type=int, default=15, help="min picks for a bucket to count")
    args = ap.parse_args()

    base = datetime.strptime(args.date, "%Y-%m-%d").date()
    dates = [(base - timedelta(days=i)).isoformat() for i in range(max(1, args.backfill))]
    print(f"  collecting picks over {len(dates)} days (this rebuilds each card)...")
    records = collect(dates)
    report(records, args.min)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
