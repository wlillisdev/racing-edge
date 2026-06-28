"""Collect a day's races, enriched — the bridge from the API to the study.

Fetches the results AND the morning card for the day, joins them, and pulls the
history of just the winner and our pick (so the study can answer course/trip/going
without a fetch per runner). Returns the enriched StudiedRunner races ready for
study_card. This is the one study module that touches the network.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Protocol

from racing_edge.data.normalise import past_runs_from_raw, racecards_from_raw, results_from_raw
from racing_edge.study.enrich import enrich_from_card, enrich_from_history
from racing_edge.study.frank import frank_form
from racing_edge.study.postmortem import StudiedRunner


class _Fetcher(Protocol):
    def racecards(self, day: str = "today") -> dict: ...
    def results_by_date(self, date_str: str) -> dict: ...
    def horse_results(self, horse_id: str, limit: int = 12) -> list[dict]: ...


def collect_day(client: _Fetcher, day: date, picks_by_race: dict[str, str],
                ) -> tuple[list[list[StudiedRunner]], list[str | None], list[str]]:
    ds = day.isoformat()
    results = results_from_raw(client.results_by_date(ds))
    cards = {r.race_id: r for r in racecards_from_raw(client.racecards(ds))}

    races: list[list[StudiedRunner]] = []
    our: list[str | None] = []
    ids: list[str] = []
    for res in results:
        base = [StudiedRunner(name=r.horse, horse_id=r.horse_id, finish_pos=r.position,
                              sp_dec=r.sp_dec, comment=r.comment, beaten_lengths=r.beaten_lengths)
                for r in res.runners]
        card = cards.get(res.race_id)
        if card is not None:
            base = enrich_from_card(base, card)

        pick_name = picks_by_race.get(res.race_id)
        winner = next((r for r in res.runners if r.position == 1), None)
        key_ids = {r.horse_id for r in (winner,) if r} | {
            r.horse_id for r in res.runners if pick_name and r.horse == pick_name}
        if card is not None and key_ids:
            enriched: list[StudiedRunner] = []
            for sr in base:
                if sr.horse_id in key_ids:
                    hist = past_runs_from_raw(client.horse_results(sr.horse_id))
                    sr = enrich_from_history(sr, hist, card)
                    sr = replace(sr, frank_note=frank_form(client, sr.horse_id, hist).note)
                enriched.append(sr)
            base = enriched

        races.append(base)
        our.append(pick_name)
        ids.append(res.race_id)
    return races, our, ids
