"""THE FAVOURITE MODEL (his word, 2026-09-27: "why dont you just do it").

The model is only as good as the match between what it learned from and what
it is fed at 07:30. These tests pin that match, the pure-Python scorer the box
runs, the loud fallback to his filter, and the archive that keeps the past."""
import csv
import json
from datetime import date
from pathlib import Path

from racing_edge.school import archive as A
from racing_edge.school import favfilter as F
from racing_edge.school import favmodel as M


def _runner(hid, sp, pos, **kw):
    base = {"horse_id": hid, "position": pos, "sp_dec": str(sp), "ovr_btn": "0",
            "draw": "", "weight_lbs": "", "or": "", "age": "", "headgear": "",
            "jockey_id": "j" + hid, "trainer_id": "t" + hid}
    base.update(kw)
    return base


def _race(day, rid, runners, **kw):
    r = {"date": day, "race_id": rid, "course": "Ayr", "region": "GB", "type": "Flat",
         "class": "Class 4", "pattern": "", "going": "Good", "surface": "Turf",
         "dist_f": "6f", "runners": runners}
    r.update(kw)
    return r


def _past_and_today():
    past = _race("2026-09-20", "rac_1", [
        _runner("hrs_1", 3.0, "1", **{"or": "70", "weight_lbs": "130"}),
        _runner("hrs_2", 4.0, "2", **{"or": "72", "weight_lbs": "132"}),
        _runner("hrs_3", 6.0, "3"), _runner("hrs_4", 9.0, "4")])
    today = _race("2026-09-28", "rac_2", [
        _runner("hrs_1", 2.5, "", **{"or": "74", "weight_lbs": "133", "draw": "3", "age": "4"}),
        _runner("hrs_2", 3.5, "", **{"or": "72", "weight_lbs": "131", "draw": "1", "age": "5"}),
        _runner("hrs_3", 7.0, "", **{"draw": "2"}), _runner("hrs_4", 11.0, "", **{"draw": "4"})])
    return past, today


def test_the_0730_card_feeds_the_model_exactly_what_it_learned_from():
    """The same race, once through the training walk and once as a 07:30
    racecard, must give the SAME 35 inputs. A mismatch here is a model
    learning one thing and being asked another."""
    past, today = _past_and_today()
    rows, _ = M.dataset([past, today], com={})
    trained = [r for r in rows if r["race_id"] == "rac_2"][0]["x"]

    card = {"date": "2026-09-28", "race_id": "rac_2", "course": "Ayr", "off_time": "2:00",
            "region": "GB", "type": "Flat", "race_class": "Class 4", "pattern": "",
            "going": "Good", "surface": "Turf", "distance_f": "6f",
            "runners": [{"horse_id": x["horse_id"], "horse": x["horse_id"],
                         "odds": [{"decimal": x["sp_dec"]}], "draw": x["draw"],
                         "lbs": x["weight_lbs"], "ofr": x["or"], "age": x["age"],
                         "jockey_id": x["jockey_id"], "trainer_id": x["trainer_id"]}
                        for x in today["runners"]]}
    model = {"median": [0.0] * 35, "mean": [0.0] * 35, "scale": [1.0] * 35,
             "coef": [0.0] * 35, "intercept": 0.0, "n": 1}
    live = M.score_cards([card], "2026-09-28", model, [past], com={})[0]["x"]
    same = lambda a, b: (a != a and b != b) or a == b
    diff = [M.FEATURES[i] for i in range(35) if not same(trained[i], live[i])]
    assert not diff, f"live inputs differ from training: {diff}"
    assert trained[M.FEATURES.index("mark_v_last_win")] == 4.0      # 74 v won off 70


def test_the_box_scorer_is_plain_arithmetic():
    """No numpy, no scikit-learn on the box: the logistic model is scored by
    hand from its exported numbers, and a missing value takes the median."""
    m = {"median": [5.0, 1.0], "mean": [4.0, 0.0], "scale": [2.0, 1.0],
         "coef": [1.0, -0.5], "intercept": -1.0}
    # z = -1 + 1*(6-4)/2 + -0.5*(1-0)/1 = -0.5  (second value missing -> median 1.0)
    p = M.probability(m, [6.0, float("nan")])
    assert abs(p - 1 / (1 + 2.718281828459045 ** 0.5)) < 1e-9


