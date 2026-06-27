"""Market stance — the Benter lesson, applied. Pure.

The one proven winning model found the public price is the strongest predictor,
and you only have an edge where you DISAGREE with the crowd. So for each pick we
flag whether it is the market's favourite (agreeing — little edge to be had) or a
non-favourite (your call against the market — the only place an edge can live).
This never scores; it tells the human WHERE their edge is, honestly.
"""

from __future__ import annotations

from racing_edge.domain.models import Race, Runner


def favourite(race: Race) -> Runner | None:
    priced = [r for r in race.runners if r.odds.consensus and r.odds.consensus > 1.0]
    return min(priced, key=lambda r: r.odds.consensus or 9e9) if priced else None


def is_favourite(runner: Runner, race: Race) -> bool:
    fav = favourite(race)
    return fav is not None and fav.horse_id == runner.horse_id


def market_stance(runner: Runner, race: Race) -> str:
    fav = favourite(race)
    if fav is None or not runner.odds.consensus:
        return ""
    if fav.horse_id == runner.horse_id:
        return "WITH the market (the favourite — agreeing with the crowd, so little edge here)"
    return "AGAINST the market (a non-favourite — your edge, if any, lives here)"
