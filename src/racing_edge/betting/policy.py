"""The betting policy — every number in ONE place (the audit's rule).

Defaults encode the learnings. The value band is a STARTING HYPOTHESIS for
winter jumps (the +20.7% 2.0-4.0 / -68% 6.0+ findings were flat-summer numbers,
so they're tracked, not trusted): permissive here, to be narrowed only if the
measurement confirms it in jumps. Nothing is hard-coded as a law.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BettingPolicy:
    value_min: float = 2.0       # below this = odds-on, no value worth taking
    value_max: float = 10.0      # above this = the longshot bleed zone (tracked for jumps)
    ew_min: float = 5.0          # at/above this a single can be worth each-way
    stake_pct: float = 0.005     # flat fraction of bank per bet — the safe default (0.5%)
    bank: float = 1000.0
    kelly_enabled: bool = False  # OFF until a real edge is proven (1000+ bets, +ve CLV)
