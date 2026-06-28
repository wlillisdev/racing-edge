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
