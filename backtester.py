"""
backtester.py — Query model_candidates vs results and measure what's working.

Usage:
    python3 backtester.py           # analyse all history
    python3 backtester.py --days 30 # last 30 days only

Exit codes:
    0 — success
    1 — DB error
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from src.db import get_db
from src.helpers import log, report_path, today_str


def _load_joined_data(db, days: Optional[int] = None) -> list[dict]:
    where = ""
    params: tuple = ()
    if days:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        where = "WHERE mc.candidate_date >= %s"
        params = (cutoff,)
    rows = db.fetch_all(
        f"""
        SELECT mc.candidate_date, mc.horse_name, mc.race_id, mc.course,
               mc.candidate_type, mc.grade, mc.score, mc.model_version,
               r.position, r.sp_decimal, r.won, r.placed, r.official_stake, r.official_pl
        FROM model_candidates mc
        LEFT JOIN results r ON mc.race_id = r.race_id AND mc.horse_id = r.horse_id
        {where}
        ORDER BY mc.candidate_date ASC
        """,
        params,
    )
    return rows


def _score_band(score: float) -> str:
    if score >= 80: return "80+"
    if score >= 70: return "70-79"
    if score >= 60: return "60-69"
    if score >= 50: return "50-59"
    return "<50"


class _Cell:
    def __init__(self):
        self.bets = 0; self.wins = 0; self.places = 0
        self.total_stake = 0.0; self.total_pl = 0.0

    def add(self, row: dict):
        if row.get("position") is None: return
        self.bets += 1
        self.total_stake += float(row.get("official_stake") or 0)
        self.total_pl += float(row.get("official_pl") or 0)
        if row.get("won") in (1, True, "1"): self.wins += 1
        if row.get("placed") in (1, True, "1"): self.places += 1

    def summary(self) -> dict:
        sr = round(self.wins / self.bets * 100, 1) if self.bets else 0.0
        pr = round(self.places / self.bets * 100, 1) if self.bets else 0.0
        roi = round(self.total_pl / self.total_stake * 100, 1) if self.total_stake else 0.0
        return {"bets": self.bets, "wins": self.wins, "places": self.places,
                "strike_rate": sr, "place_rate": pr,
                "total_pl": round(self.total_pl, 2), "roi": roi}


def _analyse(rows: list[dict]) -> dict:
    by_type = defaultdict(_Cell); by_grade = defaultdict(_Cell)
    by_band = defaultdict(_Cell); by_course = defaultdict(_Cell)
    by_model = defaultdict(_Cell); overall = _Cell()
    for row in rows:
        ctype = row.get("candidate_type") or "unknown"
        grade = row.get("grade") or "?"
        score = float(row.get("score") or 0)
        band = _score_band(score)
        course = (row.get("course") or "Unknown").strip()
        model = row.get("model_version") or "?"
        if ctype in ("nap", "best_of_card", "value_ew"):
            overall.add(row); by_type[ctype].add(row); by_grade[grade].add(row)
            by_band[band].add(row); by_course[course].add(row); by_model[model].add(row)
        else:
            by_type[ctype].add(row)
    return {
        "overall": overall.summary(),
        "by_type": {k: v.summary() for k, v in sorted(by_type.items())},
        "by_grade": {k: v.summary() for k, v in sorted(by_grade.items())},
        "by_band": {k: v.summary() for k, v in sorted(by_band.items())},
        "by_course": {k: v.summary() for k, v in sorted(by_course.items(), key=lambda x: x[1].bets, reverse=True)},
        "by_model": {k: v.summary() for k, v in sorted(by_model.items())},
    }


def _update_angle_performance(db, analysis: dict) -> None:
    def _upsert(angle_name: str, s: dict):
        if s["bets"] < 1: return
        status = "active" if s["bets"] >= 100 else ("watch_angle" if s["bets"] >= 30 else "learning")
        if s["roi"] < 0 and s["bets"] >= 30: status = "downgraded"
        expected_wins = s["bets"] * (s["strike_rate"] / 100)
        ae = round(s["wins"] / expected_wins, 2) if expected_wins > 0 else 0.0
        try:
            db.execute(
                """INSERT INTO angle_performance
                    (angle_name, sample_size, wins, places, strike_rate, place_rate, roi, ae_ratio, status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE sample_size=VALUES(sample_size), wins=VALUES(wins),
                   places=VALUES(places), strike_rate=VALUES(strike_rate), place_rate=VALUES(place_rate),
                   roi=VALUES(roi), ae_ratio=VALUES(ae_ratio), status=VALUES(status)""",
                (angle_name, s["bets"], s["wins"], s["places"],
                 s["strike_rate"], s["place_rate"], s["roi"], ae, status),
            )
        except Exception as exc:
            log(f"backtester: angle_performance upsert failed for {angle_name} — {exc}", "WARNING")
    _upsert("overall_nap", analysis["overall"])
    for k, s in analysis["by_grade"].items(): _upsert(f"grade_{k}", s)
    for k, s in analysis["by_band"].items(): _upsert(f"score_band_{k.replace('+','plus')}", s)
    for k, s in analysis["by_course"].items():
        if s["bets"] >= 3: _upsert(f"course_{k.lower().replace(' ','_')}", s)
    for k, s in analysis["by_model"].items(): _upsert(f"model_{k}", s)
    log("backtester: angle_performance table updated")


def _fmt_row(label: str, s: dict, width: int = 22) -> str:
    if s["bets"] == 0: return f"  {label:<{width}}  No data"
    pl_sign = "+" if s["total_pl"] >= 0 else ""
    return (f"  {label:<{width}}  {s['bets']:>4} bets  {s['wins']:>3}W ({s['strike_rate']:>5.1f}%)  "
            f"P/L {pl_sign}{s['total_pl']:>6.2f}u  ROI {s['roi']:>+6.1f}%")


def _build_report(date_str: str, analysis: dict, days: Optional[int]) -> str:
    sep = "═" * 70; thin = "─" * 70
    period = f"Last {days} days" if days else "All time"
    lines = [sep, "  RACING INTELLIGENCE — BACKTESTER REPORT",
             f"  Generated: {date_str}  |  Period: {period}", sep, "",
             "■ OVERALL (NAP + Best of Card)", _fmt_row("All official bets", analysis["overall"]),
             "", thin, "■ BY CANDIDATE TYPE"]
    for k, s in analysis["by_type"].items(): lines.append(_fmt_row(k, s))
    lines += ["", thin, "■ BY GRADE"]
    for k, s in sorted(analysis["by_grade"].items()): lines.append(_fmt_row(f"Grade {k}", s))
    lines += ["", thin, "■ BY SCORE BAND"]
    for k in ["80+", "70-79", "60-69", "50-59", "<50"]:
        s = analysis["by_band"].get(k)
        if s: lines.append(_fmt_row(k, s))
    lines += ["", thin, "■ BY COURSE (3+ bets)"]
    for k, s in analysis["by_course"].items():
        if s["bets"] >= 3: lines.append(_fmt_row(k, s))
    lines += ["", thin, "■ BY MODEL VERSION"]
    for k, s in analysis["by_model"].items(): lines.append(_fmt_row(k, s))
    lines += ["", thin, "■ LEARNING VERDICTS"]
    overall = analysis["overall"]
    if overall["bets"] < 10:
        lines.append(f"  Sample too small ({overall['bets']} bets) — need 30+ for reliable conclusions.")
    else:
        lines.append(f"  Overall ROI: {overall['roi']:+.1f}% — {'adding value' if overall['roi'] > 0 else 'review scoring weights'}.")
    lines += ["", sep]
    return "\n".join(lines)


def main() -> int:
    log("backtester.py started")
    date_str = today_str()
    days: Optional[int] = None
    for arg in sys.argv[1:]:
        if arg == "--days" and sys.argv.index(arg) + 1 < len(sys.argv):
            try: days = int(sys.argv[sys.argv.index(arg) + 1])
            except ValueError: pass
    try:
        db = get_db()
    except Exception as exc:
        log(f"backtester: DB connection failed — {exc}", "ERROR"); return 1
    rows = _load_joined_data(db, days)
    log(f"backtester: loaded {len(rows)} candidate rows from DB")
    if not rows:
        print("backtester: no data yet — need at least one day of selections + results"); return 0
    analysis = _analyse(rows)
    _update_angle_performance(db, analysis)
    report = _build_report(date_str, analysis, days)
    dest = report_path(f"backtest_{date_str}.txt")
    try:
        with open(dest, "w", encoding="utf-8") as fh: fh.write(report)
        log(f"backtester: report saved → {dest}")
    except OSError as exc:
        log(f"backtester: failed to write report — {exc}", "ERROR"); return 1
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
