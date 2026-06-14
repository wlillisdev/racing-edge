"""
longest_traveller_nap.py — a SEPARATE 'Longest Traveller NAP', presented
alongside the quant NAP. It NEVER touches or overrides the model's pick; it's
your travel-intent angle as its own shot, so you get two independent selections.

Qualifies the value version of the angle:
  longest traveller  +  in our 2.0-7.0 value band  +  consistent gamble
  (a steamer in market_movers)  +  in-form stable (trainer 14-day).

Usage:   python longest_traveller_nap.py [YYYY-MM-DD]
Reads:   data/longest_travellers_DATE.json, racecards_DATE.json,
         market_movers_DATE.json (optional — the gamble appears as the morning
         market firms; absent early, so re-run midday for the gamble check).
Writes:  data/traveller_nap_DATE.json
"""

from __future__ import annotations

import statistics
import sys
from typing import Optional

from src.helpers import data_path, log, safe_load_json, safe_write_json, today_str
from longest_travellers import load as load_travellers, normalise_horse

HOT_STABLE_PCT = 18.0          # trainer 14-day strike to call a stable "hot"
MIN_ODDS, MAX_ODDS = 2.0, 7.0  # our value band (matches the quant NAP gates)
STEAMER_TYPES = {"steamer", "strong_steamer"}


def _consensus_price(runner: dict) -> Optional[float]:
    """Median of the available book decimals (consensus), else SP forecast."""
    decs = []
    for o in (runner.get("odds") or []):
        try:
            d = float(o.get("decimal") or 0)
            if d > 1.0:
                decs.append(d)
        except (TypeError, ValueError):
            continue
    if decs:
        return round(statistics.median(decs), 2)
    try:
        sp = float(runner.get("sp_dec") or 0)
        return sp if sp > 1.0 else None
    except (TypeError, ValueError):
        return None


def _trainer_pct(runner: dict) -> Optional[float]:
    try:
        return float(str((runner.get("trainer_14_days") or {}).get("percent") or "")
                     .strip().rstrip("%"))
    except (TypeError, ValueError):
        return None


def build(date_str: Optional[str] = None) -> dict:
    date_str = date_str or today_str()
    travellers = (load_travellers(date_str).get("travellers")) or []
    rc = safe_load_json(data_path(f"racecards_{date_str}.json")) or {}
    mv = safe_load_json(data_path(f"market_movers_{date_str}.json")) or {}
    steamer_ids = {
        str(m.get("horse_id")) for m in (mv.get("movements") or [])
        if m.get("move_type") in STEAMER_TYPES
    }

    by_name: dict[str, tuple] = {}
    for race in (rc.get("racecards") or []):
        for r in (race.get("runners") or []):
            by_name[normalise_horse(r.get("horse"))] = (r, race)

    picks: list[dict] = []
    for t in travellers:
        hit = by_name.get(normalise_horse(t["horse"]))
        if not hit:
            continue  # traveller not on today's card (list was a different day)
        runner, race = hit
        price = _consensus_price(runner)
        pct = _trainer_pct(runner)
        in_band = price is not None and MIN_ODDS <= price <= MAX_ODDS
        hot = pct is not None and pct >= HOT_STABLE_PCT
        gambled = str(runner.get("horse_id")) in steamer_ids

        signals = []
        if in_band:
            signals.append(f"value band (@{price:.2f})")
        elif price is not None:
            signals.append(f"out of band (@{price:.2f})")
        if hot:
            signals.append(f"hot stable ({pct:.0f}%)")
        if gambled:
            signals.append("consistent gamble")

        picks.append({
            "horse": t["horse"], "horse_id": runner.get("horse_id"),
            "course": race.get("course"), "off_time": race.get("off_time"),
            "miles": t["miles"], "trainer": t["trainer"], "base": t["base"],
            "price": price, "trainer_14d": pct,
            "in_band": in_band, "hot_stable": hot, "gambled": gambled,
            # value version of your angle: in band AND (gamble or hot yard)
            "qualified": bool(in_band and (gambled or hot)),
            "signals": signals,
        })

    # Best first: most signals (band+gamble+hot), then furthest travelled.
    picks.sort(key=lambda p: (-(p["in_band"] + p["hot_stable"] + p["gambled"]), -p["miles"]))
    nap = next((p for p in picks if p["qualified"]), None)
    doc = {"date": date_str, "traveller_nap": nap, "travellers_on_card": picks}
    safe_write_json(data_path(f"traveller_nap_{date_str}.json"), doc)
    log(f"longest_traveller_nap: {len(picks)} traveller(s) on card, "
        f"{'1 qualified' if nap else 'none qualified'}")
    return doc


def main() -> int:
    doc = build(sys.argv[1] if len(sys.argv) > 1 else None)
    nap = doc["traveller_nap"]
    print(f"LONGEST TRAVELLER NAP — {doc['date']}  (separate from the quant NAP)")
    print("-" * 64)
    if nap:
        print(f"  ✈ {nap['horse']}  —  {nap['course']} {nap['off_time']}  ({nap['miles']} mi)")
        print(f"     {nap['trainer']} from {nap['base']}")
        print(f"     {' · '.join(nap['signals'])}")
    else:
        print("  No qualifying Longest Traveller NAP today "
              "(need: on card + value band + gamble or hot stable).")
    others = [p for p in doc["travellers_on_card"] if p is not nap]
    if others:
        print("\n  other travellers on the card:")
        for p in others:
            pr = f"@{p['price']:.2f}" if p["price"] else "no price"
            print(f"    {p['horse']:<22} {p['course']:<11} {p['miles']:>4}mi  "
                  f"{pr:<9} {', '.join(p['signals']) or 'no signals'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
