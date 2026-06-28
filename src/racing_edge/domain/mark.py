"""The handicap mark lens — the mark a horse last WON off vs today's mark.

The master's decisive read, and the one that beat me on Friday (Loch Cuan carried a
penalty; the winner was well-in). A horse running off the SAME or a LOWER mark than
when it last won is WELL-IN — the handicapper hasn't caught it. One carrying a HIGHER
mark has been raised and must defy it. Ratings are in pounds, so the delta IS the
weight swing. Pure: today's OR + the horse's history in, a MarkRead out.
"""

from __future__ import annotations

from dataclasses import dataclass

from racing_edge.domain.models import PastRun


@dataclass(frozen=True)
class MarkRead:
    today: int | None
    last_won: int | None        # the OR it ran off when it LAST won (None = never won / unknown)

    @property
    def delta(self) -> int | None:
        """Today's mark minus the mark it last won off — +ve = raised, <=0 = well-in."""
        if self.today is None or self.last_won is None:
            return None
        return self.today - self.last_won

    @property
    def known(self) -> bool:
        return self.delta is not None

    @property
    def verdict(self) -> str:
        d = self.delta
        if d is None:
            return ""                       # can't judge — no today mark or no prior win
        if d <= 0:
            return "WELL-IN" if d == 0 else f"WELL-IN {d}lb"
        return f"+{d}lb"                     # up in the weights since it won


def mark_read(today_or: int | None, history: tuple[PastRun, ...]) -> MarkRead:
    """today_or vs the OR it ran off the most recent time it WON."""
    last_won = next((h.official_rating for h in history
                     if h.position == 1 and h.official_rating), None)
    return MarkRead(today=today_or, last_won=last_won)
