"""Analyse a settled ledger (the backtest or the live one) for where the edge
lives — conviction, walk-forward, by-signal. No API, no tuning.

    python -m racing_edge.cli.analyse                 # the backtest ledger
    python -m racing_edge.cli.analyse --live          # the live ledger
"""

from __future__ import annotations

import argparse
from pathlib import Path

from racing_edge.config import get_config
from racing_edge.measurement.store import Ledger
from racing_edge.report.analysis import render_analysis


def main() -> int:
    ap = argparse.ArgumentParser(description="Honest optimisation analysis over a ledger.")
    ap.add_argument("--live", action="store_true", help="use the live ledger (default: backtest)")
    args = ap.parse_args()

    name = "ledger.db" if args.live else "backtest.db"
    path = Path(get_config().project_dir) / "data" / name
    print(render_analysis(Ledger(path).settled_picks()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
