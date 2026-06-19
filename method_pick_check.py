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
from datetime import datetime, timedelta
from typing import Optional

from method_pick import build as method_build
from src.api_client import get_client
from src.helpers import data_path, log, safe_load_json, today_str


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
    args = ap.parse_args()

    dates = [args.date]
    if args.backfill > 0:
        base = datetime.strptime(args.date, "%Y-%m-%d").date()
        dates = [(base - timedelta(days=i)).isoformat() for i in range(args.backfill)]

    systems = ["METHOD", "NAP", "SHADOW"]
    stats = {s: {"n": 0, "win": 0, "plc": 0, "bets": 0, "pl": 0.0} for s in systems}

    print(f"{'date':<12}{'METHOD':<26}{'NAP':<26}{'SHADOW':<26}")
    print("-" * 90)
    for d in sorted(dates):
        results = _result_lookup(d)
        if not results:
            continue
        method_nap = (method_build(d) or {}).get("method_nap")
        napdoc = safe_load_json(data_path(f"nap_candidates_{d}.json")) or {}
        quant_nap = napdoc.get("nap")
        shadow_list = napdoc.get("shadow") or []
        shadow = shadow_list[0] if shadow_list else None

        picks = {"METHOD": method_nap, "NAP": quant_nap, "SHADOW": shadow}
        cells = []
        for s in systems:
            o = _outcome(picks[s], results)
            _tally(stats[s], o)
            name = (picks[s] or {}).get("horse") or "-"
            cells.append(f"{str(name)[:14]:<15}{_fmt(o):<11}")
        print(f"{d:<12}" + "".join(cells))

    print("-" * 90)
    print(f"{'':<12}{'picks':>6}{'wins':>6}{'win%':>7}{'plc%':>7}{'ROI%':>8}")
    for s in systems:
        st = stats[s]
        n = st["n"] or 1
        roi = 100 * st["pl"] / st["bets"] if st["bets"] else 0.0
        print(f"  {s:<10}{st['n']:>6}{st['win']:>6}{100*st['win']/n:>6.0f}%"
              f"{100*st['plc']/n:>6.0f}%{roi:>7.1f}%")
    print("\n  (small samples — this is the start of the head-to-head, not the verdict.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
