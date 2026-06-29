"""The nap — one bet a day, nominated BLIND off the morning card, logged for a record.

    python -m racing_edge.cli.nap --day today --both     # nominate + bank today's nap
    python -m racing_edge.cli.nap --settle yesterday     # settle it, show the strike rate

Fixes the three honest holes in a hand-picked nap: it nominates from the racecard
(blind, no results), it only calls a nap CONFIDENT when the mark was actually read, and
it banks every nap so a strike rate accumulates instead of n=1.
"""

from __future__ import annotations

import argparse

from racing_edge.cli._common import open_nap_log, resolve_date
from racing_edge.data.client import get_client
from racing_edge.data.evidence import build_evidence
from racing_edge.data.normalise import results_from_raw
from racing_edge.pipeline.nap import evaluate_field
from racing_edge.report.scorecard import build_scorecard, render_scorecard


def _settle(day_str: str) -> int:
    day = resolve_date(day_str)
    log = open_nap_log()
    nap = next((n for n in log.pending() if n["date"] == day.isoformat()), None)
    if nap is None:
        print(f"No unsettled nap for {day}.")
        log.close()
        return 0
    results = results_from_raw(get_client().results_by_date(day.isoformat()))
    race = next((r for r in results if r.race_id == nap["race_id"]), None)
    me = next((rr for rr in race.runners if rr.horse_id == nap["horse_id"]), None) if race else None
    if me is None:
        print(f"Result for {nap['horse']} not in yet for {day}.")
        log.close()
        return 0
    won = me.position == 1
    log.settle(day, won=won, sp_dec=me.sp_dec)
    w, n = log.strike_rate()
    cw, cn = log.strike_rate(confident_only=True)
    flag = "WON" if won else f"unplaced ({me.position or me.status})"
    print(f"  {day}: nap {nap['horse']} — {flag} at SP {me.sp_dec or '?'}")
    print(f"  nap record: {w}/{n} won ({100 * w / n:.0f}%) overall; "
          f"{cw}/{cn} on CONFIDENT naps." if n else "  nap record: none settled yet.")
    log.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Nominate (or settle) the day's nap.")
    ap.add_argument("--day", default="today", help="today | tomorrow | YYYY-MM-DD")
    ap.add_argument("--flat", action="store_true", help="flat only")
    ap.add_argument("--both", action="store_true", help="both codes")
    ap.add_argument("--settle", metavar="DAY", help="settle a banked nap against results")
    args = ap.parse_args()
    if args.settle:
        return _settle(args.settle)

    codes = ("jump", "flat") if args.both else (("flat",) if args.flat else ("jump",))
    client = get_client()
    field = evaluate_field(client, day=args.day, codes=codes)
    if not field:
        print("No nap — nothing readable stands up today. Discipline is a position.")
        return 0

    # FAIR EVALUATION (rule #24): show EVERY contender's read before the pick, so the nap
    # has to beat an even reading of the field — never an anchored one.
    print("  the field, fairly evaluated (every contender, strongest first):")
    for p in field:
        c = p.conviction
        mark = "" if c.mark_known else " [mark OWED]"
        flags = f"  FLAGS: {', '.join(c.flags)}" if c.flags else ""
        print(f"    {p.runner.horse:22} {p.race.course} {p.race.off_time}  "
              f"conv {c.score}{mark}: {', '.join(c.aligned) or 'thin'}{flags}")
    print()

    nap = field[0]      # the pick is the top of the field we just evaluated — not re-fetched

    c, r = nap.conviction, nap.race
    tag = "CONFIDENT NAP" if c.confident else "best candidate — NOT confident (declinable)"
    print(f"  {tag}: {nap.runner.horse}  —  {r.course} {r.off_time} ({r.race_type})")
    print(f"  conviction {c.score}: {', '.join(c.aligned) or 'thin'}")
    if c.flags:
        print(f"  FLAGS: {', '.join(c.flags)}")
    if not c.mark_known:
        print("  ⚠ the MARK was not readable — never a confident nap without it.")
    evidence = build_evidence(r, client)
    print("\n" + render_scorecard(build_scorecard(r, evidence)))

    day = nap.race.date
    log = open_nap_log()
    log.record(day=day, race_id=r.race_id, course=r.course, horse=nap.runner.horse,
               horse_id=nap.runner.horse_id, price=nap.price, score=c.score,
               confident=c.confident)
    log.close()
    print(f"\n  banked the nap for {day} — settle it tomorrow with --settle {day}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
