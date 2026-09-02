"""AUDIT 2026-09-02 — every fix runs its behaviour; put the bug back and it screams.

The master: "a test that FAILS when the bug is put back (not a grep of the
source — run the behaviour)". Each test names the finding it pins.
"""

from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace as NS

import pytest


# --------------------------------------------------------------------------- #
# gates fail CLOSED
# --------------------------------------------------------------------------- #

def test_still_to_run_is_one_site_and_fails_closed_on_a_broken_time() -> None:
    """Delivery bot #1: the old inner guard returned True on a parse error — a
    race with an unreadable off time read as safe to bank. Now None, and the
    caller treats None as OFF."""
    from racing_edge.pipeline.nap import still_to_run
    now = datetime(2026, 9, 2, 14, 0)
    assert still_to_run("2:30", now) is True          # 14:30, 30 min to spare
    assert still_to_run("2:03", now) is False         # inside the 5-min buffer
    assert still_to_run("14:30", now) is True         # 24h form
    assert still_to_run("abc", now) is None           # cannot check -> caller closes
    assert still_to_run("", now) is None


def test_rank_key_puts_unclassed_below_class_six() -> None:
    """Selection bot #6: `race_class or 6` tied 'unknown' with 'known worst'."""
    from racing_edge.pipeline.nap import _rank_key

    def pick(cls):
        return NS(race_quality=1, price=3.0, race=NS(race_class=cls),
                  conviction=NS(confident=False, mark_known=True, score=2,
                                aligned=("a", "b")))
    assert _rank_key(pick(6)) > _rank_key(pick(None))
    assert _rank_key(pick(5)) > _rank_key(pick(6))


def test_book_code_is_one_site_and_knows_nh_flat() -> None:
    from racing_edge.domain.units import book_code
    assert book_code("Flat") == "F" and book_code("Hurdle") == "H"
    assert book_code("Handicap Chase") == "C" and book_code("NH Flat") == "N"
    assert book_code("") is None and book_code(None) is None


# --------------------------------------------------------------------------- #
# settlement: one function, non-runners void, the backlog sweeps
# --------------------------------------------------------------------------- #

def _log(tmp_path):
    from racing_edge.study.naplog import NapLog
    return NapLog(tmp_path / "nap.db")


def _bank_all(log, d):
    log.record(day=d, race_id="rac_1", course="Ripon", horse="Gem", horse_id="h1",
               price=3.0, score=3, confident=True)
    log.record_shadow(day=d, race_id="rac_1", course="Ripon", horse="Shade",
                      horse_id="h2", price=5.0, score=2)
    log.record_favline(day=d, race_id="rac_1", course="Ripon", horse="Jolly",
                       horse_id="h3", price=1.8)


def _results(runners):
    return [NS(race_id="rac_1", runners=[NS(**r) for r in runners])]


def test_settle_tables_voids_non_runners_and_absentees_and_settles_finishers(tmp_path):
    """Delivery bot #5: 'won = me.position == 1' scored a withdrawn horse as a
    LOSS. Now NR/withdrawn -> VOID with reason; absent from the result -> VOID;
    fallers RAN and lose; the winner wins."""
    from racing_edge.cli.nap import _settle_tables
    from racing_edge.study.naplog import NapLog
    log = _log(tmp_path)
    d = date(2026, 9, 2)
    _bank_all(log, d)
    out = _settle_tables(d, _results([
        {"horse_id": "h1", "position": None, "status": "NR", "sp_dec": None},
        {"horse_id": "h3", "position": 1, "status": "", "sp_dec": 1.8},
        # h2 (shadow) is absent from the result entirely
    ]), log, lambda s: None)
    assert "VOID" in out["nap"] and "non-runner" in out["nap"]
    assert "VOID" in out["shadow"] and "absent" in out["shadow"]
    assert out["favline"].startswith("Jolly WON")
    nap = log.existing(d)
    assert nap["won"] == NapLog.VOID and "NR" in nap["void_reason"]
    assert log.strike_rate() == (0, 0)                # a void is not a bet
    assert log.favline_record()[:2] == (1, 1)
    # a faller RAN: that is a loss, never a void
    (tmp_path / "b").mkdir()
    log2 = _log(tmp_path / "b")
    _bank_all(log2, d)
    out2 = _settle_tables(d, _results([
        {"horse_id": "h1", "position": None, "status": "F", "sp_dec": 3.0}]),
        log2, lambda s: None)
    assert "unplaced" in out2["nap"] and log2.existing(d)["won"] == 0


