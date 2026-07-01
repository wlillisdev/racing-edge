"""LEARN — the self-teaching loop: read the result, interrogate yourself, bank the nuance.

    python -m racing_edge.cli.learn --day today --time 16:10      # self-study ONE race
    python -m racing_edge.cli.learn --day yesterday               # every finished handicap
    python -m racing_edge.cli.learn --show                        # read the banked nuances
    python -m racing_edge.cli.learn --promote 3                   # master: rule #3 REAL
    python -m racing_edge.cli.learn --bin 1                       # master: rule #1 rubbish
    python -m racing_edge.cli.learn --synthesise [--email]        # join dots ACROSS days

Every nuance now faces THE SCEPTIC before banking — a second, adversarial model pass
that tries to kill it against the same readout (fact-check, contradiction, data-artifact,
triviality). Refuted -> shown but NOT banked. Survivor -> banked as a proposal.

This is the piece the master kept asking for: not just laying the form out (that's
cli.restudy), but THINKING about it — the AI asking itself *"why did you pick that horse?
the winner was in the form — why did you miss it? what's the nuance?"* — grounded in the
real result, and banking each lesson as a PROPOSAL to be tested (study.nuances).

Needs the model ON: set ANTHROPIC_API_KEY (and optionally ANTHROPIC_MODEL for depth). It
uses the direct-HTTP reasoner (ai.reason), NOT the SDK, so it survives the box's httpx
clash. No key -> it says so and banks nothing, rather than inventing.
"""

from __future__ import annotations

import argparse

from racing_edge.ai.reason import get_reasoner
from racing_edge.cli._common import open_nap_log, open_nuance_log, resolve_date
from racing_edge.data.client import get_client
from racing_edge.pipeline.restudy import Restudy, gather
from racing_edge.report.restudy import render_restudy
from racing_edge.study.selfcritique import (
    REFUTE_SYSTEM,
    SYSTEM,
    build_prompt,
    build_refute_prompt,
    parse_critique,
    parse_refutation,
    render_critique,
)


def _blind_pick_for(day_iso: str, race_id: str) -> str | None:
    """What we banked BLIND in this race (if anything) — from the nap ledger."""
    log = open_nap_log()
    try:
        return next((n["horse"] for n in log.history()
                     if n["date"] == day_iso and n["race_id"] == race_id), None)
    finally:
        log.close()


def _show() -> int:
    log = open_nuance_log()
    rows = log.all()
    if not rows:
        print("  No nuances banked yet. Run: python -m racing_edge.cli.learn --day yesterday")
        log.close()
        return 0
    print("  SELF-TAUGHT NUANCES (proposals until the record/master rules — "
          "--promote N / --bin N):")
    for r in rows:
        print(f"    #{r['id']:<3} [{r['status']:9}] {r['date']}  "
              f"{r['course']} — winner {r['winner']}")
        print(f"       nuance: {r['nuance']}")
        if r["owed"]:
            print(f"       OWED:   {r['owed']}   (confidence {r['confidence'] or '?'})")
    log.close()
    return 0


def _rule(nuance_id: int, status: str) -> int:
    """The master's ruling — promote a nuance to validated, or bin it as rejected.
    This is the human half of the loop: the model proposes, the record/master decide."""
    log = open_nuance_log()
    row = next((r for r in log.all() if r["id"] == nuance_id), None)
    if row is None:
        print(f"  No nuance #{nuance_id}. See them with --show.")
        log.close()
        return 1
    log.set_status(nuance_id, status)
    log.close()
    verdict = "PROMOTED — earned its place" if status == "validated" \
        else "BINNED — built on a crack"
    print(f"  #{nuance_id} {verdict}:")
    print(f"    {row['nuance']}")
    if status == "validated":
        print("  (now write it into the notebook/tells so it bites on picks — "
              "a validated nuance that stays in the DB teaches nothing.)")
    return 0


def _learn_one(st: Restudy, reason, day_iso: str) -> str:
    readout = render_restudy(st.race, st.result, st.histories)
    label = f"{st.race.course} {st.race.off_time}"
    blind = _blind_pick_for(day_iso, st.race.race_id)
    text = reason(SYSTEM, build_prompt(readout, st.winner, blind))
    crit = parse_critique(text)
    if not crit.ok:
        return render_critique(crit, label, st.winner)

    # THE SCEPTIC — a second, adversarial pass tries to KILL the nuance against the same
    # readout before it's banked (would have caught the WELL-IN/+3lb crack unaided).
    ref = parse_refutation(reason(REFUTE_SYSTEM, build_refute_prompt(readout, crit)))
    out = render_critique(crit, label, st.winner)
    if ref.refuted:
        return (out + f"\n    ✗ REFUTED by the sceptic ({ref.ground or '?'}) — NOT banked:"
                      f"\n      {ref.reason}")
    log = open_nuance_log()
    log.record(day=st.race.date, race_id=st.race.race_id, course=st.race.course,
               winner=st.winner, blind_pick=blind or "", **crit.record_fields())
    log.close()
    survived = (f"survived the sceptic ({ref.reason})" if ref.answered
                else "sceptic gave no verdict — banked anyway, rule with --show")
    return out + f"\n    ✓ {survived}"


