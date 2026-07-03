"""Tests for the contender scorecard — every lens, every contender, owed flagged."""

from __future__ import annotations

import sys
from datetime import date

from racing_edge.domain.models import Odds, PastRun, Race, Runner
from racing_edge.report.scorecard import build_scorecard, render_scorecard
from racing_edge.selection.case import RunnerEvidence


def _race() -> Race:
    return Race(race_id="r", course="Cartmel", off_time="15:50", date=date(2026, 6, 26),
                race_type="Handicap Chase", is_handicap=True, distance_f=25.0, going="Good",
                runners=(
                    Runner(horse_id="w", horse="Caughtinyourtrance", trainer="James Moffatt",
                           official_rating=120, odds=Odds(consensus=1.75)),
                    Runner(horse_id="l", horse="Loch Cuan", trainer="Gordon Elliott",
                           official_rating=118, odds=Odds(consensus=2.5)),
                    Runner(horse_id="o", horse="Outsider", odds=Odds(consensus=12.0)),
                ))


def test_scorecard_reads_every_contender_and_flags_owed() -> None:
    race = _race()
    # the winner is a REPEAT course winner; the raider got off the mark there once
    ev = [
        RunnerEvidence(runner=race.runners[0], stable_runs=10, stable_wins=3, history=(
            PastRun(date=date(2025, 6, 27), position=1, course="Cartmel",
                    going="Good", distance_f=25.0),
            PastRun(date=date(2025, 5, 1), position=1, course="Cartmel",
                    going="Good", distance_f=25.0),
        )),
        RunnerEvidence(runner=race.runners[1], stable_runs=8, stable_wins=1, history=(
            PastRun(date=date(2026, 5, 20), position=1, course="Cartmel",
                    going="Good", distance_f=25.0),
        )),
    ]
    sc = build_scorecard(race, ev, top_n=3)
    assert [c.horse for c in sc.columns] == ["Caughtinyourtrance", "Loch Cuan", "Outsider"]

    def cell(col, lens):
        return dict(sc.columns[col].cells)[lens].text

    # depth of course form is visible side by side: 2W (repeat) vs 1W (one-time)
    assert cell(0, "course") == "2W"
    assert cell(1, "course") == "1W"
    # the local-master tell fires on the winner, not the raider
    assert any("LOCAL MASTER" in t for t in sc.columns[0].tells)
    assert not sc.columns[1].tells or all("LOCAL MASTER" not in t for t in sc.columns[1].tells)

    # the blind spots are OWED, not silently skipped
    owed = "\n".join(sc.owed)
    assert "mark" in owed and "manner" in owed and "mkt-move" in owed
    # the outsider has no evidence -> its course/trip/going are owed, not invented
    assert "Outsider — course" in owed

    out = render_scorecard(sc)
    assert "Caughtinyourtrance" in out and "OWED" in out and "?" in out


def test_manner_lens_is_live_off_the_comments() -> None:
    """The brief printed manner '·?' on every horse all night (2026-07-03) while the
    comments were flowing — the lens was hard-coded OWED from before the door opened.
    Now: finisher/placer/excuse read from history comments; OWED only when truly blank."""
    race = Race(race_id="r", course="Beverley", off_time="19:02", date=date(2026, 7, 3),
                race_type="Flat", is_handicap=True,
                runners=(Runner(horse_id="A", horse="ImNext", official_rating=86,
                                odds=Odds(consensus=3.1)),
                         Runner(horse_id="B", horse="Placer", official_rating=80,
                                odds=Odds(consensus=5.0))))
    ev = [
        RunnerEvidence(runner=race.runners[0], history=(
            PastRun(date=date(2026, 6, 1), position=1,
                    comment="challenged at the last - asserted on the run-in"),)),
        RunnerEvidence(runner=race.runners[1], history=(
            PastRun(date=date(2026, 6, 1), position=2, comment="every chance, found little"),
            PastRun(date=date(2026, 5, 1), position=2, comment="one paced final furlong"),)),
    ]
    sc = build_scorecard(race, ev, top_n=2)

    def cell(col):
        return dict(sc.columns[col].cells)["manner"]

    assert cell(0).text == "FINISHER" and not cell(0).owed
    assert cell(1).text == "placer!" and not cell(1).owed


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
