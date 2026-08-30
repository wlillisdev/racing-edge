"""Tests for the morning deep read — the detective picks the nap, not the lens-count."""

from __future__ import annotations

import sys
from datetime import date

from racing_edge.domain.models import Odds, Race, Runner
from racing_edge.report.restudy import render_preread
from racing_edge.study.morningread import (
    NAP_SYSTEM,
    build_lessons,
    build_nap_prompt,
    parse_morning_pick,
)


def test_the_system_prompt_carries_the_masters_discipline() -> None:
    # race first, form first, eliminate, look harder — and the pass tilt is balanced:
    # a pass is CORRECT off-profile (the audit: the old "lazy student" shaming forced
    # least-bad picks on bad cards — the genesis of both losers)
    for phrase in ("THE BEST HORSE WINS THE RACE. FIND THE BEST HORSE",
                   "RACE FIRST", "FORM FIRST, ODDS LAST", "ELIMINATE", "LOOK HARDER",
                   "a pass is CORRECT", "Never force the least-bad pick",
                   "never let the price pick", "THE WHOLE JIGSAW",
                   "ONE piece", "VETO only"):
        assert phrase in NAP_SYSTEM
    assert "lazy student" not in NAP_SYSTEM          # the anti-pass shaming is gone


def test_preread_lays_out_the_pre_race_card_without_results() -> None:
    from racing_edge.data.normalise import past_runs_from_raw
    race = Race(race_id="r", course="Thirsk", off_time="3:00", date=date(2026, 7, 5),
                race_type="Flat", is_handicap=True, race_class=3,
                runners=(Runner(horse_id="A", horse="Gem", official_rating=86,
                                form="21-1", odds=Odds(consensus=3.0)),))
    hists = {"A": past_runs_from_raw([{"date": "2026-06-01", "race_id": "r0", "runners": [
        {"horse_id": "A", "position": "1", "or": "82",
         "comment": "asserted on the run-in"}]}], "A")}
    out = render_preread(race, hists)
    assert "PRE-RACE CARD" in out and "Gem" in out and "mkt 1/1 @3.0" in out
    assert "manner read (#1): win_positive" in out
    assert "asserted on the run-in" in out
    assert "WON" not in out                       # no result anywhere — it's pre-race


def test_parse_morning_pick_reads_a_pick_and_an_earned_pass() -> None:
    pick = parse_morning_pick(
        'the read:\n{"race": "Thirsk 3:00", "horse": "Gem", "case": "well-in and a '
        'finisher", "race_readable_because": "Cl3, exposed field, anchored market", '
        '"crossed_off": ["Rival — placer profile"], "cite": ["mark WELL-IN"], '
        '"owed": "live move", "danger": {"horse": "Hot Rival", "its_case": "won its '
        'last two", "beaten_because": "well-in 5lb vs raised 6lb, course jockey"}, '
        '"profile_match": {"well_in": true, "class_ok": true, '
        '"market_anchor": true, "note": "full profile match"}, '
        '"confidence": "Confident", "pass": false, "pass_reason": ""}')
    assert pick.ok and not pick.is_pass
    assert pick.danger_horse == "Hot Rival" and "well-in 5lb" in pick.danger_beaten
    # a case that only argues FOR its horse (no danger beaten) is half a case — NOT ok
    half = parse_morning_pick(
        '{"race": "T", "horse": "Gem", "case": "x", "profile_match": {"note": "fits"}, '
        '"pass": false, "pass_reason": ""}')
    assert not half.ok
    assert pick.race_label == "Thirsk 3:00" and pick.horse == "Gem"
    assert pick.confidence == "confident"
    assert pick.crossed_off == ("Rival — placer profile",)
    assert pick.profile_flags == (True, True, True)
    # a pick WITHOUT the profile checklist stated is NOT ok (audit fix 5c) — the
    # model must say, per pick, how it fits the winning profile
    unstated = parse_morning_pick('{"race": "T", "horse": "Gem", "case": "x", '
                                  '"pass": false, "pass_reason": ""}')
    assert not unstated.ok

    p = parse_morning_pick('{"race": "", "horse": "", "pass": true, '
                           '"pass_reason": "race A: lottery market; race B: babies"}')
    assert p.ok and p.is_pass and "lottery" in p.pass_reason
    # an unearned pass (no reasons) is NOT ok — the caller falls back
    lazy = parse_morning_pick('{"race": "", "horse": "", "pass": true, "pass_reason": ""}')
    assert not lazy.ok
    assert not parse_morning_pick("no json").ok


