"""
seasonal_context.py — what season is it, and what *kind* of race is this for the
time of year. Calendar reality, not stat-fitting.

The winter backtest proved every *fitted* edge flips by season (Good going was
+3% in summer, -30% in winter; jumps worst in summer, best in winter). But the
*structure* of the UK calendar is a fact, true every year:
  - NH (jumps) championship season is the WINTER — Nov-Mar. Summer jumping
    (May-Sep) is genuinely weak: the good horses are turned out.
  - Flat turf is the SUMMER — May-Sep prime. Winter flat is mostly All-Weather,
    a lesser product.
  - April and October are the shoulders, both codes live and mixed.

This module gives that context so the read knows what it's looking at — a prime
winter Grade race vs a summer seller-hurdle — WITHOUT excluding anything. A race
is still a race; this just says how high the bar should be.
"""

from __future__ import annotations

from datetime import date as _date
from typing import Optional


def racing_season(d: Optional[_date] = None) -> str:
    """'nh_winter' | 'flat_summer' | 'shoulder' — from the month, every year."""
    m = (d or _date.today()).month
    if m in (11, 12, 1, 2, 3):
        return "nh_winter"
    if m in (5, 6, 7, 8, 9):
        return "flat_summer"
    return "shoulder"               # April, October — transition


def is_jump_race(race: dict) -> bool:
    t = (race.get("type") or race.get("race_type") or "").lower()
    return any(k in t for k in ("chase", "hurdle", "bumper", "nh flat", "national hunt"))


# tier -> (label, selectivity). selectivity: how demanding the read should be.
#   "prime"   = in-season championship product — read it fully, normal bar.
#   "weak"    = off-season / lesser product — fields are soft, so DEMAND MORE:
#               a winner here must genuinely stand out (intent/class/breeding),
#               not just be the best of a bad bunch.
#   "mixed"   = shoulder months — judge on the race in front of you.
_TIERS = {
    "nh_prime":       ("Winter NH — prime",            "prime"),
    "nh_summer_weak": ("Summer NH — weak fields",       "weak"),
    "nh_shoulder":    ("NH — shoulder",                 "mixed"),
    "flat_prime":     ("Summer Flat — prime",           "prime"),
    "flat_winter_aw": ("Winter Flat/AW — lesser",       "weak"),
    "flat_shoulder":  ("Flat — shoulder",               "mixed"),
}


def race_tier(race: dict, d: Optional[_date] = None) -> dict:
    """Seasonal standing of this race: {season, is_jump, tier, label, selectivity}."""
    season = racing_season(d)
    jump = is_jump_race(race)
    if jump:
        key = {"nh_winter": "nh_prime",
               "flat_summer": "nh_summer_weak"}.get(season, "nh_shoulder")
    else:
        key = {"flat_summer": "flat_prime",
               "nh_winter": "flat_winter_aw"}.get(season, "flat_shoulder")
    label, selectivity = _TIERS[key]
    return {"season": season, "is_jump": jump, "tier": key,
            "label": label, "selectivity": selectivity}


def demands_extra(race: dict, d: Optional[_date] = None) -> bool:
    """True when this is an off-season/weak-field race — read it, but raise the
    bar: only bet a horse that genuinely stands out, never 'best of a bad lot'."""
    return race_tier(race, d)["selectivity"] == "weak"


if __name__ == "__main__":
    import datetime as _dt
    samples = [
        ("Winter hurdle (Jan)",  {"type": "Hurdle"},  _dt.date(2026, 1, 20)),
        ("Summer hurdle (Jun)",  {"type": "Hurdle"},  _dt.date(2026, 6, 16)),
        ("Summer flat (Jun)",    {"type": "Flat"},    _dt.date(2026, 6, 16)),
        ("Winter AW flat (Jan)", {"type": "Flat"},    _dt.date(2026, 1, 20)),
        ("April hurdle",         {"type": "Hurdle"},  _dt.date(2026, 4, 10)),
    ]
    for name, race, d in samples:
        t = race_tier(race, d)
        print(f"{name:<22} -> {t['label']:<26} selectivity={t['selectivity']}"
              f"  extra_bar={demands_extra(race, d)}")
