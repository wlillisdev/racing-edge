"""Render the CLV ledger — the honest scoreboard. Pure.

Leads with closing-line value (the proven, fast signal), shows the favourite
benchmark and a season split (never blended), and ends with the sample-size
verdict. P&L is shown but explicitly secondary.
"""

from __future__ import annotations

from racing_edge.measurement.metrics import Summary, by_season, summarise, verdict, vs_favourite
from racing_edge.measurement.record import SettledPick

_RULE = "=" * 64


def _row(label: str, s: Summary) -> str:
    clv = f"{s.mean_clv_pct:+.1f}%" if s.mean_clv_pct is not None else "  —"
    beat = f"{s.pct_positive_clv:.0f}%" if s.pct_positive_clv is not None else " —"
    return (f"  {label:<22}{s.n:>5}{s.win_pct:>6.0f}%{s.roi_pct:>8.1f}%"
            f"{clv:>9}{beat:>7}")


def render_ledger(picks: list[SettledPick]) -> str:
    method = [p for p in picks if p.system == "method"]
    if not method:
        return "No settled picks yet — record some days and settle them against results."
    lines = [
        _RULE,
        "  CLV LEDGER — the honest scoreboard (closing-line value leads)",
        _RULE,
        f"  {'':<22}{'n':>5}{'win%':>7}{'ROI%':>8}{'CLV':>9}{'beat':>7}",
    ]
    bench = vs_favourite(picks)
    lines.append(_row("METHOD", bench.method))
    lines.append(_row("FAVOURITE (same races)", bench.favourite))
    if bench.edge_clv is not None:
        lines.append(f"  -> edge on the close: {bench.edge_clv:+.2f}% CLV vs the favourite")

    lines.append("\n  by season (never blended):")
    for season, s in by_season(method).items():
        lines.append(_row(season, s))

    lines.append("\n" + verdict(summarise(method)))
    lines.append("  (CLV = how much your price beat the off; 'beat' = % of bets that beat it.")
    lines.append("   ROI is the slow, noisy number — watch CLV.)")
    return "\n".join(lines)
