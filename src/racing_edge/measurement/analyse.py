"""Honest optimisation analysis over the settled ledger — CLV-judged, sample-gated.

Implements the cheap, leak-free first cuts of the optimisation protocol, read
straight from the recorded picks (score + fired signals captured per pick):
  • by_conviction  — does the edge concentrate in HIGH-score picks? (your 10/14
                     instinct) — a COARSE threshold grid, not a fine sweep.
  • by_signal      — for each signal, CLV of picks WHERE it fired vs where it
                     didn't (associational, not true leave-one-out ablation —
                     that needs a re-pick run; flagged as a hypothesis cue).
  • walk_forward   — split the season early/late: does the picture HOLD on the
                     half it wasn't observed on, or front-load and die?

Nothing here tunes anything; it surfaces where to look. Acting on any cell needs
the sample gates and an out-of-sample confirmation (see docs/optimisation_protocol.md).
"""

from __future__ import annotations

from racing_edge.measurement.metrics import Summary, summarise
from racing_edge.measurement.record import SettledPick


def _method(picks: list[SettledPick]) -> list[SettledPick]:
    return [p for p in picks if p.system == "method"]


def _signals_of(p: SettledPick) -> list[str]:
    return [s for s in p.signals.split(",") if s] if p.signals else []


def by_conviction(picks: list[SettledPick],
                  thresholds: list[float] | None = None) -> list[tuple[str, Summary]]:
    """Summary for picks at/above each score threshold. Default = a coarse grid
    (median / 60th / 75th percentile of scores) per the protocol."""
    method = [p for p in _method(picks) if p.score is not None]
    if not method:
        return []
    if thresholds is None:
        ss = sorted(p.score for p in method if p.score is not None)
        thresholds = [ss[len(ss) // 2], ss[int(len(ss) * 0.6)], ss[int(len(ss) * 0.75)]]
    out = [("all picks", summarise(method))]
    for t in sorted(set(thresholds)):
        out.append((f"score >= {t:.1f}", summarise([p for p in method if (p.score or 0) >= t])))
    return out


def by_signal(picks: list[SettledPick]) -> list[tuple[str, Summary, Summary]]:
    """For each signal: (name, summary WHERE it fired, summary where it didn't).
    Associational — a cue for which signals to ablate properly, not a verdict."""
    method = _method(picks)
    names = sorted({n for p in method for n in _signals_of(p)})
    rows: list[tuple[str, Summary, Summary]] = []
    for n in names:
        fired = [p for p in method if n in _signals_of(p)]
        not_fired = [p for p in method if n not in _signals_of(p)]
        rows.append((n, summarise(fired), summarise(not_fired)))
    return rows


_PRICE_BANDS = [("<= 2.5", 0.0, 2.5), ("2.5-4", 2.5, 4.0), ("4-6", 4.0, 6.0),
                ("6-10", 6.0, 10.0), ("10+", 10.0, 9e9)]


def by_price_band(picks: list[SettledPick]) -> list[tuple[str, Summary]]:
    """Does the method beat the close at some PRICES and not others? (The clean,
    point-in-time version of the old loser-patterns price finding.)"""
    method = [p for p in _method(picks) if p.price_taken]
    out = []
    for label, lo, hi in _PRICE_BANDS:
        sub = [p for p in method if p.price_taken and lo < p.price_taken <= hi]
        if sub:
            out.append((label, summarise(sub)))
    return out


def by_month(picks: list[SettledPick]) -> list[tuple[str, Summary]]:
    """Seasonality within the winter — is any edge concentrated in certain months?"""
    method = _method(picks)
    months = sorted({(p.date.year, p.date.month) for p in method})
    return [(f"{y}-{m:02d}", summarise([p for p in method if p.date.year == y and p.date.month == m]))
            for y, m in months]


def walk_forward(picks: list[SettledPick]) -> list[tuple[str, Summary]]:
    """Split the method's picks chronologically in half: does the edge hold on
    the later half it wasn't 'observed' on, or front-load then fade?"""
    method = sorted(_method(picks), key=lambda p: p.date)
    if len(method) < 4:
        return []
    mid = len(method) // 2
    return [("first half (early)", summarise(method[:mid])),
            ("second half (later)", summarise(method[mid:]))]
