"""Answer the study's open questions instead of flagging them — the enrichment.

From the morning CARD (one fetch per day): the market move (morning price vs SP),
trainer form, the claimer's relief, the headgear/wind angle. From a key horse's
HISTORY (winner + our pick only, to keep the fetch count sane): course form, trip
and going proven. The mark-rise and the franking stay owed — they need historical
official ratings and the beaten-horses' next runs, heavier jobs for later.

Pure: card/history in, an enriched StudiedRunner out. No network here (that's
study.collect); these just transform.
"""

from __future__ import annotations

from dataclasses import replace

from racing_edge.domain.models import PastRun, Race
from racing_edge.domain.units import going_band
from racing_edge.study.postmortem import StudiedRunner

_TRAINER_FORM_SR = 0.15      # 14-day strike rate that counts as "in form"


def enrich_from_card(base: list[StudiedRunner], race: Race) -> list[StudiedRunner]:
    """Join the morning racecard to the result by horse_id; fill the card-derived
    clues (market move, trainer form, claimer relief, headgear angle)."""
    card = {r.horse_id: r for r in race.runners if r.horse_id}
    out: list[StudiedRunner] = []
    for sr in base:
        r = card.get(sr.horse_id)
        if r is None:
            out.append(sr)
            continue
        runs, wins = r.trainer_14d_runs or 0, r.trainer_14d_wins or 0
        out.append(replace(
            sr,
            morning_dec=r.odds.consensus,
            trainer_in_form=(runs > 0 and wins / runs >= _TRAINER_FORM_SR),
            claim_lbs=r.claim_lbs or 0,
            headgear_change=bool(r.headgear_first_time or r.wind_surgery),
        ))
    return out


def enrich_from_history(sr: StudiedRunner, history: tuple[PastRun, ...],
                        race: Race) -> StudiedRunner:
    """Course / trip / going proven, from a horse's prior runs (placed = top 3)."""
    band = race.going_band
    course = trip = going = False
    for h in history:
        if race.course and h.course == race.course and h.position == 1:
            course = True                       # genuinely won at this course
        placed = h.position is not None and h.position <= 3
        if not placed:
            continue
        if race.distance_f and h.distance_f and abs(h.distance_f - race.distance_f) <= 1.0:
            trip = True
        if band and h.going and going_band(h.going) == band:
            going = True
    return replace(sr, course_winner=course, trip_proven=trip, going_proven=going, enriched=True)
