"""Tests for the investigator's evidence tools — grounded lookups, no look-ahead."""

from __future__ import annotations

import sys
from datetime import date

from racing_edge.domain.models import Race
from racing_edge.study.investigate import TOOLS, make_executor


class _FakeClient:
    def horse_results(self, horse_id, limit=12):
        return [
            {"date": "2026-07-01", "race_id": "TODAY", "runners": [       # today — leak
                {"horse_id": horse_id, "position": "1", "or": "90"}]},
            {"date": "2026-06-03", "race_id": "rw1", "course": "Warwick",
             "runners": [{"horse_id": horse_id, "position": "1", "or": "85",
                          "comment": "asserted on the run-in"}]},
        ]

    def result_by_id(self, race_id):
        if race_id != "rw1":
            return None
        return {"runners": [
            {"position": "2", "horse": "Beaten Rival", "horse_id": "BR1",
             "sp_dec": "4.0", "comment": "kept on"},
            {"position": "1", "horse": "Knightsbridge", "horse_id": "KB1",
             "sp_dec": "3.5", "comment": "asserted on the run-in"},
        ]}


def _race() -> Race:
    return Race(race_id="r", course="Worcester", off_time="1:50",
                date=date(2026, 7, 1), race_type="Chase", is_handicap=True)


def test_horse_runs_cuts_history_before_the_race_no_lookahead() -> None:
    ex = make_executor(_FakeClient(), _race())
    out = ex("horse_runs", {"horse_id": "KB1"})
    assert "asserted on the run-in" in out and "race_id=rw1" in out
    assert "TODAY" not in out                       # today's run excluded


def test_race_result_franks_the_form_with_chainable_ids() -> None:
    ex = make_executor(_FakeClient(), _race())
    out = ex("race_result", {"race_id": "rw1"})
    assert out.index("Knightsbridge") < out.index("Beaten Rival")   # finishing order
    assert "id=BR1" in out                          # the thread can be chained
    assert "OWED" in ex("race_result", {"race_id": "nope"})


def test_executor_never_raises_and_tools_are_well_formed() -> None:
    ex = make_executor(_FakeClient(), _race())
    assert "Unknown tool" in ex("bogus", {})
    assert ex("horse_runs", {}) is not None         # missing arg -> handled, not raised
    names = {t["name"] for t in TOOLS}
    # trainer_angle joined 2026-07-26 (the master: a trainer's amazing strike with
    # today's TYPE of horse — e.g. his 4yo chasers — is a HUGE tick; the digger can
    # now ask that exact question mid-read)
    assert names == {"horse_runs", "race_result", "trainer_angle"}
    assert "OWED" in ex("trainer_angle", {"trainer_id": "trn_x"})  # fake client: honest empty
    for t in TOOLS:
        assert t["input_schema"]["required"]        # schemas declare their args


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
