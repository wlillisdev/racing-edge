"""THE SIGNPOSTS (the master, 2026-09-05: "here is some information we can look
at, it is my AI back in the day... implement all of these, they are another
dot"). Dots for the reader and a column for the record — never a score."""
from __future__ import annotations

from datetime import date

from racing_edge.data.evidence import combo_from_analysis
from racing_edge.domain.models import Odds, PastRun, Race, Runner
from racing_edge.school import signposts as sp
from racing_edge.school.mine import Runner as CorpusRunner
from racing_edge.selection.case import RunnerEvidence

DAY = date(2026, 9, 5)


def _run(d, pos, course="Thirsk"):
    return PastRun(date=d, position=pos, course=course, race_type="Flat")


# 1. the combination ------------------------------------------------------- #
def test_combo_from_the_yards_jockey_table_and_the_line_it_makes():
    rows = [{"jockey_id": "j1", "rides": "8", "1st": "5"},
            {"jockey_id": "j2", "runners": "3", "wins": "1"}]
    assert combo_from_analysis(rows, "j1") == (8, 5)
    assert combo_from_analysis(rows, "j2") == (3, 1)
    assert combo_from_analysis(rows, "j9") == (0, 0)
    assert combo_from_analysis(rows, "") == (0, 0)
    assert sp.combo_line(8, 5) == ("jockey/trainer combo 5-8 63%", "combo 33%+")
    assert sp.combo_line(10, 2)[1] == "combo 20%+"
    assert sp.combo_line(10, 0)[1] == "combo cold"
    assert sp.combo_line(3, 3) is None                    # under the bar: silence


# 2. rating clear (the Postmark) -------------------------------------------- #
def test_rating_clear_reads_the_cards_own_rating_in_a_handicap_only():
    rs = (Runner(horse_id="A", horse="A", performance_rating=90, rpr=70),
          Runner(horse_id="B", horse="B", performance_rating=86),
          Runner(horse_id="C", horse="C", rpr=80))          # falls back to rpr
    hcap = Race(race_id="r", course="Thirsk", off_time="3:15", date=DAY,
                race_type="Flat", is_handicap=True, runners=rs)
    assert sp.rating_clear(hcap) == ("A", 4)
    close = Race(race_id="r", course="Thirsk", off_time="3:15", date=DAY,
                 race_type="Flat", is_handicap=True,
                 runners=(rs[0], Runner(horse_id="D", horse="D", performance_rating=88)))
    assert sp.rating_clear(close) is None                 # 2lb is not clear
    non = Race(race_id="r", course="Thirsk", off_time="3:15", date=DAY,
               race_type="Flat", is_handicap=False, runners=rs)
    assert sp.rating_clear(non) is None


# 3 & 5. the yard at the course by type, the cold yard — from the corpus ---- #
def _corpus():
    rows = []
    for i in range(6):                                    # yard t1 at Thirsk flat: 6 runs, 2 wins
        rows.append(["2026-03-%02d" % (i + 1), f"R{i}", "Thirsk", "G", "F", "5", "8.0",
                     f"H{i}", "4.0", "1" if i < 2 else "5", "0", "j1", "t1"])
    rows.append(["2026-08-30", "R9", "Ripon", "G", "F", "5", "6.0",
                 "H9", "4.0", "3", "2", "j1", "t1"])      # a run since the last win
    rows.append(["2026-09-01", "R10", "Thirsk", "G", "F", "5", "8.0",
                 "H10", "4.0", "1", "0", "j2", "t2"])     # yard t2 won this week
    return [[CorpusRunner(r)] for r in rows]


def test_yard_tables_course_type_and_cold_yard():
    tables, cold = sp.yard_tables(_corpus())
    assert tables[("t1", "thirsk", "F")] == [6, 2]
    line, key = sp.course_type_line(tables, "t1", "Thirsk", "Flat")
    assert line == "yard at this course in flat: 2-6 33% (corpus)" and key == "yard here/flat 25%+"
    assert sp.course_type_line(tables, "t1", "Ripon", "Flat") is None   # 1 run: silence
    assert sp.course_type_line(tables, "t9", "Thirsk", "Flat") is None
    # t1's last winner was 2026-03-02 — cold by September; t2 won this week
    assert cold["t1"] == ("2026-03-02", 5)
    line, key = sp.cold_yard_line(cold, "t1", DAY)
    assert key == "cold yard" and "2026-03-02" in line and "5 runs since" in line
    assert sp.cold_yard_line(cold, "t2", DAY) is None
    assert sp.cold_yard_line(cold, "t9", DAY) is None


