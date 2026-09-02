"""END-TO-END LEARNING LOOP — a simulated three-day run, offline, no model.

Drives NapLog / NuanceLog directly and the PURE functions around them
(cli.nap._settle_tables / _sweep_backlog / _lessons_with_rulings,
study.morningread.build_lessons, study.rulings, school.tier0) the same way
tests/test_audit_fixes.py drives _settle_tables — SimpleNamespace results,
no network, no ANTHROPIC_API_KEY. Proves the record-to-morning-prompt wire
stays intact across bank -> settle -> void -> backlog-sweep, and that a
result never leaks into the memory before it happened (no lookahead).
"""

from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace as NS



def _env(monkeypatch, tmp_path) -> None:
    """Offline sandbox: cwd inside tmp_path (data/rulings.csv etc. resolve
    relative to it) and dummy Racing API creds so get_config() never raises
    if anything on an import path reaches for it — nothing here calls the
    network."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RACING_API_USERNAME", "u")
    monkeypatch.setenv("RACING_API_PASSWORD", "p")


def _settle_tracked_clues(nlog, results) -> int:
    """Mirrors cli.nap._settle()'s tracked-clue loop (the horse-ran-today
    match + settle_tracked call) without the network results fetch."""
    tracked_by_id: dict[str, list] = {}
    for t in nlog.tracked_active():
        if t["horse_id"]:
            tracked_by_id.setdefault(t["horse_id"], []).append(t)
    settled = 0
    for res in results:
        for rr in res.runners:
            for t in tracked_by_id.pop(rr.horse_id, []):
                hit = (rr.position == 1) == (t["angle"] == "follow")
                outcome = f"ran, {'WON' if rr.position == 1 else f'pos {rr.position}'}"
                settled += nlog.settle_tracked(rr.horse_id, outcome=outcome, held=hit)
    return settled


def test_three_day_learning_loop(tmp_path, monkeypatch):
    """Day 1: bank a nap (danger named, crossed list, my_price) + a tracked
    FOLLOW clue; settle with the danger WINNING and the clue's horse WINNING.
    Day 2: bank + settle as a non-runner -> VOID (never a loss, never in the
    strike rate); build_lessons carries Day-1's READ GRADED line forward but
    not Day-2 as a loss; the rulings memory rides in via
    _lessons_with_rulings without dirtying its own CSV. Day 3: bank, leave
    open; a Day-10 backlog sweep VOIDs it with the console command, Day-2
    stays untouched, and the text twin reflects all three days."""
    _env(monkeypatch, tmp_path)
    from racing_edge.cli.nap import _lessons_with_rulings, _settle_tables, _sweep_backlog
    from racing_edge.study import rulings as R
    from racing_edge.study.morningread import build_lessons
    from racing_edge.study.naplog import NapLog
    from racing_edge.study.nuances import NuanceLog

    log = NapLog(tmp_path / "nap.db")
    nlog = NuanceLog(tmp_path / "nuances.db")
    emitted: list[str] = []
    emit = emitted.append

    day1, day2, day3, day10 = (date(2026, 9, 1), date(2026, 9, 2),
                               date(2026, 9, 3), date(2026, 9, 10))

    # ================================================================ DAY 1
    log.record(day=day1, race_id="rac_1", course="Ripon", horse="Nap",
              horse_id="h1", price=4.0, score=3, confident=True,
              case="the jigsaw case joined, forty-plus characters of reasoning here",
              danger="Danger", crossed="Crossed1", my_price=3.5)
    nlog.track(day=day1, race_id="rac_2", horse="Trackee", horse_id="h9",
              angle="follow", note="stormed clear, idles in front",
              conditions="testing ground handicap")

    # --- NO LOOKAHEAD: built on the still-unsettled history, before Day-1
    # even has a result, the exam notes carry nothing about it.
    pre_hist = log.history()
    assert pre_hist[0]["won"] is None and pre_hist[0]["read_grade"] == ""
    pre_lines = build_lessons(pre_hist, log.strike_rate(), nlog.all(), [],
                              nlog.rule_tally())
    assert pre_lines == []
    assert not any("READ GRADED" in ln for ln in pre_lines)
    assert not any("RECENT LOSS" in ln for ln in pre_lines)

    results_day1 = [
        NS(race_id="rac_1", runners=[
            NS(horse_id="h2", horse="Danger", position=1, status="", sp_dec=2.5),
            NS(horse_id="h1", horse="Nap", position=2, status="", sp_dec=4.0),
            NS(horse_id="h3", horse="Crossed1", position=3, status="", sp_dec=6.0),
        ]),
        NS(race_id="rac_2", runners=[
            NS(horse_id="h9", horse="Trackee", position=1, status="", sp_dec=5.0),
            NS(horse_id="h10", horse="Other", position=2, status="", sp_dec=3.0),
        ]),
    ]
    out1 = _settle_tables(day1, results_day1, log, emit)
    assert out1["nap"].startswith("Nap unplaced (2)")
    assert "READ GRADED" in out1["nap"] and "danger WON" in out1["nap"]
    assert log.existing(day1)["won"] == 0                       # beaten by the danger
    assert "danger WON" in log.existing(day1)["read_grade"]

    settled_clues = _settle_tracked_clues(nlog, results_day1)
    assert settled_clues == 1
    trackee = nlog._conn.execute(
        "SELECT status, held FROM tracked WHERE horse_id = 'h9'").fetchone()
    assert trackee["status"] == "done" and trackee["held"] == 1
    board = nlog.clue_scoreboard(since="2020-01-01")
    assert board["follow"] == {"n": 1, "hits": 1, "rate": 1.0}

    # the night's self-critique: a nuance + a rule verdict, banked through the
    # ledger's own APIs
    nlog.record(day=day1, race_id="rac_1", course="Ripon", winner="Danger",
               blind_pick="Nap", nuance="the named danger's recent figures were "
               "the tell and went unweighed", what_missed="danger's in-form "
               "recent figures", cite="race comments", owed="", confidence="high")
    nlog.record_evidence(day=day1, race_id="rac_1", rule="#8",
                         verdict="supports", note="danger named and it won")
    assert len(nlog.all()) == 1 and nlog.all()[0]["status"] == "proposed"
    assert nlog.rule_tally() == [{"rule": "#8", "supports": 1, "contradicts": 0}]

    # ================================================================ DAY 2
    log.record(day=day2, race_id="rac_3", course="Thirsk", horse="NapDay2",
              horse_id="h20", price=3.0, score=2, confident=False)
    results_day2 = [NS(race_id="rac_3", runners=[
        NS(horse_id="h20", horse="NapDay2", position=None, status="", sp_dec=None)])]
    out2 = _settle_tables(day2, results_day2, log, emit)
    assert "VOID" in out2["nap"] and "no position, no status" in out2["nap"]
    assert log.existing(day2)["won"] == NapLog.VOID
    assert log.strike_rate() == (0, 1)          # Day-1's loss only; a void is not a bet

    lines2 = build_lessons(log.history(), log.strike_rate(), nlog.all(), [],
                           nlog.rule_tally())
    assert any(f"READ GRADED {day1.isoformat()} Nap" in ln and "danger WON" in ln
              for ln in lines2)
    assert not any("RECENT LOSS" in ln and day2.isoformat() in ln for ln in lines2)
    assert not any(day2.isoformat() in ln and "NapDay2" in ln and "LOSS" in ln
                  for ln in lines2)

    ruling_text = "the danger must always be named and beaten with a cited fact"
    R.add(ruling_text, tags="law-8", day=day2.isoformat())        # -> data/rulings.csv
    csv_path, json_path = Path("data/rulings.csv"), Path("data/rulings_recalls.json")
    assert csv_path.exists() and not json_path.exists()

    block = _lessons_with_rulings(lines2)
    assert ruling_text in block and "THE MASTER'S RULINGS" in block
    csv_row = next(csv.DictReader(open(csv_path)))
    assert csv_row["recalls"] == "0"                    # the CSV table is never touched
    assert json.loads(json_path.read_text())[ruling_text] == 1   # the recall lives in the twin

    # ================================================================ DAY 3
    log.record(day=day3, race_id="rac_5", course="Ayr", horse="NapDay3",
              horse_id="h30", price=5.0, score=1, confident=False)
    assert log.existing(day3)["won"] is None            # banked, left open

    emitted.clear()
    _sweep_backlog(day10, log, emit, fetch=lambda ds: [])
    day3_void = log.existing(day3)
    assert day3_void["won"] == NapLog.VOID
    assert "--settle 2026-09-03" in day3_void["void_reason"]
    assert any(f"backlog {day3.isoformat()} nap: VOID" in ln for ln in emitted)

    day2_after = log.existing(day2)                     # untouched by the sweep
    assert day2_after["won"] == NapLog.VOID
    assert "no finishing position and no status" in day2_after["void_reason"]
    assert "backlog sweep" not in day2_after["void_reason"]

    twin = tmp_path / "twin.csv"
    n = log.export_text(twin)
    assert n == 3                                        # 3 nap rows, no shadow/favline
    rows = {r["date"]: r for r in csv.DictReader(open(twin)) if r["table"] == "nap"}
    assert set(rows) == {day1.isoformat(), day2.isoformat(), day3.isoformat()}
    assert rows[day1.isoformat()]["won"] == "0"
    assert rows[day2.isoformat()]["won"] == str(NapLog.VOID)
    assert rows[day3.isoformat()]["won"] == str(NapLog.VOID)

    log.close()
    nlog.close()


def test_field_test_themes_promotes_by_record_and_expire_tracked_sweeps_stale(
        tmp_path, monkeypatch):
    """RECORD-BASED promotion (nuances.py:field_test_themes): a theme whose
    settled clues prove out (n>=min_n, hold-rate>=min_rate) promotes its
    'proposed' nuances to 'field-tested' with no model or master involved —
    the record itself is doing the validating. And the 28-day broom
    (expire_tracked) sweeps a clue whose horse never reappeared."""
    _env(monkeypatch, tmp_path)
    from racing_edge.study.nuances import NuanceLog

    nlog = NuanceLog(tmp_path / "nuances.db")
    nlog.record(day=date(2026, 9, 1), race_id="r0", course="X", winner="W",
               blind_pick="B", nuance="course form matters at this track",
               what_missed="", cite="", owed="", confidence="high",
               theme="course_form")
    for i in range(5):
        d = date(2026, 9, 1) + timedelta(days=i)
        nlog.track(day=d, race_id=f"r{i}", horse=f"H{i}", horse_id=f"hh{i}",
                  angle="follow", note="won on the back of course form",
                  conditions="handicap at the course", theme="course_form")
        nlog.settle_tracked(f"hh{i}", outcome="won", held=True)
    promoted = nlog.field_test_themes(min_n=5, min_rate=0.6)
    assert promoted == ["course_form (5/5 clues held)"]
    assert nlog.all()[0]["status"] == "field-tested"

    stale_day = date.today() - timedelta(days=40)
    nlog.track(day=stale_day, race_id="rold", horse="Ghost", horse_id="hg",
              angle="oppose", note="stale clue", conditions="never reappeared")
    assert not any(t["horse"] == "Ghost" for t in nlog.tracked_active())
    swept = nlog.expire_tracked()
    assert swept == 1
    row = nlog._conn.execute(
        "SELECT status, note FROM tracked WHERE horse_id = 'hg'").fetchone()
    assert row["status"] == "done" and "[expired unverified" in row["note"]
    nlog.close()


def test_tier0_month_test_traits_fails_and_holds() -> None:
    """school.tier0.traits/month_test on a synthetic rows list: a trait with
    +lift in one month and -lift in another (both n>=30) FAILS the month
    test; +lift in both qualifying months HOLDS it."""
    from racing_edge.school.tier0 import control, month_test, traits

    def mk(feat, month, wins, losses):
        rows = [{"rank": 1, "won": True, "placed": False, "month": month,
                "feats": [feat]} for _ in range(wins)]
        rows += [{"rank": 1, "won": False, "placed": False, "month": month,
                 "feats": [feat]} for _ in range(losses)]
        return rows

    rows = (mk("mixed_sign", "2026-07", 20, 10)       # this month: well above the pack
           + mk("mixed_sign", "2026-08", 5, 25)       # this month: well below it
           + mk("steady_plus", "2026-09", 20, 10)     # above the pack both months
           + mk("steady_plus", "2026-10", 20, 10))
    base = control(rows)
    t = traits(rows, base)
    assert month_test(t["mixed_sign"]) == "FAILS"
    assert month_test(t["steady_plus"]) == "HOLDS"


def test_learn_show_and_promote_need_no_model(tmp_path, monkeypatch, capsys):
    """cli.learn's --show / --promote / --bin / --rules / --tracked paths are
    pure NuanceLog reads/mutations — they never touch get_reasoner, so they
    work with NO ANTHROPIC_API_KEY at all. Only the --day self-study path
    (and --synthesise) need the model; that path is not exercised here."""
    _env(monkeypatch, tmp_path)
    monkeypatch.setenv("PROJECT_DIR", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from racing_edge.config import get_config
    get_config.cache_clear()
    try:
        from racing_edge.cli import learn
        from racing_edge.cli._common import open_nuance_log

        nlog = open_nuance_log()
        nlog.record(day=date(2026, 9, 1), race_id="r1", course="X", winner="W",
                   blind_pick="B", nuance="a testable nuance", what_missed="",
                   cite="", owed="", confidence="high")
        nlog.close()

        monkeypatch.setattr("sys.argv", ["learn", "--show"])
        assert learn.main() == 0
        assert "a testable nuance" in capsys.readouterr().out

        monkeypatch.setattr("sys.argv", ["learn", "--promote", "1"])
        assert learn.main() == 0
        assert "PROMOTED" in capsys.readouterr().out
    finally:
        get_config.cache_clear()
