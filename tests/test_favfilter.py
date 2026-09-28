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


def test_the_floor_is_the_one_he_set():
    """His word, 2026-09-27: "yes raise it to +2". At -1 the filter ruled out
    2 favourites of 18 on its first day and 12 of the 16 kept lost; +2 keeps
    about a quarter of the card, winning 34-35% in both archive periods."""
    assert F.FLOOR == 2
    at = F.score_favourite(F.LastRun(position="1", beaten=0.5, comment="",
                                     days_since=10, rclass=4),
                           rclass=4, field_size=9)
    assert at.score == 2 and not at.ruled_out       # AT the floor is kept
    below = F.score_favourite(F.LastRun(position="2", beaten=0.5, comment="",
                                        days_since=10, rclass=4),
                              rclass=4, field_size=9)
    assert below.score == 1 and below.ruled_out     # +1 is ruled out now


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


def test_the_live_07_30_list_rules_out_odds_on_too():
    """27 Sep: his "no odds on" ruling reached the grader but not the list the
    box mails at 07:30 — daily_list never passed the price, so the bar could
    not fire and odds-on favourites were named on four days of five. The rule
    must hold where the pick is made, not only where it is graded."""
    class Client:
        def racecards(self, day):
            return {"racecards": [
                {"race_id": "r1", "course": "Newmarket", "off_time": "2:00",
                 "date": "2026-09-26", "race_status": "declared", "race_class": "Class 4",
                 "runners": [{"horse_id": f"h{i}", "horse": f"H{i}",
                              "odds": [{"decimal": str(1.5 + i)}]} for i in range(5)]}]}

        def horse_results(self, hid, limit=6):
            return [{"date": "2026-09-01", "position": "1", "ovr_btn": "0",
                     "comment": "kept on well", "class": "Class 4"}]

    rows = F.daily_list("today", client=Client())
    assert rows[0]["price"] == 1.5 and rows[0]["ruled_out"], "odds-on reached the list"
    assert "odds-on" in rows[0]["reasons"][0]
    assert F.todays_picks(rows) == [], "an odds-on favourite must never be named"


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


def test_both_corpus_directories_are_read(tmp_path, monkeypatch):
    """The held-out days live in a second directory so their filenames cannot
    collide with the box's nightly files. Every reader must follow them there:
    reading only the first silently drops the held-out manner dots instead of
    failing, which shrank the named set on 2026-09-21."""
    a, b = tmp_path / "main", tmp_path / "hold"
    a.mkdir(); b.mkdir()
    (a / "2026-01-01.csv").write_text("r1,h1,kept on well\n")
    (b / "2026-09-01.csv").write_text("r2,h2,weakened badly\n")
    com = F._comments((str(a), str(b)))
    assert com[("r1", "h1")] == "kept on well"
    assert com[("r2", "h2")] == "weakened badly", "held-out comments were dropped"
    assert "holdout" in " ".join(F.COMMENT_DIRS)


def test_at_least_two_horses_every_day():
    """His instruction, 2026-09-21: "pick at least 2 horses". A day with one
    qualifier still names two — the second is flagged as a top-up so it is
    never mistaken for one that cleared the bar, and it carries its own lower
    base rate."""
    rows = [
        {"course": "Ayr", "off": "2:00", "race_id": "r1", "horse": "Alpha",
         "price": 2.5, "field": 6, "type": "Flat", "score": 4,
         "ruled_out": False, "verdict": "NAMED", "reasons": []},
        {"course": "Ayr", "off": "2:30", "race_id": "r2", "horse": "Beta",
         "price": 3.0, "field": 8, "type": "Chase", "score": 1,
         "ruled_out": False, "verdict": "kept", "reasons": []},
        {"course": "Ayr", "off": "3:00", "race_id": "r3", "horse": "Rejected",
         "price": 4.0, "field": 9, "type": "Flat", "score": -3,
         "ruled_out": True, "verdict": "RULED OUT", "reasons": []},
    ]
    picks = F.todays_picks(rows)
    assert len(picks) >= F.MIN_NAMED == 2
    assert picks[0]["horse"] == "Alpha" and picks[0]["cleared"] is True
    assert picks[1]["cleared"] is False, "the filler must be flagged as a top-up"
    assert all(p["horse"] != "Rejected" for p in picks), \
        "a ruled-out horse is never named, not even to reach the minimum"


