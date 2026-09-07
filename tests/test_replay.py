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


# --------------------------------------------------------------------------- #
# the client — serves a past day, refuses every door that knows today
# --------------------------------------------------------------------------- #
class _Api:
    def __init__(self):
        self.calls = []

    def horse_results(self, horse_id, limit=12):
        self.calls.append(horse_id)
        return [{"race_id": "old", "date": "2026-08-01", "course": "York",
                 "runners": [{"horse_id": horse_id, "position": "2"}]}]


def test_the_client_serves_the_rebuilt_card_and_caches_histories(tmp_path):
    from racing_edge.school.replay import ReplayClient
    api = _Api()
    c = ReplayClient(api, [card_from_result(DOC)], tmp_path, date(2026, 9, 6))
    assert c.racecards("2026-09-06")["racecards"][0]["race_id"] == "rac_32296677400"
    first = c.horse_results("hrs_1", limit=30)
    second = c.horse_results("hrs_1", limit=30)
    assert first == second
    assert api.calls == ["hrs_1"]            # the door was asked ONCE
    assert c.fetched == 1 and c.served_from_cache == 1
    # a re-run of the same day is free
    c2 = ReplayClient(api, [card_from_result(DOC)], tmp_path, date(2026, 9, 6))
    c2.horse_results("hrs_1", limit=30)
    assert api.calls == ["hrs_1"]
    # a DIFFERENT as_of is a different question and is fetched again
    c3 = ReplayClient(api, [card_from_result(DOC)], tmp_path, date(2026, 9, 5))
    c3.horse_results("hrs_1", limit=30)
    assert api.calls == ["hrs_1", "hrs_1"]


def test_every_current_stats_door_raises():
    """These doors answer about TODAY. build_evidence already skips them when
    as_of is set, so in a correct run they are never called — which is why
    they raise: an as_of that failed to arrive must kill the replay, not
    quietly score it with knowledge the morning never had."""
    import pytest

    from racing_edge.school.replay import LookAheadError, ReplayClient
    c = ReplayClient(_Api(), [], "/tmp", date(2026, 9, 6))
    for call in (lambda: c.trainer_jockeys("trn_1"),
                 lambda: c.trainer_course("trn_1"),
                 lambda: c.jockey_course("jky_1"),
                 lambda: c.horse_distance_times("hrs_1")):
        with pytest.raises(LookAheadError):
            call()


def test_the_shape_book_never_judges_a_race_it_has_seen(tmp_path):
    """The book that grades a replayed race must be built from races BEFORE
    it. Fails with the `before` filter removed."""
    from racing_edge.school import shapebook as sb
    from racing_edge.school.replay import seed_shapebook
    raw = tmp_path / "raw"
    raw.mkdir()
    # 40 identical Class 6 flat races on one old day, 40 more on the replay day
    def rows(day, rid0):
        out = []
        for i in range(40):
            for j, (sp, pos) in enumerate([("2.0", "1"), ("5.0", "2"),
                                           ("9.0", "3"), ("11.0", "4"),
                                           ("15.0", "5")]):
                out.append(f"{day},{rid0 + i},Kempton,G,F,Class 6,6,"
                           f"h{rid0 + i}_{j},{sp},{pos},0,jky,trn")
        return out
    (raw / "2026-08-01.csv").write_text("\n".join(rows("2026-08-01", 1000)) + "\n")
    (raw / "2026-09-06.csv").write_text("\n".join(rows("2026-09-06", 2000)) + "\n")

    all_cells = sb.build(raw)
    seeded = seed_shapebook(date(2026, 9, 6), raw)
    key = next(iter(all_cells))
    assert all_cells[key]["n"] == 80                 # both days
    assert sb._CELLS_CACHE[raw.resolve()][key]["n"] == 40   # only the earlier one
    assert seeded == len(all_cells)


def test_the_replay_imports_no_model_module():
    """Cost is real money (law 5). The replay reads the record; it never
    calls a model."""
    import racing_edge.school.replay as rp
    src = open(rp.__file__).read()
    for banned in ("from racing_edge.ai", "import ai", "resolve_model", "deep("):
        assert banned not in src, f"the replay reaches for {banned}"
