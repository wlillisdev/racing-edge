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
from racing_edge.selection.select import pick_race
from racing_edge.study.frank import frank_form


class _Client:
    def racecards(self, day: str = "today") -> dict: ...
    def results_by_date(self, date_str: str) -> dict: ...
    def horse_results(self, horse_id: str, limit: int = 12) -> list[dict]: ...
    def trainer_jockeys(self, trainer_id: str) -> list[dict]: ...


def run_day(client: _Client, policy: BettingPolicy | None = None,
            day: str = "today", code: str = "jump", frank: bool = True) -> DayCard:
    """Fetch the day's card, keep the chosen code (jumps by default), and produce
    one transparent pick per race the method stands up in.

    The pipeline order is the method itself: SHORTLIST the readable handicaps,
    PICK one runner per race, then FRANK that pick's last form line. A pick whose
    last race comes up UNFRANKED (we checked the rivals and they haven't gone on
    to win/place) is stood DOWN — the form doesn't stack up, so it's no bet. This
    is the grunt work done before the card is published, not after the race."""
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
        price = case.runner.odds.consensus
        bet = make_bet(case, price, policy)
        # FRANK THE PICK — frank the form it brings in before backing it. Only veto
        # when franking actually RAN and came up thin; a missing/unfindable last
        # race can't be held against it (don't penalise absent data).
        franking = None
        if frank:
            hist = past_runs_from_raw(client.horse_results(case.runner.horse_id),
                                      case.runner.horse_id)
            franking = frank_form(client, case.runner.horse_id, hist)
            if franking.rivals_checked > 0 and not franking.is_franked:
                bet = None       # checked and thin — stand the bet down, the form is hollow
        narrative = tuple(read_narrative(case.runner, completer)) if completer else ()
        picks.append(CardPick(race=race, case=case, price=price,
                              bet=bet, narrative=narrative, frank=franking))

    card_date = races[0].date if races else date.today()
    return DayCard(day=card_date, code=code, picks=tuple(picks))
