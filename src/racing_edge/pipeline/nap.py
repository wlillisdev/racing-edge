"""Nominate THE nap — one bet a day, blind off the morning card.

Reads every readable handicap, scores each live contender's conviction (the learned
lenses, mark-aware), and nominates the single strongest. It fetches the RACECARD, not
results, so it is blind by construction — no window-luck. A nap is returned only as
CONFIDENT when the mark was read and nothing flags it; otherwise the best candidate is
returned flagged not-confident, and the caller can decline (a bad nap you don't eat).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

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
    history: tuple = ()          # the contender's past runs — for the morning deep read


def _rank_key(p: NapPick) -> tuple[int, int, int, float]:
    # RACE QUALITY breaks ties (the master, 2026-07-05: "really bad race selections —
    # poor classes, anything could win"): between equal convictions, the pick in the
    # BETTER-CLASS race wins. A readable Class 3 beats a Class 6 scramble every time.
    return (int(p.conviction.confident), p.conviction.score,
            -(p.race.race_class or 6), -(p.price or 999.0))


def evaluate_field(client: _Client, day: str = "today",
                   codes: tuple[str, ...] = ("jump", "flat"), top_n: int = 4,
                   progress: Callable[[str], None] | None = None,
                   as_of=None) -> list[NapPick]:
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
        # as_of enforces NO LOOK-AHEAD for backtesting: histories cut strictly before
        # that date, current-stats intent lenses skipped (they know the future)
        evidence = {e.runner.horse_id: e
                    for e in build_evidence(race, client, as_of=as_of)}
        priced = sorted([r for r in race.runners if r.odds.consensus and r.odds.consensus > 1],
                        key=lambda r: r.odds.consensus)        # type: ignore[arg-type,return-value]
        ranks = {r.horse_id: i + 1 for i, r in enumerate(priced)}
        race_picks: list[NapPick] = []
        young_unexposed = 0
        # EVERY priced runner gets a conviction read (rule #24 — the audit: "the deep
        # read only sees 4 horses; Green Sky at 9/1 is exactly the horse it can't
        # weigh"). Evidence was always fetched for the whole field; now it's all used.
        for i, r in enumerate(priced):
            ev = evidence.get(r.horse_id)
            hist = ev.history if ev else ()
            # exposure counted over the top-6 of the market (age<=6 — the audit: a
            # 6yo lightly-raced field slipped the old age<=5 clause)
            if i < 6 and (r.age or 99) <= 6 and len(hist) <= 5:
                young_unexposed += 1
            # the INTENT dots (yard form + the stable's #1 booked) — collected here
            # all along, scored by conviction only since the I'm Next lesson
            strike = (ev.stable_wins / ev.stable_runs
                      if ev and ev.stable_runs and ev.stable_runs >= 8 else None)
            no1 = bool(ev and r.jockey_id and r.jockey_id in ev.stable_jockey_ids)
            c = conviction(r, race, hist, ranks.get(r.horse_id, 99), race.field_size,
                           stable_strike=strike, yard_no1=no1)
            race_picks.append(NapPick(race=race, runner=r, price=r.odds.consensus,
                                      conviction=c, history=hist))
        # THE RACE-SELECTION GATES (#3 — race selection before horse selection; the
        # master, 2026-07-05, after two poor naps: "unexposed horses, poor classes and
        # grade, anything could win — learn to pick the correct TYPE of race").
        race_flags: list[str] = []
        # 1. exposure (Chepstow 17:10, 2026-07-03): a field dominated by young,
        #    lightly-raced horses is a novice race in disguise, whatever the title
        contenders = min(len(race_picks), 6)
        if contenders and young_unexposed >= 2 and young_unexposed * 2 >= contenders:
            race_flags.append("young-unexposed field — a novice in disguise (#13/#30)")
        # 2. grade: bottom-class racing is inconsistent animals — the form doesn't hold
        if race.race_class and race.race_class >= 6:
            race_flags.append("bottom-grade race (Cl6) — inconsistent animals (#3)")
        # 3. market shape: a race with NO ANCHOR (big fav price / open field) is the
        #    market itself saying anything could win — the blanket-finish lottery
        #    (audit: a 4.5 fav in a 10-runner scramble slipped the old 12+ threshold)
        fav = min((p.price for p in race_picks if p.price), default=None)
        if fav and (fav >= 5.0 or (race.field_size >= 8 and fav >= 4.0)):
            race_flags.append(f"open market (fav {fav}) — anything-could-win race (#3)")
        if race_picks and race_flags:
            race_picks = [
                replace(p, conviction=replace(
                    p.conviction, flags=(*p.conviction.flags, *race_flags)))
                for p in race_picks
            ]
        out.extend(race_picks)
    out.sort(key=_rank_key, reverse=True)
    return out


def nominate_nap(client: _Client, day: str = "today",
                 codes: tuple[str, ...] = ("jump", "flat"), top_n: int = 4) -> NapPick | None:
    """The day's nap: zero in on the strongest SURVIVOR after crossing off every horse
    with a flaw (rule #25 — eliminate first, then pick). None if all are crossed off."""
    survivors = [p for p in evaluate_field(client, day, codes, top_n) if not p.conviction.flags]
    return survivors[0] if survivors else None
