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

from racing_edge.cli._common import open_nap_log, open_nuance_log, resolve_date
from racing_edge.data.client import get_client
from racing_edge.data.evidence import build_evidence
from racing_edge.data.normalise import results_from_raw
from racing_edge.pipeline.nap import evaluate_field, ew_advice, market_shape
from racing_edge.report.scorecard import build_scorecard, render_scorecard


# every race-level gate's flag text, in ONE place (2026-07-25 replication audit:
# the top-class door and the profile floor each kept their own partial list — one
# rewording of a flag would have silently blinded them out of step with each other)
_RACE_GATE_TERMS = ("novice in disguise", "bottom-grade", "open market",
                    "all-weather", "big-field")


def _race_gate_flags(flags) -> list[str]:
    return [f for f in flags if any(g in f for g in _RACE_GATE_TERMS)]


def _maybe_email(buf: list[str], subject: str, email: bool) -> None:
    """Email the buffered output if --email was set. Never crashes the run."""
    if not email:
        return
    from racing_edge.report.mail import configured, recipient, send
    if not configured():
        print("  (--email set, but EMAIL_SENDER/PASSWORD/RECIPIENT aren't in the env — not sent)")
        return
    ok = send(subject, "\n".join(buf), title=subject, subtitle="racing-edge form trial")
    # the delivery VERDICT, verified in the mailbox itself — not just 'sent'
    print(f"  email to {recipient() or '?'}: {ok if ok else 'FAILED — check the SMTP env'}")


def _bank_pass(day, reason: str) -> None:
    """A no-bet day is still a ledger day — banked with its reason (never overwrites
    a real pick: record_pass only fires on paths where none was banked)."""
    log = open_nap_log()
    log.record_pass(day=day, reason=reason)
    log.close()


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
        if r["won"] == -1:
            print(f"    {r['date']}  NO BET (pass) — "
                  f"{(r.get('case_text') or 'discipline')[:60]}")
            continue
        res = ("WON" if r["won"] == 1 else "lost") if r["won"] is not None else "pending"
        conf = "CONFIDENT" if r["confident"] else "lean"
        sp = f" @{r['sp_dec']}" if r["sp_dec"] else ""
        print(f"    {r['date']}  {r['horse']:22} {r['course']:12} {conf:9} {res}{sp}")
    w, n = log.strike_rate()
    cw, cn = log.strike_rate(confident_only=True)
    if n:
        print(f"  strike rate: {w}/{n} won ({100 * w / n:.0f}%) overall; "
              f"{cw}/{cn} on CONFIDENT naps.  (small samples lie — judge it over hundreds.)")
        pnl, pn = log.profit_loss()
        print(f"  LEVEL STAKES at SP: {pnl:+.1f}pt over {pn} bet(s) — "
              f"the money gauge; strike rate without prices measures nothing.")
        attr = log.lens_attribution()
        if attr:
            print("  LENS ATTRIBUTION (which lenses ride winners vs losers — the dial):")
            for a in attr[:10]:
                print(f"    {a['lens']:28} {a['wins']}W / {a['losses']}L")
    sw, sn = log.shadow_strike()
    if sn:
        # honest label (2026-07-25 replication audit): this is the RAW top survivor,
        # no frank, no floor — a signal, not a bettable method; the full A/B needs
        # the mechanical chain extracted so both sides play by the same rules
        print(f"  SHADOW (raw engine top survivor — no floor applied, not bettable "
              f"as-is): {sw}/{sn} won ({100 * sw / sn:.0f}%).")
    log.close()
    return 0


