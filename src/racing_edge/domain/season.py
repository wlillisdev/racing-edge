"""Racing season from the calendar — the spine the old system imported and then
switched off (WEAK_TIER_PREMIUM = 0.0). Here it is first-class.

- National Hunt (jumps) championship season is the WINTER, Nov-Mar. Summer
  jumping (May-Sep) is genuinely weak — the good horses are turned out.
- Flat turf is the SUMMER, May-Sep. Winter flat is mostly All-Weather.
- April and October are the shoulders — both codes live.

The owner's edge is winter jumps; the season decides which code leads.
"""

from __future__ import annotations

from datetime import date


def racing_season(d: date) -> str:
    """'nh_winter' | 'flat_summer' | 'shoulder' from the month."""
    m = d.month
    if m in (11, 12, 1, 2, 3):
        return "nh_winter"
    if m in (5, 6, 7, 8, 9):
        return "flat_summer"
    return "shoulder"  # April, October


def prime_code(d: date) -> str:
    """The code that's in its championship season: 'jump' in winter, 'flat' in
    summer, 'mixed' in the shoulders."""
    season = racing_season(d)
    if season == "nh_winter":
        return "jump"
    if season == "flat_summer":
        return "flat"
    return "mixed"


def is_prime(race_code: str, d: date) -> bool:
    """Is this code in its prime season today? (jumps in winter = the owner's
    home turf). Shoulder months count both codes as live."""
    pc = prime_code(d)
    return pc == "mixed" or pc == race_code
