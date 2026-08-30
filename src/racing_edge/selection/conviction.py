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

from racing_edge.domain.manner import nap_verdict, read_manner
from racing_edge.domain.mark import mark_read, same_code_runs
from racing_edge.domain.models import PastRun, Race, Runner
from racing_edge.domain.tells import match_tells

# The lens FAMILIES — the currency conviction is scored in. The winning-era engine
# had ~6 orthogonal lenses, so score>=3 meant half the jigsaw agreed. By 2026-07-12
# there were ~15 stackable labels (regression audit: an in-form favourite from a hot
# yard could stack 8+ correlated labels and outrank the profile that actually won).
# Distinct FAMILIES restore the old meaning: two labels saying the same thing —
# "well-in" + "heavily treated", or course winner + course jockey — count once.
_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("mark", ("well-in",)),
    ("manner", ("finisher", "excuse last time")),
    ("momentum", ("RED-HOT", "won last time out")),
    ("course", ("course winner", "course form", "local master yard",
                "local course master", "course jockey")),
    ("trip", ("trip proven",)),
    ("market", ("market sweet spot", "fair-priced favourite")),
    ("intent", ("in-form yard", "#1 rider", "headgear key")),
)


@dataclass(frozen=True)
class Conviction:
    aligned: tuple[str, ...]    # learned lenses that fired FOR it
    flags: tuple[str, ...]      # red flags AGAINST it — these DISQUALIFY
    mark_known: bool            # was the decisive lens (the mark) actually readable?
    # CAUTIONS warn but never erase (the master, 2026-08-22: "just do the
    # opposite... but dont go all nuclear on the system"). The audit's receipt:
    # 'raised N lb since last win' had no quote and no receipts, crossed Too
    # Much Trevor (won 10/1), and on 2026-08-22 was the sole cross-off on
    # dozens of horses. A caution rides into the case as a warning the pick
    # must answer; it still blocks CONFIDENT. REVERT-IF: a week of marked
    # mornings reads worse than the week before this shipped.
    cautions: tuple[str, ...] = ()

    @property
    def score(self) -> int:
        """Distinct lens FAMILIES aligned (max 7) — not the raw label count."""
        return sum(1 for _name, keys in _FAMILIES
                   if any(k in a for k in keys for a in self.aligned))

    @property
    def confident(self) -> bool:
        """A real nap: at least three FAMILIES align, the MARK was read, nothing
        flags it — the winning-era bar, meaningful again."""
        return (self.score >= 3 and self.mark_known
                and not self.flags and not self.cautions)

    # the decisive-lens facts, exposed as PROPERTIES (2026-07-25 replication audit:
    # ranking, the top-class door and the fallback floor were each string-matching
    # the aligned labels — one rewording would have silently blinded all three)
    @property
    def well_in(self) -> bool:
        return any("well-in" in a for a in self.aligned)

    @property
    def stale_anchor(self) -> bool:
        return any("STALE" in f for f in self.flags)

    @property
    def placer_risk(self) -> bool:
        return any("placer risk" in f for f in self.flags)


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
    cautions: list[str] = []

    # form lenses read SAME-CODE runs only (2026-07-21 contamination audit: a horse
    # that won two jumps races read "RED-HOT" for a flat handicap, a chase faller
    # scored "excuse last time" on the flat, and a hurdles win at the track scored
    # "course winner"). Filter FIRST, window after.
    hist = same_code_runs(history, race.code)

    _well_in_pending = None
    mr = mark_read(runner.official_rating, history, code=race.code)
    if mr.delta is not None:
        if mr.delta <= 0:
            # ONE label, whatever the gap (the master, 2026-07-26: 'the well-in claim
            # is skewing all your picks — it is ONE piece of the jigsaw'). The former
            # 'heavily treated' magnitude label was the bigger-gap-is-better magnet in
            # print; the delta still shows inside the verdict for the honest reader.
            # UP IN GRADE rides inside the label (the master, 2026-07-26): a mark
            # earned beating Cl6 horses says little about beating Cl4 ones — the
            # reader weighs it as one dot of the jigsaw, eyes open
            grade = ""
            if (mr.win_class and race.race_class
                    and race.race_class < mr.win_class):
                grade = (f" but UP IN GRADE — won in Cl{mr.win_class}, "
                         f"today Cl{race.race_class}")
            # DEMOTED to a rough guide (the master, 2026-08-17: 'we base
            # everything on well in? why... the well in has proven only a
            # rough guide and has not been reliable'; his 2026-07-26 law: a
            # well-in figure counts only with current form and manner behind
            # it). A STALE well-in never counts; a fresh one is HELD here and
            # joins the aligned lenses below only if current form or manner
            # corroborates it. The mark can no longer be the spine of a score.
            if mr.stale:
                # THE WOODSTOCK LESSON (2026-07-25 audit): an exposed loser's mark
                # erodes BECAUSE it keeps losing — 'well-in' against a win 10+ runs
                # back is a placer's profile wearing the winning profile's coat
                flags.append(f"well-in anchor STALE (last win {mr.since} runs back) "
                             "— placer risk, not a missed handicapper")
                _well_in_pending = None
            else:
                _well_in_pending = f"well-in ({mr.verdict}{grade})"
        else:
            # THE WINNING MARK, against-side (law 3g, record-born week of
            # 2026-08-24, master's word 2026-08-27 'do the above'): the NARROW
            # cohort — won last time, mark raised for it, today the FIRST look
            # at the new mark — went 0-for-5 in a week of marked cards
            # (Vaguely Royal, Molly Mac, Is She Now, Kanzi, Town Queen 15/8F
            # trailed in LAST). It is a DISTINCT, NAMED caution — not a flag,
            # because the same profile has a winner on the ledger: Too Much
            # Trevor, crossed for this exact raise on 08-22, won 10/1. Honest
            # cohort 1-for-6 — enough to block CONFIDENT and strip the solid-
            # fav shield below, never enough to erase. The same flame never
            # takes the same skin twice, in either direction.
            # ...and refined the SAME NIGHT it shipped, after Captain Cairney
            # (3yo, won LTO, first run off a raise, quick return) led the
            # Southwell 9:00 start to finish. Law 3g-ii, the master's words:
            # a developing horse 'could win 2 or 3 on the bounce befire teh
            # handicapper cathed them espicially on the all weather' — the
            # raise LAGS the improvement. The against-read applies to a
            # BROKEN bounce (a long absence, per 2b-ii's own race-fit line:
            # Town Queen, 70 days, LAST) — never to a race-fit winner
            # straight back out. Unknown days stay cautious: fail loud.
            # THE CLASS RIDER (Gore Point, 2026-08-27, two hours after 3g-ii
            # shipped: 2-1-1-1-1, back out in 5 days, 5/6F in a Cl2 chase
            # 12lb of class out of his depth — LAST, beaten 50L by the
            # top-rated top weight): the bounce carries a horse AT HIS OWN
            # GRADE, never up one. A class hike re-arms the caution.
            if mr.since == 0:
                _hike = (mr.win_class is not None
                         and race.race_class is not None
                         and race.race_class < mr.win_class)
                # THE BIG-YARD FRESHENER (law 2b-iii, taught 2026-08-29
                # minutes after Forty Years On, 1112-1 and 79 days off, won
                # easily at 6/4 while the absence scars talked the book off
                # her: 'a big yard... they know what needs to be done to get
                # a horse fit... class horses will run well fresh'): a
                # DOMINANT profile — two or more wins in the last five
                # same-code runs — answers the absence leg by itself
                # (Forty Years On, Saint Polo, Notable Speech), while one
                # win on a quick-run staircase does not (Town Queen, LAST).
                # Dominance never buys the CLASS HIKE leg — Gore Point was
                # 2-of-5 dominant and 12lb out of his depth.
                _dominant = sum(1 for h in hist[:5] if h.position == 1) >= 2
                # THE YOUNG IMPROVER CARVE-OUT (the master's word 2026-08-29,
                # Kokbastau: 'a young horse improving could be anything, he
                # is still ahead of the handicapper'): the hike walls
                # EXPOSED horses; a 3yo's figures measure yesterday's horse.
                _young = runner.age is not None and runner.age <= 3
                _quick_return = (((runner.days_since_run is not None
                                   and runner.days_since_run < 60)
                                  or _dominant)
                                 and (not _hike or _young))
                if not _quick_return:
                    _why = ("up in class — the bounce never buys a hike "
                            "(Gore Point" if _hike else
                            "raise + absence (Town Queen")
                    cautions.append(f"first run off a raised mark "
                                    f"({mr.verdict}) with the bounce broken "
                                    f"— {_why} 2026-08-27, laws 3g/3g-ii)")
            else:
                # THE ANSWERED RAISE (law 3g-iii, the master's word
                # 2026-08-28 'implement': the engine's first-day nap Drymee
                # WON 11/8 by 5L yet banked NOT-confident on this very
                # caution — while his own record held the answer, 3rd in a
                # CLASS 3 off today's exact mark). A raise is the
                # handicapper's QUESTION; a run since the win that PLACED
                # (top 3) at-or-above today's class, off at-or-above
                # today's mark, is the ANSWER — the caution stands down.
                # Unknown class or mark on the run never counts: fail loud.
                _win_i = next((i for i, h in enumerate(hist)
                               if h.position == 1 and h.official_rating),
                              None)
                # ...and the answer is read in the COMMENTS (same-day corpse,
                # 2026-08-28 evening: Machete Beach 5/2F LAST beaten 38L —
                # his 3rd-and-2nd 'answer' read 'toiling... well held' and
                # 'lost the advantage': a surrender wearing frame digits,
                # while Drymee's answering 3rd 'kept on to take third close
                # home'. A placing whose comment classifies non_finisher is
                # a REFUSAL, not an answer; a blank comment still counts
                # here only because the feed often lacks them — the study
                # table holds the stricter line: blank = OWED).
                _answered = _win_i is not None and any(
                    h.position is not None and h.position <= 3
                    and h.official_rating is not None
                    and runner.official_rating is not None
                    and h.official_rating >= runner.official_rating
                    and h.race_class is not None
                    and race.race_class is not None
                    and h.race_class <= race.race_class
                    and read_manner(h.comment or "")[0] != "non_finisher"
                    for h in hist[:_win_i])
                if not _answered:
                    cautions.append(f"raised {mr.verdict} since last win")
    # THE FENCES ARE A DIFFERENT EXAM (2026-08-27, the Lady Kara corpse: every
    # positive dot was hurdle form; her chase record was one start, one rider
    # on the floor — she trailed in last at 5/2 as the engine's pick). In a
    # CHASE, a horse with no completed chase anywhere in its visible history
    # is a DISQUALIFIER-grade risk: hurdle class does not buy fences.
    if "chase" in (race.race_type or "").lower():
        _chase_runs = [h for h in history if "chase" in (h.race_type or "").lower()]
        if not any(h.position is not None for h in _chase_runs):
            flags.append("no completed chase — jumping unproven; hurdle form "
                         "does not buy fences (Lady Kara, 2026-08-27)")

    if len(hist) >= 6 and not any(h.position == 1 for h in hist):
        # comment-independent serial-placer catch (the audit's Giant/Woodstock pair:
        # the manner flag couldn't fire because every comment was missing)
        flags.append(f"no win in {len(hist)} visible runs — placer risk")

    # THE MANNER (rule #1 — read the finish, not the figures). The reader was built
    # months ago but starved: PastRun carried no comment until the window opened. Now
    # each recent run's in-running comment feeds it. A repeated out-battled/found-little
    # profile is a FLAG (a placer, not a nap); a proven finisher is a lens FOR it.
    mv = nap_verdict([h.comment for h in hist[:4]],
                     positions=[h.position for h in hist[:4]])
    if mv.recommendation == "win_positive":
        aligned.append(f"finisher ({mv.finisher_runs} strong finish(es) in comments)")
    elif mv.recommendation == "place_only":
        flags.append("manner: out-battled/found little repeatedly — placer, not a nap (#1)")
    elif mv.recommendation == "excuse_upgrade":
        aligned.append("excuse last time (trouble in running) — form understates it")

    # CURRENT FORM / MOMENTUM (2026-07-09, the master: the nap faced an in-form rival
    # who "absolutely pissed in" — plain winning momentum had NO lens; the mark and
    # manner could both miss a horse that's simply red-hot right now)
    recent = [h.position for h in hist[:3] if h.position is not None]
    if len(recent) >= 2 and recent[0] == 1 and recent[1] == 1:
        aligned.append("RED-HOT — won its last two")
    elif recent and recent[0] == 1:
        aligned.append("won last time out")
    if len(recent) >= 2 and all(p >= 6 for p in recent[:2]):
        # demoted to CAUTION 2026-08-27 (audit rec: DEMOTE, no quote; corpse:
        # Ecclefechan won 5/1 while "cold" — his 8-6-5-3 was an improving
        # staircase; bare figures without the trend read are blind, law 3d)
        cautions.append(f"cold form ({'-'.join(str(p) for p in recent[:2])} last two)")

    # the well-in verdict lands only NOW, corroboration known (2026-08-17):
    # counted with current form or manner behind it, otherwise named as the
    # rough guide it has proven to be — visible but scoreless.
    if _well_in_pending:
        corroborated = any(a.startswith(("finisher", "excuse last time",
                                         "RED-HOT", "won last time out"))
                           for a in aligned)
        if corroborated:
            aligned.append(_well_in_pending)
        else:
            # demoted to CAUTION 2026-08-27: this is an INFORMATIONAL note —
            # "the mark earns no credit" — that was somehow EXECUTING horses
            # (dozens crossed on 08-22 and 08-27 for the absence of a positive,
            # which nobody ever taught as a fault). It informs; it never erases.
            cautions.append("well-in NOT counted — no current form or manner "
                            "behind it (rough guide only, the master 2026-08-17)")

    course_wins = sum(1 for h in hist if h.position == 1 and _same_course(h, race))
    if course_wins >= 2:
        aligned.append("proven course winner (depth)")
    elif course_wins == 1:
        aligned.append("course winner")
    elif any(h.position is not None and h.position <= 3 and _same_course(h, race)
             for h in hist):
        # THE TRACK KNOWS ITS OWN (law 3h, the master 2026-08-28 after Saint
        # Polo — 2nd at Sedgefield 'locked together with winner', scored
        # NOTHING here, then won there at 3/1 while crossed: 'bear in mind
        # he had experience and form at this race track dont understimate
        # that'): a placed run at today's course is course FORM, not
        # nothing — one dot, same family as the win labels, so it can
        # never stack with them (families count once).
        aligned.append("course form (placed here — the track knows its own)")

    price = runner.odds.consensus
    if market_rank in (2, 3):
        aligned.append("market sweet spot (2nd/3rd fav)")
    elif market_rank == 1 and price and price >= 2.5:
        # rule #19 — don't fear a FAIR-priced fav: pick the winner, not the price.
        # The engine had #2 without its counterweight, so the strongest profile on
        # the card scored a lens BEHIND a weaker one sitting 2nd fav (I'm Next, 2/1F).
        # THE SHIELD GATE (law 2b-ii, record-born 2026-08-27, both edges on one
        # Carlisle card: Town Queen 15/8F — 70 days off, first run off a raise —
        # trailed in LAST; Ten Clarets, a never-won BF fav, beaten by an earned
        # departure at 9/4): a favourite failing the engine-visible parts of the
        # solid test — HAS WON, RACE-FIT, PROVEN AT THE MARK — earns no market
        # dot; the shield comes off and the holes ride in as a caution the case
        # must answer. It strips a dot, never erases the horse.
        _solid_holes = []
        # law 2b-iii: a dominant profile (2+ wins in the last five same-code
        # runs) answers the race-fit question wherever it is asked — Forty
        # Years On, 1112-1 and 79 days, won easily at 6/4 while the absence
        # hole talked the book off her. Dominance never waives a class hike.
        _gate_dominant = sum(1 for h in hist[:5] if h.position == 1) >= 2
        if not any(h.position == 1 for h in hist):
            _solid_holes.append("never won")
        if (runner.days_since_run is not None and runner.days_since_run >= 60
                and not _gate_dominant):
            _solid_holes.append(f"{runner.days_since_run} days off")
        if (mr.delta is not None and mr.delta > 0 and mr.since == 0
                and not (((runner.days_since_run is not None
                           and runner.days_since_run < 60) or _gate_dominant)
                         and not (mr.win_class is not None
                                  and race.race_class is not None
                                  and race.race_class < mr.win_class))):
            # law 3g-ii: a race-fit developing winner straight back out is
            # ON the bounce — the raise lags him; the broken bounce (raise +
            # absence) OR a class hike (Gore Point, 5/6F, last of 4 in a Cl2
            # his streak never sampled) punches the hole in the shield
            _solid_holes.append("first run off a raised mark, bounce broken")
        if _solid_holes:
            cautions.append("favourite but NOT solid ("
                            + ", ".join(_solid_holes)
                            + ") — shield off: why NOT take him on? (2b-ii)")
        else:
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
    # the TRIP lens — proven at ~today's distance. The distance-times endpoint
    # aggregates the WHOLE career across codes (13-17f is where flat and hurdles
    # overlap — 3-from-8 over 2m hurdles read "trip proven" for a 2m flat race), so
    # a mixed-code horse's trip is read from its same-code runs instead.
    if len(hist) < len(history):
        trips = [h for h in hist
                 if h.distance_f and race.distance_f
                 and abs(h.distance_f - race.distance_f) <= 1.0]
        trip_runs = len(trips)
        trip_strike = (sum(1 for h in trips if h.position == 1) / trip_runs
                       if trip_runs else None)
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
            # demoted to CAUTION 2026-08-27 (audit row: unreceipted squatter,
            # TRIAL): it crossed Thickthorn Tom, the master's read-at-a-glance
            # solid favourite, who won at 5/4 while the engine was cornered
            # onto Lady Kara (last, 41L). Trial record 1-1 as of demotion —
            # warns and counts, never erases (the master: "why take him on?")
            cautions.append("rising-mark trap")

    # the profile that beat me twice — lightly raced, market leader, short price
    if len(history) <= 4 and market_rank == 1 and price and price <= 3.0:
        flags.append("improver-favourite (unexposed, short price)")
    if race.is_all_weather:
        flags.append("all-weather caution (#14)")
    if field_size >= 16:
        flags.append("big-field lottery")

    return Conviction(tuple(dict.fromkeys(aligned)), tuple(dict.fromkeys(flags)),
                      mr.known, tuple(dict.fromkeys(cautions)))
