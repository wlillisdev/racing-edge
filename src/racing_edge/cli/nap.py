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
    sw, sn = log.shadow_strike()
    if sn:
        print(f"  SHADOW (engine method): {sw}/{sn} won ({100 * sw / sn:.0f}%) — "
              f"the A/B the record is running between the deep read and the engine.")
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
    if now >= banked * 1.2:
        msg = (f"⚠ STAND OFF — {n['horse']} has DRIFTED {banked} -> {now}. "
               f"The drift rule has been right every time (Perfidia, Artiste d'Ainay): "
               f"the money is leaving. Keep the stake in your pocket. "
               f"(The pick stays on the ledger — this guards the stake, not the record.)")
        print(f"  {msg}")
        send(f"STAND OFF: {n['horse']} drifting ({banked}->{now})", msg,
             title="Drift guard", subtitle="racing-edge form trial")
    elif now <= banked * 0.9:
        msg = f"✓ {n['horse']} BACKED {banked} -> {now} — the market agrees with the pick."
        print(f"  {msg}")
        send(f"Backed: {n['horse']} ({banked}->{now})", msg,
             title="Drift guard", subtitle="racing-edge form trial")
    else:
        print(f"  {n['horse']} steady ({banked} -> {now}) — no signal, no email.")
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
    from racing_edge.cli._common import open_nuance_log
    nlog = open_nuance_log()
    tracked = {t["horse_id"]: t for t in nlog.tracked_active()}
    nlog.close()
    seen: dict[str, tuple] = {}
    for p in field:
        if p.runner.horse_id in tracked and p.runner.horse_id not in seen:
            seen[p.runner.horse_id] = (p, tracked[p.runner.horse_id])
    if seen:
        emit("  ★ TRACKED HORSES RUN TODAY (clues mined from past results, #27):")
        for p, t in seen.values():
            tag = "FOLLOW" if t["angle"] == "follow" else "OPPOSE"
            cond = f"  [{t['conditions']}]" if t["conditions"] else ""
            emit(f"    {tag} {p.runner.horse:22} {p.race.course} {p.race.off_time} "
                 f"— {t['note']}{cond}")
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
        cand_order: list[str] = []
        for p in survivors:
            if p.race.race_id not in cand_order:
                cand_order.append(p.race.race_id)
        cand_order = cand_order[:4]
        # a race carrying an active FOLLOW horse earns a candidate slot (audit: tracked
        # clues could never promote a race into the shortlist)
        for _hid, (tp, t) in seen.items():
            if t["angle"] == "follow" and tp.race.race_id not in cand_order:
                cand_order.append(tp.race.race_id)
        cand_races = [all_by_race[rid] for rid in cand_order[:3]]
        candidates = []
        for picks in cand_races:
            r0 = picks[0].race
            label = f"{r0.course} {r0.off_time}"
            hists = {p.runner.horse_id: p.history for p in picks}
            candidates.append((label, render_preread(r0, hists)))
        deep = get_investigator("nap", TOOLS, make_executor(client, cand_races[0][0].race))
        if deep is None:
            emit("  (deep read OFF — no ANTHROPIC_API_KEY; falling back to the "
                 "shallow engine pick)")
        else:
            # the student's own notes go into the exam: validated nuances + EVERY
            # tracked horse running today + rules under fire on the scoreboard
            lesson_lines: list[str] = []
            nlog2 = open_nuance_log()
            validated = [n for n in nlog2.all() if n["status"] == "validated"]
            lesson_lines += [f"- MASTER-VALIDATED: {n['nuance']}" for n in validated]
            # tracked clues are UNVERIFIED leads (2026-07-21: two losers were built on
            # tracked clues my old header mislabelled 'master validated' — the model
            # believed the label). Honest label + explicit weight instruction.
            tracked_lines = [
                f"- unverified lead ({t['angle']}): {t['horse']} ({tp.race.course} "
                f"{tp.race.off_time}): {t['note'][:120]}"
                for tp, t in list(seen.values())[:8]
            ]
            if tracked_lines:
                lesson_lines.append("UNVERIFIED TRACKED LEADS — colour only, weigh "
                                    "lightly, NEVER the foundation of a case:")
                lesson_lines += tracked_lines
            lesson_lines += [
                f"- RULE UNDER FIRE: {t['rule']} contradicted "
                f"{t['contradicts']}-{t['supports']} by results — weigh it lightly"
                for t in nlog2.rule_tally()
                if t["contradicts"] >= 3 and t["contradicts"] > t["supports"]
            ]
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
            chosen = next((p for picks in cand_races for p in picks
                           if mp.horse and p.runner.horse.strip().lower()
                           == mp.horse.strip().lower()), None)
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
    from racing_edge.study.frank import frank_form
    fr = None
    fallbacks = [nap] + [s for s in survivors if s is not nap]
    for cand in fallbacks[:3]:
        f = frank_form(client, cand.runner.horse_id, cand.history)
        if f.is_thin:
            emit(f"  ✗ FRANK VETO: {cand.runner.horse} — {f.note} "
                 f"(a win in a bad race is a mirage; re-picking)")
            if cand is nap:
                deep_case = []          # the vetoed pick's case no longer applies
            continue
        nap, fr = cand, f
        break
    if fr is None:
        emit("  No nap — every candidate's form franked HOLLOW. Discipline is a position.")
        _bank_pass(resolve_date(args.day), "all candidates franked hollow")
        _maybe_email(out, "Nap — no bet today (franked hollow)", args.email)
        return 0

    c, r = nap.conviction, nap.race

    # THE PROFILE FLOOR (audit fix 1: the winning profile advised the prompt but never
    # blocked the bank). Every winner matched it; both losers broke it. The bank now
    # requires: WELL-IN mark, Class 4 or better (unknown class allowed — Irish cards),
    # and an anchored market. Fail = no bet, with the reasons said out loud.
    from racing_edge.domain.mark import mark_read
    delta = mark_read(nap.runner.official_rating, nap.history,
                      code=nap.race.code).delta
    race_fav = min((p.price for p in field
                    if p.race.race_id == r.race_id and p.price), default=None)
    # FALLBACK DISCIPLINE (2026-07-21: three of six losers were shallow fallback
    # picks at conviction 3 — the bare minimum under today's inflated lens count,
    # banked when the deep read errored). Reader unavailable => the engine pick must
    # carry a WINNING-ERA core (conv >= 5 including well-in) or the day is a pass.
    if not deep_case:
        if nap.conviction.score < 5 or not any(
                "well-in" in a for a in nap.conviction.aligned):
            emit(f"  ✗ FALLBACK TOO THIN: deep read unavailable and the engine pick "
                 f"({nap.runner.horse}, conv {nap.conviction.score}) lacks the "
                 f"winning-era core — no bet without the reader.")
            _bank_pass(resolve_date(args.day),
                       f"deep read unavailable; engine fallback too thin "
                       f"(conv {nap.conviction.score})")
            _maybe_email(out, "Nap — no bet today (fallback too thin)", args.email)
            return 0

    # THE MARK IS SACRED — never a pick that isn't well-in. Non-negotiable.
    if delta is None or delta > 0:
        emit(f"  ✗ PROFILE FLOOR: {nap.runner.horse} is not WELL-IN "
             f"(mark delta {delta if delta is not None else 'OWED'}) — no bet.")
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
    if race_fav is None or race_fav >= 5.0:
        soft_fails.append(f"no market anchor (fav {race_fav})")
    off_profile = bool(soft_fails)
    argued = bool(deep_case) and mp is not None and len(mp.cite) >= 3
    if off_profile and not argued:
        emit(f"  ✗ PROFILE FLOOR: {nap.runner.horse} — {'; '.join(soft_fails)} and no "
             f"argued multi-fact case to override. No bet beats a stupid pick.")
        _maybe_email(out, "Nap — no bet today (profile floor)", args.email)
        return 0
    if off_profile:
        emit(f"  ⚠ OFF-PROFILE ({'; '.join(soft_fails)}) — allowed on an argued case "
             f"({len(mp.cite)} cited facts), as a LEAN only.")

    # the deep read's own verdict decides CONFIDENT when it made the pick —
    # but off-profile is NEVER confident
    deep_conf = mp.confidence if deep_case and mp is not None else ""
    confident = ((deep_conf == "confident") if deep_case else c.confident) \
        and not off_profile
    if nap.price and nap.price >= 8.0:
        emit(f"  instrument (#28): EACH-WAY at {nap.price} — the place is the net, "
             f"the win is the payday.")

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
               confident=confident, case=case_text, deep_conf=deep_conf)
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
