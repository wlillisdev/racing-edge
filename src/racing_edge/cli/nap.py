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
from racing_edge.domain.units import norm_horse_name  # noqa: F401 — one site, re-exported
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


def _best_floor_fit(survivors, field):
    """The engine's best PROFILE-FIT survivor — well-in, mark read, 4+ ticks,
    decent class, market not OPEN. THE no-silent-week rule (2026-07-31, the
    master: 'no naps all week — what has broken now'): NO pass is banked while
    one of these stands, whichever path tried to pass — the reader's own pass,
    the mark floor, or the class/anchor floor. The reader's reasoning still
    rides in the case; the bank is always LEAN."""
    from racing_edge.pipeline.nap import market_shape as _ms
    for sv in survivors:
        if not (sv.conviction.well_in and sv.conviction.mark_known
                and sv.conviction.score >= 4):
            continue
        if sv.race.race_class is not None and sv.race.race_class > 4:
            continue
        shape, _ = _ms([p.price for p in field
                        if p.race.race_id == sv.race.race_id and p.price])
        if shape != "OPEN":
            return sv
    return None


def _git_stamp() -> str:
    """The running code, named in the email itself (the master, 2026-09-01:
    'how do I know this is pushed and will actually run?') — the box pulls
    main before every task, and this line is the receipt: the sha printed
    in the email IS the commit that picked. Never crashes a run."""
    try:
        import subprocess
        from pathlib import Path
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True,
            text=True, timeout=5,
            cwd=Path(__file__).resolve().parent).stdout.strip()
        return f"\n\nengine code: {sha}" if sha else ""
    except Exception:
        return ""


def _maybe_email(buf: list[str], subject: str, email: bool) -> None:
    """Email the buffered output if --email was set. Never crashes the run."""
    if not email:
        return
    from racing_edge.report.mail import configured, recipient, send
    if not configured():
        print("  (--email set, but EMAIL_SENDER/PASSWORD/RECIPIENT aren't in the env — not sent)")
        return
    ok = send(subject, "\n".join(buf) + _git_stamp(), title=subject,
              subtitle="racing-edge form trial")
    # the delivery VERDICT, verified in the mailbox itself — not just 'sent'
    print(f"  email to {recipient() or '?'}: {ok if ok else 'FAILED — check the SMTP env'}")


class _EngineBankNow(Exception):
    """Control-flow sentinel (engine-first mode): the case is written, the pick
    is fixed — jump straight from the reader to the bank, skipping every
    reader-mode floor and fallback below the try block."""


def _lessons_with_rulings(lesson_lines: list[str]) -> str:
    """THE MASTER'S RULINGS ride into the morning prompt above the banked
    lessons (audit 2026-09-02, STEP 6: 'one table the reads actually recall at
    the point of use ... every recall counted'). Never crashes the read."""
    try:
        from racing_edge.study.rulings import recall, render
        block = render(recall(limit=25))     # the newest 25: his voice, not a wall of it
    except Exception as exc:                         # the read outranks the memory
        print(f"  ⚠ rulings not recalled: {exc.__class__.__name__}", flush=True)
        block = ""
    return (block + "\n\n" if block else "") + "\n".join(lesson_lines)


def _record_nap(log, day, r, nap, c, confident, case_text, deep_conf, mp, args) -> None:
    """The one bank call, with the read's claims riding in the row."""
    log.record(day=day, race_id=r.race_id, course=r.course, horse=nap.runner.horse,
               horse_id=nap.runner.horse_id, price=nap.price, score=c.score,
               confident=confident, case=case_text, deep_conf=deep_conf,
               aligned=" | ".join(c.aligned), race_quality=nap.race_quality,
               force=args.force_rebank,
               danger=(mp.danger_horse if mp is not None else ""),
               crossed=("|".join(mp.crossed_off) if mp is not None else ""),
               my_price=(mp.my_price if mp is not None else None))


def _evidence_for(race, client):
    """The race's evidence WITHOUT a second fetch (fourth audit 2026-09-02): the
    field read already paid ~47 API calls for this race and kept the result on
    evaluate_field.last_evidence. Only a race the read never saw is fetched."""
    from racing_edge.pipeline.nap import evaluate_field as _ef
    kept = getattr(_ef, "last_evidence", {}).get(race.race_id)
    return kept if kept else build_evidence(race, client)


def _bank_pass(day, reason: str) -> None:
    """A no-bet day is still a ledger day — banked with its reason (never overwrites
    a real pick: record_pass only fires on paths where none was banked)."""
    log = open_nap_log()
    try:
        log.record_pass(day=day, reason=reason)
    except ValueError as exc:      # refused at the write point (bot A) — said, not raised
        print(f"  ✗ pass NOT banked: {exc}", flush=True)
    finally:
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


# --------------------------------------------------------------------------- #
# THE BOARD (the master, 2026-09-02, ruling on the third audit: "the market is
# one price snapshot — laws 4b/4c/4d/4g have no data at all"). Two snapshots a
# day, every priced runner: 07:30 from the morning read, 12:30 from the guard.
# The difference is the board's CHARACTER — steamers, drifters, the nap race's
# whole board — read mechanically and emailed before racing. Flip-flop needs a
# third point; that is the next snapshot, on his word.
# --------------------------------------------------------------------------- #

def _field_prices(field) -> dict:
    out: dict = {}
    for p in field:
        if p.price:
            out.setdefault(p.race.race_id, {"course": p.race.course,
                                            "off": p.race.off_time, "runners": {}})
            out[p.race.race_id]["runners"][p.runner.horse_id] = [p.runner.horse, p.price]
    return out


def _cards_prices(cards) -> dict:
    out: dict = {}
    for r in cards:
        for x in r.runners:
            if x.odds.consensus and x.odds.consensus > 1:
                out.setdefault(r.race_id, {"course": r.course, "off": r.off_time,
                                           "runners": {}})
                out[r.race_id]["runners"][x.horse_id] = [x.horse, x.odds.consensus]
    return out


def _board_snapshot(day, tag: str, prices: dict) -> None:
    import json
    from pathlib import Path as _P
    d = _P("data/market_snapshots")
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{day.isoformat()}-{tag}.json").write_text(json.dumps(prices))


def board_moves(morning: dict, now: dict, steam: float = 0.85, drift: float = 1.30,
                mid: dict | None = None):
    """Pure: every runner priced in both snapshots -> (race_id, horse, then, now,
    ratio, label) with label steamer / drifter / steady. The thresholds are the
    guard's own bands (2026-07-26, the master: graded bands, not a cliff).
    With a MIDDLE snapshot (09:30, from health — the third snapshot the flip-flop
    needed, 2026-09-02): a runner that steamed then drifted, or drifted then
    steamed, by those same bands is a FLIP-FLOP — law 4g's board character."""
    rows = []
    for rid, race in now.items():
        m = morning.get(rid, {}).get("runners", {})
        md = (mid or {}).get(rid, {}).get("runners", {})
        for hid, (horse, price) in race.get("runners", {}).items():
            then = m.get(hid, [None, None])[1]
            if not then or not price:
                continue
            ratio = price / then
            label = "STEAMER" if ratio <= steam else "DRIFTER" if ratio >= drift else "steady"
            between = md.get(hid, [None, None])[1]
            if between:
                r1, r2 = between / then, price / between
                if (r1 <= steam and r2 >= drift) or (r1 >= drift and r2 <= steam):
                    label = "FLIP-FLOP"
            rows.append((rid, horse, then, price, round(ratio, 2), label))
    return rows


