"""THE BACKWARD REPLAY — the adapter, and the line it must never cross.

A result document holds the card AND the answer sheet. These tests pin the
line between them: every pre-race field reaches the Race, every post-race
figure is stripped, and the answer sheet comes back separately.

The document below is the real shape, trimmed: York 3:50 Garrowby Stakes,
2026-09-06 (the race the duty lost), as the /results door served it.
"""
from datetime import date

from racing_edge.data.normalise import race_from_raw
from racing_edge.school.replay import (card_from_result, outcome_from_result,
                                       winner_of)

DOC = {
    "race_id": "rac_32296677400", "date": "2026-09-06", "region": "GB",
    "course": "York", "off": "3:50", "off_dt": "2026-09-06T15:50:00+01:00",
    "race_name": "Starman At Tally Ho Stud Garrowby Stakes (Listed Race)",
    "type": "Flat", "class": "Class 1", "pattern": "Listed",
    "dist": "6f", "dist_y": "1320", "dist_f": "6f", "going": "Good To Soft",
    "surface": "Turf",
    "runners": [
        {"horse_id": "hrs_1", "horse": "Extremely Zain (FR)", "sp": "9/2",
         "sp_dec": "5.50", "position": "1", "draw": "9", "btn": "0",
         "ovr_btn": "0", "age": "3", "sex": "C", "weight": "9-2",
         "weight_lbs": "128", "headgear": "", "or": "103", "rpr": "115",
         "tsr": "104", "prize": "39697.00", "time": "1:10.19",
         "jockey": "Cieren Fallon", "jockey_claim_lbs": "0",
         "jockey_id": "jky_1", "trainer": "William Haggas",
         "trainer_id": "trn_1", "owner": "Sheikh Juma Dalmook Al Maktoum",
         "owner_id": "own_804908", "sire": "Hello Youmzain (FR)",
         "sire_id": "sir_1", "dam": "Alone (IRE)", "dam_id": "dam_1",
         "damsire": "Galileo", "damsire_id": "dsi_1",
         "comment": "In touch with leaders, headway 2f out, led narrowly 1f out",
         "performance_rating": "112", "speed_rating": "103"},
        {"horse_id": "hrs_2", "horse": "Regional (GB)", "sp": "14/1",
         "sp_dec": "15.00", "position": "4", "draw": "8", "ovr_btn": "2",
         "age": "8", "sex": "G", "weight_lbs": "132", "headgear": "t",
         "or": "108", "rpr": "110", "jockey": "Callum Rodriguez",
         "jockey_claim_lbs": "0", "jockey_id": "jky_2",
         "trainer": "Edward Bethell", "trainer_id": "trn_2",
         "comment": "Prominent, led narrowly under 2f out, no extra",
         "performance_rating": "108", "speed_rating": "101"},
        {"horse_id": "hrs_3", "horse": "Nariko (IRE)", "sp": "80/1",
         "position": "9", "age": "5", "sex": "M", "weight_lbs": "125",
         "or": "87", "jockey": "Jason Hart", "jockey_id": "jky_3",
         "trainer": "Hugo Palmer", "trainer_id": "trn_3",
         "comment": "Took keen hold, weakened over 1f out"},
    ],
}


def test_the_adapter_maps_every_pre_race_field():
    race = race_from_raw(card_from_result(DOC), date(2026, 9, 6))
    assert race.race_id == "rac_32296677400"
    assert race.course == "York"
    assert race.off_time == "3:50"                  # from `off`, not off_dt
    assert race.race_class == 1                     # "Class 1" -> 1
    assert race.pattern == "Listed"                 # the feed key, kept
    assert race.distance_f == 6.0                   # "6f" -> 6.0, not None
    assert race.going == "Good To Soft"
    assert race.race_type == "Flat"
    assert race.is_handicap is False                # a Listed race, not a handicap
    assert race.field_size == 3

    zain = race.runners[0]
    assert zain.horse_id == "hrs_1"
    assert zain.weight_lbs == 128                   # from weight_lbs, via lbs
    assert zain.official_rating == 103              # the mark it RAN OFF — pre-race
    assert zain.age == 3 and zain.sex == "C"
    assert zain.trainer == "William Haggas" and zain.jockey_id == "jky_1"
    assert zain.damsire == "Galileo"
    assert zain.odds.consensus == 5.50              # SP in the price slot
    assert race.runners[1].headgear == "t"


def test_the_adapter_never_carries_a_post_race_figure():
    """The look-ahead line. A replay that reads the RPR of the race it is
    replaying is not a replay, it is a memory of the result."""
    race = race_from_raw(card_from_result(DOC), date(2026, 9, 6))
    for r in race.runners:
        assert r.rpr is None
        assert r.performance_rating is None
        assert r.days_since_run is None             # absent — filled from history
        assert r.headgear_first_time is False       # headgear_run absent: never fires
    card = card_from_result(DOC)
    for raw in card["runners"]:
        for key in ("position", "btn", "ovr_btn", "time", "prize", "comment",
                    "rpr", "tsr", "performance_rating", "speed_rating", "sp"):
            assert key not in raw, f"{key} leaked onto the card"


def test_an_unpriced_runner_stays_unpriced():
    """Nariko has no sp_dec. A guessed price is a rule invented from a blank;
    the runner drops out of the priced field exactly as it would live."""
    race = race_from_raw(card_from_result(DOC), date(2026, 9, 6))
    assert race.runners[2].odds.consensus is None
    assert race.runners[0].odds.consensus == 5.50


def test_an_all_weather_course_keeps_its_suffix():
    doc = dict(DOC, course="Kempton (AW)", surface="Polytrack")
    race = race_from_raw(card_from_result(doc), date(2026, 9, 6))
    assert race.course == "Kempton (AW)"
    assert race.is_all_weather is True


def test_the_answer_sheet_comes_back_separately_and_names_the_winner():
    out = outcome_from_result(DOC)
    assert winner_of(out) == "hrs_1"
    assert out["hrs_2"]["position"] == 4
    assert out["hrs_2"]["sp_dec"] == "15.00"
    # the running comment — the manner of THIS race — is answer-sheet only
    assert "led narrowly" in out["hrs_1"]["comment"]
    assert out["hrs_1"]["status"] == ""


def test_a_non_finisher_is_a_status_not_a_crash():
    doc = dict(DOC, runners=[dict(DOC["runners"][1], position="PU")])
    out = outcome_from_result(doc)
    assert out["hrs_2"]["position"] is None and out["hrs_2"]["status"] == "PU"
    assert winner_of(out) == ""


def test_the_replay_imports_no_model_module():
    """Cost is real money (law 5). The replay reads the record; it never
    calls a model."""
    import racing_edge.school.replay as rp
    src = open(rp.__file__).read()
    for banned in ("from racing_edge.ai", "import ai", "resolve_model", "deep("):
        assert banned not in src, f"the replay reaches for {banned}"
