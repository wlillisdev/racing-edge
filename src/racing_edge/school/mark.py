"""PHASE 2 Step C — MARK: score an exam sitting. Numbers only.

Strike + ROI at SP overall, by confidence band, and versus the SP-favourite
benchmark on the same races (the pass mark). Every miss categorised:
  (a) fav won, we got clever   (picked non-fav, favourite won)
  (b) took the fav, fav lost
  (c) winner unconsidered      (picked non-fav, favourite lost too)
Plus the with-fav v against-fav split.

picks CSV: race_id,horse_id,confidence,dots
key   CSV: race_id,winner_horse,winner_sp,fav_horse   (from pack.py)

Usage: PYTHONPATH=src python -m racing_edge.school.mark
       --picks data/school/picks/DAY.csv --key data/school/keys/DAY.csv
       [--raw data/school/raw]
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from racing_edge.school.mine import load_corpus


class Bucket:
    def __init__(self):
        self.n = 0
        self.wins = 0
        self.ret = 0.0

    def add(self, won: bool, sp: float):
        self.n += 1
        self.wins += won
        self.ret += sp if won else 0.0

    def line(self):
        if not self.n:
            return "n=0"
        return (f"n={self.n} strike={100.0 * self.wins / self.n:.1f}% "
                f"ROI={100.0 * (self.ret - self.n) / self.n:+.1f}%")


def mark(picks_file: Path, key_file: Path, raw: Path) -> str:
    with open(key_file, newline="") as fh:
        key = {r[0]: {"winner": r[1], "winner_sp": float(r[2] or 0),
                      "fav": r[3]} for r in csv.reader(fh)}
    sp_of: dict[tuple[str, str], float] = {}
    for race in load_corpus(raw):
        for r in race:
            sp_of[(r.race_id, r.horse)] = r.sp

    overall, bench = Bucket(), Bucket()
    with_fav, against_fav = Bucket(), Bucket()
    by_conf = {c: Bucket() for c in "12345"}
    miss = {"a": 0, "b": 0, "c": 0}
    unmatched = []

    with open(picks_file, newline="") as fh:
        rows = [r for r in csv.reader(fh) if r and len(r) >= 3]
    for race_id, pick, conf, *_ in rows:
        k = key.get(race_id)
        if k is None:
            unmatched.append(race_id)
            continue
        sp = sp_of.get((race_id, pick), 0.0)
        won = pick == k["winner"]
        overall.add(won, sp)
        by_conf.setdefault(conf, Bucket()).add(won, sp)
        fav_sp = sp_of.get((race_id, k["fav"]), 0.0)
        bench.add(k["fav"] == k["winner"], fav_sp)
        (with_fav if pick == k["fav"] else against_fav).add(won, sp)
        if not won:
            if k["fav"] == k["winner"]:
                miss["a"] += 1
            elif pick == k["fav"]:
                miss["b"] += 1
            else:
                miss["c"] += 1

    out = [
        f"OVERALL   {overall.line()}",
        f"BENCHMARK (SP fav, same races) {bench.line()}",
        f"PASS MARK: {'BEAT' if overall.ret - overall.n > bench.ret - bench.n else 'DID NOT BEAT'} the favourite benchmark on ROI"
        f" ({'BEAT' if overall.wins > bench.wins else 'DID NOT BEAT'} on strike)",
        "",
        "By confidence:",
    ]
    for c in sorted(by_conf):
        if by_conf[c].n:
            out.append(f"  conf {c}: {by_conf[c].line()}")
    out += [
        "",
        f"With fav:    {with_fav.line()}",
        f"Against fav: {against_fav.line()}",
        "",
        f"Misses: (a) fav won, got clever = {miss['a']}   "
        f"(b) took fav, fav lost = {miss['b']}   "
        f"(c) winner unconsidered = {miss['c']}",
    ]
    if unmatched:
        out.append(f"UNMATCHED race_ids (not in key): {', '.join(unmatched)}")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--picks", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--raw", default="data/school/raw")
    a = ap.parse_args(argv)
    print(mark(Path(a.picks), Path(a.key), Path(a.raw)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
