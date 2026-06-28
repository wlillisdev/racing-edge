"""Tests for the daily pipeline and franking as a WITHIN-RACE tiebreaker.

The lesson the master drilled in: franking is not a card-wide filter and never a
veto. It's the decider when the top contenders are CLOSE — narrow the race to a
few, then let the franked form break the tie. A clear leader needs no franking;
an unfranked-but-top-scored horse is still backed (early-season, little has been
franked yet — that's the calendar, not a mark against the horse).
"""

from __future__ import annotations

import sys

from racing_edge.domain.models import Odds, Runner
from racing_edge.pipeline.daily import frank_tiebreak, run_day
from racing_edge.selection.case import Case


def _case(hid: str, score: float) -> Case:
    return Case(runner=Runner(horse_id=hid, horse=hid.upper(), odds=Odds(consensus=4.0)),
                signals=(), score=score, vetoed=False)


class _C:
    """Drives frank_form: R's last race franks (rivals re-ran and placed); L's and
    M's are 'too soon' (their rivals haven't run again)."""

    def horse_results(self, hid: str, limit: int = 12) -> list[dict]:
        return {
            "L": [{"date": "2026-06-21", "race_id": "last_L", "position": "1"}],
            "M": [{"date": "2026-06-20", "race_id": "last_M", "position": "1"}],
            "R": [{"date": "2026-05-01", "race_id": "last_R", "position": "1"}],
            "RA": [{"date": "2026-06-01", "position": "1"}],   # re-ran AND won -> franks
            "RB": [{"date": "2026-06-02", "position": "2"}],   # re-ran AND placed -> franks
        }.get(hid, [])                                          # LA/LB/MA/MB -> [] (too soon)

    def results_by_date(self, ds: str) -> dict:
        fields = {
            "2026-06-21": ("last_L", ["L", "LA", "LB"]),
            "2026-06-20": ("last_M", ["M", "MA", "MB"]),
            "2026-05-01": ("last_R", ["R", "RA", "RB"]),
        }
        if ds in fields:
            rid, ids = fields[ds]
            return {"results": [{"race_id": rid, "date": ds,
                                 "runners": [{"horse_id": h} for h in ids]}]}
        return {"results": []}


def test_franking_breaks_a_close_tie_toward_the_franked_horse() -> None:
    # leader L (10) vs rival R (9) — close (9 >= 10*0.85); R is franked, L too-soon
    chosen, f = frank_tiebreak(_C(), (_case("L", 10.0), _case("R", 9.0)))
    assert chosen.runner.horse_id == "R"       # the franked form wins the split
    assert f is not None and f.is_franked


def test_clear_leader_needs_no_franking() -> None:
    # rival far below threshold (5 < 10*0.85) -> not a split -> franking has no say
    chosen, f = frank_tiebreak(_C(), (_case("L", 10.0), _case("R", 5.0)))
    assert chosen.runner.horse_id == "L" and f is None


def test_close_but_none_franked_keeps_the_top_scored_horse() -> None:
    # both too-soon (early season) -> leader stands, but its read is still shown
    chosen, f = frank_tiebreak(_C(), (_case("L", 10.0), _case("M", 9.0)))
    assert chosen.runner.horse_id == "L"
    assert f is not None and not f.is_franked   # no veto — it just couldn't decide


class _CardClient:
    """One readable handicap; the pick's form is 'too soon' to frank. Proves the
    pipeline still backs it — franking never kills a bet."""

    def racecards(self, day: str = "today") -> dict:
        return {"racecards": [{
            "race_id": "R1", "course": "Kelso", "off_time": "14:40",
            "race_name": "Handicap Chase", "type": "Chase", "class": "3",
            "distance_f": "20.0", "going": "Soft", "date": "2026-06-28", "runners": [
                {"horse_id": "FAV", "horse": "Jolly", "trainer_id": "T2", "jockey_id": "Z",
                 "lbs": "160", "form": "11", "odds": [{"decimal": "2.0"}]},
                {"horse_id": "OURS", "horse": "Bishopton", "trainer_id": "T1", "jockey_id": "A",
                 "lbs": "150", "form": "2311", "odds": [{"decimal": "5.0"}]},
            ]}]}

    def results_by_date(self, ds: str) -> dict:
        return {"results": [{"race_id": "last_OURS", "date": "2026-06-21", "runners": [
            {"horse_id": "OURS"}, {"horse_id": "X1"}, {"horse_id": "X2"}]}]}

    def horse_results(self, hid: str, limit: int = 12) -> list[dict]:
        if hid == "OURS":
            return [{"date": "2026-06-21", "race_id": "last_OURS", "position": "1",
                     "class": "3", "going": "Soft", "dist_f": "20.0", "lbs": "154",
                     "course": "Kelso", "ran": "12"}]
        return []                                  # rivals haven't re-run -> too soon

    def trainer_jockeys(self, tid: str) -> list[dict]:
        return []


def test_pipeline_never_vetoes_on_franking() -> None:
    cp = run_day(_CardClient(), day="today", code="jump").picks[0]
    assert cp.bet is not None       # unfranked / too-soon form is NOT stood down


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
