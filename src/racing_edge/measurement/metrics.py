"""Honest metrics over settled picks — CLV first, P&L second, season-stratified,
benchmarked against the favourite, with a sample-size verdict.
"""

from __future__ import annotations

from dataclasses import dataclass

from racing_edge.measurement.record import SettledPick

TRUST_SAMPLE = 100   # below this, CLV is "direction only" and P&L is noise


@dataclass(frozen=True)
class Summary:
    n: int
    wins: int
    win_pct: float
    roi_pct: float                 # level stakes at the price taken
    mean_clv_pct: float | None     # the north star
    pct_positive_clv: float | None

    @property
    def trusted(self) -> bool:
        return self.n >= TRUST_SAMPLE


def summarise(picks: list[SettledPick]) -> Summary:
    n = len(picks)
    if n == 0:
        return Summary(0, 0, 0.0, 0.0, None, None)
    wins = sum(1 for p in picks if p.won)
    staked = [p for p in picks if p.price_taken]
    pl = sum((p.price_taken - 1.0) if p.won else -1.0 for p in staked if p.price_taken)
    roi = 100.0 * pl / len(staked) if staked else 0.0
    clvs = [p.clv for p in picks if p.clv is not None]
    mean_clv = round(100.0 * sum(clvs) / len(clvs), 2) if clvs else None
    pct_pos = round(100.0 * sum(1 for c in clvs if c > 0) / len(clvs), 1) if clvs else None
    return Summary(n, wins, round(100.0 * wins / n, 1), round(roi, 1), mean_clv, pct_pos)


def by_season(picks: list[SettledPick]) -> dict[str, Summary]:
    """Never a blended verdict — winter jumps and summer flat reported apart."""
    seasons = sorted({p.season for p in picks})
    return {s: summarise([p for p in picks if p.season == s]) for s in seasons}


@dataclass(frozen=True)
class Benchmark:
    method: Summary
    favourite: Summary

    @property
    def edge_roi(self) -> float:
        return round(self.method.roi_pct - self.favourite.roi_pct, 1)

    @property
    def edge_clv(self) -> float | None:
        if self.method.mean_clv_pct is None or self.favourite.mean_clv_pct is None:
            return None
        return round(self.method.mean_clv_pct - self.favourite.mean_clv_pct, 2)


def vs_favourite(picks: list[SettledPick]) -> Benchmark:
    """The method against the SP-favourite in the same races — the honest
    relative question (almost everything loses at level stakes)."""
    return Benchmark(
        method=summarise([p for p in picks if p.system == "method"]),
        favourite=summarise([p for p in picks if p.system == "favourite"]),
    )


def verdict(s: Summary) -> str:
    """The sample-size honesty guard — no calling an edge on noise."""
    if s.n < TRUST_SAMPLE:
        return (f"SAMPLE {s.n}/{TRUST_SAMPLE} — direction only. CLV {s.mean_clv_pct}% is the "
                f"signal to watch; treat ROI as noise.")
    if s.mean_clv_pct is not None and s.mean_clv_pct > 0:
        return f"Beating the close (+{s.mean_clv_pct}% CLV over {s.n}) — a real edge is showing."
    return f"Not beating the close ({s.mean_clv_pct}% CLV over {s.n}) — no proven edge yet."
