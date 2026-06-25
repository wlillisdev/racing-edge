"""
edge_tracker.py — the honest verdict: does the method beat the favourite?

The scoreboard logs ONE pick per system per day, so it takes months to mean
anything and reshuffles on noise week to week. This widens the sample to EVERY
bettable Method pick (10-15 a day) and judges them against the dumbest strategy
that exists: backing the market favourite in the same races, settled at SP.

That benchmark is the whole point. Being down isn't the question — almost
everything is down at level stakes. The question is whether the method's
selection adds value OVER blind favourite-backing. Two numbers decide it:

  • METHOD ROI   — back every bettable method pick at SP
  • FAVOURITE ROI — back the SP-favourite in those same races

If METHOD < FAVOURITE, the method is destroying value and we stop. If
METHOD > FAVOURITE over a real sample, there's a genuine edge to build on.
The sharpest cut: the method's CONTRARIAN picks (where it backs something
other than the favourite) — that's where it either earns its keep or bleeds.

No tuning. No thresholds. Just measurement, fast.

Usage:
  python edge_tracker.py --backfill 14     # build a real sample from saved days
  python edge_tracker.py 2026-06-24
  python edge_tracker.py --summary
"""

from __future__ import annotations

import argparse
import csv
import os
from datetime import datetime, timedelta
from typing import Optional

from method_pick import build as method_build
from src.api_client import get_client
from src.helpers import data_path, log, safe_load_json, today_str

LOG = "edge_log.csv"
FIELDS = ["date", "race_id", "horse", "won", "sp", "fav_horse", "fav_won", "fav_sp", "is_fav"]


def _to_float(v) -> Optional[float]:
    try:
        f = float(v)
        return f if f > 1.0 else None
    except (TypeError, ValueError):
        return None


def _race_outcomes(doc: dict) -> tuple[dict, dict]:
    """From a results doc return (horse_id -> {race_id,pos,sp}, race_id -> favourite info)."""
    horse: dict[str, dict] = {}
    fav: dict[str, dict] = {}
    for race in (doc.get("results") or []):
        rid = str(race.get("race_id") or "")
        best = None
        for r in (race.get("runners") or []):
            hid = str(r.get("horse_id") or "")
            sp = _to_float(r.get("sp_dec") or r.get("sp"))
            try:
                pos = int(str(r.get("position") or "").strip())
            except (TypeError, ValueError):
                pos = 99
            if hid:
                horse[hid] = {"race_id": rid, "pos": pos, "sp": sp}
            if sp is not None and (best is None or sp < best["sp"]):
                best = {"horse_id": hid, "horse": r.get("horse"), "sp": sp, "pos": pos}
        if best is not None:
            fav[rid] = best
    return horse, fav


def _logged_dates() -> set:
    path = data_path(LOG)
    if not os.path.exists(path):
        return set()
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["date"] for r in csv.DictReader(fh)}


def scan(date_str: str) -> int:
    """Settle every bettable Method pick for a date against results + the favourite."""
    if date_str in _logged_dates():
        return 0
    method = method_build(date_str) or {}
    picks = [p for p in (method.get("race_picks") or []) if p.get("bettable")]
    if not picks:
        return 0
    try:
        doc = get_client().get_results_by_date(date_str) or {}
    except Exception as exc:  # noqa: BLE001
        log(f"edge_tracker: results fetch failed {date_str} — {exc}", "WARNING")
        return 0
    horse, fav = _race_outcomes(doc)
    if not horse:
        return 0

    rows = []
    for p in picks:
        hid = str(p.get("horse_id") or "")
        o = horse.get(hid)
        if not o or o["sp"] is None:        # non-runner / unpriced -> skip
            continue
        f = fav.get(o["race_id"])
        if not f:
            continue
        rows.append({
            "date": date_str, "race_id": o["race_id"], "horse": p.get("horse"),
            "won": int(o["pos"] == 1), "sp": o["sp"],
            "fav_horse": f.get("horse"), "fav_won": int(f["pos"] == 1), "fav_sp": f["sp"],
            "is_fav": int(hid == str(f.get("horse_id") or "")),
        })
    _append(rows)
    return len(rows)