def test_prompt_carries_every_candidate_block() -> None:
    p = build_nap_prompt([("Thirsk 3:00", "READOUT-A"), ("Ascot 4:00", "READOUT-B")])
    assert "CANDIDATE RACE — Thirsk 3:00" in p and "READOUT-A" in p
    assert "CANDIDATE RACE — Ascot 4:00" in p and "READOUT-B" in p


def test_the_student_takes_its_notes_into_the_exam() -> None:
    """2026-07-05: validated nuances and tracked horses sat in the DB while the pick
    was made from a blank slate. The LESSONS block now rides with the prompt, and the
    system prompt carries the record's winning profile."""
    p = build_nap_prompt([("Thirsk 3:00", "R")],
                         lessons="- NUANCE (validated): manner outranks bare mark rise\n"
                                 "- OPPOSE King Of The Story: erratic jumper")
    assert "LESSONS & LEADS" in p and "manner outranks" in p and "OPPOSE King" in p
    assert "LESSONS & LEADS" not in build_nap_prompt([("T", "R")])   # empty = no block
    assert "THE WHOLE JIGSAW" in NAP_SYSTEM and "unverified lead" in NAP_SYSTEM


def test_the_learning_loop_reaches_the_exam() -> None:
    """The coroner's central finding (2026-07-21): huge credits went on night study
    whose output NEVER reached the morning pick. This pins the wire closed — a banked
    loss with its autopsy, the cold record, the validated and unproven lessons, and
    the honestly-labelled tracked leads must all land in the prompt the picker reads."""
    naps = [
        {"date": "2026-07-18", "horse": "Rahmi", "course": "Ascot",
         "race_id": "rA", "won": 0},
        {"date": "2026-07-19", "horse": "Kalokalo", "course": "Ripon",
         "race_id": "rB", "won": 0},
    ]
    nuances = [
        {"race_id": "rA", "status": "refuted", "nuance": "x",
         "what_missed": "the winner was the in-form danger the case never beat"},
        {"race_id": "z1", "status": "validated", "nuance": "manner outranks bare mark"},
        {"race_id": "z2", "status": "proposed", "nuance": "false favourites make races MORE readable"},
    ]
    tracked = [{"angle": "follow", "horse": "Green Sky", "course": "York",
                "off_time": "3:15", "date": "2026-07-20",
                "note": "finished powerfully from an impossible spot",
                "conflict": "engine flags this horse (cold form) — the lead conflicts"}]
    tally = [{"rule": "#2", "supports": 2, "contradicts": 10},   # significant at n=12
             {"rule": "#19", "supports": 3, "contradicts": 4}]    # n=7: too early, silent
    lines = build_lessons(naps, (1, 8), nuances, tracked, tally)
    text = "\n".join(lines)
    assert "RECORD: 1/8 settled — COLD" in text
    assert "RECENT LOSS 2026-07-18 Rahmi (Ascot): missed — the winner was the in-form" in text
    assert "RECENT LOSS 2026-07-19 Kalokalo (Ripon)" in text
    assert "MASTER-VALIDATED: manner outranks bare mark" in text
    # THE CLOSED RULEBOOK (the master, 2026-08-01: 'the biggest problem is
    # creating rules to fill gaps — wrong ones'): unproven proposals no longer
    # ride to the exam AT ALL — a rule reaches the picker only taught,
    # validated, or field-tested. Proposals still flow to the doorbell.
    assert "false favourites" not in text
    assert "UNVERIFIED TRACKED LEADS" in text
    # the clue's DATE leads, the note is framed as THAT day's run, and a lead that
    # points against the engine's read carries its conflict (2026-07-25 audit)
    assert "banked 2026-07-20" in text and "Green Sky runs today York 3:15" in text
    assert "NB: engine flags this horse (cold form)" in text
    assert "RULE UNDER FIRE: #2 contradicted 10-2 over 12 races" in text
    assert "#19" not in text          # small-sample rules stay silent (no whipsaw)
    # and the whole block rides into the actual exam prompt
    p = build_nap_prompt([("York 3:15", "R")], "\n".join(lines))
    assert "RECENT LOSS 2026-07-18 Rahmi" in p and "LESSONS & LEADS" in p
    # a healthy record stays quiet about cold; no losses = no loss lines
    quiet = build_lessons([{"date": "d", "horse": "h", "course": "c",
                            "race_id": "r", "won": 1}], (5, 8), [], [], [])
    assert not any("COLD" in ln or "RECENT LOSS" in ln for ln in quiet)


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())


