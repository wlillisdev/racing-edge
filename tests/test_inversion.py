"""THE INVERSION (the master, 2026-09-05, after five of six picks lost to the
horse with the better class line: "I picked a story over the best form line...
yes do inversion, we need to learn and improve, we keep getting it wrong").
Rule One — THE BEST HORSE WINS — becomes the FIRST term of the rank key: the
best proven form line at the highest class; the jigsaw crosses off and breaks
ties. These tests fail with the old key put back."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace as NS

from racing_edge.data.normalise import past_runs_from_raw, race_from_raw
from racing_edge.domain.models import PastRun
from racing_edge.pipeline.nap import BETTING_BAR, _rank_key, _rank_key_legacy
from racing_edge.selection import conviction as cv


# --------------------------------------------------------------------------- #
# the ladder
# --------------------------------------------------------------------------- #
def test_the_class_ladder_puts_group_above_listed_above_class_one():
    assert cv.class_level(1, "Group 1") == 1
    assert cv.class_level(1, "Group 2") == 2
    assert cv.class_level(1, "Group 3") == 3
    assert cv.class_level(1, "Listed") == 4
    assert cv.class_level(1, "") == 5                       # a non-pattern Class 1
    assert cv.class_level(2, "") == 6
    assert cv.class_level(7, "") == 11
    assert cv.class_level(None, "") == cv.NO_CLASS_LINE
    assert cv.class_level("Class 4", "") == cv.NO_CLASS_LINE  # a string is not a rung


def test_pattern_is_parsed_from_the_feed_or_dug_out_of_the_race_name():
    """The feed's `pattern` key (verified live 2026-09-05) or the race name —
    without it a Group 1 winner and a Listed winner are both 'Class 1'."""
    race = race_from_raw({"race_id": "r", "course": "Haydock", "off_time": "3:40",
                          "race_name": "Betfair Sprint Cup Stakes (Group 1)", "class": "Class 1",
                          "type": "Flat", "runners": []}, date(2026, 9, 5))
    assert race.pattern == "Group 1" and race.race_class == 1
    race2 = race_from_raw({"race_id": "r", "course": "Kempton", "off_time": "2:50",
                           "race_name": "September Stakes", "pattern": "Group 3",
                           "class": "Class 1", "type": "Flat", "runners": []}, date(2026, 9, 5))
    assert race2.pattern == "Group 3"
    runs = past_runs_from_raw([
        {"date": "2025-08-20", "course": "York", "type": "Flat", "class": "Class 1",
         "race_name": "Sky Bet Great Voltigeur Stakes (Group 2)",
         "runners": [{"horse_id": "A", "position": "1"}]},
        {"date": "2025-06-01", "course": "Salisbury", "type": "Flat", "class": "Class 1",
         "race_name": "EBF Cathedral Stakes (Listed)", "pattern": "",
         "runners": [{"horse_id": "A", "position": "3"}]},
        {"date": "2025-05-01", "course": "Thirsk", "type": "Flat", "class": "Class 4",
         "race_name": "Some Handicap", "runners": [{"horse_id": "A", "position": "1"}]},
    ], "A")
    assert [r.pattern for r in runs] == ["Group 2", "Listed", ""]
    assert [r.race_class for r in runs] == [1, 1, 4]


# --------------------------------------------------------------------------- #
# the best form line
# --------------------------------------------------------------------------- #
def _run(d, pos, cls=4, pattern=""):
    return PastRun(date=d, position=pos, race_class=cls, race_type="Flat", pattern=pattern)


def test_best_form_line_is_the_highest_rung_won_or_placed_inside_the_stale_window():
    # a Listed 3rd outranks a Cl3 win (Rocket Boy's line v a maiden win); a win
    # beats a place on the same rung; nothing outside the first three counts
    hist = (_run(date(2026, 8, 14), 3, 1, "Listed"), _run(date(2026, 7, 1), 1, 3),
            _run(date(2026, 6, 1), 4, 1, "Group 1"))
    assert cv.best_form_line(hist) == (4, False, "3rd Listed (2026-08-14)")
    assert cv.best_form_line((_run(date(2026, 8, 1), 1, 1, "Group 2"),
                              _run(date(2026, 7, 1), 2, 1, "Group 2"))) == (2, True, "won Group 2 (2026-08-01)")
    assert cv.best_form_line((_run(date(2026, 8, 1), 2, 1, "Group 2"),
                              _run(date(2026, 7, 1), 1, 1, "Group 2"))) == (2, True, "won Group 2 (2026-07-01)")
    # Oolong's line: a Cl2 3rd off 87 outranks Proposal's Cl3 win
    assert cv.best_form_line((_run(date(2026, 8, 20), 3, 2),))[0] < cv.best_form_line((_run(date(2026, 8, 1), 1, 3),))[0]
    # the STALE window: a Group win eleven runs back no longer counts
    old = tuple([_run(date(2026, 8, 1) , 5, 4)] * 10 + [_run(date(2025, 1, 1), 1, 1, "Group 1")])
    assert cv.best_form_line(old) == (cv.NO_CLASS_LINE, False, "")
    assert cv.best_form_line(()) == (cv.NO_CLASS_LINE, False, "")
    assert cv.best_form_line((_run(date(2026, 8, 1), None, 4),)) == (cv.NO_CLASS_LINE, False, "")


def test_conviction_carries_the_best_form_line():
    from racing_edge.domain.models import Odds, Race, Runner
    race = Race(race_id="r", course="Kempton", off_time="2:50", date=date(2026, 9, 5),
                race_type="Flat", race_class=1, pattern="Group 3",
                runners=(Runner(horse_id="A", horse="Pride", odds=Odds(consensus=6.5)),))
    hist = (PastRun(date=date(2026, 7, 26), position=2, race_class=1, race_type="Flat",
                    pattern="Group 2", official_rating=114),
            PastRun(date=date(2025, 8, 20), position=1, race_class=1, race_type="Flat",
                    pattern="Group 2", official_rating=111))
    c = cv.conviction(race.runners[0], race, hist, market_rank=3, field_size=5)
    assert (c.best_class_level, c.best_class_won) == (2, True)
    assert c.best_class_line == "won Group 2 (2025-08-20)"


# --------------------------------------------------------------------------- #
# the key: class first, then the jigsaw
# --------------------------------------------------------------------------- #
def _pick(level, won, score, rq=3, cls=4, price=3.0, confident=False, mark=True):
    return NS(race_quality=rq, price=price, race=NS(race_class=cls),
              conviction=NS(confident=confident, mark_known=mark, score=score,
                            aligned=tuple("x" * score), best_class_level=level,
                            best_class_won=won, best_class_line="l"))


def test_the_rank_key_puts_the_best_form_line_before_the_jigsaw():
    """Kempton 2:50 in the key: a Group 2 winner (score 1) beats a Listed winner
    with six aligned lenses. Haydock 3:40: a Group 1 winner beats a Group 2
    winner. Thirsk 3:15: a Cl2 3rd beats a Cl3 winner that was 'confident'."""
    g2_win, listed_win = _pick(2, True, 1), _pick(4, True, 6, confident=True)
    assert _rank_key(g2_win) > _rank_key(listed_win)
    assert _rank_key_legacy(listed_win) > _rank_key_legacy(g2_win)     # the old key disagrees
    assert _rank_key(_pick(1, True, 2)) > _rank_key(_pick(2, True, 5))
    assert _rank_key(_pick(6, False, 2)) > _rank_key(_pick(7, True, 4, confident=True))
    # a win beats a place on the same rung; then the jigsaw breaks the tie
    assert _rank_key(_pick(4, True, 2)) > _rank_key(_pick(4, False, 5))
    assert _rank_key(_pick(4, True, 5)) > _rank_key(_pick(4, True, 2))
    # no line at all ranks below any line
    assert _rank_key(_pick(11, False, 1)) > _rank_key(_pick(cv.NO_CLASS_LINE, False, 6, confident=True))


def test_the_bar_still_outranks_the_class_line():
    """The race must clear the betting bar first (his ruling of 2026-09-02) —
    a Group 1 winner in duty water still loses to a Cl5 placer above the bar."""
    assert BETTING_BAR == 2
    assert _rank_key(_pick(9, False, 1, rq=2)) > _rank_key(_pick(1, True, 6, rq=1))
    # below the bar the race still outranks the horse, then class, then the jigsaw
    assert _rank_key(_pick(9, False, 1, rq=1)) > _rank_key(_pick(1, True, 6, rq=0))
    assert _rank_key(_pick(1, True, 1, rq=1)) > _rank_key(_pick(9, False, 6, rq=1))


def test_stubs_without_the_line_still_rank_by_the_jigsaw():
    """Older tests build convictions without the line — they must not crash and
    must still fall through to the jigsaw."""
    def old(score):
        return NS(race_quality=3, price=3.0, race=NS(race_class=4),
                  conviction=NS(confident=False, mark_known=True, score=score,
                                aligned=tuple("x" * score)))
    assert _rank_key(old(4)) > _rank_key(old(2))


def test_the_race_picker_scores_the_class_the_race_holds():
    """The master, 2026-09-05: the fingerprint scored every ITV race 0-1 and
    sent the nap to a fillies' handicap; 'well maybe the engine is wrong?...
    I believe in what you say'. A Group/Listed race scores the class point
    twice; Class 1-2 scores it once, the same as Class 3-4; nothing else moves."""
    from racing_edge.pipeline.nap import race_quality_score as rq
    base = dict(is_handicap=False, concentration=0.5, race_type="Flat", field_size=8,
                n_race_flags=0)
    # the Sprint Cup: Group 1, not a handicap, open market — at the bar now, 0 before
    assert rq(**base, race_class=1, pattern="Group 1") == 2
    assert rq(**base, race_class=1) == 1                      # a non-pattern Class 1
    assert rq(**base, race_class=2) == rq(**base, race_class=3) == 1
    assert rq(**base, race_class=6) == 0
    # Kempton 2:50: Group 3, concentrated, all-weather → 2 + 1 - 1 = 2 (was 0)
    assert rq(**{**base, "concentration": 0.93}, race_class=1, pattern="Group 3", is_aw=True) == 2
    # Ascot 2:10: a Class 2 heritage handicap → handicap + class = 2 (was 1)
    assert rq(**{**base, "is_handicap": True}, race_class=2) == 2
    # the fingerprint race is unchanged: Thirsk 3:15 → 3
    assert rq(**{**base, "is_handicap": True, "concentration": 0.79}, race_class=3) == 3
    # the pattern point never stacks with the class point
    assert rq(**base, race_class=1, pattern="Listed") == 2


def test_the_yardstick_splits_its_race_table_by_type():
    from racing_edge.school import yardstick as ys
    assert ys.race_type_band({"pattern": "Group 3", "race_class": 1, "is_handicap": 0}) == "pattern"
    assert ys.race_type_band({"pattern": "", "race_class": 2, "is_handicap": 1}) == "heritage"
    assert ys.race_type_band({"pattern": "", "race_class": 3, "is_handicap": 1}) == "fingerprint"
    assert ys.race_type_band({"pattern": "", "race_class": 3, "is_handicap": 0}) == "other"
    assert ys.race_type_band({"pattern": "", "race_class": "", "is_handicap": 1}) == "other"
    base = {"date": "2026-09-05", "version": "v2", "course": "K", "off_time": "2:50", "code": "F",
            "race_class": 1, "is_handicap": 0, "field_size": 5, "race_quality": 2, "horse": "h",
            "score": 1, "confident": 0, "mark_known": 1, "aligned": "", "flags": "", "cautions": "",
            "pos": "", "sp_dec": "", "signposts": "", "best_class": "", "class_level": 99}
    rows = [ys._typed({**base, "race_id": "r", "horse_id": "A", "mkt_rank": 1, "price": 1.73,
                       "won": "0", "pattern": "Group 3"}),
            ys._typed({**base, "race_id": "r", "horse_id": "B", "mkt_rank": 3, "price": 6.5,
                       "won": "1", "score": 2, "pattern": "Group 3"})]
    board = ys.scoreboard(rows)
    assert "## RACE TYPE" in board
    assert "| pattern | 1 | 0/1 (0.0%) | 1/1 (100.0%) | 1/1 (100.0%) |" in board
    assert "| fingerprint | 0 |" in board
    assert "pattern" in ys.FIELDS


def test_the_yardstick_banks_the_class_line_and_grades_it():
    from datetime import date as _d
    from racing_edge.domain.models import Odds, Race, Runner
    from racing_edge.pipeline.nap import NapPick
    from racing_edge.school import yardstick as ys
    rA = Runner(horse_id="A", horse="Alpha", odds=Odds(consensus=3.0))
    race = Race(race_id="r1", course="Thirsk", off_time="3:15", date=_d(2026, 9, 5),
                race_type="Flat", is_handicap=True, race_class=3, runners=(rA,))
    c = cv.Conviction(aligned=(), flags=(), mark_known=True, best_class_level=6,
                      best_class_won=False, best_class_line="3rd Cl2 (2026-08-20)")
    rows = ys.rows_from_field(_d(2026, 9, 5), [NapPick(race=race, runner=rA, price=3.0,
                                                        conviction=c, race_quality=2)])
    assert rows[0]["best_class"] == "line Cl1-2" and rows[0]["class_level"] == 6
    assert ys.class_bucket(1) == "line G1-G3" and ys.class_bucket(4) == "line Listed"
    assert ys.class_bucket(8) == "line Cl3-4" and ys.class_bucket(11) == "line Cl5-7"
    assert ys.class_bucket(99) == "no line" and ys.class_bucket("") == "no line"
    board = ys.scoreboard([ys._typed({**rows[0], "won": "1", "sp_dec": "3.0"})])
    assert "## THE CLASS LINE" in board and "| line Cl1-2 | 1 | 1 |" in board
