"""THE FAVOURITE FILTER — his method, pinned.

The master, 2026-09-20: "why dont we simply look at all the favourites every
day, rule out the bad ones and dial in the ones that are left". Taught, not
invented (law 2, route one). These tests pin the dots he named, so nobody can
quietly add one he did not teach or drop one he did.
"""
from racing_edge.school import favfilter as F


def test_every_dot_he_taught_fires_and_is_named():
    """A favourite with everything going for it: won last time by under a
    length, comment says it kept on, dropping in class, small field, fresh."""
    good = F.LastRun(position="1", beaten=0.0, comment="kept on strongly to win",
                     days_since=21, rclass=5)
    s = F.score_favourite(good, rclass=6, field_size=6)
    assert s.score == 5, s.reasons          # won, <1L, comment, class drop, small field
    assert not s.ruled_out
    joined = " ".join(s.reasons)
    for phrase in ("won last time", "beaten under a length", "finished well",
                   "dropping in class", "small field"):
        assert phrase in joined


def test_the_bad_favourite_is_ruled_out():
    """Trounced last time, comment says it emptied, long absent, up in class,
    big field. This is the band that ran -29.6% on the tuning half."""
    bad = F.LastRun(position="8", beaten=12.0, comment="weakened quickly, no extra",
                    days_since=200, rclass=4)
    s = F.score_favourite(bad, rclass=3, field_size=16)
    assert s.score == -5, s.reasons
    assert s.ruled_out and s.verdict == "RULED OUT"


def test_trouble_in_running_is_a_positive_because_he_taught_it_so():
    """A horse beaten far but hampered gets the excuse dot — the figure
    understates the run. The two dots offset rather than cancel silently."""
    s = F.score_favourite(
        F.LastRun(position="5", beaten=9.0, comment="badly hampered 2f out",
                  days_since=14, rclass=4),
        rclass=4, field_size=9)
    joined = " ".join(s.reasons)
    assert "had an excuse" in joined and "beaten more than six lengths" in joined
    assert s.score == 0


def test_an_unread_comment_is_declared_and_never_guessed():
    s = F.score_favourite(F.LastRun(position="3", beaten=2.0, comment="",
                                    days_since=20, rclass=4),
                          rclass=4, field_size=9)
    assert any("UNREAD" in r for r in s.reasons)
    assert s.score == 0          # no comment dots either way


def test_a_horse_with_no_previous_run_returns_none_not_a_guess():
    """Unraced is not the same as bad. Scoring it would be inventing."""
    assert F.score_favourite(None, rclass=4, field_size=8) is None


def test_the_floor_is_the_one_he_was_shown():
    """-1 was chosen on the tuning half alone and must not drift: the band
    below it is the only consistently bad group the dots find."""
    assert F.FLOOR == -1
    at = F.score_favourite(F.LastRun(position="4", beaten=7.0, comment="",
                                     days_since=10, rclass=4),
                           rclass=4, field_size=9)
    assert at.score == -1 and not at.ruled_out      # AT the floor is kept


def test_the_last_run_is_the_most_recent_one_BEFORE_today():
    """A look-ahead here would score a horse on a race it has not yet run."""
    rows = [{"date": "2026-09-01", "position": "1", "ovr_btn": "0",
             "comment": "kept on", "class": "Class 4"},
            {"date": "2026-08-01", "position": "6", "ovr_btn": "9",
             "comment": "weakened", "class": "Class 3"},
            {"date": "2026-09-20", "position": "1", "ovr_btn": "0",
             "comment": "TODAY — must never be read", "class": "Class 4"}]
    last = F.last_run_from_history(rows, "2026-09-20")
    assert last.position == "1" and last.comment == "kept on"
    assert last.days_since == 19
    assert F.last_run_from_history(rows, "2026-07-01") is None