def test_the_real_model_file_is_present_and_matches_the_code():
    model = M.load_model()
    assert model is not None, "data/model/favmodel.json is missing — the nap falls back"
    assert model["features"] == M.FEATURES, "the model was trained on other inputs"
    wf = model["walk_forward"]
    assert wf["model_nap"][0] == wf["filter_nap"][0], "judged on different days"


def test_the_model_banks_the_nap_and_says_so(tmp_path):
    from racing_edge.study.naplog import NapLog
    log = NapLog(tmp_path / "nap.db")
    picks = [{"race_id": "r9", "course": "Kelso", "off": "3:10", "horse": "Top",
              "horse_id": "h9", "price": 3.2, "score": 2, "cleared": True,
              "confidence": 51.0, "confidence_n": 6444, "reasons": ["model 51%"]}]
    line = F.bank_nap([], "2026-09-28", log, picks=picks, source="v3")
    row = log.existing(date(2026, 9, 28))
    assert line.startswith("NAP: Top") and row["horse"] == "Top"
    assert row["aligned"] == "v3" and row["case_text"].startswith("V3 NAP")
    log.close()


def test_a_failed_v3_never_costs_the_day_and_says_so(tmp_path, monkeypatch, capsys):
    """If v3 cannot score, the day still gets his filter's pick — and the
    mail says in words that the shadow failed."""
    from racing_edge.study.naplog import NapLog
    import racing_edge.cli._common as C
    monkeypatch.chdir(tmp_path)
    rows = [{"race_id": "r1", "course": "Ayr", "off": "2:00", "horse": "Good",
             "horse_id": "h1", "price": 3.0, "score": 4, "type": "Flat",
             "field": 6, "reasons": [], "ruled_out": False, "date": "2026-09-28"}]
    monkeypatch.setattr(F, "daily_list", lambda day, floor: rows)
    monkeypatch.setattr(C, "open_nap_log", lambda: NapLog(tmp_path / "nap.db"))

    def boom(cards, day):
        raise FileNotFoundError("data/model/favmodel.json missing")
    monkeypatch.setattr(F, "model_picks", boom)
    assert F.main(["--day", "today", "--bank"]) == 0
    out = capsys.readouterr().out
    assert "v3 FAILED" in out and "NAP: Good" in out
    row = NapLog(tmp_path / "nap.db").existing(date(2026, 9, 28))
    assert row["horse"] == "Good" and row["aligned"] == "filter"


def test_the_archive_tops_itself_up_and_never_reads_a_race_twice(tmp_path):
    live = tmp_path / "live"
    live.mkdir()
    (live / "2026-09-26.csv").write_text(",".join(A.RACE_COLS + A.RUNNER_COLS) + "\n")

    class Client:
        def results_by_date(self, d):
            return {"results": [{"race_id": f"rac_{d}", "date": d, "course": "Ayr",
                                 "runners": [{"horse_id": "h1", "position": "1",
                                              "sp_dec": "3.0"}]}]}
    wrote = A.update(Client(), date(2026, 9, 28), live_dir=live, archive=tmp_path / "none.gz")
    assert [w[:10] for w in wrote] == ["2026-09-27", "2026-09-28"]
    assert A.update(Client(), date(2026, 9, 28), live_dir=live,
                    archive=tmp_path / "none.gz") == [], "a held day was refetched"
    with open(live / "2026-09-28.csv", "a", newline="") as fh:     # a duplicate row
        csv.writer(fh).writerow(["2026-09-28", "rac_2026-09-28"] + [""] * 8
                                + ["h1", "1", "3.0"] + [""] * 8)
    races = A.load(tmp_path / "none.gz", live)
    assert len(races) == 2 and all(len(r["runners"]) == 1 for r in races)


