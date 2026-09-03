"""THE BAR BACKTEST — did tonight's bar make race selection more readable?

The master (2026-09-02, on the night the race-selection key changed to a BAR:
BETTING_BAR = 2 in ``pipeline.nap``, races below it lose to any race above it,
above it the best horse wins): "v1 was starting to calibrate and dial in; the
changes are an unknown — has it improved or made the system worse? How can we
evaluate this without waiting months?"

This replays that bar over every RESULTED race already on disk
(data/school/raw/*.csv — no API calls, no model) and asks, purely off the
settled record: do races that clear the bar read more honestly than races
that do not — favourite strike and ROI, winner-in-the-front-three coverage,
and the 2nd/3rd favourite's strike (the "best horse not the jolly" proxy) —
month by month. An evening's arithmetic instead of months of live naps.

TERMS AND LIMITS — say them once, loudly:
  * The corpus row (see school.mine.Runner) carries NO handicap flag, no
    going, no race name. `is_handicap` is therefore scored as False/unknown
    for EVERY race here — that UNDER-SCORES every honest handicap by 1
    against the live pipeline (which reads the racecard's real flag). Every
    score in this module is biased DOWN by up to 1 versus a live read.
  * SP here is the corpus's settled starting price, not the 07:30 consensus
    price the live shape-book glance is asked with (shapebook's own named v1
    limit) — a market that drifted between 07:30 and the off is judged on
    where it FINISHED, not where the glance saw it.
  * The shape-book cell vote is replayed LEAK-SAFELY (unlike
    shapebook.build(), which is built once on the whole corpus, including
    the race it then judges): cells here are rebuilt cumulatively month by
    month, and a race is only ever glanced against cells built from races
    STRICTLY BEFORE its own month, and only when that cell already holds at
    least 30 races — otherwise the race gets NO VOTE (verdict=None, no shape
    bonus or penalty), exactly as a live glance would see an unbuilt book.

Usage: PYTHONPATH=src python -m racing_edge.school.bar_backtest
           [--raw data/school/raw] [--out data/school/bar_backtest.md]
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from racing_edge.pipeline.nap import BETTING_BAR, race_quality_score
from racing_edge.school.mine import load_corpus
from racing_edge.school.shapebook import _class_band, _field_band, _fav_band
from racing_edge.school.shapebook import triage as shape_triage

AW_COURSES = ("wolverhampton", "kempton", "lingfield", "southwell",
              "newcastle", "chelmsford", "dundalk")

_RACE_TYPE_NAME = {"F": "Flat", "H": "Hurdle", "C": "Chase", "N": "NH Flat"}

MIN_CELL_N = 30   # the shape-book's own bar for a cell to earn a vote


# --------------------------------------------------------------------------- #
# Race terms — everything the corpus can see about one race, and nothing it
# cannot (no handicap flag, no going, no race name).
# --------------------------------------------------------------------------- #

def race_terms(rows_of_one_race) -> dict:
    """The corpus-visible fingerprint of one race (a list of school.mine.Runner,
    or anything with the same .sp/.pos/.rclass/.rtype/.course attributes)."""
    rows = list(rows_of_one_race)
    priced = sorted((r for r in rows if r.sp > 1.0), key=lambda r: r.sp)
    field_size = len(priced)
    top3 = priced[:3]
    concentration = sum(1.0 / r.sp for r in top3) if top3 else 0.0
    rclass = rows[0].rclass if rows else 0
    code = rows[0].rtype if rows else ""
    course = (rows[0].course or "") if rows else ""
    is_aw = any(name in course.lower() for name in AW_COURSES)
    fav_sp = priced[0].sp if priced else None
    winner = next((r for r in priced if r.pos == "1"), None)
    winner_rank = priced.index(winner) + 1 if winner is not None else None
    return {
        "field_size": field_size,
        "concentration": concentration,
        "class": rclass if rclass else None,   # unclassed (0) -> None
        "code": code,
        "is_aw": is_aw,
        "fav_sp": fav_sp,
        "winner_rank": winner_rank,
        "front3_pos": tuple(r.pos for r in top3),
    }


def bar_score(terms: dict, shape_verdict: str | None = None) -> int:
    """The race-quality fingerprint, replayed on corpus-visible terms only —
    `is_handicap` is always False (unknown), never a live racecard read."""
    return race_quality_score(
        is_handicap=False,
        concentration=terms["concentration"],
        race_class=terms["class"],
        race_type=_RACE_TYPE_NAME.get(terms["code"], terms["code"] or ""),
        field_size=terms["field_size"],
        n_race_flags=0,
        is_aw=terms["is_aw"],
        hollow=False,
        shape_verdict=shape_verdict,
    )


# --------------------------------------------------------------------------- #
# Leak-safe cumulative shape-book cells (school.shapebook.build() rebuilt to
# take races already in memory, not a corpus path, so it can be replayed
# month-by-month instead of once on the whole file).
# --------------------------------------------------------------------------- #

def _new_cell() -> dict:
    return {"n": 0, "fav": 0, "r2": 0, "r3": 0, "out": 0, "no_win": 0, "win_sps": []}


def _accumulate_cell(cells: dict, race) -> None:
    priced = sorted((r for r in race if r.sp > 1.0), key=lambda r: r.sp)
    if len(priced) < 2:
        return
    winner = next((r for r in priced if r.pos == "1"), None)
    key = (priced[0].rtype, _class_band(priced[0].rclass),
           _field_band(len(priced)), _fav_band(priced[0].sp))
    c = cells[key]
    c["n"] += 1
    if winner is None:            # winner unpriced/void — count the race,
        c["no_win"] += 1          # never guess the rank
        return
    rank = priced.index(winner) + 1
    if rank == 1:
        c["fav"] += 1
    elif rank == 2:
        c["r2"] += 1
    elif rank == 3:
        c["r3"] += 1
    else:
        c["out"] += 1
    c["win_sps"].append(winner.sp)


def _shape_verdict_for(terms: dict, cells_snapshot: dict) -> str | None:
    if terms["fav_sp"] is None:
        return None
    key = (terms["code"], _class_band(terms["class"] or 0),
           _field_band(terms["field_size"]), _fav_band(terms["fav_sp"]))
    cell = cells_snapshot.get(key)
    return shape_triage(cell) if cell is not None else None


# --------------------------------------------------------------------------- #
# The backtest
# --------------------------------------------------------------------------- #

def _stats(rows: list) -> dict:
    """Fav strike/ROI, top-3 coverage, 2nd/3rd-fav strike, mean field — over
    one bucket of {"terms": ...} rows. None where the sample can't answer."""
    n = len(rows)
    if n == 0:
        return {"n": 0, "n_fav": 0, "fav_strike": None, "fav_roi": None,
                "top3_cov": None, "n_top3": 0, "fav2_strike": None,
                "n_fav2": 0, "fav3_strike": None, "n_fav3": 0, "mean_field": None}
    has_fav = [r for r in rows if r["terms"]["fav_sp"] is not None]
    n_fav = len(has_fav)
    fav_wins = sum(1 for r in has_fav if r["terms"]["front3_pos"][0] == "1")
    fav_ret = sum(r["terms"]["fav_sp"] for r in has_fav
                  if r["terms"]["front3_pos"][0] == "1")
    has_rank = [r for r in rows if r["terms"]["winner_rank"] is not None]
    n_top3 = len(has_rank)
    top3_hits = sum(1 for r in has_rank if r["terms"]["winner_rank"] <= 3)
    has_2nd = [r for r in rows if len(r["terms"]["front3_pos"]) > 1]
    n_fav2 = len(has_2nd)
    fav2_wins = sum(1 for r in has_2nd if r["terms"]["front3_pos"][1] == "1")
    has_3rd = [r for r in rows if len(r["terms"]["front3_pos"]) > 2]
    n_fav3 = len(has_3rd)
    fav3_wins = sum(1 for r in has_3rd if r["terms"]["front3_pos"][2] == "1")
    return {
        "n": n,
        "n_fav": n_fav,
        "fav_strike": 100.0 * fav_wins / n_fav if n_fav else None,
        "fav_roi": 100.0 * (fav_ret - n_fav) / n_fav if n_fav else None,
        "top3_cov": 100.0 * top3_hits / n_top3 if n_top3 else None,
        "n_top3": n_top3,
        "fav2_strike": 100.0 * fav2_wins / n_fav2 if n_fav2 else None,
        "n_fav2": n_fav2,
        "fav3_strike": 100.0 * fav3_wins / n_fav3 if n_fav3 else None,
        "n_fav3": n_fav3,
        "mean_field": sum(r["terms"]["field_size"] for r in rows) / n,
    }