# 4. the same race last year ------------------------------------------------ #
def _last_year_raw():
    return {"results": [
        {"date": "2025-09-06", "course": "Thirsk", "dist_f": "6f", "class": "Class 4",
         "race_name": "Acme Sponsor Handicap (Div 1)",
         "runners": [{"horse_id": "X", "horse": "Xray", "position": "1", "sp_dec": "5.0", "sp": "4/1",
                      "or": "80", "weight": "9-2", "weight_lbs": "128", "trainer": "A Balding",
                      "jockey": "D Probert", "draw": "4"},
                     {"horse_id": "A", "horse": "Alpha", "position": "3", "sp_dec": "9.0", "or": "77",
                      "weight": "9-9", "weight_lbs": "135"},
                     {"horse_id": "Y", "horse": "Yank", "position": "PU", "sp_dec": "21.0", "or": "70",
                      "weight": "8-11", "weight_lbs": "123"}]},
        {"date": "2025-09-06", "course": "Thirsk", "dist_f": "8f", "class": "Class 4",
         "race_name": "Acme Sponsor Handicap (Div 2)", "runners": []},
        {"date": "2025-09-06", "course": "Ripon", "dist_f": "6f", "class": "Class 4",
         "race_name": "Acme Sponsor Handicap", "runners": []},
    ]}


def test_same_race_last_year_matches_course_trip_and_name():
    assert sp.last_year_window(DAY) == ("2025-09-05", "2025-09-12")   # start clamped to the door
    race = Race(race_id="r", course="Thirsk", off_time="3:15", date=DAY, race_type="Flat",
                is_handicap=True, race_class=4, distance_f=6.0,
                race_name="Other Sponsor Handicap (Div 1)", runners=())
    got = sp.same_race_last_year(_last_year_raw(), race)
    assert got is not None and got["winner"] == "Xray" and got["winner_sp"] == "5.0"
    assert got["runners"]["A"] == (3, 3, "9.0", "77")
    assert got["runners"]["Y"][0] is None
    other = Race(race_id="r", course="Thirsk", off_time="3:15", date=DAY, race_type="Flat",
                 race_class=2, distance_f=12.0, race_name="Something Else Stakes", runners=())
    assert sp.same_race_last_year(_last_year_raw(), other) is None
    assert sp.same_race_last_year(None, race) is None


# 6. fresh ------------------------------------------------------------------- #
def test_fresh_start_line_says_whether_it_has_won_fresh_before():
    won_fresh = (_run(date(2025, 3, 1), 4), _run(date(2025, 10, 1), 1),   # 214 days, WON
                 _run(date(2025, 11, 1), 2))
    line, key = sp.fresh_start_line(won_fresh, date(2026, 9, 5))
    assert key == "won fresh before" and "2025-10-01 after 214 days" in line
    never = (_run(date(2025, 3, 1), 4), _run(date(2025, 10, 1), 3))
    assert sp.fresh_start_line(never, date(2026, 9, 5))[1] == "fresh, never won fresh"
    assert sp.fresh_start_line((_run(date(2026, 8, 1), 1),), DAY) is None   # not fresh
    assert sp.fresh_start_line((), DAY) is None


# the assembly ---------------------------------------------------------------- #
def test_build_gives_each_runner_its_dots_and_the_race_its_last_year_line():
    rA = Runner(horse_id="A", horse="Alpha", trainer_id="t1", jockey_id="j1",
                performance_rating=90, odds=Odds(consensus=3.0))
    rB = Runner(horse_id="B", horse="Beta", trainer_id="t2", jockey_id="j2",
                performance_rating=84, odds=Odds(consensus=5.0))
    race = Race(race_id="r", course="Thirsk", off_time="3:15", date=DAY, race_type="Flat",
                is_handicap=True, race_class=4, distance_f=6.0,
                race_name="Other Sponsor Handicap (Div 1)", runners=(rA, rB))
    ev = {"r": [RunnerEvidence(runner=rA, combo_rides=8, combo_wins=5,
                               history=(_run(date(2025, 3, 1), 4), _run(date(2025, 10, 1), 1))),
                RunnerEvidence(runner=rB, combo_rides=2, combo_wins=0,
                               history=(_run(date(2026, 8, 20), 2),))]}
    out = sp.build(DAY, [race], ev, corpus_races=_corpus(), last_year_raw=_last_year_raw())
    a = out["A"]
    assert a["keys"] == ["combo 33%+", "rating clear", "yard here/flat 25%+", "cold yard",
                         "ran here before — placed", "won fresh before"]
    assert "rating clear in the handicap by 6lb (the Postmark)" in a["lines"]
    assert "ran in this race (2025-09-06): 3 of 3 at SP 9.0 off 77" in a["lines"]
    assert "B" not in out                                  # nothing to say: no entry
    assert out["race:r"]["lines"][0].startswith(
        "THIS RACE, PAST WINNERS (1 runnings): 2025 Xray 9-2 SP 5.00 off 80 (A Balding/D Probert, dr 4)")
    assert "THE RACE'S DNA (#29): winners carried 9-2 to 9-2 · top weight won 0/1 · favourite won 0/1" \
        in out["race:r"]["lines"][1]
    # every source missing: no dot, no crash
    assert sp.build(DAY, [race], {}, corpus_races=None, last_year_raw=None) == {
        "A": {"lines": ["rating clear in the handicap by 6lb (the Postmark)"],
              "keys": ["rating clear"]}}