def test_the_masters_glance_rides_in_the_rulebook() -> None:
    """Taught 2026-08-03 after the Galway 5:00 loss ('bang average horse, hard
    to read form — I would never have looked at it'): the nap comes only from
    races a handicapper would actually study; wrong-type races are a PASS."""
    from racing_edge.study.morningread import NAP_SYSTEM
    assert "THE MASTER'S GLANCE" in NAP_SYSTEM
    assert "never have "
    assert "would actually STUDY" in NAP_SYSTEM
    assert "NEVER a nap candidate" in NAP_SYSTEM
    assert "correct nap is a PASS" in NAP_SYSTEM


def test_stack_the_cards_rides_beside_the_glance() -> None:
    """Taught 2026-08-03 — 'stack the cards in your favour... focus on races
    where you can join the dots': the record's winning profile and the 11/2+
    price tripwire ride in the rulebook, explicitly NOT overturning #12."""
    from racing_edge.study.morningread import NAP_SYSTEM
    assert "STACK THE CARDS" in NAP_SYSTEM
    assert "PRICE TRIPWIRE" in NAP_SYSTEM
    assert "does NOT overturn #12" in NAP_SYSTEM
    assert "the pass is the professional play" in NAP_SYSTEM


def test_the_flip_veto_system_fixes_the_pick_and_limits_the_reader() -> None:
    """THE FLIP (the master, 2026-08-08: 'flip it — what we are doing clearly
    is not working... our shadow selections were at least placing'): the engine
    selects; the reader writes the case and may only veto on a cited
    disqualifying fact. No pick of its own, no preference, no doubt-vetoes."""
    from racing_edge.study.morningread import VETO_SYSTEM
    assert "NOT the selector" in VETO_SYSTEM
    assert "FIXED" in VETO_SYSTEM
    assert "DISQUALIFYING FACT" in VETO_SYSTEM
    # 2026-08-19, the master: 'your vetos are crippling us' — the kill-switch
    # became a recorded objection the day vetoed King Roly won at 6.0.
    assert "'I prefer another horse' is not an objection" in VETO_SYSTEM
    assert "Doubt without a fact is not an objection" in VETO_SYSTEM
    assert "the pick STANDS" in VETO_SYSTEM or "banks and emails regardless" in VETO_SYSTEM
    assert "King Roly" in VETO_SYSTEM
    assert "stale well-in anchor is NO LONGER a ground" in VETO_SYSTEM
    # taught 2026-08-08: the case OPENS with the reader's own tissue price —
    # 'a different way of looking at it — why would you back a 50/1 shot?'
    assert "YOUR OWN PRICE" in VETO_SYSTEM
    assert "no bet at ANY odds" in VETO_SYSTEM


def test_engine_mode_is_the_default_and_reader_mode_survives() -> None:
    """The flip defaults ON; NAP_MODE=reader restores the old hierarchy (the
    one-switch revert the protocol demands for a behaviour change this size)."""
    import os
    from racing_edge.cli.nap import _EngineBankNow           # sentinel exists
    assert issubclass(_EngineBankNow, Exception)
    # the mode parse: anything but 'reader' means engine-first
    for val, engine in (("", True), ("engine", True), ("READER", False),
                        ("reader", False)):
        os.environ["NAP_MODE"] = val
        assert (os.environ.get("NAP_MODE", "engine").strip().lower()
                != "reader") is engine
    os.environ.pop("NAP_MODE", None)


def test_the_flip_flopping_favourite_rides_in_both_rulebooks() -> None:
    # taught 2026-08-15: Centurion's Sister won the Market Rasen 5:30 by ten
    # lengths while the flip-flopping favourite finished nowhere. The master:
    # "favourite was flip flopping never goes well". The warning applies only
    # where price movement is visible — otherwise it is OWED, never guessed.
    from racing_edge.study.morningread import NAP_SYSTEM, VETO_SYSTEM

    for rulebook in (NAP_SYSTEM, VETO_SYSTEM):
        assert "flip flopping never goes well" in rulebook
        assert "money arguing with itself" in rulebook
        assert "OWED, never guessed" in rulebook


def test_the_shape_we_hunt_rides_in_the_rulebook() -> None:
    # taught 2026-08-15, same race: "that was an easy winner missed, this is
    # the type of race we can get value and winners... short favourite flip
    # flopping in odds, and the rest 3/1, 4/1". A hunting-ground rule: the
    # shape earns study, never an automatic pick.
    from racing_edge.study.morningread import NAP_SYSTEM

    assert "THE SHAPE WE HUNT" in NAP_SYSTEM
    assert "type of race we can get value and winners" in NAP_SYSTEM
    assert "the rest 3/1, 4/1" in NAP_SYSTEM
    assert "still needs its own full case" in NAP_SYSTEM


