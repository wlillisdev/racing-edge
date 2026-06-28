"""Study every race on a day's card and store it — the learning loop's evening half.

    python -m racing_edge.cli.study --day yesterday

Runs AFTER settle. Pulls the day's results (with the in-running comments), studies
the WHOLE card — was the winner the 2nd/3rd fav, did it finish like a winner, did
our pick lose as a nearly-type — and stores each study so the notebook's rules can
be tested against a growing body of real results. Shadow only: reads results,
writes the study DB, touches nothing the live engine does.
"""

from __future__ import annotations

import argparse

from racing_edge.cli._common import open_ledger, open_study_store, resolve_date
from racing_edge.data.client import get_client
from racing_edge.data.normalise import results_from_raw
from racing_edge.study.postmortem import StudiedRunner, study_card


def main() -> int:
    ap = argparse.ArgumentParser(description="Study the whole card and bank the lessons.")
    ap.add_argument("--day", default="yesterday", help="today | yesterday | YYYY-MM-DD")
    args = ap.parse_args()

    day = resolve_date(args.day)
    results = results_from_raw(get_client().results_by_date(day.isoformat()))
    if not results:
        print(f"No results available yet for {day} — nothing to study.")
        return 0

    # our method picks for the day (race_id -> horse), so the study can flag our losses
    picks_by_race = {p.race_id: p.horse for p in open_ledger().settled_picks()
                     if p.system == "method" and p.date == day}

    races: list[list[StudiedRunner]] = []
    our: list[str | None] = []
    race_ids: list[str] = []
    for res in results:
        races.append([StudiedRunner(name=r.horse, finish_pos=r.position,
                                    sp_dec=r.sp_dec, comment=r.comment) for r in res.runners])
        our.append(picks_by_race.get(res.race_id))
        race_ids.append(res.race_id)

    card = study_card(races, our)
    store = open_study_store()
    store.record_card(day, race_ids, [""] * len(race_ids), card.studies)

    hits, total = store.rule2_rate()
    print(f"  studied {card.n_races} race(s) for {day}; stored (DB now holds {store.count()}).")
    if total:
        print(f"  rule #2 in the wild: 2nd/3rd fav won {hits}/{total} "
              f"({100 * hits / total:.0f}%) across all studied races.")
    fresh = [lesson for s in card.studies for lesson in s.lessons]
    if fresh:
        print("\n  what the card taught:")
        for lesson in fresh[:20]:
            print(f"    • {lesson}")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