def test_the_past_winners_roll_writes_the_races_dna_and_whether_today_fits_it():
    """The master, 2026-09-05, after Ascot 2:10 (Archers Bay 9-9 top weight,
    3rd; nine runnings, not one winner above 9-6): 'i have said this before
    but past winners give key clues to find a potential winner'. Law #29."""
    def year(y, winner, lbs, sp, trainer, top_lbs):
        return {"results": [{"date": f"{y}-09-06", "course": "Ascot", "dist_f": "12f",
                             "class": "Class 2", "race_name": "Sponsor Handicap (Heritage Handicap)",
                             "runners": [{"horse_id": f"W{y}", "horse": winner, "position": "1",
                                          "sp_dec": "5.0", "sp": sp, "or": "90", "weight_lbs": str(lbs),
                                          "weight": f"{lbs // 14}-{lbs % 14}", "trainer": trainer,
                                          "jockey": "J", "draw": "3"},
                                         {"horse_id": f"T{y}", "horse": "Top", "position": "5",
                                          "sp_dec": "8.0", "or": "99", "weight_lbs": str(top_lbs)}]}]}
    raws = [year(2025, "Tenability", 124, "85/40", "W Haggas", 135),
            year(2024, "The Reverend", 124, "4/1", "W Haggas", 135),
            year(2023, "Alsakib", 120, "5/1", "A Balding", 135),
            year(2022, "La Yakel", 117, "100/30F", "W Haggas", 133)]
    # the date door serves 12 months and no more (live, 2026-09-05: 422 on a
    # start 372 days back) — the window's start is clamped, older years dropped
    assert sp.last_year_window(date(2026, 9, 5)) == ("2025-09-05", "2025-09-12")
    assert sp.past_windows(date(2026, 9, 5), 3) == [("2025-09-05", "2025-09-12")]
    race = Race(race_id="r", course="Ascot", off_time="2:10", date=DAY, race_type="Flat",
                is_handicap=True, race_class=2, distance_f=12.0,
                race_name="Other Sponsor Handicap (Heritage Handicap)",
                runners=(Runner(horse_id="A", horse="Archers Bay", weight_lbs=135),
                         Runner(horse_id="B", horse="Turty Tree", weight_lbs=126)))
    roll = sp.past_winners_roll(raws, race)
    assert [m["winner"] for m in roll] == ["Tenability", "The Reverend", "Alsakib", "La Yakel"]
    assert roll[0]["top_weight_won"] is False and roll[3]["winner_fav"] is True
    dna = sp.race_dna(roll)
    assert dna[0].startswith("THIS RACE, PAST WINNERS (4 runnings): 2025 Tenability 8-12 SP 5.00 off 90 (W Haggas/J, dr 3)")
    assert dna[1] == ("THE RACE'S DNA (#29): winners carried 8-5 to 8-12 · top weight won 0/4 · "
                      "favourite won 1/4 · yards that keep winning it: W Haggas 3")
    out = sp.build(DAY, [race], {}, last_year_raw=raws)
    assert out["A"] == {"lines": ["carries 9-9: above every winner of this race in 4 runnings (8-5 to 8-12)"],
                        "keys": ["above DNA weight"]}
    assert out["B"]["keys"] == ["above DNA weight"]      # 9-0 is above 8-12 too — the line, no verdict
    assert out["race:r"]["lines"] == dna
    # a single dict still works (the one-year form of the morning)
    assert sp.build(DAY, [race], {}, last_year_raw=raws[0])["race:r"]["lines"][0].startswith(
        "THIS RACE, PAST WINNERS (1 runnings)")


