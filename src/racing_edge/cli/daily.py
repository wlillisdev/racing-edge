"""Thin CLI entry point — no logic. Fetch today's jumps card and print the
owner's picks with reasons.

    python -m racing_edge.cli.daily            # today's jumps card
    python -m racing_edge.cli.daily --flat     # flat instead
    python -m racing_edge.cli.daily --day tomorrow
"""

from __future__ import annotations

import argparse

from racing_edge.betting.policy import BettingPolicy
from racing_edge.data.client import get_client
from racing_edge.pipeline.daily import run_day
from racing_edge.report.card import render_card


def main() -> int:
    ap = argparse.ArgumentParser(description="The owner's daily card — method picks with reasons.")
    ap.add_argument("--day", default="today", help="today | tomorrow | YYYY-MM-DD")
    ap.add_argument("--flat", action="store_true", help="flat racing instead of jumps")
    ap.add_argument("--bank", type=float, default=1000.0)
    args = ap.parse_args()

    policy = BettingPolicy(bank=args.bank)
    card = run_day(get_client(), policy, day=args.day, code=("flat" if args.flat else "jump"))
    print(render_card(card))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
