"""
result_enricher.py — Enrich results data with additional context for the
evidence warehouse.

For each result, adds:
  - beaten_by_winner:    Horse name that won (if not our horse)
  - winner_sp:           The winner's SP decimal (if available from API results)
  - race_pace_indicator: "fast" | "honest" | "slow" based on field behaviour
  - was_easy_win:        True if won by more than 5 lengths (dominant)
  - was_close_second:    True if placed within 1 length (unlucky/near miss)

This enriched data feeds the evidence warehouse for pattern learning.

Input:
    data/results_YYYY-MM-DD.json

Output:
    data/results_enriched_YYYY-MM-DD.json

Exit codes:
    0  — success
    1  — unrecoverable error (missing results or write failure)
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Optional

from src.helpers import (
    data_path,
    log,
    safe_load_json,
    safe_write_json,
    today_str,
)
from src.api_client import get_client, RacingAPIError


# ---------------------------------------------------------------------------
# Configuration thresholds
# ---------------------------------------------------------------------------

EASY_WIN_THRESHOLD: float   = 5.0   # Lengths — dominant performance
CLOSE_SECOND_THRESHOLD: float = 1.0  # Lengths — near miss / unlucky

# If this many runners did not complete (F/U/P), flag pace as "fast".
FAST_PACE_FAIL_THRESHOLD: int = 2


# ---------------------------------------------------------------------------
# Pace indicator helpers
# ---------------------------------------------------------------------------

def _classify_pace(api_result: dict) -> str:
    """Classify race pace from the result data.

    Logic:
      - Count runners with F/U/P positions.
      - If >= FAST_PACE_FAIL_THRESHOLD → "fast" (strong pace caused attrition).
      - Otherwise check if the winner's time beats the course record (not
        available in basic API response) → default to "honest".
      - If all runners completed and field was small → "slow" is possible but
        we can only detect it via course/track records, so default to "honest".
    """
    runners: list[dict] = (
        api_result.get("results")
        or api_result.get("runners")
        or api_result.get("data")
        or []
    )

    if not runners:
        return "honest"

    fail_chars = frozenset(("F", "U", "P", "R", "B", "f", "u", "p", "r", "b"))
    fail_count = 0

    for r in runners:
        raw_pos = str(
            r.get("position")
            or r.get("finish_position")
            or r.get("pos")
            or ""
        ).strip().upper()

        # Check if the position field indicates a non-completion.
        if raw_pos in fail_chars or (len(raw_pos) == 1 and raw_pos in fail_chars):
            fail_count += 1

    if fail_count >= FAST_PACE_FAIL_THRESHOLD:
        return "fast"

    # Further heuristic: if the winner won by a very large margin, the pace
    # may have been slow (one runner dominated). But without time data we
    # cannot confirm "slow" definitively — default to "honest".
    return "honest"


# ---------------------------------------------------------------------------
# Winner extraction
# ---------------------------------------------------------------------------

def _extract_winner(api_result: dict) -> tuple[Optional[str], Optional[float]]:
    """Return (winner_name, winner_sp) from API race result data."""
    runners: list[dict] = (
        api_result.get("results")
        or api_result.get("runners")
        or api_result.get("data")
        or []
    )

    for r in runners:
        raw_pos = r.get("position") or r.get("finish_position") or r.get("pos")
        try:
            pos = int(str(raw_pos).strip().rstrip("stndrh"))
        except (ValueError, TypeError):
            pos = None

        if pos == 1:
            name = str(r.get("horse") or r.get("horse_name") or "").strip()
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
# Row enricher
# ---------------------------------------------------------------------------

def _enrich_result_row(row: dict, api_result: Optional[dict]) -> dict:
    """Add enrichment fields to a single result row."""
    enriched = dict(row)

    horse_name  = str(row.get("horse") or "")
    position    = row.get("position")
    beaten_lengths = row.get("beaten_lengths")

    # beaten_by_winner and winner_sp
    if api_result:
        winner_name, winner_sp = _extract_winner(api_result)
        if winner_name and winner_name.lower() != horse_name.lower():
            enriched["beaten_by_winner"] = winner_name
        else:
            enriched["beaten_by_winner"] = None   # this horse won
        enriched["winner_sp"] = winner_sp
    else:
        enriched["beaten_by_winner"] = None
        enriched["winner_sp"] = None

    # race_pace_indicator
    if api_result:
        enriched["race_pace_indicator"] = _classify_pace(api_result)
    else:
        enriched["race_pace_indicator"] = "unknown"

    # was_easy_win: won by more than EASY_WIN_THRESHOLD lengths
    if position == 1 and beaten_lengths is not None:
        # When our horse won, beaten_lengths = 0 (margin over 2nd place
        # would need full runner list). For now, check if the API result
        # has a margin field for the winner.
        winner_margin: Optional[float] = None
        if api_result:
            runners: list[dict] = (
                api_result.get("results")
                or api_result.get("runners")
                or api_result.get("data")
                or []
            )
            # Find the 2nd placed horse's beaten_lengths as proxy for win margin.
            for r in runners:
                raw_pos = r.get("position") or r.get("finish_position") or r.get("pos")
                try:
                    rpos = int(str(raw_pos).strip().rstrip("stndrh"))
                except (ValueError, TypeError):
                    rpos = None
                if rpos == 2:
                    raw_bl = r.get("beaten_lengths") or r.get("btn") or r.get("distance_beaten")
                    try:
                        winner_margin = float(str(raw_bl).replace("l", "").strip())
                    except (ValueError, TypeError):
                        winner_margin = None
                    break

        if winner_margin is not None:
            enriched["was_easy_win"] = winner_margin > EASY_WIN_THRESHOLD
        else:
            enriched["was_easy_win"] = False   # Cannot confirm without margin data
    else:
        enriched["was_easy_win"] = False

    # was_close_second: placed (pos 2 or 3) within CLOSE_SECOND_THRESHOLD lengths
    try:
        pos_int = int(position) if position is not None else None
    except (TypeError, ValueError):
        pos_int = None

    if pos_int is not None and pos_int in (2, 3) and beaten_lengths is not None:
        try:
            bl_float = float(beaten_lengths)
            enriched["was_close_second"] = bl_float <= CLOSE_SECOND_THRESHOLD
        except (TypeError, ValueError):
            enriched["was_close_second"] = False
    else:
        enriched["was_close_second"] = False

    return enriched


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Run result enrichment. Returns exit code."""
    log("result_enricher.py started")

    # Date defined first — consistent with defensive pattern across all scripts.
    date_str: str = today_str()
    now = datetime.now(timezone.utc)
    log(f"result_enricher: date={date_str}")

    # ------------------------------------------------------------------
    # 1. Load results
    # ------------------------------------------------------------------
    results_path = data_path(f"results_{date_str}.json")
    results_doc: Optional[dict] = safe_load_json(results_path)

    if results_doc is None:
        log(
            f"result_enricher: results file not found at {results_path}. "
            "Run results_auditor.py first.",
            "ERROR",
        )
        return 1

    # ------------------------------------------------------------------
    # 2. Collect unique race IDs across all result lists
    # ------------------------------------------------------------------
    all_result_rows: list[dict] = []
    for key in ("official_results", "shadow_results", "watchlist_results"):
        all_result_rows.extend(results_doc.get(key) or [])

    race_ids: set[str] = set()
    for row in all_result_rows:
        rid = str(row.get("race_id") or "")
        if rid:
            race_ids.add(rid)

    log(f"result_enricher: enriching {len(all_result_rows)} rows across {len(race_ids)} race(s)")

    # ------------------------------------------------------------------
    # 3. Fetch API results (needed for winner/pace data)
    # ------------------------------------------------------------------
    client = get_client()
    api_cache: dict[str, Optional[dict]] = {}

    for race_id in race_ids:
        try:
            api_result = client.get_race_results(race_id)
            api_cache[race_id] = api_result
            if api_result is None:
                log(f"result_enricher: no API result for race {race_id} — enrichment partial", "WARNING")
            else:
                log(f"result_enricher: fetched API result for race {race_id}")
        except RacingAPIError as exc:
            log(f"result_enricher: API error for race {race_id} — {exc}", "WARNING")
            api_cache[race_id] = None   # Continue with partial enrichment

    # ------------------------------------------------------------------
    # 4. Enrich each result row
    # ------------------------------------------------------------------
    enriched_official: list[dict] = []
    enriched_shadow: list[dict] = []
    enriched_watchlist: list[dict] = []

    for row in (results_doc.get("official_results") or []):
        api_res = api_cache.get(str(row.get("race_id") or ""))
        enriched_official.append(_enrich_result_row(row, api_res))

    for row in (results_doc.get("shadow_results") or []):
        api_res = api_cache.get(str(row.get("race_id") or ""))
        enriched_shadow.append(_enrich_result_row(row, api_res))

    for row in (results_doc.get("watchlist_results") or []):
        api_res = api_cache.get(str(row.get("race_id") or ""))
        enriched_watchlist.append(_enrich_result_row(row, api_res))

    # ------------------------------------------------------------------
    # 5. Build enriched output document
    # ------------------------------------------------------------------
    enriched_doc: dict = {
        "date":               date_str,
        "enriched_at":        now.isoformat(),
        "source_audit_ts":    results_doc.get("audit_ts", ""),
        "official_results":   enriched_official,
        "shadow_results":     enriched_shadow,
        "watchlist_results":  enriched_watchlist,
        "summary":            results_doc.get("summary", {}),
        "enrichment_meta": {
            "races_fetched":      len([v for v in api_cache.values() if v is not None]),
            "races_missing":      len([v for v in api_cache.values() if v is None]),
            "easy_wins":          sum(1 for r in enriched_official if r.get("was_easy_win")),
            "close_seconds":      sum(1 for r in enriched_official if r.get("was_close_second")),
            "fast_pace_races":    len({
                r.get("race_id") for r in enriched_official
                if r.get("race_pace_indicator") == "fast"
            }),
        },
    }

    # ------------------------------------------------------------------
    # 6. Save enriched JSON
    # ------------------------------------------------------------------
    json_dest = data_path(f"results_enriched_{date_str}.json")
    if not safe_write_json(json_dest, enriched_doc):
        log(f"result_enricher: failed to write enriched JSON — {json_dest}", "ERROR")
        return 1
    log(f"result_enricher: enriched JSON saved → {json_dest}")

    # ------------------------------------------------------------------
    # 7. Console summary
    # ------------------------------------------------------------------
    meta = enriched_doc["enrichment_meta"]
    print(
        f"result_enricher: COMPLETE — "
        f"rows={len(enriched_official)}, "
        f"easy_wins={meta['easy_wins']}, "
        f"close_seconds={meta['close_seconds']}, "
        f"fast_pace_races={meta['fast_pace_races']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