def test_confidence_is_a_base_rate_from_the_record_not_an_opinion():
    """Every figure is the historical strike rate of favourites that scored
    the same way, with its sample size carried beside it so a 46% built on 88
    runners can never be read as a 46% built on thousands."""
    pct, n = F.confidence(4)
    assert (pct, n) == (46.6, 88)
    assert F.confidence(-2) == (21.5, 177)
    # off the top and bottom of the table it clamps, never extrapolates
    assert F.confidence(9) == F.CONFIDENCE[max(F.CONFIDENCE)]
    assert F.confidence(-9) == F.CONFIDENCE[min(F.CONFIDENCE)]
    assert F.confidence(None) == F.BASE_RATE
    # the named band must actually beat backing any eligible favourite
    assert F.CONFIDENCE[4][0] > F.BASE_RATE[0] > F.CONFIDENCE[-2][0]


def _card_rows():
    """Two scored favourites and one chase favourite, as daily_list shapes them."""
    base = {"off": "2:00", "field": 6, "reasons": [], "ruled_out": False,
            "date": "2026-09-27"}
    return [dict(base, race_id="r1", course="Ayr", horse="Good", horse_id="h1",
                 price=3.0, score=4, type="Flat"),
            dict(base, race_id="r2", course="Ayr", horse="Okay", horse_id="h2",
                 price=2.5, score=2, type="Hurdle"),
            dict(base, race_id="r3", course="Kelso", horse="Chaser", horse_id="h3",
                 price=2.2, score=1, type="Chase")]


def test_the_filter_banks_its_picks_before_the_off_and_never_re_picks(tmp_path):
    """27 Sep: the filter and the chase line printed at 07:30 and nothing kept
    them, while the mail said GRADED NIGHTLY. A line never recorded can never
    be judged. Law 1: bank pre-off, never re-pick intraday."""
    p = tmp_path / "filter_record.csv"
    # 2 picks + 1 chase + every favourite's 07:30 price (3) + the Chaser as a
    # favourite race (races_all + races)
    assert F.record_picks(_card_rows(), "2026-09-27", p) == 8
    rows = [r for r in F._load_record(p) if r["line"] not in ("fav", "races", "races_all")]
    assert [(r["line"], r["horse"]) for r in rows] == [
        ("filter", "Good"), ("filter", "Okay"), ("chase", "Chaser")]
    assert rows[0]["cleared"] == "1" and rows[1]["cleared"] == "0"
    assert F.record_picks(_card_rows()[:1], "2026-09-27", p) == 0, "a re-run re-picked"
    assert len(F._load_record(p)) == 8


def test_the_night_settles_the_filter_at_sp(tmp_path):
    """Won is first; beaten or fell is LOST; missing from the runners is a
    non-runner VOID; a race the results do not hold stays open."""
    p = tmp_path / "filter_record.csv"
    F.record_picks(_card_rows(), "2026-09-27", p)
    results = {"results": [
        {"race_id": "r1", "runners": [{"horse_id": "h1", "position": "1", "sp_dec": "3.25"}]},
        {"race_id": "r2", "runners": [{"horse_id": "h9", "position": "1", "sp_dec": "5.0"}]},
    ]}
    assert F.settle_record("2026-09-27", results, p) == 4        # 2 picks + their 2 fav rows
    got = {r["horse"]: (r["result"], r["sp"]) for r in F._load_record(p) if r["line"] != "fav"}
    assert got == {"Good": ("WON", "3.25"), "Okay": ("VOID", ""), "Chaser": ("", "")}
    assert F.settle_record("2026-09-27", results, p) == 0, "settle must be write-once"
    out = F.render_record(p)
    assert "1 settled ·   1 won · strike 100.0% · P/L +2.25" in out


def test_the_filter_banks_the_nap_in_the_real_record(tmp_path):
    """His word, 2026-09-27: "6 from 11 is solid ... u just gave me shitty
    engine picks". The filter's best pick is the day's nap in nap.db, the same
    ledger the engine banked to, settled the same way. A re-run never re-picks."""
    from racing_edge.study.naplog import NapLog
    log = NapLog(tmp_path / "nap.db")
    line = F.bank_nap(_card_rows(), "2026-09-27", log)
    row = log.existing(__import__("datetime").date(2026, 9, 27))
    assert row["horse"] == "Good" and row["race_id"] == "r1" and row["price"] == 3.0
    assert row["won"] is None and row["confident"] == 1
    assert "FILTER NAP" in row["case_text"], "health reds a nap with no case"
    assert line.startswith("NAP: Good")
    again = F.bank_nap(list(reversed(_card_rows())), "2026-09-27", log)
    assert "not re-banked" in again
    assert log.existing(__import__("datetime").date(2026, 9, 27))["horse"] == "Good"
    log.close()


