"""NAPCHECK — backtest the WHOLE nap pipeline over past days. The proof, not the promise.

    python -m racing_edge.cli.napcheck --from 2026-06-15 --to 2026-07-04 [--email]

Born 2026-07-05, the master: "I have no idea if it's fixed or if it will learn — and
we have a serious amount of data." This runs the CURRENT pipeline — gates, conviction,
frank veto, profile floor — over each past day exactly as the morning task would have
(NO LOOK-AHEAD: histories cut before each day, intent stats skipped, franking bounded),
then settles every would-have-been pick against the real result. Output: the pick or
the pass per day, the strike rate, and level-stakes P/L at SP. Run it after every
significant change: the record over hundreds of races judges the fix, not anyone's
word. Writes NOTHING to the live ledger.

(The deep model is not in this loop — it tests the mechanical skeleton the deep read
stands on. If the skeleton's floor-and-gates alone don't beat random, no model on top
is trustworthy.)
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta

from racing_edge.data.client import get_client
from racing_edge.data.normalise import results_from_raw
from racing_edge.domain.mark import mark_read
from racing_edge.pipeline.nap import anchor_bar, evaluate_field
from racing_edge.study.frank import frank_form


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> int:
    ap = argparse.ArgumentParser(description="Backtest the full nap pipeline, no look-ahead.")
    ap.add_argument("--from", dest="start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--email", action="store_true", help="email the verdict")
    args = ap.parse_args()
    start, end = _d(args.start), _d(args.end)

    client = get_client()
    out: list[str] = []

    def emit(s: str = "") -> None:
        print(s, flush=True)
        out.append(s)

    emit(f"  NAPCHECK: the current pipeline replayed {start} -> {end} (no look-ahead)")
    bets = wins = passes = 0
    pnl = 0.0
    day = start
    while day <= end:
        iso = day.isoformat()
        print(f"    replaying {iso}…", flush=True)
        field = evaluate_field(client, day=iso, codes=("jump", "flat"), as_of=day)
        survivors = [p for p in field if not p.conviction.flags]
        pick = None
        reason = "no survivors (gates crossed everything off)"
        for cand in survivors[:3]:
            fr = frank_form(client, cand.runner.horse_id, cand.history, as_of=day,
                            code=cand.race.code)
            if fr.is_thin:
                reason = f"frank veto on {cand.runner.horse}"
                continue
            delta = mark_read(cand.runner.official_rating, cand.history,
                              code=cand.race.code).delta
            fav = min((p.price for p in field
                       if p.race.race_id == cand.race.race_id and p.price), default=None)
            fails = []
            if delta is None or delta > 0:
                fails.append("not well-in")
            if cand.race.race_class is not None and cand.race.race_class > 4:
                fails.append(f"Cl{cand.race.race_class}")
            if fav is None or fav >= anchor_bar(cand.race.race_class):
                fails.append(f"no anchor (fav {fav})")
            if fails:
                reason = f"profile floor on {cand.runner.horse}: {', '.join(fails)}"
                continue
            pick = cand
            break
        if pick is None:
            passes += 1
            emit(f"    {iso}  PASS — {reason}")
        else:
            results = results_from_raw(client.results_by_date(iso))
            race = next((r for r in results if r.race_id == pick.race.race_id), None)
            me = next((rr for rr in race.runners
                       if rr.horse_id == pick.runner.horse_id), None) if race else None
            if me is None:
                emit(f"    {iso}  {pick.runner.horse} — result OWED, not counted")
            else:
                won = me.position == 1
                bets += 1
                wins += int(won)
                pnl += (me.sp_dec - 1.0) if (won and me.sp_dec) else -1.0
                emit(f"    {iso}  {pick.runner.horse:22} {pick.race.course} "
                     f"{pick.race.off_time} (Cl{pick.race.race_class or '?'}) -> "
                     f"{'WON' if won else 'lost'}"
                     f"{' @' + str(me.sp_dec) if me.sp_dec else ''}")
        day += timedelta(days=1)

    emit("")
    if bets:
        emit(f"  VERDICT: {wins}/{bets} won ({100 * wins / bets:.0f}%), "
             f"level stakes at SP: {pnl:+.1f}pt, {passes} pass day(s).")
    else:
        emit(f"  VERDICT: no bets in the window ({passes} pass day(s)) — the floor may "
             f"be too tight, or the window too quiet. Both are findings.")
    emit("  (small samples lie — weight this by the number of bets, not the percentage.)")

    if args.email:
        from racing_edge.report.mail import configured, send
        if configured():
            ok = send(f"Napcheck {start}->{end}: {wins}/{bets}, {pnl:+.1f}pt",
                      "\n".join(out), title="Nap pipeline backtest",
                      subtitle="racing-edge — replayed with no look-ahead")
            print(f"  email: {'sent' if ok else 'FAILED'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
