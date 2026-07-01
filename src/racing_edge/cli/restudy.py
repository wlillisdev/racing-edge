"""RE-STUDY finished races off the FULL FORM — the real learning loop (#27/#29).

    python -m racing_edge.cli.restudy --day today                 # all readable handicaps
    python -m racing_edge.cli.restudy --day today --time 16:10    # focus ONE race (fast)
    python -m racing_edge.cli.restudy --day 2026-07-01 --course Thirsk [--email]

The master's loop, made honest: when the result is in, go BACK to the full form — the
mark, the figures, the OR, and each horse's last runs WITH their in-running comments —
and study the whole race again knowing who won, to find the clue you missed. Runs on the
box (real API), shows only what the window returns, prints OWED where it's blank. Never
invents a comment or a price. It's slow by design (it pulls every runner's history), so
focus with --time when you're studying one race.
"""

from __future__ import annotations

import argparse

from racing_edge.cli._common import resolve_date
from racing_edge.data.client import get_client
from racing_edge.data.normalise import (
    past_runs_from_raw,
    racecards_from_raw,
    results_from_raw,
)
from racing_edge.report.restudy import render_restudy


def main() -> int:
    ap = argparse.ArgumentParser(description="Re-study finished races off the full form.")
    ap.add_argument("--day", default="today", help="today | yesterday | YYYY-MM-DD")
    ap.add_argument("--course", help="only this course (substring, case-insensitive)")
    ap.add_argument("--time", help="only this off-time, e.g. 16:10 — focus ONE race (fast)")
    ap.add_argument("--past", type=int, default=3, help="how many past runs per horse")
    ap.add_argument("--email", action="store_true", help="email the readout (SMTP env vars)")
    args = ap.parse_args()

    client = get_client()
    ds = resolve_date(args.day).isoformat()
    results = {r.race_id: r for r in results_from_raw(client.results_by_date(ds))}
    cards = racecards_from_raw(client.racecards(ds))

    # pick the readable handicaps that have a result AND match the focus filters
    def _match(c) -> bool:
        if not c.is_readable_handicap or c.race_id not in results:
            return False
        if args.course and args.course.lower() not in c.course.lower():
            return False
        return not (args.time and args.time not in c.off_time)

    races = [c for c in cards if _match(c)]
    if not races:
        print(f"  Nothing to re-study for {ds} "
              f"(no readable handicap with a result matched your filter).")
        return 0

    out: list[str] = []

    def emit(s: str = "") -> None:
        print(s, flush=True)
        out.append(s)

    print(f"  re-studying {len(races)} race(s) off the full form — pulling every runner's "
          f"history (slow; --time focuses one)…", flush=True)
    for race in races:
        print(f"    · {race.course} {race.off_time} — reading {race.field_size} "
              f"runners' full form", flush=True)
        histories = {
            r.horse_id: past_runs_from_raw(client.horse_results(r.horse_id), r.horse_id)
            for r in race.runners if r.horse_id
        }
        emit(render_restudy(race, results[race.race_id], histories, past_n=args.past))
        emit("")

    if args.email:
        from racing_edge.report.mail import configured, send
        if not configured():
            print("  (--email set, but SMTP env vars aren't configured — not sent)")
        else:
            ok = send(f"Re-study — {ds}", "\n".join(out), title=f"Re-study {ds}",
                      subtitle="racing-edge — the full-form learning loop")
            print(f"  email: {'sent' if ok else 'FAILED — check SMTP env vars'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
