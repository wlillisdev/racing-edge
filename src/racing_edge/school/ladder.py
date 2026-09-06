"""THE EVOLUTION LAW — if it's failing, change tack. Automatically.

The master, 2026-08-15: 'we need a system that if its failing, we evolve
change tack, no point in repeating something that is not working, i am at
this 3 months and so far have achieved nothing spent thousands on claude.'

The ladder reads the daily grind (data/school/daily_policy.csv — every
policy graded on every race, every day) and rules with the master's own
bars, no new thresholds invented:
  - judge nothing under 50 picks (his law 2);
  - a regime is judged over a rolling window of up to 500 graded picks
    (his law 1's graduation bar, applied in reverse as the demotion bar).

Verdicts:
  CHANGE TACK  — the champion policy is running below the SP-favourite
                 benchmark over its window (repeating what is not working),
                 and the best qualifying challenger is named; or the
                 champion trails a challenger that beats the benchmark.
  HOLD         — the champion beats the benchmark and no challenger beats
                 the champion.
  NO VERDICT   — under 50 graded picks for the champion; say so, decide
                 nothing (his law: 8-10 straight losses are arithmetic).

This is the gym ladder: it moves POLICIES. Promotion into live selections
still rings the master's doorbell — evolution proposes, the master
disposes. Wire the verdict line into health so a CHANGE TACK is impossible
to miss.

Usage: PYTHONPATH=src python -m racing_edge.school.ladder
         --champion cell:mr1+ltowin [--csv data/school/daily_policy.csv]
         [--window 500]
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

MIN_JUDGE = 50      # the master: judge nothing on fewer than 50 picks
WINDOW = 500        # the master: 500+ unseen races is the graduation bar
SHADOW_PREFIX = "shadow:"   # THE SHADOW LADDER (the master, 2026-09-05: "we have
                            # 50 races a day... do all the testing on the
                            # shadow"): variant rank keys graded nightly off the
                            # banked yardstick rows. Namespaced because they are
                            # MEASURED, never CROWNED — a shadow policy never
                            # enters the verdict as a challenger; promotion is a
                            # doorbell decision, always.


def load_rows(csv_path: Path):
    """-> {policy: [(day, picks, wins, returned), ...] sorted by day}"""
    rows = defaultdict(list)
    if not csv_path.exists():
        return rows
    with open(csv_path, newline="") as fh:
        rd = csv.DictReader(fh)
        for r in rd:
            rows[r["policy"]].append(
                (r["day"], int(r["picks"]), int(r["wins"]),
                 float(r["returned"])))
    for p in rows:
        rows[p].sort()
    return rows


def nap_policy_rows(history) -> list[tuple]:
    """THE NAP COLUMN AS THE LADDER'S CHAMPION (the master, 2026-09-02 21:05,
    on the first honest ladder read — engine opinions 19% v the jolly 30%:
    "best horse wins; we read the form; we pick winners — that is what we
    measure"). Every SETTLED real pick (won 0/1) is one graded pick at SP;
    passes and voids are positions, not picks, and carry no row."""
    from racing_edge.study.naplog import version
    out = []
    for r in history:
        if r.get("won") not in (0, 1):
            continue
        won = int(r["won"])
        ret = float(r.get("sp_dec") or 0.0) if won else 0.0
        out.append((r["date"], "nap", 1, won, ret))
        if version(r["date"]) == "v2":
            # THE NEW BEAST on its own ladder line (the master, 2026-09-02)
            out.append((r["date"], "nap-v2", 1, won, ret))
    return out


def last_day(rows, policy: str) -> str:
    """The most recent day a policy was graded ('' if never) — the ladder's
    freshness, so a silent night school is a named fault not a red verdict."""
    dr = rows.get(policy) or []
    return max(d for d, _p, _w, _r in dr) if dr else ""


def window_stats(day_rows, window: int = WINDOW):
    """Rolling window of the most recent days totalling <= window picks
    (whole days — the day is the school's unit)."""
    n = wins = 0
    ret = 0.0
    for day, picks, w, r in reversed(day_rows):
        if n + picks > window and n >= MIN_JUDGE:
            break
        n += picks
        wins += w
        ret += r
    roi = 100.0 * (ret - n) / n if n else 0.0
    strike = 100.0 * wins / n if n else 0.0
    return n, strike, roi


def verdict(rows, champion: str, window: int = WINDOW) -> str:
    if champion not in rows:
        return f"NO VERDICT — champion '{champion}' has no graded picks yet"
    cn, cs, croi = window_stats(rows[champion], window)
    if cn < MIN_JUDGE:
        return (f"NO VERDICT — champion {champion} has {cn} graded picks "
                f"(<{MIN_JUDGE}); losses at this size are arithmetic, "
                "not evidence")
    bn, bs, broi = window_stats(rows.get("fav", []), window)
    bench = f"fav n={bn} strike={bs:.1f}% ROI={broi:+.1f}%"
    if bn < MIN_JUDGE:
        # 2026-09-02, the box's 09:30 health: "CHANGE TACK ... vs fav n=0" —
        # a red verdict against an EMPTY benchmark. A thin benchmark judges
        # nothing; the fault is upstream (night school not grading the
        # corpus) and is named as such.
        return (f"NO VERDICT — favourite benchmark has {bn} graded picks "
                f"(<{MIN_JUDGE}): night school is not grading the corpus "
                f"(last fav day {last_day(rows, 'fav') or 'never'}) — "
                "check the night fetch before judging anyone")
    champ = f"{champion} n={cn} strike={cs:.1f}% ROI={croi:+.1f}%"

    challengers = []
    for p, dr in rows.items():
        if p in (champion, "fav") or p.startswith(SHADOW_PREFIX):
            continue
        n, s, roi = window_stats(dr, window)
        if n >= MIN_JUDGE and roi > broi and roi > croi:
            challengers.append((roi, s, n, p))
    challengers.sort(reverse=True)

    if croi <= broi:
        line = (f"CHANGE TACK — champion is not beating the favourite "
                f"benchmark over its window ({champ} vs {bench}).")
        if challengers:
            roi, s, n, p = challengers[0]
            line += (f" Best challenger: {p} n={n} strike={s:.1f}% "
                     f"ROI={roi:+.1f}% — ring the doorbell.")
        else:
            line += (" No challenger qualifies yet — widen the policy "
                     "menu; do NOT keep repeating the champion unchanged.")
        return line
    if challengers:
        roi, s, n, p = challengers[0]
        return (f"CHANGE TACK — challenger {p} (n={n} strike={s:.1f}% "
                f"ROI={roi:+.1f}%) beats both champion ({champ}) and "
                f"benchmark ({bench}) — ring the doorbell.")
    return f"HOLD — {champ} beats {bench}; no challenger qualifies."


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--champion", required=True)
    ap.add_argument("--csv", default="data/school/daily_policy.csv")
    ap.add_argument("--window", type=int, default=WINDOW)
    a = ap.parse_args(argv)
    print(verdict(load_rows(Path(a.csv)), a.champion, a.window))
    return 0


if __name__ == "__main__":
    sys.exit(main())
