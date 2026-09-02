"""TIER-0 — every runner, every resulted race, scored against the market. Free.

The master (audit 2026-09-02): "If the system only scores its own picks, add a
Tier-0 (free, scripted) pass that scores EVERY runner's finishing position in
EVERY resulted race against market rank and every pre-race trait the store can
see, for yesterday AND the trailing 14 days side by side, with the market as the
control. Nothing from it is carved until it passes the month test." And: "a lift
that dies when you control for market rank is the market's, not the form's."

Data: the night-school corpus (data/school/raw/<day>.csv, one row per runner).
Traits: the mine's leakage-guarded features (school/mine.py:featurise) — the
store's own vocabulary, nothing invented here. Control: win% and place% by
market rank over the whole store. A trait's LIFT is its runners' actual win%
minus the win% their market ranks would predict — the market held constant.
The month test: lift > 0 in every month the store holds at the shape book's
own cell floor (30 runners a month) — the same rule as mine.Cell.stable,
applied to lift instead of ROI. Output: data/school/tier0.md, rewritten nightly.
A report, never a rule: the doorbell still rings before anything is carved.

Usage: PYTHONPATH=src python -m racing_edge.school.tier0 [--day YYYY-MM-DD]
           [--raw data/school/raw] [--out data/school/tier0.md]
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from racing_edge.school.mine import featurise, load_corpus

MIN_FIELD = 5                 # the daily grind's own floor (school/daily.py)
MONTH_MIN_N = 30              # the shape book's cell floor, reused — not a new bar
RANK_CAP = 7                  # ranks 7+ pooled: the tail is one shape, not seven
MARKET_FEATS = ("mr1", "mr2", "mr3", "p20", "p35", "p60", "p110", "p11plus")


def place_bar(field: int) -> int:
    """Standard place terms: 8+ runners pay three, 5-7 pay two, under 5 win only."""
    return 3 if field >= 8 else 2 if field >= 5 else 1


def rows_from(races_scored) -> list[dict]:
    """One row per priced runner in every 5+ runner race with a priced winner:
    market rank (ties by horse id, as the mine does), won, placed, traits."""
    by_race: dict[str, list] = defaultdict(list)
    for r in races_scored:
        by_race[r.race_id].append(r)
    out: list[dict] = []
    for rs in by_race.values():
        priced = sorted((r for r in rs if r.sp > 0), key=lambda r: (r.sp, r.horse))
        if len(priced) < MIN_FIELD or not any(r.pos == "1" for r in priced):
            continue          # void / abandoned / unpriced winner: counted nowhere
        bar = place_bar(len(priced))
        for k, r in enumerate(priced, 1):
            # "0" is the corpus's UNKNOWN position (fetch.py writes `or "0"`) —
            # it is not a placing (second audit 2026-09-02: 0 <= bar read as placed)
            pos = int(r.pos) if r.pos.isdigit() and int(r.pos) > 0 else None
            out.append({"date": r.date, "month": r.month, "rank": min(k, RANK_CAP),
                        "won": r.pos == "1",
                        "placed": pos is not None and pos <= bar,
                        "feats": [f for f in r.feats if f not in MARKET_FEATS]})
    return out


def control(rows: list[dict]) -> dict[int, tuple[int, int, int]]:
    """{rank: (n, wins, places)} — the market's own scoreboard."""
    t: dict[int, list[int]] = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        c = t[r["rank"]]
        c[0] += 1
        c[1] += r["won"]
        c[2] += r["placed"]
    return {k: tuple(v) for k, v in t.items()}


def traits(rows: list[dict], base: dict[int, tuple[int, int, int]]):
    """{feat: {"n", "wins", "exp", "months": {m: [n, wins, exp]}}} — exp is the
    wins the runners' market ranks predict (from the whole-store control)."""
    rate = {k: (v[1] / v[0] if v[0] else 0.0) for k, v in base.items()}
    t: dict[str, dict] = defaultdict(lambda: {"n": 0, "wins": 0, "exp": 0.0,
                                             "months": defaultdict(lambda: [0, 0, 0.0])})
    for r in rows:
        e = rate.get(r["rank"], 0.0)
        for f in r["feats"]:
            c = t[f]
            c["n"] += 1
            c["wins"] += r["won"]
            c["exp"] += e
            m = c["months"][r["month"]]
            m[0] += 1
            m[1] += r["won"]
            m[2] += e
    return t


def lift_pp(c: dict) -> float:
    return 100.0 * (c["wins"] - c["exp"]) / c["n"] if c["n"] else 0.0


