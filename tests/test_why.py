"""THE WHY LEDGER (the master, 2026-09-03: "check results and see what won,
what lost, and understand why... store it and remember and recall it")."""
from __future__ import annotations

from datetime import date

from racing_edge.domain.models import RaceResult, RunnerResult
from racing_edge.school import why

DAY = "2026-09-03"


def _yrows():
    base = {"date": DAY, "race_id": "R1", "course": "Thirsk", "off_time": "3:00",
            "code": "F", "race_class": 4, "distance_f": 8.0, "field_size": 3,
            "race_quality": 2, "flags": "", "cautions": ""}
    return [
        {**base, "horse_id": "A", "horse": "Alpha", "mkt_rank": 1, "price": 2.5,
         "score": 3, "aligned": "finisher|course winner"},
        {**base, "horse_id": "B", "horse": "Bravo", "mkt_rank": 2, "price": 4.0,
         "score": 1, "aligned": "well in"},
        {**base, "horse_id": "C", "horse": "Charlie", "mkt_rank": 3, "price": 8.0,
         "score": 0, "aligned": "", "flags": "novice in disguise"},
        {**base, "race_id": "R2", "off_time": "3:30", "horse_id": "D", "horse": "Delta",
         "mkt_rank": 1, "price": 3.0, "score": 2, "aligned": "finisher"},
    ]


def _results():
    return [
        RaceResult(race_id="R1", date=date(2026, 9, 3), runners=(
            RunnerResult(horse_id="B", position=1, sp_dec=4.5, horse="Bravo",
                         comment="led throughout, kept on well"),
            RunnerResult(horse_id="C", position=2, sp_dec=9.0, horse="Charlie",
                         comment="stayed on"),
            RunnerResult(horse_id="A", position=3, sp_dec=2.4, horse="Alpha",
                         comment="held up, no extra final furlong"),
        )),
        # R2 has no result yet — it must be left out, not crash
    ]


def test_build_prompt_carries_the_morning_read_and_the_result_for_each_resulted_race():
    prompt, ids = why.build_prompt(DAY, _yrows(), _results())
    assert ids == ["R1"]
    assert "RACE R1: Thirsk 3:00" in prompt
    assert "Alpha — mkt 1 @2.5, score 3, for: finisher, course winner" in prompt
    assert "1. Bravo SP 4.5 — 'led throughout, kept on well'" in prompt
    assert "OUR TOP READ" not in prompt          # Alpha finished 3rd — in the first four


def test_our_top_read_is_named_when_it_finished_outside_the_first_four():
    res = [RaceResult(race_id="R1", date=date(2026, 9, 3), runners=(
        RunnerResult(horse_id="B", position=1, sp_dec=4.5, horse="Bravo", comment="led"),
        RunnerResult(horse_id="C", position=2, sp_dec=9.0, horse="Charlie", comment=""),
        RunnerResult(horse_id="X", position=3, sp_dec=9.0, horse="Xray", comment=""),
        RunnerResult(horse_id="Y", position=4, sp_dec=9.0, horse="Yank", comment=""),
        RunnerResult(horse_id="A", position=5, sp_dec=2.4, horse="Alpha", comment="weakened"),
    ))]
    prompt, _ = why.build_prompt(DAY, _yrows(), res)
    assert "OUR TOP READ Alpha finished 5 SP 2.4 — 'weakened'" in prompt


def test_parse_takes_the_json_and_nothing_else():
    text = ('Here you go:\n{"races": [{"race_id": "R1", "winner": "Bravo", '
            '"why_won": "led throughout in a race with no other pace", '
            '"told_by": "pace map / run-style front", "in_morning_read": "no", '
            '"our_top": "Alpha", "our_top_finished": "3rd", '
            '"why_lost": "held up, no pace to close into", "lesson": "no pace = front runner"}]}')
    rows = why.parse(text)
    assert len(rows) == 1 and rows[0]["winner"] == "Bravo"
    assert rows[0]["in_morning_read"] == "no"
    assert why.parse("nothing here") == []
    assert why.parse('{"races": [{"no_id": 1}]}') == []


def test_bank_load_and_recall_by_shape(tmp_path):
    rows = why.parse('{"races": [{"race_id": "R1", "winner": "Bravo", "why_won": "led all the way", '
                     '"told_by": "run-style", "in_morning_read": "no", "our_top": "Alpha", '
                     '"our_top_finished": "3rd", "why_lost": "no pace", "lesson": "front runner"}]}')
    p = why.bank(DAY, rows, _yrows(), _results(), tmp_path)
    assert p.exists()
    got = why.load(tmp_path)
    assert len(got) == 1
    g = got[0]
    assert g["course"] == "Thirsk" and g["code"] == "F" and g["race_class"] == "4"
    assert g["winner"] == "Bravo" and g["winner_mkt_rank"] == "2" and g["winner_sp"] == "4.5"
    # the same shape recalls it; a different course, code and trip does not
    lines = why.recall("Thirsk", "F", 4, 8.0, root=tmp_path)
    assert len(lines) == 1
    assert "Bravo (mkt 2 @4.5) won — led all the way" in lines[0]
    assert "the morning read had it: no" in lines[0]
    assert "our top Alpha finished 3rd: no pace" in lines[0]
    assert "lesson: front runner" in lines[0]
    assert why.recall("Chepstow", "H", 4, 20.0, root=tmp_path) == []
    # same code, class and trip on another course still scores enough to recall
    assert len(why.recall("Ripon", "F", 5, 7.0, root=tmp_path)) == 1
    # banking again overwrites, never doubles
    why.bank(DAY, rows, _yrows(), _results(), tmp_path)
    assert len(why.load(tmp_path)) == 1


def test_digest_counts_what_the_morning_read_had():
    rows = [{"in_morning_read": "yes", "told_by": "finisher", "lesson": ""},
            {"in_morning_read": "no", "told_by": "run-style", "lesson": "pace first"},
            {"in_morning_read": "no", "told_by": "finisher", "lesson": ""}]
    d = why.digest(rows)
    assert "3 races reverse-engineered" in d[0] and "yes 1 · no 2 · owed 0" in d[0]
    assert "finisher (2)" in d[1]
    assert any("lesson: pace first" in x for x in d)


def test_the_why_ledger_has_its_own_model_row_and_budget():
    """The master, 2026-09-03: "cost effective, using the right models" — the
    nightly why is its own task: sonnet, its own ceiling, never sharing the
    self-study's pool."""
    from racing_edge.ai import reason
    assert reason.resolve_model("why") == "claude-sonnet-5"
    assert reason._TASK_BUDGETS["why"] == 30_000
    import inspect
    assert 'get_reasoner("why"' in inspect.getsource(why.main)

