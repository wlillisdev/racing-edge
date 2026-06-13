"""
final_nap_decision.py — Market-time final NAP decision.

Runs after late odds and non-runner scans are available.  Applies a
final layer of safety checks before confirming (or blocking) the NAP.

CRITICAL DESIGN NOTE:
  This script MUST NEVER crash silently.  Any exception that previously
  blocked the email must be caught and turned into a BLOCKED output
  with a clear reason.  All optional data is gracefully skipped.

Inputs:
  data/nap_candidates_YYYY-MM-DD.json    (required — BLOCKED if missing)
  data/market_movers_YYYY-MM-DD.json     (optional — warn only, never block)
  reports/non_runners_YYYY-MM-DD.txt     (optional — warn if missing)

Outputs:
  data/final_nap_decision_YYYY-MM-DD.json
  reports/final_nap_decision_YYYY-MM-DD.txt

Exit codes:
  0 — success (BLOCKED/NO_BET/CONFIRMED are all valid outcomes)
  1 — unrecoverable I/O error (cannot write output files)
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
    safe_write_json,
    today_str,
)

# ---------------------------------------------------------------------------
# Non-runner file parser
# ---------------------------------------------------------------------------

def _load_non_runners(date_str: str) -> tuple[list[str], bool]:
    """
    Parse the non-runners report and return (non_runner_names, file_found).

    non_runner_names: lower-cased horse names confirmed as non-runners.
    file_found: True if the file existed (False triggers a warning, not a block).

    The non-runners report is expected to contain one horse name per line
    (it may contain free text; any line that is short and looks like a name
    is kept).
    """
    path = Path(report_path(f"non_runners_{date_str}.txt"))

    if not path.exists():
        log(
            f"final_nap_decision: non_runners file not found — {path}",
            "WARNING",
        )
        return [], False

    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw_lines = [l.strip() for l in fh if l.strip()]
    except OSError as exc:
        log(f"final_nap_decision: could not read non_runners file — {exc}", "WARNING")
        return [], True   # file existed but unreadable

    # Heuristic: treat lines that are not headings/separators as horse names.
    # Headings often contain ':', '=', '-' repeated, or are ALL CAPS long.
    non_runners: list[str] = []
    for line in raw_lines:
        # Skip separator lines
        if set(line) <= set("=─-_ "):
            continue
        # Skip obvious heading lines (contain colon or are very long)
        if ":" in line or len(line) > 60:
            continue
        non_runners.append(line.lower())

    log(
        f"final_nap_decision: {len(non_runners)} non-runner entries loaded"
        f" from {path}",
        "INFO",
    )
    return non_runners, True


# ---------------------------------------------------------------------------
# Market movers lookup
# ---------------------------------------------------------------------------

def _get_market_movement(horse_id: str, market_movers: dict | None) -> str:
    """
    Return the movement string for a given horse from the market_movers dict.
    Returns 'unknown' if unavailable.
    """
    if not market_movers or not isinstance(market_movers, dict):
        return "unknown"

    # market_movers.py writes "movements" with per-entry "move_type";
    # legacy keys kept as fallbacks.
    movers: list[dict] = market_movers.get("movements") or market_movers.get("movers") or []
    for mover in movers:
        if str(mover.get("horse_id") or "") == str(horse_id):
            return (mover.get("move_type") or mover.get("movement") or "stable").lower()

    return "unknown"


def _get_latest_odds(horse_id: str, market_movers: dict | None,
                     fallback_sp: float | None) -> float | None:
    """
    Return the most up-to-date decimal odds for a horse.

    Prefers the 'latest_price' from the market_movers entry, then the
    'morning_price', then falls back to the racecard sp_dec.
    """
    if market_movers and isinstance(market_movers, dict):
        movers: list[dict] = market_movers.get("movements") or market_movers.get("movers") or []
        for mover in movers:
            if str(mover.get("horse_id") or "") != str(horse_id):
                continue
            # market_movers.py writes "late_odds"/"morning_odds"
            for key in ("late_odds", "latest_price", "late_price", "morning_odds", "morning_price"):
                val = mover.get(key)
                if val is not None:
                    try:
                        return float(val)
                    except (TypeError, ValueError):
                        pass

    if fallback_sp is not None:
        try:
            return float(fallback_sp)
        except (TypeError, ValueError):
            pass

    return None


# ---------------------------------------------------------------------------
# Decision logic
# ---------------------------------------------------------------------------

def _make_decision(
    nap: dict | None,
    non_runners: list[str],
    nr_file_found: bool,
    market_movers: dict | None,
    mm_available: bool,
) -> tuple[str, str | None, dict | None, list[str]]:
    """
    Apply all safety checks and produce the final decision.

    Returns:
      (status, block_reason, nap_summary_dict, warnings)

    status: 'CONFIRMED' | 'BLOCKED' | 'NO_BET'
    """
    warnings: list[str] = []

    if not mm_available:
        warnings.append("market_movers_unavailable — using morning odds only")

    if not nr_file_found:
        warnings.append("non_runners_file_not_found — non-runner check skipped")

    # --- No NAP selected ---
    if nap is None:
        return "NO_BET", None, None, warnings

    horse_name = str(nap.get("horse") or "")
    horse_id   = str(nap.get("horse_id") or "")

    # --- Non-runner check ---
    # Match by horse name (case-insensitive)
    horse_lower = horse_name.lower()
    is_nr = any(
        horse_lower == nr or horse_lower in nr or nr in horse_lower
        for nr in non_runners
        if nr
    )
    if is_nr:
        log(
            f"final_nap_decision: NAP '{horse_name}' appears in non-runners list",
            "WARNING",
        )
        nap_summary = {
            "horse":      horse_name,
            "course":     nap.get("course", ""),
            "off_time":   nap.get("off_time", ""),
            "latest_odds": None,
            "movement":   "unknown",
            "status":     "NON_RUNNER",
        }
        return "BLOCKED", "NAP is a non-runner", nap_summary, warnings

    # --- Dangerous drift check ---
    nap_warnings: list[str] = nap.get("warnings") or []
    if "dangerous_drift" in nap_warnings:
        log(
            f"final_nap_decision: NAP '{horse_name}' has dangerous_drift warning",
            "WARNING",
        )
        nap_summary = {
            "horse":       horse_name,
            "course":      nap.get("course", ""),
            "off_time":    nap.get("off_time", ""),
            "latest_odds": nap.get("morning_price") or nap.get("sp_dec"),
            "movement":    "dangerous_drift",
            "status":      "LIVE",
        }
        return "BLOCKED", "Dangerous drift warning", nap_summary, warnings

    # --- Market movement ---
    movement    = _get_market_movement(horse_id, market_movers)
    # nap_candidates entries carry "morning_price" (not "sp_dec")
    latest_odds = _get_latest_odds(
        horse_id, market_movers, nap.get("morning_price") or nap.get("sp_dec")
    )

    # Also check for dangerous_drift surfaced via movers (belt-and-braces)
    if movement == "dangerous_drift":
        log(
            f"final_nap_decision: market_movers confirms dangerous_drift "
            f"for '{horse_name}'",
            "WARNING",
        )
        nap_summary = {
            "horse":       horse_name,
            "course":      nap.get("course", ""),
            "off_time":    nap.get("off_time", ""),
            "latest_odds": latest_odds,
            "movement":    movement,
            "status":      "LIVE",
        }
        return "BLOCKED", "Dangerous drift confirmed in market movers", nap_summary, warnings

    # --- All checks passed ---
    nap_summary = {
        "horse":       horse_name,
        "course":      nap.get("course", ""),
        "off_time":    nap.get("off_time", ""),
        "latest_odds": latest_odds,
        "movement":    movement,
        "status":      "LIVE",
    }

    return "CONFIRMED", None, nap_summary, warnings


# ---------------------------------------------------------------------------
# Report formatter
# ---------------------------------------------------------------------------

def _format_text_report(
    date_str: str,
    generated_hm: str,
    status: str,
    block_reason: str | None,
    nap_summary: dict | None,
    warnings: list[str],
) -> str:
    sep = "═" * 56
    lines: list[str] = [
        sep,
        "  FINAL NAP DECISION — Market Update",
        f"  Date: {date_str}  |  Generated: {generated_hm}",
        sep,
        "",
    ]

    if status == "CONFIRMED":
        horse     = nap_summary.get("horse", "N/A") if nap_summary else "N/A"
        course    = nap_summary.get("course", "") if nap_summary else ""
        off_time  = nap_summary.get("off_time", "") if nap_summary else ""
        latest    = nap_summary.get("latest_odds") if nap_summary else None
        movement  = nap_summary.get("movement", "unknown") if nap_summary else "unknown"

        odds_str  = format_odds(latest) if latest else "N/A"
        dec_str   = f"({latest:.2f})" if latest else ""

        # Movement display
        movement_arrow = {
            "strong_steamer": "Steamer ↑↑",
            "steamer":        "Steamer ↑",
            "late_support":   "Late support ↑",
            "stable":         "Stable →",
            "weak_drift":     "Drifting ↓",
            "unknown":        "Unknown",
        }.get(movement, movement.title())

        lines += [
            "STATUS: CONFIRMED NAP",
            "",
            f"  NAP: {horse.upper()} — {course} {off_time}",
            f"  Latest odds: {odds_str} {dec_str}",
            f"  Movement: {movement_arrow}",
            "  Safe to bet: YES",
        ]

    elif status == "BLOCKED":
        reason = block_reason or "Unknown reason"
        horse_line = ""
        if nap_summary:
            horse_line = (
                f"  (Horse: {nap_summary.get('horse', 'N/A')} — "
                f"{nap_summary.get('course', '')} {nap_summary.get('off_time', '')})"
            )
        lines += [
            f"STATUS: BLOCKED — {reason}",
            "",
            f"  ⚠ BLOCKED — {reason}",
        ]
        if horse_line:
            lines.append(horse_line)
        lines.append("  No official bet today.")

    else:  # NO_BET
        lines += [
            "STATUS: NO BET",
            "",
            "  No clear NAP after market review.",
            "  No official bet today.",
        ]

    if warnings:
        lines.append("")
        lines.append("  Warnings:")
        for w in warnings:
            lines.append(f"    - {w}")

    lines.append("")
    lines.append(sep)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Run final NAP decision. Returns exit code."""
    log("final_nap_decision.py started")

    date_str     = today_str()
    now          = datetime.now(timezone.utc)
    generated_at = now.isoformat()
    generated_hm = now.strftime("%H:%M")

    # ------------------------------------------------------------------
    # 1. Load nap_candidates (required)
    # ------------------------------------------------------------------
    candidates_path = data_path(f"nap_candidates_{date_str}.json")
    candidates      = safe_load_json(candidates_path)

    if candidates is None:
        log(
            "final_nap_decision: nap_candidates file not found — BLOCKED",
            "ERROR",
        )
        status       = "BLOCKED"
        block_reason = "NAP candidates file not found"
        nap_summary  = None
        warnings: list[str] = ["nap_candidates_missing"]

        # Fall through to output — do not return early
    else:
        # ------------------------------------------------------------------
        # 2. Load market_movers (optional — never block)
        # ------------------------------------------------------------------
        mm_path      = data_path(f"market_movers_{date_str}.json")
        market_movers: dict | None = safe_load_json(mm_path)
        mm_available  = market_movers is not None

        if not mm_available:
            log(
                "final_nap_decision: market_movers not available — "
                "continuing with warning",
                "WARNING",
            )

        # ------------------------------------------------------------------
        # 3. Load non-runners (optional — warn, never block)
        # ------------------------------------------------------------------
        non_runners, nr_file_found = _load_non_runners(date_str)

        # ------------------------------------------------------------------
        # 4. Apply decision logic
        # ------------------------------------------------------------------
        nap = candidates.get("nap")
        day_verdict = candidates.get("day_verdict") or "UNKNOWN"

        # If candidates says BLOCKED or no NAP, respect that first
        if day_verdict == "BLOCKED":
            status       = "BLOCKED"
            block_reason = candidates.get("block_reason") or "Blocked by nap_selector_v3"
            nap_summary  = None
            warnings     = ["inherited_block_from_nap_selector"]
        else:
            status, block_reason, nap_summary, warnings = _make_decision(
                nap,
                non_runners,
                nr_file_found,
                market_movers,
                mm_available,
            )

    safe_to_bet = (status == "CONFIRMED")

    # ------------------------------------------------------------------
    # 5. Build and save JSON output
    # ------------------------------------------------------------------
    output: dict = {
        "date":         date_str,
        "generated_at": generated_at,
        "status":       status,
        "block_reason": block_reason,
        "nap":          nap_summary,
        "value_ew":     None,   # populated by optional EW script if present
        "warnings":     warnings,
        "safe_to_bet":  safe_to_bet,
    }

    json_dest = data_path(f"final_nap_decision_{date_str}.json")
    if not safe_write_json(json_dest, output):
        log(f"final_nap_decision: failed to write JSON — {json_dest}", "ERROR")
        return 1
    log(f"final_nap_decision: JSON saved → {json_dest}")

    # ------------------------------------------------------------------
    # 6. Build and save text report
    # ------------------------------------------------------------------
    report_text = _format_text_report(
        date_str,
        generated_hm,
        status,
        block_reason,
        nap_summary,
        warnings,
    )
    report_dest = report_path(f"final_nap_decision_{date_str}.txt")
    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
        log(f"final_nap_decision: text report saved → {report_dest}")
    except OSError as exc:
        log(f"final_nap_decision: failed to write text report — {exc}", "ERROR")
        return 1

    # ------------------------------------------------------------------
    # 7. Print summary
    # ------------------------------------------------------------------
    if status == "CONFIRMED" and nap_summary:
        print(
            f"final_nap_decision: CONFIRMED — {nap_summary['horse']}"
            f" ({nap_summary['course']} {nap_summary['off_time']})"
            f" safe_to_bet=True"
        )
    elif status == "BLOCKED":
        print(f"final_nap_decision: BLOCKED — {block_reason}")
    else:
        print("final_nap_decision: NO_BET — no NAP confirmed after market review")

    return 0


if __name__ == "__main__":
    sys.exit(main())