def test_settle_tables_leaves_a_missing_race_open(tmp_path):
    from racing_edge.cli.nap import _settle_tables
    log = _log(tmp_path)
    d = date(2026, 9, 2)
    _bank_all(log, d)
    out = _settle_tables(d, [NS(race_id="rac_OTHER", runners=[])], log, lambda s: None)
    assert "no result yet" in out["nap"]
    assert log.existing(d)["won"] is None


def test_backlog_sweep_settles_old_days_and_voids_after_seven_with_the_command(tmp_path):
    """Delivery bot #7: '--settle today' never revisited a missed day; the
    comment 'retries tomorrow' was not code. The sweep fetches each open date
    once, settles what it can, and voids what is a week old WITH the console
    command in the reason."""
    from racing_edge.cli.nap import VOID_AFTER_DAYS, _sweep_backlog
    from racing_edge.study.naplog import NapLog
    log = _log(tmp_path)
    today = date(2026, 9, 10)
    _bank_all(log, date(2026, 9, 8))          # 2 days old, result arrives
    log.record(day=date(2026, 9, 1), race_id="rac_1", course="Ripon", horse="Old",
               horse_id="h1", price=3.0, score=1, confident=False)   # 9 days old
    _bank_all(log, date(2026, 9, 9))          # 1 day old, no result yet
    fetched: list[str] = []

    def fetch(ds):
        fetched.append(ds)
        if ds == "2026-09-08":
            return _results([{"horse_id": "h1", "position": 1, "status": "", "sp_dec": 4.0},
                             {"horse_id": "h2", "position": 3, "status": "", "sp_dec": 5.0},
                             {"horse_id": "h3", "position": 2, "status": "", "sp_dec": 1.8}])
        return [NS(race_id="none", runners=[])]

    lines: list[str] = []
    _sweep_backlog(today, log, lines.append, fetch=fetch)
    assert sorted(fetched) == ["2026-09-01", "2026-09-08", "2026-09-09"]   # once each
    assert log.existing(date(2026, 9, 8))["won"] == 1
    old = log.existing(date(2026, 9, 1))
    assert old["won"] == NapLog.VOID and "--settle 2026-09-01" in old["void_reason"]
    assert (today - date(2026, 9, 1)).days >= VOID_AFTER_DAYS
    assert log.existing(date(2026, 9, 9))["won"] is None       # young: still open, named
    assert any("2026-09-09 nap: still open" in ln for ln in lines)


# --------------------------------------------------------------------------- #
# reads: vocabulary
# --------------------------------------------------------------------------- #

def test_manner_reads_the_common_tokens_the_audit_found_blind() -> None:
    from racing_edge.domain.manner import read_manner
    assert read_manner("hung left under pressure inside final furlong")[0] == "trouble"
    assert read_manner("too keen early, weakened")[0] == "trouble"
    assert read_manner("led 2f out, ridden out")[0] == "finisher"
    assert read_manner("carried head high and found little")[0] == "non_finisher"


# --------------------------------------------------------------------------- #
# fetch / store
# --------------------------------------------------------------------------- #

def test_fetch_day_refuses_a_page_without_total(monkeypatch) -> None:
    """Fetch bot #4: a missing 'total' defaulted to 0 and the loop returned after
    one page — hundreds of runners silently dropped."""
    from racing_edge.school import fetch

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": [{"race_id": "1", "runners": []}]}
    monkeypatch.setattr(fetch.requests, "get", lambda *a, **k: _Resp())
    with pytest.raises(ValueError, match="total"):
        fetch.fetch_day("2026-09-01", ("u", "p"))


def test_day_fetched_measures_rows_not_a_file_on_disk(tmp_path) -> None:
    from racing_edge.school.fetch import day_fetched
    f = tmp_path / "2026-09-01.csv"
    assert not day_fetched(f)
    f.write_text("")
    assert not day_fetched(f)                 # an empty file is a failed day
    f.write_text("2026-09-01,1,Ripon,G,F,4,6,1,3.0,1,0,1,1\n")
    assert day_fetched(f)


def test_results_by_date_carries_the_regions_and_raises_on_an_empty_document() -> None:
    """Fetch bot #1/#3: the docstring claimed region filtering that the code
    never passed; a None answer became 'no races today'."""
    from racing_edge.data.client import RacingAPIClient, RacingAPIError
    cfg = NS(api=NS(username="u", password="p", base_url="http://x",
                    regions="gb,ire"))
    c = RacingAPIClient(cfg)
    seen = {}

    def fake_get(path, params=None, allow_404=True):
        seen["params"] = params
        return {"results": []}
    c._get = fake_get
    assert c.results_by_date("2026-09-01") == {"results": []}
    assert ("region_codes", "gb") in seen["params"] and ("region_codes", "ire") in seen["params"]
    c._get = lambda path, params=None, allow_404=True: None
    with pytest.raises(RacingAPIError, match="outage"):
        c.results_by_date("2026-09-01")


