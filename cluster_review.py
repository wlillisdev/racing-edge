"""
cluster_review.py — Identify clustered races and apply a cross-field cluster
warning to the NAP candidates document.

A race is "clustered" when the top-2 runners score within CLUSTER_SPREAD points
of each other AND both score >= CLUSTER_MIN_SCORE — no clean standout exists.

A "field cluster" warning is raised when the selected NAP's score is within
FIELD_CLUSTER_PCT % of the 2nd-highest scorer *across all races*.

Inputs:
  data/nap_candidates_YYYY-MM-DD.json   (produced by nap_selector_v3.py)

Outputs:
  reports/cluster_review_YYYY-MM-DD.txt    (human-readable)
  data/nap_candidates_YYYY-MM-DD.json      (updated in-place with confirmed clusters)

Exit codes:
  0 — success (cluster review complete — clusters found is not an error)
  1 — unrecoverable I/O error
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from src.helpers import (
    data_path,
    log,
    report_path,
    safe_load_json,
    safe_write_json,
    today_str,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CLUSTER_SPREAD: float   = 8.0    # max gap for per-race cluster
CLUSTER_MIN_SCORE: float = 55.0  # both runners must reach this to be clustered
FIELD_CLUSTER_PCT: float = 10.0  # secondary: NAP vs next-best, percent gap


# ---------------------------------------------------------------------------
# Per-race cluster detection
# ---------------------------------------------------------------------------

def _detect_race_cluster(runners: list[dict]) -> tuple[bool, str]:
    """
    Examine the top-2 runners in a race (already score-sorted descending).

    Returns (is_clustered, description).
    """
    if len(runners) < 2:
        return False, "Too few runners to form a cluster"

    top    = runners[0]
    second = runners[1]

    top_score    = top.get("score", 0) or 0
    second_score = second.get("score", 0) or 0
    gap          = top_score - second_score

    clustered = (
        gap <= CLUSTER_SPREAD
        and top_score    >= CLUSTER_MIN_SCORE
        and second_score >= CLUSTER_MIN_SCORE
    )

    if clustered:
        desc = (
            f"{top.get('horse', '?')} ({top_score:.1f}) vs "
            f"{second.get('horse', '?')} ({second_score:.1f}) — "
            f"gap {gap:.1f} pts (threshold {CLUSTER_SPREAD})"
        )
    else:
        desc = (
            f"Top: {top.get('horse', '?')} ({top_score:.1f}), "
            f"2nd: {second.get('horse', '?')} ({second_score:.1f}) — "
            f"gap {gap:.1f} pts — no cluster"
        )

    return clustered, desc


# ---------------------------------------------------------------------------
# Field-level secondary cluster check
# ---------------------------------------------------------------------------

def _check_field_cluster(nap: dict, all_runners: list[dict]) -> tuple[bool, str]:
    """
    Check whether the NAP horse's score is within FIELD_CLUSTER_PCT % of the
    next-highest scorer across all races.

    all_runners: flat list of all scored runners from the candidates document.
    Returns (is_field_clustered, description).
    """
    nap_id    = nap.get("horse_id", "")
    nap_score = nap.get("score", 0) or 0

    others = [
        r for r in all_runners
        if r.get("horse_id") != nap_id and (r.get("score") or 0) > 0
    ]
    if not others:
        return False, "No other scored runners to compare"

    others.sort(key=lambda r: r.get("score", 0), reverse=True)
    next_best       = others[0]
    next_best_score = next_best.get("score", 0) or 0

    threshold = nap_score * (FIELD_CLUSTER_PCT / 100.0)
    gap = nap_score - next_best_score

    is_clustered = gap <= threshold

    desc = (
        f"NAP {nap.get('horse', '?')} ({nap_score:.1f}) vs "
        f"next-best {next_best.get('horse', '?')} ({next_best_score:.1f}) — "
        f"gap {gap:.1f} pts (threshold {threshold:.1f} = {FIELD_CLUSTER_PCT}% of NAP score)"
    )

    return is_clustered, desc


# ---------------------------------------------------------------------------
# Report formatter
# ---------------------------------------------------------------------------

def _format_report(
    date_str: str,
    generated_hm: str,
    race_analysis: list[dict],
    field_cluster: bool,
    field_cluster_desc: str,
    confirmed_clusters: list[str],
    nap: dict | None,
) -> str:
    sep  = "═" * 56
    sep2 = "─" * 56
    lines: list[str] = [
        sep,
        "  CLUSTER REVIEW REPORT",
        f"  Date: {date_str}",
        f"  Generated: {generated_hm}",
        sep,
        "",
    ]

    lines.append(f"Races analysed:    {len(race_analysis)}")
    lines.append(f"Clustered races:   {len(confirmed_clusters)}")
    lines.append("")

    lines.append("■ PER-RACE ANALYSIS")
    lines.append(sep2)
    for entry in race_analysis:
        flag = " [CLUSTER]" if entry["clustered"] else ""
        lines.append(f"  Race: {entry['race_id']}{flag}")
        lines.append(f"    {entry['description']}")
    lines.append("")

    lines.append("■ FIELD-LEVEL (CROSS-RACE) CLUSTER CHECK")
    lines.append(sep2)
    flag = " [WARNING]" if field_cluster else " [OK]"
    lines.append(f"  {field_cluster_desc}{flag}")
    lines.append("")

    if confirmed_clusters:
        lines.append("■ CONFIRMED CLUSTER RACES")
        for r in confirmed_clusters:
            lines.append(f"  - {r}")
    else:
        lines.append("■ NO CLUSTERED RACES")
    lines.append("")

    lines.append("■ NAP SUMMARY")
    if nap:
        lines.append(f"  NAP: {nap.get('horse', 'N/A')} "
                     f"({nap.get('course', '')} {nap.get('off_time', '')})")
        lines.append(f"  Score: {nap.get('score', 0):.1f}  Grade: {nap.get('grade', '?')}")
        if field_cluster:
            lines.append("  ⚠ Field-cluster WARNING — NAP margin over next-best is narrow.")
        else:
            lines.append("  Cluster checks passed.")
    else:
        lines.append("  No NAP selected today.")
    lines.append("")
    lines.append(sep)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Run cluster review. Returns exit code."""
    log("cluster_review.py started")

    date_str = today_str()
    now      = datetime.now(timezone.utc)
    generated_hm = now.strftime("%H:%M")

    # ------------------------------------------------------------------
    # Load nap_candidates document
    # ------------------------------------------------------------------
    candidates_path = data_path(f"nap_candidates_{date_str}.json")
    candidates      = safe_load_json(candidates_path)

    if candidates is None:
        log("cluster_review: nap_candidates file not found — cannot proceed", "ERROR")
        # Write a minimal error report so the pipeline doesn't produce silence
        try:
            with open(
                report_path(f"cluster_review_{date_str}.txt"), "w", encoding="utf-8"
            ) as fh:
                fh.write(
                    f"CLUSTER REVIEW — ERROR\n"
                    f"Date: {date_str}\n"
                    f"nap_candidates file not found. Run nap_selector_v3.py first.\n"
                )
        except OSError as exc:
            log(f"cluster_review: could not write error report — {exc}", "ERROR")
        return 1

    # ------------------------------------------------------------------
    # Reconstruct race groups from the candidates document
    # ------------------------------------------------------------------
    # nap_candidates stores individual horse dicts (nap, best_of_card,
    # watchlist, shadow). We need to group by race_id.  We also need
    # to read ALL runners — nap_selector already ran scoring, but the
    # JSON only stores selected representatives.  We reconstruct what
    # we can from the stored data.
    #
    # Better approach: re-derive from nap_candidates["cluster_races"] list
    # (already computed by nap_selector_v3) and augment with our own
    # independent verification pass.
    # ------------------------------------------------------------------

    # Collect all horse entries from the document
    all_entries: list[dict] = []

    nap_entry = candidates.get("nap")
    if nap_entry:
        all_entries.append(nap_entry)

    best_entry = candidates.get("best_of_card")
    if best_entry:
        all_entries.append(best_entry)

    for h in (candidates.get("watchlist") or []):
        all_entries.append(h)
    for h in (candidates.get("shadow") or []):
        all_entries.append(h)

    # Group by race_id
    race_groups: dict[str, list[dict]] = {}
    for entry in all_entries:
        rid = str(entry.get("race_id") or "")
        race_groups.setdefault(rid, []).append(entry)

    # Sort each group by score descending
    for rid in race_groups:
        race_groups[rid].sort(key=lambda r: r.get("score", 0), reverse=True)

    # ------------------------------------------------------------------
    # Per-race cluster analysis
    # ------------------------------------------------------------------
    race_analysis: list[dict] = []
    confirmed_clusters: list[str] = []

    # Start from the set already flagged by nap_selector_v3
    pre_flagged: list[str] = candidates.get("cluster_races") or []

    all_race_ids = set(list(race_groups.keys()) + pre_flagged)

    for race_id in sorted(all_race_ids):
        runners = race_groups.get(race_id, [])
        is_clustered, desc = _detect_race_cluster(runners)

        # Accept cluster if either our check OR nap_selector found it
        if is_clustered or race_id in pre_flagged:
            confirmed_clusters.append(race_id)
            if race_id in pre_flagged and not is_clustered:
                desc = (
                    f"Pre-flagged by nap_selector_v3 "
                    f"(insufficient runner data stored to re-verify independently)"
                )
                is_clustered = True

        race_analysis.append({
            "race_id":     race_id,
            "clustered":   is_clustered,
            "description": desc,
        })

    log(f"cluster_review: {len(confirmed_clusters)} clustered races "
        f"out of {len(all_race_ids)} analysed")

    # ------------------------------------------------------------------
    # Secondary field-level cluster check
    # ------------------------------------------------------------------
    nap = candidates.get("nap")
    field_cluster      = False
    field_cluster_desc = "No NAP to compare against."

    if nap:
        field_cluster, field_cluster_desc = _check_field_cluster(nap, all_entries)
        if field_cluster:
            log(
                f"cluster_review: field-level cluster WARNING — {field_cluster_desc}",
                "WARNING",
            )

    # ------------------------------------------------------------------
    # Update nap_candidates document with confirmed clusters
    # ------------------------------------------------------------------
    candidates["cluster_races"] = confirmed_clusters
    if field_cluster and nap:
        existing_warnings = list(nap.get("warnings") or [])
        if "field_cluster_warning" not in existing_warnings:
            existing_warnings.append("field_cluster_warning")
        candidates["nap"]["warnings"] = existing_warnings

    if not safe_write_json(candidates_path, candidates):
        log("cluster_review: failed to update nap_candidates JSON", "ERROR")
        return 1
    log(f"cluster_review: updated nap_candidates JSON at {candidates_path}")

    # ------------------------------------------------------------------
    # Write text report
    # ------------------------------------------------------------------
    report_text = _format_report(
        date_str,
        generated_hm,
        race_analysis,
        field_cluster,
        field_cluster_desc,
        confirmed_clusters,
        nap,
    )
    report_dest = report_path(f"cluster_review_{date_str}.txt")
    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
        log(f"cluster_review: report saved → {report_dest}")
    except OSError as exc:
        log(f"cluster_review: failed to write report — {exc}", "ERROR")
        return 1

    # ------------------------------------------------------------------
    # Print summary
    # ------------------------------------------------------------------
    if confirmed_clusters:
        print(
            f"cluster_review: {len(confirmed_clusters)} cluster race(s) confirmed: "
            + ", ".join(confirmed_clusters)
        )
    else:
        print("cluster_review: no cluster races — NAP field is clean")

    if field_cluster:
        print("cluster_review: WARNING — field-level cluster detected")

    return 0


if __name__ == "__main__":
    sys.exit(main())