class _ChainClient:
    """The two doors the chain uses: a horse's whole career (no date limit)
    and a race by id (no date limit) — recorded so the test counts calls."""
    def __init__(self):
        self.history_calls, self.id_calls = [], []
        # Paddy ran in the 2024 and 2023 runnings; Stress in 2024 only
        self.histories = {
            "PADDY": [{"race_id": "R2024", "date": "2024-09-07", "course": "Ascot", "dist_f": "12f",
                       "race_name": "Old Sponsor Handicap (Heritage Handicap)", "class": "Class 2",
                       "runners": [{"horse_id": "PADDY", "position": "4"}]},
                      {"race_id": "R2023", "date": "2023-09-09", "course": "Ascot", "dist_f": "12f",
                       "race_name": "Older Sponsor Handicap (Heritage Handicap)", "class": "Class 2",
                       "runners": [{"horse_id": "PADDY", "position": "1"}]},
                      {"race_id": "RX", "date": "2024-06-01", "course": "York", "dist_f": "12f",
                       "race_name": "Some Other Handicap", "runners": [{"horse_id": "PADDY", "position": "2"}]}],
            "STRESS": [{"race_id": "R2024", "date": "2024-09-07", "course": "Ascot", "dist_f": "12f",
                        "race_name": "Old Sponsor Handicap (Heritage Handicap)", "class": "Class 2",
                        "runners": [{"horse_id": "STRESS", "position": "2"}]}],
        }
        self.results = {
            "R2024": {"race_id": "R2024", "date": "2024-09-07", "race_name": "Old Sponsor Handicap (Heritage Handicap)",
                      "runners": [{"horse_id": "W24", "horse": "The Reverend", "position": "1", "sp_dec": "5.0",
                                   "sp": "4/1", "or": "95", "weight": "8-12", "weight_lbs": "124",
                                   "trainer": "W Haggas", "jockey": "D Probert", "draw": "3"},
                                  {"horse_id": "STRESS", "horse": "Stress", "position": "2", "weight_lbs": "135",
                                   "sp_dec": "9.0", "or": "99"},
                                  {"horse_id": "PADDY", "horse": "Paddy", "position": "4", "weight_lbs": "130"}]},
            "R2023": {"race_id": "R2023", "date": "2023-09-09", "race_name": "Older Sponsor Handicap (Heritage Handicap)",
                      "runners": [{"horse_id": "PADDY", "horse": "Paddy", "position": "1", "sp_dec": "6.0",
                                   "sp": "5/1", "or": "90", "weight": "8-8", "weight_lbs": "120",
                                   "trainer": "A Balding", "jockey": "D Probert", "draw": "3"},
                                  {"horse_id": "Z", "horse": "Zed", "position": "2", "weight_lbs": "133"}]},
        }

    def horse_results(self, horse_id, limit=12):
        self.history_calls.append(horse_id)
        return self.histories.get(horse_id, [])

    def result_by_id(self, race_id):
        self.id_calls.append(race_id)
        return self.results.get(race_id)


