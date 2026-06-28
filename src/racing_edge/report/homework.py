"""Render the homework report — the forensic read of the studied races, in plain
text a handicapper reads. Pure: a HomeworkReport in, a string out.
"""

from __future__ import annotations

from racing_edge.study.homework import HomeworkReport

_RULE = "=" * 70


def _pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f}%" if d else "—"


def _dist(counts: dict[str, int], total: int, order: list[str] | None = None) -> list[str]:
    keys = order or sorted(counts, key=lambda k: -counts[k])
    return [f"      {k:<28} {counts.get(k, 0):>4}  ({_pct(counts.get(k, 0), total)})"
            for k in keys if counts.get(k, 0) or order]


def render_homework(rep: HomeworkReport) -> str:
    lines = [
        _RULE,
        f"  HOMEWORK — forensic read of {rep.n_races} studied race(s)",
        "  DIRECTIONAL until the sample is large — leads to test, not proven edges.",
        _RULE,
        "",
        f"  Where winners came from in the market ({rep.n_ranked} priced):",
        *_dist(rep.rank_counts, rep.n_ranked, ["fav", "2nd fav", "3rd fav", "4th+"]),
        f"      -> rule #2 (2nd/3rd fav won): {rep.rule2_hits}/{rep.n_ranked} "
        f"({_pct(rep.rule2_hits, rep.n_ranked)})",
        "",
        "  How the winner finished (manner):",
        *_dist(rep.winner_manner, rep.n_races),
        "",
        "  Clues that showed on the winner (which legwork actually points right):",
        *_dist(rep.clue_hits, rep.n_races, [label for label in rep.clue_hits]),
        "",
        "  Franking verdict on winners (is the legwork separating them?):",
        *_dist(rep.frank_among_winners, rep.n_races,
               ["FRANKED", "thin", "too soon", "not checked"]),
        "",
        f"  Our picks: {rep.our_wins}/{rep.our_n} won ({_pct(rep.our_wins, rep.our_n)}), "
        f"{rep.our_places}/{rep.our_n} placed ({_pct(rep.our_places, rep.our_n)})",
        "  When our pick LOST, how it ran (the 'nearly type' check):",
        *_dist(rep.our_loss_manner, max(rep.our_n - rep.our_wins, 1)),
        "",
        _RULE,
        "  Read these as questions for the notebook, not answers. Small samples lie.",
    ]
    return "\n".join(lines)