def _resend(day_str: str) -> int:
    """Re-EMAIL the already-banked nap for a day, straight from the ledger — never
    re-picks, never re-banks (re-running the picker intra-day would overwrite the
    pre-off record with moved prices). For when the morning email goes missing."""
    day = resolve_date(day_str).isoformat()
    log = open_nap_log()
    n = next((x for x in log.history() if x["date"] == day), None)
    log.close()
    if n is None:
        print(f"  No nap banked for {day} — nothing to resend.")
        return 1
    if n["won"] == -1:
        body = (f"NO BET banked for {day} — an earned pass, not a failure.\n"
                f"reason: {n.get('case_text') or 'discipline'}")
        print(body)
        _maybe_email([body], f"Nap — no bet ({day}, resend)", email=True)
        return 0
    tag = "CONFIDENT NAP" if n["confident"] else "best candidate (not confident)"
    res = ("" if n["won"] is None else
           f"\nresult: {'WON' if n['won'] == 1 else 'lost'}"
           f"{' @' + str(n['sp_dec']) if n['sp_dec'] else ''}")
    subject = f"{tag}: {n['horse']} — {n['course']} ({day})"
    body = (f"{subject}\n"
            f"price at banking: {n['price']}   conviction score: {n['score']}{res}\n"
            f"banked pre-off in nap.db — this is a RESEND of the banked record, "
            f"nothing re-picked.")
    print(body)
    _maybe_email([body], subject, email=True)
    return 0


def _guard() -> int:
    """The pre-off DRIFT GUARD (audit fix 4). The move called the winner four times in
    one day and the drift saved the Perfidia stake — yet the banked nap was never
    re-checked. Compares the pick's price NOW vs at banking: a 20%+ drift = STAND OFF
    (emailed); firmed = confirmation. The ledger is untouched either way — this guards
    the STAKE, not the record."""
    from racing_edge.data.normalise import racecards_from_raw
    day = resolve_date("today")
    log = open_nap_log()
    n = next((x for x in log.pending() if x["date"] == day.isoformat()), None)
    log.close()
    if not n:
        print("  No unsettled nap banked for today — nothing to guard.")
        return 0
    cards = racecards_from_raw(get_client().racecards("today"))
    race = next((r for r in cards if r.race_id == n["race_id"]), None)
    runner = next((x for x in race.runners if x.horse_id == n["horse_id"]), None) \
        if race else None
    now = runner.odds.consensus if runner else None
    banked = n["price"]
    if not (now and banked):
        print(f"  price OWED (banked {banked}, now {now}) — cannot judge the move.")
        return 0
    from racing_edge.report.mail import send
    if banked * 1.10 <= now < banked * 1.2:
        # graded bands, not one cliff (the master, 2026-07-26): 10-20% is the money
        # cooling — said out loud before it becomes a stand-off
        msg = (f"⚠ drifting: {n['horse']} {banked} -> {now} (10-20%) — not a stand-off "
               f"yet, but the money is cooling; watch before the off.")
        print(f"  {msg}")
        ok = send(f"Drift caution: {n['horse']} ({banked}->{now})", msg,
                  title="Drift guard", subtitle="racing-edge form trial")
        print(f"  email: {ok or 'FAILED'}")
    elif now >= banked * 1.2:
        msg = (f"⚠ STAND OFF — {n['horse']} has DRIFTED {banked} -> {now}. "
               f"The drift rule has been right every time (Perfidia, Artiste d'Ainay): "
               f"the money is leaving. Keep the stake in your pocket. "
               f"(The pick stays on the ledger — this guards the stake, not the record.)")
        print(f"  {msg}")
        ok = send(f"STAND OFF: {n['horse']} drifting ({banked}->{now})", msg,
                  title="Drift guard", subtitle="racing-edge form trial")
        print(f"  email: {ok or 'FAILED'}")   # the one email that guards the stake
    elif now <= banked * 0.9:
        msg = f"✓ {n['horse']} BACKED {banked} -> {now} — the market agrees with the pick."
        print(f"  {msg}")
        ok = send(f"Backed: {n['horse']} ({banked}->{now})", msg,
                  title="Drift guard", subtitle="racing-edge form trial")
        print(f"  email: {ok or 'FAILED'}")
    else:
        print(f"  {n['horse']} steady ({banked} -> {now}) — no signal, no email.")
    return 0


