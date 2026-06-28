"""Post-mortem study — interrogate a result the way we interrogated Cartmel.

Not three lazy questions — the full detective questionnaire we actually ran:
of the WINNER (why did it win, what could we have read beforehand?), of OUR PICK
(why did it lose, what did we miss?), and of the RACE (should we have been here?).

Crucially, when a clue can't be checked from the data on hand it is NOT skipped —
it's flagged as grunt work still owed ("TO CHECK: ..."). A detective says what he
hasn't verified. Pure: clues in, findings out.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from racing_edge.domain.manner import Manner, read_manner


@dataclass(frozen=True)
class StudiedRunner:
    name: str
    finish_pos: int | None              # 1 = won; None = did not complete
    sp_dec: float | None                # starting price (decimal)
    comment: str = ""                   # in-running / closing comment
    beaten_lengths: float | None = None # margin — cruel photo vs clear miss
    morning_dec: float | None = None    # morning price — for the market move vs SP
    official_rating: int | None = None  # today's mark
    course_winner: bool = False         # course / course-and-distance winner
    trip_proven: bool = False
    going_proven: bool = False
    trainer_in_form: bool | None = None
    claim_lbs: int = 0                  # claiming-jockey relief
    headgear_change: bool = False       # first-time headgear / wind-op angle


@dataclass(frozen=True)
class RaceStudy:
    winner: str | None
    winner_market_rank: int | None
    winner_manner: Manner
    field_size: int
    our_pick: str | None
    our_pick_pos: int | None
    our_pick_manner: Manner
    lessons: tuple[str, ...]            # findings — what the card taught
    gaps: tuple[str, ...] = field(default_factory=tuple)   # grunt work still owed


def _market_rank(runners: Sequence[StudiedRunner]) -> dict[str, int]:
    priced = sorted([r for r in runners if r.sp_dec and r.sp_dec > 1.0],
                    key=lambda r: r.sp_dec)  # type: ignore[arg-type,return-value]
    return {r.name: i + 1 for i, r in enumerate(priced)}


def _ordinal(n: int) -> str:
    return {1: "favourite", 2: "2nd favourite", 3: "3rd favourite"}.get(n, f"{n}th in the market")


def _move(r: StudiedRunner) -> str | None:
    """Backed or drifted, morning -> SP. None if we can't tell."""
    if not (r.morning_dec and r.sp_dec and r.morning_dec > 1 and r.sp_dec > 1):
        return None
    if r.sp_dec < r.morning_dec * 0.92:
        return "backed"
    if r.sp_dec > r.morning_dec * 1.08:
        return "drifted"
    return "steady"


def study_race(runners: Sequence[StudiedRunner], our_pick: str | None = None) -> RaceStudy:
    rank = _market_rank(runners)
    winner = next((r for r in runners if r.finish_pos == 1), None)
    pick = next((r for r in runners if r.name == our_pick), None) if our_pick else None
    w_rank = rank.get(winner.name) if winner else None
    w_manner = read_manner(winner.comment)[0] if winner else "neutral"
    p_manner = read_manner(pick.comment)[0] if pick else "neutral"
    lessons: list[str] = []
    gaps: list[str] = []

    # ---- the WINNER: why did it win, what could we have read? ---------------- #
    if winner:
        if w_rank:
            held = " — rule #2 held" if w_rank in (2, 3) else ""
            lessons.append(f"WINNER {winner.name} was the {_ordinal(w_rank)}{held}")
        mv = _move(winner)
        if mv == "backed":
            lessons.append("  market: BACKED into it (morning→SP) — the money knew")
        elif mv == "drifted":
            lessons.append("  market: DRIFTED yet won — unusual, the move misled")
        elif mv is None:
            gaps.append("winner's market move (no morning price captured)")
        if w_manner == "finisher":
            lessons.append(f"  finish: won like a winner ({read_manner(winner.comment)[1]!r})")
        elif w_manner == "non_finisher":
            lessons.append("  finish: scrambled home — a soft race? worth a look")
        elif not winner.comment:
            gaps.append("winner's running comment (read the finish)")
        if winner.course_winner:
            lessons.append("  course: a course winner — proven here (key at quirky tracks)")
        else:
            gaps.append("winner's course form (was it proven here?)")
        if winner.trip_proven and winner.going_proven:
            lessons.append("  conditions: proven over trip AND going")
        elif not (winner.trip_proven or winner.going_proven):
            gaps.append("winner's trip/going suitability")
        if winner.trainer_in_form:
            lessons.append("  yard: trainer in form")
        if winner.claim_lbs:
            lessons.append(f"  weight: {winner.claim_lbs}lb claimer's relief — ahead of the mark")
        if winner.headgear_change:
            lessons.append("  angle: headgear/wind change — trainer found the key")
        gaps.append(f"FRANK the winner: did the form behind {winner.name} produce winners since?")

    # ---- OUR PICK: why did it lose, what did we miss? ----------------------- #
    if pick and pick.finish_pos != 1:
        bl = pick.beaten_lengths
        if p_manner == "non_finisher":
            lessons.append(f"OUR PICK {pick.name} lost as a NON-FINISHER "
                           f"({read_manner(pick.comment)[1]!r}) — rule #1 would have downgraded it")
        elif p_manner == "trouble":
            lessons.append(f"OUR PICK {pick.name} met trouble "
                           f"({read_manner(pick.comment)[1]!r}) — bad luck, not a bad pick")
        elif not pick.comment:
            gaps.append("our pick's running comment (was it out-battled, or unlucky?)")
        if bl is not None and bl <= 0.75:
            lessons.append(f"  beaten only {bl}l — likely a cruel photo (variance), not a miss")
        elif bl is not None and bl >= 3.0:
            lessons.append(f"  beaten {bl}l — clearly held, a real miss to learn from")
        if winner and w_rank and rank.get(pick.name) == 1 and w_rank > 1:
            lessons.append(f"  we napped the fav; a {_ordinal(w_rank)} ({winner.name}) beat us "
                           "— a scramble to leave? (rule #3)")
        gaps.append(f"the mark: were we caught by the handicapper vs {pick.name}'s last win?")

    # ---- the RACE: should we have been here at all? ------------------------ #
    margins = [r.beaten_lengths for r in runners if r.beaten_lengths and r.beaten_lengths > 0]
    if len([m for m in margins if m <= 1.5]) >= 3:
        lessons.append("RACE: blanket finish (3+ within 1.5l) — a scramble, marginal NAP (rule #3)")

    return RaceStudy(
        winner=winner.name if winner else None, winner_market_rank=w_rank,
        winner_manner=w_manner, field_size=len(runners),
        our_pick=our_pick, our_pick_pos=pick.finish_pos if pick else None,
        our_pick_manner=p_manner, lessons=tuple(lessons), gaps=tuple(gaps),
    )


@dataclass(frozen=True)
class CardStudy:
    n_races: int
    winner_was_2nd_or_3rd_fav: int
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
