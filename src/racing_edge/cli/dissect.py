"""Dissect the day's readable handicaps — the nightly 'go through it together' readout.

    python -m racing_edge.cli.dissect --day today

Runs on the box (real API) so the data is TRUE — real SPs and the real market move,
no WebSearch, no hallucination. For every readable handicap it prints the whole field
with each runner's finish, SP and whether it was BACKED or drifted. The manner/comment
column is OWED — that's the bit we read together from the form (#27).
"""

from __future__ import annotations

import argparse

from racing_edge.cli._common import resolve_date
from racing_edge.data.client import get_client
from racing_edge.data.normalise import racecards_from_raw, results_from_raw
from racing_edge.report.dissect import render_race_dissection
from racing_edge.study.enrich import enrich_from_card
from racing_edge.study.postmortem import StudiedRunner


def main() -> int:
    ap = argparse.ArgumentParser(description="Per-horse dissection of the day's handicaps.")
    ap.add_argument("--day", default="today", help="today | yesterday | YYYY-MM-DD")
    ap.add_argument("--email", action="store_true", help="email the readout (uses SMTP env vars)")
    args = ap.parse_args()

    client = get_client()
    ds = resolve_date(args.day).isoformat()
    results = results_from_raw(client.results_by_date(ds))
    cards = {r.race_id: r for r in racecards_from_raw(client.racecards(ds))}

    out: list[str] = []

    def emit(s: str = "") -> None:
        print(s)
        out.append(s)

    printed = 0
    for res in results:
        card = cards.get(res.race_id)
        if card is None or not card.is_readable_handicap:   # readable handicaps only
            continue
        runners = [StudiedRunner(name=r.horse, horse_id=r.horse_id, finish_pos=r.position,
                                 sp_dec=r.sp_dec, comment=r.comment,
                                 beaten_lengths=r.beaten_lengths)
                   for r in res.runners]
        runners = enrich_from_card(runners, card)       # sets morning_dec -> the market move
        emit(render_race_dissection(card, runners))
        emit("")
        printed += 1

    if not printed:
        emit(f"No readable handicaps to dissect for {ds} (results not in yet, or none qualified).")
    if args.email:
        from racing_edge.report.mail import configured, send
        if not configured():
            print("  (--email set, but SMTP env vars aren't configured — not sent)")
        else:
            ok = send(f"Dissection — {ds}", "\n".join(out), title=f"Dissection {ds}",
                      subtitle="racing-edge form trial")
            print(f"  email: {'sent' if ok else 'FAILED — check SMTP env vars / task log'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
