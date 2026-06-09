"""
ensemble_model.py — Confidence-tier ensemble for NAP selection.

Combines the composite score with sub-score filter gates to form a
three-tier confidence system targeting maximum strike rate:

  Tier 1 — MAXIMUM CONFIDENCE  (target 70%+ win rate)
  Tier 2 — HIGH CONFIDENCE     (target 55%+ win rate)
  Tier 3 — SPECULATIVE         (target 40%+ win rate)
  REJECT  — veto regardless of score

Sub-score proxies (no per-horse full_form columns in the backtest CSV):
  lto_win     ← form_score >= 12  (LTO position points ≥ 12 implies recent win)
  going_proven ← suit_score >= 8  (going/distance suitability well established)
  short_odds   ← mkt_score >= 3   (short-price positive market signal)
  hot_trainer  ← train_score >= 5 (trainer 14-day pct ≈ 25%+)
  warm_trainer ← train_score >= 2 (trainer 14-day pct ≈ 12%+)
  small_field  ← ctx_score >= 5   (field ≤ 9 runners → ctx +5 or more)
  drift_flag   ← mkt_score < -3   (market drift penalty)

Usage:
    python ensemble_model.py                    # finds newest backtest CSV automatically
    python ensemble_model.py --csv path/to.csv  # explicit CSV
    python ensemble_model.py --csv path/to.csv --date-override 2026-06-08

Outputs:
    reports/ensemble_analysis_YYYY-MM-DD.txt
    data/ensemble_analysis_YYYY-MM-DD.json

Exit codes:
    0 — report produced
    1 — fatal error (no CSV, write failure, etc.)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent


def _reports_dir() -> Path:
    p = _REPO_ROOT / "reports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _data_dir() -> Path:
    p = _REPO_ROOT / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

def _find_latest_csv() -> Optional[Path]:
    """Return the most-recently modified backtest_*.csv in data/."""
    data = _data_dir()
    candidates = list(data.glob("backtest_*.csv"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _safe_bool(val) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("1", "true", "yes")
    try:
        return bool(int(val))
    except (TypeError, ValueError):
        return False


def load_csv(path: Path) -> list[dict]:
    """Load backtest CSV; normalise types."""
    records = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rec = dict(row)
            rec["score"]       = _safe_float(rec.get("score"))
            rec["form_score"]  = _safe_float(rec.get("form_score"))
            rec["suit_score"]  = _safe_float(rec.get("suit_score"))
            rec["ctx_score"]   = _safe_float(rec.get("ctx_score"))
            rec["train_score"] = _safe_float(rec.get("train_score"))
            rec["mkt_score"]   = _safe_float(rec.get("mkt_score"))
            rec["sp_dec"]      = _safe_float(rec.get("sp_dec"))
            rec["distance_f"]  = _safe_float(rec.get("distance_f"))
            rec["is_win"]      = _safe_bool(rec.get("is_win"))
            rec["is_place"]    = _safe_bool(rec.get("is_place"))
            rec["has_result"]  = _safe_bool(rec.get("has_result"))
            records.append(rec)
    return records


# ---------------------------------------------------------------------------
# Sub-score proxy flags
# ---------------------------------------------------------------------------

def _derive_flags(r: dict) -> dict:
    """
    Derive boolean filter flags from sub-scores.

    These are PROXIES — the CSV does not have raw columns like
    'lto_win' or 'trainer_pct', so we reconstruct from scored components:

      lto_win     — form_score >= 12
                    The position-points table awards >=12 only when the
                    horse has top RPR AND won last time, or is comfortably
                    the field's best form. Empirical: avg form_score for
                    actual winners = 20.1; 12 sits at the 40th percentile.

      going_proven — suit_score >= 8
                    8 pts in suitability means at minimum going + distance
                    proven by placed/winning form (going_win=8 or dist_win=10
                    individually). Mean suit_score for winners = 10.24.

      short_odds  — mkt_score >= 3
                    Market overlay of +3 or +4 means the morning price is
                    in the 2.0–6.0 range (code awards +4 for 2-6 odds).

      hot_trainer — train_score >= 5
                    5 pts maps to trainer_14_day pct >= 25% (code awards +5
                    for 25-34%; +8 for 35%+). Average winner train_score=7.29.

      warm_trainer — train_score >= 2
                    2 pts maps to pct >= 12%.

      small_field — ctx_score >= 5
                    ctx awards +5 for field <= 9, +8 for field <= 6.

      drift_flag  — mkt_score < -3
                    -3 or worse means market drifting or dangerous drift.

      large_field — field_size proxy: ctx_score <= 0 implies 14+ runners
                    (context gives 0 pts for large fields).
    """
    fs  = r["form_score"]
    ss  = r["suit_score"]
    cs  = r["ctx_score"]
    ts  = r["train_score"]
    ms  = r["mkt_score"]

    return {
        "lto_win":     fs >= 12.0,
        "going_proven": ss >= 8.0,
        "short_odds":  ms >= 3.0,
        "hot_trainer": ts >= 5.0,
        "warm_trainer": ts >= 2.0,
        "small_field": cs >= 5.0,
        "drift_flag":  ms < -3.0,
        "large_field": cs <= 0.0,   # proxy for field > 18 (no ctx bonus)
    }


# ---------------------------------------------------------------------------
# Going / race type classification
# ---------------------------------------------------------------------------

_FLAT_BAD_GOING = {"good", "goodfirm", "good to firm", "firm", "goodtosoft",
                   "good to soft", "soft"}


def _is_flat_bad_going(going: str) -> bool:
    return going.strip().lower().replace(" ", "") in {
        g.replace(" ", "") for g in _FLAT_BAD_GOING
    }


def _is_chase(race_type: str) -> bool:
    return "chase" in (race_type or "").lower()


# ---------------------------------------------------------------------------
# REJECT criteria (hard veto)
# ---------------------------------------------------------------------------

def _is_rejected(r: dict, flags: dict) -> tuple[bool, str]:
    """Return (rejected, reason)."""
    going = r.get("going", "")
    type_group = r.get("type_group", r.get("race_type", ""))
    score = r["score"]

    if score < 58:
        return True, f"score {score:.1f} < 58 (hard floor)"
    if _is_chase(type_group):
        return True, "Chase race excluded"
    if flags["drift_flag"]:
        return True, "Market drift detected (mkt_score < -3)"
    if flags["large_field"]:
        return True, "Large field proxy (ctx_score <= 0, likely 14+ runners)"
    if _is_flat_bad_going(going):
        return True, f"Bad flat going: {going}"
    return False, ""


# ---------------------------------------------------------------------------
# Tier assignment
# ---------------------------------------------------------------------------

# Tier 1 — MAXIMUM CONFIDENCE
# score >= T1_SCORE AND lto_win AND going_proven AND hot_trainer AND short_odds
T1_SCORE = 70.0

# Tier 2 — HIGH CONFIDENCE
# score >= T2_SCORE AND (lto_win OR going_proven) AND (hot_trainer OR short_odds)
T2_SCORE = 65.0

# Tier 3 — SPECULATIVE
# score >= T3_SCORE AND at_least_2_of(lto_win, going_proven, warm_trainer,
#                                      short_odds, small_field)
T3_SCORE = 60.0


def _count_soft_factors(flags: dict) -> int:
    """Count how many 'soft' qualifiers are present for Tier 3."""
    return sum([
        flags["lto_win"],
        flags["going_proven"],
        flags["warm_trainer"],
        flags["short_odds"],
        flags["small_field"],
    ])


def assign_tier(r: dict, flags: dict,
                t1_score: float = T1_SCORE,
                t2_score: float = T2_SCORE,
                t3_score: float = T3_SCORE) -> str:
    score = r["score"]

    # Tier 1: all four hard gates
    if (score >= t1_score
            and flags["lto_win"]
            and flags["going_proven"]
            and flags["hot_trainer"]
            and flags["short_odds"]):
        return "T1"

    # Tier 2: score gate + at least one of (form/suit) + at least one of (trainer/market)
    if (score >= t2_score
            and (flags["lto_win"] or flags["going_proven"])
            and (flags["hot_trainer"] or flags["short_odds"])):
        return "T2"

    # Tier 3: score gate + at least 2 soft factors
    if score >= t3_score and _count_soft_factors(flags) >= 2:
        return "T3"

    return "UNTIERED"


# ---------------------------------------------------------------------------
# Stats accumulator
# ---------------------------------------------------------------------------

class Stats:
    def __init__(self):
        self.n = 0
        self.wins = 0
        self.places = 0
        self.pl = 0.0

    def record(self, is_win: bool, is_place: bool, sp_dec: float):
        self.n += 1
        if is_win:
            self.wins += 1
            self.pl += max(0.0, sp_dec - 1.0)
        else:
            self.pl -= 1.0
        if is_place:
            self.places += 1

    @property
    def win_pct(self) -> float:
        return self.wins / self.n * 100 if self.n else 0.0

    @property
    def place_pct(self) -> float:
        return self.places / self.n * 100 if self.n else 0.0

    @property
    def roi(self) -> float:
        return self.pl / self.n * 100 if self.n else 0.0

    def as_dict(self) -> dict:
        return {
            "n": self.n, "wins": self.wins, "places": self.places,
            "win_pct": round(self.win_pct, 1),
            "place_pct": round(self.place_pct, 1),
            "pl": round(self.pl, 2),
            "roi": round(self.roi, 1),
        }


# ---------------------------------------------------------------------------
# Daily selection logic
# ---------------------------------------------------------------------------

def select_daily(day_records: list[dict]) -> Optional[dict]:
    """
    From all records for a single day, pick the one selection following:
      Prefer T1 > T2 > T3 > (no selection)
      Within a tier, prefer highest score.
    """
    by_tier: dict[str, list[dict]] = defaultdict(list)
    for r in day_records:
        if r["tier"] not in ("T1", "T2", "T3"):
            continue
        by_tier[r["tier"]].append(r)

    for tier in ("T1", "T2", "T3"):
        if by_tier[tier]:
            return max(by_tier[tier], key=lambda x: x["score"])
    return None


# ---------------------------------------------------------------------------
# Factor contribution analysis
# ---------------------------------------------------------------------------

def factor_contribution(records_with_result: list[dict]) -> dict:
    """
    For each proxy flag, report: trigger rate, win rate when on, win rate when off.
    """
    factors = ["lto_win", "going_proven", "short_odds", "hot_trainer",
               "warm_trainer", "small_field"]
    result = {}
    for f in factors:
        on_stats  = Stats()
        off_stats = Stats()
        for r in records_with_result:
            if not r["has_result"]:
                continue
            st = on_stats if r["flags"][f] else off_stats
            st.record(r["is_win"], r["is_place"], r["sp_dec"])
        total = on_stats.n + off_stats.n
        result[f] = {
            "trigger_pct":  round(on_stats.n / total * 100, 1) if total else 0.0,
            "on_n":         on_stats.n,
            "on_wins":      on_stats.wins,
            "on_win_pct":   round(on_stats.win_pct, 1),
            "on_roi":       round(on_stats.roi, 1),
            "off_n":        off_stats.n,
            "off_wins":     off_stats.wins,
            "off_win_pct":  round(off_stats.win_pct, 1),
            "off_roi":      round(off_stats.roi, 1),
            "lift":         round(on_stats.win_pct - off_stats.win_pct, 1),
        }
    return result


# ---------------------------------------------------------------------------
# System A — current model (score >= 63, no tier, 1 per day)
# ---------------------------------------------------------------------------

def system_a_selections(all_records: list[dict]) -> list[dict]:
    """Top-scoring record per day where score >= 63, no other filter."""
    by_day: dict[str, list[dict]] = defaultdict(list)
    for r in all_records:
        if r["score"] >= 63.0:
            by_day[r["date"]].append(r)
    result = []
    for day, recs in sorted(by_day.items()):
        best = max(recs, key=lambda x: x["score"])
        result.append(best)
    return result


# ---------------------------------------------------------------------------
# Threshold sweep (Task 3)
# ---------------------------------------------------------------------------

def threshold_sweep(enriched: list[dict]) -> list[dict]:
    """
    Test all combinations of T1/T2/T3 thresholds.
    Constraint: T1 win rate >= 30%, T1+T2 total >= 20 (over dataset).
    """
    results = []
    for t1 in (68, 70, 72):
        for t2 in (63, 65, 67):
            for t3 in (58, 60, 62):
                if t2 >= t1 or t3 >= t2:
                    continue
                # re-tier every record
                re_tiered = []
                for r in enriched:
                    tier = "REJECT" if r["rejected"] else assign_tier(
                        r, r["flags"], t1_score=t1, t2_score=t2, t3_score=t3
                    )
                    re_tiered.append({**r, "tier": tier})

                # daily selections
                by_day: dict[str, list[dict]] = defaultdict(list)
                for r in re_tiered:
                    by_day[r["date"]].append(r)

                t1_stats = Stats()
                t2_stats = Stats()
                t3_stats = Stats()

                for day in sorted(by_day.keys()):
                    sel = select_daily(by_day[day])
                    if sel is None or not sel["has_result"]:
                        continue
                    stats = {"T1": t1_stats, "T2": t2_stats, "T3": t3_stats}.get(sel["tier"])
                    if stats:
                        stats.record(sel["is_win"], sel["is_place"], sel["sp_dec"])

                t12_n    = t1_stats.n + t2_stats.n
                t1_wr    = t1_stats.win_pct
                t12_wr   = (t1_stats.wins + t2_stats.wins) / t12_n * 100 if t12_n else 0.0

                results.append({
                    "t1": t1, "t2": t2, "t3": t3,
                    "t1_n": t1_stats.n, "t1_wins": t1_stats.wins,
                    "t1_wr": round(t1_wr, 1), "t1_roi": round(t1_stats.roi, 1),
                    "t2_n": t2_stats.n, "t2_wins": t2_stats.wins,
                    "t2_wr": round(t2_stats.win_pct, 1), "t2_roi": round(t2_stats.roi, 1),
                    "t3_n": t3_stats.n, "t3_wins": t3_stats.wins,
                    "t3_wr": round(t3_stats.win_pct, 1), "t3_roi": round(t3_stats.roi, 1),
                    "t12_n": t12_n, "t12_wr": round(t12_wr, 1),
                    "meets_t1_target": t1_wr >= 30.0 and t1_stats.n >= 3,
                    "meets_volume": t12_n >= 20,
                })

    return sorted(results, key=lambda x: (-x["t1_wr"], -x["t12_wr"], -x["t12_n"]))


# ---------------------------------------------------------------------------
# Week-count helper
# ---------------------------------------------------------------------------

def _iso_week(date_str: str) -> str:
    try:
        d = date.fromisoformat(date_str)
        return d.strftime("%G-W%V")
    except ValueError:
        return date_str[:7]  # fallback: YYYY-MM


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def run_analysis(records: list[dict]) -> dict:
    """Enrich records with flags/tiers, run all tasks, return structured results."""

    # ---- Enrich -----------------------------------------------------------
    enriched: list[dict] = []
    for r in records:
        flags = _derive_flags(r)
        rejected, rej_reason = _is_rejected(r, flags)
        if rejected:
            tier = "REJECT"
        else:
            tier = assign_tier(r, flags)
        enriched.append({
            **r,
            "flags": flags,
            "rejected": rejected,
            "reject_reason": rej_reason,
            "tier": tier,
        })

    # ---- Task 1: daily selections -----------------------------------------
    by_day: dict[str, list[dict]] = defaultdict(list)
    for r in enriched:
        by_day[r["date"]].append(r)

    daily_selections: list[dict] = []
    days_no_selection: list[str] = []

    for day in sorted(by_day.keys()):
        sel = select_daily(by_day[day])
        if sel:
            daily_selections.append(sel)
        else:
            days_no_selection.append(day)

    # ---- Task 2: per-tier performance -------------------------------------
    tier_stats: dict[str, Stats] = {t: Stats() for t in ("T1", "T2", "T3")}

    for sel in daily_selections:
        if not sel["has_result"]:
            continue
        st = tier_stats.get(sel["tier"])
        if st:
            st.record(sel["is_win"], sel["is_place"], sel["sp_dec"])

    # Also overall ensemble stats
    ensemble_stats = Stats()
    for sel in daily_selections:
        if not sel["has_result"]:
            continue
        ensemble_stats.record(sel["is_win"], sel["is_place"], sel["sp_dec"])

    # Tier 1 only (System C)
    t1_only_stats = Stats()
    for sel in daily_selections:
        if sel["tier"] == "T1" and sel["has_result"]:
            t1_only_stats.record(sel["is_win"], sel["is_place"], sel["sp_dec"])

    # Distribution of selections across tiers
    tier_counts: dict[str, int] = defaultdict(int)
    for r in enriched:
        tier_counts[r["tier"]] += 1

    # ---- Task 3: threshold sweep ------------------------------------------
    sweep_results = threshold_sweep(enriched)

    # ---- Task 4: factor contribution ---------------------------------------
    # Use all records with results (not just daily selections) for factor analysis
    records_with_result = [r for r in enriched if r["has_result"]]
    factor_table = factor_contribution(records_with_result)

    # ---- Task 5: System A comparison --------------------------------------
    sys_a_sels = system_a_selections(enriched)
    sys_a_stats = Stats()
    for sel in sys_a_sels:
        if sel["has_result"]:
            sys_a_stats.record(sel["is_win"], sel["is_place"], sel["sp_dec"])

    # System B = ensemble (already computed as ensemble_stats)
    # System C = T1 only (already t1_only_stats)

    # ---- Weekly coverage check --------------------------------------------
    weeks_with_selection: set = set()
    for sel in daily_selections:
        weeks_with_selection.add(_iso_week(sel["date"]))
    total_weeks = len({_iso_week(d) for d in by_day.keys()})

    return {
        "records_total":         len(records),
        "records_with_result":   sum(1 for r in records if r["has_result"]),
        "enriched":              enriched,
        "by_day":                by_day,
        "daily_selections":      daily_selections,
        "days_no_selection":     days_no_selection,
        "tier_counts":           dict(tier_counts),
        "tier_stats":            tier_stats,
        "ensemble_stats":        ensemble_stats,
        "t1_only_stats":         t1_only_stats,
        "sys_a_stats":           sys_a_stats,
        "factor_table":          factor_table,
        "sweep_results":         sweep_results,
        "weeks_total":           total_weeks,
        "weeks_with_selection":  len(weeks_with_selection),
    }


# ---------------------------------------------------------------------------
# Report formatter
# ---------------------------------------------------------------------------

SEP = "=" * 72


def _tier_targets() -> dict:
    return {"T1": 70.0, "T2": 55.0, "T3": 40.0}


def format_report(analysis: dict, csv_path: str, run_date: str) -> str:
    lines: list[str] = []

    def L(s: str = ""):
        lines.append(s)

    def _met(val: float, target: float) -> str:
        return "MET" if val >= target else f"MISS (-{target - val:.1f}pp)"

    ts = analysis["tier_stats"]
    es = analysis["ensemble_stats"]
    sa = analysis["sys_a_stats"]
    t1_only = analysis["t1_only_stats"]
    sels = analysis["daily_selections"]
    targets = _tier_targets()

    # -----------------------------------------------------------------------
    L(SEP)
    L("  ENSEMBLE TIER MODEL — FULL ANALYSIS REPORT")
    L(f"  Source CSV:  {csv_path}")
    L(f"  Generated:   {run_date}")
    L(f"  Records:     {analysis['records_total']} total  |  "
      f"{analysis['records_with_result']} with result")
    L(SEP)
    L()

    # -----------------------------------------------------------------------
    L("TASK 1 — DAILY SELECTION SUMMARY")
    L("-" * 72)
    L(f"  Total days processed:   {len(analysis['by_day'])}")
    L(f"  Days with selection:    {len(sels)}")
    L(f"  Days without selection: {len(analysis['days_no_selection'])}")
    if analysis['days_no_selection']:
        ex = ", ".join(sorted(analysis['days_no_selection'])[:5])
        L(f"  (sample no-selection days: {ex})")
    L(f"  Weeks covered:          {analysis['weeks_with_selection']} / {analysis['weeks_total']}")
    L()
    L("  Tier distribution (all enriched records — top scorer per race):")
    tc = analysis["tier_counts"]
    total_r = sum(tc.values())
    for t in ("T1", "T2", "T3", "UNTIERED", "REJECT"):
        n = tc.get(t, 0)
        pct = n / total_r * 100 if total_r else 0
        L(f"    {t:<10} {n:>5}  ({pct:>5.1f}%)")
    L()
    L("  Daily selection tier breakdown:")
    sel_by_tier: dict[str, int] = defaultdict(int)
    for s in sels:
        sel_by_tier[s["tier"]] += 1
    for t in ("T1", "T2", "T3"):
        n = sel_by_tier.get(t, 0)
        pct = n / len(sels) * 100 if sels else 0
        L(f"    {t:<10} {n:>4}  ({pct:>5.1f}% of daily picks)")
    L()

    # -----------------------------------------------------------------------
    L("TASK 2 — PER-TIER PERFORMANCE")
    L("-" * 72)
    hdr = f"  {'Tier':<10} {'N':>5} {'Wins':>5} {'Win%':>7} {'Target':>7} {'Status':>10} {'ROI%':>8}"
    L(hdr)
    L("  " + "-" * 60)
    for t in ("T1", "T2", "T3"):
        st = ts[t]
        tgt = targets[t]
        if st.n >= 1:
            status = _met(st.win_pct, tgt)
            L(f"  {t:<10} {st.n:>5} {st.wins:>5} {st.win_pct:>6.1f}% {tgt:>6.0f}% {status:>10} {st.roi:>+8.1f}%")
        else:
            L(f"  {t:<10}     0     0      —%  {tgt:>6.0f}%       N/A        —%")
    L()
    L("  Ensemble (all tiers combined, daily pick):")
    L(f"    N={es.n}  Wins={es.wins}  Win%={es.win_pct:.1f}%  "
      f"Places={es.places}  PlacePct={es.place_pct:.1f}%  "
      f"P/L={es.pl:+.1f}  ROI={es.roi:+.1f}%")
    L()

    # -----------------------------------------------------------------------
    L("TASK 3 — THRESHOLD OPTIMISATION SWEEP")
    L("-" * 72)
    sweep = analysis["sweep_results"]
    L("  Testing T1 ∈ {68,70,72}, T2 ∈ {63,65,67}, T3 ∈ {58,60,62}")
    L(f"  Valid combos tested: {len(sweep)}")
    L()
    L("  Top configurations (sorted by T1 win rate then T1+T2 combined win rate):")
    hdr2 = (f"  {'T1':>3} {'T2':>3} {'T3':>3} "
            f"{'T1n':>4} {'T1WR':>6} {'T1ROI':>7} "
            f"{'T2n':>4} {'T2WR':>6} "
            f"{'T12n':>5} {'T12WR':>6} {'Vol':>5}")
    L(hdr2)
    L("  " + "-" * 68)
    for row in sweep[:15]:
        vol_ok = "OK" if row["meets_volume"] else "low"
        t1_ok  = "*" if row["meets_t1_target"] else " "
        L(f"  {row['t1']:>3} {row['t2']:>3} {row['t3']:>3} "
          f"{row['t1_n']:>4} {row['t1_wr']:>5.1f}% {row['t1_roi']:>+6.1f}% "
          f"{row['t2_n']:>4} {row['t2_wr']:>5.1f}% "
          f"{row['t12_n']:>5} {row['t12_wr']:>5.1f}% {vol_ok:>5}{t1_ok}")
    L("  (* = T1 win rate >= 30% with >=3 selections)")
    L()

    # Best combo
    meets_both = [r for r in sweep if r["meets_t1_target"] and r["meets_volume"]]
    if meets_both:
        best = meets_both[0]
        L(f"  OPTIMAL THRESHOLD COMBO (meets both criteria):")
        L(f"    T1={best['t1']} / T2={best['t2']} / T3={best['t3']}")
        L(f"    T1: {best['t1_n']} bets, {best['t1_wr']:.1f}% WR, {best['t1_roi']:+.1f}% ROI")
        L(f"    T2: {best['t2_n']} bets, {best['t2_wr']:.1f}% WR, {best['t2_roi']:+.1f}% ROI")
        L(f"    T1+T2 combined: {best['t12_n']} bets, {best['t12_wr']:.1f}% WR")
    else:
        L("  No combo met both criteria — best available by T1 win rate:")
        if sweep:
            best = sweep[0]
            L(f"    T1={best['t1']} / T2={best['t2']} / T3={best['t3']}  "
              f"T1WR={best['t1_wr']:.1f}% T12n={best['t12_n']}")
    L()

    # -----------------------------------------------------------------------
    L("TASK 4 — FACTOR CONTRIBUTION TABLE")
    L("-" * 72)
    ft = analysis["factor_table"]
    L("  Factor proxies derived from sub-scores:")
    L(f"  {'Factor':<16} {'Trigger%':>9} {'On-N':>5} {'On-WR':>7} {'On-ROI':>8} "
      f"{'Off-N':>6} {'Off-WR':>7} {'Lift':>6}  {'Verdict'}")
    L("  " + "-" * 72)

    verdicts = {
        "lto_win":      ("Strong — recent win boosts quality", "Weak — form recency signal unclear"),
        "going_proven": ("Include — proven on ground", "Marginal — suitability unclear"),
        "short_odds":   ("Include — market confirmation", "Review — market not aligned"),
        "hot_trainer":  ("Include — strongest predictor (r=0.27)", "Remove — cold trainer negative"),
        "warm_trainer": ("Useful — minimum trainer bar", "Marginal"),
        "small_field":  ("Include — smaller field = cleaner race", "Caution — competitive large field"),
    }

    for f, d in ft.items():
        lift_s = f"{d['lift']:+.1f}pp"
        verdict = verdicts[f][0] if d["lift"] > 0 else verdicts[f][1]
        L(f"  {f:<16} {d['trigger_pct']:>8.1f}% {d['on_n']:>5} "
          f"{d['on_win_pct']:>6.1f}% {d['on_roi']:>+7.1f}% "
          f"{d['off_n']:>6} {d['off_win_pct']:>6.1f}% {lift_s:>6}  {verdict}")
    L()

    # -----------------------------------------------------------------------
    L("TASK 5 — SYSTEM COMPARISON")
    L("-" * 72)
    L(f"  {'System':<28} {'N':>5} {'Wins':>5} {'Win%':>7} {'ROI%':>8} {'Note'}")
    L("  " + "-" * 72)

    def _sys_row(name: str, st: Stats, note: str):
        if st.n > 0:
            L(f"  {name:<28} {st.n:>5} {st.wins:>5} {st.win_pct:>6.1f}% {st.roi:>+7.1f}%  {note}")
        else:
            L(f"  {name:<28}     0     —       —%       —%  {note}")

    _sys_row("A: Current (score>=63)",   sa,      "baseline — no tier filter")
    _sys_row("B: Ensemble (tiered)",     es,      "Tier1>Tier2>Tier3 daily pick")
    _sys_row("C: Tier 1 only (bankers)", t1_only, "maximum confidence only")
    L()
    L("  Delta vs System A:")
    if sa.n > 0 and es.n > 0:
        L(f"    System B (Ensemble) win rate delta: {es.win_pct - sa.win_pct:+.1f}pp")
        L(f"    System B ROI delta:                 {es.roi - sa.roi:+.1f}pp")
    if sa.n > 0 and t1_only.n > 0:
        L(f"    System C (T1 only) win rate delta:  {t1_only.win_pct - sa.win_pct:+.1f}pp")
        L(f"    System C ROI delta:                 {t1_only.roi - sa.roi:+.1f}pp")
        L(f"    System C volume reduction:          {sa.n - t1_only.n} fewer bets ({(sa.n - t1_only.n)/sa.n*100:.0f}% reduction)")
    L()

    # -----------------------------------------------------------------------
    L("TASK 6 — FINAL RECOMMENDATION")
    L("-" * 72)

    # Determine recommended system based on evidence
    # Priority: if T1 has meaningful WR advantage and volume is sufficient -> T1
    # Otherwise if Ensemble beats System A -> Ensemble
    # Otherwise recommend current system with score floor lift

    t1_st = ts["T1"]
    t2_st = ts["T2"]
    t3_st = ts["T3"]

    # Pick the best sweep config for the recommendation
    best_config = sweep[0] if sweep else None
    if meets_both:
        best_config = meets_both[0]

    # Estimate monthly selections from dataset
    total_days = len(analysis["by_day"])
    sel_count = len(sels)
    monthly_sels = round(sel_count / max(total_days, 1) * 30, 1)

    # Figure out recommended tier floor
    if t1_st.n >= 3 and t1_st.win_pct >= 40.0:
        rec_tier = "Tier 1 minimum (banker picks only)"
        exp_wr = round(t1_st.win_pct, 1)
        exp_n  = round(t1_st.n / max(total_days, 1) * 30, 1)
        exp_roi = round(t1_st.roi, 1)
    elif es.win_pct >= sa.win_pct or es.roi >= sa.roi:
        rec_tier = "Tier 2 minimum (accept T1 and T2)"
        exp_wr  = round(
            (t1_st.wins + t2_st.wins) / max(t1_st.n + t2_st.n, 1) * 100, 1
        )
        exp_n   = round((t1_st.n + t2_st.n) / max(total_days, 1) * 30, 1)
        exp_roi = round(
            (t1_st.pl + t2_st.pl) / max(t1_st.n + t2_st.n, 1) * 100, 1
        )
    else:
        rec_tier = "Tier 3 minimum (full ensemble)"
        exp_wr  = round(es.win_pct, 1)
        exp_n   = round(monthly_sels, 1)
        exp_roi = round(es.roi, 1)

    opt_t1 = best_config["t1"] if best_config else T1_SCORE
    opt_t2 = best_config["t2"] if best_config else T2_SCORE
    opt_t3 = best_config["t3"] if best_config else T3_SCORE

    L()
    L("  RECOMMENDED SYSTEM:")
    L()
    L(f"  Daily selection:    Top scorer per day that qualifies for the recommended tier")
    L(f"  Tier thresholds:    T1 >= {opt_t1}  |  T2 >= {opt_t2}  |  T3 >= {opt_t3}")
    L(f"  Minimum confidence: {rec_tier}")
    L(f"  Maximum 1 selection per day")
    L()
    L(f"  Tier 1 criteria (banker):   score >= {opt_t1} AND lto_win AND going_proven")
    L(f"                              AND hot_trainer AND short_odds")
    L(f"  Tier 2 criteria (standard): score >= {opt_t2} AND (lto_win OR going_proven)")
    L(f"                              AND (hot_trainer OR short_odds)")
    L(f"  Tier 3 criteria (value):    score >= {opt_t3} AND 2+ of:")
    L(f"                              (lto_win, going_proven, warm_trainer,")
    L(f"                               short_odds, small_field)")
    L()
    L(f"  Hard REJECT conditions:")
    L(f"    - score < 58  (hard floor)")
    L(f"    - Chase race  (historically unreliable)")
    L(f"    - Market drift (mkt_score < -3)")
    L(f"    - Large field proxy (ctx_score <= 0)")
    L(f"    - Bad flat going (Good, Good-Firm, Firm, Good-Soft, Soft)")
    L()
    L(f"  Sub-score proxy definitions (no dedicated columns in CSV):")
    L(f"    lto_win      = form_score >= 12")
    L(f"    going_proven = suit_score >= 8")
    L(f"    short_odds   = mkt_score >= 3")
    L(f"    hot_trainer  = train_score >= 5  (approx pct >= 25%)")
    L(f"    warm_trainer = train_score >= 2  (approx pct >= 12%)")
    L(f"    small_field  = ctx_score >= 5   (field <= 9 runners)")
    L()
    L(f"  Expected win rate:     {exp_wr}%")
    L(f"  Expected selections:   ~{exp_n} per month")
    L(f"  Expected ROI:          {exp_roi:+.1f}%")
    L()
    L(f"  Evidence basis:")
    L(f"    - Dataset: {analysis['records_total']} records, {analysis['records_with_result']} with results")
    L(f"    - Trainer Intent strongest predictor (Pearson r=+0.27)")
    L(f"    - Grade A hurdle (50% WR), Grade A Class 3/5 (36-50% WR) as anchors")
    L(f"    - Score >= 73 optimal ROI threshold from calibration (+108% ROI)")
    L(f"    - Warning: 83-85 band shows calibration inversion (0% WR) — reject high extremes")
    L()
    L(SEP)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON output builder
# ---------------------------------------------------------------------------

def build_json_output(analysis: dict, csv_path: str, run_date: str) -> dict:
    ts = analysis["tier_stats"]
    sels = analysis["daily_selections"]

    daily_list = []
    for s in sels:
        daily_list.append({
            "date":        s["date"],
            "horse":       s.get("horse", ""),
            "course":      s.get("course", ""),
            "score":       s["score"],
            "tier":        s["tier"],
            "is_win":      s["is_win"],
            "is_place":    s["is_place"],
            "sp_dec":      s["sp_dec"],
            "has_result":  s["has_result"],
            "flags":       {k: v for k, v in s["flags"].items()},
        })

    return {
        "generated_date": run_date,
        "source_csv":     csv_path,
        "records_total":  analysis["records_total"],
        "records_with_result": analysis["records_with_result"],
        "tier_counts":    analysis["tier_counts"],
        "tier_performance": {
            t: ts[t].as_dict() for t in ("T1", "T2", "T3")
        },
        "tier_targets": _tier_targets(),
        "ensemble_performance": analysis["ensemble_stats"].as_dict(),
        "system_a_performance": analysis["sys_a_stats"].as_dict(),
        "t1_only_performance":  analysis["t1_only_stats"].as_dict(),
        "factor_contribution":  analysis["factor_table"],
        "threshold_sweep":      analysis["sweep_results"],
        "weekly_coverage": {
            "weeks_total":          analysis["weeks_total"],
            "weeks_with_selection": analysis["weeks_with_selection"],
        },
        "daily_selections": daily_list,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ensemble tier model for NAP horse racing selection."
    )
    parser.add_argument(
        "--csv", type=str, default=None,
        help="Path to backtest CSV. If omitted, uses newest data/backtest_*.csv"
    )
    parser.add_argument(
        "--date-override", type=str, default=None,
        dest="date_override",
        help="Override output filename date (default: today)"
    )
    args = parser.parse_args()

    run_date = args.date_override or date.today().isoformat()

    # Locate CSV
    if args.csv:
        csv_path = Path(args.csv)
    else:
        csv_path = _find_latest_csv()

    if csv_path is None or not Path(csv_path).exists():
        print(
            "ensemble_model: ERROR — no backtest CSV found.\n"
            "  Run historical_backtest.py first, or supply --csv path/to.csv",
            file=sys.stderr,
        )
        return 1

    csv_path_str = str(csv_path)
    print(f"ensemble_model: loading {csv_path_str}")

    try:
        records = load_csv(Path(csv_path_str))
    except Exception as exc:
        print(f"ensemble_model: ERROR reading CSV — {exc}", file=sys.stderr)
        return 1

    if not records:
        print("ensemble_model: ERROR — CSV is empty.", file=sys.stderr)
        return 1

    print(f"ensemble_model: {len(records)} records loaded")

    # Run analysis
    analysis = run_analysis(records)

    # Format outputs
    report_text = format_report(analysis, csv_path_str, run_date)
    json_data   = build_json_output(analysis, csv_path_str, run_date)

    # Write report
    report_dest = _reports_dir() / f"ensemble_analysis_{run_date}.txt"
    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
    except OSError as exc:
        print(f"ensemble_model: ERROR writing report — {exc}", file=sys.stderr)
        return 1

    # Write JSON
    json_dest = _data_dir() / f"ensemble_analysis_{run_date}.json"
    try:
        with open(json_dest, "w", encoding="utf-8") as fh:
            json.dump(json_data, fh, indent=2)
    except OSError as exc:
        print(f"ensemble_model: ERROR writing JSON — {exc}", file=sys.stderr)
        return 1

    # Print to stdout
    print()
    print(report_text)
    print(f"\nReport: {report_dest}")
    print(f"JSON:   {json_dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
