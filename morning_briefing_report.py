"""
morning_briefing_report.py — Assemble the morning briefing email from the
day's scored candidates, cluster review, and jump alternative.

Reads:
    data/nap_candidates_YYYY-MM-DD.json    (from nap_selector_v3 + cluster_review)
    reports/cluster_review_YYYY-MM-DD.txt  (optional — appended if present)

Writes:
    reports/morning_briefing_YYYY-MM-DD.txt  (read by email_report.py)

Exit codes:
    0  — briefing written
    1  — fatal error (no candidates file, write failure)
"""

from __future__ import annotations

import sys
from datetime import datetime

from src.helpers import data_path, log, report_path, safe_load_json, today_str

SEP = "═" * 60


def _fmt_odds(price: float | None) -> str:
    if price is None:
        return "—"
    if price < 2.0:
        num = round(price - 1, 2)
        return f"{num:.0f}/{1}" if num == int(num) else f"{num:.2g}/1"
    frac = price - 1
    for denom in (1, 2, 4, 5, 8, 10):
        num = frac * denom
        if abs(num - round(num)) < 0.05:
            return f"{int(round(num))}/{denom}"
    return f"{price:.1f}"


def _section(title: str) -> str:
    return f"\n■ {title}\n"


def _build_briefing(date_str: str, data: dict) -> str:
    now = datetime.now().strftime("%H:%M")
    lines: list[str] = [
        SEP,
        "  RACING INTELLIGENCE — MORNING BRIEFING",
        f"  {date_str}  |  Generated: {now}",
        SEP,
        "",
    ]

    # --- NAP ---
    nap = data.get("nap")
    lines.append("■ TODAY'S NAP")
    if nap:
        price = nap.get("morning_price")
        warnings = nap.get("warnings") or []
        lines += [
            f"  {nap['horse'].upper()}",
            f"  {nap.get('course', '?')}  {nap.get('off_time', '?')}",
            f"  Score: {nap['score']:.1f}  |  Grade: {nap.get('grade', '?')}  |  Price: {_fmt_odds(price)}",
            f"  Form: {nap.get('form', '—')}  |  RPR: {nap.get('rpr', '—')}  |  OR: {nap.get('ofr', '—')}",
            f"  Race type: {nap.get('race_type', '?')}  |  Going: {nap.get('going', '?')}",
            "",
            "  Key reasons:",
        ]
        for r in (nap.get("reasons") or [])[:6]:
            lines.append(f"    • {r}")
        if warnings:
            lines.append(f"\n  ⚠ Warnings: {', '.join(warnings)}")
    else:
        day_verdict = data.get("day_verdict", "NO BET")
        lines.append(f"  No NAP selected today — {day_verdict}")

    lines.append("")

    # --- Jump alternative ---
    jump_nap = data.get("jump_nap")
    lines.append("■ JUMP ALTERNATIVE")
    if jump_nap:
        price = jump_nap.get("morning_price")
        lines += [
            f"  {jump_nap['horse'].upper()}",
            f"  {jump_nap.get('course', '?')}  {jump_nap.get('off_time', '?')}",
            f"  Score: {jump_nap['score']:.1f}  |  Type: {jump_nap.get('race_type', '?')}  |  Price: {_fmt_odds(price)}",
        ]
        for r in (jump_nap.get("reasons") or [])[:3]:
            lines.append(f"    • {r}")
    else:
        lines.append("  None qualifying today.")

    lines.append("")

    # --- Watchlist ---
    watchlist = data.get("watchlist") or []
    lines.append("■ WATCHLIST")
    if watchlist:
        for h in watchlist[:5]:
            price = h.get("morning_price")
            lines.append(
                f"  {h['horse']} | {h.get('course','?')} {h.get('off_time','?')} "
                f"| Score: {h['score']:.1f} | {_fmt_odds(price)}"
            )
    else:
        lines.append("  Empty.")

    lines.append("")

    # --- Cluster warnings ---
    cluster_races = data.get("cluster_races") or []
    field_cluster = data.get("field_cluster_warning", False)
    if cluster_races or field_cluster:
        lines.append("■ CLUSTER WARNINGS")
        if field_cluster:
            lines.append("  ⚠ Field-level cluster detected — NAP margins are tight across card")
        for rid in cluster_races:
            lines.append(f"  ⚠ Clustered race: {rid} — no clear standout")
        lines.append("")

    # --- Day verdict ---
    day_verdict = data.get("day_verdict", "UNKNOWN")
    lines += ["■ DAY VERDICT", f"  {day_verdict}", "", SEP]

    return "\n".join(lines)


def main() -> int:
    log("morning_briefing_report.py started")
    date_str = today_str()

    candidates_path = data_path(f"nap_candidates_{date_str}.json")
    data = safe_load_json(candidates_path)
    if not data:
        log(f"morning_briefing_report: no candidates file at {candidates_path}", "ERROR")
        return 1

    briefing = _build_briefing(date_str, data)

    dest = report_path(f"morning_briefing_{date_str}.txt")
    try:
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(briefing)
        log(f"morning_briefing_report: written to {dest}")
    except OSError as exc:
        log(f"morning_briefing_report: write failed — {exc}", "ERROR")
        return 1

    print(f"morning_briefing_report: SUCCESS — {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
