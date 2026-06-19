"""
method_pick_check.py — the 3-way head-to-head: Method vs quant NAP vs Shadow.

For each date we have data for, take each system's pick, fetch the result, and
tally win% / place% / level-stakes ROI. This is the test you asked for — three
reads side by side, judged on real results.

Needs per date: racecards_<date>.json + full_form_<date>.json (for the Method
pick), nap_candidates_<date>.json (for the quant NAP + Shadow), and the API for
results. Days missing data are skipped.

Usage:
    python method_pick_check.py                 # today
    python method_pick_check.py --backfill 7    # last 7 days
    python method_pick_check.py 2026-06-19
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

_LOG = "scoreboard_log.csv"     # data/scoreboard_log.csv — banks every day's 3 outcomes


def _logged_dates() -> set:
    path = data_path(_LOG)
    if not os.path.exists(path):
        return set()
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["date"] for r in csv.DictReader(fh)}


def _append_log(rows: list[dict]) -> None:
    """Append (date, system, horse, won, placed, sp) rows; never double-log a date."""
    if not rows:
        return
    path = data_path(_LOG)
    is_new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "system", "horse", "won", "placed", "sp"])
        if is_new:
            w.writeheader()
        w.writerows(rows)


def summary() -> None:
    """The RUNNING scoreboard — cumulative win%/place%/ROI from the whole log."""
    path = data_path(_LOG)
    if not os.path.exists(path):
        print("No scoreboard log yet — run the check after some results.")
        return
    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8")))
    days = sorted({r["date"] for r in rows})
    print("=" * 60)
    print(f"RUNNING SCOREBOARD — {len(days)} day(s): {days[0]} → {days[-1]}")
    print("=" * 60)
    print(f"  {'system':<10}{'picks':>6}{'wins':>6}{'win%':>7}{'plc%':>7}{'ROI%':>8}")
    for s in ("METHOD", "NAP", "SHADOW"):
        sr = [r for r in rows if r["system"] == s]
        n = len(sr) or 1
        win = sum(r["won"] == "1" for r in sr)
        plc = sum(r["placed"] == "1" for r in sr)
        bets = [r for r in sr if r["sp"] not in ("", "None") and float(r["sp"]) > 1]
        pl = sum((float(r["sp"]) - 1) if r["won"] == "1" else -1 for r in bets)
        roi = 100 * pl / len(bets) if bets else 0.0
        print(f"  {s:<10}{len(sr):>6}{win:>6}{100*win/n:>6.0f}%{100*plc/n:>6.0f}%{roi:>7.1f}%")


def _result_lookup(date_str: str) -> dict:
    """horse_id -> {pos, sp} for the date's results."""
    try:
        doc = get_client().get_results_by_date(date_str) or {}
    except Exception as exc:  # noqa: BLE001
        log(f"method_pick_check: results fetch failed {date_str} — {exc}", "WARNING")
        return {}
    out: dict[str, dict] = {}
    for race in (doc.get("results") or []):
        for r in (race.get("runners") or []):
            hid = str(r.get("horse_id") or "")
            if not hid:
                continue
            sp = r.get("sp_dec") or r.get("bsp") or r.get("sp")
            try:
                sp = float(sp)
            except (TypeError, ValueError):
                sp = None
            out[hid] = {"pos": str(r.get("position") or "").strip(), "sp": sp}
    return out


def _outcome(pick: Optional[dict], results: dict) -> Optional[dict]:
    if not pick:
        return None
    res = results.get(str(pick.get("horse_id") or ""))
    if not res:
        return None
    try:
        pi = int(res["pos"])
    except (TypeError, ValueError):
        pi = 99
    return {"won": pi == 1, "placed": pi <= 3, "sp": res["sp"], "pos": res["pos"]}


def _fmt(o: Optional[dict]) -> str:
    if not o:
        return "no result"
    flag = "WON" if o["won"] else ("plc" if o["placed"] else f"{o['pos']}")
    sp = f"@{o['sp']:.1f}" if o["sp"] else ""
    return f"{flag} {sp}".strip()


def _tally(stats: dict, o: Optional[dict]) -> None:
    if not o:
        return
    stats["n"] += 1
    stats["win"] += 1 if o["won"] else 0
    stats["plc"] += 1 if o["placed"] else 0
    if o["sp"] and o["sp"] > 1:
        stats["bets"] += 1
        stats["pl"] += (o["sp"] - 1) if o["won"] else -1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=today_str())
    ap.add_argument("--backfill", type=int, default=0)
    ap.add_argument("--summary", action="store_true", help="Running scoreboard from the log (no API)")
    args = ap.parse_args()

    if args.summary:
        summary()
        return 0

    dates = [args.date]
    if args.backfill > 0:
        base = datetime.strptime(args.date, "%Y-%m-%d").date()
        dates = [(base - timedelta(days=i)).isoformat() for i in range(args.backfill)]

    systems = ["METHOD", "NAP", "SHADOW"]
    already = _logged_dates()
    new_rows: list[dict] = []

    print(f"{'date':<12}{'METHOD':<26}{'NAP':<26}{'SHADOW':<26}")
    print("-" * 90)
    for d in sorted(dates):
        results = _result_lookup(d)
        if not results:
            continue
        method_nap = (method_build(d) or {}).get("method_nap")
        napdoc = safe_load_json(data_path(f"nap_candidates_{d}.json")) or {}
        shadow_list = napdoc.get("shadow") or []
        picks = {"METHOD": method_nap, "NAP": napdoc.get("nap"),
                 "SHADOW": shadow_list[0] if shadow_list else None}
        cells = []
        for s in systems:
            o = _outcome(picks[s], results)
            cells.append(f"{str((picks[s] or {}).get('horse') or '-')[:14]:<15}{_fmt(o):<11}")
            if o and d not in already:    # bank it once, only resulted picks
                new_rows.append({"date": d, "system": s, "horse": (picks[s] or {}).get("horse"),
                                 "won": int(o["won"]), "placed": int(o["placed"]), "sp": o["sp"]})
        print(f"{d:<12}" + "".join(cells))

    _append_log(new_rows)
    if new_rows:
        print(f"\n  banked {len({r['date'] for r in new_rows})} new day(s) to {_LOG}")
    print()
    summary()    # always show the cumulative running scoreboard
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
