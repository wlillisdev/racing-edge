"""BACKCHECK — test a proposed pattern against real past results, day by day.

    python -m racing_edge.cli.backcheck --from 2026-06-17 --to 2026-06-30 [--email]

The honest way to settle "is this nuance real?": not the master's memory, not the
model's confidence — the record. Sweeps each day through the box's real API (past
racecards + results + every runner's history), applies the pattern blind, and counts.

Pattern under test: LEAST-RAISED RECENT WINNER (from the Epsom 6:22 study) — in a
handicap with 2+ last-time-out winners, back the one raised least since its win.

Slow by design: one history fetch per runner per race (~a minute per raceday at the
API throttle). Run it on the box, let it grind, read the verdict at the end.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta

from racing_edge.data.client import get_client
from racing_edge.pipeline.restudy import gather
from racing_edge.study.patterns import least_raised_recent_winner, summarise


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> int:
    ap = argparse.ArgumentParser(description="Backcheck a pattern against real results.")
    ap.add_argument("--from", dest="start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--email", action="store_true", help="email the verdict (SMTP env)")
    args = ap.parse_args()
    start, end = _d(args.start), _d(args.end)
    if end < start:
        print("  --to is before --from.")
        return 1

    client = get_client()
    out: list[str] = []

    def emit(s: str = "") -> None:
        print(s, flush=True)
        out.append(s)

    emit(f"  BACKCHECK: least-raised recent winner, {start} -> {end}")
    emit("  (banked blind per race off past cards; results only used to settle)")
    hits = []
    day = start
    while day <= end:
        print(f"    sweeping {day}…", flush=True)
        for st in gather(client, day.isoformat()):
            h = least_raised_recent_winner(st)
            if h:
                hits.append(h)
                emit(f"    {h.date} {h.course} {h.off_time}: {h.horse} "
                     f"(+{h.delta}lb, {h.rivals} recent winners) -> "
                     f"{'WON' if h.won else 'lost'}"
                     f"{' @' + str(h.sp_dec) if h.sp_dec else ''}")
        day += timedelta(days=1)
    emit("")
    emit(summarise(hits))

    if args.email:
        from racing_edge.report.mail import configured, send
        if configured():
            ok = send(f"Backcheck — least-raised recent winner {start}->{end}",
                      "\n".join(out), title="Pattern backcheck",
                      subtitle="racing-edge — tested against the record")
            print(f"  email: {'sent' if ok else 'FAILED'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
