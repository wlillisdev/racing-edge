"""Tests for reading the finish (rule #1) and the post-mortem study (the loop)."""

from __future__ import annotations

from datetime import date

from racing_edge.domain.manner import nap_verdict, read_manner
from racing_edge.study.postmortem import StudiedRunner, study_card, study_race
from racing_edge.study.store import StudyStore


# --------------------------------------------------------------------------- #
# reading the finish
# --------------------------------------------------------------------------- #
def test_read_manner_classifies() -> None:
    assert read_manner("led, headed final 100yds, no extra")[0] == "non_finisher"
    assert read_manner("stayed on strongly to win going away")[0] == "finisher"
    assert read_manner("hampered and short of room over 1f out")[0] == "trouble"
    assert read_manner("ran green, will improve")[0] == "green"
    assert read_manner("mid-division throughout")[0] == "neutral"


def test_read_manner_winning_flourish_beats_soft_phrase() -> None:
    # "kept on well" (finisher) should win over a stray soft word
    assert read_manner("kept on well to lead near the finish")[0] == "finisher"


def test_read_manner_knows_the_words_the_card_taught() -> None:
    """Earned 2026-07-01: 'asserted on the run-in' read NEUTRAL and the rules missed
    Knightsbridge (Worcester 1:50). The vocabulary grows as the eye sharpens."""
    assert read_manner("challenged at the last - asserted on the run-in")[0] == "finisher"
    assert read_manner("led at the last - asserted under pressure and forged clear")[0] \
        == "finisher"


def test_nap_verdict_downgrades_a_nearly_type() -> None:
    # out-battled twice in three runs -> placer, not a NAP (the "again" pattern)
    v = nap_verdict(["beaten a neck, no extra",
                     "every chance, found little",
                     "won readily"])
    assert v.recommendation == "place_only"
    assert v.non_finisher_runs == 2


def test_nap_verdict_backs_a_genuine_finisher() -> None:
    v = nap_verdict(["stayed on strongly to win", "ran on well when second"])
    assert v.recommendation == "win_positive"


def test_nap_verdict_flags_an_excuse() -> None:
    v = nap_verdict(["badly hampered when going well", "mid-field"])
    assert v.recommendation == "excuse_upgrade"


# --------------------------------------------------------------------------- #
# the study engine — runs over the whole card
# --------------------------------------------------------------------------- #
def test_study_race_flags_rule2_and_rule1() -> None:
    runners = [
        StudiedRunner("Fav", 3, 2.5, "every chance, no extra"),
        StudiedRunner("Second Fav", 1, 4.0, "ran on strongly to win"),
        StudiedRunner("Outsider", 2, 9.0, "kept on"),
    ]
    s = study_race(runners, our_pick="Fav")
    assert s.winner == "Second Fav" and s.winner_market_rank == 2
    assert any("rule #2 held" in lesson for lesson in s.lessons)
    assert any("rule #1" in lesson for lesson in s.lessons)
    # our pick lost as a non-finisher -> rule #1 would have downgraded it
    assert s.our_pick_manner == "non_finisher"
    assert any("NON-FINISHER" in lesson for lesson in s.lessons)


def test_study_race_asks_the_full_questionnaire() -> None:
    # a richly-clued winner: backed, finished well, course winner, claimer relief
    runners = [
        StudiedRunner("Gem", 1, 4.0, "stayed on strongly to win", morning_dec=8.0,
                      course_winner=True, trip_proven=True, going_proven=True,
                      trainer_in_form=True, claim_lbs=5),
        StudiedRunner("Fav", 3, 2.5, "every chance, no extra", beaten_lengths=1.0),
    ]
    s = study_race(runners, our_pick="Fav")
    joined = " | ".join(s.lessons)
    assert "BACKED into it" in joined           # market move read
    assert "won like a winner" in joined        # the finish
    assert "course winner" in joined            # course form
    assert "claimer's relief" in joined         # the weight nuance
    # and it owns the grunt work it could not do from the result alone
    assert any("FRANK the winner" in g for g in s.gaps)
    assert any("caught by the handicapper" in g for g in s.gaps)


def test_scramble_rule_is_strict() -> None:
    def field(third_btn: float) -> list[StudiedRunner]:
        def btn(i: int) -> float | None:
            return None if i == 1 else (third_btn if i == 3 else float(i))
        return [StudiedRunner(f"h{i}", i, 2.0 + i, beaten_lengths=btn(i)) for i in range(1, 9)]
    assert any("real scramble" in line for line in study_race(field(1.0)).lessons)
    assert not any("scramble" in line for line in study_race(field(3.0)).lessons)
    # and a tight finish in a SMALL field is not a scramble
    small = [StudiedRunner("a", 1, 2.0), StudiedRunner("b", 2, 3.0, beaten_lengths=0.5),
             StudiedRunner("c", 3, 4.0, beaten_lengths=1.0)]
    assert not any("scramble" in line for line in study_race(small).lessons)