def test_load_corpus_counts_the_rows_it_drops(tmp_path, capsys) -> None:
    from racing_edge.school.mine import load_corpus
    (tmp_path / "2026-09-01.csv").write_text(
        "2026-09-01,1,Ripon,G,F,4,6,h1,3.0,1,0,j,t\nbroken,row\n")
    races = load_corpus(tmp_path)
    assert len(races) == 1 and load_corpus.last_skipped == 1
    assert "1 malformed row" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# the memory (rulings) and tier-0
# --------------------------------------------------------------------------- #

def test_rulings_store_verbatim_recall_counted_and_never_consulted_named(tmp_path):
    from racing_edge.study import rulings as R
    p = tmp_path / "rulings.csv"
    a = R.add("hes odds on,", tags="odds-on", day="2026-09-01", path=p)
    R.add("hes odds on,", tags="odds-on", day="2026-09-01", path=p)   # idempotent
    R.add("fix it", tags="law-5c", day="2026-09-01", path=p)
    assert len(R.load(p)) == 2 and a["recalls"] == 0
    with pytest.raises(ValueError):
        R.add("   ", path=p)
    assert {r["ruling"] for r in R.never_consulted(p)} == {"hes odds on,", "fix it"}
    got = R.recall(tags=["odds-on"], path=p)
    assert [r["ruling"] for r in got] == ["hes odds on,"]
    assert R.load(p)[0]["recalls"] == 1 and R.load(p)[1]["recalls"] == 0
    assert [r["ruling"] for r in R.never_consulted(p)] == ["fix it"]
    block = R.render(R.recall(path=p))
    assert "[2026-09-01]" in block and '"fix it"' in block
    assert R.load(p)[0]["recalls"] == 2


def _corpus(tmp_path: Path) -> Path:
    raw = tmp_path / "raw"
    raw.mkdir()
    # two months, one 5-runner race a day for 4 days each month; fav wins some
    rows = []
    n = 0
    for month, days in (("2026-07", (1, 2, 3, 4)), ("2026-08", (1, 2, 3, 4))):
        for dd in days:
            n += 1
            d = f"{month}-{dd:02d}"
            for k, sp in enumerate((2.0, 4.0, 6.0, 10.0, 20.0), 1):
                pos = "1" if k == (1 if dd % 2 else 2) else str(k + 1)
                if k == 5:
                    pos = "0"          # the corpus's UNKNOWN position — never a placing
                rows.append([d, f"r{n}", "Ripon", "G", "F", "4", "6", f"h{k}",
                             f"{sp}", pos, "0", "j", "t"])
            with open(raw / f"{d}.csv", "w", newline="") as fh:
                csv.writer(fh).writerows(r for r in rows if r[0] == d)
    return raw


def test_tier0_scores_every_runner_against_the_market_and_writes_the_report(tmp_path):
    from racing_edge.school import tier0
    from racing_edge.school.mine import featurise, load_corpus
    raw = _corpus(tmp_path)
    rows = tier0.rows_from(featurise(load_corpus(raw), "2026-07-01"))
    assert len(rows) == 8 * 5                       # every runner, every race
    ctl = tier0.control(rows)
    assert ctl[1][0] == 8 and ctl[1][1] == 4          # favs: 8 runs, 4 wins
    assert ctl[2][1] == 4                             # 2nd favs: the other 4
    assert ctl[5][2] == 0                             # rank-5 "0" positions: never placed (bot F)
    out = tmp_path / "tier0.md"
    assert tier0.main(["--day", "2026-08-04", "--raw", str(raw), "--out", str(out),
                       "--score-from", "2026-07-01"]) == 0
    text = out.read_text()
    assert "TIER-0" in text and "THE CONTROL" in text and "| 1 |" in text
    assert tier0.main(["--day", "2026-08-04", "--raw", str(tmp_path / "nowhere"),
                       "--out", str(out)]) == 1     # no corpus: fail loud


# --------------------------------------------------------------------------- #
# second audit (bot D's holes): the branches nobody had reached
# --------------------------------------------------------------------------- #