def test_a_day_with_no_eligible_favourite_is_a_named_pass(tmp_path):
    from racing_edge.study.naplog import NapLog
    log = NapLog(tmp_path / "nap.db")
    out = [dict(r, ruled_out=True) for r in _card_rows()]
    assert "NO BET" in F.bank_nap(out, "2026-09-27", log)
    row = log.existing(__import__("datetime").date(2026, 9, 27))
    assert row["won"] == -1 and "no eligible favourite" in row["case_text"]
    log.close()


def test_the_record_labels_the_filter_era():
    from racing_edge.study.naplog import version, FILTER_FROM
    from racing_edge.school import record_export as R
    assert FILTER_FROM == R.FILTER_FROM == "2026-09-27"
    assert (version("2026-09-26"), version("2026-09-27")) == ("v2", "filter")
    assert version("2026-09-02") == "v1"


def test_the_07_30_task_runs_the_filter_not_the_paid_engine():
    """The nap task banks the filter's pick by default; the engine's deep read
    runs only under NAP_SOURCE=engine. CODE lines only, never the comments."""
    from pathlib import Path
    sh = Path("trial.sh").read_text()
    nap = sh[sh.index("\n  nap)"):sh.index("\n  dissect)")]
    code = "\n".join(l for l in nap.splitlines() if not l.strip().startswith("#"))
    assert "favfilter --day today --bank --email" in code
    assert '"${NAP_SOURCE:-filter}" = "engine"' in code
    engine_at = code.index("racing_edge.cli.nap")
    assert code.index("NAP_SOURCE") < engine_at, "the engine must sit behind the switch"


def test_every_favourite_keeps_its_0730_price_and_settles_at_sp(tmp_path):
    """His word, 2026-09-27: "yes add it". The study of the first filter day
    saw his market law 4d in the results but could not test it: only the
    picks kept a morning price. Every favourite on the card, ruled out or
    not, is now banked with its 07:30 price and settled at SP."""
    p = tmp_path / "filter_record.csv"
    rows = _card_rows() + [dict(_card_rows()[0], race_id="r4", horse="Crunched",
                                horse_id="h4", price=2.1, score=-2, ruled_out=True)]
    F.record_picks(rows, "2026-09-27", p)
    favs = [r for r in F._load_record(p) if r["line"] == "fav"]
    assert [r["horse"] for r in favs] == ["Good", "Okay", "Chaser", "Crunched"]
    assert favs[3]["price"] == "2.1" and favs[3]["score"] == "-2"
    results = {"results": [
        {"race_id": "r1", "runners": [{"horse_id": "h1", "position": "1", "sp_dec": "3.6"}]},
        {"race_id": "r4", "runners": [{"horse_id": "h4", "position": "4", "sp_dec": "1.83"}]}]}
    F.settle_record("2026-09-27", results, p)
    out = F.render_record(p)
    assert "backed 10%+" in out and "drifted 20%+" in out
    assert "backed 10%+        1 ·   0 won" in out         # 2.10 -> 1.83, beaten
    assert "drifted 20%+       1 ·   1 won" in out         # 3.00 -> 3.60, won


