"""THE DAILY GRIND — grade mechanical policies on EVERY race, every day.

The master, 2026-08-15: 'as a system we need to progress and not stagnate,
we have enough data and power every day to accelerate the learning and
honing of the system which we don't use, we keep saying wait 50 races to
see, there are 50 races every day.'

So: one pick per race across the WHOLE card, mechanically, for free — not
one nap a day. The graduation bars (beat the SP-fav over 500+ unseen races;
judge nothing under 50 picks) fill in days, not months. This grades
POLICIES, not the banked ledger — staking is still judged only on the
record in nap.db.

Policies:
  fav          — take the SP favourite (the benchmark itself)
  cell:<name>  — take the runner matching a mine cell, e.g. cell:ltowin+mr1
                 (pair = both features; single = that feature). Skips races
                 with no matching runner; ties broken by shortest SP.

Usage: PYTHONPATH=src python -m racing_edge.school.daily
         --from 2026-03-01 --to 2026-08-14 --policy fav --policy cell:mr1+ltowin
         [--raw data/school/raw] [--csv data/school/daily_policy.csv]
Appends one line per day per policy to the CSV and prints the rollup.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

from racing_edge.school.mine import Runner, featurise, load_corpus


def pick_for(policy: str, race: list[Runner]) -> Runner | None:
    if policy == "fav":
        cands = [r for r in race if "mr1" in r.feats]
    elif policy == "shape:crowdfav":
        # TRIAL (taught 2026-08-16, Southwell 1:30): in a big field whose
        # favourite has been crunched to a price the race shape can't
        # justify, take the firm mid-price horse instead. Corpus proxy
        # (no movement data at SP): 10+ runners, fav SP <= 2.5 -> shortest
        # runner in the 5.0-10.0 band. A school policy on trial, not a rule.
        if len(race) < 10:
            return None
        fav = min((r for r in race if r.sp > 0), key=lambda r: (r.sp, r.horse),
                  default=None)
        if fav is None or fav.sp > 2.5:
            return None
        cands = [r for r in race if 5.0 <= r.sp <= 10.0]
    else:
        want = set(policy.split(":", 1)[1].split("+"))
        cands = [r for r in race if want <= set(r.feats)]
    if not cands:
        return None
    return min(cands, key=lambda r: (r.sp, r.horse))


def grade(races_by_day: dict[str, list[list[Runner]]], policies: list[str]):
    """-> {policy: {day: [picks, wins, returned]}} over 5+ runner races."""
    out: dict[str, dict[str, list[float]]] = {
        p: defaultdict(lambda: [0, 0, 0.0]) for p in policies}
    for day, races in races_by_day.items():
        for race in races:
            if len(race) < 5:
                continue
            for p in policies:
                r = pick_for(p, race)
                if r is None:
                    continue
                row = out[p][day]
                row[0] += 1
                if r.pos == "1":
                    row[1] += 1
                    row[2] += r.sp
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--to", dest="to", required=True)
    ap.add_argument("--policy", action="append", default=None)
    ap.add_argument("--raw", default="data/school/raw")
    ap.add_argument("--csv", default="data/school/daily_policy.csv")
    a = ap.parse_args(argv)
    policies = a.policy or ["fav"]

    races = load_corpus(Path(a.raw))
    scored = featurise(races, a.frm)
    by_race: dict[str, list[Runner]] = defaultdict(list)
    for r in scored:
        if a.frm <= r.date <= a.to:
            by_race[r.race_id].append(r)
    by_day: dict[str, list[list[Runner]]] = defaultdict(list)
    for rs in by_race.values():
        by_day[rs[0].date].append(rs)

    graded = grade(by_day, policies)
    csv_path = Path(a.csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    new = not csv_path.exists()
    with open(csv_path, "a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["day", "policy", "picks", "wins", "returned"])
        for p in policies:
            for day in sorted(graded[p]):
                n, wins, ret = graded[p][day]
                w.writerow([day, p, n, wins, f"{ret:.2f}"])

    print(f"days graded: {len(by_day)}  races (5+ runners): "
          f"{sum(len(v) for v in by_day.values())}")
    for p in policies:
        n = sum(v[0] for v in graded[p].values())
        wins = sum(v[1] for v in graded[p].values())
        ret = sum(v[2] for v in graded[p].values())
        if n:
            print(f"{p}: picks={n} strike={100.0 * wins / n:.1f}% "
                  f"ROI={100.0 * (ret - n) / n:+.1f}%")
        else:
            print(f"{p}: picks=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
