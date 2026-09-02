"""THE RECORD — write-point guards, voids, the backlog, the text twin.

Audit 2026-09-02 (the master: "is every gate on money enforced at the write
point or only in a caller"; "non-runners voided automatically, voids with a
mandatory reason"; "no pick open over two days without a named cause"; "if
there is no text twin, build one"). Every test here runs the behaviour and
fails when the bug is put back — none greps the source.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from racing_edge.study.naplog import NapLog


def _log(tmp_path: Path) -> NapLog:
    return NapLog(tmp_path / "nap.db")


def _bank(log: NapLog, d: date, horse: str = "Gem", **kw) -> None:
    log.record(day=d, race_id="rac_1", course="Ripon", horse=horse, horse_id="h1",
               price=3.0, score=3, confident=True, **kw)


def test_record_refuses_a_second_bank_for_the_day_unless_forced(tmp_path):
    """The pre-off record is sacred AT THE WRITE POINT: a second record() for a
    banked day raises; only force=True (the --force-rebank caller) may re-pick.
    Put the bug back (drop the guard in NapLog.record) and this fails."""
    log = _log(tmp_path)
    d = date(2026, 9, 2)
    _bank(log, d, "Gem")
    with pytest.raises(ValueError, match="already carries a banked row"):
        _bank(log, d, "Other")
    assert log.existing(d)["horse"] == "Gem"          # untouched
    _bank(log, d, "Other", force=True)                 # the one legal override
    assert log.existing(d)["horse"] == "Other"


def test_a_settled_result_can_never_be_erased_by_rebanking_or_passing(tmp_path):
    """--force-rebank used to fall through to INSERT OR REPLACE with won=NULL —
    a settled outcome silently reset. Now a settled row refuses both record()
    (even forced) and record_pass()."""
    log = _log(tmp_path)
    d = date(2026, 9, 2)
    _bank(log, d)
    log.settle(d, won=True, sp_dec=4.0)
    with pytest.raises(ValueError, match="SETTLED"):
        _bank(log, d, "Other", force=True)
    with pytest.raises(ValueError, match="SETTLED"):
        log.record_pass(day=d, reason="late pass")
    assert log.existing(d)["won"] == 1 and log.existing(d)["sp_dec"] == 4.0


def test_void_needs_a_reason_and_never_touches_a_settled_bet(tmp_path):
    log = _log(tmp_path)
    d = date(2026, 9, 2)
    _bank(log, d)
    with pytest.raises(ValueError, match="reason"):
        log.void(d, "   ")
    log.void(d, "non-runner (NR)")
    row = log.existing(d)
    assert row["won"] == NapLog.VOID and row["void_reason"] == "non-runner (NR)"
    # a void is not a bet: the strike rate and P/L ignore it
    assert log.strike_rate() == (0, 0)
    assert log.profit_loss() == (0.0, 0)
    # a settled bet is never voided
    d2 = date(2026, 9, 3)
    _bank(log, d2)
    log.settle(d2, won=False, sp_dec=None)
    with pytest.raises(ValueError, match="never voided"):
        log.void(d2, "changed my mind")


def test_void_reaches_shadow_and_favline_with_the_same_rules(tmp_path):
    log = _log(tmp_path)
    d = date(2026, 9, 2)
    log.record_shadow(day=d, race_id="r", course="c", horse="S", horse_id="s", price=2.0,
                      score=2)
    log.record_favline(day=d, race_id="r", course="c", horse="F", horse_id="f", price=1.5)
    log.void(d, "abandoned meeting", table="shadow")
    log.void(d, "abandoned meeting", table="favline")
    assert log.pending_shadow() == [] and log.pending_favline() == []
    with pytest.raises(ValueError, match="unknown table"):
        log.void(d, "x", table="opinions")


def test_pending_all_lists_every_open_row_oldest_first(tmp_path):
    """The settle backlog: every unsettled row in every table — the sweep's
    worklist (the old --settle today never revisited a missed day)."""
    log = _log(tmp_path)
    _bank(log, date(2026, 9, 1))
    _bank(log, date(2026, 8, 30))
    log.settle(date(2026, 8, 30), won=False)
    _bank(log, date(2026, 8, 28))
    log.record_favline(day=date(2026, 8, 29), race_id="r", course="c", horse="F",
                       horse_id="f", price=2.0)
    p = log.pending_all()
    assert [r["date"] for r in p["nap"]] == ["2026-08-28", "2026-09-01"]
    assert [r["date"] for r in p["favline"]] == ["2026-08-29"]
    assert p["shadow"] == []


def test_export_text_writes_the_whole_book_as_one_csv(tmp_path):
    """The text twin: every table, every row, rewritten whole; a void's reason
    and a settled SP survive the round trip."""
    import csv
    log = _log(tmp_path)
    d = date(2026, 9, 2)
    _bank(log, d)
    log.settle(d, won=True, sp_dec=3.5)
    log.record_favline(day=d, race_id="rac_1", course="Ripon", horse="F", horse_id="f",
                       price=1.5)
    log.void(d, "fav withdrawn", table="favline")
    twin = tmp_path / "nap_record.csv"
    assert log.export_text(twin) == 2
    rows = list(csv.DictReader(open(twin)))
    nap = next(r for r in rows if r["table"] == "nap")
    fav = next(r for r in rows if r["table"] == "favline")
    assert nap["horse"] == "Gem" and nap["won"] == "1" and nap["sp_dec"] == "3.5"
    assert fav["won"] == str(NapLog.VOID) and fav["void_reason"] == "fav withdrawn"


def test_a_read_without_a_case_is_not_a_read() -> None:
    """Audit 2026-09-02 (reads bot #1): an empty "case" passed MorningPick.ok and
    banked as the argued jigsaw. Now a case needs words; a pass still needs only
    its reason."""
    import json
    from racing_edge.study.morningread import parse_morning_pick
    base = {"race": "Ripon 3:40", "horse": "Gem", "profile_match": {"note": "fits"},
            "danger": {"horse": "Rival", "its_case": "in form", "beaten_because": "13lb"},
            "confidence": "lean", "pass": False, "my_price": "3/1"}
    assert not parse_morning_pick(json.dumps({**base, "case": ""})).ok
    assert not parse_morning_pick(json.dumps({**base, "case": "good horse"})).ok
    full = parse_morning_pick(json.dumps({**base, "case": "x" * 60}))
    assert full.ok and full.my_price == 4.0
    assert parse_morning_pick(json.dumps({**base, "my_price": "nonsense",
                                          "case": "x" * 60})).my_price is None
    assert parse_morning_pick(json.dumps({"pass": True, "pass_reason": "all dreck"})).ok


def test_the_reads_claims_are_banked_and_graded_at_settle(tmp_path):
    """The master: 'the edge is joining the dots' — so every dot the read joins
    is marked: the named danger, the crossed-off list, the reader's own price."""
    from types import SimpleNamespace as NS
    from racing_edge.cli.nap import _settle_tables, grade_read_claims
    log = _log(tmp_path)
    d = date(2026, 9, 2)
    log.record(day=d, race_id="rac_1", course="Ripon", horse="Gem", horse_id="h1",
               price=3.0, score=3, confident=False, danger="Rival",
               crossed="Plodder — no win in 20|Faller — manner placer", my_price=2.5)
    row = log.existing(d)
    assert row["danger"] == "Rival" and row["my_price"] == 2.5
    race = NS(race_id="rac_1", runners=[
        NS(horse="Plodder", horse_id="h9", position=1, status="", sp_dec=12.0),
        NS(horse="Rival", horse_id="h2", position=2, status="", sp_dec=2.0),
        NS(horse="Gem", horse_id="h1", position=3, status="", sp_dec=4.0),
    ])
    out = _settle_tables(d, [race], log, lambda s: None)
    g = log.existing(d)["read_grade"]
    assert "danger beat us (2 v 3)" in g
    assert "winner was CROSSED OFF" in g
    assert "my price 2.5 shorter than SP 4.0" in g
    assert "READ GRADED" in out["nap"]
    sb = log.read_grades()
    assert sb == {"graded": 1, "danger_won": 0, "danger_beat_us": 1,
                  "winner_crossed_off": 1, "price_shorter_than_sp": 1}
    # a pure grade with the danger winning and nothing crossed
    me = NS(horse="Gem", position=4, sp_dec=3.0)
    r2 = NS(runners=[NS(horse="Rival", position=1, sp_dec=2.0), me])
    assert grade_read_claims({"danger": "rival", "crossed": "", "my_price": None},
                             r2, me) == "danger WON"


def test_a_pass_never_overwrites_a_pending_pick_without_force(tmp_path):
    """Second audit (bot A): record_pass could INSERT OR REPLACE a pending real
    pick away. Now it refuses unless forced; a pass on an empty day still banks."""
    log = _log(tmp_path)
    d = date(2026, 9, 2)
    _bank(log, d)
    with pytest.raises(ValueError, match="already carries a banked pick"):
        log.record_pass(day=d, reason="late cold feet")
    assert log.existing(d)["horse"] == "Gem"
    log.record_pass(day=date(2026, 9, 3), reason="nothing readable")
    assert log.existing(date(2026, 9, 3))["won"] == NapLog.PASS
    log.record_pass(day=d, reason="forced", force=True)
    assert log.existing(d)["race_id"] == "PASS"


def test_a_null_position_with_no_status_voids_through_the_real_normaliser(tmp_path):
    """Second audit (bot B): the API can mark a withdrawn horse with position
    null and NO status string; that fell through to 'unplaced' (a loss). Fed
    through results_from_raw end to end, it now voids."""
    from racing_edge.cli.nap import _settle_tables
    from racing_edge.data.normalise import results_from_raw
    log = _log(tmp_path)
    d = date(2026, 9, 2)
    _bank(log, d)
    results = results_from_raw({"results": [{
        "race_id": "rac_1", "date": "2026-09-02", "course": "Ripon",
        "runners": [{"horse_id": "h1", "horse": "Gem", "position": None, "sp_dec": None},
                    {"horse_id": "h2", "horse": "Win", "position": "1", "sp_dec": "3.0"}]}]})
    out = _settle_tables(d, results, log, lambda s: None)
    assert "VOID" in out["nap"] and log.existing(d)["won"] == NapLog.VOID
    # a genuine faller still loses through the same normaliser
    log2_dir = tmp_path / "f"; log2_dir.mkdir()
    log2 = _log(log2_dir)
    _bank(log2, d)
    results = results_from_raw({"results": [{
        "race_id": "rac_1", "date": "2026-09-02", "course": "Ripon",
        "runners": [{"horse_id": "h1", "horse": "Gem", "position": "F", "sp_dec": "3.0"},
                    {"horse_id": "h2", "horse": "Win", "position": "1", "sp_dec": "3.0"}]}]})
    _settle_tables(d, results, log2, lambda s: None)
    assert log2.existing(d)["won"] == 0


def test_settle_is_write_once_at_the_write_point(tmp_path):
    log = _log(tmp_path)
    d = date(2026, 9, 2)
    _bank(log, d)
    log.settle(d, won=True, sp_dec=3.0)
    with pytest.raises(ValueError, match="never edited"):
        log.settle(d, won=False, sp_dec=None)
    assert log.existing(d)["won"] == 1


def test_the_reads_own_grades_reach_the_next_mornings_lessons() -> None:
    """Third audit (bot P3): read_grade was written at settle and consulted by
    nobody but health. The morning lessons now carry the last graded reads."""
    from racing_edge.study.morningread import build_lessons
    hist = [{"date": "2026-09-01", "horse": "Mr Cool", "course": "Brighton", "won": 0,
             "race_id": "r1", "read_grade": "danger WON; my price 4.0 longer than SP 3.0"},
            {"date": "2026-09-02", "horse": "Open", "course": "Bath", "won": None,
             "race_id": "r2", "read_grade": ""}]
    lines = build_lessons(hist, (0, 1), [], [], [])
    assert any("READ GRADED 2026-09-01 Mr Cool: danger WON" in ln for ln in lines)
    assert not any("Open" in ln and "READ GRADED" in ln for ln in lines)


def test_objection_watch_counts_the_readers_recorded_doubts(tmp_path) -> None:
    """Bot B5 (fourth audit): the old veto_watch matched 'reader veto%' — a
    prefix no writer has produced since the 2026-08-19 law; the health line
    was always zero. The objection watch reads the real case text and judges
    the doubt by the result."""
    from datetime import date, timedelta
    from racing_edge.study.naplog import NapLog
    log = NapLog(tmp_path / "nap.db")
    d1 = (date.today() - timedelta(days=1)).isoformat()
    d2 = (date.today() - timedelta(days=2)).isoformat()
    d3 = (date.today() - timedelta(days=3)).isoformat()
    for d, txt in ((d1, "  READER OBJECTION (2026-08-19 law: ...):\n    doubt"),
                   (d2, "  READER OBJECTION (2026-08-19 law: ...):\n    doubt"),
                   (d3, "engine pick: conviction 3 — clean")):
        log.record(day=date.fromisoformat(d), race_id=f"R{d}", course="Bath",
                   horse=f"Horse {d}", horse_id=f"H{d}", price=4.0, score=3,
                   confident=False, case=txt)
    log.settle(date.fromisoformat(d1), won=True, sp_dec=4.0)
    log.settle(date.fromisoformat(d2), won=False, sp_dec=4.0)
    log.settle(date.fromisoformat(d3), won=True, sp_dec=4.0)
    assert log.objection_watch(days=7) == (2, 1, 1)
    assert not hasattr(log, "veto_watch")
