"""
qa_regression_check.py — Compare today's output against a baseline to detect
unexpected changes.

If a baseline snapshot exists in archive/system_snapshots/baseline_*.json,
compare:
  1. Number of races in today's racecard vs baseline
  2. Candidate count in nap_candidates vs baseline
  3. NAP grade in candidates vs baseline

Flag any significant differences (>50% change in counts).

If no baseline exists, create one from today's data and report "Baseline created".

Outputs:
    reports/qa_regression_YYYY-MM-DD.txt

Usage:
    python qa_regression_check.py              # uses today's date
    python qa_regression_check.py 2026-06-06   # override date

Exit codes:
    0 — pass (or baseline created)
    1 — regression detected
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.helpers import data_path, log, report_path, safe_load_json, today_str


# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

_PROJECT_DIR = Path(__file__).parent
_SNAPSHOTS_DIR = _PROJECT_DIR / "archive" / "system_snapshots"

# Threshold: flag if a count changes by more than this fraction
REGRESSION_THRESHOLD = 0.50  # 50%


# ---------------------------------------------------------------------------
# Data extraction helpers
# ---------------------------------------------------------------------------

def _extract_racecard_stats(racecard_doc) -> dict:
    """Extract key metrics from a racecard document."""
    if racecard_doc is None:
        return {"race_count": 0, "total_runners": 0}

    if isinstance(racecard_doc, list):
        races = racecard_doc
    elif isinstance(racecard_doc, dict):
        races = racecard_doc.get("races") or racecard_doc.get("results") or []
    else:
        races = []

    total_runners = sum(len(r.get("runners") or []) for r in races)
    return {
        "race_count": len(races),
        "total_runners": total_runners,
    }


def _extract_candidate_stats(candidates_doc) -> dict:
    """Extract key metrics from a nap_candidates document."""
    if candidates_doc is None:
        return {
            "total_candidates": 0,
            "nap_grade": None,
            "nap_score": None,
            "watchlist_count": 0,
            "shadow_count": 0,
        }

    nap = candidates_doc.get("nap") or {}
    watchlist = candidates_doc.get("watchlist") or []
    shadow = candidates_doc.get("shadow") or []

    # Count all candidate types
    count = 0
    for key in ("nap", "value_ew", "best_of_card"):
        if candidates_doc.get(key):
            count += 1
    count += len(watchlist) + len(shadow)

    return {
        "total_candidates": count,
        "nap_grade": nap.get("grade") if isinstance(nap, dict) else None,
        "nap_score": nap.get("score") if isinstance(nap, dict) else None,
        "watchlist_count": len(watchlist),
        "shadow_count": len(shadow),
    }


# ---------------------------------------------------------------------------
# Baseline management
# ---------------------------------------------------------------------------

def _find_latest_baseline() -> Optional[Path]:
    """Return the most recent baseline_*.json file, or None."""
    _SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    candidates = sorted(_SNAPSHOTS_DIR.glob("baseline_*.json"), reverse=True)
    return candidates[0] if candidates else None


def _save_baseline(date_str: str, snapshot: dict) -> Path:
    """Save a new baseline snapshot and return its path."""
    _SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    baseline_path = _SNAPSHOTS_DIR / f"baseline_{ts}.json"
    with open(baseline_path, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, indent=2, ensure_ascii=False)
    return baseline_path


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def _pct_change(baseline_val, current_val) -> Optional[float]:
    """Return percentage change from baseline to current, or None if
    baseline is zero/None."""
    if baseline_val is None or current_val is None:
        return None
    try:
        b = float(baseline_val)
        c = float(current_val)
        if b == 0:
            return None
        return (c - b) / b
    except (TypeError, ValueError):
        return None


def _compare(
    baseline: dict,
    current: dict,
    report_lines: list[str],
) -> int:
    """Compare baseline vs current snapshot. Appends report lines.
    Returns number of regressions found.
    """
    regressions = 0

    def _check(label: str, baseline_key: str, current_key: str) -> None:
        nonlocal regressions
        b_val = baseline.get(baseline_key)
        c_val = current.get(current_key)
        pct = _pct_change(b_val, c_val)

        if pct is None:
            report_lines.append(
                f"  {label}: baseline={b_val!r} current={c_val!r} — SKIP (no numeric baseline)"
            )
            return

        pct_str = f"{pct:+.1%}"
        if abs(pct) > REGRESSION_THRESHOLD:
            regressions += 1
            report_lines.append(
                f"  {label}: baseline={b_val} current={c_val} "
                f"change={pct_str} — REGRESSION (>{REGRESSION_THRESHOLD:.0%} change)"
            )
        else:
            report_lines.append(
                f"  {label}: baseline={b_val} current={c_val} change={pct_str} — OK"
            )

    _check("Race count",        "racecard.race_count",      "racecard.race_count")
    _check("Total runners",     "racecard.total_runners",   "racecard.total_runners")
    _check("Total candidates",  "candidates.total_candidates", "candidates.total_candidates")
    _check("Watchlist count",   "candidates.watchlist_count",  "candidates.watchlist_count")

    # Grade comparison (non-numeric — just flag if changed)
    b_grade = baseline.get("candidates.nap_grade")
    c_grade = current.get("candidates.nap_grade")
    if b_grade != c_grade:
        report_lines.append(
            f"  NAP grade: baseline={b_grade!r} current={c_grade!r} — CHANGED (informational)"
        )
    else:
        report_lines.append(
            f"  NAP grade: {c_grade!r} — UNCHANGED"
        )

    return regressions


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    log("qa_regression_check.py started")
    start_ts = time.time()

    date_str = sys.argv[1] if len(sys.argv) > 1 else today_str()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log(f"qa_regression_check: date={date_str}")

    # ------------------------------------------------------------------
    # 1. Load today's data
    # ------------------------------------------------------------------
    racecard = safe_load_json(data_path(f"racecards_{date_str}.json"))
    candidates = safe_load_json(data_path(f"nap_candidates_{date_str}.json"))

    racecard_stats = _extract_racecard_stats(racecard)
    candidate_stats = _extract_candidate_stats(candidates)

    current_snapshot: dict = {
        "date": date_str,
        "captured_at": now_str,
        # Flatten with dot-notation keys for easy comparison
        "racecard.race_count":        racecard_stats["race_count"],
        "racecard.total_runners":     racecard_stats["total_runners"],
        "candidates.total_candidates": candidate_stats["total_candidates"],
        "candidates.nap_grade":       candidate_stats["nap_grade"],
        "candidates.nap_score":       candidate_stats["nap_score"],
        "candidates.watchlist_count": candidate_stats["watchlist_count"],
        "candidates.shadow_count":    candidate_stats["shadow_count"],
        # Nested originals for human readability
        "racecard_stats":   racecard_stats,
        "candidate_stats":  candidate_stats,
    }

    # ------------------------------------------------------------------
    # 2. Find baseline
    # ------------------------------------------------------------------
    baseline_path = _find_latest_baseline()
    report_lines: list[str] = [
        "QA REGRESSION CHECK",
        f"Date: {date_str} | Run: {now_str}",
        "",
    ]

    exit_code = 0

    if baseline_path is None:
        # No baseline — create one
        saved_path = _save_baseline(date_str, current_snapshot)
        log(f"qa_regression_check: no baseline found — created at {saved_path}")
        report_lines += [
            "STATUS: Baseline created (no prior baseline found)",
            f"Baseline saved to: {saved_path.name}",
            "",
            "TODAY'S SNAPSHOT:",
            f"  Races:           {racecard_stats['race_count']}",
            f"  Total runners:   {racecard_stats['total_runners']}",
            f"  Candidates:      {candidate_stats['total_candidates']}",
            f"  NAP grade:       {candidate_stats['nap_grade'] or 'N/A'}",
            f"  Watchlist count: {candidate_stats['watchlist_count']}",
            f"  Shadow count:    {candidate_stats['shadow_count']}",
            "",
            "RESULT: Baseline created — no regression check performed",
        ]
        exit_code = 0
    else:
        # Load baseline and compare
        baseline = safe_load_json(str(baseline_path))
        if baseline is None:
            report_lines += [
                f"ERROR: Could not load baseline from {baseline_path.name}",
                "RESULT: SKIP — baseline unreadable",
            ]
            exit_code = 0  # Don't fail the pipeline on unreadable baseline
        else:
            report_lines += [
                f"BASELINE: {baseline_path.name} (from {baseline.get('date', 'unknown')})",
                "",
                "COMPARISON:",
            ]

            regressions = _compare(baseline, current_snapshot, report_lines)

            report_lines += [
                "",
                f"Regressions found: {regressions}",
                f"Threshold: >{REGRESSION_THRESHOLD:.0%} change flags as regression",
                "",
            ]

            if regressions == 0:
                report_lines.append("RESULT: PASS — no significant regressions detected")
                exit_code = 0
            else:
                report_lines.append(
                    f"RESULT: FAIL — {regressions} regression(s) detected. "
                    "Investigate before continuing."
                )
                exit_code = 1

    # ------------------------------------------------------------------
    # 3. Write report
    # ------------------------------------------------------------------
    duration = round(time.time() - start_ts, 2)
    report_lines.append(f"\nDuration: {duration}s")

    report_text = "\n".join(report_lines)
    report_dest = report_path(f"qa_regression_{date_str}.txt")

    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
        log(f"qa_regression_check: report saved to {report_dest}")
    except OSError as exc:
        log(f"qa_regression_check: failed to write report — {exc}", "WARNING")

    print(report_text)
    log(f"qa_regression_check.py finished in {duration}s — exit_code={exit_code}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
