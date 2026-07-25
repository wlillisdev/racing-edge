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
    since: int | None = None    # runs between today and that win (0 = won last time out)

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
    def stale(self) -> bool:
        """The anchor is from a dead era (2026-07-25, the Woodstock audit): a horse
        that hasn't won in 10+ runs reads 'well-in' against its ancient winning mark
        precisely BECAUSE it kept losing — the opposite of the handicapper missing it."""
        return self.since is not None and self.since >= 10

    @property
    def verdict(self) -> str:
        d = self.delta
        if d is None:
            return ""                       # can't judge — no today mark or no prior win
        if d <= 0:
            base = "WELL-IN" if d == 0 else f"WELL-IN {d}lb"
            if self.stale:
                base += f" (STALE — last win {self.since} runs back)"
            return base
        return f"+{d}lb"                     # up in the weights since it won


def mark_read(today_or: int | None, history: tuple[PastRun, ...],
              code: str | None = None) -> MarkRead:
    """today_or vs the OR it ran off the most recent time it WON — within the SAME
    CODE when `code` is given. (2026-07-21, caught BY THE DEEP READ mid-pass: a flat
    mark of 61 was compared against a hurdles win off 107, producing a fantasy
    'WELL-IN -46lb'. Flat and jumps marks are different currencies — never convert.)"""
    from racing_edge.domain.units import race_code

    def _counts(h: PastRun) -> bool:
        # `since` is measured in SAME-CODE runs (2026-07-25 adversarial review: the
        # raw index counted a dual-code horse's jumps runs against its flat anchor —
        # a horse that won its last flat start read 'STALE, 10 runs back')
        return code is None or not h.race_type or race_code(h.race_type) == code

    for i, h in enumerate(history):
        if (h.position == 1 and h.official_rating
                and (code is None
                     or bool(h.race_type) and race_code(h.race_type) == code)):
            return MarkRead(today=today_or, last_won=h.official_rating,
                            since=sum(1 for x in history[:i] if _counts(x)))
    return MarkRead(today=today_or, last_won=None)


def same_code_runs(history: tuple[PastRun, ...], code: str) -> tuple[PastRun, ...]:
    """History filtered to runs in the SAME code as today's race. Filter FIRST, window
    after — a [:3] window sliced before filtering still reads the wrong-code runs
    (2026-07-21 contamination audit: momentum, manner, course and trip lenses were all
    scoring a flat race off jumps runs, and vice versa). A blank race_type is a data
    gap, not evidence of the wrong code: those runs stay in for the SOFT lenses. The
    sacred mark gate is stricter — mark_read refuses a blank-typed win as its anchor,
    because a fantasy well-in is worse than an OWED one."""
    from racing_edge.domain.units import race_code
    return tuple(h for h in history
                 if not h.race_type or race_code(h.race_type) == code)
