"""PHASE 1 — THE MINE (master's method, 2026-08-15; amended 2026-08-16).

Backtest every stored historical result, leakage-guarded: every feature is
computed from runs strictly BEFORE the race date. The original 5,000-race
corpus floor is GONE (the master, 2026-08-16: '5000 is gone, we need to be
agile, if we consistently see something not working we cant wait 5000
races to fix it') — the mine reports at whatever sample exists, always
with n attached, and consistent failure is acted on at the 50-pick bar. Test features alone and in
pairs; report n / strike% / ROI at SP per cell; split promising cells BY
MONTH — a cell whose ROI sign flips month to month is noise and is discarded.
The single most stable positive-ROI cell with n>=800 becomes THE RULE.

Corpus: data/school/raw/YYYY-MM-DD.csv, one line per runner:
date,race_id,course,region,type,class,dist,horse_id,sp,pos,btn,jockey_id,trainer_id

Usage: PYTHONPATH=src python -m racing_edge.school.mine [--raw DIR]
       [--score-from 2026-03-01] [--report PATH]
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date as _date
from pathlib import Path

RAW_DIR = Path("data/school/raw")
SCORE_FROM = "2026-03-01"   # warm-up before this date feeds features only
MIN_REPORT_N = 500          # recommend nothing under this (master's law)
MIN_RULE_N = 800            # THE RULE needs at least this
STRIKE_WINDOW_DAYS = 90     # jockey/trainer strike window (disclosed choice)
STRIKE_MIN_RUNS = 10        # a strike% on fewer runs than this is unknown


def _won(pos: str) -> bool:
    return pos == "1"


class Runner:
    __slots__ = ("date", "race_id", "course", "region", "rtype", "rclass",
                 "dist", "horse", "sp", "pos", "btn", "jockey", "trainer",
                 "month", "feats")

    def __init__(self, row):
        self.date = row[0]
        self.race_id = row[1]
        self.course = row[2]
        self.region = row[3]
        self.rtype = row[4]
        # agents sometimes leave "Class 6" unstripped — take the digits
        cls_digits = "".join(ch for ch in row[5] if ch.isdigit())
        self.rclass = int(cls_digits or 0)
        self.dist = float(row[6] or 0)
        self.horse = row[7]
        try:
            self.sp = float(row[8])
        except ValueError:
            self.sp = 0.0
        self.pos = row[9]
        try:
            self.btn = float(row[10])
        except ValueError:
            self.btn = -1.0  # unknown margin
        self.jockey = row[11]
        self.trainer = row[12]
        self.month = self.date[:7]
        self.feats = []


def load_corpus(raw_dir: Path) -> list[list[Runner]]:
    """All races, sorted by date; each race a list of Runners."""
    by_race: dict[str, list[Runner]] = defaultdict(list)
    for f in sorted(raw_dir.glob("*.csv")):
        with open(f, newline="") as fh:
            for row in csv.reader(fh):
                if len(row) != 13:
                    continue
                by_race[row[1]].append(Runner(row))
    races = sorted(by_race.values(), key=lambda rs: (rs[0].date, rs[0].race_id))
    return races


class Tally:
    """Rolling per-key (date, won) record so strike% uses only prior days."""

    def __init__(self):
        self.runs: dict[str, list[tuple[str, bool]]] = defaultdict(list)

    def add(self, key: str, day: str, won: bool):
        self.runs[key].append((day, won))

    def strike(self, key: str, before: str, window_days: int) -> float | None:
        """Strike % over runs in [before - window, before). None if too few."""
        lo = _shift(before, -window_days)
        rows = [w for (d, w) in self.runs.get(key, ()) if lo <= d < before]
        if len(rows) < STRIKE_MIN_RUNS:
            return None
        return 100.0 * sum(rows) / len(rows)


def _shift(iso: str, days: int) -> str:
    from datetime import timedelta
    y, m, d = map(int, iso.split("-"))
    return (_date(y, m, d) + timedelta(days=days)).isoformat()


def _days_between(a: str, b: str) -> int:
    ya, ma, da = map(int, a.split("-"))
    yb, mb, db = map(int, b.split("-"))
    return (_date(yb, mb, db) - _date(ya, ma, da)).days


# ---------------------------------------------------------------------------
# Feature extraction — the only place leakage could enter. Every source below
# is a structure built exclusively from races dated BEFORE r.date (the corpus
# walk adds a race to history only after the whole race day is featurised).
# ---------------------------------------------------------------------------

def featurise(races: list[list[Runner]], score_from: str) -> list[Runner]:
    horse_hist: dict[str, list[dict]] = defaultdict(list)
    jky, trn = Tally(), Tally()
    scored: list[Runner] = []

    i = 0
    n = len(races)
    while i < n:
        day = races[i][0].date
        todays = []
        while i < n and races[i][0].date == day:
            todays.append(races[i])
            i += 1

        for race in todays:
            # market rank: 1 = favourite; ties broken by horse id for
            # determinism (joint favourites both being "rank 1" would let one
            # race put two horses in the fav cell).
            ranked = sorted((r for r in race if r.sp > 0),
                            key=lambda r: (r.sp, r.horse))
            rank_of = {r.horse: k + 1 for k, r in enumerate(ranked)}

            for r in race:
                if r.date < score_from or r.sp <= 0:
                    continue
                f = r.feats
                mr = rank_of.get(r.horse)
                if mr in (1, 2, 3):
                    f.append(f"mr{mr}")
                hist = horse_hist[r.horse]
                if hist:
                    last = hist[-1]
                    if last["won"]:
                        f.append("ltowin")
                    dsl = _days_between(last["date"], r.date)
                    f.append("dsl14" if dsl <= 14 else
                             "dsl30" if dsl <= 30 else "dsl31")
                    if r.rclass and last["rclass"]:
                        f.append("clsdrop" if r.rclass > last["rclass"] else
                                 "clsrise" if r.rclass < last["rclass"] else
                                 "clssame")
                    if any(h["won"] and h["course"] == r.course
                           and h["dist"] == r.dist for h in hist):
                        f.append("cdwin")
                    # tight2 — the Gower Prince nuance (self-study
                    # 2026-08-15, PROPOSED, testing only): last two runs
                    # both runner-up with the margin tightening — a
                    # progressive finisher, not a stale placer.
                    if len(hist) >= 2:
                        a, b = hist[-2], hist[-1]
                        if (a["pos"] == "2" and b["pos"] == "2"
                                and 0 <= b["btn"] < a["btn"]):
                            f.append("tight2")
                js = jky.strike(r.jockey, r.date, STRIKE_WINDOW_DAYS)
                if js is not None and js >= 15.0:
                    f.append("jky15")
                ts = trn.strike(r.trainer, r.date, STRIKE_WINDOW_DAYS)
                if ts is not None and ts >= 15.0:
                    f.append("trn15")
                f.append("p20" if r.sp <= 2.0 else
                         "p35" if r.sp <= 3.5 else
                         "p60" if r.sp <= 6.0 else
                         "p110" if r.sp <= 11.0 else "p11plus")
                scored.append(r)

        # only now does today enter history — nothing same-day leaks
        for race in todays:
            for r in race:
                won = _won(r.pos)
                horse_hist[r.horse].append(
                    {"date": r.date, "course": r.course, "dist": r.dist,
                     "rclass": r.rclass, "won": won, "pos": r.pos,
                     "btn": r.btn})
                if r.jockey != "0":
                    jky.add(r.jockey, r.date, won)
                if r.trainer != "0":
                    trn.add(r.trainer, r.date, won)
    return scored


# ---------------------------------------------------------------------------
# Cells
# ---------------------------------------------------------------------------

FAMILY = {  # a pair must cross families or it is the same fact twice
    "mr1": "mr", "mr2": "mr", "mr3": "mr",
    "ltowin": "lto", "tight2": "t2",
    "dsl14": "dsl", "dsl30": "dsl", "dsl31": "dsl",
    "cdwin": "cd", "jky15": "jky", "trn15": "trn",
    "clsdrop": "cls", "clsrise": "cls", "clssame": "cls",
    "p20": "p", "p35": "p", "p60": "p", "p110": "p", "p11plus": "p",
}


class Cell:
    __slots__ = ("n", "wins", "ret", "months")

    def __init__(self):
        self.n = 0
        self.wins = 0
        self.ret = 0.0
        self.months: dict[str, list[float]] = defaultdict(lambda: [0, 0, 0.0])

    def add(self, r: Runner):
        won = _won(r.pos)
        self.n += 1
        self.wins += won
        self.ret += r.sp if won else 0.0
        m = self.months[r.month]
        m[0] += 1
        m[1] += won
        m[2] += r.sp if won else 0.0

    @property
    def strike(self):
        return 100.0 * self.wins / self.n if self.n else 0.0

    @property
    def roi(self):
        return 100.0 * (self.ret - self.n) / self.n if self.n else 0.0

    def month_rois(self):
        return {m: 100.0 * (v[2] - v[0]) / v[0]
                for m, v in sorted(self.months.items()) if v[0] > 0}

    def stable(self) -> bool:
        """Positive ROI in EVERY month — the master's noise test."""
        rois = self.month_rois()
        return bool(rois) and all(v > 0 for v in rois.values())

    def min_month_roi(self):
        rois = self.month_rois()
        return min(rois.values()) if rois else float("-inf")


