"""Tests for the daily pipeline — and the franking GATE that stands a pick down.

The method's order is: shortlist readable handicaps -> pick -> FRANK the pick. A
pick whose last form line comes up unfranked (rivals checked, none went on to
win/place) is no bet. This is the grunt work done before the card is published.
"""

from __future__ import annotations

import sys

from racing_edge.pipeline.daily import run_day


class _FrankClient:
    """A card with one pick-able readable handicap. `mode` sets how the pick's
    last-race rivals have fared SINCE: 'franked' (re-ran and placed), 'thin'
    (re-ran and flopped), or 'too_soon' (haven't run again at all)."""

    def __init__(self, mode: str) -> None:
        self.mode = mode

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
        # the field of the pick's most recent prior race (what frank_form looks up)
        return {"results": [{"race_id": "last_OURS", "date": "2025-12-01", "runners": [
            {"horse_id": "OURS"}, {"horse_id": "R1A"}, {"horse_id": "R1B"}]}]}

    def horse_results(self, hid: str, limit: int = 12) -> list[dict]:
        if hid == "OURS":
            return [{"date": "2025-12-01", "race_id": "last_OURS", "position": "1",
                     "class": "3", "going": "Soft", "dist_f": "20.0", "lbs": "154",
                     "course": "Kelso", "ran": "12"}]
        if hid in ("R1A", "R1B"):
            if self.mode == "franked":
                return [{"date": "2026-02-01", "position": "1"}]   # re-ran AND won -> franks
            if self.mode == "thin":
                return [{"date": "2026-02-01", "position": "9"}]   # re-ran but flopped -> thin
        return []                                                 # too_soon: never re-ran

    def trainer_jockeys(self, tid: str) -> list[dict]:
        return []


def test_frank_gate_stands_down_only_genuinely_thin_form() -> None:
    franked = run_day(_FrankClient("franked"), day="today", code="jump").picks[0]
    thin = run_day(_FrankClient("thin"), day="today", code="jump").picks[0]
    too_soon = run_day(_FrankClient("too_soon"), day="today", code="jump").picks[0]
    assert franked.case.runner.horse == thin.case.runner.horse == "Bishopton"

    # solid form -> bet stands, franking recorded
    assert franked.frank is not None and franked.frank.is_franked
    assert franked.bet is not None

    # rivals re-ran and flopped -> genuinely thin -> stood down
    assert thin.frank is not None and thin.frank.is_thin
    assert thin.bet is None

    # rivals haven't run again yet -> "too soon", NOT thin -> NOT vetoed (the bug we fixed)
    assert too_soon.frank is not None
    assert not too_soon.frank.is_thin and not too_soon.frank.is_franked
    assert too_soon.bet is not None


def test_frank_can_be_skipped() -> None:
    # --no-frank path: no franking ran, so nothing is stood down on form grounds
    cp = run_day(_FrankClient("thin"), day="today", code="jump", frank=False).picks[0]
    assert cp.frank is None
    assert cp.bet is not None      # would have been vetoed had franking run


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
