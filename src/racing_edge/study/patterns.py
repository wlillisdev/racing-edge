"""Pattern checks — test a proposed nuance against REAL results, not memory (#27).

When a self-study (or the master's eye) proposes a pattern, the honest next step is
not to argue about it — it's to CHECK IT against the record: sweep past days through
the box's real API and count. First pattern in the book, from the Epsom 6:22 study:

  LEAST-RAISED RECENT WINNER — in a handicap holding 2+ last-time-out winners, side
  with the one the assessor raised LEAST since its last win (the best-treated of the
  in-form horses). Does it win more than its share?

Pure: a gathered Restudy in, a verdict out. The sweep lives in cli.backcheck.
"""

from __future__ import annotations

from dataclasses import dataclass

from racing_edge.domain.mark import mark_read
from racing_edge.pipeline.restudy import Restudy


@dataclass(frozen=True)
class PatternHit:
    course: str
    off_time: str
    date: str
    horse: str
    delta: int              # the pick's rise since its last win (lowest in the race)
    rivals: int             # how many last-time-out winners were in the race
    won: bool
    sp_dec: float | None


def least_raised_recent_winner(st: Restudy) -> PatternHit | None:
    """Apply the pattern to one finished race. None = race doesn't qualify
    (fewer than two last-time-out winners with readable marks, or a tie for
    least-raised — ambiguous, so no bet)."""
    cands: list[tuple[str, str, int]] = []          # (horse_id, horse, delta)
    for r in st.race.runners:
        hist = st.histories.get(r.horse_id, ())
        if not hist or hist[0].position != 1:       # most recent run must be a WIN
            continue
        mr = mark_read(r.official_rating, hist)
        if mr.delta is None:
            continue
        cands.append((r.horse_id, r.horse, mr.delta))
    if len(cands) < 2:
        return None                                  # nothing to compare against
    best = min(d for _, _, d in cands)
    leaders = [c for c in cands if c[2] == best]
    if len(leaders) != 1:
        return None                                  # tie -> ambiguous -> no bet
    hid, horse, delta = leaders[0]
    rr = next((x for x in st.result.runners if x.horse_id == hid), None)
    return PatternHit(
        course=st.race.course, off_time=st.race.off_time, date=st.race.date.isoformat(),
        horse=horse, delta=delta, rivals=len(cands),
        won=bool(rr and rr.position == 1), sp_dec=rr.sp_dec if rr else None,
    )


def summarise(hits: list[PatternHit]) -> str:
    """The verdict lines: strike rate + level-stakes SP return. Small-sample honest."""
    if not hits:
        return "  No qualifying races — pattern untested."
    wins = [h for h in hits if h.won]
    n, w = len(hits), len(wins)
    stake_return = sum((h.sp_dec or 0.0) for h in wins) - n      # 1pt win stakes at SP
    lines = [
        f"  PATTERN VERDICT: {w}/{n} won ({100 * w / n:.0f}%), "
        f"level stakes at SP: {stake_return:+.1f}pt over {n} bets.",
        "  (small samples lie — treat under ~50 qualifiers as a lead, not a law.)",
    ]
    return "\n".join(lines)