def backtest(races: list) -> dict:
    """races: list of races, each a list of school.mine.Runner rows (one
    race day's worth, as school.mine.load_corpus returns). Buckets every
    race above/below BETTING_BAR, per month, plus a score-band view."""
    races_sorted = sorted(races, key=lambda rs: (rs[0].date, rs[0].race_id)) if races else []
    by_month: dict[str, list] = defaultdict(list)
    for race in races_sorted:
        by_month[race[0].date[:7]].append(race)
    months_order = sorted(by_month)

    running_cells: dict = defaultdict(_new_cell)
    per_race: list[dict] = []
    for month in months_order:
        # LEAK GUARD: only cells built from months strictly before this one,
        # and only ones that already hold n>=30 races, ever get to vote.
        snapshot = {k: v for k, v in running_cells.items() if v["n"] >= MIN_CELL_N}
        for race in by_month[month]:
            terms = race_terms(race)
            verdict = _shape_verdict_for(terms, snapshot)
            score = bar_score(terms, verdict)
            per_race.append({"month": month, "score": score, "terms": terms})
        for race in by_month[month]:               # NOW this month joins history
            _accumulate_cell(running_cells, race)

    above = [r for r in per_race if r["score"] >= BETTING_BAR]
    below = [r for r in per_race if r["score"] < BETTING_BAR]

    def month_table(rows: list) -> dict:
        by_m: dict[str, list] = defaultdict(list)
        for r in rows:
            by_m[r["month"]].append(r)
        out = {m: _stats(rs) for m, rs in sorted(by_m.items())}
        out["ALL"] = _stats(rows)
        return out

    bands: dict[str, list] = {"<=0": [], "1": [], "2": [], "3+": []}
    for r in per_race:
        s = r["score"]
        key = "<=0" if s <= 0 else ("1" if s == 1 else ("2" if s == 2 else "3+"))
        bands[key].append(r)

    return {
        "n_races": len(per_race),
        "above": month_table(above),
        "below": month_table(below),
        "bands": {k: _stats(v) for k, v in bands.items()},
    }


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

