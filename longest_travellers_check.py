"""
longest_travellers_check.py — today's longest traveller(s), trainer form, vs the
actual result.

This signal CANNOT be backtested (no historical traveller data — we only began
collecting it today), so it is forward-tracked: every run appends a row to
data/longest_traveller_log.csv, which becomes the evidence over time.

Usage:
    python longest_travellers_check.py [RACE_DATE]    # default today

Reads the saved longest-travellers list, fetches results for RACE_DATE, matches
by horse name, and prints horse / miles / trainer / 14-day form / finishing
position / SP / verdict. Pass the date the travellers actually RAN if the
freebets page was a day ahead/behind (e.g. it showed 'Saturday').
"""

from __future__ import annotations

import csv
import os
import sys
from typing import Optional

from src.api_client import get_client
from src.helpers import data_path, log, safe_load_json, today_str
from longest_travellers import load as load_travellers, normalise_horse


def _result_lookup(date_str: str) -> dict:
    """horse_key -> {position, sp, trainer, course} from the day's results."""
    doc = get_client().get_results_by_date(date_str) or {}
    out: dict[str, dict] = {}
    for race in (doc.get("results") or []):
        course = race.get("course") or ""
        for r in (race.get("runners") or []):
            key = normalise_horse(r.get("horse") or r.get("horse_name"))
            if not key:
                continue
            out[key] = {
                "position": str(r.get("position") or r.get("finish_position") or ""),
                "sp": r.get("sp_dec") or r.get("sp") or "",
                "trainer": r.get("trainer") or "",
                "course": course,
            }
    return out


def _trainer_form(date_str: str) -> dict:
    """horse_key -> trainer 14-day strike %, from the racecard when present."""
    rc = safe_load_json(data_path(f"racecards_{date_str}.json")) or {}
    out: dict[str, Optional[str]] = {}
    for race in (rc.get("racecards") or []):
        for r in (race.get("runners") or []):
            key = normalise_horse(r.get("horse"))
            if key:
                out[key] = (r.get("trainer_14_days") or {}).get("percent")
    return out


def main() -> int:
    race_date = sys.argv[1] if len(sys.argv) > 1 else today_str()
    travellers = (load_travellers().get("travellers")) or []
    if not travellers:
        print("No saved longest travellers — run `python longest_travellers.py` first.")
        return 1

    try:
        results = _result_lookup(race_date)
    except Exception as exc:  # noqa: BLE001
        log(f"longest_travellers_check: results fetch failed — {exc}", "ERROR")
        return 1
    forms = _trainer_form(race_date)

    print(f"LONGEST TRAVELLERS vs RESULTS — {race_date}")
    print("-" * 78)
    print(f"{'horse':<22}{'miles':>6}  {'trainer':<18}{'14d%':>6}{'pos':>5}{'sp':>8}  verdict")
    print("-" * 78)

    log_rows: list[list] = []
    for t in sorted(travellers, key=lambda x: -x["miles"]):
        key = normalise_horse(t["horse"])
        res = results.get(key)
        pct = forms.get(key)
        pct_s = f"{pct}%" if pct not in (None, "") else "-"
        if not res:
            print(f"{t['horse']:<22}{t['miles']:>6}  {t['trainer']:<18}{pct_s:>6}"
                  f"{'--':>5}{'--':>8}  (not in {race_date} results)")
            continue
        pos = res["position"]
        try:
            pi = int(pos)
        except (TypeError, ValueError):
            pi = 99
        verdict = "WON ✅" if pi == 1 else ("placed" if pi <= 3 else "unplaced")
        print(f"{t['horse']:<22}{t['miles']:>6}  {t['trainer']:<18}{pct_s:>6}"
              f"{pos:>5}{str(res['sp']):>8}  {verdict}")
        log_rows.append([race_date, t["horse"], t.get("course"), t["miles"],
                         t["trainer"], pct, pos, res["sp"],
                         int(pi == 1), int(pi <= 3)])

    if log_rows:
        path = data_path("longest_traveller_log.csv")
        is_new = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if is_new:
                w.writerow(["date", "horse", "course", "miles", "trainer",
                            "trainer_14d_pct", "position", "sp", "won", "placed"])
            w.writerows(log_rows)
        print("-" * 78)
        print(f"Logged {len(log_rows)} row(s) → {path}")
        print("(forward track record — the proof for this signal builds here, run by run)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
