"""The daily run — one in-process flow: fetch the card, apply the method, build
the day's picks. Jumps-first (winter focus). No subprocesses, no JSON hand-offs.
"""

from __future__ import annotations

from datetime import date

from racing_edge.ai.llm import get_completer
from racing_edge.ai.narrative import read_narrative
from racing_edge.betting.bet import make_bet
from racing_edge.betting.policy import BettingPolicy
from racing_edge.data.evidence import build_evidence
from racing_edge.data.normalise import past_runs_from_raw, racecards_from_raw
from racing_edge.report.card import CardPick, DayCard
from racing_edge.selection.case import Case
from racing_edge.selection.select import pick_race
from racing_edge.study.frank import Franking, frank_form

# A contender within this fraction of the leader's score is "close" — a real split
# where franking earns its keep. A clear leader needs no tiebreaker.
_CLOSE = 0.85


class _Client:
    def racecards(self, day: str = "today") -> dict: ...
    def results_by_date(self, date_str: str) -> dict: ...
    def horse_results(self, horse_id: str, limit: int = 12) -> list[dict]: ...
    def trainer_jockeys(self, trainer_id: str) -> list[dict]: ...


def frank_tiebreak(client: _Client, ranked: tuple[Case, ...],
                   cap: int = 3) -> tuple[Case, Franking | None]:
    """Franking is a within-race DECIDER, used ONLY when the top contenders are
    close — exactly how the master uses it: narrow the race to a few, then let the
    franked form break the tie. It NEVER vetoes and NEVER removes a horse.

    If there's a clear leader (no rival within `_CLOSE` of its score), franking has
    nothing to decide → return the leader, no franking. Otherwise frank the close
    group and prefer the highest-scored horse whose form is FRANKED. If none is
    franked (common early-season, when little form has been franked yet), the
    top-scored horse stands — franking simply had no say."""
    leader = ranked[0]
    close = [c for c in ranked[:cap] if c.score >= leader.score * _CLOSE]
    if len(close) < 2:
        return leader, None                  # not a split — nothing for franking to decide
    pairs: list[tuple[Case, Franking]] = []
    for c in close:
        hist = past_runs_from_raw(client.horse_results(c.runner.horse_id), c.runner.horse_id)
        pairs.append((c, frank_form(client, c.runner.horse_id, hist)))
    for c, f in pairs:                        # pairs are score-sorted; first franked wins the tie
        if f.is_franked:
            return c, f
    return pairs[0][0], pairs[0][1]           # none franked — leader stands, show its read


def run_day(client: _Client, policy: BettingPolicy | None = None,
            day: str = "today", code: str = "jump", frank: bool = True) -> DayCard:
    """Fetch the day's card, keep the chosen code (jumps by default), and produce
    one transparent pick per race the method stands up in.

    SHORTLIST the readable handicaps, RANK each field, then — only when the top
    contenders are close — let FRANKING break the tie between them. Franking is a
    decider between a few, never a filter on the card and never a veto."""
    policy = policy or BettingPolicy()
    completer = get_completer()              # None without ANTHROPIC_API_KEY -> no AI reads
    # RACE SELECTION FIRST: only readable handicaps — never a novice/maiden/bumper,
    # where the form doesn't stack up. The gate that stops a NAP out of a lottery.
    races = [r for r in racecards_from_raw(client.racecards(day))
             if r.code == code and r.is_readable_handicap]

    picks: list[CardPick] = []
    for race in races:
        result = pick_race(race, build_evidence(race, client))
        if not result.is_bet or result.pick is None:
            continue
        case = result.pick
        franking = None
        if frank and len(result.ranked) >= 2:
            case, franking = frank_tiebreak(client, result.ranked)
        price = case.runner.odds.consensus
        narrative = tuple(read_narrative(case.runner, completer)) if completer else ()
        picks.append(CardPick(race=race, case=case, price=price,
                              bet=make_bet(case, price, policy), narrative=narrative,
                              frank=franking))

    card_date = races[0].date if races else date.today()
    return DayCard(day=card_date, code=code, picks=tuple(picks))
