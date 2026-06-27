"""Form-string reads — improving vs bottler. Pure: the figures only.

The owner's lines:
  • "improving form, the 5-3-2-3 type — running into it, just needs the right race."
  • "perennial bottlers, 2-2-2-2 — best avoided unless they drop in class."
"""

from __future__ import annotations

from racing_edge.domain.signal import Signal
from racing_edge.domain.units import parse_form


def improving(form: str) -> Signal | None:
    """Knocking on the door: the newer runs are clearly better than the older
    ones, it's placing, and it hasn't yet won. The right race away from winning.
    """
    figs = parse_form(form)
    if len(figs) < 3:
        return None
    recent = list(reversed(figs))[:6]            # most-recent first
    if recent.count(1) > 0:
        return None                              # already a winner in this run of form
    half = max(1, len(recent) // 2)
    newer, older = recent[:half], recent[half:]
    trending_up = (sum(newer) / len(newer)) < (sum(older) / len(older)) - 0.5
    near_the_front = min(recent[:2]) <= 3
    if trending_up and near_the_front:
        line = "".join(str(p if p < 10 else 0) for p in reversed(recent))
        return Signal("improving", 4.0, f"Improving — knocking on the door ({line})")
    return None


def bottler(form: str) -> Signal | None:
    """Runs well, won't win: no win, plenty of placings, no upward trend. A hard
    leave-it UNLESS it drops in class (the selection layer applies that let-off).
    """
    figs = parse_form(form)
    if len(figs) < 4:
        return None
    recent = list(reversed(figs))[:6]
    if recent.count(1) > 0:
        return None
    places = sum(1 for p in recent if p in (2, 3))
    if places >= 3:
        line = "".join(str(p if p < 10 else 0) for p in reversed(recent))
        return Signal("bottler", -5.0, f"Perennial placer ({line}) — runs well, won't win",
                      veto=True)
    return None
