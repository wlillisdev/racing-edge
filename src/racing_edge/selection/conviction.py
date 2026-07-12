"""Conviction — how many of the LEARNED lenses align on a runner, mark-aware.

This session's hard lessons in one score. It REWARDS a well-in mark, proven course
form, the market sweet spot and the positive tells; it FLAGS the rising-mark penalty,
the unexposed improver-favourite (Loch Cuan / Who's Lope — beaten at short prices) and
the all-weather / big-field lottery. A nap is only CONFIDENT when the decisive lens —
the mark — was actually readable and nothing red-flags it. Otherwise it's a reasoned
lean, not a nap (a bad nap you don't eat). Pure.
"""

from __future__ import annotations

from dataclasses import dataclass

from racing_edge.domain.manner import nap_verdict
from racing_edge.domain.mark import mark_read
from racing_edge.domain.models import PastRun, Race, Runner
from racing_edge.domain.tells import match_tells


@dataclass(frozen=True)
class Conviction:
    aligned: tuple[str, ...]    # learned lenses that fired FOR it
    flags: tuple[str, ...]      # red flags AGAINST it
    mark_known: bool            # was the decisive lens (the mark) actually readable?

    @property
    def score(self) -> int:
        return len(self.aligned)

    @property
    def confident(self) -> bool:
        """A real nap: at least three lenses align, the MARK was read, nothing flags it."""
        return self.score >= 3 and self.mark_known and not self.flags


def _same_course(h: PastRun, race: Race) -> bool:
    return (bool(h.course and race.course)
            and h.course.strip().lower() == race.course.strip().lower())


def conviction(runner: Runner, race: Race, history: tuple[PastRun, ...],
               market_rank: int, field_size: int = 0, *,
               stable_strike: float | None = None, yard_no1: bool = False,
               local_strike: float | None = None, local_runs: int = 0,
               trip_strike: float | None = None, trip_runs: int = 0,
               jockey_course_strike: float | None = None,
               jockey_course_rides: int = 0) -> Conviction:
    """`stable_strike` (0..1, the yard's 14-day form) and `yard_no1` (the stable's #1
    rider is booked) are the INTENT dots — collected by evidence, printed on the brief,
    and, until 2026-07-03, never scored here. That night the engine napped a filly
    while two stronger profiles (I'm Next, Giant Haystacks — both won) sat structurally
    capped: favourites earned nothing (#19 missing), -9lb scored the same as 0lb, and
    intent couldn't score at all. The master's question — 'why weren't these part of
    today's read?' — is answered by the three lenses added below."""
    aligned: list[str] = []
    flags: list[str] = []

    mr = mark_read(runner.official_rating, history)
    if mr.delta is not None:
        if mr.delta <= 0:
            aligned.append(f"well-in ({mr.verdict})")
            if mr.delta <= -5:
                # MAGNITUDE matters: a 5lb+ gap is its own signal, not the same dot
                # twice (Giant Haystacks won off -9; it had scored level with a 0lb)
                aligned.append(f"heavily treated ({mr.delta}lb below last winning mark)")
        else:
            flags.append(f"raised {mr.verdict} since last win")

    # THE MANNER (rule #1 — read the finish, not the figures). The reader was built
    # months ago but starved: PastRun carried no comment until the window opened. Now
    # each recent run's in-running comment feeds it. A repeated out-battled/found-little
    # profile is a FLAG (a placer, not a nap); a proven finisher is a lens FOR it.
    mv = nap_verdict([h.comment for h in history[:4]])
    if mv.recommendation == "win_positive":
        aligned.append(f"finisher ({mv.finisher_runs} strong finish(es) in comments)")
    elif mv.recommendation == "place_only":
        flags.append("manner: out-battled/found little repeatedly — placer, not a nap (#1)")
    elif mv.recommendation == "excuse_upgrade":
        aligned.append("excuse last time (trouble in running) — form understates it")

    # CURRENT FORM / MOMENTUM (2026-07-09, the master: the nap faced an in-form rival
    # who "absolutely pissed in" — plain winning momentum had NO lens; the mark and
    # manner could both miss a horse that's simply red-hot right now)
    recent = [h.position for h in history[:3] if h.position is not None]
    if len(recent) >= 2 and recent[0] == 1 and recent[1] == 1:
        aligned.append("RED-HOT — won its last two")
    elif recent and recent[0] == 1:
        aligned.append("won last time out")
    if len(recent) >= 2 and all(p >= 6 for p in recent[:2]):
        flags.append(f"cold form ({'-'.join(str(p) for p in recent[:2])} last two)")

    course_wins = sum(1 for h in history if h.position == 1 and _same_course(h, race))
    if course_wins >= 2:
        aligned.append("proven course winner (depth)")
    elif course_wins == 1:
        aligned.append("course winner")

    price = runner.odds.consensus
    if market_rank in (2, 3):
        aligned.append("market sweet spot (2nd/3rd fav)")
    elif market_rank == 1 and price and price >= 2.5:
        # rule #19 — don't fear a FAIR-priced fav: pick the winner, not the price.
        # The engine had #2 without its counterweight, so the strongest profile on
        # the card scored a lens BEHIND a weaker one sitting 2nd fav (I'm Next, 2/1F).
        aligned.append("fair-priced favourite (#19 — the winner, not the price)")

    # INTENT (#5) — the yard's form and the booking. Half the winning jigsaw
    # (I'm Next: 17% yard + stable's #1 up) that conviction could never see.
    if stable_strike is not None and stable_strike >= 0.15:
        aligned.append(f"in-form yard ({round(stable_strike * 100)}%)")
    if yard_no1:
        aligned.append("stable's #1 rider up (intent)")
    # rule #10 — THE LOCAL MASTER off data at last: the yard that wins at THIS track
    if local_strike is not None and local_runs >= 10 and local_strike >= 0.18:
        aligned.append(f"local master yard ({round(local_strike * 100)}% at this "
                       f"course, {local_runs} runs — #10)")
    # the TRIP lens — proven at ~today's distance (the distance-times endpoint)
    if trip_strike is not None and trip_runs >= 4 and trip_strike >= 0.25:
        aligned.append(f"trip proven ({round(trip_strike * 100)}% over this distance, "
                       f"{trip_runs} runs)")
    # the #30 jockey lens — the rider who wins at THIS track, and its quiet inverse
    if jockey_course_strike is not None and jockey_course_rides >= 15:
        if jockey_course_strike >= 0.15:
            aligned.append(f"course jockey ({round(jockey_course_strike * 100)}% here, "
                           f"{jockey_course_rides} rides — #30)")
        elif jockey_course_strike == 0.0 and jockey_course_rides >= 25:
            flags.append(f"jockey 0/{jockey_course_rides} at this course (#30)")

    for t in match_tells(runner, race, history):
        if "LOCAL MASTER" in t:
            aligned.append("local course master")
        elif "headgear" in t.lower():
            aligned.append("headgear key")
        elif "distrust" in t:
            flags.append("rising-mark trap")

    # the profile that beat me twice — lightly raced, market leader, short price
    if len(history) <= 4 and market_rank == 1 and price and price <= 3.0:
        flags.append("improver-favourite (unexposed, short price)")
    if race.is_all_weather:
        flags.append("all-weather caution (#14)")
    if field_size >= 16:
        flags.append("big-field lottery")

    return Conviction(tuple(dict.fromkeys(aligned)), tuple(dict.fromkeys(flags)), mr.known)