def test_his_filter_picks_the_nap_and_v3_rides_beside_it(tmp_path, monkeypatch, capsys):
    """His word, 2026-09-27 evening: "use the system that actually picks
    winners". The filter's first day went 2 from 2; v3's would-be picks 0
    from 2. So the FILTER banks the nap by default, and v3 is scored and
    recorded beside it every morning — it takes the nap only on
    NAP_PICKER=v3, which it has to earn live."""
    from racing_edge.study.naplog import NapLog
    import racing_edge.cli._common as C
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NAP_PICKER", raising=False)
    rows = [{"race_id": "r1", "course": "Ayr", "off": "2:00", "horse": "Good",
             "horse_id": "h1", "price": 3.0, "score": 4, "type": "Flat",
             "field": 6, "reasons": [], "ruled_out": False, "date": "2026-09-28"}]
    v3 = [{"race_id": "r9", "course": "Kelso", "off": "3:10", "horse": "Other",
           "horse_id": "h9", "price": 2.6, "score": 1, "cleared": True, "prob": 0.44,
           "confidence": 44.0, "confidence_n": 6444, "why": ["price +"],
           "reasons": ["model 44%"]}]
    monkeypatch.setattr(F, "daily_list", lambda day, floor: rows)
    monkeypatch.setattr(F, "model_picks", lambda cards, day: v3)
    monkeypatch.setattr(C, "open_nap_log", lambda: NapLog(tmp_path / "nap.db"))
    assert F.main(["--day", "today", "--bank"]) == 0
    out = capsys.readouterr().out
    row = NapLog(tmp_path / "nap.db").existing(date(2026, 9, 28))
    assert row["horse"] == "Good" and row["aligned"] == "filter", "v3 took the nap"
    assert "V3 SHADOW" in out and "Other" in out
    rec = {r["line"]: r["horse"] for r in F._load_record(tmp_path / "data/filter_record.csv")}
    assert rec.get("v3") == "Other", "v3's pick must be recorded to be judged"


def test_v3_picks_only_when_told_to(tmp_path, monkeypatch):
    from racing_edge.study.naplog import NapLog
    import racing_edge.cli._common as C
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NAP_PICKER", "v3")
    rows = [{"race_id": "r1", "course": "Ayr", "off": "2:00", "horse": "Good",
             "horse_id": "h1", "price": 3.0, "score": 4, "type": "Flat",
             "field": 6, "reasons": [], "ruled_out": False, "date": "2026-09-28"}]
    v3 = [{"race_id": "r9", "course": "Kelso", "off": "3:10", "horse": "Other",
           "horse_id": "h9", "price": 2.6, "score": 1, "cleared": True, "prob": 0.44,
           "confidence": 44.0, "confidence_n": 6444, "why": [], "reasons": ["model 44%"]}]
    monkeypatch.setattr(F, "daily_list", lambda day, floor: rows)
    monkeypatch.setattr(F, "model_picks", lambda cards, day: v3)
    monkeypatch.setattr(C, "open_nap_log", lambda: NapLog(tmp_path / "nap.db"))
    F.main(["--day", "today", "--bank"])
    assert NapLog(tmp_path / "nap.db").existing(date(2026, 9, 28))["horse"] == "Other"


def test_the_record_keeps_the_filter_label_and_the_night_keeps_the_archive():
    from racing_edge.study.naplog import version
    assert (version("2026-09-27"), version("2026-09-28")) == ("filter", "filter")
    sh = Path("trial.sh").read_text()
    night = sh[sh.index("\n  night)"):]
    code = "\n".join(l for l in night.splitlines() if not l.strip().startswith("#"))
    assert "racing_edge.school.archive --update" in code


def test_v3_never_picks_a_favourite_his_filter_ruled_out(monkeypatch):
    """27 Sep, v3's first card: Kingdom Of Camelot scored -2 on his dots and
    v3 still put it top on price (4th at 1.83). His filter rules out first;
    v3 only sorts the favourites that are left."""
    fi = M.FEATURES.index("filter_score")

    def scored(cards, day, model, races, com=None):
        base = {"course": "Curragh", "off": "2:00", "horse_id": "h", "why": []}
        x_bad, x_good, x_unread = [0.0] * 35, [0.0] * 35, [0.0] * 35
        x_bad[fi], x_good[fi], x_unread[fi] = -2.0, 2.0, float("nan")
        return [dict(base, race_id="r1", horse="Kingdom Of Camelot", price=2.1, prob=0.43, x=x_bad),
                dict(base, race_id="r2", horse="Rose Moon", price=2.63, prob=0.41, x=x_good),
                dict(base, race_id="r3", horse="Unread", price=2.2, prob=0.42, x=x_unread)]
    monkeypatch.setattr(M, "score_cards", scored)
    monkeypatch.setattr(M, "load_model", lambda: {"n": 1})
    monkeypatch.setattr(A, "load", lambda: [])
    picks = F.model_picks([], "2026-09-27")
    assert [p["horse"] for p in picks] == ["Rose Moon"], "v3 overruled his filter"
