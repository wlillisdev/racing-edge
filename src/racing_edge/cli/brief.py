"""The brief — the full contender scorecard for every readable handicap.

The diligence artifact, and the cure for spoon-feeding: every lens across every
contender, side by side, with the blanks (OWED) called out. The machine does the
tireless reading; you make the call on a complete picture.

    python -m racing_edge.cli.brief --day today --both
"""

from __future__ import annotations

import argparse

from racing_edge.data.client import get_client
from racing_edge.data.evidence import build_evidence
from racing_edge.data.normalise import racecards_from_raw
from racing_edge.report.scorecard import build_scorecard, render_scorecard


def main() -> int:
    ap = argparse.ArgumentParser(description="The contender scorecard for each readable race.")
    ap.add_argument("--day", default="today", help="today | tomorrow | YYYY-MM-DD")
    ap.add_argument("--flat", action="store_true", help="flat instead of jumps")
    ap.add_argument("--both", action="store_true", help="both codes")
    ap.add_argument("--top", type=int, default=4, help="how many contenders per race")
    ap.add_argument("--race", metavar='"COURSE H:MM"',
                    help='full pre-race form readout for ONE race (any type, '
                         'handicap or not) — e.g. --race "Salisbury 7:15". '
                         'Born 2026-07-25: the on-demand read channel — paste the '
                         'output to the reader, get the method applied.')
    args = ap.parse_args()

    codes = ["jump", "flat"] if args.both else ["flat" if args.flat else "jump"]
    client = get_client()

    if args.race:
        from racing_edge.data.normalise import past_runs_from_raw
        from racing_edge.report.restudy import render_preread
        want = args.race.strip().lower()
        course_part, _, time_part = want.rpartition(" ")
        cards = racecards_from_raw(client.racecards(args.day))
        race = next((r for r in cards
                     if r.off_time.strip() == time_part
                     and course_part in r.course.strip().lower()), None)
        if race is None:
            print(f"  No race matching '{args.race}' on {args.day}'s card. On today:")
            for r in cards:
                print(f"    {r.course} {r.off_time} — {r.race_type}"
                      + (f" (Cl{r.race_class})" if r.race_class else ""))
            return 1
        print(f"  {race.course} {race.off_time} — fetching form for "
              f"{race.field_size} runner(s)…", flush=True)
        hists = {}
        for r in race.runners:
            try:
                hists[r.horse_id] = past_runs_from_raw(
                    client.horse_results(r.horse_id, limit=20), r.horse_id)
            except Exception:
                hists[r.horse_id] = ()
        print(render_preread(race, hists))
        return 0
    races = [r for r in racecards_from_raw(client.racecards(args.day))
             if r.is_readable_handicap and r.code in codes]
    if not races:
        print("No readable handicaps to brief.")
        return 0
    for race in races:
        evidence = build_evidence(race, client)
        print(render_scorecard(build_scorecard(race, evidence, top_n=args.top)))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
