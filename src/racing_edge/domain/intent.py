"""Intent / angle reads — the signals that need data beyond the bare racecard.

The owner's lines:
  • "the form of the STABLE is critical — an in-form yard is a big plus."
  • "first-time headgear should be a positive."
  • "has the form been FRANKED — did the rivals go on to win?"

These are pure functions of inputs the data layer supplies (trainer form, the
runner's headgear flag, a collateral-form franked count). Jockey-intent (the
stable jockey on the 2nd string) and the market read (winners go short) land
here next, once the data feeds are wired.
"""

from __future__ import annotations

from racing_edge.domain.models import Odds, Race, Runner
from racing_edge.domain.signal import Signal
from racing_edge.domain.units import format_odds


def stable_in_form(runs: int, wins: int) -> Signal | None:
    """An in-form yard is a big plus (the owner: 'critical'). Strike-rate over a
    recent window (e.g. the trainer's last 14 days)."""
    if runs < 8:
        return None
    strike = 100.0 * wins / runs
    if strike >= 25.0:
        return Signal("stable_hot", 4.0, f"Stable red-hot ({strike:.0f}% recent) — yard flying")
    if strike >= 18.0:
        return Signal("stable_form", 3.0, f"Stable in form ({strike:.0f}% recent) — big plus")
    if runs >= 20 and strike <= 5.0:
        return Signal("stable_cold", -2.0, f"Stable out of form ({strike:.0f}% recent)")
    return None


def first_time_headgear(runner: Runner) -> Signal | None:
    """First time in headgear (blinkers/cheekpieces/hood/visor/tongue-tie) — the
    trainer looking for improvement. A positive."""
    if runner.headgear_first_time and runner.headgear:
        return Signal("first_headgear", 2.0,
                      f"First-time {runner.headgear} — trainer looking for improvement")
    return None


def form_franked(franked_count: int) -> Signal | None:
    """Has the form been franked — have horses beaten (or that beat this one)
    gone on to win since? Validated form is worth far more than bare figures.
    `franked_count` comes from the collateral-form follow-up in the data layer."""
    if franked_count >= 1:
        return Signal("form_franked", 3.0,
                      f"Form franked — {franked_count} rival(s) have won since, the form stands up")
    return None


def jockey_intent(runner: Runner, race: Race, stable_jockey_ids: frozenset[str]) -> Signal | None:
    """The stable-jockey-on-the-second-string read (the Townend signal). When a
    yard runs more than one and its NUMBER-ONE jockey takes a horse that is NOT
    the yard's market-elect, that quietly-fancied one is the message. The flip —
    the stable jockey is on a different runner — marks this one as the lesser."""
    if not runner.trainer_id:
        return None
    yard = [r for r in race.runners if r.trainer_id == runner.trainer_id]
    priced = [(r, r.odds.consensus) for r in yard if r.odds.consensus]
    if len(priced) < 2:
        return None
    shortest = min(p for _, p in priced)
    this_price = runner.odds.consensus
    a_main_in_yard = any(r.jockey_id in stable_jockey_ids for r, _ in priced)
    if runner.jockey_id in stable_jockey_ids and this_price and this_price > shortest * 1.05:
        return Signal("jockey_intent", 4.0,
                      f"Stable jockey on the yard's longer one "
                      f"({format_odds(this_price)} vs elect {format_odds(shortest)}) — quietly fancied")
    if a_main_in_yard and runner.jockey_id not in stable_jockey_ids:
        return Signal("not_stable_elect", -2.0,
                      "Yard's main jockey is on another runner — this is the lesser")
    return None


def jockey_trainer_combo(rides: int, wins: int) -> Signal | None:
    """A hot jockey/trainer partnership over a real sample."""
    if rides < 15:
        return None
    strike = 100.0 * wins / rides
    if strike >= 18.0:
        return Signal("hot_combo", 2.0, f"Hot jockey/trainer combo ({strike:.0f}% over {rides} rides)")
    return None


def market_move(odds: Odds) -> Signal | None:
    """The market read — but honestly weighted, per the research. Steamers DO win
    slightly more, but following the steam is NOT profitable: the market prices
    the move in, so the value was in the EARLY price, before it shortened. So a
    steamer is mild confirmation only (+1, take the early price), while a big
    drift is a genuine warning the informed money is against it."""
    morning = odds.morning
    now = odds.late or odds.consensus
    if not morning or not now:
        return None
    if now <= morning * 0.85:        # shortened 15%+
        return Signal("steamer", 1.0,
                      f"Backed in {format_odds(morning)} -> {format_odds(now)} — market agrees "
                      f"(value was the early price)")
    if now >= morning * 1.30:        # drifted 30%+
        return Signal("drifter", -2.0,
                      f"Drifting {format_odds(morning)} -> {format_odds(now)} — informed money against it")
    return None
