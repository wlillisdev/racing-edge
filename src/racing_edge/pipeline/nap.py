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
    race_quality: int = 0        # race-first ranking (the master, 2026-08-17: 'picking
                                 # the right race... is a weak point in the system'):
                                 # +1 honest handicap (the record's winning profile),
                                 # -1 per race gate flag. The RACE outranks the horse.


def race_quality_score(*, is_handicap: bool, concentration: float,
                       race_class: int | None, race_type: str,
                       field_size: int, n_race_flags: int,
                       is_aw: bool = False, hollow: bool = False) -> int:
    """THE BETTING-RACE FINGERPRINT (the master, 2026-08-17: 'we need to give
    ourself the best chance of winning consistently... lets go'), every term
    receipted by the 1,978-race study of that date:
      +1 honest handicap        (the record's winning profile, 6 of 8 winners)
      +1 concentrated market    (top-3 conc > 0.75: winner in front three 79%
                                 vs 45-55% in open markets — the strongest
                                 race-reading signal measured)
      +1 Class 3-4              (fav 38.2%, top-3 73% — the sweet spot)
      -1 hurdles                (fav ROI -26.5%, the quietly terrible code)
      -1 unclassed              (IRE unclassed: hierarchy weakest, fav -22.6%)
      -1 field of 12+           (front-three coverage collapses to ~55% —
                                 shape-bet territory, not form-bet)
      -1 per race gate flag     (the taught laws: novice-in-disguise, Cl6,
                                 anything-could-win shape)
    The score picks the RACE; the trap-avoidance discipline (my price first,
    defection rule) still picks the horse — nothing here nudges toward the
    favourite standing in the bookies' trap."""
    q = 0
    q += 1 if is_handicap else 0
    # HOLLOW CONCENTRATION (the master, 2026-08-19, after Percy's Lad 5th:
    # 'for the record that was a terrible race to pick in wolverhampton'):
    # a market can be short at the front because everything behind it is
    # dead wood — absentees, cold form, serial non-winners. That is a
    # coin-flip in a phone box, not a readable hierarchy. The concentration
    # bonus counts only when the field's QUALITY earned it.
    q += 1 if concentration > 0.75 and not hollow else 0
    q += 1 if race_class in (3, 4) else 0
    q -= 1 if "hurdle" in (race_type or "").lower() else 0
    q -= 1 if not race_class else 0
    q -= 1 if field_size >= 12 else 0
    # AW penalty — taught law #14, now receipted (2026-08-18 corpus split:
    # concentrated AW holds the front three 71.9% vs 79.9% on turf, fav ROI
    # -10.0% vs -6.6%): the surface itself taxes readability.
    q -= 1 if is_aw else 0
    q -= n_race_flags
    return q


def ew_advice(price: float | None, field_size: int) -> str:
    """Each-way as a CALCULATION, not the old 8.0 cliff (the master, 2026-07-26).
    Standard handicap terms: 16+ runners = 1/4 odds 4 places; 12-15 = 1/4 odds
    3 places; 8-11 = 1/5 odds 3 places. The place part stands on its own when
    frac*(price-1) >= 1: ~5.0+ at 1/4 odds, ~6.0+ at 1/5. Below 8 runners the
    terms rarely pay — win only."""
    if not price:
        return ""
    if field_size >= 16 and price >= 5.0:
        return (f"EACH-WAY (#28): {field_size} runners = 4 places at 1/4 odds — "
                f"the place part pays its own way at {price}")
    if field_size >= 12 and price >= 5.0:
        return f"EACH-WAY (#28): 3 places at 1/4 odds — place part pays at {price}"
    if field_size >= 8 and price >= 6.0:
        return f"EACH-WAY (#28): 3 places at 1/5 odds — place part pays at {price}"
    if price >= 8.0:
        return (f"price {price} but only {field_size} runners — place terms thin; "
                f"win single unless the book offers extra places")
    return ""


def market_shape(prices) -> tuple[str, float]:
    """The market's SHAPE from top-3 concentration (sum of 1/price) — not a cliff
    (the master, 2026-07-26: 'price threshold must not be so rigid'). A 4.9 fav with
    5.0s behind it is an open race; a 4.9 fav clear of a 9.0 field is anchored —
    same number, opposite meanings, and only the shape can tell them apart.
    >= 0.62 anchored | >= 0.52 loose | else OPEN."""
    top = sorted(p for p in prices if p and p > 1)[:3]
    conc = sum(1.0 / p for p in top)
    band = "anchored" if conc >= 0.62 else ("loose" if conc >= 0.52 else "OPEN")
    return band, conc


def anchor_bar(race_class: int | None) -> float:
    """The fav price at which a race's market counts as ANCHORLESS — defined ONCE
    (2026-07-25: the gate was class-tiered to 6.0 for Cl<=3 while the profile floor
    kept a flat 5.0, so the exact races the Saturday recalibration opened could pass
    the gate yet never bank). Top-class races earn the higher bar (rule #22)."""
    return 6.0 if (race_class or 9) <= 3 else 5.0