def _fmt(x, spec: str = "{:.1f}") -> str:
    return "-" if x is None else spec.format(x)


def _emit_table(w, month_dict: dict) -> None:
    w("month | n | fav strike% | fav ROI% | top-3 coverage% | "
      "2nd-fav strike% | 3rd-fav strike% | mean field")
    w("--- | --- | --- | --- | --- | --- | --- | ---")
    for m in [k for k in month_dict if k != "ALL"] + ["ALL"]:
        s = month_dict[m]
        w(f"{m} | {s['n']} | {_fmt(s['fav_strike'])} | "
          f"{_fmt(s['fav_roi'], '{:+.1f}')} | {_fmt(s['top3_cov'])} | "
          f"{_fmt(s['fav2_strike'])} | {_fmt(s['fav3_strike'])} | "
          f"{_fmt(s['mean_field'])}")
    w("")


def _verdict_paragraph(result: dict) -> str:
    a = result["above"]["ALL"]
    b = result["below"]["ALL"]
    bands = result["bands"]
    band_line = ", ".join(
        f"{name} (n={bands[name]['n']}) top-3 {_fmt(bands[name]['top3_cov'])}%, "
        f"fav strike {_fmt(bands[name]['fav_strike'])}%"
        for name in ("<=0", "1", "2", "3+"))
    return (
        f"Above the bar (n={a['n']}) the favourite struck {_fmt(a['fav_strike'])}% "
        f"at {_fmt(a['fav_roi'], '{:+.1f}')}% ROI, the winner sat in the front "
        f"three {_fmt(a['top3_cov'])}% of the time (n={a['n_top3']} races with a "
        f"ranked winner), and the 2nd/3rd favourite struck "
        f"{_fmt(a['fav2_strike'])}%/{_fmt(a['fav3_strike'])}%. Below the bar "
        f"(n={b['n']}) those same reads were fav strike {_fmt(b['fav_strike'])}%, "
        f"fav ROI {_fmt(b['fav_roi'], '{:+.1f}')}%, top-3 coverage "
        f"{_fmt(b['top3_cov'])}%. By score band: {band_line}. These are "
        "observations off the resulted record under the stated corpus limits "
        "(no handicap flag, settled SP not the 07:30 price, shape votes "
        "leak-guarded month by month) — no new rule is proposed here; the "
        "numbers are for the master to read against the bar at "
        f"{BETTING_BAR}."
    )


