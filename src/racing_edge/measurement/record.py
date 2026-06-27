"""The settled-pick record — one immutable row per pick, written once after
results. The audit's fix for three split CSVs + double-logging: one canonical
record everything reads from, carrying the season/code so truth is never blended
and the price actually taken so CLV is real.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class SettledPick:
    date: date
    race_id: str
    horse_id: str
    horse: str
    system: str                    # "method" (the owner) | "favourite" (benchmark)
    season: str                    # nh_winter | flat_summer | shoulder
    code: str                      # jump | flat
    price_taken: float | None      # the price actually available when picked (NOT sp)
    sp: float | None               # settled price — for CLV and conservative P&L
    position: int | None

    @property
    def won(self) -> bool:
        return self.position == 1

    @property
    def clv(self) -> float | None:
        """Closing-line value: how much the price taken beat the off. The honest,
        fast signal of a real edge. Positive = you took a bigger price than the
        market closed at."""
        if self.price_taken and self.sp and self.sp > 1.0:
            return round(self.price_taken / self.sp - 1.0, 4)
        return None
