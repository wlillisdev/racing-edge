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

from racing_edge.domain.models import Runner
from racing_edge.domain.signal import Signal


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