def month_test(c: dict, min_n: int = MONTH_MIN_N) -> str:
    """HOLDS = lift > 0 in every month with min_n runners (and at least two such
    months); THIN = fewer than two qualifying months; FAILS otherwise."""
    ms = [(m, v) for m, v in c["months"].items() if v[0] >= min_n]
    if len(ms) < 2:
        return "THIN"
    return "HOLDS" if all(v[1] - v[2] > 0 for _, v in ms) else "FAILS"


def month_test_line(c: dict, min_n: int = MONTH_MIN_N) -> str:
    """The verdict WITH the lift over the months it was judged on (fourth audit
    2026-09-02, bot B3: a trait read HOLDS beside a NEGATIVE store lift, because
    the store column sums every month and the test reads only the 30+ months —
    two numbers, two populations, one glance). e.g. 'HOLDS · 2 mo · +1.4'."""
    verdict = month_test(c, min_n)
    ms = [v for v in c["months"].values() if v[0] >= min_n]
    n = sum(v[0] for v in ms)
    if not ms or not n:
        return verdict
    lift = 100.0 * (sum(v[1] for v in ms) - sum(v[2] for v in ms)) / n
    return f"{verdict} · {len(ms)} mo · {lift:+.1f}"


def render(day: str, rows_all: list[dict]) -> str:
    d0 = date.fromisoformat(day)
    w14 = (d0 - timedelta(days=13)).isoformat()
    yday = [r for r in rows_all if r["date"] == day]
    last14 = [r for r in rows_all if w14 <= r["date"] <= day]
    base = control(rows_all)
    L = [f"# TIER-0 — every runner v the market, {day} | trailing 14d | whole store",
         "",
         "(The master, 2026-09-02: score EVERY runner in EVERY resulted race against",
         "market rank and every trait the store can see, the market as the control;",
         "nothing is carved until it passes the month test. Lift = win% minus the",
         "win% the runners' market ranks predict — the market held constant. A report,",
         "not a rule; the doorbell rings before anything is carved.)", "",
         f"runners scored: yesterday {len(yday)} · 14d {len(last14)} · store {len(rows_all)}",
         "", "## THE CONTROL — win% / place% by market rank",
         "| rank | yesterday n · win% · place% | 14d n · win% · place% | store n · win% · place% |",
         "|---|---|---|---|"]

    def cell(c, k):
        n, w, p = c.get(k, (0, 0, 0))
        return f"{n} · {100 * w / n:.0f}% · {100 * p / n:.0f}%" if n else "-"

    cy, c14 = control(yday), control(last14)
    for k in sorted(base):
        lab = f"{k}" if k < RANK_CAP else f"{RANK_CAP}+"
        L.append(f"| {lab} | {cell(cy, k)} | {cell(c14, k)} | {cell(base, k)} |")
    L += ["", "## TRAITS — lift over the market (percentage points), month test on the store",
          "| trait | yesterday n · lift | 14d n · lift | store n · win% · lift | month test |",
          "|---|---|---|---|---|"]
    ty, t14, ts = traits(yday, base), traits(last14, base), traits(rows_all, base)

    def tcell(t, f):
        c = t.get(f)
        return f"{c['n']} · {lift_pp(c):+.1f}" if c and c["n"] else "-"

    for f in sorted(ts, key=lambda f: -ts[f]["n"]):
        c = ts[f]
        L.append(f"| {f} | {tcell(ty, f)} | {tcell(t14, f)} | {c['n']} · "
                 f"{100 * c['wins'] / c['n']:.1f}% · {lift_pp(c):+.1f} | {month_test_line(c)} |")
    L += ["", "month test: HOLDS = lift > 0 in every month with 30+ runners (two months",
          "minimum); THIN = not enough months; FAILS = at least one month against.",
          "Only HOLDS rows may be brought to the doorbell — and even then as a question."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=(date.today() - timedelta(days=1)).isoformat())
    ap.add_argument("--raw", default="data/school/raw")
    ap.add_argument("--out", default="data/school/tier0.md")
    ap.add_argument("--score-from", default="2026-01-01")
    a = ap.parse_args(argv)
    races = load_corpus(Path(a.raw))
    if not races:
        print(f"tier-0: no corpus under {a.raw} — nothing scored (fail loud)")
        return 1
    rows = rows_from(featurise(races, a.score_from))
    text = render(a.day, rows)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(text)
    yday = sum(1 for r in rows if r["date"] == a.day)
    print(f"tier-0: {yday} runner(s) scored for {a.day}, {len(rows)} in store -> {a.out}")
    if not yday:
        print(f"tier-0: WARNING — no resulted runners for {a.day} in the corpus "
              "(fetch missing or blank day) — the report shows the store only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
