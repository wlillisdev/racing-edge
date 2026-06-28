"""Homework — forensically mine the studied races for what SEPARATES winners.

The notebook's rules are claims; this tests them against the body of real results
the study loop has banked. Where do winners come from in the market? Do they win
going away or scramble home? Which clues actually cluster on winners — the market
move, course form, trainer form? And our own picks: how often do we win, and when
we lose, do we lose as 'nearly types' (the system's core fault)?

Pure: study rows in, a HomeworkReport out. The numbers are DIRECTIONAL until the
sample is large — read them as leads to test, not proven edges.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

# (label, substring found in a race's joined lessons) — the clues we mine for.
# Strings must match the tags study_race() actually writes.
_CLUES = (
    ("market backed (the money knew)", "the money knew"),
    ("course winner", "a course winner"),
    ("trainer in form", "trainer in form"),
    ("proven trip & going", "proven over trip AND going"),
    ("claimer's relief", "claimer's relief"),
    ("headgear/wind angle", "headgear/wind change"),
    ("real scramble (rule #3)", "real scramble"),
)


def _rank_bucket(rank: int) -> str:
    return {1: "fav", 2: "2nd fav", 3: "3rd fav"}.get(rank, "4th+")


def _frank_verdict(lessons: str) -> str:
    if "FRANKED" in lessons:
        return "FRANKED"
    if "thin:" in lessons:
        return "thin"
    if "too soon" in lessons:
        return "too soon"
    return "not checked"


@dataclass(frozen=True)
class HomeworkReport:
    n_races: int
    n_ranked: int                       # races with a priced (rankable) winner
    rank_counts: dict[str, int]         # fav / 2nd fav / 3rd fav / 4th+
    rule2_hits: int                     # winner was 2nd or 3rd fav
    winner_manner: dict[str, int]       # finisher / non_finisher / ...
    clue_hits: dict[str, int]           # clue label -> races where it appeared on the winner
    frank_among_winners: dict[str, int]  # FRANKED / thin / too soon / not checked
    our_n: int                          # races where we had a pick
    our_wins: int
    our_places: int                     # finished 1-3
    our_loss_manner: dict[str, int]     # manner of our pick when it did NOT win


def analyse_homework(rows: Sequence[dict]) -> HomeworkReport:
    rank_counts = {"fav": 0, "2nd fav": 0, "3rd fav": 0, "4th+": 0}
    winner_manner: dict[str, int] = {}
    clue_hits = {label: 0 for label, _ in _CLUES}
    frank = {"FRANKED": 0, "thin": 0, "too soon": 0, "not checked": 0}
    loss_manner: dict[str, int] = {}
    n_ranked = rule2 = our_n = our_wins = our_places = 0

    for r in rows:
        rank = r.get("winner_market_rank")
        if rank is not None:
            n_ranked += 1
            rank_counts[_rank_bucket(int(rank))] += 1
            if rank in (2, 3):
                rule2 += 1
        wm = r.get("winner_manner") or "neutral"
        winner_manner[wm] = winner_manner.get(wm, 0) + 1
        lessons = r.get("lessons") or ""
        for label, sub in _CLUES:
            if sub in lessons:
                clue_hits[label] += 1
        frank[_frank_verdict(lessons)] += 1
        if r.get("our_pick"):
            our_n += 1
            pos = r.get("our_pick_pos")
            if pos == 1:
                our_wins += 1
            if pos is not None and pos <= 3:
                our_places += 1
            if pos != 1:
                pm = r.get("our_pick_manner") or "neutral"
                loss_manner[pm] = loss_manner.get(pm, 0) + 1

    return HomeworkReport(
        n_races=len(rows), n_ranked=n_ranked, rank_counts=rank_counts, rule2_hits=rule2,
        winner_manner=winner_manner, clue_hits=clue_hits, frank_among_winners=frank,
        our_n=our_n, our_wins=our_wins, our_places=our_places, our_loss_manner=loss_manner,
    )