def _rank_key(p: NapPick) -> tuple[int, int, int, int, int, float]:
    # RACE QUALITY breaks ties (the master, 2026-07-05: "really bad race selections —
    # poor classes, anything could win"): between equal convictions, the pick in the
    # BETTER-CLASS race wins. A readable Class 3 beats a Class 6 scramble every time.
    # score is lens FAMILIES (coarse, honest); raw label count breaks family ties.
    # a READABLE mark ranks ahead of an OWED one (slot efficiency: the floor can't
    # bank mark-OWED picks) — but well-in itself carries no extra rank weight (the
    # master, 2026-07-26: the mark is one jigsaw piece and a veto, never a magnet).
    # RACE FIRST (the master, 2026-08-17: 'one of the big problems is picking
    # the right race i think this is a weak point in the system' — and his
    # 2026-07-05 law finally reaches the RANKING, not just the flags): the
    # readable race outranks the seductive horse. Within equal races, the
    # old horse-first key decides as before.
    return (p.race_quality,
            int(p.conviction.confident), int(p.conviction.mark_known),
            p.conviction.score, len(p.conviction.aligned),
            -(p.race.race_class or 6), -(p.price or 999.0))


def evaluate_field(client: _Client, day: str = "today",
                   codes: tuple[str, ...] = ("jump", "flat"), top_n: int = 4,
                   progress: Callable[[str], None] | None = None,
                   as_of=None, now=None) -> list[NapPick]:
    """EVERY contender in every readable race (handicaps + the Zavateri pattern
    gate), each given its own conviction read,
    sorted strongest-first. The fair-evaluation enforcement (rule #24): no horse is
    skipped, so a pick has to beat an even reading of the whole field, not an anchor.

    `progress`, if given, is called with a status line as each race is read — so the
    caller can NARRATE the (slow, per-horse) evidence fetch instead of sitting silent."""
    races = [r for r in racecards_from_raw(client.racecards(day))
             if r.is_readable and r.code in codes]
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
        progress(f"  reading the form on {len(races)} readable race(s) "
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
        import time as _time
        _t0 = _time.monotonic()
        evidence = {e.runner.horse_id: e
                    for e in build_evidence(race, client, as_of=as_of)}
        _dt = _time.monotonic() - _t0
        if progress and _dt > 30:
            # slow must never masquerade as stuck (2026-08-01: the racecards
            # results door carries whole past FIELDS per horse — fat payloads)
            progress(f"      (slow, not stuck: those {race.field_size} runners "
                     f"took {int(_dt)}s of API time)")
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
        # SCOPE FIX 2026-08-27 (Thickthorn Tom night): in an AGE-RESTRICTED race
        # (whole field 2yo/3yo — nurseries, 3yo-only handicaps) EVERYONE is young,
        # so "a novice in disguise" fires on 100% of them and erased Carlisle's
        # nursery wholesale — the exact race type the weight doctrine wins in
        # (Forest Berry, 2026-08-24). The gate's teaching (#13: young unexposed
        # horses hiding AMONG ELDERS) only means something in open-age company.
        _age_restricted = bool(priced) and all((r.age or 99) <= 3 for r in priced)
        if (contenders and not _age_restricted
                and young_unexposed >= 2 and young_unexposed * 2 >= contenders):
            race_flags.append("young-unexposed field — a novice in disguise (#13/#30)")
        # 2. grade: bottom-class racing is inconsistent animals — the form doesn't hold
        # THE CANDY EXEMPTION (the master, 2026-08-27, after Captain Cairney
        # 10/3 led the Southwell 9:00 start to finish on the far side of this
        # very wall: "that was a very winnable race, these should be easy
        # picks... these are the type of races we need to hoover up, taking
        # candy from a baby when you look at it properly"; and on the wall:
        # "keep an open mind as we recalibrate the system — if the opportunity
        # is there we should take"). Brief #15 splits the grade: bottom grade
        # + BIG open field of unexposed animals = the 07-05 lottery, wall
        # stands; bottom grade + SMALL field (the two-place each-way boundary,
        # <=7) + exactly ONE horse in winning form = the candy race — the wall
        # stands down and the read decides. REVERT-IF: a week of candy-race
        # picks reads worse than the dreck column they came from.
        _in_form = [p for p in race_picks
                    if p.history and p.history[0].position == 1]
        _candy = len(race_picks) <= 7 and len(_in_form) == 1
        if race.race_class and race.race_class >= 6 and not _candy:
            race_flags.append("bottom-grade race (Cl6) — inconsistent animals (#3)")
        # 3. market shape: a race with NO ANCHOR is the market itself saying anything
        #    could win. Rewritten 2026-07-26 on the master's ruling ('price threshold
        #    must not be so rigid'): the SHAPE decides, not a fav-price cliff — the
        #    top-3 concentration tells an anchored 4.9 from an open one.
        fav = min((p.price for p in race_picks if p.price), default=None)
        band, conc = market_shape([p.price for p in race_picks])
        if fav and band == "OPEN":
            race_flags.append(f"open market (fav {fav}, top-3 concentration "
                              f"{conc:.2f}) — anything-could-win shape (#3)")
        if race_picks and race_flags:
            race_picks = [
                replace(p, conviction=replace(
                    p.conviction, flags=(*p.conviction.flags, *race_flags)))
                for p in race_picks
            ]
        # RACE QUALITY, scored not just flagged (2026-08-17, extended same day
        # on the master's word with the 1,978-race fingerprint study). Rides
        # on every pick so the ranking puts the race before the horse.
        _dead = sum(1 for p in race_picks
                    if any(("cold form" in f) or ("no win in" in f)
                           or ("STALE" in f)
                           for f in (*p.conviction.flags,
                                     *p.conviction.cautions)))
        rq = race_quality_score(is_handicap=race.is_handicap, concentration=conc,
                                race_class=race.race_class,
                                race_type=race.race_type or "",
                                field_size=len(race_picks),
                                n_race_flags=len(race_flags),
                                is_aw="(AW)" in (race.course or ""),
                                hollow=_dead * 2 > len(race_picks))
        race_picks = [replace(p, race_quality=rq) for p in race_picks]
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
