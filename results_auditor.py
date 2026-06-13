"""
results_auditor.py — Pull evening results from the API and audit how selected
horses performed.

Pipeline:
    1. Load data/final_nap_decision_YYYY-MM-DD.json  (official bet details)
    2. Load data/nap_candidates_YYYY-MM-DD.json       (all candidates)
    3. For each race with a candidate, call get_client().get_race_results()
    4. Exit code 2 if results are not yet available ("retry later")
    5. Record position, beaten_lengths, SP and calculate P/L

Outputs:
    data/results_YYYY-MM-DD.json
    reports/results_audit_YYYY-MM-DD.txt

Exit codes:
    0  — success
    1  — unrecoverable error
    2  — results not yet available (retry later)
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
from src.api_client import get_client, RacingAPIError


# ---------------------------------------------------------------------------
# P/L helpers
# ---------------------------------------------------------------------------

def _calc_official_pl(position: Optional[int], sp_decimal: float, stake: float) -> float:
    """Calculate P/L for a win-only bet.

    Win:  (sp_decimal - 1) * stake
    Loss: -stake
    """
    if position == 1 and sp_decimal and sp_decimal > 1.0:
        return round((sp_decimal - 1.0) * stake, 2)
    return round(-stake, 2)


# ---------------------------------------------------------------------------
# Result extraction
# ---------------------------------------------------------------------------

def _find_horse_in_results(horse_id: str, horse_name: str, api_results: dict) -> dict:
    """Find a specific horse within an API race-result response.

    The Racing API returns a dict with a 'results' or 'runners' list.
    Returns a normalised dict with position, beaten_lengths, sp_decimal.
    Missing data yields safe defaults.
    """
    runners: list[dict] = (
        api_results.get("results")
        or api_results.get("runners")
        or api_results.get("data")
        or []
    )

    # Match by horse_id first, then fall back to name comparison.
    matched: Optional[dict] = None
    for r in runners:
        if str(r.get("horse_id") or "") == horse_id:
            matched = r
            break
        if matched is None:
            r_name = str(r.get("horse") or r.get("horse_name") or "").strip().lower()
            if r_name and r_name == horse_name.strip().lower():
                matched = r

    if matched is None:
        return {
            "position": None,
            "beaten_lengths": None,
            "sp_decimal": None,
        }

    # Extract position — the API may return int, string "1", or "1st" etc.
    raw_pos = matched.get("position") or matched.get("finish_position") or matched.get("pos")
    position: Optional[int] = None
    if raw_pos is not None:
        try:
            position = int(str(raw_pos).strip().rstrip("stndrh"))
        except (ValueError, TypeError):
            position = None

    # Beaten lengths
    raw_bl = matched.get("beaten_lengths") or matched.get("btn") or matched.get("distance_beaten")
    beaten_lengths: Optional[float] = None
    if raw_bl is not None and raw_bl != "":
        try:
            beaten_lengths = float(str(raw_bl).replace("l", "").strip())
        except (ValueError, TypeError):
            beaten_lengths = None
    if position == 1:
        beaten_lengths = 0.0

    # SP decimal
    raw_sp = (
        matched.get("sp_dec")
        or matched.get("sp")
        or matched.get("starting_price_dec")
    )
    sp_decimal: Optional[float] = None
    if raw_sp is not None:
        try:
            sp_decimal = float(raw_sp)
            if sp_decimal <= 1.0:
                sp_decimal = None
        except (ValueError, TypeError):
            sp_decimal = None

    return {
        "position": position,
        "beaten_lengths": beaten_lengths,
        "sp_decimal": sp_decimal,
    }


def _find_winner_in_results(api_results: dict) -> tuple[Optional[str], Optional[float]]:
    """Return (winner_name, winner_sp) from API race results."""
    runners: list[dict] = (
        api_results.get("results")
        or api_results.get("runners")
        or api_results.get("data")
        or []
    )
    for r in runners:
        raw_pos = r.get("position") or r.get("finish_position") or r.get("pos")
        try:
            pos = int(str(raw_pos).strip().rstrip("stndrh"))
        except (ValueError, TypeError):
            pos = None
        if pos == 1:
            name = str(r.get("horse") or r.get("horse_name") or "")
            raw_sp = r.get("sp_dec") or r.get("sp") or r.get("starting_price_dec")
            sp: Optional[float] = None
            try:
                sp = float(raw_sp) if raw_sp is not None else None
                if sp is not None and sp <= 1.0:
                    sp = None
            except (ValueError, TypeError):
                sp = None
            return name or None, sp
    return None, None


# ---------------------------------------------------------------------------
# Candidate extraction
# ---------------------------------------------------------------------------

def _extract_candidates(candidates_doc: dict) -> list[dict]:
    """Flatten all candidates from nap_candidates doc into a single list."""
    all_candidates: list[dict] = []

    nap = candidates_doc.get("nap")
    if nap:
        c = dict(nap)
        c["candidate_type"] = "nap"
        all_candidates.append(c)

    best = candidates_doc.get("best_of_card")
    if best:
        c = dict(best)
        c["candidate_type"] = "value_ew"
        all_candidates.append(c)

    for h in (candidates_doc.get("watchlist") or []):
        c = dict(h)
        c["candidate_type"] = "watchlist"
        all_candidates.append(c)

    for h in (candidates_doc.get("shadow") or []):
        c = dict(h)
        c["candidate_type"] = "shadow"
        all_candidates.append(c)

    return all_candidates


# ---------------------------------------------------------------------------
# Report formatter
# ---------------------------------------------------------------------------

def _format_text_report(
    date_str: str,
    generated_hm: str,
    official_results: list[dict],
    shadow_results: list[dict],
    watchlist_results: list[dict],
    summary: dict,
) -> str:
    lines: list[str] = [
        "EVENING RESULTS AUDIT",
        f"Date: {date_str} | Compiled: {generated_hm}",
        "",
        "OFFICIAL SELECTIONS:",
    ]

    if not official_results:
        lines.append("  No official selections today.")
    else:
        for res in official_results:
            horse = res.get("horse", "Unknown")
            course = res.get("course", "")
            off_time = res.get("off_time", "")
            ctype = res.get("candidate_type", "").upper()
            pos = res.get("position")
            sp = res.get("sp_decimal")
            pl = res.get("official_pl", 0.0)
            bl = res.get("beaten_lengths")

            sp_str = format_odds(sp) if sp else "N/A"
            if pos == 1:
                pos_label = "1st"
            elif pos == 2:
                pos_label = "2nd"
            elif pos == 3:
                pos_label = "3rd"
            elif pos:
                pos_label = f"{pos}th"
            else:
                pos_label = "N/R"

            won_mark = "+" if res.get("won") else " "
            lines.append(f"  [{won_mark}] {ctype}: {horse.upper()} — {course} {off_time}")
            bl_str = f" ({bl}L)" if bl is not None and bl > 0 else ""
            lines.append(f"    Result: {pos_label}{bl_str} | SP: {sp_str} | P/L: {pl:+.2f} units")
            lines.append("")

    if watchlist_results:
        lines.append("WATCHLIST:")
        for res in watchlist_results:
            horse = res.get("horse", "Unknown")
            course = res.get("course", "")
            off_time = res.get("off_time", "")
            pos = res.get("position")
            sp = res.get("sp_decimal")
            sp_str = format_odds(sp) if sp else "N/A"
            pos_label = f"{pos}" if pos else "N/R"
            lines.append(f"  Watchlist: {horse.upper()} — {course} {off_time}")
            lines.append(f"    Result: {pos_label} | SP: {sp_str} | (Watchlist — not in official P/L)")
            lines.append("")

    if shadow_results:
        lines.append("SHADOW SELECTIONS (tracking only):")
        for res in shadow_results:
            horse = res.get("horse", "Unknown")
            course = res.get("course", "")
            off_time = res.get("off_time", "")
            pos = res.get("position")
            sp = res.get("sp_decimal")
            sp_str = format_odds(sp) if sp else "N/A"
            pos_label = f"{pos}" if pos else "N/R"
            lines.append(f"  Shadow: {horse.upper()} — {course} {off_time}")
            lines.append(f"    Result: {pos_label} | SP: {sp_str} | (Shadow only — not in official P/L)")
            lines.append("")

    official_pl = summary.get("official_pl", 0.0)
    pl_sign = "+" if official_pl >= 0 else ""
    lines += [
        "=" * 50,
        f"OFFICIAL P/L TODAY: {pl_sign}{official_pl:.2f} units",
        f"Official bets: {summary.get('official_bets', 0)}  "
        f"Wins: {summary.get('official_wins', 0)}",
        f"Shadow bets: {summary.get('shadow_bets', 0)}  "
        f"Shadow wins: {summary.get('shadow_wins', 0)}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Run results audit. Returns exit code.

    Optional argv[1] = YYYY-MM-DD overrides the date, so a day whose results
    published late can be recovered the next evening instead of becoming a
    permanent gap in P/L and learning data.
    """
    log("results_auditor.py started")

    # Define date first — avoids any possible NameError downstream.
    date_str: str = today_str()
    if len(sys.argv) > 1 and sys.argv[1].strip():
        date_str = sys.argv[1].strip()
        log(f"results_auditor: date override — auditing {date_str}")
    now = datetime.now(timezone.utc)
    audit_ts = now.isoformat()
    generated_hm = now.strftime("%H:%M")

    log(f"results_auditor: date={date_str}")

    # ------------------------------------------------------------------
    # 1. Load final_nap_decision (official bet reference)
    # ------------------------------------------------------------------
    decision_path = data_path(f"final_nap_decision_{date_str}.json")
    decision: Optional[dict] = safe_load_json(decision_path)
    if decision is None:
        log(
            f"results_auditor: final_nap_decision not found at {decision_path}. "
            "This is expected on NO_BET days.",
            "WARNING",
        )

    # ------------------------------------------------------------------
    # 2. Load nap_candidates (all candidates including watchlist/shadow)
    # ------------------------------------------------------------------
    candidates_path = data_path(f"nap_candidates_{date_str}.json")
    candidates_doc: Optional[dict] = safe_load_json(candidates_path)
    if candidates_doc is None:
        log(
            f"results_auditor: nap_candidates not found at {candidates_path}. "
            "Cannot audit — ensure nap_selector_v3.py has run.",
            "ERROR",
        )
        return 1

    all_candidates = _extract_candidates(candidates_doc)
    if not all_candidates:
        log("results_auditor: no candidates found — nothing to audit", "WARNING")

    # ------------------------------------------------------------------
    # 3. Collect unique race IDs and fetch results from API
    # ------------------------------------------------------------------
    client = get_client()

    race_id_groups: dict[str, list[dict]] = {}   # race_id -> list of candidates
    for candidate in all_candidates:
        rid = str(candidate.get("race_id") or "")
        if rid:
            race_id_groups.setdefault(rid, []).append(candidate)

    log(f"results_auditor: fetching results for {len(race_id_groups)} race(s)")

    api_results_cache: dict[str, dict] = {}

    for race_id in race_id_groups:
        log(f"results_auditor: fetching race_id={race_id}")
        try:
            result = client.get_race_results(race_id)
        except RacingAPIError as exc:
            log(
                f"results_auditor: API error fetching race {race_id} — {exc}",
                "ERROR",
            )
            # Treat as not-yet-available to allow retry.
            return 2

        if result is None:
            log(
                f"results_auditor: race {race_id} results not available yet (API returned None)",
                "WARNING",
            )
            # Exit code 2 signals "retry later" to the pipeline orchestrator.
            return 2

        api_results_cache[race_id] = result
        log(f"results_auditor: race {race_id} results received")

    # ------------------------------------------------------------------
    # 4. Process each candidate against fetched results
    # ------------------------------------------------------------------
    official_stake = 1.0   # 1 unit per official bet

    official_results: list[dict] = []
    shadow_results: list[dict] = []
    watchlist_results: list[dict] = []

    for candidate in all_candidates:
        race_id = str(candidate.get("race_id") or "")
        horse_id = str(candidate.get("horse_id") or "")
        horse_name = str(candidate.get("horse") or "")
        ctype = candidate.get("candidate_type", "shadow")

        api_res = api_results_cache.get(race_id, {})
        extracted = _find_horse_in_results(horse_id, horse_name, api_res)

        position: Optional[int] = extracted["position"]
        beaten_lengths: Optional[float] = extracted["beaten_lengths"]
        sp_decimal: Optional[float] = extracted["sp_decimal"]

        won = position == 1
        placed = position is not None and position <= 3

        result_row: dict = {
            "horse_id":       horse_id,
            "horse":          horse_name,
            "race_id":        race_id,
            "course":         candidate.get("course", ""),
            "off_time":       candidate.get("off_time", ""),
            "candidate_type": ctype,
            "grade":          candidate.get("grade", ""),
            "score":          candidate.get("score", 0),
            "position":       position,
            "beaten_lengths": beaten_lengths,
            "sp_decimal":     sp_decimal,
            "won":            won,
            "placed":         placed,
        }

        if ctype in ("nap", "value_ew"):
            pl = _calc_official_pl(position, sp_decimal or 0.0, official_stake)
            result_row["official_stake"] = official_stake
            result_row["official_pl"] = pl
            official_results.append(result_row)

        elif ctype == "shadow":
            result_row["official_stake"] = 0.0
            result_row["official_pl"] = 0.0
            shadow_results.append(result_row)

        else:   # watchlist and any other type
            result_row["official_stake"] = 0.0
            result_row["official_pl"] = 0.0
            watchlist_results.append(result_row)

    # ------------------------------------------------------------------
    # 5. Summary
    # ------------------------------------------------------------------
    total_official_pl = round(sum(r.get("official_pl", 0.0) for r in official_results), 2)
    official_wins = sum(1 for r in official_results if r.get("won"))
    shadow_wins = sum(1 for r in shadow_results if r.get("won"))

    summary: dict = {
        "official_bets":  len(official_results),
        "official_wins":  official_wins,
        "official_pl":    total_official_pl,
        "shadow_bets":    len(shadow_results),
        "shadow_wins":    shadow_wins,
    }

    # ------------------------------------------------------------------
    # 6. Save JSON
    # ------------------------------------------------------------------
    output: dict = {
        "date":              date_str,
        "audit_ts":          audit_ts,
        "official_results":  official_results,
        "shadow_results":    shadow_results,
        "watchlist_results": watchlist_results,
        "summary":           summary,
    }

    json_dest = data_path(f"results_{date_str}.json")
    if not safe_write_json(json_dest, output):
        log(f"results_auditor: failed to write results JSON — {json_dest}", "ERROR")
        return 1
    log(f"results_auditor: results JSON saved → {json_dest}")

    # ------------------------------------------------------------------
    # 7. Save text report
    # ------------------------------------------------------------------
    report_text = _format_text_report(
        date_str,
        generated_hm,
        official_results,
        shadow_results,
        watchlist_results,
        summary,
    )
    report_dest = report_path(f"results_audit_{date_str}.txt")
    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
        log(f"results_auditor: text report saved → {report_dest}")
    except OSError as exc:
        log(f"results_auditor: failed to write text report — {exc}", "ERROR")
        return 1

    # ------------------------------------------------------------------
    # 8. Console summary
    # ------------------------------------------------------------------
    pl_sign = "+" if total_official_pl >= 0 else ""
    print(
        f"results_auditor: COMPLETE — "
        f"official_bets={len(official_results)}, "
        f"wins={official_wins}, "
        f"P/L={pl_sign}{total_official_pl:.2f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
