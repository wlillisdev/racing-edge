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
        confidence = nap.get("confidence", "")
        stake_rec = nap.get("stake_recommendation", "")
        try:
            score_str = f"{float(nap.get('score', 0)):.1f}"
        except (TypeError, ValueError):
            score_str = "?"
        lines += [
            f"  {str(nap.get('horse', '?')).upper()}",
            f"  {nap.get('course', '?')}  {nap.get('off_time', '?')}",
            f"  Score: {score_str}  |  Grade: {nap.get('grade', '?')}  |  Price: {_fmt_odds(price)}",
            f"  Form: {nap.get('form', '—')}  |  RPR: {nap.get('rpr', '—')}  |  OR: {nap.get('ofr', '—')}",
            f"  Race type: {nap.get('race_type', '?')}  |  Going: {nap.get('going', '?')}",
        ]
        if confidence:
            lines.append(f"  Confidence: {confidence}  |  Stake: {stake_rec}")
        lines += ["", "  Key reasons:"]
        for r in (nap.get("reasons") or [])[:6]:
            lines.append(f"    • {r}")
        if warnings:
            clean_warnings = [w for w in warnings if w != "cluster_warning"]
            if "cluster_warning" in warnings:
                clean_warnings = ["CLUSTERED RACE — tight margins, reduce stake"] + clean_warnings
            if clean_warnings:
                lines.append(f"\n  ⚠ Warnings: {', '.join(clean_warnings)}")
    else:
        day_verdict = data.get("day_verdict", "NO BET")
        lines.append(f"  No NAP selected today — {day_verdict}")

    lines.append("")

    # --- AI second opinion (independent arbiter) ---
    arb = safe_load_json(data_path(f"arbiter_{date_str}.json")) or {}
    res = arb.get("result") or {}
    if res:
        lines.append("■ AI SECOND OPINION")
        ai = res.get("ai_nap") or {}
        # If the model truncated before writing agreement, derive it from horse names.
        agree = str(res.get("agreement") or "").upper()
        if not agree:
            model_horse = str((nap or {}).get("horse") or "").strip().lower()
            ai_horse = str(ai.get("horse") or "").strip().lower()
            if model_horse and ai_horse:
                agree = "AGREE" if model_horse == ai_horse else "DISAGREE"
            else:
                agree = "UNKNOWN"
        flag = "   ⚠⚠ DISAGREES WITH MODEL ⚠⚠" if agree == "DISAGREE" else ""
        conf = res.get("confidence")
        conf_str = f"{conf}/100" if isinstance(conf, int) else "—"
        lines += [
            f"  AI NAP: {str(ai.get('horse', '?')).upper()} — {ai.get('course', '?')}  {ai.get('off_time', '?')}",
            f"  Agreement: {agree}{flag}  (confidence {conf_str})",
        ]
        note = str(res.get("agreement_note") or "").strip()
        if note:
            lines.append(f"  {note}")
        if ai.get("reason"):
            lines.append(f"  Why: {ai.get('reason')}")
        lines.append("")

    # --- THE METHOD (your pick: NAP base + overlay) ---
    method = safe_load_json(data_path(f"method_pick_{date_str}.json")) or {}
    m_nap = method.get("method_nap")
    lines.append("■ THE METHOD  (your pick — NAP base + your overlay)")
    if m_nap:
        lines += [
            f"  {str(m_nap.get('horse', '?')).upper()}",
            f"  {m_nap.get('course', '?')}  {m_nap.get('off_time', '?')}",
            f"  Case: {m_nap.get('method_case', '?')}  "
            f"(NAP base {m_nap.get('base', '?')} + overlay {m_nap.get('overlay', '?')})  "
            f"|  Price: {_fmt_odds(m_nap.get('price'))}",
        ]
        if nap and str(nap.get("horse", "")).lower() == str(m_nap.get("horse", "")).lower():
            lines.append("  ✓ Agrees with the quant NAP — both lenses on the same horse")
        lines += ["", "  Why:"]
        for r in (m_nap.get("reasons") or [])[:6]:
            lines.append(f"    • {r}")
    else:
        lines.append("  No bettable Method pick in the value band today.")
    lines.append("")

    # --- Jump alternative ---
    jump_nap = data.get("jump_nap")
    lines.append("■ JUMP ALTERNATIVE")
    if jump_nap:
        price = jump_nap.get("morning_price")
        try:
            j_score_str = f"{float(jump_nap.get('score', 0)):.1f}"
        except (TypeError, ValueError):
            j_score_str = "?"
        lines += [
            f"  {str(jump_nap.get('horse', '?')).upper()}",
            f"  {jump_nap.get('course', '?')}  {jump_nap.get('off_time', '?')}",
            f"  Score: {j_score_str}  |  Type: {jump_nap.get('race_type', '?')}  |  Price: {_fmt_odds(price)}",
        ]
        for r in (jump_nap.get("reasons") or [])[:3]:
            lines.append(f"    • {r}")
    else:
        lines.append("  None qualifying today.")

    lines.append("")

    # --- Watchlist / Alternative bets ---
    watchlist = data.get("watchlist") or []
    lines.append("■ OTHER OPTIONS — ALTERNATIVE BETS")
    if watchlist:
        for h in watchlist[:5]:
            price = h.get("morning_price")
            try:
                w_score_str = f"{float(h.get('score', 0)):.1f}"
            except (TypeError, ValueError):
                w_score_str = "?"
            w_conf = h.get("confidence", "")
            conf_tag = f" [{w_conf}]" if w_conf else ""
            lines.append(
                f"  {h.get('horse', '?')} | {h.get('course','?')} {h.get('off_time','?')} "
                f"| Score: {w_score_str}{conf_tag} | {_fmt_odds(price)}"
            )
    else:
        lines.append("  None qualifying today.")

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

    # --- TODAY'S BET (dynamic multiple/single — the reads pick the shape) ---
    bet = safe_load_json(data_path(f"dynamic_bet_{date_str}.json")) or {}
    lines.append("■ TODAY'S BET  (dynamic — double / Patent / Lucky 15 / single)")
    if bet.get("legs"):
        pot = bet.get("potential") or {}
        kind = "EACH-WAY" if bet.get("ew") else "WIN"
        lines.append(f"  {str(bet.get('structure', '?')).upper()}  ({kind})   "
                     f"stake £{float(pot.get('stake', 0)):.2f}")
        if bet.get("conviction"):
            lines.append(f"  {bet['conviction']}")
        for l in bet["legs"]:
            lines.append(f"    · {l.get('horse', '?')} — {l.get('course', '?')} "
                         f"{l.get('off_time', '?')}  @{l.get('odds', '?')}  ({l.get('source', '')})")
        if pot.get("all_win"):
            lines.append(f"  if all win: £{float(pot['all_win']):.2f}")
        if bet.get("why"):
            lines.append(f"  {bet['why']}")
        lines.append("  (paper-trade — flat stake until the ledger proves an edge)")
    else:
        lines.append("  No bet today — nothing in the value band.")
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
        # Write a minimal briefing so email_report still sends something useful
        data = {"day_verdict": "PIPELINE FAILURE — candidates file missing", "nap": None}

    try:
        briefing = _build_briefing(date_str, data)
    except Exception as exc:
        log(f"morning_briefing_report: _build_briefing failed — {exc}", "ERROR")
        briefing = (
            f"MORNING BRIEFING — BUILD FAILURE\n\n"
            f"Date: {date_str}\n"
            f"Error: {exc}\n\n"
            f"Pipeline ran but briefing could not be assembled.\n"
            f"Check: data/nap_candidates_{date_str}.json\n"
        )

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
