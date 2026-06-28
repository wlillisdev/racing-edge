"""Backtest the method over a date range — the honest verdict.

    python -m racing_edge.cli.backtest --start 2025-11-01 --end 2026-03-31
    python -m racing_edge.cli.backtest --start 2025-11-01 --end 2026-03-31 --flat

Writes to a SEPARATE ledger (data/backtest.db) so it never mixes with the live
one. Point-in-time evidence (no look-ahead). Prints the CLV scoreboard.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path

from racing_edge.config import get_config
from racing_edge.data.client import get_client
from racing_edge.measurement.store import Ledger
from racing_edge.pipeline.backtest import backtest
from racing_edge.report.ledger import render_ledger


def main() -> int:
    ap = argparse.ArgumentParser(description="Backtest the method over a date range.")
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--flat", action="store_true", help="flat instead of jumps")
    args = ap.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()
    path = Path(get_config().project_dir) / "data" / "backtest.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(path)

    print(f"  backtesting {'flat' if args.flat else 'jumps'} {start} -> {end} "
          f"(point-in-time, no look-ahead)...", flush=True)

    def _progress(d: date, races: int, picks: int) -> None:
        print(f"    {d}  {races:>2} races   {picks} picks so far", flush=True)

    days, picks = backtest(get_client(), start, end, ledger,
                           code=("flat" if args.flat else "jump"), progress=_progress)
    print(f"\n  {days} day(s), {picks} pick(s)\n")
    print(render_ledger(ledger.settled_picks()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