def _board_read(day, cards) -> None:
    import json
    from pathlib import Path as _P
    now = _cards_prices(cards)
    _board_snapshot(day, "1230", now)
    f = _P("data/market_snapshots") / f"{day.isoformat()}-0730.json"
    if not f.exists():
        print("  board: no 07:30 snapshot — the read starts tomorrow", flush=True)
        return
    morning = json.loads(f.read_text())
    _mid = _P("data/market_snapshots") / f"{day.isoformat()}-0930.json"
    mid = json.loads(_mid.read_text()) if _mid.exists() else None
    rows = board_moves(morning, now, mid=mid)
    movers = [x for x in rows if x[5] != "steady"]
    lines = [f"THE BOARD at 12:30 v 07:30 — {len(rows)} runners priced both times, "
             f"{len(movers)} mover(s)"]
    for rid, horse, then, price, ratio, label in sorted(movers, key=lambda x: x[4]):
        race = now[rid]
        lines.append(f"  {label:8} {horse:22} {then} -> {price}  ({race['course']} {race['off']})")
    log = open_nap_log()
    n = next((x for x in log.pending() if x["date"] == day.isoformat()), None)
    log.close()
    if n and n["race_id"] in now:
        lines.append(f"\n  THE NAP'S RACE ({now[n['race_id']]['course']} {now[n['race_id']]['off']}):")
        for rid, horse, then, price, ratio, label in sorted(
                (x for x in rows if x[0] == n["race_id"]), key=lambda x: x[3]):
            lines.append(f"    {horse:22} {then} -> {price}  {label}")
    text = "\n".join(lines)
    print(text)
    if movers:
        from racing_edge.report.mail import configured, send
        if configured():
            send(f"The board 12:30: {len(movers)} mover(s)", text,
                 title="The board", subtitle="racing-edge form trial")


def _guard() -> int:
    """The pre-off DRIFT GUARD (audit fix 4). The move called the winner four times in
    one day and the drift saved the Perfidia stake — yet the banked nap was never
    re-checked. Compares the pick's price NOW vs at banking: a 20%+ drift = STAND OFF
    (emailed); firmed = confirmation. The ledger is untouched either way — this guards
    the STAKE, not the record."""
    from racing_edge.data.normalise import racecards_from_raw
    day = resolve_date("today")
    cards = racecards_from_raw(get_client().racecards("today"))
    # THE BOARD, SNAPSHOT TWO + THE READ (the master, 2026-09-02): the whole
    # card's prices now against 07:30 — steamers, drifters, the nap race's
    # board — emailed before racing so law 4g finally has data behind it.
    try:
        _board_read(day, cards)
    except Exception as _e:
        print(f"  ⚠ board read failed: {_e.__class__.__name__}", flush=True)
    log = open_nap_log()
    n = next((x for x in log.pending() if x["date"] == day.isoformat()), None)
    log.close()
    if not n:
        print("  No unsettled nap banked for today — nothing to guard.")
        return 0
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


VOID_AFTER_DAYS = 7     # a pick with no result after a week is voided WITH its reason
                        # and the console command — a hygiene bound, not a betting rule
                        # (audit 2026-09-02; REVERT-IF the master rules a longer wait)


def _settle_tables(day, results, log, emit) -> dict[str, str]:
    """Settle the day's nap / shadow / favline rows against `results` — ONE
    definition for all three (audit 2026-09-02). Non-runner statuses and a
    horse absent from a found race's runners VOID with a reason (the bet never
    ran); fallers/pulled-up RAN and lose; a race not in the results stays open
    for the backlog sweep. Returns {table: outcome line} for the rows touched."""
    from racing_edge.study.naplog import NapLog
    out: dict[str, str] = {}
    pend = log.pending_all()
    settlers = {"nap": log.settle, "shadow": log.settle_shadow,
                "favline": log.settle_favline}
    for table in ("nap", "shadow", "favline"):
        row = next((x for x in pend[table] if x["date"] == day.isoformat()), None)
        if row is None:
            continue
        race = next((r for r in results if r.race_id == row["race_id"]), None)
        if race is None:
            out[table] = f"{row['horse']} — no result yet (race {row['race_id']} not in the feed)"
            continue
        me = next((rr for rr in race.runners if rr.horse_id == row["horse_id"]), None)
        if me is None:
            log.void(day, f"{row['horse']} absent from the result's runners — "
                          "non-runner/withdrawn", table=table)
            out[table] = f"{row['horse']} VOID — absent from the result (non-runner)"
            continue
        status = (getattr(me, "status", "") or "").upper()
        if status in NapLog.NON_RUNNER:
            log.void(day, f"{row['horse']} non-runner ({status})", table=table)
            out[table] = f"{row['horse']} VOID — non-runner ({status})"
            continue
        if me.position is None and not status:
            # second audit 2026-09-02 (bot B): a null position with NO status
            # string is how a feed marks a withdrawn horse — it is not a beaten
            # one. A void names the uncertainty; a loss would invent a bet.
            log.void(day, f"{row['horse']} no finishing position and no status in "
                          "the result — treated as a non-runner", table=table)
            out[table] = f"{row['horse']} VOID — no position, no status (non-runner)"
            continue
        won = me.position == 1
        settlers[table](day, won=won, sp_dec=me.sp_dec)
        out[table] = (f"{row['horse']} {'WON' if won else 'unplaced'} "
                      f"({me.position or status or '?'}) at SP {me.sp_dec or '?'}")
        if table == "nap":
            grade = grade_read_claims(row, race, me)
            if grade:
                log.grade_read(day, grade)
                out[table] += f" | READ GRADED: {grade}"
    return out


def grade_read_claims(row: dict, race, me) -> str:
    """THE READ'S OWN CLAIMS, MARKED (audit 2026-09-02, the master: "the edge
    is joining the dots") — the named danger, the crossed-off list and the
    reader's own price were produced every morning and graded by nobody. Now:
      danger  -> WON / beat us / behind us / absent
      crossed -> did the WINNER stand in the crossed-off list (a cross that
                 crossed the winner is the read's loudest lesson)
      price   -> my price v the SP (shorter than SP = we called value the
                 market did not give; longer = the market liked it more)
    Pure: takes the banked row, the result race and our runner."""
    parts: list[str] = []
    runners = list(getattr(race, "runners", []) or [])

    def _name(rr) -> str:
        return norm_horse_name(getattr(rr, "horse", "") or "")

    def _pos(rr):
        p = getattr(rr, "position", None)
        return p if isinstance(p, int) else None

    danger = norm_horse_name(row.get("danger") or "")
    if danger:
        dr = next((rr for rr in runners if _name(rr) == danger), None)
        if dr is None:
            parts.append("danger absent")
        elif _pos(dr) == 1:
            parts.append("danger WON")
        elif _pos(dr) is not None and (_pos(me) is None or _pos(dr) < _pos(me)):
            parts.append(f"danger beat us ({_pos(dr)} v {_pos(me) or 'unplaced'})")
        else:
            parts.append("danger behind us")
    crossed = [norm_horse_name(x.split(" — ")[0].split(" - ")[0])
               for x in (row.get("crossed") or "").split("|") if x.strip()]
    if crossed:
        winner = next((rr for rr in runners if _pos(rr) == 1), None)
        wname = _name(winner) if winner is not None else ""
        parts.append("winner was CROSSED OFF" if wname and any(
            c and (c == wname or c in wname or wname in c) for c in crossed)
                     else "crossed-off all beaten")
    mp = row.get("my_price")
    sp = getattr(me, "sp_dec", None)
    if mp and sp:
        parts.append(f"my price {mp} {'shorter than' if mp < sp else 'longer than' if mp > sp else 'equal to'} SP {sp}")
    return "; ".join(parts)


