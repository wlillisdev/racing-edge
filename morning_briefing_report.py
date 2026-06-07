"""
morning_briefing_report.py — Generate the professional morning briefing.

Aggregates the day's NAP selection, signposts, race reader notes, and
shortlist into a single polished briefing document suitable for email.

Inputs (all optional except nap_candidates):
  data/nap_candidates_YYYY-MM-DD.json   (required — BLOCKED if missing)
  reports/signposts_YYYY-MM-DD.txt      (optional — warn if missing)
  reports/race_reader_YYYY-MM-DD.txt    (optional — skip section if missing)
  data/shortlist_YYYY-MM-DD.json        (optional — skip section if missing)

Outputs:
  reports/morning_briefing_YYYY-MM-DD.txt

Exit codes:
  0 — success (even if result is BLOCKED/NO_BET — that is valid)
  1 — unrecoverable I/O error
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from src.helpers import (
    data_path,
    format_odds,
    log,
    report_path,
    safe_load_json,
    today_str,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL_VERSION: str = "v3"

# How many signpost lines to include in the briefing
SIGNPOST_MAX_LINES: int = 5


# ---------------------------------------------------------------------------
# Date formatting
# ---------------------------------------------------------------------------

_WEEKDAY_NAMES = (
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
)
_MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def _format_display_date(date_str: str) -> str:
    """
    Convert 'YYYY-MM-DD' to 'Saturday 06 June 2026'.
    Falls back to the raw string on parse error.
    """
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        weekday = _WEEKDAY_NAMES[d.weekday()]
        month   = _MONTH_NAMES[d.month - 1]
        return f"{weekday} {d.day:02d} {month} {d.year}"
    except (ValueError, IndexError):
        return date_str


# ---------------------------------------------------------------------------
# Signposts loader
# ---------------------------------------------------------------------------

def _load_signposts(date_str: str) -> list[str]:
    """
    Load the signposts report, returning the top SIGNPOST_MAX_LINES lines.
    Returns [] with a warning if the file is absent.
    """
    path = report_path(f"signposts_{date_str}.txt")
    if not Path(path).exists():
        log(f"morning_briefing: signposts file not found — {path}", "WARNING")
        return []

    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = [l.rstrip() for l in fh if l.strip()]
        return lines[:SIGNPOST_MAX_LINES]
    except OSError as exc:
        log(f"morning_briefing: could not read signposts — {exc}", "WARNING")
        return []


# ---------------------------------------------------------------------------
# Race reader loader
# ---------------------------------------------------------------------------

def _load_race_reader(date_str: str) -> str | None:
    """
    Load the race reader report as a string.
    Returns None if the file is absent (no warning — it is optional).
    """
    path = report_path(f"race_reader_{date_str}.txt")
    if not Path(path).exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError as exc:
        log(f"morning_briefing: could not read race_reader — {exc}", "WARNING")
        return None


# ---------------------------------------------------------------------------
# Value EW extraction
# ---------------------------------------------------------------------------

def _extract_value_ew(candidates: dict) -> dict | None:
    """
    Look for a value each-way angle in the candidates document.

    Currently checks for a 'value_ew' key, or falls back to a watchlist
    horse with sp_dec >= 6.0 and grade B+/A.
    Returns a horse dict or None.
    """
    # Explicit value_ew field
    ew = candidates.get("value_ew")
    if ew:
        return ew

    # Fallback: first watchlist horse with reasonable EW price (>= 6.0)
    watchlist = candidates.get("watchlist") or []
    for h in watchlist:
        sp = h.get("sp_dec") or 0
        try:
            sp = float(sp)
        except (TypeError, ValueError):
            sp = 0.0
        if sp >= 6.0 and h.get("grade") in ("A", "B+", "B"):
            return h

    return None


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def _build_briefing(
    date_str: str,
    generated_hm: str,
    candidates: dict,
    signposts: list[str],
    race_reader: str | None,
    shortlist: dict | None,
) -> str:
    sep  = "═" * 56
    sep2 = "─" * 56

    display_date = _format_display_date(date_str)
    nap          = candidates.get("nap")
    best         = candidates.get("best_of_card")
    watchlist    = candidates.get("watchlist") or []
    cluster_races = candidates.get("cluster_races") or []
    day_verdict  = candidates.get("day_verdict") or "UNKNOWN"

    lines: list[str] = [
        sep,
        "  RACING INTELLIGENCE SYSTEM — MORNING BRIEFING",
        f"  Date: {display_date}",
        f"  Generated: {generated_hm}  |  Model: {MODEL_VERSION}",
        sep,
        "",
    ]

    # ------------------------------------------------------------------
    # OFFICIAL NAP
    # ------------------------------------------------------------------
    lines.append("■ OFFICIAL NAP")
    if nap:
        sp_frac = format_odds(nap.get("sp_dec") or 0)
        sp_dec  = nap.get("sp_dec")
        sp_str  = f"{sp_frac} ({sp_dec})" if sp_dec else "N/A"

        reasons_text = ". ".join(nap.get("reasons") or [])
        if not reasons_text:
            reasons_text = "See scoring report for detail."

        warnings_text = (
            ", ".join(nap.get("warnings") or []) or "None"
        )

        lines += [
            f"  {nap['horse'].upper()} — {nap.get('course', '')}, "
            f"{nap.get('off_time', '')}",
            f"  Grade: {nap.get('grade', '?')}  |  "
            f"Score: {nap.get('score', 0):.0f}/100",
            f"  Reason: {reasons_text}",
            f"  Warnings: {warnings_text}",
            f"  Odds: {sp_str}",
        ]
    else:
        lines.append(
            "  No NAP selected today."
            f" Day verdict: {day_verdict}"
        )
    lines.append("")

    # ------------------------------------------------------------------
    # VALUE EACH-WAY ANGLE
    # ------------------------------------------------------------------
    lines.append("■ VALUE EACH-WAY ANGLE")
    ew = _extract_value_ew(candidates)
    if ew:
        ew_sp_frac = format_odds(ew.get("sp_dec") or 0)
        ew_sp_dec  = ew.get("sp_dec")
        ew_sp_str  = f"{ew_sp_frac} ({ew_sp_dec})" if ew_sp_dec else "N/A"
        lines += [
            f"  {ew['horse'].upper()} — {ew.get('course', '')}, "
            f"{ew.get('off_time', '')}",
            f"  Grade: {ew.get('grade', '?')}  |  "
            f"Score: {ew.get('score', 0):.0f}/100",
            f"  Odds: {ew_sp_str}",
            "  Note: Each-way angle — not an official NAP bet.",
        ]
    else:
        lines.append(
            "  No independent EW angle identified today."
        )
    lines.append("")

    # ------------------------------------------------------------------
    # BEST OF CARD
    # ------------------------------------------------------------------
    lines.append("■ BEST OF CARD")
    if best:
        lines += [
            f"  {best['horse'].upper()} — {best.get('course', '')}, "
            f"{best.get('off_time', '')}",
            f"  Grade: {best.get('grade', '?')}  |  "
            f"Score: {best.get('score', 0):.0f}/100",
            "  Note: Strong form but not clear enough for official NAP.",
        ]
    else:
        lines.append("  None identified.")
    lines.append("")

    # ------------------------------------------------------------------
    # WATCHLIST
    # ------------------------------------------------------------------
    lines.append("■ WATCHLIST")
    if watchlist:
        for h in watchlist:
            sp_f = format_odds(h.get("sp_dec") or 0)
            lines.append(
                f"  - {h['horse']} — {h.get('course', '')} "
                f"{h.get('off_time', '')}  ({sp_f})"
            )
    else:
        lines.append("  Nothing to report today.")
    lines.append("")

    # ------------------------------------------------------------------
    # CLUSTER RACES
    # ------------------------------------------------------------------
    lines.append("■ CLUSTER RACES (NO BET)")
    if cluster_races:
        for race_id in cluster_races:
            lines.append(f"  - Race {race_id}: Clustered field — no clean standout")
    else:
        lines.append("  None — all races have a clear leader.")
    lines.append("")

    # ------------------------------------------------------------------
    # DAY VERDICT
    # ------------------------------------------------------------------
    verdict_display = {
        "NAP_SELECTED":        "NAP SELECTED",
        "NO_BET_CLUSTERED":    "NO BET — Clustered fields",
        "NO_BET_NO_STANDOUT":  "NO BET — No standout selection",
        "BLOCKED":             "BLOCKED — Data unavailable",
    }.get(day_verdict, day_verdict)

    lines.append(f"■ DAY VERDICT: {verdict_display}")
    lines.append("")
    lines.append(sep)

    # ------------------------------------------------------------------
    # SIGNPOSTS SUMMARY
    # ------------------------------------------------------------------
    lines.append("  SIGNPOSTS SUMMARY")
    if signposts:
        for sp_line in signposts:
            lines.append(f"  {sp_line}")
    else:
        lines.append("  (Signposts report not available today.)")
    lines.append("")

    # ------------------------------------------------------------------
    # RACE READER (optional)
    # ------------------------------------------------------------------
    if race_reader:
        lines.append("  RACE READER NOTES")
        lines.append(sep2)
        # Include up to 20 lines so the briefing stays readable
        rr_lines = race_reader.splitlines()[:20]
        for rr_line in rr_lines:
            lines.append(f"  {rr_line}")
        if len(race_reader.splitlines()) > 20:
            lines.append("  [...see full race_reader report for detail...]")
        lines.append("")

    # ------------------------------------------------------------------
    # SHORTLIST SUMMARY (optional)
    # ------------------------------------------------------------------
    if shortlist:
        sl_races = shortlist.get("races") or []
        if sl_races:
            lines.append(f"  SHORTLIST: {len(sl_races)} race(s) of interest today")
            for sl_race in sl_races[:5]:   # cap at 5 for brevity
                course   = sl_race.get("course", "")
                off_time = sl_race.get("off_time", "")
                n_horses = len(sl_race.get("shortlisted_runners") or [])
                lines.append(
                    f"    • {course} {off_time} — {n_horses} horse(s) shortlisted"
                )
            lines.append("")

    # ------------------------------------------------------------------
    # Footer
    # ------------------------------------------------------------------
    lines += [
        sep,
        "  ✓ Briefing complete. Official P/L tracked for NAP only.",
        "  ✓ Watchlist/Best of Card are NOT official bets.",
        sep,
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Generate morning briefing report. Returns exit code."""
    log("morning_briefing_report.py started")

    date_str     = today_str()
    now          = datetime.now(timezone.utc)
    generated_hm = now.strftime("%H:%M")

    # ------------------------------------------------------------------
    # Load nap_candidates (required)
    # ------------------------------------------------------------------
    candidates_path = data_path(f"nap_candidates_{date_str}.json")
    candidates      = safe_load_json(candidates_path)

    if candidates is None:
        log(
            "morning_briefing: nap_candidates not found — cannot generate briefing",
            "ERROR",
        )
        # Write a minimal BLOCKED briefing so the pipeline always produces output
        blocked_text = (
            f"═══════════════════════════════════════════════════════\n"
            f"  RACING INTELLIGENCE SYSTEM — MORNING BRIEFING\n"
            f"  Date: {_format_display_date(date_str)}\n"
            f"  Generated: {generated_hm}  |  Model: {MODEL_VERSION}\n"
            f"═══════════════════════════════════════════════════════\n"
            f"\n"
            f"  BLOCKED — nap_candidates file not found.\n"
            f"  Run nap_selector_v3.py first.\n"
            f"\n"
            f"  No official bet today.\n"
            f"═══════════════════════════════════════════════════════\n"
        )
        report_dest = report_path(f"morning_briefing_{date_str}.txt")
        try:
            with open(report_dest, "w", encoding="utf-8") as fh:
                fh.write(blocked_text)
            log(f"morning_briefing: BLOCKED report written to {report_dest}")
        except OSError as exc:
            log(f"morning_briefing: could not write BLOCKED report — {exc}", "ERROR")
            return 1
        print(f"morning_briefing: BLOCKED — nap_candidates unavailable for {date_str}")
        return 0   # BLOCKED is a valid pipeline outcome

    # ------------------------------------------------------------------
    # Load optional inputs
    # ------------------------------------------------------------------
    signposts   = _load_signposts(date_str)
    race_reader = _load_race_reader(date_str)
    shortlist   = safe_load_json(data_path(f"shortlist_{date_str}.json"))

    if shortlist is None:
        log("morning_briefing: shortlist not available — section skipped", "INFO")

    # ------------------------------------------------------------------
    # Build briefing
    # ------------------------------------------------------------------
    briefing_text = _build_briefing(
        date_str,
        generated_hm,
        candidates,
        signposts,
        race_reader,
        shortlist,
    )

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    report_dest = report_path(f"morning_briefing_{date_str}.txt")
    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(briefing_text)
        log(f"morning_briefing: briefing saved → {report_dest}")
    except OSError as exc:
        log(f"morning_briefing: failed to write briefing — {exc}", "ERROR")
        return 1

    # ------------------------------------------------------------------
    # Print summary
    # ------------------------------------------------------------------
    day_verdict = candidates.get("day_verdict") or "UNKNOWN"
    nap = candidates.get("nap")
    if nap:
        print(
            f"morning_briefing: SUCCESS — NAP: {nap.get('horse', 'N/A')}"
            f" ({nap.get('course', '')} {nap.get('off_time', '')})"
        )
    else:
        print(f"morning_briefing: SUCCESS — {day_verdict} — no NAP today")

    return 0


if __name__ == "__main__":
    sys.exit(main())
