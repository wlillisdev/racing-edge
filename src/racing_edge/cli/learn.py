"""LEARN — the self-teaching loop: read the result, interrogate yourself, bank the nuance.

    python -m racing_edge.cli.learn --day today --time 16:10      # self-study ONE race
    python -m racing_edge.cli.learn --day yesterday               # every finished handicap
    python -m racing_edge.cli.learn --show                        # read the banked nuances

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
    SYSTEM,
    build_prompt,
    parse_critique,
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
    print("  SELF-TAUGHT NUANCES (proposals until the record/master promotes them):")
    for r in rows:
        print(f"    [{r['status']:9}] {r['date']}  {r['course']} — winner {r['winner']}")
        print(f"       nuance: {r['nuance']}")
        if r["owed"]:
            print(f"       OWED:   {r['owed']}   (confidence {r['confidence'] or '?'})")
    log.close()
    return 0


def _learn_one(st: Restudy, reason, day_iso: str) -> str:
    readout = render_restudy(st.race, st.result, st.histories)
    label = f"{st.race.course} {st.race.off_time}"
    blind = _blind_pick_for(day_iso, st.race.race_id)
    text = reason(SYSTEM, build_prompt(readout, st.winner, blind))
    crit = parse_critique(text)
    if crit.ok:
        log = open_nuance_log()
        log.record(day=st.race.date, race_id=st.race.race_id, course=st.race.course,
                   winner=st.winner, blind_pick=blind or "", **crit.record_fields())
        log.close()
    return render_critique(crit, label, st.winner)


def main() -> int:
    ap = argparse.ArgumentParser(description="Self-interrogate finished races; bank nuances.")
    ap.add_argument("--day", default="today", help="today | yesterday | YYYY-MM-DD")
    ap.add_argument("--course", help="only this course (substring)")
    ap.add_argument("--time", help="only this off-time, e.g. 16:10 — focus ONE race")
    ap.add_argument("--show", action="store_true", help="print the banked nuances and exit")
    ap.add_argument("--email", action="store_true", help="email the self-study (SMTP env)")
    args = ap.parse_args()
    if args.show:
        return _show()

    # load .env FIRST (it carries ANTHROPIC_API_KEY on the box) — get_reasoner reads the
    # env, and without this it would run before get_client()'s load_dotenv and see no key.
    from racing_edge.config import get_config
    get_config()
    reason = get_reasoner()
    if reason is None:
        print("  The model is OFF — set ANTHROPIC_API_KEY (and ANTHROPIC_MODEL for depth) "
              "to self-interrogate. Banking nothing rather than inventing.")
        return 0

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