def render(result: dict) -> str:
    lines: list[str] = []
    w = lines.append
    w("# THE BAR BACKTEST — race selection judged on the resulted record")
    w("")
    w(f"No API calls, no model: every resulted race in the corpus is scored "
      f"exactly as `pipeline.nap.race_quality_score` would score it, then "
      f"bucketed against BETTING_BAR = {BETTING_BAR}. This asks, off the "
      "settled record alone, whether races that clear the bar read more "
      "honestly than races that do not.")
    w("")
    w("**Terms and limits — read before the tables:**")
    w("- The corpus carries no handicap flag, no going, no race name. "
      "`is_handicap` is scored as False/unknown for EVERY race here, which "
      "UNDER-SCORES every honest handicap by 1 versus a live read (the live "
      "pipeline reads the racecard's real flag) — every score below is "
      "biased down by up to 1 relative to a live nap.")
    w("- SP is the corpus's SETTLED starting price, not the 07:30 consensus "
      "price the live shape-book glance uses.")
    w("- The shape-book vote is replayed leak-safely: cells are rebuilt "
      "cumulatively month by month, and a race is glanced only against "
      f"cells built from races strictly BEFORE its own month, only once "
      f"that cell holds n>={MIN_CELL_N} — otherwise no vote at all. This is "
      "stricter than shapebook.build(), which is built once on the whole "
      "corpus including the race it then judges.")
    w("")
    w(f"Races scored: **{result['n_races']}**")
    w("")
    w(f"## Above the bar (score >= {BETTING_BAR})")
    _emit_table(w, result["above"])
    w(f"## Below the bar (score < {BETTING_BAR})")
    _emit_table(w, result["below"])
    w("## Score bands — does readability actually turn at the bar?")
    w("band | n | fav strike% | fav ROI% | top-3 coverage% | "
      "2nd-fav strike% | 3rd-fav strike% | mean field")
    w("--- | --- | --- | --- | --- | --- | --- | ---")
    for band in ("<=0", "1", "2", "3+"):
        s = result["bands"][band]
        w(f"{band} | {s['n']} | {_fmt(s['fav_strike'])} | "
          f"{_fmt(s['fav_roi'], '{:+.1f}')} | {_fmt(s['top3_cov'])} | "
          f"{_fmt(s['fav2_strike'])} | {_fmt(s['fav3_strike'])} | "
          f"{_fmt(s['mean_field'])}")
    w("")
    w("## What this says")
    w(_verdict_paragraph(result))
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/school/raw")
    ap.add_argument("--out", default="data/school/bar_backtest.md")
    a = ap.parse_args(argv)
    races = load_corpus(Path(a.raw))
    result = backtest(races)
    text = render(result)
    out = Path(a.out)
    out.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