def scan(scored: list[Runner]):
    singles: dict[str, Cell] = defaultdict(Cell)
    pairs: dict[str, Cell] = defaultdict(Cell)
    fav_bench = Cell()
    for r in scored:
        fs = r.feats
        if "mr1" in fs:
            fav_bench.add(r)
        for a in fs:
            singles[a].add(r)
        for x in range(len(fs)):
            for y in range(x + 1, len(fs)):
                a, b = sorted((fs[x], fs[y]))
                if FAMILY[a] != FAMILY[b]:
                    pairs[f"{a}+{b}"].add(r)
    return singles, pairs, fav_bench


def report(raw_dir: Path, score_from: str, out: Path | None):
    races = load_corpus(raw_dir)
    n_races = len(races)
    n_scored_races = len({r[0].race_id for r in races if r[0].date >= score_from})
    scored = featurise(races, score_from)
    singles, pairs, fav = scan(scored)

    lines = []
    w = lines.append
    w(f"# THE MINE — {n_races} races loaded, {n_scored_races} scored "
      f"(from {score_from}), {len(scored)} runner rows")
    w("")
    w(f"SP-favourite benchmark: n={fav.n} strike={fav.strike:.1f}% "
      f"ROI={fav.roi:+.1f}%")
    w("")

    def block(title, cells, min_n):
        w(f"## {title}")
        w("cell | n | strike% | ROI% | monthly ROI | stable")
        w("---- | - | ------- | ---- | ----------- | ------")
        for name, c in sorted(cells.items(), key=lambda kv: -kv[1].roi):
            if c.n < min_n:
                continue
            mo = " ".join(f"{m[5:]}:{v:+.0f}" for m, v in c.month_rois().items())
            w(f"{name} | {c.n} | {c.strike:.1f} | {c.roi:+.1f} | {mo} | "
              f"{'YES' if c.stable() else 'no'}")
        w("")

    block("Singles (n>=500 shown)", singles, MIN_REPORT_N)
    block("Pairs (n>=500 shown)", pairs, MIN_REPORT_N)

    candidates = [(k, c) for k, c in {**singles, **pairs}.items()
                  if c.n >= MIN_RULE_N and c.roi > 0 and c.stable()]
    w("## THE RULE candidate (stable positive ROI, n>=800)")
    if candidates:
        candidates.sort(key=lambda kv: -kv[1].min_month_roi())
        for k, c in candidates[:5]:
            w(f"- {k}: n={c.n} strike={c.strike:.1f}% ROI={c.roi:+.1f}% "
              f"worst month {c.min_month_roi():+.1f}%")
        w(f"\nTHE RULE: **{candidates[0][0]}**")
    else:
        w("- NONE survived (positive every month at n>=800). "
          "Single signals are market-priced; that is the expected result, "
          "not a failure of the mine.")
    text = "\n".join(lines)
    if out:
        out.write_text(text)
    print(text)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(RAW_DIR))
    ap.add_argument("--score-from", default=SCORE_FROM)
    ap.add_argument("--report", default="data/school/mine_report.md")
    a = ap.parse_args(argv)
    report(Path(a.raw), a.score_from, Path(a.report) if a.report else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
