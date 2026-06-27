"""Print the CLV ledger — the honest scoreboard, any time (no API).

    python -m racing_edge.cli.report
"""

from __future__ import annotations

from racing_edge.cli._common import open_ledger
from racing_edge.report.ledger import render_ledger


def main() -> int:
    print(render_ledger(open_ledger().settled_picks()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
