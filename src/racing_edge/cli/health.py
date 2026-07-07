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
    all_ok &= _check(
        today.isoformat() in dates or yday.isoformat() in dates,
        f"nap banked recently (latest {max(dates) if dates else 'never'})",
        "NO NAP banked today or yesterday — the 07:30 task is dead or dying silently",
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
    old_tracked = [t for t in tracked
                   if t["date"] < (today - timedelta(days=21)).isoformat()]
    all_ok &= _check(
        len(old_tracked) < 10,
        f"tracked list healthy ({len(tracked)} active clue(s))",
        f"{len(old_tracked)} tracked clues older than 3 weeks and never settled — "
        "the follow/oppose list is silting up unverified",
        lines)

    w, n = 0, 0
    settled = [x for x in naps if x["won"] is not None]
    w, n = sum(x["won"] for x in settled), len(settled)
    lines.append(f"  record: {w}/{n} settled naps won"
                 + (f" ({100 * w / n:.0f}%)" if n else ""))
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
