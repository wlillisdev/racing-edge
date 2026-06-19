"""
method_pick.py — THE METHOD as its own picker (standalone, parallel to the NAP).

This does NOT use the quant score. It builds a case from your handicapping lines
and picks the horse the method likes best — to run shoulder-to-shoulder with the
quant NAP and the shadow, logged, and judged on a few weeks of real results.

The case (transparent — every point carries a reason):
  + racing_wisdom : your coded read (class drop, weight, course+distance, pace,
                    freshness, market, narrative, field quality, form franking)
  + handicap_trajectory : well-in AND ahead of the mark (proven at the level)
  + improving form / knocking on the door     (from the form string)
  - perennial bottler (places, never wins)     (from the form string)
  + consistent gamble (steamer in market_movers)
The quant's job here is nothing. This is your eye, codified.

Writes data/method_pick_<date>.json — the day's Method NAP + every race's method
pick, each with its reasons, so you can audit exactly why it chose.

Usage:  python method_pick.py [YYYY-MM-DD]
"""

from __future__ import annotations

import sys
from typing import Optional

from racecard_loader import load_racecard
from src.helpers import data_path, log, safe_load_json, safe_write_json, today_str
from racing_wisdom import score_racing_wisdom, _parse_form_chars
from nap_selector_v3 import handicap_trajectory

MIN_ODDS, MAX_ODDS = 2.0, 7.0          # bettable value band (same as the NAP)
STEAMER_TYPES = {"steamer", "strong_steamer"}


def _consensus_price(runner: dict) -> Optional[float]:
    import statistics
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


def form_signals(form: str) -> tuple[float, list[str]]:
    """Improving-form (+) / perennial-bottler (-) read off the form string."""
    digits = [int(c) for c in (form or "") if c.isdigit()]   # left=oldest, right=newest
    if len(digits) < 3:
        return 0.0, []
    recent = list(reversed(digits))[:6]          # most-recent first
    wins = recent.count(1)
    places = sum(1 for p in recent if p in (2, 3))
    line = "".join(str(p) for p in reversed(recent))   # oldest->newest for display
    # Improving / knocking on the door takes precedence (an improver with
    # placings is NOT a bottler): newer runs clearly better, not yet winning.
    if wins == 0 and len(recent) >= 3:
        half = max(1, len(recent) // 2)
        newer, older = recent[:half], recent[half:]
        if (sum(newer) / len(newer)) < (sum(older) / len(older)) - 0.5 and min(recent[:2]) <= 3:
            return 4.0, [f"Improving - knocking on the door ({line})"]
    # Perennial bottler: no win, lots of placings, no upward trend -> leave it.
    if wins == 0 and places >= 3 and len(recent) >= 4:
        return -5.0, [f"Perennial placer ({line}) - runs well, won't win"]
    return 0.0, []


def steamer_signal(runner: dict, market_movers: Optional[dict]) -> tuple[float, list[str]]:
    hid = str(runner.get("horse_id") or "")
    for m in ((market_movers or {}).get("movements") or []):
        if str(m.get("horse_id") or "") == hid and m.get("move_type") in STEAMER_TYPES:
            return 3.0, ["Consistent gamble — market support"]
    return 0.0, []


def trajectory_signal(traj: dict) -> tuple[float, list[str]]:
    """Well-in AND ahead of the mark = live winner; topped-out = leave it."""
    t = traj.get("traj")
    if t == "live_winner":
        return 5.0, ["Well-in AND proven at the level — live winner"]
    if t == "topped_out":
        return -4.0, ["Topped out — only won below today's class"]
    if traj.get("well_in"):
        return 2.0, ["Well-in on the weights"]
    return 0.0, []


def method_case(runner: dict, race: dict, all_runners: list[dict],
                full_form: Optional[dict], market_movers: Optional[dict]) -> dict:
    """Build the method's case for one horse — pure read, no quant score."""
    reasons: list[str] = []
    total = 0.0

    w, wr = score_racing_wisdom(runner, race, all_runners, full_form)
    total += w
    if wr:
        reasons.append(f"[read +{w:.0f}] " + "; ".join(wr[:4]))

    for fn, args in (
        (trajectory_signal, (handicap_trajectory(runner, race, full_form),)),
        (form_signals, (runner.get("form") or "",)),
        (steamer_signal, (runner, market_movers)),
    ):
        pts, rs = fn(*args)
        total += pts
        reasons += rs

    return {
        "horse_id": str(runner.get("horse_id") or ""),
        "horse": runner.get("horse"),
        "trainer": runner.get("trainer"),
        "jockey": runner.get("jockey"),
        "price": _consensus_price(runner),
        "method_case": round(total, 2),
        "reasons": reasons,
    }


def build(date_str: Optional[str] = None) -> dict:
    date_str = date_str or today_str()
    doc = load_racecard(date_str) or {}
    full_form = safe_load_json(data_path(f"full_form_{date_str}.json"))
    market_movers = safe_load_json(data_path(f"market_movers_{date_str}.json"))

    race_picks: list[dict] = []
    for race in (doc.get("racecards") or []):
        runners = race.get("runners") or []
        if not runners:
            continue
        cases = [method_case(r, race, runners, full_form, market_movers) for r in runners]
        cases.sort(key=lambda c: -c["method_case"])
        top = cases[0]
        # Only a bettable pick if it's priced in the value band.
        top["bettable"] = top["price"] is not None and MIN_ODDS <= top["price"] <= MAX_ODDS
        top["course"] = race.get("course")
        top["off_time"] = race.get("off_time")
        top["race_name"] = race.get("race_name")
        race_picks.append(top)

    # The day's Method NAP: the strongest bettable case on the card.
    bettable = [p for p in race_picks if p["bettable"]]
    nap = max(bettable, key=lambda p: p["method_case"]) if bettable else None
    out = {"date": date_str, "method_nap": nap, "race_picks": race_picks}
    safe_write_json(data_path(f"method_pick_{date_str}.json"), out)
    log(f"method_pick: {len(race_picks)} race picks; "
        f"method NAP = {(nap or {}).get('horse', 'none')}")
    return out


def main() -> int:
    out = build(sys.argv[1] if len(sys.argv) > 1 else None)
    nap = out["method_nap"]
    print(f"METHOD PICK — {out['date']}  (standalone; your read, not the quant)")
    print("=" * 66)
    if nap:
        print(f"  METHOD NAP: {nap['horse']}  —  {nap['course']} {nap['off_time']}  "
              f"@ {nap['price']}  (case {nap['method_case']:+.0f})")
        for r in nap["reasons"]:
            print(f"     · {r}")
    else:
        print("  No bettable Method NAP today (nothing strong in the value band).")
    print("\n  per-race method picks:")
    for p in sorted(out["race_picks"], key=lambda x: -x["method_case"])[:12]:
        tag = "" if p["bettable"] else "  (out of band)"
        pr = f"@{p['price']:.1f}" if p["price"] else "no price"
        print(f"   {p['method_case']:>+5.0f}  {str(p['horse']):<20} {str(p['course'])[:10]:<10} {pr}{tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
