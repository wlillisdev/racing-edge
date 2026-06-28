"""Tests for the homework miner — does it read winners/clues/our-picks correctly?"""

from __future__ import annotations

import sys

from racing_edge.report.homework import render_homework
from racing_edge.study.homework import analyse_homework


def _row(rank, manner="finisher", lessons="", our=None, our_pos=None, our_manner="neutral"):
    return {"winner_market_rank": rank, "winner_manner": manner, "lessons": lessons,
            "our_pick": our, "our_pick_pos": our_pos, "our_pick_manner": our_manner}


def test_analyse_homework_aggregates() -> None:
    rows = [
        _row(1, lessons="  market: BACKED into it — the money knew\n  course: a course winner",
             our="A", our_pos=1),
        _row(2, lessons="  frank: 2026-05-01 race FRANKED: 3/3", our="B", our_pos=3,
             our_manner="non_finisher"),
        _row(2, lessons="  frank: 2026-05-01 race thin: 1/5\n  yard: trainer in form",
             our="C", our_pos=4, our_manner="non_finisher"),
        _row(None, manner="non_finisher", lessons="too soon to frank"),   # unpriced winner
    ]
    rep = analyse_homework(rows)
    assert rep.n_races == 4 and rep.n_ranked == 3
    assert rep.rank_counts == {"fav": 1, "2nd fav": 2, "3rd fav": 0, "4th+": 0}
    assert rep.rule2_hits == 2                                   # two 2nd-favs
    assert rep.clue_hits["market backed (the money knew)"] == 1
    assert rep.clue_hits["course winner"] == 1
    assert rep.clue_hits["trainer in form"] == 1
    assert rep.frank_among_winners["FRANKED"] == 1
    assert rep.frank_among_winners["thin"] == 1
    assert rep.frank_among_winners["too soon"] == 1
    assert rep.our_n == 3 and rep.our_wins == 1 and rep.our_places == 2
    # two losing picks, both non-finishers (the 'nearly type' fault)
    assert rep.our_loss_manner["non_finisher"] == 2
    assert "HOMEWORK" in render_homework(rep)


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