def _settle_yardstick(day, results, emit) -> None:
    """THE YARDSTICK LEDGER settles beside the record (the master, 2026-09-03:
    the stored races as learning data): every runner's morning read for the
    day gets its position, SP and won. Never fatal — the record comes first."""
    try:
        from racing_edge.school.yardstick import settle_day as _ysettle
        n = _ysettle(day, results)
        if n:
            emit(f"  yardstick {day}: {n} morning reads graded")
    except Exception as exc:
        emit(f"  ⚠ yardstick {day} not graded: {exc.__class__.__name__}: {str(exc)[:80]}")


def _sweep_backlog(day, log, emit, fetch=None) -> None:
    """Every open row OLDER than `day`, in every table: fetch that date's results
    once and settle; still open past VOID_AFTER_DAYS -> VOID with the reason and
    the console command. Nothing stays open unnamed."""
    from datetime import date as _date
    if fetch is None:
        def fetch(ds: str):
            return results_from_raw(get_client().results_by_date(ds))
    pend = log.pending_all()
    dates = sorted({r["date"] for rows in pend.values() for r in rows
                    if r["date"] < day.isoformat()})
    for ds in dates:
        d = _date.fromisoformat(ds)
        try:
            res = fetch(ds)
        except Exception as exc:
            emit(f"  ⚠ backlog {ds}: results fetch failed ({exc.__class__.__name__}) "
                 "— still open")
            res = None
        if res is not None:
            for t, o in _settle_tables(d, res, log, emit).items():
                emit(f"  backlog {ds} {t}: {o}")
            _settle_yardstick(d, res, emit)
        age = (day - d).days
        still = log.pending_all()
        for t in ("nap", "shadow", "favline"):
            if not any(r["date"] == ds for r in still[t]):
                continue
            cmd = f"PYTHONPATH=src venv/bin/python -m racing_edge.cli.nap --settle {ds}"
            if age >= VOID_AFTER_DAYS:
                log.void(d, f"no result after {age} days — voided by the backlog "
                            f"sweep; console: {cmd}", table=t)
                emit(f"  backlog {ds} {t}: VOID — no result after {age} days")
            else:
                emit(f"  backlog {ds} {t}: still open ({age}d) — console: {cmd}")


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
             f"settled this run; the backlog sweep retries it tomorrow")
        _maybe_email(out, f"Settle FAILED — results fetch error ({day})", email)
        return 1
    nlog = open_nuance_log()
    # EVERY active clue per horse, not one (audit 2026-09-02: a dict keyed on
    # horse_id silently dropped a second angle on the same horse before settle)
    tracked_by_id: dict[str, list] = {}
    for t in nlog.tracked_active():
        if t["horse_id"]:
            tracked_by_id.setdefault(t["horse_id"], []).append(t)
    settled_clues = 0
    for res in results:
        for rr in res.runners:
            for t in tracked_by_id.pop(rr.horse_id, []):
                # SP in the stamp (ROI audit: without it the clue stream can never be
                # judged in money or against the fav baseline)
                outcome = (f"ran {day.isoformat()}, "
                           f"{'WON' if rr.position == 1 else f'pos {rr.position or rr.status}'}"
                           + (f", SP {rr.sp_dec}" if rr.sp_dec else ""))
                hit = (rr.position == 1) == (t["angle"] == "follow")
                settled_clues += nlog.settle_tracked(rr.horse_id, outcome=outcome, held=hit)
                emit(f"  tracked clue settled: [{t['angle']}] {t['horse']} — "
                     f"{outcome} ({'clue HELD' if hit else 'clue missed'})")
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
    # EVERY LEDGER TABLE SETTLES THROUGH ONE FUNCTION (audit 2026-09-02): nap,
    # shadow and fav line — non-runners VOID with a reason, absentees VOID,
    # finishers settle; a race with no result yet stays open for the sweep.
    outcome = _settle_tables(day, results, log, emit)
    for _t, _o in outcome.items():
        emit(f"  {day} {_t}: {_o}")
    _settle_yardstick(day, results, emit)
    # MARK THE MORNING OPINIONS (the master, 2026-08-18: 'this is the test').
    # Every race the engine studied this morning is graded against tonight's
    # winners and fed to the ladder as the 'engine' policy.
    try:
        import csv as _csv
        from pathlib import Path as _Path
        _ofile = _Path("data/school/opinions") / f"{day.isoformat()}.csv"
        if _ofile.exists():
            _n = _w = _bn = _bw = _tw = _wt = 0
            _ret = _bret = 0.0
            # COVERAGE (dog-school lesson 2026-08-24: "nothing recorded what
            # the fetch MISSED"): a studied race with no result tonight was
            # previously a silent `continue` — invisible rot. Now every one
            # is named, loud, so a thin results feed can't read as green.
            _missing: list[str] = []
            with open(_ofile, newline="") as _fh:
                for _row in _csv.reader(_fh):
                    _r = next((x for x in results if x.race_id == _row[0]), None)
                    _me = next((rr for rr in _r.runners
                                if rr.horse_id == _row[3]), None) if _r else None
                    if _me is None:
                        _missing.append(f"{_row[1]} {_row[2]}")
                        continue
                    _n += 1
                    # the two-column record (2026-08-22): betting races
                    # (fingerprint score >= 2) judged apart from the dreck
                    _bet = len(_row) > 6 and str(_row[6]).lstrip("-").isdigit() \
                        and int(_row[6]) >= 2
                    if _bet:
                        _bn += 1
                    # the twin-choice gauge (2026-08-22): was the winner in my
                    # two, and did I take the wrong twin?
                    _winner = next((rr.horse_id for rr in _r.runners
                                    if rr.position == 1), None)
                    if _winner and _winner == _row[3]:
                        _tw += 1
                    elif _winner and len(_row) > 7 and _winner == _row[7]:
                        _tw += 1
                        _wt += 1
                    if _me.position == 1:
                        _w += 1
                        _ret += _me.sp_dec or 0.0
                        if _bet:
                            _bw += 1
                            _bret += _me.sp_dec or 0.0
            if _n:
                from racing_edge.school.daily import append_policy_rows as _apr
                _prow = [(day.isoformat(), "engine", _n, _w, _ret)]
                if _bn:
                    _prow.append((day.isoformat(), "engine-bet", _bn, _bw, _bret))
                # THE NEW BEAST'S ARITHMETIC ON ITS OWN LINE (the master, 2026-09-03:
                # "has it improved or made the system worse? how can we evaluate this
                # without waiting months" — 20-40 opinions a day pass the 50-pick bar
                # in two days; the ladder shows engine-v2 against engine within a week)
                from racing_edge.study.naplog import version as _ver
                if _ver(day) == "v2":
                    _prow.append((day.isoformat(), "engine-v2", _n, _w, _ret))
                    if _bn:
                        _prow.append((day.isoformat(), "engine-bet-v2", _bn, _bw, _bret))
                _apr(_Path("data/school/daily_policy.csv"), _prow)
                emit(f"  MORNING OPINIONS marked: {_w}/{_n} races read right "
                     f"({100.0 * _w / _n:.0f}%), level stakes {_ret - _n:+.1f}pt "
                     f"— the day's full test, fed to the ladder")
                if _bn:
                    emit(f"  BETTING RACES (fingerprint >= 2): {_bw}/{_bn} read "
                         f"right — the column the system is judged on")
                emit(f"  TWIN CHOICE: winner in my two {_tw}/{_n}; wrong twin "
                     f"taken {_wt} — close-and-fixable if the first number is "
                     f"high, deeper if it is low")
            if _missing:
                emit(f"  ⚠ COVERAGE: {len(_missing)} studied race(s) got NO "
                     f"result tonight — {', '.join(_missing[:8])}"
                     + (" …" if len(_missing) > 8 else "")
                     + " — a thin results feed, NOT an empty day. Marked "
                     "figures above are PROVISIONAL until these settle.")
    except Exception as _e:
        emit(f"  ⚠ morning opinions not marked: {_e}")
    # THE BACKLOG SWEEP (audit 2026-09-02: '--settle today' never revisited a
    # missed day; the comment "retries tomorrow" was a comment, not code)
    _sweep_backlog(day, log, emit)
    # WHAT WE MEASURE (the master, 2026-09-02): the nap column is the ladder's
    # champion — every settled pick rides into the policy ledger as 'nap'
    # (whole history, deduped: the first settle after this lands backfills)
    try:
        from pathlib import Path as _PP
        from racing_edge.school.daily import append_policy_rows as _apr2
        from racing_edge.school.ladder import nap_policy_rows as _npr
        _apr2(_PP("data/school/daily_policy.csv"), _npr(log.history()))
    except Exception as _e:
        emit(f"  ⚠ nap column not written to the policy ledger: {_e.__class__.__name__}")
    from pathlib import Path as _TP
    log.export_text(_TP("data/nap_record.csv"))      # the text twin, rewritten whole
    log.close()
    _nap_line = outcome.get("nap")
    if _nap_line is None:
        print(f"No unsettled nap for {day} (pass day or already settled).")
        _maybe_email(out, f"Settle — {day} (no nap to settle)", email)
        return 0
    _maybe_email(out, f"Nap settled — {_nap_line} ({day})", email)
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

    from racing_edge.data import evidence as _evmod
    _evmod.owed_notes.clear()                 # one run, one list
    field = evaluate_field(client, day=args.day, codes=codes, progress=_progress)
    # THE SIGNPOSTS (the master, 2026-09-05: "my AI back in the day... implement
    # all of these, they are another dot"): combo, rating clear, the yard here
    # by type, the same race last year, fresh, cold yard — one block per runner
    # for the reader, one column in the yardstick for the record. ONE results
    # call (last year's week), the corpus already on disk. Never fatal.
    _signposts: dict = {}
    try:
        from pathlib import Path as _P
        from racing_edge.school import signposts as _spmod
        from racing_edge.school.mine import load_corpus as _load_corpus
        _races = list({p.race.race_id: p.race for p in field}.values())
        _day = resolve_date(args.day)
        try:
            _corpus = _load_corpus(_P("data/school/raw"))
        except Exception:
            _corpus = None
        # law #29 (the master, 2026-08-31; again 2026-09-05 after two losses:
        # "past winners give key clues to find a potential winner"): one
        # results window per year back, the whole card matched against each
        _ly = []
        for _w in _spmod.past_windows(_day):
            try:
                _ly.append(client.results_range(*_w))
            except Exception as _e:
                print(f"  ⚠ past winners {_w[0][:4]} not read: {_e.__class__.__name__}",
                      flush=True)
        _signposts = _spmod.build(_day, _races,
                                  getattr(evaluate_field, "last_evidence", {}),
                                  corpus_races=_corpus, last_year_raw=_ly)
        print(f"  signposts: {sum(1 for k in _signposts if not k.startswith('race:'))} "
              f"runners carry a dot", flush=True)
    except Exception as _e:
        print(f"  ⚠ signposts not built: {_e.__class__.__name__}: {str(_e)[:80]}",
              flush=True)
    # THE YARDSTICK LEDGER (the master, 2026-09-03: "the stored races as
    # learning data... the calibration of the system"): every runner's read,
    # banked before anything is chosen, graded at settle. Never fatal.
    try:
        from racing_edge.school.yardstick import bank as _bank_yardstick
        _yp = _bank_yardstick(resolve_date(args.day), field, signposts=_signposts)
        print(f"  yardstick banked: {len(field)} reads → {_yp}", flush=True)
    except Exception as _e:
        print(f"  ⚠ yardstick not banked: {_e.__class__.__name__}: {str(_e)[:80]}",
              flush=True)
    # THE BOARD, SNAPSHOT ONE (the master, 2026-09-02: the market was one number
    # and laws 4b/4c/4d/4g had no data): every priced runner's 07:30 price is
    # kept so the 12:30 guard can read the whole card's character against it.
    try:
        _board_snapshot(resolve_date(args.day), "0730",
                        {p.race.race_id: {} for p in field} and _field_prices(field))
    except Exception as _e:
        print(f"  ⚠ board snapshot not written: {_e.__class__.__name__}", flush=True)
    # EVIDENCE OWED, in the email not just the console (third audit, bot P1:
    # a history-fetch failure printed to stdout and the emailed sheet never
    # showed it — an unmeasured horse looked measured)
    try:
        from racing_edge.data.evidence import owed_notes as _owed
        if _owed:
            emit(f"  ⚠ EVIDENCE OWED — {len(_owed)} lens fetch(es) failed; those "
                 "horses are measured on LESS than the sheet implies:")
            for _n in _owed[:12]:
                emit(f"    · {_n}")
            if len(_owed) > 12:
                emit(f"    · … {len(_owed) - 12} more in the task log")
    except Exception:
        pass

    # THE MORNING OPINIONS (the master, 2026-08-18: 'you should study the
    # form of every race each day, then look at the winners in the evening,
    # this is the test, and then learn from the results, it is not rocket
    # science'): the engine already forms an opinion on EVERY race to choose
    # its nap — from today it keeps all of them. One line per race (its
    # top-ranked runner), banked pre-off, marked at settle, fed to the
    # ladder as the 'engine' policy so the whole card grades the brain daily.
    try:
        import csv as _csv
        from pathlib import Path as _Path
        from racing_edge.pipeline.nap import _rank_key as _rk
        _oday = resolve_date(args.day).isoformat()
        # keep the TOP TWO per race (2026-08-22, the twin-choice gauge — the
        # master: the winner stands in a group of three or four; the skill
        # that pays is taking the right one of the last two)
        _byrace: dict[str, list] = {}
        for _p in field:
            _byrace.setdefault(_p.race.race_id, []).append(_p)
        _odir = _Path("data/school/opinions")
        _odir.mkdir(parents=True, exist_ok=True)
        with open(_odir / f"{_oday}.csv", "w", newline="") as _fh:
            _w = _csv.writer(_fh)
            _best = {}
            for _rid, _ps in _byrace.items():
                _ps.sort(key=_rk, reverse=True)
                _best[_rid] = _ps[0]
                _p, _second = _ps[0], (_ps[1] if len(_ps) > 1 else None)
                _w.writerow([_p.race.race_id, _p.race.course, _p.race.off_time,
                             _p.runner.horse_id, _p.runner.horse,
                             _p.price or 0, _p.race_quality,
                             _second.runner.horse_id if _second else ""])
        print(f"  morning opinions banked: {len(_best)} race(s) — marked at settle",
              flush=True)
    except Exception as _e:                                    # never kill the nap
        print(f"  ⚠ morning opinions not banked: {_e}", flush=True)

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
        # a caution warns but no longer erases (2026-08-22) — the case must answer it
        warn = f"  ⚠ must answer: {'; '.join(c.cautions)}" if c.cautions else ""
        emit(f"    • {p.runner.horse:22} {p.race.course} {p.race.off_time}  "
             f"conv {c.score}{mark}: {', '.join(c.aligned) or 'thin'}{warn}")
    emit("")

    # ═══ THE FLIP (the master, 2026-08-08: 'flip it — what we are doing clearly
    # is not working... our shadow selections were at least placing'). The
    # record's A/B agreed: the mechanical engine's top survivor (the shadow
    # column) out-struck the deep reader's chosen picks. So the ENGINE now
    # SELECTS — the exact selection the shadow scored with, no floors, no
    # re-picks — and the reader is demoted to CASE-WRITER with one power: a
    # veto on a cited disqualifying fact. Restore the old reader-selects mode
    # with NAP_MODE=reader. REVERT-IF: engine-led naps go 0/8, or strike below
    # the reader era's 36% over the next 15 settled.
    import os as _os
    engine_mode = _os.environ.get("NAP_MODE", "engine").strip().lower() != "reader"
    if engine_mode:
        emit("  MODE: ENGINE-FIRST — the engine selects (the shadow method, "
             "promoted by the record); the reader writes the case and may only "
             "veto on a cited disqualifying fact.")
        if not survivors:
            emit("  ENGINE-FIRST: no survivor stands — the engine has no pick. "
                 "Discipline is a position.")
            _bank_pass(resolve_date(args.day), "engine-first: no survivors")
            _maybe_email(out, "Nap — no bet today (engine: no survivors)",
                         args.email)
            return 0
    elif not survivors:
        # THE FOURTH TRAPDOOR (2026-08-01, found in the ledger's own words: 'every
        # contender crossed off by the gates' — a Saturday passed before the reader
        # ever opened its eyes). Neutral eyes mean the READER still reads: flags are
        # cautions in its candidates, the floors still guard the bank, and with no
        # survivors there is no fallback — the reader's case must stand alone or
        # the day passes honestly AFTER the reading, never before it.
        emit("  ⚠ every engine survivor crossed off — the reader reads the flagged "
             "card regardless (cautions, not blindfolds); floors still guard the bank.")

    # THE MORNING DEEP READ (2026-07-05 — the master: "you can find a winner, just
    # look harder; stop stupid picks"). The engine only SHORTLISTS; the deep model
    # (with the franking tools) reads the candidate races form-first and picks THE
    # race and THE horse — or earns a pass race by race. Fallback: the engine's
    # strongest survivor, honestly labelled as the shallow pick.
    nap = survivors[0] if survivors else field[0]
    # THE CORNERED-DAY KLAXON (2026-08-27, the master: 'we need to fix this,
    # selection was bizarre' — Lady Kara, last at 5/2, picked only because the
    # gates had erased every flat race and left nothing but jumps dreck; same
    # mechanism as Max Of Stars 08-22). When the best survivor's own race
    # scores below the betting-race bar, the day is CORNERED, not chosen:
    # a NAMED PASS under law 5 (the master's ruling 2026-09-02, below) — the
    # old "still banks, loudly labelled" regime is gone.
    from racing_edge.pipeline.nap import BETTING_BAR as _BAR
    cornered = bool(survivors) and getattr(nap, "race_quality", 0) < _BAR
    if cornered:
        # THE CORNERED DAY IS A PASS (the master, 2026-09-02, ruling on the
        # third audit: the forced 'duty only' pick was the dreck column's
        # whole supply — law 5, a pass is CORRECT when no candidate matches,
        # now outranks the one-pick-a-day habit). Named race by race.
        _why = ("CORNERED DAY: no betting race survived the gates (best survivor "
                f"{nap.runner.horse} in {nap.race.course} {nap.race.off_time} scores "
                f"race quality {getattr(nap, 'race_quality', 0)} < bar {_BAR}) — "
                "law 5: a pass is the correct pick")
        emit(f"  ✗ {_why}")
        _bank_pass(resolve_date(args.day), _why)
        _maybe_email(out, "Nap — no bet today (cornered: no betting race)", args.email)
        return 0
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
        # three candidates, not four (2026-07-27 cost audit): the fourth race's
        # full-field readout bought little and billed daily; a FOLLOW race takes
        # the third slot when one runs
        if engine_mode:
            # ENGINE-FIRST: one race — the engine's pick's race. The reader
            # reads it in full to write the case (or find a disqualifier); it
            # chooses nothing.
            # TWO races, not one (the master, 2026-09-02): the engine's pick's
            # race first, then the next-best DISTINCT race — so the reader sees
            # the runner-up race too and can object with a cited fact.
            cand_order: list[str] = [nap.race.race_id]
            for p in field:
                if p.race.race_id not in cand_order:
                    cand_order.append(p.race.race_id)
                    break
        else:
            cand_order = []
            for p in field:                  # field is rank-sorted, flagged included
                if p.race.race_id not in cand_order:
                    cand_order.append(p.race.race_id)
                if len(cand_order) >= 2:
                    break
            for _hid, (tp, t) in seen.items():
                if (t["angle"] == "follow" and tp.race.race_id not in cand_order
                        and len(cand_order) < 3):
                    cand_order.append(tp.race.race_id)
            for p in field:
                if len(cand_order) >= 3:
                    break
                if p.race.race_id not in cand_order:
                    cand_order.append(p.race.race_id)
        cand_races = [all_by_race[rid] for rid in cand_order[:3]]
        candidates = []
        from racing_edge.school.sitting import sitting_floor as _floor
        for picks in cand_races:
            r0 = picks[0].race
            label = f"{r0.course} {r0.off_time}"
            # LAW 5c AT THE MACHINE'S OWN READ (second audit 2026-09-02: the wall
            # had no caller): a race whose class, distance or favourite the read
            # cannot name is not read — a named pass line, never an order.
            _favp = min((p for p in picks if p.price), key=lambda p: p.price,
                        default=None)
            _wall = _floor(r0.race_class,
                           getattr(r0, "distance_f", None) or getattr(r0, "distance", None),
                           _favp.runner.horse if _favp is not None else None)
            if _wall:
                emit(f"  ✗ {label}: {_wall}")
                continue
            hists = {p.runner.horse_id: p.history for p in picks}
            race_flags = sorted({f for p in picks
                                 for f in _race_gate_flags(p.conviction.flags)})
            warn = ("  ⚠ RACE WARNINGS (cautions, not blindfolds — a pick here must "
                    "ANSWER each one in its case, and is LEAN at best): "
                    + "; ".join(race_flags) + "\n" if race_flags else "")
            # THE ENGINE'S YARDSTICK RIDES INTO THE READ (third audit 2026-09-02,
            # bot P1: every priced runner was measured, and the reader never saw a
            # single per-horse finding — it argued blind to the manner reads,
            # the cautions and the flags). Law 5b at the reader's desk.
            _yard = ["  ENGINE'S YARDSTICK — every priced runner measured; the case "
                     "must ANSWER each caution and flag it argues past:"]
            for _p in sorted(picks, key=lambda x: (x.price or 999.0)):
                _c = _p.conviction
                _yard.append(f"    {_p.runner.horse} @{_p.price or '?'}: conv {_c.score}"
                             + (f" — for: {', '.join(_c.aligned)}" if _c.aligned else "")
                             + (f" | cautions: {'; '.join(_c.cautions)}" if _c.cautions else "")
                             + (f" | FLAGS: {'; '.join(_c.flags)}" if _c.flags else "")
                             + ("" if _c.mark_known else " | mark OWED"))
            # THE PAST WINNERS THROUGH THE HORSES (the master, 2026-09-05: "find
            # a workaround... not just the easy way"): for the races the reader
            # sees, the roll is extended by id beyond the date door's 12 months.
            try:
                from racing_edge.school import signposts as _spmod2
                _roll = _spmod2.deepen(client, r0, hists, _signposts, resolve_date(args.day))
                if _roll:
                    print(f"  past winners {label}: {len(_roll)} runnings "
                          f"({_roll[-1]['date']} to {_roll[0]['date']})", flush=True)
            except Exception as _e:
                print(f"  ⚠ past winners {label} not deepened: {_e.__class__.__name__}",
                      flush=True)
            candidates.append((label, warn + "\n".join(_yard) + "\n"
                               + render_preread(r0, hists, extra=_signposts)))
        # max_steps=6 (2026-07-25 audit: rules 4+8 demand ~2 lookups per candidate
        # race — franking the key form AND checking the danger — and at 4 the model
        # ran dry mid-frank on a 3-race Saturday shortlist)
        # max_tokens 6000 up front (2026-07-27 cost audit: the checklist-era cases
        # outgrew 3000, so EVERY morning truncated and regenerated at double size —
        # the flagship answer was being paid for twice, daily)
        deep = get_investigator("nap", TOOLS,
                                make_executor(client, cand_races[0][0].race),
                                max_steps=6, max_tokens=16000)
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
            # THE MEMORY, RECALLED (the master, 2026-09-03: "store it and
            # remember and recall it... 30 years of experience"): for every
            # candidate race, what won a race of this shape before and WHY,
            # from the why ledger — the read walks in knowing the place.
            try:
                from racing_edge.domain.units import book_code as _bc
                from racing_edge.school.why import recall as _why_recall
                _mem: list[str] = []
                for _picks in cand_races:
                    _r0 = _picks[0].race
                    _lines = _why_recall(_r0.course, _bc(_r0.race_type) or "",
                                         _r0.race_class, _r0.distance_f, n=6)
                    if _lines:
                        _mem.append(f"MEMORY — what won here before, and why "
                                    f"({_r0.course} {_r0.off_time}):")
                        _mem.extend(f"  · {x}" for x in _lines)
                if _mem:
                    lesson_lines = list(lesson_lines) + [""] + _mem
                    print(f"  memory recalled: {sum(1 for x in _mem if x.startswith('  ·'))} "
                          "past results of this shape, with their whys", flush=True)
            except Exception as _e:                  # the read outranks the memory
                print(f"  ⚠ memory not recalled: {_e.__class__.__name__}", flush=True)
            print(f"  deep read: {resolve_model('nap')} on "
                  f"{len(candidates)} candidate race(s), "
                  f"{len(lesson_lines)} banked lesson(s) in hand…", flush=True)
            if engine_mode:
                from racing_edge.study.morningread import VETO_SYSTEM
                _fixed = (f"\n\nTHE ENGINE'S PICK (FIXED — you do not choose): "
                          f"{nap.runner.horse} in {nap.race.course} "
                          f"{nap.race.off_time}. Write its case with that exact "
                          f"race and horse, or veto (pass=true) with the cited "
                          f"disqualifying fact as pass_reason.")
                # THE RULEBOOK RIDES INTO ENGINE MODE (third audit 2026-09-02, bot
                # P2 — the finding of the night): under the default NAP_MODE the
                # model was sent VETO_SYSTEM ALONE; NAP_SYSTEM, every law in the
                # master's own words, reached the reader only in a mode nobody
                # runs. The veto clause now sits BELOW the rulebook, not instead
                # of it (prompt caching keeps the cost of the fixed text low).
                text, trail = deep(NAP_SYSTEM + "\n\n" + VETO_SYSTEM,
                                   build_nap_prompt(candidates,
                                                    _lessons_with_rulings(lesson_lines))
                                   + _fixed)
            else:
                text, trail = deep(NAP_SYSTEM,
                                   build_nap_prompt(candidates,
                                                    _lessons_with_rulings(lesson_lines)))
            for t in trail:
                print(f"      🔎 {t}", flush=True)
            mp = parse_morning_pick(text)
            if engine_mode and mp.ok and mp.is_pass:
                # THE VETO — one power, one duty: the fact rides in the ledger,
                # and the vetoed engine pick banks in the shadow column so the
                # RECORD judges every veto (a veto that keeps killing winners
                # will hang by its own rope).
                # THE VETO IS CUT TO AN OBJECTION (the master, 2026-08-19:
                # 'your vetos are crippling us' and 'if you put your hand in
                # the fire and get burnt do you do it again' — the pre-agreed
                # trigger fired the same day: vetoed King Roly WON at 6.0
                # after six kill-vetoes in ten days, five of them citing the
                # SAME stale-anchor fact the engine can no longer even
                # nominate on since the well-in demotion). The reader keeps
                # its voice and loses the handbrake: pass=true now RECORDS a
                # strong objection, the engine's pick banks and emails
                # regardless at LEAN, and the record judges whether the
                # reader's doubts predict losses. No more no-bet days by
                # reader's hand — the record starves without picks.
                emit(f"  READER OBJECTION (recorded — the pick STANDS, LEAN): "
                     f"{mp.pass_reason}")
                deep_case = [
                    "  READER OBJECTION (2026-08-19 law: objection recorded, "
                    "pick stands at LEAN — the record judges the doubt):",
                    f"    {mp.pass_reason}"]
                mp = None
                raise _EngineBankNow
            if engine_mode:
                # agreement path: the pick is FIXED — the case attaches only if
                # the reader wrote it for the engine's horse; a re-pick attempt
                # is not a power it has.
                _same = bool(mp.horse) and (norm_horse_name(mp.horse)
                                            == norm_horse_name(nap.runner.horse))
                if _same and mp.case.strip():
                    deep_case = [
                        f"  DEEP READ ({resolve_model('nap')}) — the case for "
                        f"the ENGINE'S pick:",
                        f"    {mp.case}",
                        f"    THE DANGER: {mp.danger_horse} — {mp.danger_case}",
                        f"    beaten because: {mp.danger_beaten}"]
                    if mp.cite:
                        deep_case.append(f"    rests on: {' | '.join(mp.cite)}")
                    if mp.owed:
                        deep_case.append(f"    OWED: {mp.owed}")
                    if not mp.ok:
                        # second audit 2026-09-02 (bot E): a terse or half-built
                        # case for the RIGHT horse used to be thrown away whole
                        # and the email degraded to a one-line blurb. It is kept,
                        # named incomplete, and can never be CONFIDENT.
                        import dataclasses as _dc
                        deep_case.append("    ⚠ INCOMPLETE CASE (danger, profile "
                                         "or length missing) — LEAN at best")
                        mp = _dc.replace(mp, confidence="lean")
                elif mp.horse and not _same:
                    emit(f"  ⚠ reader attempted a re-pick ('{mp.horse}') — not "
                         f"its power in engine mode; the engine pick banks "
                         f"with the mechanical case.")
                    mp = None      # its claims belong to the wrong horse (bot A)
                else:
                    emit("  (no usable case from the reader — the engine pick "
                         "banks with the mechanical case)")
                    mp = None
                raise _EngineBankNow                     # skip reader-mode logic below
            if mp.ok and mp.is_pass:
                emit("  DEEP READ: argued a PASS, race by race:")
                emit(f"    {mp.pass_reason}")
                _fb = _best_floor_fit(survivors, field)
                if _fb is not None:
                    emit(f"  …but a floor-fit survivor stands: banking the engine's "
                         f"{_fb.runner.horse} as the day's LEAN (the reader's pass "
                         f"reasons ride in the case for the night study to judge).")
                    nap = _fb
                    deep_case = [f"  engine pick (the reader passed): "
                                 f"{mp.pass_reason[:300]}"]
                    mp = None
                else:
                    emit("  No nap today — a pass argued on facts, and no floor-fit "
                         "survivor stands.")
                    _bank_pass(resolve_date(args.day),
                               f"deep-read pass: {mp.pass_reason}")
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
                        if (mp.horse and norm_horse_name(p.runner.horse)
                                == norm_horse_name(mp.horse)):
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
    except _EngineBankNow:
        pass                       # engine mode: case written (or not) — bank the pick
    except Exception as exc:                      # the deep read must never kill the bank
        mp = None          # a half-parsed pick must not bank its claims (bot A)
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
    # THE DANGER IS FRANKED LIKE THE PICK (third audit, bot P6: the pick's key
    # form got a mechanical frank, the named danger's was only the model's own
    # narrative — an asymmetry that made every pick look weaker than its rival)
    try:
        _dname = norm_horse_name(mp.danger_horse) if mp is not None else ""
        _dp = next((p for p in field if p.race.race_id == nap.race.race_id
                    and norm_horse_name(p.runner.horse) == _dname), None) if _dname else None
        if _dp is not None:
            _frd = frank_form(client, _dp.runner.horse_id, _dp.history, code=nap.race.code)
            emit(f"  danger frank (#5/#15): {_dp.runner.horse} — {_frd.note}")
    except Exception as _e:
        emit(f"  danger frank OWED: {_e.__class__.__name__}")
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
    if (not engine_mode) and not deep_case:
        if not survivors or nap.conviction.score < 4 or not nap.conviction.well_in:
            emit(f"  ✗ FALLBACK TOO THIN: deep read unavailable and the engine pick "
                 f"({nap.runner.horse}, conv {nap.conviction.score}) lacks the "
                 f"winning-era core — no bet without the reader.")
            _bank_pass(resolve_date(args.day),
                       f"deep read unavailable; engine fallback too thin "
                       f"(conv {nap.conviction.score})")
            _maybe_email(out, "Nap — no bet today (fallback too thin)", args.email)
            return 0

    # THE MARK IS SACRED — never a pick that isn't well-in, and never one whose
    # well-in anchor is from a dead era (2026-07-25 Woodstock audit). Non-negotiable
    # for the BANK — but the reader's choice failing the floor must not kill the
    # day while floor-fit survivors stand (2026-07-27, the master: 'no naps since
    # all of this' — Monday passed with two conv-4 well-in survivors on the sheet).
    def _floor_fit_survivor():
        return _best_floor_fit(survivors, field)

    if (not engine_mode) and (delta is None or delta > 0 or _mr.stale):
        why_mark = ("STALE anchor — " + _mr.verdict if _mr.stale else
                    f"mark delta {delta if delta is not None else 'OWED'}")
        fb = _floor_fit_survivor()
        if fb is not None and fb.runner.horse_id != nap.runner.horse_id:
            emit(f"  ✗ floor refused the reader's choice {nap.runner.horse} "
                 f"({why_mark}) — falling back to the engine's best profile-fit "
                 f"survivor, LEAN only:")
            nap, deep_case, mp = fb, [], None
            fr = frank_form(client, nap.runner.horse_id, nap.history,
                            code=nap.race.code)
            frank_thin_deep = fr.is_thin
            c, r = nap.conviction, nap.race
            _mr = mark_read(nap.runner.official_rating, nap.history,
                            code=nap.race.code)
            delta = _mr.delta
            race_fav = min((p.price for p in field
                            if p.race.race_id == r.race_id and p.price),
                           default=None)
        else:
            emit(f"  ✗ PROFILE FLOOR: {nap.runner.horse} is not soundly WELL-IN "
                 f"({why_mark}) — and no floor-fit survivor stands. No bet.")
            _bank_pass(resolve_date(args.day),
                       f"profile floor: {nap.runner.horse} not soundly well-in "
                       f"({why_mark}); no floor-fit fallback")
            _maybe_email(out, "Nap — no bet today (not well-in)", args.email)
            return 0
    # class and anchor are ARGUABLE — an argued multi-fact deep case may override them
    # as a LEAN (Ebony Maw, 2026-07-06: the reader found the 12.0 rematch winner and
    # the fitted class/price floor threw it away — the number-cruncher overruling the
    # form reader, the exact thing the master said he does not want). Never CONFIDENT
    # off-profile; in engine mode the same licence applies, capped at LEAN (below).
    soft_fails = []
    # THE FLOORS LIVE IN ENGINE MODE TOO (the master, 2026-09-02, ruling on the
    # third audit: mark, class and anchor were dead under the default while
    # their comments claimed protection). In engine mode the pick is fixed, so
    # a floor never re-picks — it CAPS: off-profile is LEAN, never CONFIDENT.
    if engine_mode and (delta is None or delta > 0 or _mr.stale):
        soft_fails.append("mark not soundly well-in ("
                          + ("STALE anchor" if _mr.stale else
                             f"delta {delta if delta is not None else 'OWED'}") + ")")
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
        _fb2 = _best_floor_fit(survivors, field)
        if _fb2 is not None and _fb2.runner.horse_id != nap.runner.horse_id:
            emit(f"  ✗ floor refused {nap.runner.horse} ({'; '.join(soft_fails)}; "
                 f"{why}) — falling back to the engine's floor-fit "
                 f"{_fb2.runner.horse}, LEAN only.")
            nap, deep_case, mp = _fb2, [], None
            fr = frank_form(client, nap.runner.horse_id, nap.history,
                            code=nap.race.code)
            frank_thin_deep = fr.is_thin
            c, r = nap.conviction, nap.race
            _mr = mark_read(nap.runner.official_rating, nap.history,
                            code=nap.race.code)
            delta = _mr.delta
            race_fav = min((p.price for p in field
                            if p.race.race_id == r.race_id and p.price),
                           default=None)
            soft_fails, off_profile = [], False
        else:
            emit(f"  ✗ PROFILE FLOOR: {nap.runner.horse} — {'; '.join(soft_fails)} "
                 f"and {why}; no floor-fit fallback stands. No bet.")
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
        and not off_profile and not c.flags and not c.cautions \
        and not frank_thin_deep and not cornered
    # THE GLANCE DECLINE GATE (the master, 2026-08-31 — Play Me, 4th in the
    # market inside a top-3-94% shape, banked as a "declinable" lean nobody
    # declined: "we need to stop making these mistakes"): before a LEAN banks,
    # the shape book gets a veto. Confident naps pass untouched; no book, no
    # gate. A declined lean banks as a NAMED PASS — discipline is a position.
    from racing_edge.school.shapebook import glance_decline, glance_for
    _race_picks = sorted([p for p in field if p.race.race_id == r.race_id
                          and p.price], key=lambda p: p.price)
    _nap_rank = next((i + 1 for i, p in enumerate(_race_picks)
                      if p.runner.horse_id == nap.runner.horse_id), None)
    from racing_edge.domain.units import book_code as _book_code
    _code = _book_code(r.race_type)
    _glance = glance_for(_code, r.race_class, len(_race_picks),
                         _race_picks[0].price if _race_picks else None)
    _decline = glance_decline(confident, _glance, _nap_rank)
    if _decline:
        emit(f"\n  {_decline}")
        emit(f"  candidate stood down: {nap.runner.horse} — {r.course} "
             f"{r.off_time} (lean; the book's shape prior objected)")
        _bank_pass(nap.race.date, _decline)
        _maybe_email(out, f"Nap — named pass (glance decline): {r.course} "
                     f"{r.off_time}", args.email)
        return 0
    _ew = ew_advice(nap.price, r.field_size)
    if _ew:
        emit(f"  instrument: {_ew}")

    tag = "CONFIDENT NAP" if confident else "best candidate — NOT confident (declinable)"
    # the beast's version in the subject line (the master, 2026-09-02)
    from racing_edge.study.naplog import version as _version
    tag = f"[{_version(nap.race.date)}] {tag}"
    emit(f"  {tag}: {nap.runner.horse}  —  {r.course} {r.off_time} ({r.race_type})")
    for line in deep_case:
        emit(line)
    emit(f"  conviction {c.score}: {', '.join(c.aligned) or 'thin'}")
    emit(f"  frank (#5/#15): {fr.note}")
    if c.flags:
        emit(f"  FLAGS: {', '.join(c.flags)}")
    if c.cautions:
        emit(f"  CAUTIONS (warn, never erase — 2026-08-22): {', '.join(c.cautions)}"
             " — the case above must answer this or the pick is a lean, not a nap")
    if not c.mark_known:
        emit("  ⚠ the MARK was not readable — never a confident nap without it.")
    evidence = _evidence_for(r, client)          # kept from the field read — no refetch
    emit("\n" + render_scorecard(build_scorecard(r, evidence)))

    day = nap.race.date
    # THE PRE-BANK TRIPWIRE (audit 2026-09-02: the field was time-guarded once,
    # at the start of the read; the deep read then ran for minutes and nothing
    # re-checked before the row was written — scar 2026-08-24
    # banked_after_the_off). Same clock, same function, asked again NOW.
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo as _ZI
    from racing_edge.pipeline.nap import still_to_run as _str
    _now_uk = _dt.now(_ZI("Europe/London")).replace(tzinfo=None)
    if not (_str(r.off_time, _now_uk) if nap.race.date == _now_uk.date() else True):
        _why = (f"TRIPWIRE at bank time: {r.course} {r.off_time} is off or inside "
                f"the 5-minute buffer (now {_now_uk:%H:%M} UK) — a pick banked "
                "after the off is never a pick")
        emit(f"\n  ✗ {_why}")
        _bank_pass(day, _why)
        _maybe_email(out, f"Nap — named pass (tripwire): {r.course} {r.off_time}",
                     args.email)
        return 0
    log = open_nap_log()
    # THE WRITTEN EDGE (audit 2026-09-02: "does a departure from the market
    # favourite have to state its edge in writing"): the favourite of the
    # nap's race is named BEFORE the case banks, and a pick that is not the
    # favourite carries its edge line — the lenses that put it above the
    # market's horse — or the word NONE, in the record, where it can be judged.
    fav = min((p for p in field if p.race.race_id == r.race_id and p.price),
              key=lambda p: (p.price, p.runner.horse_id), default=None)
    # the CASE banks with the pick — the night study interrogates the real reasoning,
    # not a guess at it (audit: "a self-critique of an invented memory")
    case_text = "\n".join(deep_case) if deep_case else \
        f"engine pick: conviction {c.score} — {', '.join(c.aligned) or 'thin'}"
    if fav is not None and fav.runner.horse_id != nap.runner.horse_id:
        case_text += (f"\nDEPARTURE FROM THE FAVOURITE {fav.runner.horse} ({fav.price}): "
                      f"written edge = {', '.join(c.aligned) or 'NONE — thin'}")
    try:
        _record_nap(log, day, r, nap, c, confident, case_text, deep_conf, mp, args)
    except ValueError as exc:
        # a settled day, or a banked day without --force-rebank: refused at the
        # write point and said plainly — never a crash email (bot A)
        emit(f"  ✗ NOT banked: {exc}")
        log.close()
        return 1
    # THE SHADOW: the mechanical engine's own top survivor, banked silently for the
    # A/B record (one machine, two ledgers — the record decides which method earns
    # the stakes). Costs nothing: it was already computed.
    eng = survivors[0] if survivors else nap
    if (not engine_mode) or eng.runner.horse_id != nap.runner.horse_id:
        log.record_shadow(day=day, race_id=eng.race.race_id, course=eng.race.course,
                          horse=eng.runner.horse, horse_id=eng.runner.horse_id,
                          price=eng.price, score=eng.conviction.score)
    if eng.runner.horse_id != nap.runner.horse_id:
        emit(f"  shadow (engine method): {eng.runner.horse} — {eng.race.course} "
             f"{eng.race.off_time} (paper only, banked for the A/B record)")
    # THE FAV LINE (the master, 2026-08-16: 'lets do favourite and value bet,
    # what have we got to lose the information is there'): the favourite of
    # the nap's own race banks beside the pick — two bets, same race, and the
    # record judges both. No new selection rule: the market names this horse.
    if fav is not None and hasattr(log, "record_favline"):
        log.record_favline(day=day, race_id=r.race_id, course=r.course,
                           horse=fav.runner.horse, horse_id=fav.runner.horse_id,
                           price=fav.price)
        emit(f"  FAV LINE: {fav.runner.horse} at {fav.price} — "
             + ("same horse as the nap today"
                if fav.runner.horse_id == nap.runner.horse_id
                else "the market's answer in the same race, banked beside ours"))
    from pathlib import Path as _TwinPath
    log.export_text(_TwinPath("data/nap_record.csv"))     # the text twin
    log.close()
    emit(f"\n  banked the nap for {day} — settle it tomorrow with --settle {day}.")
    _maybe_email(out, f"{tag}: {nap.runner.horse} — {r.course} {r.off_time} ({day})", args.email)
    return 0


if __name__ == "__main__":
    from racing_edge.cli._common import run_guarded
    raise SystemExit(run_guarded("nap", main))