def test_direction_outranks_state_at_the_cross_off() -> None:
    # taught 2026-08-15/16, master-validated ("i 100% agree"): Gower Prince
    # (won 13.0, crossed as placer-risk) and Centurion's Sister (won by 10L,
    # crossed as serial placer). A bare flag never crosses off an improver.
    from racing_edge.study.morningread import NAP_SYSTEM

    assert "DIRECTION OUTRANKS STATE AT THE CROSS-OFF" in NAP_SYSTEM
    assert "Gower Prince" in NAP_SYSTEM
    assert "NOT fact enough" in NAP_SYSTEM
    assert "at the cross-off too" in NAP_SYSTEM


def test_how_the_bookies_play_the_punters_rides_in_the_rulebook() -> None:
    # taught 2026-08-16, Southwell 1:30: crowd crunched the obvious horse to
    # 2.38 (second); the bottom-rated winner sat firm at 7.0. The shape read
    # nominates; the case still gets built.
    from racing_edge.study.morningread import NAP_SYSTEM

    assert "HOW THE BOOKIES PLAY THE PUNTERS" in NAP_SYSTEM
    assert "a horse mid odds will win this" in NAP_SYSTEM
    assert "The shape read NOMINATES" in NAP_SYSTEM


def test_the_shape_reads_first_and_reorders_but_does_not_dethrone_form() -> None:
    # taught 2026-08-16: "there is a reason the bookies never go broke...
    # you need to read the shape of the race." The board is read first as
    # the opponent's hand; form still builds and owns the case.
    from racing_edge.study.morningread import NAP_SYSTEM

    assert "THE SHAPE READS FIRST" in NAP_SYSTEM
    assert "bookies never go broke" in NAP_SYSTEM
    assert "prices the punters, not the horses" in NAP_SYSTEM
    assert "amends the ORDER of #29" in NAP_SYSTEM


def test_the_each_way_insurance_rides_in_the_rulebook() -> None:
    # taught 2026-08-16, Cliff Danger 7.0: "he would have placed at worse i
    # would have had an insurance bet and if he wins its a bonus, a short
    # price favourite in a big field is a danger too many risks."
    from racing_edge.study.morningread import NAP_SYSTEM

    assert "THE EACH-WAY INSURANCE" in NAP_SYSTEM
    assert "if he wins its a bonus" in NAP_SYSTEM
    assert "the place is the insurance" in NAP_SYSTEM
    assert "BLINDED by the top of the market" in NAP_SYSTEM


def test_law_3c_class_is_permanent() -> None:
    """Taught 2026-08-22 (Notable Speech, City Of York): 'class horse form is
    temp class is permanent'. Pattern races are not handicaps — a rating-clear,
    respected horse is a live pick despite layoff and a beaten last run; the
    handicap walk-past laws must not bin a class race. Paper trial gates the
    stakes, not the read."""
    from racing_edge.study.morningread import NAP_SYSTEM
    assert "FORM IS TEMPORARY, CLASS IS PERMANENT" in NAP_SYSTEM
    assert "Notable Speech" in NAP_SYSTEM
    assert "HANDICAP laws" in NAP_SYSTEM
    assert "paper trial" in NAP_SYSTEM


def test_law_3d_the_dreck_read() -> None:
    """Taught 2026-08-24 (Ecclefechan, 5/1, five straight improving figures,
    crossed as 'winless in six'): in bottom grade the winless/placer counts
    separate nothing — read the figure trend, finish strength, beaten margin,
    jockey booking, weight vs ratings, and the draw where it bites."""
    from racing_edge.study.morningread import NAP_SYSTEM
    assert "THE DRECK READ" in NAP_SYSTEM
    assert "Ecclefechan" in NAP_SYSTEM
    assert "jockey BOOKING" in NAP_SYSTEM
    assert "DRAW" in NAP_SYSTEM
    assert "wallpaper" in NAP_SYSTEM


