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
    args = ap.parse_args()

    codes = ["jump", "flat"] if args.both else ["flat" if args.flat else "jump"]
    client = get_client()
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
