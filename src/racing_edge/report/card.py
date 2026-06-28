"""The daily card view — the owner's picks with every reason shown. Pure render.

This is the augmentation output: the human reads it and decides. Each race shows
the method's pick, the price, whether it's a value bet (and the stake), and the
full transparent case. No score, no black box — just the reasons, as a clerk
would lay them out for the handicapper.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from racing_edge.ai.narrative import NarrativeRead
from racing_edge.betting.bet import Bet
from racing_edge.domain.models import Race
from racing_edge.domain.units import format_odds
from racing_edge.selection.case import Case
from racing_edge.study.frank import Franking

_RULE = "=" * 70


@dataclass(frozen=True)
class CardPick:
    race: Race
    case: Case
    price: float | None
    bet: Bet | None                          # None = the method's pick, but not a value bet today
    narrative: tuple[NarrativeRead, ...] = ()  # optional AI reads of the comment (advisory, cited)
    frank: Franking | None = None            # the pipeline's franking of the pick's last form line


@dataclass(frozen=True)
class DayCard:
    day: date
    code: str              # "jump" / "flat"
    picks: tuple[CardPick, ...]


def _price_str(price: float | None) -> str:
    return f"{format_odds(price)} ({price:.1f})" if price else "no price"


def render_card(card: DayCard) -> str:
    season = "winter jumps" if card.code == "jump" else card.code
    lines = [
        _RULE,
        f"  YOUR CARD — {season} — {card.day:%a %d %b %Y}",
        f"  {len(card.picks)} race(s) the method has a pick in. You decide.",
        _RULE,
    ]
    if not card.picks:
        lines.append("\n  No picks today — nothing the method stands up. Discipline is a position.")
        return "\n".join(lines)

    for cp in card.picks:
        r, c = cp.race, cp.case
        hcap = "Handicap " if r.is_handicap else ""
        cls = f"Class {r.race_class}" if r.race_class else "?"
        lines.append(
            f"\n  {r.course} {r.off_time}  —  {hcap}{r.race_type} ({cls}, {r.going_band})"
        )
        lines.append(f"    {str(c.runner.horse).upper()}   {_price_str(cp.price)}")
        if c.stance:
            lines.append(f"    [{c.stance}]")
        # franking — shown only when it was used to DECIDE a close call (a real split)
        if cp.frank is not None and cp.frank.note:
            lines.append(f"    frank (tiebreaker): {cp.frank.note}")
        if cp.bet:
            ew = " each-way" if cp.bet.each_way else " win"
            lines.append(f"    >> VALUE BET: £{cp.bet.stake:.2f}{ew} single "
                         "(take the best/early price)")
        elif cp.price is not None:
            lines.append("    (the method's pick, but the price is out of "
                         "the value range — no bet)")
        for reason in c.reasons:
            lines.append(f"       - {reason}")
        if cp.narrative:
            lines.append("    AI read of the comment (verify — never a tip):")
            for nr in cp.narrative:
                lines.append(f"       ~ {nr.note}  [\"{nr.citation}\"]")
    lines.append("\n" + _RULE)
    lines.append("  The method's read. Your eye, your call — overrule any of it.")
    return "\n".join(lines)
