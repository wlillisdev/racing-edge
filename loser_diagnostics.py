"""
loser_diagnostics.py — After a losing day, classify WHY the selection lost.

Only runs analysis when an official NAP exists and lost (position > 1 or None).
If no NAP today or NAP won, writes a brief "no diagnostics needed" report.

Failure classifications (applied in order; first match wins):
  bad_form_read           — model score below 55 — insufficient confidence
  place_profile_promoted  — horse's form shows 2s/3s but weak win record
  cluster_race            — race was clustered but NAP selected anyway
  market_warning_ignored  — horse had a drift warning in market data
  race_type_mismatch      — wins on different surface/distance
  pipeline_data_issue     — market or non-runner data was missing
  unlucky_or_excused      — beaten < 2 lengths (potential flag for next time)

Inputs:
    data/results_YYYY-MM-DD.json
    data/nap_candidates_YYYY-MM-DD.json

Outputs:
    reports/loser_diagnostics_YYYY-MM-DD.txt
    data/loser_diagnostics_YYYY-MM-DD.json

Exit codes:
    0  — success (including "no diagnostics needed" case)
    1  — write error
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Optional

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
# Thresholds
# ---------------------------------------------------------------------------

# Score below this: model was not confident — "bad_form_read"
BAD_FORM_SCORE_THRESHOLD: float = 55.0

# Beaten by less than this (lengths): "unlucky_or_excused"
UNLUCKY_BEATEN_THRESHOLD: float = 2.0

# Minimum ratio of '2'/'3' chars to total chars for "place_profile_promoted"
PLACE_PROFILE_RATIO: float = 0.5


# ---------------------------------------------------------------------------
# Form parser (same logic as rest of system)
# ---------------------------------------------------------------------------

def _parse_form(form: str) -> list[str]:
    if not form or form.strip() in ("-", ""):
        return []
    form = form.strip().replace(" ", "")
    last_dash = form.rfind("-")
    segment = form[last_dash + 1:] if last_dash != -1 else form
    valid: list[str] = []
    for ch in reversed(segment):
        upper = ch.upper()
        if upper.isdigit() or upper in ("F", "U", "P", "R", "B"):
            valid.append(upper)
    return valid


# ---------------------------------------------------------------------------
# Classification logic
# ---------------------------------------------------------------------------

def _classify_loss(
    nap: dict,
    result: dict,
    candidates_doc: dict,
) -> tuple[str, str, str]:
    """Classify the loss for a NAP horse.

    Returns (failure_type, description, recommended_action).
    """
    score: float = float(nap.get("score") or result.get("score") or 0)
    warnings: list[str] = list(nap.get("warnings") or [])
    form: str = str(nap.get("form") or "")
    beaten_lengths: Optional[float] = result.get("beaten_lengths")

    # Retrieve cluster races from candidates doc.
    cluster_races: list[str] = candidates_doc.get("cluster_races") or []
    race_id: str = str(nap.get("race_id") or result.get("race_id") or "")

    # --- 1. Bad form read: score below threshold ---
    if score < BAD_FORM_SCORE_THRESHOLD:
        return (
            "bad_form_read",
            f"Model score was {score:.1f} — below the {BAD_FORM_SCORE_THRESHOLD} confidence threshold. "
            "Selection was made on marginal evidence.",
            "Raise NAP minimum score threshold. Review what caused the low confidence.",
        )

    # --- 2. Place profile promoted: form is 2s/3s not 1s ---
    chars = _parse_form(form)
    if chars:
        win_count   = chars.count("1")
        place_count = sum(1 for c in chars if c in ("2", "3"))
        total_runs  = sum(1 for c in chars if c.isdigit())

        if total_runs >= 3 and win_count == 0 and place_count >= 2:
            ratio = place_count / total_runs
            if ratio >= PLACE_PROFILE_RATIO:
                return (
                    "place_profile_promoted",
                    f"Horse shows consistent placing ({place_count} places, {win_count} wins "
                    f"from {total_runs} runs). Form string: {form}. "
                    "Selected without a recent winning run.",
                    "Require at least one win in last 6 runs for NAP selection. "
                    "Consider value EW instead for consistent placers.",
                )

    # --- 3. Cluster race: race was identified as clustered ---
    if race_id in cluster_races:
        return (
            "cluster_race",
            f"Race {race_id} was flagged as a cluster race (two evenly-matched runners). "
            "NAP was selected from a race without a clear standout.",
            "Enforce the cluster block more strictly. Do not select NAP from clustered races.",
        )

    # --- 4. Market warning ignored ---
    drift_warnings = [w for w in warnings if "drift" in w.lower()]
    if drift_warnings:
        return (
            "market_warning_ignored",
            f"Horse carried market warning(s): {', '.join(drift_warnings)}. "
            "A drift signal was present but selection proceeded.",
            "Treat any drift warning as a hard veto. Review the market_movers logic.",
        )

    # --- 5. Race type / surface mismatch ---
    # Suitability score <= 5 suggests poor distance/going match.
    suit_score: float = float(nap.get("suitability_score") or 0)
    if suit_score <= 5.0:
        return (
            "race_type_mismatch",
            f"Suitability score was {suit_score:.1f}/30 — low going/distance match. "
            "Horse's wins may have come on different surface or trip.",
            "Increase weight of suitability score in NAP gate. "
            "Require minimum suitability score of 8 for official bets.",
        )

    # --- 6. Pipeline data issue ---
    no_odds_warning = "no_valid_odds" in warnings
    if no_odds_warning:
        return (
            "pipeline_data_issue",
            "Horse was selected without valid odds data (no_valid_odds flag present). "
            "Market or non-runner data may have been missing at selection time.",
            "Add a hard gate: do not select NAP if no valid SP is available. "
            "Check market_snapshot.py and non_runner_scan.py pipeline logs.",
        )

    # --- 7. Unlucky / excused (must be last — least concerning) ---
    if beaten_lengths is not None and 0 < beaten_lengths < UNLUCKY_BEATEN_THRESHOLD:
        return (
            "unlucky_or_excused",
            f"Horse ran well, beaten only {beaten_lengths}L. "
            "Result may be excused — narrow margin, could represent hidden value.",
            f"Flag horse for re-selection consideration. "
            "Monitor next run — beaten favourite in close finish often bounces back.",
        )

    # --- Default: no clear single cause ---
    return (
        "unclassified",
        f"Loss does not clearly match a single failure pattern. "
        f"Score={score:.1f}, Suitability={suit_score:.1f}, Beaten={beaten_lengths}L. "
        "Possible factors: race tactics, going deterioration, or simply beaten by better.",
        "Review in full in the next weekly analysis session. "
        "No immediate model change recommended.",
    )


# ---------------------------------------------------------------------------
# Report formatter
# ---------------------------------------------------------------------------

def _format_text_report(
    date_str: str,
    generated_hm: str,
    diagnostics: Optional[list[dict]],
    nap_won: bool,
    no_nap: bool,
) -> str:
    sep = "=" * 56
    lines: list[str] = [
        sep,
        "  LOSER DIAGNOSTICS",
        f"  Date: {date_str}  |  Generated: {generated_hm}",
        sep,
        "",
    ]

    if no_nap:
        lines += [
            "  No official NAP was selected today.",
            "  Loser diagnostics are not applicable.",
            "",
            sep,
        ]
        return "\n".join(lines)

    if nap_won:
        lines += [
            "  NAP WON today — no loser diagnostics needed.",
            "",
            sep,
        ]
        return "\n".join(lines)

    if not diagnostics:
        lines += [
            "  No losing NAP diagnostics to report.",
            "",
            sep,
        ]
        return "\n".join(lines)

    for d in diagnostics:
        horse      = d.get("horse", "Unknown")
        course     = d.get("course", "")
        off_time   = d.get("off_time", "")
        sp         = d.get("sp_decimal")
        pos        = d.get("position")
        bl         = d.get("beaten_lengths")
        grade      = d.get("grade", "")
        score      = d.get("score", 0)
        ftype      = d.get("failure_type", "unclassified")
        fdesc      = d.get("failure_description", "")
        faction    = d.get("recommended_action", "")

        sp_str  = format_odds(sp) if sp else "N/A"
        pos_str = f"{pos}" if pos else "N/R"
        bl_str  = f" ({bl}L)" if bl is not None and bl > 0 else ""

        lines += [
            f"  LOSING NAP: {horse.upper()} — {course} {off_time}",
            f"  Grade: {grade}  |  Score: {score:.1f}  |  SP: {sp_str}",
            f"  Result: {pos_str}{bl_str}",
            "",
            f"  FAILURE TYPE: {ftype.upper().replace('_', ' ')}",
            f"  {fdesc}",
            "",
            f"  RECOMMENDED ACTION:",
            f"  {faction}",
            "",
            "-" * 56,
            "",
        ]

    lines.append(sep)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Run loser diagnostics. Returns exit code."""
    log("loser_diagnostics.py started")

    # Define date at the very top — same defensive pattern as performance_tracker.
    date_str: str = today_str()
    now = datetime.now(timezone.utc)
    generated_hm = now.strftime("%H:%M")
    log(f"loser_diagnostics: date={date_str}")

    # ------------------------------------------------------------------
    # 1. Load results
    # ------------------------------------------------------------------
    results_path = data_path(f"results_{date_str}.json")
    results_doc: Optional[dict] = safe_load_json(results_path)

    if results_doc is None:
        log(
            f"loser_diagnostics: results file not found at {results_path}. "
            "Run results_auditor.py first.",
            "WARNING",
        )
        # Write a brief no-data report rather than crashing.
        _write_no_data_report(date_str, generated_hm, "Results file not available.")
        return 0

    # ------------------------------------------------------------------
    # 2. Load nap_candidates
    # ------------------------------------------------------------------
    candidates_path = data_path(f"nap_candidates_{date_str}.json")
    candidates_doc: Optional[dict] = safe_load_json(candidates_path)

    if candidates_doc is None:
        log(
            f"loser_diagnostics: nap_candidates not found at {candidates_path}.",
            "WARNING",
        )
        candidates_doc = {}

    # ------------------------------------------------------------------
    # 3. Find official NAP result(s)
    # ------------------------------------------------------------------
    official_results: list[dict] = results_doc.get("official_results") or []
    nap_results = [r for r in official_results if r.get("candidate_type") == "nap"]

    no_nap = len(nap_results) == 0
    nap_won = any(r.get("won") for r in nap_results)

    if no_nap:
        log("loser_diagnostics: no official NAP today — writing brief report", "INFO")
        report_text = _format_text_report(date_str, generated_hm, None, False, True)
        _save_outputs(date_str, now, report_text, [], no_nap=True, nap_won=False)
        print(f"loser_diagnostics: no NAP today — no diagnostics needed")
        return 0

    if nap_won:
        log("loser_diagnostics: NAP won today — no loss diagnostics needed", "INFO")
        report_text = _format_text_report(date_str, generated_hm, None, True, False)
        _save_outputs(date_str, now, report_text, [], no_nap=False, nap_won=True)
        print(f"loser_diagnostics: NAP won — no diagnostics needed")
        return 0

    # ------------------------------------------------------------------
    # 4. Classify each losing NAP
    # ------------------------------------------------------------------
    # Build a map of horse_id -> nap candidate record from candidates_doc.
    nap_candidate = candidates_doc.get("nap") or {}

    diagnostics: list[dict] = []

    for result in nap_results:
        if result.get("won"):
            continue  # Skip winners (should be none given checks above).

        horse_id   = str(result.get("horse_id") or "")
        horse_name = str(result.get("horse") or "")

        # Find the candidate record.
        if str(nap_candidate.get("horse_id") or "") == horse_id:
            nap_record = nap_candidate
        else:
            nap_record = result   # Fall back to result row if no candidate match.

        failure_type, failure_desc, recommended_action = _classify_loss(
            nap_record, result, candidates_doc
        )

        log(
            f"loser_diagnostics: {horse_name} — classified as {failure_type}",
            "INFO",
        )

        diagnostics.append({
            "horse_id":              horse_id,
            "horse":                 horse_name,
            "race_id":               result.get("race_id", ""),
            "course":                result.get("course", ""),
            "off_time":              result.get("off_time", ""),
            "grade":                 result.get("grade", ""),
            "score":                 result.get("score", 0),
            "sp_decimal":            result.get("sp_decimal"),
            "position":              result.get("position"),
            "beaten_lengths":        result.get("beaten_lengths"),
            "failure_type":          failure_type,
            "failure_description":   failure_desc,
            "recommended_action":    recommended_action,
            "warnings":              nap_record.get("warnings") or [],
        })

    # ------------------------------------------------------------------
    # 5. Save outputs
    # ------------------------------------------------------------------
    report_text = _format_text_report(date_str, generated_hm, diagnostics, False, False)
    rc = _save_outputs(date_str, now, report_text, diagnostics, no_nap=False, nap_won=False)

    if rc != 0:
        return rc

    print(
        f"loser_diagnostics: COMPLETE — "
        f"{len(diagnostics)} losing NAP(s) classified"
    )
    return 0


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _write_no_data_report(date_str: str, generated_hm: str, reason: str) -> None:
    report_text = (
        f"LOSER DIAGNOSTICS\n"
        f"Date: {date_str} | Generated: {generated_hm}\n\n"
        f"No loser diagnostics needed today.\n"
        f"Reason: {reason}\n"
    )
    _save_report(date_str, report_text)
    safe_write_json(
        data_path(f"loser_diagnostics_{date_str}.json"),
        {
            "date": date_str,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "diagnostics_needed": False,
            "reason": reason,
            "diagnostics": [],
        },
    )


def _save_outputs(
    date_str: str,
    now: datetime,
    report_text: str,
    diagnostics: list[dict],
    no_nap: bool,
    nap_won: bool,
) -> int:
    """Save JSON and text report. Returns 0 on success, 1 on write error."""
    json_payload: dict = {
        "date":               date_str,
        "generated_at":       now.isoformat(),
        "diagnostics_needed": not no_nap and not nap_won,
        "no_nap":             no_nap,
        "nap_won":            nap_won,
        "diagnostics":        diagnostics,
    }

    json_dest = data_path(f"loser_diagnostics_{date_str}.json")
    if not safe_write_json(json_dest, json_payload):
        log(f"loser_diagnostics: failed to write JSON — {json_dest}", "ERROR")
        return 1
    log(f"loser_diagnostics: JSON saved → {json_dest}")

    return _save_report(date_str, report_text)


def _save_report(date_str: str, text: str) -> int:
    report_dest = report_path(f"loser_diagnostics_{date_str}.txt")
    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(text)
        log(f"loser_diagnostics: text report saved → {report_dest}")
        return 0
    except OSError as exc:
        log(f"loser_diagnostics: failed to write text report — {exc}", "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
