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
    for phrase in ("RACE FIRST", "FORM FIRST, ODDS LAST", "ELIMINATE", "LOOK HARDER",
                   "a pass is CORRECT", "Never force the least-bad pick",
                   "never let the price pick", "WINNING PROFILE"):
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
    assert "WINNING PROFILE" in NAP_SYSTEM and "unverified lead" in NAP_SYSTEM


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
    tally = [{"rule": "#2", "supports": 1, "contradicts": 4}]
    lines = build_lessons(naps, (1, 8), nuances, tracked, tally)
    text = "\n".join(lines)
    assert "RECORD: 1/8 settled — COLD" in text
    assert "RECENT LOSS 2026-07-18 Rahmi (Ascot): missed — the winner was the in-form" in text
    assert "RECENT LOSS 2026-07-19 Kalokalo (Ripon)" in text
    assert "MASTER-VALIDATED: manner outranks bare mark" in text
    assert "UNPROVEN nuance (weigh lightly): false favourites" in text
    assert "UNVERIFIED TRACKED LEADS" in text
    # the clue's DATE leads, the note is framed as THAT day's run, and a lead that
    # points against the engine's read carries its conflict (2026-07-25 audit)
    assert "banked 2026-07-20" in text and "Green Sky runs today York 3:15" in text
    assert "NB: engine flags this horse (cold form)" in text
    assert "RULE UNDER FIRE: #2 contradicted 4-1" in text
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