def test_earlier_runnings_are_found_through_the_horses_and_fetched_by_id():
    """The master, 2026-09-05: 'find a workaround to find past winners, not
    just the easy way'. The date door stops at 12 months; the horses do not."""
    from racing_edge.data.normalise import past_runs_from_raw
    client = _ChainClient()
    race = Race(race_id="r", course="Ascot", off_time="2:10", date=DAY, race_type="Flat",
                is_handicap=True, race_class=2, distance_f=12.0,
                race_name="New Sponsor Handicap (Heritage Handicap)",
                runners=(Runner(horse_id="STRESS", horse="Stress", weight_lbs=136),
                         Runner(horse_id="NEWBOY", horse="Newboy", weight_lbs=126)))
    # last year's running, as the date door gave it (2025) — Paddy and Stress ran in it
    last = {"results": [{"race_id": "R2025", "date": "2025-09-06", "course": "Ascot", "dist_f": "12f",
                         "class": "Class 2", "race_name": "Sponsor Handicap (Heritage Handicap)",
                         "runners": [{"horse_id": "W25", "horse": "Tenability", "position": "1", "sp_dec": "3.1",
                                      "sp": "85/40F", "or": "85", "weight": "8-12", "weight_lbs": "124",
                                      "trainer": "W Haggas", "jockey": "C Fallon", "draw": "7"},
                                     {"horse_id": "PADDY", "horse": "Paddy", "position": "5", "weight_lbs": "132"},
                                     {"horse_id": "STRESS", "horse": "Stress", "position": "3", "weight_lbs": "135",
                                      "sp_dec": "12.0", "or": "102"}]}]}
    sps = sp.build(DAY, [race], {}, last_year_raw=last)
    assert [m["winner"] for m in sps["race:r"]["roll"]] == ["Tenability"]
    # today's runners' own histories (already in hand) index 2024; last year's
    # field (Paddy, fetched) indexes 2023 as well; each new running fetched ONCE by id
    hists = {"STRESS": past_runs_from_raw(client.histories["STRESS"], "STRESS"), "NEWBOY": ()}
    roll = sp.deepen(client, race, hists, sps, DAY)
    assert [m["winner"] for m in roll] == ["Tenability", "The Reverend", "Paddy"]
    assert client.history_calls == ["W25", "PADDY"] or sorted(client.history_calls) == ["PADDY", "W25"]
    assert sorted(client.id_calls) == ["R2023", "R2024"]
    dna = sps["race:r"]["lines"]
    assert dna[0].startswith("THIS RACE, PAST WINNERS (3 runnings): 2025 Tenability 8-12")
    assert "winners carried 8-8 to 8-12 · top weight won 0/3 · favourite won 1/3" in dna[1]
    assert "yards that keep winning it: W Haggas 2" in dna[1]
    s = sps["STRESS"]
    assert s["lines"][0] == "ran in this race (2025-09-06): 3 of 3 at SP 12.0 off 102"
    assert s["lines"][1] == "ran in this race (2024-09-07): 2 of 3 at SP 9.0 off 99"
    assert s["keys"] == ["ran here before — placed", "ran here before — placed", "above DNA weight"]
    assert sps["NEWBOY"]["keys"] == ["above DNA weight"]     # 9-0 v a band topping at 8-12
    # a dead id door: the roll is what the date door gave, nothing raised
    class _Dead(_ChainClient):
        def result_by_id(self, race_id):
            raise RuntimeError("door down")
    sps2 = sp.build(DAY, [race], {}, last_year_raw=last)
    assert [m["winner"] for m in sp.deepen(_Dead(), race, hists, sps2, DAY)] == ["Tenability"]


def test_the_yardstick_carries_the_signposts_column_and_grades_it():
    from racing_edge.pipeline.nap import NapPick
    from racing_edge.school import yardstick as ys
    from racing_edge.selection.conviction import Conviction
    rA = Runner(horse_id="A", horse="Alpha", odds=Odds(consensus=3.0))
    race = Race(race_id="r1", course="Thirsk", off_time="3:15", date=DAY,
                race_type="Flat", is_handicap=True, race_class=4, runners=(rA,))
    p = NapPick(race=race, runner=rA, price=3.0, race_quality=2,
                conviction=Conviction(aligned=(), flags=(), mark_known=True))
    rows = ys.rows_from_field(DAY, [p], {"A": {"lines": ["x", "y"],
                                              "keys": ["combo 33%+", "cold yard", "combo 33%+"]}})
    assert ys.FIELDS[-1] == "signposts"
    assert rows[0]["signposts"] == "combo 33%+|cold yard"
    assert ys.rows_from_field(DAY, [p])[0]["signposts"] == ""
    board = ys.scoreboard([{**ys._typed({**rows[0], "won": "1", "sp_dec": "3.0"})}])
    assert "## SIGNPOSTS" in board and "| combo 33%+ | 1 | 1 |" in board


def test_the_preread_prints_the_signposts_block_and_last_years_line():
    from racing_edge.report.restudy import render_preread
    race = Race(race_id="r", course="Thirsk", off_time="3:15", date=DAY, race_type="Flat",
                is_handicap=True, runners=(Runner(horse_id="A", horse="Alpha",
                                                  odds=Odds(consensus=3.0)),))
    extra = {"A": {"lines": ["jockey/trainer combo 5-8 63%", "fresh (300 days) — never won"],
                   "keys": []},
             "race:r": {"lines": ["THIS RACE LAST YEAR (2025-09-06): won by Xray at SP 5.0 off 80"],
                        "keys": []}}
    out = render_preread(race, {"A": ()}, extra=extra)
    assert "  THIS RACE LAST YEAR (2025-09-06): won by Xray" in out
    assert "SIGNPOSTS: jockey/trainer combo 5-8 63% | fresh (300 days) — never won" in out
    assert "SIGNPOSTS" not in render_preread(race, {"A": ()})
