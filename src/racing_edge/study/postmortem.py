"""Post-mortem study — turn a result into a lesson, every race, every night.

For each race it asks the detective's questions: who won, were they the 2nd/3rd
favourite (rule #2), did the winner finish like a winner (rule #1), and — if we
picked — did our horse lose as a non-finisher we should have downgraded? Run over
the whole card it tests the notebook against reality and surfaces new patterns.

Pure: settled runners in, observations out. No network, no DB. The phrasing of the
lessons is deliberately plain so the owner can mark them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from racing_edge.domain.manner import Manner, read_manner


@dataclass(frozen=True)
class StudiedRunner:
    name: str
    finish_pos: int | None          # 1 = won; None = did not complete
    sp_dec: float | None            # starting price (decimal) — for market rank
    comment: str = ""               # in-running / closing comment


@dataclass(frozen=True)
class RaceStudy:
    winner: str | None
    winner_market_rank: int | None  # 1 = favourite, 2 = 2nd fav, ...
    winner_manner: Manner
    field_size: int
    our_pick: str | None
    our_pick_pos: int | None
    our_pick_manner: Manner
    lessons: tuple[str, ...]


def _market_rank(runners: Sequence[StudiedRunner]) -> dict[str, int]:
    priced = sorted([r for r in runners if r.sp_dec and r.sp_dec > 1.0],
                    key=lambda r: r.sp_dec)  # type: ignore[arg-type,return-value]
    return {r.name: i + 1 for i, r in enumerate(priced)}


def study_race(runners: Sequence[StudiedRunner], our_pick: str | None = None) -> RaceStudy:
    rank = _market_rank(runners)
    winner = next((r for r in runners if r.finish_pos == 1), None)
    pick = next((r for r in runners if r.name == our_pick), None) if our_pick else None
    w_rank = rank.get(winner.name) if winner else None
    w_manner = read_manner(winner.comment)[0] if winner else "neutral"
    p_manner = read_manner(pick.comment)[0] if pick else "neutral"

    lessons: list[str] = []
    if winner and w_rank in (2, 3):
        lessons.append(f"winner ({winner.name}) was the {w_rank}{'nd' if w_rank == 2 else 'rd'} "
                       "favourite — rule #2 held (2nd/3rd fav wins these)")
    if winner and w_manner == "finisher":
        lessons.append(f"winner finished like a winner ({read_manner(winner.comment)[1]!r}) "
                       "— rule #1: the winner's manner shows in the comment")
    if pick and pick.finish_pos != 1:
        if p_manner == "non_finisher":
            lessons.append(f"our pick ({pick.name}) lost as a NON-FINISHER "
                           f"({read_manner(pick.comment)[1]!r}) — rule #1 would have downgraded it")
        elif p_manner == "trouble":
            lessons.append(f"our pick ({pick.name}) met trouble "
                           f"({read_manner(pick.comment)[1]!r}) — bad luck, not a bad pick")
        elif winner and w_rank and pick.name in rank and rank[pick.name] == 1 and w_rank > 1:
            lessons.append(f"we napped the favourite and a bigger price ({winner.name}) beat us "
                           "— was this a scramble we should have left? (rule #3)")
    return RaceStudy(
        winner=winner.name if winner else None, winner_market_rank=w_rank,
        winner_manner=w_manner, field_size=len(runners),
        our_pick=our_pick, our_pick_pos=pick.finish_pos if pick else None,
        our_pick_manner=p_manner, lessons=tuple(lessons),
    )


@dataclass(frozen=True)
class CardStudy:
    n_races: int
    winner_was_2nd_or_3rd_fav: int    # how often rule #2 held across the card
    winner_was_fav: int
    studies: tuple[RaceStudy, ...]

    @property
    def rule2_rate(self) -> float | None:
        return self.winner_was_2nd_or_3rd_fav / self.n_races if self.n_races else None


def study_card(races: Sequence[Sequence[StudiedRunner]],
               our_picks: Sequence[str | None] | None = None) -> CardStudy:
    """Study every race on the card. our_picks (optional) aligns 1:1 with races."""
    picks = list(our_picks) if our_picks else [None] * len(races)
    studies = [study_race(r, picks[i] if i < len(picks) else None) for i, r in enumerate(races)]
    return CardStudy(
        n_races=len(studies),
        winner_was_2nd_or_3rd_fav=sum(1 for s in studies if s.winner_market_rank in (2, 3)),
        winner_was_fav=sum(1 for s in studies if s.winner_market_rank == 1),
        studies=tuple(studies),
    )
