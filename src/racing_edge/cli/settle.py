"""Settle a day's picks against results and print the CLV ledger.

    python -m racing_edge.cli.settle               # settle today
    python -m racing_edge.cli.settle --day yesterday
"""

from __future__ import annotations

import argparse

from racing_edge.cli._common import open_ledger, resolve_date
from racing_edge.data.client import get_client
from racing_edge.data.normalise import results_from_raw
from racing_edge.pipeline.ledger import settle_day
from racing_edge.report.ledger import render_ledger


def main() -> int:
    ap = argparse.ArgumentParser(description="Settle the ledger against results.")
    ap.add_argument("--day", default="today", help="today | yesterday | YYYY-MM-DD")
    args = ap.parse_args()

    day = resolve_date(args.day)
    results = results_from_raw(get_client().results_by_date(day.isoformat()))
    if not results:
        print(f"No results available yet for {day} — leaving picks pending.")
        return 0

    ledger = open_ledger()
    settle_day(day, results, ledger)
    print(f"  settled {day}; {ledger.pending_count()} pick(s) still pending\n")
    print(render_ledger(ledger.settled_picks()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