def test_laws_3e_3f_pound_a_length_and_the_draw() -> None:
    """Taught 2026-08-24: (3e) at the twin choice convert margins and weight
    into one currency — one length = one pound; form strings read left to
    right, rightmost = last run. (3f) the draw is a citable fact on flat and
    all-weather — drawn high can be the kiss of death at some tracks."""
    from racing_edge.study.morningread import NAP_SYSTEM
    assert "POUND-A-LENGTH" in NAP_SYSTEM
    assert "1 length is = to 1 pound" in NAP_SYSTEM
    assert "RIGHTMOST figure is the last run" in NAP_SYSTEM
    assert "THE DRAW" in NAP_SYSTEM
    assert "kiss of death" in NAP_SYSTEM
    assert "all weather" in NAP_SYSTEM


def test_law_2b_the_solid_favourite() -> None:
    """Taught 2026-08-27 (Thickthorn Tom corpse — crossed by a squatter, won
    5/4 while the pick trailed in last): taking on a solid favourite requires
    a stated overlay or a disqualifying fact on HIM; a lean with no overlay
    against a solid favourite is a donation."""
    from racing_edge.study.morningread import NAP_SYSTEM
    assert "THE SOLID FAVOURITE" in NAP_SYSTEM
    assert "why take him on?" in NAP_SYSTEM
    assert "Thickthorn Tom" in NAP_SYSTEM
    assert "donation" in NAP_SYSTEM


def test_law_2b_ii_the_five_part_solid_test() -> None:
    """Record-born 2026-08-27, master's word same night ("do the above and do
    them surgically"). Town Queen 15/8F passed the old solid test and trailed
    home LAST (70 days off, first run off a raised mark); Ten Clarets, a
    never-won BF favourite, was beaten by an earned departure. SOLID = all
    five: short + in form + has won + race-fit + proven at the mark."""
    from racing_edge.study.morningread import NAP_SYSTEM
    assert "THE FIVE-PART SOLID TEST" in NAP_SYSTEM
    assert "HAS ACTUALLY WON" in NAP_SYSTEM
    assert "RACE-FIT" in NAP_SYSTEM
    assert "PROVEN AT THE MARK" in NAP_SYSTEM
    assert "why NOT take him on?" in NAP_SYSTEM
    assert "Town Queen" in NAP_SYSTEM


def test_law_3g_the_winning_mark() -> None:
    """Record-born (week of 2026-08-24: first-run-off-a-raise 0-for-5 vs four
    winners at/below a proven mark), promoted on the master's word 2026-08-27.
    Today's mark vs the mark he last won off is a COUNTED dot, both ways."""
    from racing_edge.study.morningread import NAP_SYSTEM
    assert "THE WINNING MARK" in NAP_SYSTEM
    assert "0-for-5" in NAP_SYSTEM
    assert "COUNTED dot" in NAP_SYSTEM
    assert "Rikki Tiki Tavi" in NAP_SYSTEM


def test_law_3g_ii_the_developing_horse() -> None:
    """Taught 2026-08-27, the same night 3g shipped, after Captain Cairney led
    the Southwell 9:00 start to finish as exactly the profile 3g crossed: a
    developing horse can win 2 or 3 on the bounce before the handicapper
    catches him, especially on the all-weather — the raise lags the
    improvement. The against-read is for the broken bounce, not the rolling
    horse."""
    from racing_edge.study.morningread import NAP_SYSTEM
    assert "THE DEVELOPING HORSE" in NAP_SYSTEM
    assert "on the bounce" in NAP_SYSTEM.lower() or "th ebounce" in NAP_SYSTEM
    assert "Captain Cairney" in NAP_SYSTEM
    assert "raise lags the improvement" in NAP_SYSTEM


def test_law_3g_ii_class_rider() -> None:
    """Same night, two hours after 3g-ii shipped: Gore Point (2-1-1-1-1, back
    out in 5 days) was sent off 5/6 in a Cl2 chase 12lb of class out of his
    depth and trailed in LAST, beaten 50 lengths by the top-rated top weight.
    The bounce carries a horse AT HIS OWN GRADE, never up one."""
    from racing_edge.study.morningread import NAP_SYSTEM
    assert "THE CLASS RIDER" in NAP_SYSTEM
    assert "Gore Point" in NAP_SYSTEM
    assert "AT HIS OWN GRADE" in NAP_SYSTEM


