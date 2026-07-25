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


def _check(ok: bool, good: str, bad: str, lines: list[str]) -> bool:
    lines.append(f"  {'✓' if ok else '✗ RED:'} {good if ok else bad}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="Loop health — red/green ledger report.")
    ap.add_argument("--email", action="store_true", help="email the report (SMTP env)")
    args = ap.parse_args()

    today = date.today()
    yday = today - timedelta(days=1)
    lines: list[str] = [f"LOOP HEALTH — {today}"]
    all_ok = True

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
    all_ok &= _check(
        not stale,
        "no stale unsettled naps",
        f"{len(stale)} nap(s) unsettled for 2+ days ({', '.join(n['date'] for n in stale[:5])}) "
        "— the 22:00 night task is not settling",
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
    fresh_nu = [n for n in nuances if n["date"] >= fresh_cut]
    all_ok &= _check(
        bool(fresh_nu) or not naps,
        f"self-study flowing ({len(fresh_nu)} nuance row(s) in the last 2 days; "
        f"{sum(1 for n in nuances if n['status'] == 'validated')} validated, "
        f"{sum(1 for n in nuances if n['status'] == 'refuted')} refuted on record)",
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
    nlog_stale = open_nuance_log()
    stale_clues = nlog_stale.tracked_stale()
    nlog_stale.close()
    all_ok &= _check(
        stale_clues < 10,
        f"tracked list healthy ({len(tracked)} live clue(s); {stale_clues} awaiting "
        "the nightly broom)",
        f"{stale_clues} clues sitting active beyond the 28-day expiry — the nightly "
        "broom (expire_tracked in --settle) is not running",
        lines)
    # THE DOORBELL (coroner 2026-07-21: 0 validated / 104 refuted — nuances have no
    # path to 'validated' without the master's ruling, and nothing ever ASKED him).
    # The freshest proposals ring here daily, with the exact commands to rule.
    pending = [n for n in nuances if n["status"] == "proposed"][-3:]
    if pending:
        lines.append(f"  AWAITING YOUR RULING ({sum(1 for n in nuances if n['status'] == 'proposed')} "
                     "proposed nuance(s) — promote what your eye confirms, bin the rest):")
        for n in pending:
            lines.append(f"    #{n['id']}: {n['nuance'][:120]}")
            lines.append(f"        promote: python -m racing_edge.cli.learn --promote {n['id']}"
                         f"   |   bin: --bin {n['id']}")

    # THE FLIGHT RECORDER — did the scheduler actually LAUNCH anything today?
    # (2026-07-21: the ledger proved scheduled runs weren't happening; this separates
    # 'PythonAnywhere never started it' from 'started and died at line X')
    try:
        from pathlib import Path as _P
        tail = _P("data/task_runs.log").read_text().splitlines()
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

    # THE MODEL BILL, counted by the machine itself (real token counts from every
    # API response, logged to data/model_usage.csv — multiply by your plan's rates)
    try:
        import csv
        from pathlib import Path
        by_day: dict[str, list[int]] = {}
        with (Path("data") / "model_usage.csv").open() as f:
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
    log2.close()
    lines.append(f"  record: {w}/{n} settled naps won"
                 + (f" ({100 * w / n:.0f}%)" if n else ""))
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
    raise SystemExit(main())
