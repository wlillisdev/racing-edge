"""
forensic_backtest_analysis.py — Deep forensic analysis of NAP model backtest results.

Loads the most recent backtest CSV (data/backtest_*.csv) and optional raw JSON
results from data/backtest_cache/results/*.json to produce a multi-dimensional
forensic report identifying exploitable edges and loss traps.

Sections produced:
  A. Score Calibration
  B. Sub-score Attribution (winners vs losers)
  C. Going × Class Cross-tabulation
  D. Odds Bracket Analysis
  E. Distance Analysis (flat only)
  F. Trainer Form Effectiveness
  G. Days-Since-Last-Run (freshness)
  H. Field-Size × Class Interaction
  I. Winning Form Patterns
  J. Market Movement Effectiveness
  K. Time-of-Year (Monthly) Patterns
  L. Course-Type Analysis

Outputs:
    reports/forensic_analysis_YYYY-MM-DD.txt
    data/forensic_analysis_YYYY-MM-DD.json

Usage:
    python forensic_backtest_analysis.py
    python forensic_backtest_analysis.py --csv data/backtest_2025-01-01_to_2026-01-01.csv

Exit codes:
    0 — report produced
    1 — fatal error (no CSV found, write failure)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Path helpers (inline — no project imports to avoid circular deps)
# ---------------------------------------------------------------------------

def _project_dir() -> Path:
    """Return the directory containing this script."""
    return Path(__file__).resolve().parent


def _data_path(filename: str) -> Path:
    p = _project_dir() / "data" / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _report_path(filename: str) -> Path:
    p = _project_dir() / "reports" / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Going normalisation (inline copy — avoids importing from src)
# ---------------------------------------------------------------------------

_GOING_RULES: list[tuple[str, str]] = [
    ("standard to slow", "Slow"),
    ("slow",             "Slow"),
    ("standard",         "Standard"),
    ("fast",             "Standard"),
    ("good to firm",     "Good to Firm"),
    ("good to soft",     "Good to Soft"),
    ("soft to heavy",    "Heavy"),
    ("heavy",            "Heavy"),
    ("firm",             "Firm"),
    ("good",             "Good"),
    ("soft",             "Soft"),
    ("yielding to soft", "Soft"),
    ("yielding",         "Good to Soft"),
    ("hard",             "Firm"),
]


def going_normalise(going_str: str) -> str:
    if not going_str:
        return going_str
    normalised = going_str.strip().lower()
    normalised = re.sub(r"\(.*?\)", "", normalised).strip()
    for pattern, canonical in _GOING_RULES:
        if pattern in normalised:
            return canonical
    return going_str.strip().title()


# ---------------------------------------------------------------------------
# Category helpers (inline)
# ---------------------------------------------------------------------------

def going_category(going: str) -> str:
    """Map a going string to one of 5 forensic categories."""
    g = going_normalise(going or "").lower()
    if g in ("heavy", "soft"):
        return "Heavy/Soft"
    if g in ("good to soft",):
        return "Good-to-Soft"
    if g == "good":
        return "Good"
    if g in ("good to firm", "firm"):
        return "Good-to-Firm/Firm"
    if g in ("standard", "slow"):
        return "AW"
    return "Other/Unknown"


def class_category(race_class_raw) -> str:
    """Map raw race class to a coarse forensic bracket."""
    if race_class_raw is None:
        return "Unknown"
    s = str(race_class_raw).strip().lower()
    if not s or s in ("none", ""):
        return "Unknown"
    if s.startswith("class"):
        s = s[5:].strip()
    # NH grades
    if "grade 1" in s or s == "g1" or "listed" in s:
        return "NH Grade 1/Listed"
    if "grade 2" in s or s == "g2":
        return "NH Grade 2"
    if "grade 3" in s or s == "g3":
        return "NH Grade 3"
    if "grade" in s:
        return "NH Graded"
    try:
        c = int(s)
        if c <= 2:
            return "Class 1-2"
        if c <= 4:
            return "Class 3-4"
        return "Class 5-6"
    except (TypeError, ValueError):
        return "Unknown"


def score_band_fine(s: float) -> str:
    """5-point score bands for calibration analysis."""
    if s >= 80:
        return "80+"
    if s >= 75:
        return "75-80"
    if s >= 70:
        return "70-75"
    if s >= 65:
        return "65-70"
    if s >= 60:
        return "60-65"
    if s >= 55:
        return "55-60"
    return "<55"


def odds_bracket(sp_dec: float) -> str:
    if sp_dec <= 0:
        return "Unknown"
    if sp_dec <= 3.0:
        return "Evens-2/1"
    if sp_dec <= 4.0:
        return "2/1-3/1"
    if sp_dec <= 6.0:
        return "3/1-5/1"
    if sp_dec <= 9.0:
        return "5/1-8/1"
    return "8/1+"


def distance_band_flat(f: float) -> str:
    if f <= 0:
        return "Unknown"
    if f <= 6.0:
        return "5f-6f (Sprint)"
    if f <= 8.0:
        return "6f-8f (Speed)"
    if f <= 10.0:
        return "8f-10f (Mile)"
    if f <= 14.0:
        return "10f-14f (Mid-dist)"
    return "14f+ (Staying)"


def trainer_pct_band(pct: float) -> str:
    if pct >= 30:
        return "30%+ (Hot)"
    if pct >= 20:
        return "20-30% (In-form)"
    if pct >= 10:
        return "10-20% (Ticking)"
    return "<10% (Cold)"


def freshness_band(days: int) -> str:
    if days < 10:
        return "<10 days"
    if days <= 14:
        return "10-14 days"
    if days <= 28:
        return "14-28 days"
    if days <= 45:
        return "28-45 days"
    if days <= 70:
        return "45-70 days"
    return "70+ days"


def field_size_bracket(n: int) -> str:
    if n <= 6:
        return "Small (<=6)"
    if n <= 10:
        return "Medium (7-10)"
    return "Large (11+)"


# ---------------------------------------------------------------------------
# Stats accumulator
# ---------------------------------------------------------------------------

class Stats:
    __slots__ = ("n", "wins", "places", "pl", "sp_sum", "score_sum", "n_score",
                 "form_sum", "suit_sum", "ctx_sum", "train_sum", "mkt_sum", "n_sub")

    def __init__(self):
        self.n = 0
        self.wins = 0
        self.places = 0
        self.pl = 0.0
        self.sp_sum = 0.0
        self.score_sum = 0.0
        self.n_score = 0
        # sub-score accumulators
        self.form_sum = 0.0
        self.suit_sum = 0.0
        self.ctx_sum = 0.0
        self.train_sum = 0.0
        self.mkt_sum = 0.0
        self.n_sub = 0

    def record(self, row: dict) -> None:
        """Add one CSV row to this bucket."""
        # Only count rows that have a result
        has_result = _bool(row.get("has_result", ""))
        if not has_result:
            return
        self.n += 1
        is_win = _bool(row.get("is_win", ""))
        is_place = _bool(row.get("is_place", ""))
        sp = _float(row.get("sp_dec", 0))
        if is_win:
            self.wins += 1
            self.pl += max(0.0, sp - 1.0)
        else:
            self.pl -= 1.0
        if is_place:
            self.places += 1
        if sp > 0:
            self.sp_sum += sp
        score = _float(row.get("score", None))
        if score is not None and score > 0:
            self.score_sum += score
            self.n_score += 1
        # sub-scores
        fs = _float(row.get("form_score", None))
        ss = _float(row.get("suit_score", None))
        cs = _float(row.get("ctx_score", None))
        ts = _float(row.get("train_score", None))
        ms = _float(row.get("mkt_score", None))
        if all(v is not None for v in (fs, ss, cs, ts, ms)):
            self.form_sum += fs
            self.suit_sum += ss
            self.ctx_sum += cs
            self.train_sum += ts
            self.mkt_sum += ms
            self.n_sub += 1

    @property
    def win_pct(self) -> float:
        return self.wins / self.n * 100 if self.n else 0.0

    @property
    def place_pct(self) -> float:
        return self.places / self.n * 100 if self.n else 0.0

    @property
    def roi(self) -> float:
        return self.pl / self.n * 100 if self.n else 0.0

    @property
    def avg_sp(self) -> float:
        n_sp = sum(1 for _ in range(self.n))  # approximate; use sp_sum count
        # re-derive from sp_sum — n is count of result rows, sp_sum only inc non-zero
        return self.sp_sum / self.n if self.n else 0.0

    @property
    def avg_score(self) -> float:
        return self.score_sum / self.n_score if self.n_score else 0.0

    def avg_sub(self, name: str) -> float:
        if self.n_sub == 0:
            return 0.0
        return getattr(self, f"{name}_sum") / self.n_sub


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def _float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _int(v, default: int = -1) -> int:
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return default


def _bool(v) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    return s in ("true", "1", "yes", "t")


# ---------------------------------------------------------------------------
# Table rendering helpers
# ---------------------------------------------------------------------------

def _pct_str(v: float) -> str:
    return f"{v:+.1f}%"


def _table_header_full() -> str:
    return (
        f"  {'Category':<32} {'N':>5} {'Wins':>5} {'Win%':>6} "
        f"{'Plc%':>6} {'AvgSP':>6} {'P/L':>8} {'ROI%':>7}"
    )


def _table_sep_full() -> str:
    return "  " + "-" * 76


def _table_row_full(name: str, s: Stats, flag: str = "") -> str:
    if s.n < 3:
        return f"  {name:<32} {s.n:>5}    —      —      —         —       — {flag}"
    return (
        f"  {name:<32} {s.n:>5} {s.wins:>5} {s.win_pct:>5.1f}% "
        f"{s.place_pct:>5.1f}% {s.avg_sp:>6.2f} "
        f"{s.pl:>+8.1f} {s.roi:>+6.1f}%{flag}"
    )


def _render_breakdown(
    bd: dict[str, Stats],
    min_n: int = 3,
    sort_by: str = "roi",      # "roi" | "win_pct"
    flag_low: Optional[int] = 5,
) -> list[str]:
    lines = [_table_header_full(), _table_sep_full()]
    items = sorted(
        bd.items(),
        key=lambda kv: (
            -(getattr(kv[1], sort_by) if kv[1].n >= min_n else -9999)
        ),
    )
    for name, s in items:
        flag = ""
        if flag_low and s.n < flag_low and s.n >= min_n:
            flag = "  [!small]"
        lines.append(_table_row_full(name, s, flag))
    return lines


# ---------------------------------------------------------------------------
# CSV loader
# ---------------------------------------------------------------------------

def load_csv(csv_path: Path) -> list[dict]:
    rows: list[dict] = []
    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                rows.append(row)
    except OSError as exc:
        print(f"ERROR: Cannot read CSV {csv_path} — {exc}", file=sys.stderr)
        return []
    return rows


def find_latest_csv() -> Optional[Path]:
    data_dir = _project_dir() / "data"
    candidates = sorted(data_dir.glob("backtest_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


# ---------------------------------------------------------------------------
# JSON results cache loader (optional enrichment)
# ---------------------------------------------------------------------------

def load_result_jsons() -> dict[str, dict]:
    """Load per-day result JSONs from data/backtest_cache/results/*.json.
    Returns a dict keyed by date_str -> raw result dict."""
    results: dict[str, dict] = {}
    results_dir = _project_dir() / "data" / "backtest_cache" / "results"
    if not results_dir.exists():
        return results
    for jf in results_dir.glob("*.json"):
        try:
            with open(jf, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            date_key = jf.stem  # filename = YYYY-MM-DD
            results[date_key] = data
        except (OSError, json.JSONDecodeError):
            continue
    return results


# ---------------------------------------------------------------------------
# Sub-analysis functions
# ---------------------------------------------------------------------------

def analysis_a_score_calibration(rows: list[dict]) -> tuple[list[str], dict]:
    """Score band calibration — is higher score = higher win rate?"""
    bands = ["<55", "55-60", "60-65", "65-70", "70-75", "75-80", "80+"]
    bd: dict[str, Stats] = {b: Stats() for b in bands}

    for row in rows:
        score = _float(row.get("score", 0))
        band = score_band_fine(score)
        if band in bd:
            bd[band].record(row)

    lines = [
        "=" * 78,
        "A. SCORE CALIBRATION",
        "   Is higher composite score correlated with higher win rate?",
        "   (5-point bands — should show monotonic improvement for a well-calibrated model)",
        "=" * 78,
    ]
    lines += _render_breakdown(bd, sort_by="win_pct", flag_low=5)

    # Calibration verdict
    valid_bands = [(b, bd[b]) for b in bands if bd[b].n >= 3]
    if len(valid_bands) >= 3:
        win_rates = [s.win_pct for _, s in valid_bands]
        monotonic = all(win_rates[i] <= win_rates[i+1] for i in range(len(win_rates)-1))
        direction = all(win_rates[i] >= win_rates[i+1] for i in range(len(win_rates)-1))
        if monotonic:
            lines.append("\n  VERDICT: Model is WELL CALIBRATED (win rate increases with score)")
        elif direction:
            lines.append("\n  VERDICT: Model is INVERSELY calibrated (higher score = lower win rate) — investigate!")
        else:
            lines.append("\n  VERDICT: Model calibration is MIXED — not monotonic across bands")

    # Structured data
    data = {
        band: {
            "n": bd[band].n, "wins": bd[band].wins,
            "win_pct": round(bd[band].win_pct, 2),
            "roi": round(bd[band].roi, 2),
            "avg_sp": round(bd[band].avg_sp, 2),
        }
        for band in bands
    }
    return lines, {"score_calibration": data}


def analysis_b_subscore_attribution(rows: list[dict]) -> tuple[list[str], dict]:
    """Compare sub-scores for winners vs losers."""
    winners = Stats()
    losers = Stats()

    for row in rows:
        if not _bool(row.get("has_result", "")):
            continue
        if _bool(row.get("is_win", "")):
            winners.record(row)
        else:
            losers.record(row)

    sub_names = [
        ("form_score",  "Form Score  (0-40)"),
        ("suit_sum",    "Suitability (0-25)"),
        ("ctx_sum",     "Context     (0-15)"),
        ("train_sum",   "Trainer     (0-15)"),
        ("mkt_sum",     "Market      (-10/+5)"),
    ]
    # Map CSV column names to Stats accumulator attributes
    col_to_attr = {
        "form_score": "form",
        "suit_sum":   "suit",
        "ctx_sum":    "ctx",
        "train_sum":  "train",
        "mkt_sum":    "mkt",
    }

    lines = [
        "",
        "=" * 78,
        "B. SUB-SCORE ATTRIBUTION — Winners vs Losers",
        "   Which sub-score best differentiates winning NAPs from losing NAPs?",
        "=" * 78,
        f"  {'Sub-Score':<26} {'Winners avg':>12} {'Losers avg':>12} {'Delta':>8} {'Differentiator?':>16}",
        "  " + "-" * 76,
    ]

    attribution_data = {}
    deltas: list[tuple[str, float]] = []

    for col_key, label in sub_names:
        attr = col_to_attr[col_key]
        w_avg = winners.avg_sub(attr) if winners.n_sub > 0 else 0.0
        l_avg = losers.avg_sub(attr) if losers.n_sub > 0 else 0.0
        delta = w_avg - l_avg
        deltas.append((label, delta))
        star = "  *** BEST EDGE ***" if abs(delta) == max(abs(d) for _, d in deltas) and len(deltas) == 5 else ""
        lines.append(f"  {label:<26} {w_avg:>12.2f} {l_avg:>12.2f} {delta:>+8.2f}{star}")
        attribution_data[col_key] = {
            "winners_avg": round(w_avg, 2),
            "losers_avg": round(l_avg, 2),
            "delta": round(delta, 2),
        }

    # Re-annotate after all deltas are known
    if deltas:
        max_delta_label = max(deltas, key=lambda x: abs(x[1]))
        lines.append(f"\n  VERDICT: '{max_delta_label[0].strip()}' has the largest winner/loser delta ({max_delta_label[1]:+.2f} pts)")
        lines.append(f"  Winners: n={winners.n}   Losers: n={losers.n}")

    return lines, {"subscore_attribution": attribution_data}


def analysis_c_going_class_crosstab(rows: list[dict]) -> tuple[list[str], dict]:
    """Going × class cross-tabulation."""
    going_cats = ["Heavy/Soft", "Good-to-Soft", "Good", "Good-to-Firm/Firm", "AW", "Other/Unknown"]
    class_cats = ["Class 1-2", "Class 3-4", "Class 5-6", "NH Grade 1/Listed", "NH Grade 2", "NH Grade 3", "NH Graded", "Unknown"]

    # nested dict: [going][class] = Stats
    crosstab: dict[str, dict[str, Stats]] = {
        g: {c: Stats() for c in class_cats} for g in going_cats
    }

    for row in rows:
        going = going_category(row.get("going", "") or row.get("going_group", ""))
        cls   = class_category(row.get("race_class", "") or row.get("class", ""))
        if going not in crosstab:
            going = "Other/Unknown"
        if cls not in class_cats:
            cls = "Unknown"
        crosstab[going][cls].record(row)

    lines = [
        "",
        "=" * 78,
        "C. GOING × CLASS CROSS-TABULATION",
        "   Win rate for every (going × class) cell.  [!small] = < 5 selections.",
        "=" * 78,
    ]

    crosstab_data: dict = {}
    for going in going_cats:
        has_data = any(crosstab[going][c].n >= 3 for c in class_cats)
        if not has_data:
            continue
        lines.append(f"\n  Going: {going}")
        lines.append(f"  {'Class':<22} {'N':>5} {'Wins':>5} {'Win%':>6} {'P/L':>8} {'ROI%':>7}")
        lines.append("  " + "-" * 60)
        for cls in class_cats:
            s = crosstab[going][cls]
            flag = "  [!small]" if 0 < s.n < 5 else ""
            if s.n == 0:
                continue
            if s.n < 3:
                lines.append(f"  {cls:<22} {s.n:>5}    —      —         —       — {flag}")
            else:
                lines.append(
                    f"  {cls:<22} {s.n:>5} {s.wins:>5} {s.win_pct:>5.1f}% "
                    f"{s.pl:>+8.1f} {s.roi:>+6.1f}%{flag}"
                )
        crosstab_data[going] = {
            cls: {"n": crosstab[going][cls].n, "win_pct": round(crosstab[going][cls].win_pct, 2),
                  "roi": round(crosstab[going][cls].roi, 2)}
            for cls in class_cats if crosstab[going][cls].n > 0
        }

    return lines, {"going_class_crosstab": crosstab_data}


def analysis_d_odds_brackets(rows: list[dict]) -> tuple[list[str], dict]:
    """Win rate and ROI by odds bracket."""
    bracket_order = ["Evens-2/1", "2/1-3/1", "3/1-5/1", "5/1-8/1", "8/1+", "Unknown"]
    bd: dict[str, Stats] = {b: Stats() for b in bracket_order}

    for row in rows:
        sp = _float(row.get("sp_dec", 0))
        bracket = odds_bracket(sp)
        if bracket not in bd:
            bracket = "Unknown"
        bd[bracket].record(row)

    lines = [
        "",
        "=" * 78,
        "D. ODDS BRACKET ANALYSIS",
        "   Identify VALUE ZONES where ROI > 0 consistently.",
        "=" * 78,
    ]
    lines += _render_breakdown(
        {b: bd[b] for b in bracket_order},
        sort_by="roi",
        flag_low=5,
    )

    value_zones = [b for b in bracket_order if bd[b].n >= 5 and bd[b].roi > 0]
    loss_zones  = [b for b in bracket_order if bd[b].n >= 5 and bd[b].roi < -20]
    if value_zones:
        lines.append(f"\n  VALUE ZONES (ROI > 0): {', '.join(value_zones)}")
    if loss_zones:
        lines.append(f"  LOSS ZONES  (ROI < -20%): {', '.join(loss_zones)}")

    data = {
        b: {"n": bd[b].n, "win_pct": round(bd[b].win_pct, 2), "roi": round(bd[b].roi, 2)}
        for b in bracket_order
    }
    return lines, {"odds_brackets": data}


def analysis_e_distance(rows: list[dict]) -> tuple[list[str], dict]:
    """Distance analysis — flat races only."""
    flat_rows = [
        r for r in rows
        if not any(x in (r.get("race_type", "") or r.get("type_group", "")).lower()
                   for x in ("chase", "hurdle", "bumper", "nhf"))
    ]

    band_order = ["5f-6f (Sprint)", "6f-8f (Speed)", "8f-10f (Mile)",
                  "10f-14f (Mid-dist)", "14f+ (Staying)", "Unknown"]
    bd: dict[str, Stats] = {b: Stats() for b in band_order}

    for row in flat_rows:
        dist_f = _float(row.get("distance_f", 0))
        band = distance_band_flat(dist_f)
        if band not in bd:
            band = "Unknown"
        bd[band].record(row)

    lines = [
        "",
        "=" * 78,
        f"E. DISTANCE ANALYSIS (flat races only — {len(flat_rows)} rows)",
        "=" * 78,
    ]
    lines += _render_breakdown(
        {b: bd[b] for b in band_order},
        sort_by="roi",
        flag_low=5,
    )

    data = {
        b: {"n": bd[b].n, "win_pct": round(bd[b].win_pct, 2), "roi": round(bd[b].roi, 2)}
        for b in band_order
    }
    return lines, {"distance_analysis": data}


def analysis_f_trainer_form(rows: list[dict]) -> tuple[list[str], dict]:
    """Trainer 14-day strike rate effectiveness.
    The CSV itself doesn't contain trainer pct — we try to source it from
    the raw JSON result files if available, otherwise skip gracefully."""

    # The backtest CSV records train_score (0-15), which encodes pct bands:
    # >=30% -> 8pts, 20-30% -> 5pts, 10-20% -> 2pts, <10% -> 0pts
    # We can reverse-engineer approximate bands from train_score.
    band_order = ["30%+ (Hot)", "20-30% (In-form)", "10-20% (Ticking)", "<10% (Cold)", "No data"]

    def train_score_to_band(ts: float) -> str:
        # wind_surgery (+3) and stable_tour (+2) can inflate, so use conservative cutoffs
        if ts >= 7.5:
            return "30%+ (Hot)"
        if ts >= 4.5:
            return "20-30% (In-form)"
        if ts >= 1.5:
            return "10-20% (Ticking)"
        if ts >= 0:
            return "<10% (Cold)"
        return "No data"

    bd: dict[str, Stats] = {b: Stats() for b in band_order}

    for row in rows:
        ts = _float(row.get("train_score", None))
        if ts is None:
            band = "No data"
        else:
            band = train_score_to_band(ts)
        if band not in bd:
            band = "No data"
        bd[band].record(row)

    lines = [
        "",
        "=" * 78,
        "F. TRAINER FORM EFFECTIVENESS",
        "   Bucketed via train_score proxy (score >= 7.5 = hot trainer etc.).",
        "   Note: train_score may include wind-surgery and stable-tour bonuses.",
        "=" * 78,
    ]
    lines += _render_breakdown(
        {b: bd[b] for b in band_order},
        sort_by="roi",
        flag_low=5,
    )

    # ROI contribution insight
    hot = bd.get("30%+ (Hot)")
    cold = bd.get("<10% (Cold)")
    if hot and cold and hot.n >= 3 and cold.n >= 3:
        diff = hot.roi - cold.roi
        lines.append(
            f"\n  HOT vs COLD trainer ROI spread: {diff:+.1f}% pts "
            f"(Hot={hot.roi:+.1f}%, Cold={cold.roi:+.1f}%)"
        )

    data = {
        b: {"n": bd[b].n, "win_pct": round(bd[b].win_pct, 2), "roi": round(bd[b].roi, 2)}
        for b in band_order if bd[b].n > 0
    }
    return lines, {"trainer_form": data}


def analysis_g_freshness(rows: list[dict]) -> tuple[list[str], dict]:
    """Days since last run analysis, split by flat vs jumps."""
    band_order = ["<10 days", "10-14 days", "14-28 days", "28-45 days", "45-70 days", "70+ days", "Unknown"]

    bd_flat:  dict[str, Stats] = {b: Stats() for b in band_order}
    bd_jumps: dict[str, Stats] = {b: Stats() for b in band_order}
    bd_all:   dict[str, Stats] = {b: Stats() for b in band_order}

    for row in rows:
        # last_run is not in CSV directly — approximate from form_score freshness component.
        # The backtest CSV does NOT include last_run, so we use form_score deltas as proxy.
        # However if the raw data does have it via another column we accept it.
        last_run_raw = row.get("last_run", "") or row.get("days_since_run", "")
        days = _int(last_run_raw, default=-1)
        if days < 0:
            band = "Unknown"
        else:
            band = freshness_band(days)

        rt = (row.get("race_type", "") or row.get("type_group", "")).lower()
        is_jump = any(x in rt for x in ("chase", "hurdle", "bumper", "nhf"))

        if band not in bd_all:
            band = "Unknown"
        bd_all[band].record(row)
        if is_jump:
            bd_jumps[band].record(row)
        else:
            bd_flat[band].record(row)

    lines = [
        "",
        "=" * 78,
        "G. DAYS-SINCE-LAST-RUN (FRESHNESS) ANALYSIS",
        "   Note: 'last_run' not stored in CSV — using available data.",
        "   If all rows fall into 'Unknown', re-run backtest to include this column.",
        "=" * 78,
    ]

    n_unknown = bd_all.get("Unknown", Stats()).n
    n_total   = sum(s.n for s in bd_all.values())

    if n_unknown == n_total and n_total > 0:
        lines.append(
            "\n  [SKIPPED] No 'last_run'/'days_since_run' column in CSV.\n"
            "  Add last_run to backtest CSV output to enable this analysis."
        )
        return lines, {"freshness": {"skipped": True, "reason": "last_run column not in CSV"}}

    lines.append("\n  ALL SELECTIONS:")
    lines += _render_breakdown({b: bd_all[b] for b in band_order}, sort_by="roi", flag_low=5)
    lines.append("\n  FLAT ONLY:")
    lines += _render_breakdown({b: bd_flat[b] for b in band_order}, sort_by="roi", flag_low=5)
    lines.append("\n  JUMPS ONLY:")
    lines += _render_breakdown({b: bd_jumps[b] for b in band_order}, sort_by="roi", flag_low=5)

    data = {
        "all":   {b: {"n": bd_all[b].n, "win_pct": round(bd_all[b].win_pct, 2), "roi": round(bd_all[b].roi, 2)} for b in band_order},
        "flat":  {b: {"n": bd_flat[b].n, "win_pct": round(bd_flat[b].win_pct, 2), "roi": round(bd_flat[b].roi, 2)} for b in band_order},
        "jumps": {b: {"n": bd_jumps[b].n, "win_pct": round(bd_jumps[b].win_pct, 2), "roi": round(bd_jumps[b].roi, 2)} for b in band_order},
    }
    return lines, {"freshness": data}


def analysis_h_field_class_interaction(rows: list[dict]) -> tuple[list[str], dict]:
    """Field-size × Class interaction — validate small-field (+8) bonus."""
    # Build composite keys
    bd: dict[str, Stats] = defaultdict(Stats)

    for row in rows:
        # field_size not in CSV directly — derive from context_score
        # ctx_score: <=6 runners -> +8, <=9 -> +5, <=13 -> +3, else 0
        # plus class modifier. Approximate field size from ctx_score.
        ctx = _float(row.get("ctx_score", None))
        cls = class_category(row.get("race_class", "") or row.get("class", ""))

        # bucket class
        if cls in ("Class 1-2",):
            cls_bucket = "Class 1-2 (Elite)"
        elif cls in ("Class 3-4",):
            cls_bucket = "Class 3-4 (Competitive)"
        elif cls in ("Class 5-6",):
            cls_bucket = "Class 5-6 (Lower)"
        elif "NH" in cls or "Grade" in cls:
            cls_bucket = "NH Graded"
        else:
            cls_bucket = "Unknown"

        # approximate field from ctx_score contribution
        # ctx includes class points: class1-2=+5, class3=+3, class4=+1, class5=-2, class6=-4
        # and field: <=6=+8, <=9=+5, <=13=+3, else=0
        # We can only approximate — try to use both
        if ctx >= 12:
            fs_bucket = "Small (<=6)"
        elif ctx >= 7:
            fs_bucket = "Medium (7-10)"
        elif ctx >= 2:
            fs_bucket = "Large (11+)"
        else:
            fs_bucket = "Unknown"

        key = f"{fs_bucket} | {cls_bucket}"
        bd[key].record(row)

    lines = [
        "",
        "=" * 78,
        "H. FIELD-SIZE × CLASS INTERACTION",
        "   Field size approximated from context_score (exact field_size not in CSV).",
        "   Is the small-field bonus (+8 pts) justified at all class levels?",
        "=" * 78,
    ]
    lines += _render_breakdown(dict(bd), sort_by="roi", flag_low=5)

    # Specific test: small field in top class vs bottom class
    small_elite  = bd.get("Small (<=6) | Class 1-2 (Elite)", Stats())
    small_lower  = bd.get("Small (<=6) | Class 5-6 (Lower)", Stats())
    if small_elite.n >= 3 and small_lower.n >= 3:
        lines.append(
            f"\n  Small-field bonus effectiveness:"
            f"\n    Class 1-2 Elite : Win={small_elite.win_pct:.1f}%  ROI={small_elite.roi:+.1f}%  (n={small_elite.n})"
            f"\n    Class 5-6 Lower : Win={small_lower.win_pct:.1f}%  ROI={small_lower.roi:+.1f}%  (n={small_lower.n})"
        )
        if small_elite.roi > small_lower.roi:
            lines.append("  VERDICT: Small-field bonus is MORE effective in elite classes.")
        else:
            lines.append("  VERDICT: Small-field bonus is MORE effective in lower classes.")

    data = {k: {"n": s.n, "win_pct": round(s.win_pct, 2), "roi": round(s.roi, 2)} for k, s in bd.items()}
    return lines, {"field_class_interaction": data}


def analysis_i_form_patterns(rows: list[dict]) -> tuple[list[str], dict]:
    """Winning form string patterns."""

    def parse_form_chars(form: str) -> list[str]:
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

    def is_improving(chars: list[str]) -> bool:
        nums = []
        for c in chars[:3]:
            try:
                nums.append(int(c))
            except ValueError:
                return False
        if len(nums) < 3:
            return False
        return nums[0] < nums[1] < nums[2]

    winners_rows = [
        r for r in rows
        if _bool(r.get("has_result", "")) and _bool(r.get("is_win", ""))
    ]
    losers_rows = [
        r for r in rows
        if _bool(r.get("has_result", "")) and not _bool(r.get("is_win", ""))
    ]

    def calc_pattern_stats(sample: list[dict]) -> dict:
        n = len(sample)
        if n == 0:
            return {}
        won_lto = sum(1 for r in sample if parse_form_chars(r.get("form", ""))[:1] == ["1"])
        improving = sum(1 for r in sample if is_improving(parse_form_chars(r.get("form", ""))))
        has_fup = sum(
            1 for r in sample
            if any(c in parse_form_chars(r.get("form", ""))[:3] for c in ("F", "U", "P"))
        )
        no_form = sum(1 for r in sample if not parse_form_chars(r.get("form", "")))
        return {
            "n": n,
            "won_lto_pct": round(won_lto / n * 100, 1),
            "improving_trend_pct": round(improving / n * 100, 1),
            "had_FUP_last3_pct": round(has_fup / n * 100, 1),
            "no_form_pct": round(no_form / n * 100, 1),
        }

    w_stats = calc_pattern_stats(winners_rows)
    l_stats = calc_pattern_stats(losers_rows)

    lines = [
        "",
        "=" * 78,
        "I. WINNING FORM PATTERNS",
        "=" * 78,
    ]
    if not w_stats:
        lines.append("  [SKIPPED] No winners with result data found.")
        return lines, {"form_patterns": {"skipped": True}}

    lines += [
        f"  {'Pattern':<30} {'Winners':>10} {'Losers':>10} {'Edge':>8}",
        "  " + "-" * 62,
        f"  {'Won last time out':<30} {w_stats.get('won_lto_pct', 0):>9.1f}% {l_stats.get('won_lto_pct', 0):>9.1f}% "
        f"{w_stats.get('won_lto_pct', 0) - l_stats.get('won_lto_pct', 0):>+7.1f}%",
        f"  {'Improving trend (3 runs)':<30} {w_stats.get('improving_trend_pct', 0):>9.1f}% {l_stats.get('improving_trend_pct', 0):>9.1f}% "
        f"{w_stats.get('improving_trend_pct', 0) - l_stats.get('improving_trend_pct', 0):>+7.1f}%",
        f"  {'F/U/P in last 3':<30} {w_stats.get('had_FUP_last3_pct', 0):>9.1f}% {l_stats.get('had_FUP_last3_pct', 0):>9.1f}% "
        f"{w_stats.get('had_FUP_last3_pct', 0) - l_stats.get('had_FUP_last3_pct', 0):>+7.1f}%",
        f"  {'No form (debutant/blank)':<30} {w_stats.get('no_form_pct', 0):>9.1f}% {l_stats.get('no_form_pct', 0):>9.1f}% "
        f"{w_stats.get('no_form_pct', 0) - l_stats.get('no_form_pct', 0):>+7.1f}%",
        "",
        f"  Winners: n={w_stats['n']}   Losers: n={l_stats['n']}",
    ]

    return lines, {"form_patterns": {"winners": w_stats, "losers": l_stats}}


def analysis_j_market_movement(rows: list[dict]) -> tuple[list[str], dict]:
    """Market movement effectiveness — validate dangerous_drift block.
    Uses market_score as proxy for movement signal."""

    # market_score bands:
    # strong_steamer -> +5, steamer -> +3, no movement with price -> see odds
    # weak_drift -> -3, dangerous_drift -> -10 (but these are blocked so won't appear)
    # We approximate:
    # mkt_score >= 4 -> likely steamer; 0-4 -> neutral; < 0 -> drifter
    bd_move: dict[str, Stats] = {
        "Strong steamer (mkt>=4)":   Stats(),
        "Neutral/no signal (0-4)":   Stats(),
        "Drifter (mkt<0)":           Stats(),
        "No market data":            Stats(),
    }

    n_no_mkt = 0
    for row in rows:
        ms = row.get("mkt_score", "")
        if ms == "" or ms is None:
            bd_move["No market data"].record(row)
            n_no_mkt += 1
            continue
        ms_f = _float(ms)
        if ms_f >= 4.0:
            bd_move["Strong steamer (mkt>=4)"].record(row)
        elif ms_f >= 0.0:
            bd_move["Neutral/no signal (0-4)"].record(row)
        else:
            bd_move["Drifter (mkt<0)"].record(row)

    lines = [
        "",
        "=" * 78,
        "J. MARKET MOVEMENT EFFECTIVENESS",
        "   market_score proxy: >=4 = steamer, 0-4 = neutral, <0 = drifter.",
        "   dangerous_drift selections are BLOCKED so they do not appear here.",
        "=" * 78,
    ]
    lines += _render_breakdown(bd_move, sort_by="roi", flag_low=5)

    steamer  = bd_move["Strong steamer (mkt>=4)"]
    drifter  = bd_move["Drifter (mkt<0)"]
    neutral  = bd_move["Neutral/no signal (0-4)"]
    if steamer.n >= 3 and drifter.n >= 3:
        lines.append(
            f"\n  Steamer vs Drifter ROI gap: {steamer.roi - drifter.roi:+.1f}% pts "
            f"(Steamer={steamer.roi:+.1f}%, Drifter={drifter.roi:+.1f}%)"
        )
    if n_no_mkt > 0:
        lines.append(f"  Rows with no market data: {n_no_mkt}")

    data = {k: {"n": s.n, "win_pct": round(s.win_pct, 2), "roi": round(s.roi, 2)} for k, s in bd_move.items()}
    return lines, {"market_movement": data}


def analysis_k_monthly(rows: list[dict]) -> tuple[list[str], dict]:
    """Monthly and seasonal win rate patterns."""
    month_names = {
        1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
        7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
    }
    bd_month: dict[str, Stats] = {f"{i:02d} {month_names[i]}": Stats() for i in range(1, 13)}
    bd_season: dict[str, Stats] = {
        "Early Flat (Mar-May)":  Stats(),
        "Mid Season (Jun-Aug)":  Stats(),
        "Late Flat (Sep-Nov)":   Stats(),
        "Winter/Jumps (Dec-Feb)": Stats(),
    }

    for row in rows:
        date_str = row.get("date", "")
        try:
            dt = date.fromisoformat(str(date_str).strip())
            m = dt.month
        except (ValueError, AttributeError):
            continue

        key = f"{m:02d} {month_names[m]}"
        if key in bd_month:
            bd_month[key].record(row)

        if m in (3, 4, 5):
            bd_season["Early Flat (Mar-May)"].record(row)
        elif m in (6, 7, 8):
            bd_season["Mid Season (Jun-Aug)"].record(row)
        elif m in (9, 10, 11):
            bd_season["Late Flat (Sep-Nov)"].record(row)
        else:
            bd_season["Winter/Jumps (Dec-Feb)"].record(row)

    lines = [
        "",
        "=" * 78,
        "K. TIME-OF-YEAR PATTERNS",
        "   Are there seasonal edges or traps?",
        "=" * 78,
        "\n  BY MONTH (sorted by ROI):",
    ]
    lines += _render_breakdown(bd_month, sort_by="roi", flag_low=5)
    lines.append("\n  BY SEASON:")
    lines += _render_breakdown(bd_season, sort_by="roi", flag_low=5)

    data = {
        "monthly": {k: {"n": s.n, "win_pct": round(s.win_pct, 2), "roi": round(s.roi, 2)} for k, s in bd_month.items()},
        "seasonal": {k: {"n": s.n, "win_pct": round(s.win_pct, 2), "roi": round(s.roi, 2)} for k, s in bd_season.items()},
    }
    return lines, {"monthly_patterns": data}


def analysis_l_courses(rows: list[dict]) -> tuple[list[str], dict]:
    """Top/bottom courses by ROI (min 5 selections)."""
    bd: dict[str, Stats] = defaultdict(Stats)

    for row in rows:
        course = (row.get("course", "") or "").strip().title()
        if not course:
            course = "Unknown"
        bd[course].record(row)

    # Filter to courses with enough data
    qualified = {k: v for k, v in bd.items() if v.n >= 5}

    lines = [
        "",
        "=" * 78,
        "L. COURSE-TYPE ANALYSIS",
        f"   {len(qualified)} courses with >= 5 selections (total courses seen: {len(bd)})",
        "=" * 78,
        "\n  TOP 10 COURSES BY ROI (min 5 selections):",
    ]

    sorted_by_roi = sorted(qualified.items(), key=lambda kv: -kv[1].roi)
    top10 = sorted_by_roi[:10]
    header = f"  {'Course':<28} {'N':>5} {'Wins':>5} {'Win%':>6} {'P/L':>8} {'ROI%':>7}"
    sep = "  " + "-" * 64
    lines += [header, sep]
    for name, s in top10:
        lines.append(
            f"  {name:<28} {s.n:>5} {s.wins:>5} {s.win_pct:>5.1f}%"
            f" {s.pl:>+8.1f} {s.roi:>+6.1f}%"
        )

    lines.append("\n  BOTTOM 5 COURSES BY ROI (traps — min 5 selections):")
    lines += [header, sep]
    bottom5 = sorted_by_roi[-5:] if len(sorted_by_roi) >= 5 else sorted_by_roi
    for name, s in reversed(bottom5):
        lines.append(
            f"  {name:<28} {s.n:>5} {s.wins:>5} {s.win_pct:>5.1f}%"
            f" {s.pl:>+8.1f} {s.roi:>+6.1f}%"
        )

    if not qualified:
        lines.append("  [SKIPPED] No courses with >= 5 selections.")

    data = {
        "top_10": [
            {"course": k, "n": s.n, "win_pct": round(s.win_pct, 2), "roi": round(s.roi, 2)}
            for k, s in top10
        ],
        "bottom_5": [
            {"course": k, "n": s.n, "win_pct": round(s.win_pct, 2), "roi": round(s.roi, 2)}
            for k, s in reversed(bottom5)
        ],
    }
    return lines, {"course_analysis": data}


# ---------------------------------------------------------------------------
# Summary / top-3 edges + bottom-3 traps
# ---------------------------------------------------------------------------

def build_summary(all_data: dict) -> list[str]:
    """Scan structured analysis data and surface top 3 edges + bottom 3 traps."""
    candidates: list[tuple[float, str, str]] = []  # (roi, label, description)

    def _scan_section(section_name: str, section_data: dict) -> None:
        for key, val in section_data.items():
            if not isinstance(val, dict):
                continue
            roi = val.get("roi")
            n   = val.get("n", 0)
            wp  = val.get("win_pct")
            if roi is None or n < 5:
                continue
            label = f"[{section_name}] {key}"
            desc  = f"ROI={roi:+.1f}%, Win={wp:.1f}%, n={n}"
            candidates.append((roi, label, desc))

    # Flatten all top-level sections
    for section, data in all_data.items():
        if isinstance(data, dict):
            # depth 1 flat dict
            if any(isinstance(v, dict) and "roi" in v for v in data.values()):
                _scan_section(section, data)
            else:
                # depth 2 (e.g. going_class_crosstab -> going -> class)
                for subkey, subdata in data.items():
                    if isinstance(subdata, dict):
                        _scan_section(f"{section}/{subkey}", subdata)

    if not candidates:
        return ["  No summary candidates found (insufficient data)."]

    edges = sorted(candidates, key=lambda x: -x[0])
    traps = sorted(candidates, key=lambda x: x[0])

    lines = [
        "",
        "=" * 78,
        "SUMMARY: TOP 3 EDGES & BOTTOM 3 TRAPS",
        "=" * 78,
        "",
        "  TOP 3 EXPLOITABLE EDGES (highest ROI):",
        "  " + "-" * 60,
    ]
    for i, (roi, label, desc) in enumerate(edges[:3], 1):
        lines.append(f"  {i}. {label}")
        lines.append(f"     {desc}")
    lines += [
        "",
        "  BOTTOM 3 TRAPS TO AVOID (lowest ROI):",
        "  " + "-" * 60,
    ]
    for i, (roi, label, desc) in enumerate(traps[:3], 1):
        lines.append(f"  {i}. {label}")
        lines.append(f"     {desc}")
    lines.append("")

    return lines


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Forensic NAP model backtest analysis")
    parser.add_argument("--csv", type=str, default=None,
                        help="Path to backtest CSV (default: most recent data/backtest_*.csv)")
    parser.add_argument("--min-score", type=float, default=0.0, dest="min_score",
                        help="Only include rows with score >= this value (default: 0 = all)")
    args = parser.parse_args()

    # --- Find CSV ----------------------------------------------------------------
    if args.csv:
        csv_path = Path(args.csv)
        if not csv_path.is_absolute():
            csv_path = _project_dir() / args.csv
    else:
        csv_path = find_latest_csv()

    if csv_path is None or not csv_path.exists():
        print(
            "ERROR: No backtest CSV found.\n"
            "Run historical_backtest.py first to generate data/backtest_*.csv",
            file=sys.stderr,
        )
        return 1

    print(f"Loading CSV: {csv_path}")
    rows = load_csv(csv_path)
    if not rows:
        print("ERROR: CSV is empty or unreadable.", file=sys.stderr)
        return 1

    # --- Optional JSON enrichment ------------------------------------------------
    json_results = load_result_jsons()
    if json_results:
        print(f"Loaded {len(json_results)} daily result JSON files (optional enrichment)")

    # --- Filter ------------------------------------------------------------------
    if args.min_score > 0:
        rows = [r for r in rows if _float(r.get("score", 0)) >= args.min_score]
        print(f"Filtered to score >= {args.min_score}: {len(rows)} rows")

    # Only rows that have result data for win-rate calculations
    result_rows = [r for r in rows if _bool(r.get("has_result", ""))]
    print(f"Total CSV rows: {len(rows)}  |  Rows with results: {len(result_rows)}")

    if len(result_rows) < 3:
        print("ERROR: Fewer than 3 rows with result data — analysis not meaningful.", file=sys.stderr)
        return 1

    date_str_today = date.today().isoformat()

    # --- Run all analyses --------------------------------------------------------
    all_lines: list[str] = []
    all_data:  dict = {}

    header = [
        "=" * 78,
        "  FORENSIC BACKTEST ANALYSIS — NAP MODEL",
        f"  Source CSV:  {csv_path.name}",
        f"  Total rows:  {len(rows)}  |  With results: {len(result_rows)}",
        f"  Generated:   {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"  Min score:   {args.min_score if args.min_score > 0 else 'none'}",
        "=" * 78,
    ]
    all_lines += header

    analyses = [
        ("A", analysis_a_score_calibration),
        ("B", analysis_b_subscore_attribution),
        ("C", analysis_c_going_class_crosstab),
        ("D", analysis_d_odds_brackets),
        ("E", analysis_e_distance),
        ("F", analysis_f_trainer_form),
        ("G", analysis_g_freshness),
        ("H", analysis_h_field_class_interaction),
        ("I", analysis_i_form_patterns),
        ("J", analysis_j_market_movement),
        ("K", analysis_k_monthly),
        ("L", analysis_l_courses),
    ]

    for label, func in analyses:
        try:
            lines, data = func(rows)
            all_lines += lines
            all_data.update(data)
        except Exception as exc:
            all_lines.append(f"\n[Section {label} ERROR: {exc}]")
            print(f"WARNING: Section {label} failed: {exc}")

    # --- Summary -----------------------------------------------------------------
    try:
        summary_lines = build_summary(all_data)
        all_lines += summary_lines
    except Exception as exc:
        all_lines.append(f"\n[Summary ERROR: {exc}]")

    # --- Outputs -----------------------------------------------------------------
    report_text = "\n".join(all_lines)

    txt_dest = _report_path(f"forensic_analysis_{date_str_today}.txt")
    try:
        with open(txt_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
        print(f"\nText report:  {txt_dest}")
    except OSError as exc:
        print(f"ERROR: Failed to write report — {exc}", file=sys.stderr)
        return 1

    json_dest = _data_path(f"forensic_analysis_{date_str_today}.json")
    try:
        with open(json_dest, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "generated_at": datetime.now().isoformat(),
                    "csv_source": str(csv_path),
                    "n_rows": len(rows),
                    "n_result_rows": len(result_rows),
                    "analyses": all_data,
                },
                fh,
                indent=2,
                ensure_ascii=False,
            )
        print(f"JSON data:    {json_dest}")
    except OSError as exc:
        print(f"WARNING: Failed to write JSON — {exc}")

    # --- Print summary to stdout -------------------------------------------------
    print("\n" + "=" * 78)
    print("QUICK SUMMARY")
    print("=" * 78)
    try:
        summary_lines = build_summary(all_data)
        print("\n".join(summary_lines))
    except Exception as exc:
        print(f"Summary error: {exc}")

    print(f"\nFull forensic report: {txt_dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