def _settle(day_str: str, email: bool) -> int:
    day = resolve_date(day_str)
    out: list[str] = []

    def emit(s: str = "") -> None:
        print(s)
        out.append(s)

    # TRACKED CLUES + THE BROOM RUN FIRST (2026-07-25 audit: they sat below the
    # 'no nap banked' early return, so on every PASS day no clue settled and the
    # 28-day broom never swept — the exact silting the fix existed to end)
    try:
        results = results_from_raw(get_client().results_by_date(day.isoformat()))
    except Exception as exc:
        # a transient API failure must not kill the settle run with a bare
        # traceback (2026-07-25 review) — say it, email it, retry tomorrow
        emit(f"  ⚠ results fetch failed ({exc.__class__.__name__}) — nothing "
             f"settled this run; the night task retries tomorrow")
        _maybe_email(out, f"Settle FAILED — results fetch error ({day})", email)
        return 1
    nlog = open_nuance_log()
    tracked_by_id = {t["horse_id"]: t for t in nlog.tracked_active() if t["horse_id"]}
    settled_clues = 0
    for res in results:
        for rr in res.runners:
            t = tracked_by_id.get(rr.horse_id)
            if t is None:
                continue
            # SP in the stamp (ROI audit: without it the clue stream can never be
            # judged in money or against the fav baseline)
            outcome = (f"ran {day.isoformat()}, "
                       f"{'WON' if rr.position == 1 else f'pos {rr.position or rr.status}'}"
                       + (f", SP {rr.sp_dec}" if rr.sp_dec else ""))
            hit = (rr.position == 1) == (t["angle"] == "follow")
            settled_clues += nlog.settle_tracked(rr.horse_id, outcome=outcome, held=hit)
            emit(f"  tracked clue settled: [{t['angle']}] {t['horse']} — "
                 f"{outcome} ({'clue HELD' if hit else 'clue missed'})")
            del tracked_by_id[rr.horse_id]
    swept = nlog.expire_tracked()
    # RECORD-BASED promotion: a theme whose settled clues prove out promotes its
    # nuances to 'field-tested' — the trial record doing the validating, exactly as
    # the ledger's own law allows ('the TRIAL RECORD or the MASTER promotes')
    for ft in nlog.field_test_themes():
        emit(f"  ★ FIELD-TESTED by the record: theme '{ft}' — its lessons now ride "
             f"with weight in the morning prompt")
    nlog.close()
    if settled_clues:
        emit(f"  ({settled_clues} tracked clue(s) marked done)")
    if swept:
        emit(f"  ({swept} stale clue(s) expired unverified — 28-day broom)")

    log = open_nap_log()
    nap = next((n for n in log.pending() if n["date"] == day.isoformat()), None)
    if nap is None:
        print(f"No unsettled nap for {day} (pass day or already settled).")
        log.close()
        return 0
    race = next((r for r in results if r.race_id == nap["race_id"]), None)
    me = next((rr for rr in race.runners if rr.horse_id == nap["horse_id"]), None) if race else None
    if me is None:
        print(f"Result for {nap['horse']} not in yet for {day}.")
        log.close()
        return 0
    won = me.position == 1
    log.settle(day, won=won, sp_dec=me.sp_dec)
    sh = next((x for x in log.pending_shadow() if x["date"] == day.isoformat()), None)
    if sh is not None:
        shr = next((r for r in results if r.race_id == sh["race_id"]), None)
        shm = next((rr for rr in shr.runners if rr.horse_id == sh["horse_id"]), None) \
            if shr else None
        if shm is not None:
            log.settle_shadow(day, won=shm.position == 1, sp_dec=shm.sp_dec)
            out.append(f"  shadow settled: {sh['horse']} "
                       f"{'WON' if shm.position == 1 else 'lost'}")
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
    ap.add_argument("--resend", metavar="DAY",
                    help="re-EMAIL the banked nap for a day (never re-picks)")
    ap.add_argument("--guard", action="store_true",
                    help="pre-off drift guard: re-check the banked nap's price NOW")
    ap.add_argument("--email", action="store_true", help="email the output (uses SMTP env vars)")
    ap.add_argument("--force-rebank", action="store_true",
                    help="allow re-picking a day that already has a banked row "
                         "(otherwise refused — the pre-off record is sacred)")
    args = ap.parse_args()
    if args.record:
        return _record()
    if args.resend:
        return _resend(args.resend)
    if args.guard:
        return _guard()
    if args.settle:
        return _settle(args.settle, args.email)

    out: list[str] = []

    def emit(s: str = "") -> None:
        print(s)
        out.append(s)

    # THE PRE-OFF RECORD IS SACRED (2026-07-25 audit: a midday manual re-run silently
    # overwrote the morning's banked row — price at banking, drift baseline, the pick
    # itself). A day that already has a row is refused unless --force-rebank.
    _existing_log = open_nap_log()
    _existing = next((n for n in _existing_log.history()
                      if n["date"] == resolve_date(args.day).isoformat()), None)
    _existing_log.close()
    if _existing is not None and not args.force_rebank:
        was = "PASS" if _existing["won"] == -1 else _existing["horse"]
        print(f"  A row is already banked for {resolve_date(args.day)} ({was}). "
              f"Re-picking would overwrite the pre-off record.")
        print("  Use --resend to re-email it, or --force-rebank to deliberately re-pick.")
        return 0          # an intentional no-op, not a failure (set -e in trial.sh all)

    codes = ("jump", "flat") if args.both else (("flat",) if args.flat else ("jump",))
    client = get_client()
    # narrate the (slow) per-horse evidence fetch to stdout so the tool never sits SILENT
    # while it grinds — the "nothing prints" trap. These lines aren't emit()'d into the
    # email body; they're live progress only.
    print("  reading today's card…", flush=True)

    def _progress(line: str) -> None:
        print(line, flush=True)

    field = evaluate_field(client, day=args.day, codes=codes, progress=_progress)

    # THE FORWARD CLUES (#27): horses mined from past results that reappear TODAY.
    # This is the result-mining paying off on the card, not sitting in a database.
    nlog = open_nuance_log()
    tracked = {t["horse_id"]: t for t in nlog.tracked_active()}
    nlog.close()
    seen: dict[str, tuple] = {}
    for p in field:
        if p.runner.horse_id in tracked and p.runner.horse_id not in seen:
            seen[p.runner.horse_id] = (p, tracked[p.runner.horse_id])
    if seen:
        # the note narrates the PAST race that taught the clue (2026-07-25 audit:
        # 'ran on to finish 2nd' against today's race label read like a result that
        # hadn't happened yet) — the clue's date now leads every line, and the full
        # dump is capped: the signal was drowning in ~60 lines about gated races
        emit("  ★ TRACKED HORSES RUN TODAY (clues mined from past results, #27):")
        for p, t in list(seen.values())[:12]:
            tag = "FOLLOW" if t["angle"] == "follow" else "OPPOSE"
            cond = f"  [{t['conditions']}]" if t["conditions"] else ""
            emit(f"    {tag} {p.runner.horse:22} {p.race.course} {p.race.off_time} "
                 f"— from its {t['date']} run: {t['note']}{cond}")
        if len(seen) > 12:
            emit(f"    … and {len(seen) - 12} more tracked lead(s) (learn --tracked)")
        emit("")

    if not field:
        emit("No nap — nothing readable stands up today. Discipline is a position.")
        _bank_pass(resolve_date(args.day), "nothing readable on the card")
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
        _bank_pass(resolve_date(args.day), "every contender crossed off by the gates")
        _maybe_email(out, "Nap — no bet today", args.email)
        return 0

    # THE MORNING DEEP READ (2026-07-05 — the master: "you can find a winner, just
    # look harder; stop stupid picks"). The engine only SHORTLISTS; the deep model
    # (with the franking tools) reads the candidate races form-first and picks THE
    # race and THE horse — or earns a pass race by race. Fallback: the engine's
    # strongest survivor, honestly labelled as the shallow pick.
    nap = survivors[0]
    deep_case: list[str] = []
    mp = None
    try:
        from racing_edge.ai.reason import get_investigator, resolve_model
        from racing_edge.report.restudy import render_preread
        from racing_edge.study.investigate import TOOLS, make_executor
        from racing_edge.study.morningread import (
            NAP_SYSTEM,
            build_nap_prompt,
            parse_morning_pick,
        )
        # candidate races come from the survivor ranking, but the deep read sees the
        # WHOLE field of each (audit: "the deep read only sees 4 horses; Green Sky at
        # 9/1 is exactly the horse it can't weigh"). All picks per race, all histories.
        all_by_race: dict[str, list] = {}
        for p in field:
            all_by_race.setdefault(p.race.race_id, []).append(p)
        # NEUTRAL EYES IN THE READING ROOM (the master, 2026-07-26: 'every race is
        # unique... you create a concrete rule and then rule out everything — look at
        # all the horses properly with a neutral lens and you might find a gem').
        # Candidacy is no longer survivors-only: the top races by best pick enter the
        # exam REGARDLESS of flags — the flags ride along as printed WARNINGS the case
        # must answer. Laws stay at the betting window (the floor, the LEAN cap, the
        # mechanical fallback's gates), never over the reader's eyes. This replaces
        # the survivors-only rule and the narrow top-class door it made necessary.
        cand_order: list[str] = []
        for p in field:                      # field is rank-sorted, flagged included
            if p.race.race_id not in cand_order:
                cand_order.append(p.race.race_id)
            if len(cand_order) >= 3:
                break
        # a race carrying an active FOLLOW horse earns the 4th candidate slot (audit:
        # tracked clues could never promote a race into the shortlist)
        for _hid, (tp, t) in seen.items():
            if (t["angle"] == "follow" and tp.race.race_id not in cand_order
                    and len(cand_order) < 4):
                cand_order.append(tp.race.race_id)
        cand_races = [all_by_race[rid] for rid in cand_order[:4]]
        candidates = []
        for picks in cand_races:
            r0 = picks[0].race
            label = f"{r0.course} {r0.off_time}"
            hists = {p.runner.horse_id: p.history for p in picks}
            race_flags = sorted({f for p in picks
                                 for f in _race_gate_flags(p.conviction.flags)})
            warn = ("  ⚠ RACE WARNINGS (cautions, not blindfolds — a pick here must "
                    "ANSWER each one in its case, and is LEAN at best): "
                    + "; ".join(race_flags) + "\n" if race_flags else "")
            candidates.append((label, warn + render_preread(r0, hists)))
        # max_steps=6 (2026-07-25 audit: rules 4+8 demand ~2 lookups per candidate
        # race — franking the key form AND checking the danger — and at 4 the model
        # ran dry mid-frank on a 3-race Saturday shortlist)
        deep = get_investigator("nap", TOOLS,
                                make_executor(client, cand_races[0][0].race),
                                max_steps=6)
        if deep is None:
            emit("  (deep read OFF — no ANTHROPIC_API_KEY; falling back to the "
                 "shallow engine pick)")
        else:
            # the student's own notes go into the exam — assembled by the PURE
            # build_lessons (tested: a banked loss + its autopsy MUST reach the
            # morning prompt; the coroner found this wire cut while credits burned)
            from racing_edge.study.morningread import build_lessons
            _llog = open_nap_log()
            _hist = _llog.history()
            _strike = _llog.strike_rate()
            _llog.close()
            nlog2 = open_nuance_log()
            # leads about candidate races ride FIRST (the [:8] cut was dropping the
            # only actionable leads in favour of gated-race colour), each with its
            # clue DATE and a CONFLICT note when it points against the engine's read
            _surv_ids = {p.runner.horse_id for p in survivors}
            _cand_ids = set(cand_order[:4])

            def _lead_row(tp, t) -> dict:
                conflict = ""
                if t["angle"] == "oppose" and tp.runner.horse_id in _surv_ids:
                    conflict = "engine ranks this horse a SURVIVOR — the lead conflicts"
                elif t["angle"] == "follow" and tp.conviction.flags:
                    conflict = ("engine flags this horse "
                                f"({tp.conviction.flags[0]}) — the lead conflicts")
                return {"angle": t["angle"], "horse": t["horse"], "date": t["date"],
                        "course": tp.race.course, "off_time": tp.race.off_time,
                        "note": t["note"], "conflict": conflict}

            _leads = sorted(seen.values(),
                            key=lambda pt: pt[0].race.race_id not in _cand_ids)
            lesson_lines = build_lessons(
                _hist, _strike, nlog2.all(),
                [_lead_row(tp, t) for tp, t in _leads],
                nlog2.rule_tally())
            nlog2.close()
            print(f"  deep read: {resolve_model('nap')} on "
                  f"{len(candidates)} candidate race(s), "
                  f"{len(lesson_lines)} banked lesson(s) in hand…", flush=True)
            text, trail = deep(NAP_SYSTEM,
                               build_nap_prompt(candidates, "\n".join(lesson_lines)))
            for t in trail:
                print(f"      🔎 {t}", flush=True)
            mp = parse_morning_pick(text)
            if mp.ok and mp.is_pass:
                emit("  DEEP READ: PASS earned, race by race:")
                emit(f"    {mp.pass_reason}")
                emit("  No nap today — a pass argued on facts beats a stupid pick.")
                _bank_pass(resolve_date(args.day), f"deep-read pass: {mp.pass_reason}")
                _maybe_email(out, "Nap — no bet today (pass earned)", args.email)
                return 0
            # match the horse WITHIN the race the model named (2026-07-25 audit:
            # name-only matching across all candidates could bank a duplicate name
            # against the wrong race); fall back to name-only with a loud warning
            def _match(require_label: bool):
                for picks in cand_races:
                    label_ok = (not require_label or not mp.race_label
                                or mp.race_label.strip().lower().startswith(
                                    picks[0].race.course.strip().lower()))
                    if not label_ok:
                        continue
                    for p in picks:
                        if (mp.horse and p.runner.horse.strip().lower()
                                == mp.horse.strip().lower()):
                            return p
                return None

            chosen = _match(require_label=True)
            if chosen is None and mp.horse:
                chosen = _match(require_label=False)
                if chosen is not None:
                    emit(f"  ⚠ race label '{mp.race_label}' did not match the chosen "
                         f"horse's race ({chosen.race.course} {chosen.race.off_time}) "
                         f"— matched by name only; verify before trusting.")
            if mp.ok and chosen is not None:
                nap = chosen
                deep_case = [f"  DEEP READ ({resolve_model('nap')}) — the case:",
                             f"    race readable: {mp.race_readable_because}",
                             f"    {mp.case}",
                             f"    THE DANGER: {mp.danger_horse} — {mp.danger_case}",
                             f"    beaten because: {mp.danger_beaten}"]
                deep_case += [f"    ✗ crossed: {x}" for x in mp.crossed_off]
                if mp.cite:
                    deep_case.append(f"    rests on: {' | '.join(mp.cite)}")
                if mp.owed:
                    deep_case.append(f"    OWED: {mp.owed}")
            else:
                emit("  (deep read gave no usable pick — falling back to the shallow "
                     "engine pick; raw kept in the task log)")
                print(f"  raw: {mp.raw[:300]}", flush=True)
    except Exception as exc:                      # the deep read must never kill the bank
        emit(f"  (deep read failed: {exc.__class__.__name__} — shallow engine pick used)")

    # standing guard (rule #26): the two decisive facts the brief CAN'T see — never
    # invent them, never cross off or nap on a guessed run-style or a stale price.
    emit("  ⚠ DECISIVE FACTS OWED — do NOT invent (rule #26):")
    emit("     · live market MOVE (backed/drifted) — a forecast price is not the market")
    emit("     · run-STYLE / manner — who leads, who's held up (the comments door)")

    # FRANK = VETO, not a downgrade (audit fix 2: under the old code a hollow-win pick
    # still got banked as a "declinable lean" — Chepstow would have banked even without
    # the exposure gate). A thin frank crosses the pick off and we fall to the next.
    # FRANK = TIEBREAKER, restored to the master's #15 (2026-07-26: 'franking is a
    # tiebreaker' — the student had promoted it to an executioner; the Saturday
    # wipe-out was the price). A thin frank is a stated CON on the ledger — it
    # caps confidence at LEAN — never a veto, never a re-pick.
    from racing_edge.study.frank import frank_form
    frank_thin_deep = False
    fr = frank_form(client, nap.runner.horse_id, nap.history, code=nap.race.code)
    if fr.is_thin:
        frank_thin_deep = True
        emit(f"  ⚠ FRANK THIN ({fr.note}) — a con on the ledger: LEAN at best, "
             f"and the case must carry the form question openly.")

    c, r = nap.conviction, nap.race

    # THE PROFILE FLOOR (audit fix 1: the winning profile advised the prompt but never
    # blocked the bank). Every winner matched it; both losers broke it. The bank now
    # requires: WELL-IN mark, Class 4 or better (unknown class allowed — Irish cards),
    # and an anchored market. Fail = no bet, with the reasons said out loud.
    from racing_edge.domain.mark import mark_read
    _mr = mark_read(nap.runner.official_rating, nap.history, code=nap.race.code)
    delta = _mr.delta
    race_fav = min((p.price for p in field
                    if p.race.race_id == r.race_id and p.price), default=None)
    # FALLBACK DISCIPLINE (2026-07-21: three of six losers were shallow fallback
    # picks at conviction 3 — the bare minimum under the then-inflated lens count,
    # banked when the deep read errored). Reader unavailable => the engine pick must
    # carry a WINNING-ERA core (4+ lens FAMILIES including well-in — the banked
    # winners' shape: mark + course + market + one more) or the day is a pass.
    if not deep_case:
        if nap.conviction.score < 4 or not nap.conviction.well_in:
            emit(f"  ✗ FALLBACK TOO THIN: deep read unavailable and the engine pick "
                 f"({nap.runner.horse}, conv {nap.conviction.score}) lacks the "
                 f"winning-era core — no bet without the reader.")
            _bank_pass(resolve_date(args.day),
                       f"deep read unavailable; engine fallback too thin "
                       f"(conv {nap.conviction.score})")
            _maybe_email(out, "Nap — no bet today (fallback too thin)", args.email)
            return 0

    # THE MARK IS SACRED — never a pick that isn't well-in, and never one whose
    # well-in anchor is from a dead era (2026-07-25 Woodstock audit: 'WELL-IN -7lb'
    # against a win older than the visible history is a placer profile, not a
    # missed handicapper). Non-negotiable.
    if delta is None or delta > 0 or _mr.stale:
        why_mark = ("STALE anchor — " + _mr.verdict if _mr.stale else
                    f"mark delta {delta if delta is not None else 'OWED'}")
        emit(f"  ✗ PROFILE FLOOR: {nap.runner.horse} is not soundly WELL-IN "
             f"({why_mark}) — no bet.")
        _bank_pass(resolve_date(args.day),
                   f"profile floor: {nap.runner.horse} not soundly well-in "
                   f"({why_mark})")
        _maybe_email(out, "Nap — no bet today (not well-in)", args.email)
        return 0
    # class and anchor are ARGUABLE — an argued multi-fact deep case may override them
    # as a LEAN (Ebony Maw, 2026-07-06: the reader found the 12.0 rematch winner and
    # the fitted class/price floor threw it away — the number-cruncher overruling the
    # form reader, the exact thing the master said he does not want). Never CONFIDENT
    # off-profile, and the shallow engine pick gets no such licence.
    soft_fails = []
    if r.race_class is not None and r.race_class > 4:
        soft_fails.append(f"class Cl{r.race_class}")
    _shape, _conc = market_shape([p.price for p in field
                                  if p.race.race_id == r.race_id and p.price])
    if race_fav is None or _shape == "OPEN":
        soft_fails.append(f"no market anchor (fav {race_fav}, "
                          f"top-3 concentration {_conc:.2f})")
    off_profile = bool(soft_fails)
    # the bypass needs more than eloquence (regression audit: an LLM cites 3 facts
    # every single time — the bar filtered nothing). An off-profile case is arguable
    # only in a race the gates did NOT flag: the Ebony Maw race was READABLE (a
    # rematch, a false favourite); a gated race arguing itself off-profile is exactly
    # the eloquent-loser signature.
    # only STRUCTURAL gates kill the off-profile licence (the master, 2026-07-26:
    # price cautions are shape, not law — an argued case may answer an open market
    # or a big field and bank as a LEAN; unexposed fields, bottom grade and the AW
    # remain hard because no case can argue marks into existence)
    _STRUCTURAL = ("novice in disguise", "bottom-grade", "all-weather")
    race_gated = any(any(g in f for g in _STRUCTURAL) for f in c.flags)
    argued = (bool(deep_case) and mp is not None and len(mp.cite) >= 3
              and not race_gated)
    if off_profile and not argued:
        why = ("the race itself is gated — no off-profile licence in a flagged race"
               if race_gated and deep_case else
               "no argued multi-fact case to override")
        emit(f"  ✗ PROFILE FLOOR: {nap.runner.horse} — {'; '.join(soft_fails)} and "
             f"{why}. No bet beats a stupid pick.")
        _bank_pass(resolve_date(args.day),
                   f"profile floor: {'; '.join(soft_fails)} — {why}")
        _maybe_email(out, "Nap — no bet today (profile floor)", args.email)
        return 0
    if off_profile:
        emit(f"  ⚠ OFF-PROFILE ({'; '.join(soft_fails)}) — allowed on an argued case "
             f"({len(mp.cite)} cited facts), as a LEAN only.")

    # the deep read's own verdict decides CONFIDENT when it made the pick — but
    # off-profile is NEVER confident, and neither is a pick the engine flagged (the
    # reader may overrule the cruncher's red flags, but only ever as a LEAN)
    deep_conf = mp.confidence if deep_case and mp is not None else ""
    if deep_case and c.flags:
        emit(f"  ⚠ the engine flags this horse ({', '.join(c.flags)}) — the reader "
             f"may overrule, but never at full confidence. LEAN only.")
    confident = ((deep_conf == "confident") if deep_case else c.confident) \
        and not off_profile and not c.flags and not frank_thin_deep
    _ew = ew_advice(nap.price, r.field_size)
    if _ew:
        emit(f"  instrument: {_ew}")

    tag = "CONFIDENT NAP" if confident else "best candidate — NOT confident (declinable)"
    emit(f"  {tag}: {nap.runner.horse}  —  {r.course} {r.off_time} ({r.race_type})")
    for line in deep_case:
        emit(line)
    emit(f"  conviction {c.score}: {', '.join(c.aligned) or 'thin'}")
    emit(f"  frank (#5/#15): {fr.note}")
    if c.flags:
        emit(f"  FLAGS: {', '.join(c.flags)}")
    if not c.mark_known:
        emit("  ⚠ the MARK was not readable — never a confident nap without it.")
    evidence = build_evidence(r, client)
    emit("\n" + render_scorecard(build_scorecard(r, evidence)))

    day = nap.race.date
    log = open_nap_log()
    # the CASE banks with the pick — the night study interrogates the real reasoning,
    # not a guess at it (audit: "a self-critique of an invented memory")
    case_text = "\n".join(deep_case) if deep_case else \
        f"engine pick: conviction {c.score} — {', '.join(c.aligned) or 'thin'}"
    log.record(day=day, race_id=r.race_id, course=r.course, horse=nap.runner.horse,
               horse_id=nap.runner.horse_id, price=nap.price, score=c.score,
               confident=confident, case=case_text, deep_conf=deep_conf,
               aligned=" | ".join(c.aligned))
    # THE SHADOW: the mechanical engine's own top survivor, banked silently for the
    # A/B record (one machine, two ledgers — the record decides which method earns
    # the stakes). Costs nothing: it was already computed.
    eng = survivors[0]
    log.record_shadow(day=day, race_id=eng.race.race_id, course=eng.race.course,
                      horse=eng.runner.horse, horse_id=eng.runner.horse_id,
                      price=eng.price, score=eng.conviction.score)
    if eng.runner.horse_id != nap.runner.horse_id:
        emit(f"  shadow (engine method): {eng.runner.horse} — {eng.race.course} "
             f"{eng.race.off_time} (paper only, banked for the A/B record)")
    log.close()
    emit(f"\n  banked the nap for {day} — settle it tomorrow with --settle {day}.")
    _maybe_email(out, f"{tag}: {nap.runner.horse} — {r.course} {r.off_time} ({day})", args.email)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