def test_novice_and_maiden_races_are_avoided():
    """His word, 2026-09-27: "novice n maiden avoid from now on", after the
    Haydock nap — a +4 built on one run in a race of one- and two-run babies,
    beaten by an improver. The favourite is still listed and recorded (so the
    record shows what is being avoided) but it can never be picked, never
    ride the chase line, and never be sorted by v3."""
    class Client:
        def racecards(self, day):
            def card(rid, name, typ="Flat"):
                return {"race_id": rid, "course": "Haydock", "off_time": "2:00",
                        "date": "2026-09-28", "race_status": "declared",
                        "race_class": "Class 3", "race_name": name, "type": typ,
                        "runners": [{"horse_id": f"{rid}h{i}", "horse": f"{rid}H{i}",
                                     "odds": [{"decimal": str(2.5 + i)}]} for i in range(5)]}
            return {"racecards": [card("n1", "EBF Novice Stakes (GBB Race)"),
                                  card("m1", "Maiden Hurdle", "Hurdle"),
                                  card("c1", "Novices' Chase", "Chase"),
                                  card("h1", "Class 3 Handicap")]}

        def horse_results(self, hid, limit=6):
            return [{"date": "2026-09-01", "position": "1", "ovr_btn": "0",
                     "comment": "kept on well", "class": "Class 4"}]

    rows = F.daily_list("today", client=Client())
    by = {r["race_id"]: r for r in rows}
    for rid in ("n1", "m1", "c1"):
        assert by[rid]["ruled_out"] and "novice/maiden" in by[rid]["reasons"][0]
    assert not by["h1"]["ruled_out"]
    assert [p["race_id"] for p in F.todays_picks(rows)] == ["h1"]
    assert F.chase_line(rows) == [], "a novices' chase rode the chase line"
    assert F.avoided_race("Beginners' Chase") is False      # his words only: novice, maiden


def test_the_favourite_races_are_a_recorded_shadow(tmp_path):
    """His word, 2026-09-27: "yes shadow it". Favourites under 3.0, in nine
    runners or fewer, not hurdles, not Class 5-6, not novice/maiden: recorded
    every morning with their top two by his dots, settled beside the filter,
    and never the nap."""
    base = {"off": "2:00", "reasons": [], "ruled_out": False, "date": "2026-09-28",
            "race_name": "Handicap", "type": "Flat", "rclass": 4, "field": 7}
    rows = [dict(base, race_id="a", course="Ayr", horse="In", horse_id="a1", price=2.5, score=2),
            dict(base, race_id="b", course="Ayr", horse="Also", horse_id="b1", price=2.2, score=3),
            dict(base, race_id="c", course="Ayr", horse="Third", horse_id="c1", price=2.8, score=1),
            dict(base, race_id="d", course="Ayr", horse="Price", horse_id="d1", price=3.0, score=4),
            dict(base, race_id="e", course="Ayr", horse="Big", horse_id="e1", price=2.4, score=4, field=10),
            dict(base, race_id="f", course="Ayr", horse="Hurdler", horse_id="f1", price=2.4, score=4, type="Hurdle"),
            dict(base, race_id="g", course="Ayr", horse="Low", horse_id="g1", price=2.4, score=4, rclass=6),
            dict(base, race_id="h", course="Ayr", horse="Baby", horse_id="h1", price=2.4, score=4,
                 race_name="Maiden Stakes"),
            dict(base, race_id="i", course="Curragh", horse="Irish", horse_id="i1", price=2.6, score=0, rclass=None)]
    fr = F.favourite_races(rows)
    assert [r["horse"] for r in fr] == ["Also", "In", "Third", "Irish"]
    p = tmp_path / "filter_record.csv"
    F.record_picks(rows, "2026-09-28", p)
    rec = F._load_record(p)
    assert [r["horse"] for r in rec if r["line"] == "races"] == ["Also", "In"]
    assert len([r for r in rec if r["line"] == "races_all"]) == 4
    assert "fav races (top 2)" in F.render_record(p)


def test_bumpers_are_avoided_too():
    """His word, 2026-09-28: "bumpers out too". Caught by the race name
    (bumper / NH flat / INH flat) or by the card's race type."""
    for name in ("Mares' Standard Open National Hunt Flat Race", "INH Flat Race",
                 "Junior Bumper", "Open NH Flat Race"):
        assert F.avoided_race(name), name
    assert F.avoided_race("NH Flat")                      # the card's type field
    assert not F.avoided_race("Beginners' Chase"), "not his word: beginners' chases stay"
    assert not F.avoided_race("Class 3 Handicap Hurdle")
    base = {"off": "2:00", "reasons": [], "ruled_out": False, "date": "2026-09-29",
            "race_name": "Open Race", "rclass": 4, "field": 7, "score": 3,
            "course": "Ayr", "horse_id": "b1", "horse": "Bumper Fav", "price": 2.4}
    assert F.favourite_races([dict(base, race_id="b", type="NH Flat")]) == []
