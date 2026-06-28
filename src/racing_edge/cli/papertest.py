"""Paper-test the reading against real results — for MARKING, no live effect.

    python -m racing_edge.cli.papertest --start 2026-06-20 --end 2026-06-27

Walks real settled days, studies every race, and prints the reads for you to mark:
what won, how I read it, and — honestly — what the result data couldn't tell me
(the open gaps). It scores rule #2 (a real, non-circular check) and writes NOTHING
to the live DBs. This is how the manner read proves itself before it ever touches
a pick.
"""

from __future__ import annotations

import argparse
from datetime import timedelta

from racing_edge.cli._common import open_ledger, resolve_date
from racing_edge.data.client import get_client
from racing_edge.study.collect import collect_day
from racing_edge.study.papertest import summarise_review
from racing_edge.study.postmortem import StudiedRunner, study_card


def main() -> int:
    ap = argparse.ArgumentParser(description="Paper-test the reads against real results.")
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()

    start, end = resolve_date(args.start), resolve_date(args.end)
    client = get_client()
    picks = {p.race_id: p.horse for p in open_ledger().settled_picks() if p.system == "method"}

    races: list[list[StudiedRunner]] = []
    our: list[str | None] = []
    day = start
    while day <= end:
        d_races, d_our, _ = collect_day(client, day, picks)
        races.extend(d_races)
        our.extend(d_our)
        day += timedelta(days=1)

    if not races:
        print(f"No settled races between {start} and {end} to paper-test.")
        return 0

    card = study_card(races, our)
    print(f"\n  PAPER TEST {start} -> {end}  ({card.n_races} races) — mark these reads\n")
    for i, s in enumerate(card.studies, 1):
        if not s.lessons and not s.gaps:
            continue
        print(f"  ── race {i}: won by {s.winner or '?'} "
              f"({'fav' if s.winner_market_rank == 1 else f'{s.winner_market_rank} in mkt'})")
        for lesson in s.lessons:
            print(f"      {lesson}")
        for g in s.gaps:
            print(f"      ⚠ owed: {g}")

    r = summarise_review(card)
    print("\n  " + "-" * 56)
    print(f"  rule #2 (2nd/3rd fav won): {r.rule2_held}/{r.rule2_total}"
          + (f"  ({r.rule2_pct:.0f}%)" if r.rule2_pct is not None else ""))
    print(f"  grunt work still owed across the sample: {r.open_gaps} checks")
    print("  (the manner-downgrade's real test — do nearly-types lose their NEXT race —")
    print("   needs each runner's prior comments; that's the history enrichment owed.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
