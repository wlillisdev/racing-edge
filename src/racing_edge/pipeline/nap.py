"""Nominate THE nap — one bet a day, blind off the morning card.

Reads every readable handicap, scores each live contender's conviction (the learned
lenses, mark-aware), and nominates the single strongest. It fetches the RACECARD, not
results, so it is blind by construction — no window-luck. A nap is returned only as
CONFIDENT when the mark was read and nothing flags it; otherwise the best candidate is
returned flagged not-confident, and the caller can decline (a bad nap you don't eat).
"""

from __future__ import annotations

from dataclasses import dataclass

from racing_edge.data.evidence import build_evidence
from racing_edge.data.normalise import racecards_from_raw
from racing_edge.domain.models import Race, Runner
from racing_edge.selection.conviction import Conviction, conviction


class _Client:
    def racecards(self, day: str = "today") -> dict: ...
    def horse_results(self, horse_id: str, limit: int = 12) -> list[dict]: ...
    def trainer_jockeys(self, trainer_id: str) -> list[dict]: ...


@dataclass(frozen=True)
class NapPick:
    race: Race
    runner: Runner
    price: float | None
    conviction: Conviction


def _better(a: NapPick, b: NapPick | None) -> bool:
    if b is None:
        return True
    if a.conviction.confident != b.conviction.confident:
        return a.conviction.confident                 # a confident nap beats a flagged one
    if a.conviction.score != b.conviction.score:
        return a.conviction.score > b.conviction.score
    return (a.price or 999.0) < (b.price or 999.0)     # tie-break: the more fancied


def nominate_nap(client: _Client, day: str = "today",
                 codes: tuple[str, ...] = ("jump", "flat"), top_n: int = 4) -> NapPick | None:
    """The day's strongest single selection across the readable handicaps, or None."""
    races = [r for r in racecards_from_raw(client.racecards(day))
             if r.is_readable_handicap and r.code in codes]
    best: NapPick | None = None
    for race in races:
        evidence = {e.runner.horse_id: e for e in build_evidence(race, client)}
        priced = sorted([r for r in race.runners if r.odds.consensus and r.odds.consensus > 1],
                        key=lambda r: r.odds.consensus)        # type: ignore[arg-type,return-value]
        ranks = {r.horse_id: i + 1 for i, r in enumerate(priced)}
        for r in priced[:top_n]:
            ev = evidence.get(r.horse_id)
            hist = ev.history if ev else ()
            c = conviction(r, race, hist, ranks.get(r.horse_id, 99), race.field_size)
            cand = NapPick(race=race, runner=r, price=r.odds.consensus, conviction=c)
            if _better(cand, best):
                best = cand
    return best