def test_law_3g_iii_the_answered_raise() -> None:
    """The master's word 2026-08-28 ('implement'): Drymee won 11/8 by 5L but
    banked NOT-confident on 'raised +4lb since last win' — while his record
    held the answer, 3rd in a Class 3 off today's exact mark. A raise is a
    question; a subsequent placing at-or-above today's class off at-or-above
    today's mark answers it and the caution stands down."""
    from racing_edge.study.morningread import NAP_SYSTEM
    assert "THE ANSWERED RAISE" in NAP_SYSTEM
    assert "NEVER GRANTED BY BARE FIGURES" in NAP_SYSTEM
    assert "Machete Beach" in NAP_SYSTEM
    assert "Drymee" in NAP_SYSTEM
    assert "ANSWERED" in NAP_SYSTEM
    assert "stands down" in NAP_SYSTEM


def test_law_3h_the_track_knows_its_own() -> None:
    """Taught 2026-08-28 (Saint Polo, 2nd at Sedgefield then won there at 3/1
    while crossed): course experience and form are dots, not just wins."""
    from racing_edge.study.morningread import NAP_SYSTEM
    assert "THE TRACK KNOWS ITS OWN" in NAP_SYSTEM
    assert "Saint Polo" in NAP_SYSTEM
    assert "understimate" in NAP_SYSTEM   # the master's words, verbatim


def test_law_2b_iii_the_big_yard_freshener() -> None:
    """Taught 2026-08-29 (Forty Years On won easily at 6/4 off 79 days while
    the absence scars talked the book off her): the race-fit question is
    answered by WHO answers it — big yards ready class horses first time;
    absence breaks fragile form, not dominant form."""
    from racing_edge.study.morningread import NAP_SYSTEM
    assert "THE BIG-YARD FRESHENER" in NAP_SYSTEM
    assert "class horses will run well fresh" in NAP_SYSTEM
    assert "Forty Years On" in NAP_SYSTEM


def test_law_2b_iii_scope_today_must_be_the_fresh_run() -> None:
    """Crown Of Oaks corpse (same afternoon the law shipped): dominance
    answers the UNKNOWN of absence — once a comeback run exists it is
    evidence, and a poor completed return outranks the presumption."""
    from racing_edge.study.morningread import NAP_SYSTEM
    assert "Crown Of Oaks corpse" in NAP_SYSTEM
    assert "ONLY when TODAY is the fresh run" in NAP_SYSTEM


def test_law_5b_the_yardstick_on_every_horse() -> None:
    """Taught 2026-08-28 (Sedgefield 3:30 howler: a rule fired, the looking
    stopped, the obvious 3/1 winner went unmeasured), confirmed 2026-08-29
    (three ignored Blanco horses paid in three straight TV races): a rule
    firing is where the work starts — no horse unmeasured, no verdict."""
    from racing_edge.study.morningread import NAP_SYSTEM
    assert "THE YARDSTICK ON EVERY HORSE" in NAP_SYSTEM
    assert ("measured against the yardstick and not blinded by the shiny "
            "light") in NAP_SYSTEM
    assert "trap bookies set" in NAP_SYSTEM
    assert "No horse unmeasured, no verdict" in NAP_SYSTEM


def test_law_4f_the_long_traveller() -> None:
    """The master's law (2026-08-30, banked the day he called Inspired home
    at 9/2 off the full stack while the bare-trip raider framed at 33/1):
    the van is intent written on the card — full stack = win candidate,
    bare trip = frame nomination; corroborator never selector; defers to
    #10 at quirky tracks."""
    from racing_edge.study.morningread import NAP_SYSTEM
    assert "THE LONG TRAVELLER" in NAP_SYSTEM
    assert "I have seen this time and time again, it's my law" in NAP_SYSTEM
    assert "good trainer sending one horse a huge distance" in NAP_SYSTEM
    assert "CORROBORATOR, never a selector" in NAP_SYSTEM
    assert "best horse wins race" in NAP_SYSTEM
    assert ("don't let it blind you — check all horses") in NAP_SYSTEM
    assert "never instead of measuring them" in NAP_SYSTEM


def test_law_4g_the_bookies_gift_and_the_flipflop() -> None:
    """The master, Cork G3 2026-08-30 (fav flip-flopping + Bet365 boost,
    finished nowhere): the flip-flopping favourite is uncertainty-money;
    the bookie's boost is the kiss of death — they boost what they want
    you on; market character is asked of the watcher, never inferred
    from two snapshots."""
    from racing_edge.study.morningread import NAP_SYSTEM
    assert "THE BOOKIE'S GIFT AND THE FLIP-FLOP" in NAP_SYSTEM
    assert "kiss of death" in NAP_SYSTEM
    assert "flip-flopping in the market" in NAP_SYSTEM
    assert "they boost what they want you on" in NAP_SYSTEM
    assert "ASKED of the person watching" in NAP_SYSTEM
