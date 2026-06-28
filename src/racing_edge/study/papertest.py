"""Paper test — put the reads in front of the master before they touch a pick.

A read only earns trust by meeting reality. This runs the full study over real,
settled races and lays the verdicts out to be MARKED: did the notebook's rules
hold, and where is the reading still blind? It scores only what can be scored
without circularity — rule #2 (did the 2nd/3rd fav actually win) is a real,
falsifiable check; the manner-downgrade's true test (do nearly-types lose their
NEXT race) needs each runner's prior comments, which the history enrichment owes.

Pure: a studied card in, a markable summary out.
"""

from __future__ import annotations

from dataclasses import dataclass

from racing_edge.study.postmortem import CardStudy


@dataclass(frozen=True)
class ReviewSummary:
    n_races: int
    rule2_held: int          # winner was the 2nd/3rd fav
    rule2_total: int         # races with a ranked winner (the honest denominator)
    open_gaps: int           # grunt work the result data couldn't answer

    @property
    def rule2_pct(self) -> float | None:
        return 100.0 * self.rule2_held / self.rule2_total if self.rule2_total else None


def summarise_review(card: CardStudy) -> ReviewSummary:
    return ReviewSummary(
        n_races=card.n_races,
        rule2_held=card.winner_was_2nd_or_3rd_fav,
        rule2_total=sum(1 for s in card.studies if s.winner_market_rank is not None),
        open_gaps=sum(len(s.gaps) for s in card.studies),
    )
