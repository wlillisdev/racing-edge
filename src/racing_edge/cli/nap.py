"""The nap — one bet a day, nominated BLIND off the morning card, logged for a record.

    python -m racing_edge.cli.nap --day today --both            # nominate + bank
    python -m racing_edge.cli.nap --day today --both --email     # ...and email it to you
    python -m racing_edge.cli.nap --settle yesterday [--email]   # settle + strike rate

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


def _maybe_email(buf: list[str], subject: str, email: bool) -> None:
    """Email the buffered output if --email was set. Never crashes the run."""
    if not email:
        return
    from racing_edge.report.mail import configured, recipient, send
    if not configured():
        print("  (--email set, but EMAIL_SENDER/PASSWORD/RECIPIENT aren't in the env — not sent)")
        return
    ok = send(subject, "\n".join(buf), title=subject, subtitle="racing-edge form trial")
    # show the ADDRESS it went to — so you can check it's really yours (and check spam)
    print(f"  email: {'sent to ' + (recipient() or '?') if ok else 'FAILED — check the SMTP env'}")


def _record() -> int:
    """Show the banked nap record — read it yourself, don't take my word for it."""
    log = open_nap_log()
    rows = log.history()
    if not rows:
        print("No naps banked yet.")
        log.close()
        return 0
    print("  NAP RECORD (banked BEFORE each race, settled AFTER — the real ledger):")
    for r in rows:
        res = ("WON" if r["won"] == 1 else "lost") if r["won"] is not None else "pending"
        conf = "CONFIDENT" if r["confident"] else "lean"
        sp = f" @{r['sp_dec']}" if r["sp_dec"] else ""
        print(f"    {r['date']}  {r['horse']:22} {r['course']:12} {conf:9} {res}{sp}")
    w, n = log.strike_rate()
    cw, cn = log.strike_rate(confident_only=True)
    if n:
        print(f"  strike rate: {w}/{n} won ({100 * w / n:.0f}%) overall; "
              f"{cw}/{cn} on CONFIDENT naps.  (small samples lie — judge it over hundreds.)")
    log.close()
    return 0


def _settle(day_str: str, email: bool) -> int:
    day = resolve_date(day_str)
    out: list[str] = []

    def emit(s: str = "") -> None:
        print(s)
        out.append(s)

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
    emit(f"  {day}: nap {nap['horse']} — {flag} at SP {me.sp_dec or '?'}")
    emit(f"  nap record: {w}/{n} won ({100 * w / n:.0f}%) overall; "
         f"{cw}/{cn} on CONFIDENT naps." if n else "  nap record: none settled yet.")
    log.close()
    _maybe_email(out, f"Nap settled — {nap['horse']} {flag} ({day})", email)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Nominate (or settle) the day's nap.")
    ap.add_argument("--day", default="today", help="today | tomorrow | YYYY-MM-DD")
    ap.add_argument("--flat", action="store_true", help="flat only")
    ap.add_argument("--both", action="store_true", help="both codes")
    ap.add_argument("--settle", metavar="DAY", help="settle a banked nap against results")
    ap.add_argument("--record", action="store_true", help="show the banked nap record")
    ap.add_argument("--email", action="store_true", help="email the output (uses SMTP env vars)")
    args = ap.parse_args()
    if args.record:
        return _record()
    if args.settle:
        return _settle(args.settle, args.email)

    out: list[str] = []

    def emit(s: str = "") -> None:
        print(s)
        out.append(s)

    codes = ("jump", "flat") if args.both else (("flat",) if args.flat else ("jump",))
    client = get_client()
    field = evaluate_field(client, day=args.day, codes=codes)
    if not field:
        emit("No nap — nothing readable stands up today. Discipline is a position.")
        _maybe_email(out, "Nap — no bet today", args.email)
        return 0

    # SELECT BY ELIMINATION (rule #25): cross off what can't win FIRST, then zero in on
    # the survivors — never start from a horse to love. Forces the fair evaluation of #24.
    crossed = [p for p in field if p.conviction.flags]
    survivors = [p for p in field if not p.conviction.flags]
    if crossed:
        emit("  CROSSED OFF — won't win, and why (knock out the no-hopers first):")
        for p in crossed:
            emit(f"    ✗ {p.runner.horse:22} {p.race.course} {p.race.off_time}  "
                 f"— {', '.join(p.conviction.flags)}")
    emit("\n  SURVIVORS — zero in on these (strongest first):")
    for p in survivors:
        c = p.conviction
        mark = "" if c.mark_known else " [mark OWED]"
        emit(f"    • {p.runner.horse:22} {p.race.course} {p.race.off_time}  "
             f"conv {c.score}{mark}: {', '.join(c.aligned) or 'thin'}")
    emit("")

    if not survivors:
        emit("No nap — every contender crossed off. Discipline is a position.")
        _maybe_email(out, "Nap — no bet today", args.email)
        return 0
    nap = survivors[0]      # zero in on the strongest SURVIVOR, not the top of the raw field

    # standing guard (rule #26): the two decisive facts the brief CAN'T see — never
    # invent them, never cross off or nap on a guessed run-style or a stale price.
    emit("  ⚠ DECISIVE FACTS OWED — do NOT invent (rule #26):")
    emit("     · live market MOVE (backed/drifted) — a forecast price is not the market")
    emit("     · run-STYLE / manner — who leads, who's held up (the comments door)")

    c, r = nap.conviction, nap.race
    tag = "CONFIDENT NAP" if c.confident else "best candidate — NOT confident (declinable)"
    emit(f"  {tag}: {nap.runner.horse}  —  {r.course} {r.off_time} ({r.race_type})")
    emit(f"  conviction {c.score}: {', '.join(c.aligned) or 'thin'}")
    if c.flags:
        emit(f"  FLAGS: {', '.join(c.flags)}")
    if not c.mark_known:
        emit("  ⚠ the MARK was not readable — never a confident nap without it.")
    evidence = build_evidence(r, client)
    emit("\n" + render_scorecard(build_scorecard(r, evidence)))

    day = nap.race.date
    log = open_nap_log()
    log.record(day=day, race_id=r.race_id, course=r.course, horse=nap.runner.horse,
               horse_id=nap.runner.horse_id, price=nap.price, score=c.score,
               confident=c.confident)
    log.close()
    emit(f"\n  banked the nap for {day} — settle it tomorrow with --settle {day}.")
    _maybe_email(out, f"{tag}: {nap.runner.horse} — {r.course} {r.off_time} ({day})", args.email)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
