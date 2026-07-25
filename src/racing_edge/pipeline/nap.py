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


def _rank_key(p: NapPick) -> tuple[int, int, int, int, int, float]:
    # RACE QUALITY breaks ties (the master, 2026-07-05: "really bad race selections —
    # poor classes, anything could win"): between equal convictions, the pick in the
    # BETTER-CLASS race wins. A readable Class 3 beats a Class 6 scramble every time.
    # score is lens FAMILIES (coarse, honest); raw label count breaks family ties.
    # WELL-IN ranks first among equals (2026-07-25 audit: a mark-OWED conv-4 outranked
    # well-in conv-3 horses — wasting candidate slots and fallback places on picks the
    # sacred floor can never bank; the decisive lens now carries rank weight).
    return (int(p.conviction.confident), int(p.conviction.well_in), p.conviction.score,
            len(p.conviction.aligned), -(p.race.race_class or 6), -(p.price or 999.0))


def evaluate_field(client: _Client, day: str = "today",
                   codes: tuple[str, ...] = ("jump", "flat"), top_n: int = 4,
                   progress: Callable[[str], None] | None = None,
                   as_of=None, now=None) -> list[NapPick]:
    """EVERY contender in every readable handicap, each given its own conviction read,
    sorted strongest-first. The fair-evaluation enforcement (rule #24): no horse is
    skipped, so a pick has to beat an even reading of the whole field, not an anchor.

    `progress`, if given, is called with a status line as each race is read — so the
    caller can NARRATE the (slow, per-horse) evidence fetch instead of sitting silent."""
    races = [r for r in racecards_from_raw(client.racecards(day))
             if r.is_readable_handicap and r.code in codes]
    # LIVE-DAY TIME GUARD (2026-07-13, an 8pm manual run): races already OFF must
    # never be pickable — banking a race whose result exists would corrupt the
    # pre-off ledger. Off-times print without am/pm; racing runs ~11:00-21:45, so
    # hours 1-9 read as PM. Unparseable times are kept (safe: better shown than
    # silently dropped).
    if day == "today" and as_of is None:
        from datetime import datetime
        from datetime import timedelta as _td
        if now is None:
            # UK WALL-CLOCK, not box time (2026-07-25 reliability audit: the box
            # runs UTC; in BST a race gone off 55 minutes ago still read as 'still
            # to run' — the guard must speak the card's own timezone)
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo("Europe/London")).replace(tzinfo=None)
        _now = now                            # injectable clock — tests pass a morning

        def _still_to_run(r: Race) -> bool:
            try:
                h, m = r.off_time.strip().split(":")[:2]
                hh, mm = int(h), int(m[:2])
                if 1 <= hh <= 9:
                    hh += 12
                off = _now.replace(hour=hh, minute=mm, second=0)
                return off > _now + _td(minutes=5)
            except (ValueError, AttributeError):
                return True
        before = len(races)
        races = [r for r in races if _still_to_run(r)]
        if progress and before != len(races):
            progress(f"  time guard: {before - len(races)} race(s) already off — "
                     f"only {len(races)} still to run are readable")
    if progress:
        progress(f"  reading the form on {len(races)} readable handicap(s) "
                 f"(form first, price last — rule #29)…")
    out: list[NapPick] = []
    oddsless = 0
    for race in races:
        if progress:
            progress(f"    · {race.course} {race.off_time} — reading {race.field_size} runners")
        if race.runners and not any(r.odds.consensus and r.odds.consensus > 1
                                    for r in race.runners):
            oddsless += 1
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
                           stable_strike=strike, yard_no1=no1,
                           local_strike=ev.local_strike if ev else None,
                           local_runs=ev.local_runs if ev else 0,
                           trip_strike=ev.trip_strike if ev else None,
                           trip_runs=ev.trip_runs if ev else 0,
                           jockey_course_strike=ev.jockey_course_strike if ev else None,
                           jockey_course_rides=ev.jockey_course_rides if ev else 0)
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
        #    market itself saying anything could win — the blanket-finish lottery.
        #    Loosened 2026-07-21 (regression audit): fav>=4.0 in ANY 8+ field was
        #    crossing off the exact competitive Cl3/4 handicaps the banked winners
        #    came from (2nd/3rd fav at 4.5-6.5); the 4.0 bar now needs a 12+ field.
        #    Class-tiered 2026-07-25 (the Saturday audit): a 5.6 fav over ten exposed
        #    Cl2/3 handicappers is rule #22's green light ("study the FIELD"), not a
        #    lottery — top-class races get a 6.0 bar; everything else keeps 5.0.
        fav = min((p.price for p in race_picks if p.price), default=None)
        fav_bar = 6.0 if (race.race_class or 9) <= 3 else 5.0
        if fav and (fav >= fav_bar or (race.field_size >= 12 and fav >= 4.0)):
            crowd = " in a 12+ field" if fav < fav_bar else ""
            race_flags.append(f"open market (fav {fav}{crowd}) — "
                              "anything-could-win race (#3)")
        if race_picks and race_flags:
            race_picks = [
                replace(p, conviction=replace(
                    p.conviction, flags=(*p.conviction.flags, *race_flags)))
                for p in race_picks
            ]
        out.extend(race_picks)
    if oddsless and progress:
        # AN OUTAGE MUST NEVER WEAR DISCIPLINE'S COAT (2026-07-25 reliability audit:
        # an odds-feed failure produced an empty field and banked as an earned pass)
        progress(f"  ⚠ {oddsless} race(s) carried runners but NO odds — possible "
                 f"odds-feed outage; those races are unreadable, not passed on merit")
    out.sort(key=_rank_key, reverse=True)
    return out


def nominate_nap(client: _Client, day: str = "today",
                 codes: tuple[str, ...] = ("jump", "flat"), top_n: int = 4,
                 now=None) -> NapPick | None:
    """The day's nap: zero in on the strongest SURVIVOR after crossing off every horse
    with a flaw (rule #25 — eliminate first, then pick). None if all are crossed off."""
    survivors = [p for p in evaluate_field(client, day, codes, top_n, now=now)
                 if not p.conviction.flags]
    return survivors[0] if survivors else None
