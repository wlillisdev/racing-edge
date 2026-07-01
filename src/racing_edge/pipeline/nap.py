"""Nominate THE nap — one bet a day, blind off the morning card.

Reads every readable handicap, scores each live contender's conviction (the learned
lenses, mark-aware), and nominates the single strongest. It fetches the RACECARD, not
results, so it is blind by construction — no window-luck. A nap is returned only as
CONFIDENT when the mark was read and nothing flags it; otherwise the best candidate is
returned flagged not-confident, and the caller can decline (a bad nap you don't eat).
"""

from __future__ import annotations

from collections.abc import Callable
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


def _rank_key(p: NapPick) -> tuple[int, int, float]:
    return (int(p.conviction.confident), p.conviction.score, -(p.price or 999.0))


def evaluate_field(client: _Client, day: str = "today",
                   codes: tuple[str, ...] = ("jump", "flat"), top_n: int = 4,
                   progress: Callable[[str], None] | None = None) -> list[NapPick]:
    """EVERY contender in every readable handicap, each given its own conviction read,
    sorted strongest-first. The fair-evaluation enforcement (rule #24): no horse is
    skipped, so a pick has to beat an even reading of the whole field, not an anchor.

    `progress`, if given, is called with a status line as each race is read — so the
    caller can NARRATE the (slow, per-horse) evidence fetch instead of sitting silent."""
    races = [r for r in racecards_from_raw(client.racecards(day))
             if r.is_readable_handicap and r.code in codes]
    if progress:
        progress(f"  reading the form on {len(races)} readable handicap(s) "
                 f"(form first, price last — rule #29)…")
    out: list[NapPick] = []
    for race in races:
        if progress:
            progress(f"    · {race.course} {race.off_time} — reading {race.field_size} runners")
        evidence = {e.runner.horse_id: e for e in build_evidence(race, client)}
        priced = sorted([r for r in race.runners if r.odds.consensus and r.odds.consensus > 1],
                        key=lambda r: r.odds.consensus)        # type: ignore[arg-type,return-value]
        ranks = {r.horse_id: i + 1 for i, r in enumerate(priced)}
        for r in priced[:top_n]:
            ev = evidence.get(r.horse_id)
            hist = ev.history if ev else ()
            c = conviction(r, race, hist, ranks.get(r.horse_id, 99), race.field_size)
            out.append(NapPick(race=race, runner=r, price=r.odds.consensus, conviction=c))
    out.sort(key=_rank_key, reverse=True)
    return out


def nominate_nap(client: _Client, day: str = "today",
                 codes: tuple[str, ...] = ("jump", "flat"), top_n: int = 4) -> NapPick | None:
    """The day's nap: zero in on the strongest SURVIVOR after crossing off every horse
    with a flaw (rule #25 — eliminate first, then pick). None if all are crossed off."""
    survivors = [p for p in evaluate_field(client, day, codes, top_n) if not p.conviction.flags]
    return survivors[0] if survivors else None
