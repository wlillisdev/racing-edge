"""LOOP HEALTH — the machine proves its own plumbing, to the MASTER, mechanically.

    python -m racing_edge.cli.health [--email]

Born 2026-07-05, the master's alarm: "I thought we were locked in — all I see is an
unreliable system full of holes. How do I know it's fixed?" Answer: you don't take
anyone's word. This reads every ledger and reports, red/green, whether each part of
the loop actually RAN and actually FED the next part. Scheduled daily, it lands in
your inbox — a silent failure anywhere in the pipeline becomes a red line within a
day, not an audit weeks later. No model, no API fetches (email aside): pure ledger
reads, nothing to hallucinate.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from racing_edge.cli._common import open_nap_log, open_nuance_log
from racing_edge.domain.units import uk_today


def _check(ok: bool, good: str, bad: str, lines: list[str]) -> bool:
    lines.append(f"  {'✓' if ok else '✗ RED:'} {good if ok else bad}")
    return ok


def _engineer_sweep(log_text: str, today: str) -> tuple[bool, list[str]]:
    """THE DAILY ENGINEER'S EYE (2026-08-01, the master: 'build in the senior
    engineer to audit the system every day'). The checks an engineer would run
    each morning over the flight recorder are MECHANICAL, so the free watchman
    runs them — no model, no tokens. (Model-driven code review stays in the
    monthly window, where code actually changes.)

    Three checks: tracebacks in today's output (must be zero — the crash net
    emails them; this is the belt to that braces), each task's runtime vs its
    own 7-day norm (slow creep is tomorrow's outage), and warning volume."""
    import re
    from datetime import datetime
    pat = re.compile(r"^=== (\S+) (\S+) UTC :: trial\.sh (\S+) (START|EXIT)")
    runs: list[tuple[str, str, float]] = []          # (date, task, seconds)
    open_runs: dict[str, tuple[str, datetime]] = {}
    for ln in log_text.splitlines():
        m = pat.match(ln)
        if not m:
            continue
        d, t, task, kind = m.groups()
        try:
            stamp = datetime.strptime(f"{d} {t}", "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if kind == "START":
            open_runs[task] = (d, stamp)
        elif task in open_runs and open_runs[task][0] == d:
            runs.append((d, task, (stamp - open_runs.pop(task)[1]).total_seconds()))
    ok = True
    out: list[str] = []
    idx = log_text.find(today)
    today_block = log_text[idx:] if idx >= 0 else ""
    tbs = today_block.count("Traceback (most recent call last)")
    if tbs:
        ok = False
        out.append(f"  ✗ RED: {tbs} traceback(s) in today's runs — something died "
                   "mid-task; the crash email names it, the log has the full story")
    parts = []
    for task in sorted({t for d, t, _ in runs if d == today}):
        secs = [s for d, t, s in runs if d == today and t == task]
        base = [s for d, t, s in runs if d < today and t == task][-7:]
        cur, avg = max(secs), (sum(base) / len(base) if base else 0.0)
        slow = avg and cur > 2 * avg and cur > 120
        parts.append(f"{task} {cur:.0f}s" + (f" (7d~{avg:.0f}s)" if avg else ""))
        if slow:
            ok = False
            out.append(f"  ✗ RED: '{task}' took {cur:.0f}s vs ~{avg:.0f}s norm — "
                       "2x slow-down; find the drag before it becomes an outage")
    if parts:
        out.append(f"  engineer's eye: runtimes {', '.join(parts)}; "
                   f"{today_block.count('⚠')} warning line(s) today")
    return ok, out


def _data_dir():
    """ONE root for everything health reads (fourth audit 2026-09-02, bot B2:
    the flight recorder read the checkout's data/, the school files read the
    cwd, the ledgers read PROJECT_DIR — three roots in one report). The
    ledgers' root wins: config.project_dir, the same door _common opens."""
    from pathlib import Path
    from racing_edge.config import get_config
    return Path(get_config().project_dir) / "data"


def main() -> int:
    ap = argparse.ArgumentParser(description="Loop health — red/green ledger report.")
    ap.add_argument("--email", action="store_true", help="email the report (SMTP env)")
    args = ap.parse_args()

    today = uk_today()
    yday = today - timedelta(days=1)
    lines: list[str] = [f"LOOP HEALTH — {today}"]
    all_ok = True

    # THE BOARD, SNAPSHOT TWO (2026-09-02: the flip-flop needed a third price
    # point; health runs at 09:30, between the read and the guard — one
    # racecards call, no model). Failure is a line, never a red.
    try:
        from racing_edge.cli.nap import _board_snapshot, _cards_prices
        from racing_edge.data import client as _cl
        from racing_edge.data.normalise import racecards_from_raw
        _cards = racecards_from_raw(_cl.get_client().racecards("today"))
        _prices = _cards_prices(_cards)
        _board_snapshot(today, "0930", _prices)
        lines.append(f"  board: 09:30 snapshot written ({len(_prices)} races)")
    except Exception as _e:
        lines.append(f"  board: 09:30 snapshot not written ({_e.__class__.__name__})")

    log = open_nap_log()
    naps = log.history()
    log.close()
    dates = {n["date"] for n in naps}
    recent = [n for n in naps if n["date"] >= (today - timedelta(days=3)).isoformat()]
    # health runs at 09:00, the nap at 07:30 — so TODAY'S row must exist by now.
    # (2026-07-13: 'yesterday counts' showed ALL GREEN while a 422 was killing every
    # morning — the watchman waved through the exact failure he exists to catch.)
    all_ok &= _check(
        today.isoformat() in dates,
        f"today's nap banked (latest {max(dates) if dates else 'never'})",
        f"NO NAP banked TODAY (latest {max(dates) if dates else 'never'}) — the 07:30 "
        "task failed or crashed; open its log on the Tasks page",
        lines)
    stale = [n for n in naps if n["won"] is None and n["date"] < yday.isoformat()]
    # the named console command rides with the alarm (audit 2026-09-02: "no pick
    # open over two days without a named cause and a named console command")
    all_ok &= _check(
        not stale,
        "no stale unsettled naps",
        f"{len(stale)} nap(s) unsettled for 2+ days ({', '.join(n['date'] for n in stale[:5])}) "
        "— the night settle's backlog sweep has not closed them; console: "
        f"PYTHONPATH=src venv/bin/python -m racing_edge.cli.nap --settle "
        f"{stale[0]['date'] if stale else 'YYYY-MM-DD'} --email  (a row with no "
        "result after 7 days is auto-voided with its reason)",
        lines)
    # only judge naps banked since the case feature existed (2026-07-06) — rows from
    # before it are legitimately caseless legacy, not a live fault
    caseless = [n for n in recent
                if n["date"] >= "2026-07-06" and not (n.get("case_text") or "").strip()]
    all_ok &= _check(
        not caseless,
        "recent naps carry their CASE (the night study reads real reasoning)",
        f"{len(caseless)} nap(s) since 2026-07-06 banked with NO case — the deep read "
        "is not running in the task env or not being stored (check the 07:30 task log "
        "for 'deep read OFF' or 'deep read failed')",
        lines)

    nlog = open_nuance_log()
    nuances = nlog.all()
    tally = nlog.rule_tally()
    tracked = nlog.tracked_active()
    nlog.close()
    fresh_cut = (today - timedelta(days=2)).isoformat()
    # A RE-DERIVED lesson is learning too (2026-08-03: the night school ran
    # perfectly — both studies re-stated banked #194, stamped as VOTES with
    # 'seen_count incremented, no new row' — and this alarm cried 'not running'
    # because it only counted NEW rows. Convergence stamps last_seen; freshness
    # honours either.)
    fresh_nu = [n for n in nuances
                if n["date"] >= fresh_cut or (n.get("last_seen") or "") >= fresh_cut]
    all_ok &= _check(
        bool(fresh_nu) or not naps,
        f"self-study flowing ({len(fresh_nu)} nuance row(s) in the last 2 days; "
        f"{sum(1 for n in nuances if n['status'] == 'validated')} validated, "
        f"{sum(1 for n in nuances if n['status'] in ('refuted', 'rejected'))} killed on record)",
        "NO nuance rows in 2+ days — the learn/night task is not running; the "
        "ledgers are starving again (the exact audit finding of 2026-07-05)",
        lines)
    all_ok &= _check(
        bool(tally) or not fresh_nu,
        f"rule scoreboard accumulating ({len(tally)} rule(s) on trial)",
        "self-studies run but NO rule evidence banked — the scoreboard pipe is broken",
        lines)
    # the silting alarm now watches the BROOM, not the backlog (2026-07-25: the old
    # 21-day count red-lined forever on legacy rows the 28-day expiry already hid
    # from the working lists — an alarm nobody can silence teaches people to ignore
    # alarms). Stale = rows STILL 'active' in the DB beyond 28 days: ~0 while the
    # nightly expire_tracked broom runs; growing = the broom is dead.
    # Count only rows that SURVIVED last night's sweep (2026-08-02: the July-4
    # clue flood crossed the 28-day line at dawn — after the 22:00 broom, before
    # tonight's — and the alarm cried 'broom dead' at a broom that had verifiably
    # swept 71 rows hours earlier. Judged at 29 days: anything still active past
    # THAT line was there when the broom last ran, which is the real dead-broom
    # signal. The daily wave gets swept tonight and is reported, not redded.)
    nlog_stale = open_nuance_log()
    stale_clues = nlog_stale.tracked_stale(29)
    todays_wave = nlog_stale.tracked_stale(28) - stale_clues
    nlog_stale.close()
    all_ok &= _check(
        stale_clues < 10,
        f"tracked list healthy ({len(tracked)} live clue(s); {todays_wave} newly "
        "expired awaiting tonight's broom)",
        f"{stale_clues} clues survived last night's broom beyond the 28-day expiry "
        "— the nightly broom (expire_tracked in --settle) is genuinely not running",
        lines)
    # THE DOORBELL (coroner 2026-07-21: 0 validated / 104 refuted — nuances have no
    # path to 'validated' without the master's ruling, and nothing ever ASKED him).
    # The freshest proposals ring here daily, with the exact commands to rule.
    pending = sorted((n for n in nuances if n["status"] == "proposed"),
                     key=lambda n: -(n.get("seen_count") or 1))[:3]
    if pending:
        lines.append(f"  AWAITING YOUR RULING ({sum(1 for n in nuances if n['status'] == 'proposed')} "
                     "proposed nuance(s) — strongest first; promote what your eye "
                     "confirms, bin the rest):")
        for n in pending:
            seen = n.get("seen_count") or 1
            tag = f" [RECURRING — independently re-derived {seen}x]" if seen >= 3 else                   (f" [seen {seen}x]" if seen > 1 else "")
            lines.append(f"    #{n['id']}{tag}: {n['nuance'][:120]}")
            lines.append(f"        promote: python -m racing_edge.cli.learn --promote {n['id']}"
                         f"   |   bin: --bin {n['id']}")
    # THE CLUE SCOREBOARD (value audit: the study bets its judgment forward nightly;
    # settlement closes each bet — this is the most direct measure of study value)
    nlog_cs = open_nuance_log()
    cs = nlog_cs.clue_scoreboard()
    nlog_cs.close()
    f, o = cs["follow"], cs["oppose"]
    if f["n"] or o["n"]:
        lines.append(
            "  clue scoreboard: follow "
            + (f"{f['hits']}/{f['n']} ({100 * f['rate']:.0f}% vs ~11% random-runner base)"
               if f["n"] else "0 settled")
            + " | oppose "
            + (f"{o['hits']}/{o['n']} ({100 * o['rate']:.0f}% — judge vs fancied only)"
               if o["n"] else "0 settled"))

    # THE FLIGHT RECORDER — did the scheduler actually LAUNCH anything today?
    # (2026-07-21: the ledger proved scheduled runs weren't happening; this separates
    # 'PythonAnywhere never started it' from 'started and died at line X')
    try:
        tail = (_data_dir() / "task_runs.log").read_text().splitlines()
        starts = [ln for ln in tail if "START" in ln and today.isoformat() in ln]
        exits = [ln for ln in tail if "EXIT" in ln and today.isoformat() in ln]
        all_ok &= _check(
            bool(starts),
            f"scheduler launched {len(starts)} run(s) today "
            f"(last exit: {exits[-1].split('EXIT')[-1].strip() if exits else 'n/a'})",
            "the scheduler NEVER LAUNCHED trial.sh today — this is a PythonAnywhere-"
            "side failure (task disabled/expired, account plan limits, or CPU quota), "
            "NOT a code failure. Check the Tasks page and account plan.",
            lines)
    except FileNotFoundError:
        lines.append("  flight recorder: no runs logged yet (starts with the next run)")
    except Exception:
        lines.append("  flight recorder: log unreadable")

    # THE DAILY ENGINEER'S EYE — mechanical audit of the flight recorder
    try:
        _txt = (_data_dir() / "task_runs.log").read_text()
        _eok, _elines = _engineer_sweep(_txt, today.isoformat())
        all_ok &= _eok
        lines.extend(_elines)
    except Exception:
        pass

    # WASTE TRIPWIRES (the master, 2026-07-27: 'stop wasting tokens, build a
    # fail-safe in — this is ridiculous'). The double-billing truncation ran silent
    # for days; now waste itself goes RED within 24 hours.
    try:
        _log_txt = (_data_dir() / "task_runs.log").read_text()
        _today_block = _log_txt[_log_txt.rfind(today.isoformat()):] \
            if today.isoformat() in _log_txt else ""
        _truncs = _today_block.count("truncated at")
        all_ok &= _check(
            _truncs == 0,
            "no truncation retries today (answers paid for once)",
            f"{_truncs} truncation retr(y/ies) today — the model is PAYING TWICE "
            "for its answers; raise that task's max_tokens",
            lines)
    except Exception:
        pass
    try:
        import csv as _csv
        from datetime import timedelta as _td2
        _by = {}
        with (_data_dir() / "model_usage.csv").open() as _f:
            for _row in _csv.DictReader(_f):
                _by.setdefault(_row["date"], 0)
                _by[_row["date"]] += (int(_row["input_tokens"])
                                      + int(_row["output_tokens"]))
        _t = _by.get(today.isoformat(), 0)
        _prev = [_by[d] for d in _by if d != today.isoformat()
                 and d >= (today - _td2(days=7)).isoformat()]
        _avg = sum(_prev) / len(_prev) if _prev else 0
        all_ok &= _check(
            not (_avg and _t > 2 * _avg and _t > 100_000),
            f"spend steady (today {_t / 1000:.0f}k vs 7d avg {_avg / 1000:.0f}k)",
            f"SPEND SPIKE — today {_t / 1000:.0f}k tokens vs 7-day average "
            f"{_avg / 1000:.0f}k: something is burning; check the task log before "
            "it burns again tomorrow",
            lines)
    except Exception:
        pass

    # THE MODEL BILL, counted by the machine itself (real token counts from every
    # API response, logged to data/model_usage.csv — multiply by your plan's rates)
    try:
        import csv
        by_day: dict[str, list[int]] = {}
        with (_data_dir() / "model_usage.csv").open() as f:
            for row in csv.DictReader(f):
                d = by_day.setdefault(row["date"], [0, 0])
                d[0] += int(row["input_tokens"])
                d[1] += int(row["output_tokens"])
        for d in sorted(by_day)[-3:]:
            i, o = by_day[d]
            lines.append(f"  model usage {d}: {i / 1000:.0f}k in / {o / 1000:.0f}k out")
    except FileNotFoundError:
        lines.append("  model usage: no calls logged yet (ledger starts with the next run)")
    except Exception:
        lines.append("  model usage: ledger unreadable")

    log2 = open_nap_log()
    w, n = log2.strike_rate()                      # correct: pass days (won=-1) excluded
    sw, sn = log2.shadow_strike()
    # THE READER'S DOUBTS, JUDGED (2026-08-19 law: an objection is recorded
    # and the pick stands at LEAN; fourth audit 2026-09-02: the old veto
    # tripwire matched a prefix nobody wrote and always read zero). Not a
    # gate — a scoreboard: do the reader's doubts predict losses?
    if hasattr(log2, "objection_watch"):
        _on, _ow, _ol = log2.objection_watch()
        if _on:
            lines.append(f"  reader objections this week: {_on} — the pick then "
                         f"won {_ow}, lost {_ol}, {_on - _ow - _ol} open "
                         "(a doubt that keeps losing is a doubt worth a law)")
    # P/L must be read BEFORE close (2026-08-01: it sat after close() and the
    # whole health report died on 'Cannot operate on a closed database')
    pnl, _pn = log2.profit_loss() if hasattr(log2, "profit_loss") else (0.0, 0)
    # favline read BEFORE close too (same trap as P/L, 2026-08-01)
    _fav = log2.favline_record() if hasattr(log2, "favline_record") else (0, 0, 0.0)
    # the two-column record read BEFORE close (same closed-DB trap)
    _bet, _dreck = (log2.record_split() if hasattr(log2, "record_split")
                    else ((0, 0), (0, 0)))
    log2.close()
    lines.append(f"  record: {w}/{n} settled naps won"
                 + (f" ({100 * w / n:.0f}%), level stakes at SP {pnl:+.1f}pt" if n else ""))
    if _bet[1] or _dreck[1]:
        lines.append(f"  two-column record: BETTING races {_bet[0]}/{_bet[1]} · "
                     f"forced/dreck days {_dreck[0]}/{_dreck[1]} — judge the first")
    # THE FAV LINE beside the value line (the master, 2026-08-16: 'lets do
    # favourite and value bet') — both bets, one glance, every day.
    fw, fn, fpnl = _fav
    if fn:
        lines.append(f"  fav line: {fw}/{fn} won ({100 * fw / fn:.0f}%), "
                     f"level stakes at SP {fpnl:+.1f}pt")
    # LOSS-STREAK ALARM (coroner fix 1: six losses passed with no alarm anywhere)
    real = [x for x in naps if x["won"] in (0, 1)]
    streak = 0
    for x in reversed(real):
        if x["won"] == 0:
            streak += 1
        else:
            break
    last7 = real[-7:]
    cold = sum(1 for x in last7 if x["won"] == 1) <= 1 and len(last7) >= 6
    all_ok &= _check(
        streak < 4 and not cold,
        f"form healthy (current losing streak: {streak})",
        f"COLD STREAK — {streak} straight losses / {sum(1 for x in last7 if x['won'] == 1)}"
        f"/{len(last7)} in the last 7. Tighten race selection; review the losing cases "
        "before trusting another pick.",
        lines)
    # SHADOW A/B ALARM (coroner fix 3: if the free engine outpicks the flagship
    # deep read, that fact must surface, not sit unread in a table)
    if sn >= 7:
        all_ok &= _check(
            not (sw - w >= 2),
            f"deep read holding its own vs shadow engine ({w}/{n} vs {sw}/{sn})",
            f"the SHADOW ENGINE is outpicking the deep read ({sw}/{sn} vs {w}/{n}) — "
            "the flagship may be subtracting value; review the A/B before paying for "
            "more deep reads.",
            lines)
    elif sn:
        lines.append(f"  shadow A/B: {sw}/{sn} (needs 7+ settled for the alarm)")
    # THE EVOLUTION LAW in the daily eye (2026-08-16, the master closing the
    # loop on 'the machine finds these things and then nothing changes'): the
    # school ladder's verdict rides in health — a CHANGE TACK is RED and
    # impossible to miss. Quiet when the school isn't deployed here.
    import os as _os
    _lcsv = _data_dir() / "school" / "daily_policy.csv"
    _champ = _os.environ.get("SCHOOL_CHAMPION") or "nap"      # what we measure (09-02)
    if _lcsv.exists() and _champ:
        from racing_edge.school.ladder import load_rows as _lr
        from racing_edge.school.ladder import verdict as _lv
        _v = _lv(_lr(_lcsv), _champ)
        all_ok &= _check(
            not _v.startswith("CHANGE TACK"),
            f"school ladder: {_v}",
            f"SCHOOL LADDER: {_v}",
            lines)
    if _lcsv.exists():
        # NIGHT SCHOOL FRESHNESS (2026-09-02: the box's ladder read 'fav n=0' —
        # the benchmark had NO graded days while the engine rows kept coming
        # from settle; nobody watched the grader itself). The fav line is
        # graded ONLY by the night run on the corpus: a stale fav day means
        # the night fetch or grader is dead, whatever the verdict says.
        from racing_edge.school.ladder import last_day as _ld
        from racing_edge.school.ladder import load_rows as _lr2
        _rows = _lr2(_lcsv)
        _fav_day = _ld(_rows, "fav")
        _age = (today - date.fromisoformat(_fav_day)).days if _fav_day else None
        all_ok &= _check(
            _age is not None and _age <= 2,
            f"night school grading (fav benchmark last graded {_fav_day}, "
            f"engine {_ld(_rows, 'engine') or 'never'})",
            f"NIGHT SCHOOL NOT GRADING — fav benchmark last graded "
            f"{_fav_day or 'never'}; the corpus fetch or the grader is dead: "
            "console `tail -40 data/task_runs.log` after 22:00 and "
            "`ls -la data/school/raw | tail -5`",
            lines)
    # THE HONEST HALF (dog-school lesson, 2026-08-24: "a dashboard showing
    # only what it measures is how a system looks healthy while rotting").
    # Every report ends with what is NOT being watched. Update this list
    # when an item is fixed or a new blind spot is found — a stale honest
    # half is the dishonest kind.
    # THE READ'S OWN SCOREBOARD (audit 2026-09-02): the claims every read makes,
    # marked against results — the learning loop's real gauge, not win/loss
    try:
        _lg = open_nap_log()
        try:
            _rg = _lg.read_grades() if hasattr(_lg, "read_grades") else {}
        finally:
            _lg.close()
        if _rg and _rg.get("graded"):
            lines.append(f"  read scoreboard ({_rg['graded']} graded): named danger won "
                         f"{_rg['danger_won']}, beat us {_rg['danger_beat_us']}; winner "
                         f"was crossed off {_rg['winner_crossed_off']}; my price "
                         f"shorter than SP {_rg['price_shorter_than_sp']}")
    except Exception:
        lines.append("  read scoreboard: unreadable")
    # THE MEMORY AND THE TIER-0 PASS (audit 2026-09-02, steps 5 and 6): knowledge
    # never consulted is named; a tier-0 report older than yesterday is red.
    try:
        from racing_edge.study.rulings import load as _rl, never_consulted as _nc
        _all, _never = _rl(), _nc()
        lines.append(f"  rulings: {len(_all)} stored, {len(_never)} never consulted"
                     + (f" — {', '.join(r['date'] + ' ' + r['ruling'][:40] for r in _never[:3])}"
                        if _never else ""))
    except Exception:
        lines.append("  rulings: table unreadable")
    try:
        from datetime import datetime as _dtm
        _t0 = _data_dir() / "school" / "tier0.md"
        _age = (_dtm.now() - _dtm.fromtimestamp(_t0.stat().st_mtime)).days if _t0.exists() else None
        if _age is None:
            # never written yet is not a fault (second audit, bot F): the same
            # courtesy the flight recorder gets on its first morning
            lines.append("  tier-0: not yet run (starts with tonight's night task)")
        else:
            all_ok &= _check(
                _age <= 1,
                f"tier-0 pass fresh (data/school/tier0.md, {_age}d old)",
                f"tier-0 pass STALE ({_age}d old) — the night task's tier0 step did not run",
                lines)
    except Exception:
        lines.append("  tier-0: unreadable")
    lines.append("\n  NOT WATCHED (the honest half — nobody is checking these):")
    lines.append("    · morning card coverage — races never STUDIED at all "
                 "(summaries vs opinions count); settle-side coverage of "
                 "studied races is watched since 2026-08-24")
    lines.append("    · unsettled shadow rows before 2026-08-19 (backfill open "
                 "— shadow strike is PROVISIONAL until settled)")
    lines.append("    · corpus hole Apr–Jul (mine/vision figures PROVISIONAL)")
    lines.append("    · external heartbeat (healthchecks.io) not configured — "
                 "if the whole scheduler dies, no one is told")
    verdict = "ALL GREEN — the loop is running and feeding itself." if all_ok else \
        "RED LINES ABOVE — a part of the loop is silently dead. Fix before trusting a pick."
    lines.append(f"\n  {verdict}")
    report = "\n".join(lines)
    print(report)

    if args.email:
        from racing_edge.report.mail import configured, send
        if configured():
            subj = ("Loop health: ALL GREEN" if all_ok else "Loop health: RED — attention")
            ok = send(subj, report, title="Loop health", subtitle="racing-edge form trial")
            print(f"  email: {'sent' if ok else 'FAILED'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    from racing_edge.cli._common import run_guarded
    raise SystemExit(run_guarded("health", main))