_SYNTH_SYSTEM = (
    "You are a 30-year handicapper's apprentice doing the WEEKLY REVIEW — joining the "
    "dots ACROSS days, which no single race shows. You get (a) every nuance you have "
    "taught yourself (with status: the master promoted, binned, or hasn't ruled) and "
    "(b) the blind nap record (picked before the off, settled after).\n"
    "Find what single races can't: nuances that REPEAT across days (a pattern), nuances "
    "that CONTRADICT each other (at most one can be right), what the binned ones have in "
    "common (your own failure mode), and what the nap record says about which lenses are "
    "actually winning. Reason ONLY over what is given; blanks are unknown. Be blunt and "
    "brief — a page the master can read over breakfast, plain text, no JSON."
)


def _synthesise(reason, email: bool) -> int:
    nlog = open_nuance_log()
    nuances = nlog.all()
    nlog.close()
    plog = open_nap_log()
    naps = plog.history()
    plog.close()
    if not nuances and not naps:
        print("  Nothing to synthesise yet — no nuances banked, no naps on the record.")
        return 0
    nu_lines = [f"- [{n['status']}] {n['date']} {n['course']} (winner {n['winner']}): "
                f"{n['nuance']}" for n in nuances] or ["(none yet)"]
    nap_lines = []
    for n in naps:
        res = ("WON" if n["won"] == 1 else "lost") if n["won"] is not None else "pending"
        nap_lines.append(f"- {n['date']} {n['horse']} ({n['course']}) "
                         f"{'CONFIDENT' if n['confident'] else 'lean'}: {res}"
                         f"{' @' + str(n['sp_dec']) if n['sp_dec'] else ''}")
    prompt = ("SELF-TAUGHT NUANCES (status = the master's ruling):\n"
              + "\n".join(nu_lines)
              + "\n\nTHE BLIND NAP RECORD:\n" + "\n".join(nap_lines or ["(none yet)"])
              + "\n\nJoin the dots. What repeats, what contradicts, what do the binned "
                "ones share, and what is the record saying? End with at most three "
                "SHARP actions for the coming week.")
    print("  synthesising across the ledger + the record…", flush=True)
    text = reason(_SYNTH_SYSTEM, prompt)
    if not text:
        print("  no synthesis returned (model error) — nothing invented.")
        return 1
    print("\n" + text)
    if email:
        from racing_edge.report.mail import configured, send
        if configured():
            ok = send("Weekly synthesis — joining the dots", text,
                      title="Weekly synthesis", subtitle="racing-edge — across-days review")
            print(f"\n  email: {'sent' if ok else 'FAILED'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Self-interrogate finished races; bank nuances.")
    ap.add_argument("--day", default="today", help="today | yesterday | YYYY-MM-DD")
    ap.add_argument("--course", help="only this course (substring)")
    ap.add_argument("--time", help="only this off-time, e.g. 16:10 — focus ONE race")
    ap.add_argument("--show", action="store_true", help="print the banked nuances and exit")
    ap.add_argument("--promote", type=int, metavar="N",
                    help="rule nuance #N VALIDATED (the master's promote)")
    ap.add_argument("--bin", type=int, metavar="N", dest="bin_id",
                    help="rule nuance #N REJECTED (the master's bin)")
    ap.add_argument("--synthesise", action="store_true",
                    help="join the dots ACROSS days: nuances + nap record -> patterns")
    ap.add_argument("--email", action="store_true", help="email the self-study (SMTP env)")
    args = ap.parse_args()
    if args.show:
        return _show()
    if args.promote is not None:
        return _rule(args.promote, "validated")
    if args.bin_id is not None:
        return _rule(args.bin_id, "rejected")

    # load .env FIRST (it carries ANTHROPIC_API_KEY on the box) — get_reasoner reads the
    # env, and without this it would run before get_client()'s load_dotenv and see no key.
    from racing_edge.config import get_config
    get_config()
    reason = get_reasoner()
    if reason is None:
        print("  The model is OFF — set ANTHROPIC_API_KEY (and ANTHROPIC_MODEL for depth) "
              "to self-interrogate. Banking nothing rather than inventing.")
        return 0
    if args.synthesise:
        return _synthesise(reason, args.email)

    client = get_client()
    ds = resolve_date(args.day).isoformat()

    def _progress(line: str) -> None:
        print(line, flush=True)

    studies = gather(client, ds, course=args.course, time=args.time, progress=_progress)
    if not studies:
        print(f"  Nothing to self-study for {ds} (no readable handicap with a result matched).")
        return 0

    out: list[str] = []
    for st in studies:
        print(f"    · thinking about {st.race.course} {st.race.off_time}…", flush=True)
        block = _learn_one(st, reason, ds)
        print(block, flush=True)
        print(flush=True)
        out.append(block)

    if args.email and out:
        from racing_edge.report.mail import configured, send
        if configured():
            ok = send(f"Self-study — {ds}", "\n\n".join(out),
                      title=f"Self-study {ds}", subtitle="racing-edge — self-taught nuances")
            print(f"  email: {'sent' if ok else 'FAILED — check SMTP env vars'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