def test_the_daily_list_skips_a_race_that_has_already_run():
    """The tripwire (scar 2026-08-27): race_status 'result' is never read."""
    class Client:
        def racecards(self, day):
            return {"racecards": [
                {"race_id": "r1", "course": "Ayr", "off_time": "2:00",
                 "date": "2026-09-20", "race_status": "result", "race_class": "Class 4",
                 "runners": [{"horse_id": "h1", "horse": "Gone",
                              "odds": [{"decimal": "2.0"}]}] * 5},
                {"race_id": "r2", "course": "Ayr", "off_time": "3:00",
                 "date": "2026-09-20", "race_status": "declared", "race_class": "Class 4",
                 "runners": [{"horse_id": f"h{i}", "horse": f"H{i}",
                              "odds": [{"decimal": str(2.0 + i)}]} for i in range(5)]}]}

        def horse_results(self, hid, limit=6):
            return [{"date": "2026-09-01", "position": "1", "ovr_btn": "0",
                     "comment": "kept on well", "class": "Class 4"}]

    rows = F.daily_list("today", client=Client())
    assert [r["race_id"] for r in rows] == ["r2"]
    assert rows[0]["horse"] == "H0" and not rows[0]["ruled_out"]


def test_a_dead_history_door_makes_a_horse_unread_not_bad():
    class Client:
        def racecards(self, day):
            return {"racecards": [
                {"race_id": "r1", "course": "Ayr", "off_time": "3:00",
                 "date": "2026-09-20", "race_status": "declared", "race_class": "Class 4",
                 "runners": [{"horse_id": f"h{i}", "horse": f"H{i}",
                              "odds": [{"decimal": str(2.0 + i)}]} for i in range(5)]}]}

        def horse_results(self, hid, limit=6):
            raise RuntimeError("door down")

    rows = F.daily_list("today", client=Client())
    assert rows[0]["score"] is None and "UNREAD" in rows[0]["verdict"]


def test_an_odds_on_favourite_is_ruled_out_before_its_dots_are_counted():
    """His instruction, 2026-09-20: "well no odd on horses rule out" — his own
    bar #16. Without it the dots quietly select short prices, because a short
    price is what good recent form produces: every horse the filter named over
    18-19 September was 1.40. Ruling them out improved the held-out return
    from +16.7% to +35.1%."""
    perfect = F.LastRun(position="1", beaten=0.0, comment="kept on strongly",
                        days_since=14, rclass=5)
    # the same horse, priced either side of the bar
    keep = F.score_favourite(perfect, rclass=6, field_size=6, price=2.5)
    assert keep.score == 5 and keep.named and not keep.ruled_out

    out = F.score_favourite(perfect, rclass=6, field_size=6, price=1.40)
    assert out.ruled_out and not out.named
    assert "odds-on" in out.reasons[0] and "71%" in out.reasons[0]

    assert F.ODDS_ON == 2.0
    evens = F.score_favourite(perfect, rclass=6, field_size=6, price=2.0)
    assert not evens.ruled_out, "evens is not odds-on"


def test_price_is_optional_so_the_corpus_grader_still_works():
    """Called without a price the bar cannot fire — the grader passes None
    deliberately when measuring the no-bar baseline."""
    s = F.score_favourite(F.LastRun(position="1", beaten=0.0, comment="kept on",
                                    days_since=14, rclass=5),
                          rclass=6, field_size=6)
    assert not s.ruled_out and s.named


def test_the_chase_line_is_blunt_on_purpose():
    """Born by the RECORD (law 2 route three): chase favourites at 2.0+ ran
    +13.1% over 540 races, positive in 7 months of 9, where flat and hurdle
    managed 1 of 9. Two conditions only — a fact about the race and his own
    odds-on bar — so there is nothing here anyone can tune."""
    rows = [
        {"type": "Chase", "price": 3.0, "course": "Ayr", "off": "2:00",
         "horse": "Jumper", "field": 7},
        {"type": "Chase", "price": 1.80, "course": "Ayr", "off": "2:30",
         "horse": "Too Short", "field": 6},          # odds-on: out
        {"type": "Hurdle", "price": 3.0, "course": "Ayr", "off": "3:00",
         "horse": "Wrong Code", "field": 8},         # hurdle: out
        {"type": "Flat", "price": 4.0, "course": "Ayr", "off": "3:30",
         "horse": "Wrong Code Too", "field": 9},     # flat: out
    ]
    picked = F.chase_line(rows)
    assert [r["horse"] for r in picked] == ["Jumper"]
    assert F.CHASE_LINE_MIN_PRICE == 2.0
    # exactly 2.0 is kept — evens is not odds-on
    assert F.chase_line([{"type": "Chase", "price": 2.0, "course": "x",
                          "off": "1:00", "horse": "Evens", "field": 6}])