def _append(rows: list[dict]) -> None:
    if not rows:
        return
    path = data_path(LOG)
    is_new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if is_new:
            w.writeheader()
        w.writerows(rows)


def _roi(rows: list[dict], price_key: str, won_key: str) -> tuple[int, float, float]:
    """(n, win%, level-stakes ROI%) backing `price_key` when `won_key`."""
    bets = [r for r in rows if _to_float(r[price_key])]
    n = len(bets)
    if not n:
        return 0, 0.0, 0.0
    wins = sum(int(r[won_key] in ("1", 1)) for r in bets)
    pl = sum((_to_float(r[price_key]) - 1) if r[won_key] in ("1", 1) else -1 for r in bets)
    return n, 100 * wins / n, 100 * pl / n


def report() -> None:
    path = data_path(LOG)
    if not os.path.exists(path):
        print("No edge log yet — run a scan/backfill first.")
        return
    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8")))
    days = sorted({r["date"] for r in rows})
    n, mwin, mroi = _roi(rows, "sp", "won")
    _, fwin, froi = _roi(rows, "fav_sp", "fav_won")
    contrarian = [r for r in rows if r["is_fav"] in ("0", 0)]
    cn, cwin, croi = _roi(contrarian, "sp", "won")

    print("=" * 64)
    print(f"EDGE TRACKER — {n} bettable method picks over {len(days)} day(s)")
    print("  Does the method beat blind favourite-backing? (settled at SP)")
    print("=" * 64)
    print(f"  {'':<22}{'n':>5}{'win%':>7}{'ROI%':>9}")
    print(f"  {'METHOD picks':<22}{n:>5}{mwin:>6.0f}%{mroi:>8.1f}%")
    print(f"  {'FAVOURITE (same races)':<22}{n:>5}{fwin:>6.0f}%{froi:>8.1f}%")
    edge = mroi - froi
    print(f"  {'-> EDGE vs favourite':<22}{'':>5}{'':>7}{edge:>+8.1f}%")
    print()
    print(f"  method's CONTRARIAN picks (not the jolly): {cn}")
    if cn:
        print(f"      win {cwin:.0f}%   ROI {croi:+.1f}%   "
              f"(this is where the method's read lives or dies)")
    # by SP band
    print("\n  method picks by SP band:")
    bands = [("<= 2.0 (odds-on)", 1.0, 2.0), ("2.0-4.0", 2.0, 4.0),
             ("4.0-8.0", 4.0, 8.0), ("8.0+", 8.0, 9e9)]
    for label, lo, hi in bands:
        b = [r for r in rows if (_to_float(r["sp"]) or 0) > lo and (_to_float(r["sp"]) or 0) <= hi]
        if b:
            bn, bw, br = _roi(b, "sp", "won")
            print(f"    {label:<18}{bn:>5}{bw:>6.0f}%{br:>8.1f}%")

    print()
    if n < 100:
        print(f"  SAMPLE ({n}/100): firming up but not final. Direction only.")
    if edge > 0:
        print(f"  READ: method is BEATING the favourite by {edge:+.1f}%/£ — a real glimmer worth pressing.")
    else:
        print(f"  READ: method is {edge:+.1f}%/£ vs the favourite — no edge over the jolly yet.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=today_str())
    ap.add_argument("--backfill", type=int, default=0)
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()

    if args.summary:
        report()
        return 0

    dates = [args.date]
    if args.backfill > 0:
        base = datetime.strptime(args.date, "%Y-%m-%d").date()
        dates = [(base - timedelta(days=i)).isoformat() for i in range(args.backfill)]

    total = 0
    for d in sorted(dates):
        added = scan(d)
        if added:
            print(f"  {d}: +{added} picks")
            total += added
    print(f"\n  banked {total} picks")
    print()
    report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
