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
