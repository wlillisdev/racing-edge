"""THE FINAL CALL — which tie-break picks the winner when we are down to two?

The master, 2026-09-07: "we seem to be very close to getting this right, we
can get it down to the final few horses, we just need to fine tune this...
there has to be a better way of making the final call." And the weekly
synthesis the same night: the notebook reaches for a MENU when the data is
thin (mark / market move / course form / figure trend) and "the scoreboard
shows the menu items perform wildly differently".

Three times we have chosen a tie-break by thinking hard — most reasons, then
the class line, then the mark — and each was wrong inside a fortnight. This
script does not think. It counts.

THE QUESTION, stated exactly: over every corpus race, take the two shortest
in the market as the final two. Which rule picks the winner of that pair
more often than simply taking the market's first?

LEAK SAFETY: every feature for a race on day D is computed from that horse's
corpus runs STRICTLY BEFORE D, and from trainer/jockey rows strictly before
D. Nothing from the race itself is read except the market (SP) and, for
scoring only, the result.

WHAT THIS CANNOT ANSWER, said plainly:
  - MANNER of running (the one lens the six-week synthesis says wins
    consistently) needs the comments file, which lives on the box, not in
    this repo. It is absent from every rule below. This study ranks the
    REST of the menu; manner is measured by the backward replay.
  - the market rank here is by SP, not by the 07:30 price. That INFLATES
    the benchmark (the market's first at SP is a stronger favourite than at
    dawn), so every rule below is scored against a harder benchmark than a
    live morning would face. Conservative, and named.
  - our real final two is the engine's pick + the named danger. The market's
    top two is a PROXY: the record says the winner sat in the market's first
    or second in six of nine danger-wins (bot A, 2026-09-05). Named as a
    proxy, never as the thing itself.

NOTHING HERE IS A RULE (CLAUDE.md law 2). It is a count, for his ruling.

Usage: PYTHONPATH=src python docs/research_final_call_2026-09-07.py
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

RAW = Path("data/school/raw")
MIN_N = 50          # his bar: judge nothing on fewer than 50 picks


# --------------------------------------------------------------------------- #
# the corpus
# --------------------------------------------------------------------------- #
class Run:
    __slots__ = ("date", "race_id", "course", "region", "rtype", "rclass",
                 "dist", "horse", "sp", "pos", "btn", "jockey", "trainer")

    def __init__(self, row):
        self.date = row[0]
        self.race_id = row[1]
        self.course = row[2]
        self.region = row[3]
        self.rtype = row[4]
        self.rclass = int("".join(c for c in row[5] if c.isdigit()) or 0)
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
            self.btn = -1.0
        self.jockey = row[11]
        self.trainer = row[12]

    @property
    def finished(self) -> int | None:
        """Finishing position as an int, or None (fell, pulled up, refused)."""
        return int(self.pos) if str(self.pos).isdigit() and int(self.pos) > 0 else None

    @property
    def won(self) -> bool:
        return self.finished == 1


def load(raw: Path = RAW) -> list[Run]:
    out = []
    for f in sorted(raw.glob("*.csv")):
        with open(f, newline="") as fh:
            for row in csv.reader(fh):
                if len(row) >= 13:
                    out.append(Run(row))
    return out


# --------------------------------------------------------------------------- #
# the features — every one from runs STRICTLY BEFORE the race's own day
# --------------------------------------------------------------------------- #
def _class_rung(r: Run) -> int:
    """Lower is better. Unclassed (Irish, mostly) ranks below Class 7."""
    return r.rclass if 1 <= r.rclass <= 7 else 9


def best_class_line(prior: list[Run]) -> tuple[int, int]:
    """(rung, won) of the best line the horse has: the highest class at which
    it WON or PLACED (first three) in its last ten runs. Mirrors
    selection/conviction.best_form_line: lower rung better, a win beats a
    place on the same rung. (99, 0) when there is no line at all."""
    best = (99, 0)
    for r in prior[:10]:
        p = r.finished
        if p is None or p > 3:
            continue
        cand = (_class_rung(r), 1 if p == 1 else 0)
        if cand[0] < best[0] or (cand[0] == best[0] and cand[1] > best[1]):
            best = cand
    return best


def direction(prior: list[Run]) -> int:
    """The Gower Prince law (3b, master-validated: 'direction outranks state')
    applied to the last three finishes: +1 improving, -1 declining, 0 flat or
    unreadable. Improving = the last finish better than the one before AND no
    worse than two back."""
    pos = [r.finished for r in prior[:3] if r.finished is not None]
    if len(pos) < 2:
        return 0
    if len(pos) == 2:
        return 1 if pos[0] < pos[1] else (-1 if pos[0] > pos[1] else 0)
    if pos[0] < pos[1] <= pos[2] or (pos[0] < pos[1] and pos[0] < pos[2]):
        return 1
    if pos[0] > pos[1] >= pos[2] or (pos[0] > pos[1] and pos[0] > pos[2]):
        return -1
    return 0


def days_since(prior: list[Run], day: str) -> int:
    if not prior:
        return 999
    d0 = date.fromisoformat(day)
    d1 = date.fromisoformat(prior[0].date)
    return (d0 - d1).days


def strike_before(rows: list[Run], day: str, window: int = 30) -> tuple[int, int]:
    """(runs, wins) inside `window` days before `day` — the in-form-yard and
    in-form-jockey lenses, computed leak-safe from the corpus itself."""
    d0 = date.fromisoformat(day)
    n = w = 0
    for r in rows:
        if r.date >= day:
            continue
        if (d0 - date.fromisoformat(r.date)).days > window:
            break
        n += 1
        w += 1 if r.won else 0
    return n, w


# --------------------------------------------------------------------------- #
# the rules — each takes the two candidates and returns the one it picks
# (a, b are (Run, features) pairs; a is the market's first)
# --------------------------------------------------------------------------- #
def _cmp(a_val, b_val, higher_better: bool):
    """-> 0 pick a, 1 pick b, None no opinion (equal)."""
    if a_val == b_val:
        return None
    if higher_better:
        return 0 if a_val > b_val else 1
    return 0 if a_val < b_val else 1


def rule_market_first(a, b):
    return 0                                     # THE BENCHMARK


def rule_class_line(a, b):
    """The inversion (2026-09-05, reverted 09-07): the better class line."""
    ka, kb = a["class_line"], b["class_line"]
    if ka == kb:
        return None
    if ka[0] != kb[0]:
        return 0 if ka[0] < kb[0] else 1
    return 0 if ka[1] > kb[1] else 1


def rule_direction(a, b):
    """Law 3b: the rising lines beat the falling ones."""
    return _cmp(a["direction"], b["direction"], True)


def rule_class_then_direction(a, b):
    """His teaching of 2026-09-06 in the flesh: the class line FIRST, but the
    direction of the recent lines decides between near-equal rungs."""
    ka, kb = a["class_line"], b["class_line"]
    if abs(ka[0] - kb[0]) <= 1:
        return _cmp(a["direction"], b["direction"], True)
    return 0 if ka[0] < kb[0] else 1


def rule_direction_then_class(a, b):
    d = _cmp(a["direction"], b["direction"], True)
    return d if d is not None else rule_class_line(a, b)


def rule_lto_winner(a, b):
    return _cmp(a["lto_won"], b["lto_won"], True)


def rule_yard_form(a, b):
    """The in-form yard, 30-day strike, both sides needing 5+ runs."""
    if a["yard_n"] < 5 or b["yard_n"] < 5:
        return None
    return _cmp(a["yard_sr"], b["yard_sr"], True)


def rule_jockey_form(a, b):
    if a["jky_n"] < 5 or b["jky_n"] < 5:
        return None
    return _cmp(a["jky_sr"], b["jky_sr"], True)


def rule_fresher(a, b):
    return _cmp(a["days"], b["days"], False)


def rule_closer_last_time(a, b):
    """Beaten less last time — the 'pound a length' instinct, crudely."""
    if a["btn_last"] < 0 or b["btn_last"] < 0:
        return None
    return _cmp(a["btn_last"], b["btn_last"], False)


def rule_yard_then_market(a, b):
    """The Juggernaut shape, 2026-09-07: the 25% yard beat the 8% yard, and
    the market's first was the 8% yard. Yard form decides; the market breaks
    a tie."""
    r = rule_yard_form(a, b)
    return 0 if r is None else r


RULES = {
    "market's first (BENCHMARK)": rule_market_first,
    "better class line": rule_class_line,
    "rising lines (law 3b)": rule_direction,
    "class line, direction within a rung": rule_class_then_direction,
    "direction, then class line": rule_direction_then_class,
    "won last time out": rule_lto_winner,
    "hotter yard (30d)": rule_yard_form,
    "hotter yard, else market": rule_yard_then_market,
    "hotter jockey (30d)": rule_jockey_form,
    "fresher (fewer days)": rule_fresher,
    "beaten less last time": rule_closer_last_time,
}


# --------------------------------------------------------------------------- #
# the run
# --------------------------------------------------------------------------- #
def main() -> int:
    runs = load()
    if not runs:
        print(f"no corpus at {RAW.resolve()} — nothing to count")
        return 1

    by_horse: dict[str, list[Run]] = defaultdict(list)
    by_trainer: dict[str, list[Run]] = defaultdict(list)
    by_jockey: dict[str, list[Run]] = defaultdict(list)
    by_race: dict[str, list[Run]] = defaultdict(list)
    for r in runs:
        by_horse[r.horse].append(r)
        by_trainer[r.trainer].append(r)
        by_jockey[r.jockey].append(r)
        by_race[r.race_id].append(r)
    for d in (by_horse, by_trainer, by_jockey):
        for k in d:
            d[k].sort(key=lambda r: r.date, reverse=True)   # newest first

    def prior(rows: list[Run], day: str) -> list[Run]:
        return [r for r in rows if r.date < day]            # STRICTLY before

    def feats(r: Run) -> dict:
        p = prior(by_horse[r.horse], r.date)
        yn, yw = strike_before(by_trainer[r.trainer], r.date)
        jn, jw = strike_before(by_jockey[r.jockey], r.date)
        return {"class_line": best_class_line(p),
                "direction": direction(p),
                "lto_won": 1 if (p and p[0].won) else 0,
                "days": days_since(p, r.date),
                "btn_last": p[0].btn if p else -1.0,
                "yard_n": yn, "yard_sr": (yw / yn if yn else 0.0),
                "jky_n": jn, "jky_sr": (jw / jn if jn else 0.0),
                "n_prior": len(p)}

    # THE HELD-OUT HALF (the master, 2026-09-07: "can we not run the same set
    # of criteria and lenses on our set of results and keep fine tuning it
    # until we get a better win percentage?"). Yes — with the discipline his
    # own graduation bar already names: 500+ UNSEEN races. Tune on the first
    # half of the record, then look ONCE at the half never touched. A rule
    # that only works on the half it was chosen from was chosen by chance.
    days = sorted({r.date for r in runs})
    cut = days[len(days) // 2]

    # tally[rule][band] = [decided, wins, returned]
    tally: dict[str, dict[str, list]] = {k: defaultdict(lambda: [0, 0, 0.0])
                                         for k in RULES}
    pairs = 0
    for rid, rs in by_race.items():
        priced = [r for r in rs if r.sp > 1.0]
        if len(priced) < 5:                      # the mine's own field floor
            continue
        if not any(r.won for r in priced):       # no identified winner
            continue
        priced.sort(key=lambda r: (r.sp, r.horse))
        a, b = priced[0], priced[1]
        if a.sp == b.sp:                         # joint favourites: no "first"
            continue
        if not (a.won or b.won):                 # the pair did not hold the winner
            continue
        fa, fb = feats(a), feats(b)
        if fa["n_prior"] == 0 or fb["n_prior"] == 0:
            continue                             # a first-timer has no lines to read
        pairs += 1
        cls = a.rclass if 1 <= a.rclass <= 7 else 0
        # HOW SPLIT IS THE MARKET? The real down-to-two moment is the one where
        # the crowd itself cannot separate them: if a lens is ever going to
        # beat the market's order, it is here, where that order means least.
        gap = b.sp / a.sp
        split = "SPLIT" if gap <= 1.25 else "CLEAR" if gap <= 1.75 else "DECIDED"
        half = "TUNED ON" if a.date < cut else "HELD OUT"
        bands = ["ALL",
                 f"code {a.rtype}",
                 ("Cl1-2" if cls in (1, 2) else "Cl3-4" if cls in (3, 4)
                  else "Cl5-7" if cls else "unclassed"),
                 {"SPLIT": "market SPLIT (2nd within 25%)",
                  "CLEAR": "market CLEAR (2nd 25-75% longer)",
                  "DECIDED": "market DECIDED (2nd 75%+ longer)"}[split],
                 f"market {split} · {half}"]
        for name, fn in RULES.items():
            side = fn(fa, fb)
            if side is None:
                continue                         # the rule has no opinion here
            pick = a if side == 0 else b
            for band in bands:
                t = tally[name][band]
                t[0] += 1
                if pick.won:
                    t[1] += 1
                    t[2] += pick.sp

    def line(name: str, band: str) -> str:
        n, w, ret = tally[name][band]
        if n < MIN_N:
            return f"| {name} | {n} | — | — | under {MIN_N}, no verdict |"
        return (f"| {name} | {n} | {100.0 * w / n:.1f}% | "
                f"{100.0 * (ret - n) / n:+.1f}% | |")

    print(f"# THE FINAL CALL — which rule picks the winner of the market's top two?\n")
    print(f"corpus: {len(runs)} runner rows, {len(by_race)} races, "
          f"{pairs} races where the top two held the winner and both had form\n")
    print("Every feature is computed from that horse's runs STRICTLY BEFORE the "
          "race day. MANNER IS ABSENT (the comments file lives on the box) — the "
          "one lens the weekly synthesis says wins consistently is NOT tested "
          "here. Market rank is by SP, which makes the benchmark harder than a "
          "07:30 read would face. Nothing below is a rule.\n")
    print(f"\nTHE HELD-OUT TEST: the record is cut at {cut}. A rule is TUNED ON "
          f"the earlier half and then looked at ONCE on the later half it never "
          f"saw. A rule that only works on the half it was chosen from was "
          f"chosen by chance.\n")
    for band in ["ALL",
                 "market SPLIT (2nd within 25%)",
                 "market SPLIT · TUNED ON", "market SPLIT · HELD OUT",
                 "market CLEAR (2nd 25-75% longer)",
                 "market CLEAR · TUNED ON", "market CLEAR · HELD OUT",
                 "market DECIDED (2nd 75%+ longer)",
                 "Cl1-2", "Cl3-4", "Cl5-7", "unclassed",
                 "code F", "code H", "code C", "code N"]:
        rows = [line(n, band) for n in RULES]
        if all("under" in r for r in rows):
            continue
        print(f"\n## {band}\n")
        print("| rule | decided | strike | ROI at SP | |")
        print("|---|---|---|---|---|")
        for r in rows:
            print(r)
    print("\n---\nNothing above is a rule. A rule is born three ways only: the "
          "master teaches it, the master validates it, or the record "
          "field-tests it long enough to earn belief.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