def test_grade_read_claims_names_a_beaten_danger_and_an_equal_price() -> None:
    from racing_edge.cli.nap import grade_read_claims
    me = NS(horse="Gem", position=2, sp_dec=4.0)
    race = NS(runners=[NS(horse="Win", position=1, sp_dec=3.0), me,
                       NS(horse="Rival", position=5, sp_dec=6.0)])
    g = grade_read_claims({"danger": "Rival", "crossed": "Nobody — slow",
                           "my_price": 4.0}, race, me)
    assert "danger behind us" in g and "crossed-off all beaten" in g
    assert "equal to SP 4.0" in g
    assert grade_read_claims({"danger": "Ghost", "crossed": "", "my_price": None},
                             race, me) == "danger absent"


def test_sweep_backlog_names_a_fetch_failure_and_leaves_the_row_open(tmp_path):
    from racing_edge.cli.nap import _sweep_backlog
    log = _log(tmp_path)
    _bank_all(log, date(2026, 9, 8))

    def fetch(ds):
        raise RuntimeError("api down")
    lines: list[str] = []
    _sweep_backlog(date(2026, 9, 10), log, lines.append, fetch=fetch)
    assert any("results fetch failed (RuntimeError)" in ln for ln in lines)
    assert log.existing(date(2026, 9, 8))["won"] is None


def test_export_text_round_trips_a_shadow_row(tmp_path):
    import csv
    log = _log(tmp_path)
    d = date(2026, 9, 2)
    log.record_shadow(day=d, race_id="r", course="c", horse="Shade", horse_id="s",
                      price=5.0, score=2)
    log.settle_shadow(d, won=True, sp_dec=6.0)
    twin = tmp_path / "twin.csv"
    log.export_text(twin)
    row = next(r for r in csv.DictReader(open(twin)) if r["table"] == "shadow")
    assert row["horse"] == "Shade" and row["won"] == "1" and row["score"] == "2"


def test_month_test_holds_fails_and_thin() -> None:
    from racing_edge.school.tier0 import month_test, place_bar
    holds = {"months": {"2026-07": [40, 10, 6.0], "2026-08": [40, 9, 6.0]}}
    fails = {"months": {"2026-07": [40, 10, 6.0], "2026-08": [40, 3, 6.0]}}
    thin = {"months": {"2026-07": [40, 10, 6.0], "2026-08": [10, 5, 1.0]}}
    assert month_test(holds) == "HOLDS" and month_test(fails) == "FAILS"
    assert month_test(thin) == "THIN"
    assert place_bar(8) == 3 and place_bar(5) == 2 and place_bar(4) == 1


def test_gem_shape_verdict_also_earns_the_bonus() -> None:
    from racing_edge.pipeline.nap import race_quality_score
    kw = dict(is_handicap=True, concentration=0.8, race_class=4, race_type="Flat",
              field_size=6, n_race_flags=0)
    assert race_quality_score(**kw, shape_verdict="GEM BEHIND THE JOLLY — x") == \
        race_quality_score(**kw) + 1


def test_git_stamp_never_crashes_without_git(monkeypatch) -> None:
    import subprocess
    from racing_edge.cli.nap import _git_stamp
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    assert _git_stamp() == ""


def test_rulings_survive_a_corrupt_counts_twin(tmp_path):
    from racing_edge.study import rulings as R
    p = tmp_path / "rulings.csv"
    R.add("fix it", tags="law", day="2026-09-01", path=p)
    R._counts_path(p).write_text("{not json")
    assert R.load(p)[0]["recalls"] == 0
    assert R.recall(path=p)[0]["recalls"] == 1


def test_danger_grading_survives_quotes_case_and_country_suffix() -> None:
    from racing_edge.cli.nap import grade_read_claims, norm_horse_name
    assert norm_horse_name("Yes I’m Mali (IRE)") == "yes i'm mali"
    me = NS(horse="Gem", position=3, sp_dec=4.0)
    race = NS(runners=[NS(horse="Yes I'm Mali", position=1, sp_dec=1.7), me])
    g = grade_read_claims({"danger": "YES I’M MALI (IRE)", "crossed": "", "my_price": None},
                          race, me)
    assert g == "danger WON"


def test_no_tracked_corpus_file_can_collide_with_the_boxs_own_nightly_files() -> None:
    """Second audit (bot C): the box writes data/school/raw/<day>.csv nightly
    from 2026-08-18; a future commit adding a file with one of those names
    would make the box's git pull fail forever. The tracked corpus must end
    before the box's own files begin."""
    import subprocess
    out = subprocess.run(["git", "ls-files", "data/school/raw"], capture_output=True,
                         text=True).stdout.split()
    if not out:
        pytest.skip("no git or no tracked corpus here")
    latest = max(Path(f).stem for f in out)
    assert latest <= "2026-08-14", f"tracked corpus reaches {latest} — the box owns later days"