def test_owed_only_when_not_checked() -> None:
    # checked (history fetched) but not a course winner -> NOT owed, just silently not a factor
    checked = study_race([StudiedRunner("W", 1, 3.0, "won well", enriched=True)])
    assert not any("course form" in g for g in checked.gaps)
    assert not any("FRANK" in g for g in checked.gaps)
    # never checked -> genuinely owed
    owed = study_race([StudiedRunner("W", 1, 3.0, "won well", enriched=False)])
    assert any("course form" in g for g in owed.gaps)
    assert any("FRANK" in g for g in owed.gaps)


def test_study_race_excuses_unlucky_pick() -> None:
    runners = [
        StudiedRunner("Ours", 2, 3.0, "denied a clear run when staying on"),
        StudiedRunner("Winner", 1, 2.0, "made all, kept on well"),
    ]
    s = study_race(runners, our_pick="Ours")
    assert any("bad luck, not a bad pick" in lesson for lesson in s.lessons)


def test_study_card_aggregates_rule2_rate() -> None:
    race_a = [StudiedRunner("A", 1, 4.0), StudiedRunner("B", 2, 2.5)]   # 2nd fav won
    race_b = [StudiedRunner("C", 1, 2.0), StudiedRunner("D", 2, 5.0)]   # fav won
    card = study_card([race_a, race_b])
    assert card.n_races == 2
    assert card.winner_was_2nd_or_3rd_fav == 1 and card.winner_was_fav == 1
    assert card.rule2_rate == 0.5


# --------------------------------------------------------------------------- #
# the study store — the detective work persists and stays queryable
# --------------------------------------------------------------------------- #
def test_study_store_persists_and_queries() -> None:
    store = StudyStore(":memory:")
    s1 = study_race([StudiedRunner("A", 1, 4.0), StudiedRunner("B", 2, 2.5)])  # 2nd fav won
    s2 = study_race([StudiedRunner("C", 1, 2.0), StudiedRunner("D", 2, 5.0)])  # fav won
    store.record(day=date(2026, 6, 27), race_id="r1", course="Kelso", study=s1)
    store.record(day=date(2026, 6, 27), race_id="r2", course="Ayr", study=s2)
    assert store.count() == 2
    assert store.rule2_rate() == (1, 2)         # rule #2 held in 1 of 2
    # idempotent — re-recording the same race replaces, not duplicates
    store.record(day=date(2026, 6, 27), race_id="r1", course="Kelso", study=s1)
    assert store.count() == 2
    store.close()


def test_enrich_from_card_and_history() -> None:
    from racing_edge.domain.models import Odds, PastRun, Race, Runner
    from racing_edge.study.enrich import enrich_from_card, enrich_from_history
    race = Race(race_id="r1", course="Kelso", off_time="14:00", date=date(2026, 2, 1),
                race_type="Chase", distance_f=20.0, going="Soft",
                runners=(Runner(horse_id="a", horse="A", odds=Odds(consensus=6.0),
                                trainer_14d_runs=10, trainer_14d_wins=2, claim_lbs=5,
                                headgear_first_time=True),))
    base = [StudiedRunner(name="A", horse_id="a", finish_pos=1, sp_dec=4.5)]
    e = enrich_from_card(base, race)[0]
    assert e.morning_dec == 6.0          # the move: backed 6.0 -> 4.5
    assert e.trainer_in_form is True     # 2/10 = 0.20 strike
    assert e.claim_lbs == 5 and e.headgear_change is True

    hist = (PastRun(date=date(2026, 1, 1), position=1, going="Soft",
                    distance_f=20.0, course="Kelso"),)
    h = enrich_from_history(e, hist, race)
    assert h.course_winner and h.trip_proven and h.going_proven


def test_frank_form_counts_rivals_scored_since() -> None:
    from racing_edge.domain.models import PastRun
    from racing_edge.study.frank import frank_form

    class _C:
        def results_by_date(self, ds: str) -> dict:
            if ds == "2026-06-01":
                return {"results": [{"race_id": "last1", "date": "2026-06-01", "runners": [
                    {"horse_id": "W"}, {"horse_id": "R1"},
                    {"horse_id": "R2"}, {"horse_id": "R3"}]}]}
            return {"results": []}

        def horse_results(self, hid: str, limit: int = 12) -> list[dict]:
            return {
                "R1": [{"date": "2026-06-15", "position": "1"}],   # won since -> franked
                "R2": [{"date": "2026-06-20", "position": "3"}],   # placed since -> franked
                "R3": [{"date": "2026-06-18", "position": "8"}],   # ran poorly -> not
            }.get(hid, [])

    history = (PastRun(date=date(2026, 6, 1), position=1, race_id="last1"),)
    f = frank_form(_C(), "W", history)
    assert f.rivals_checked == 3 and f.rivals_franked == 2 and f.is_franked is True
    assert "FRANKED" in f.note


def test_study_race_reports_franking_when_present() -> None:
    runners = [StudiedRunner("Gem", 1, 4.0, "won well",
                             frank_note="last race FRANKED: 3/5 rivals won/placed since")]
    s = study_race(runners)
    assert any("frank:" in line and "FRANKED" in line for line in s.lessons)
    assert not any("FRANK the winner" in g for g in s.gaps)   # finding replaces the gap
