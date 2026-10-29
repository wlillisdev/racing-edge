"""BOT C — "the single best form line at the highest CLASS" v "most lines that fit".

One hypothesis, tested mechanically on the night-school corpus. Nothing is
carved: this file writes a report and reads numbers back. Report, never rule.

Design notes (stated up front because they change the answer):
  * History is built FROM THE CORPUS ONLY. Warm-up = every race before
    SCORE_FROM (mine.SCORE_FROM, 2026-03-01); those races feed features and are
    never scored. A horse whose first corpus appearance is the race being scored
    has n_prior = 0 and NO class line at all.
  * class_drop follows the repo's own convention (mine.featurise "clsdrop"):
    drop = today.rclass - last.rclass, POSITIVE = dropping to a weaker class
    (Class 1 highest, Class 6 lowest). The brief's formula was written the other
    way round; its parenthetical ("positive = dropping") is what is implemented.
  * TIES: primary rule is SHORTEST SP among the tied runners (then horse id, as
    mine.featurise breaks market ties). Because that tiebreak leans on the
    market, every strategy also reports UNIQ — the same strategy restricted to
    races where the criterion had exactly ONE holder and no tiebreak was needed.
  * A strategy that cannot name a horse in a race SKIPS that race, so each
    strategy has its own n. %fav = share of a strategy's picks that were the
    market favourite (how much of it is just the jolly wearing a hat).
  * HANDICAP v NON-HANDICAP IS NOT DERIVABLE from these 13 columns. rclass
    bands are used instead, and that is a substitute, not the thing asked for.

Usage: PYTHONPATH=src python class_line_test.py [--raw DIR] [--score-from D]
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from racing_edge.school.mine import (MIN_REPORT_N, SCORE_FROM, _days_between,
                                     load_corpus)
from racing_edge.school.tier0 import MIN_FIELD, RANK_CAP, lift_pp, month_test

MONTH_MIN_N = 30   # tier0's own month-cell floor, reused (not a new bar)


# ---------------------------------------------------------------------------
# feature build — strictly prior runs
# ---------------------------------------------------------------------------

def _ipos(pos: str):
    """Finishing position as int, or None for PU/F/UR/BD/RO/'0'/blank."""
    return int(pos) if pos.isdigit() and int(pos) > 0 else None


def build(races, score_from: str):
    """Walk the corpus day by day; return the scored races as feature dicts.

    A race day only enters horse history AFTER every race on it is featurised,
    so nothing same-day leaks (the mine's own guard, copied deliberately).
    """
    hist: dict[str, list[dict]] = defaultdict(list)
    out = []
    i, n = 0, len(races)
    while i < n:
        day = races[i][0].date
        todays = []
        while i < n and races[i][0].date == day:
            todays.append(races[i])
            i += 1

        for race in todays:
            priced = sorted((r for r in race if r.sp > 0),
                            key=lambda r: (r.sp, r.horse))
            if day < score_from:
                continue
            if len(priced) < MIN_FIELD:
                continue
            if not any(r.pos == "1" for r in priced):
                continue          # void / winner unpriced: counted nowhere
            runners = []
            for rank, r in enumerate(priced, 1):
                h = hist[r.horse]
                won_classes = [x["rclass"] for x in h
                               if x["rclass"] and x["pos"] == 1]
                plc_classes = [x["rclass"] for x in h
                               if x["rclass"] and x["pos"] is not None
                               and x["pos"] <= 3]
                run_classes = [x["rclass"] for x in h if x["rclass"]]
                last = h[-1] if h else None
                last3 = h[-3:]
                d = {
                    "horse": r.horse, "sp": r.sp, "rank": rank,
                    "won": r.pos == "1", "rclass": r.rclass,
                    "rtype": r.rtype, "field": len(priced),
                    "n_prior": len(h),
                    "best_class_won": min(won_classes) if won_classes else None,
                    "best_class_placed": min(plc_classes) if plc_classes else None,
                    "best_class_run": min(run_classes) if run_classes else None,
                    "last_class": last["rclass"] if last and last["rclass"] else None,
                    "last_pos": last["pos"] if last else None,
                    "last_won": bool(last and last["pos"] == 1),
                    "last_placed": bool(last and last["pos"] is not None
                                        and last["pos"] <= 3),
                    "days_since_last": (_days_between(last["date"], r.date)
                                        if last else None),
                    "wins_l3": sum(1 for x in last3 if x["pos"] == 1),
                    "places_l3": sum(1 for x in last3 if x["pos"] is not None
                                     and x["pos"] <= 3),
                }
                # positive = dropping to a weaker (higher-numbered) class
                d["class_drop"] = (r.rclass - d["last_class"]
                                   if r.rclass and d["last_class"] else None)
                runners.append(d)
            out.append({"date": day, "month": day[:7],
                        "race_id": race[0].race_id, "runners": runners})

        for race in todays:
            for r in race:
                hist[r.horse].append({"date": r.date, "rclass": r.rclass,
                                      "pos": _ipos(r.pos)})
    return out


# ---------------------------------------------------------------------------
# selection strategies — each names AT MOST ONE horse per race
# ---------------------------------------------------------------------------

def pick(runners, key, best=min, pool=None):
    """(chosen, unique) — chosen by key (min or max), ties to shortest SP.

    unique is True when exactly one runner held the winning key value, i.e. the
    pick needed no market tiebreak at all.
    """
    cands = [d for d in (pool if pool is not None else runners)
             if key(d) is not None]
    if not cands:
        return None, False
    tgt = best(key(d) for d in cands)
    tied = [d for d in cands if key(d) == tgt]
    tied.sort(key=lambda d: (d["sp"], d["horse"]))
    return tied[0], len(tied) == 1


def top(runners, k):
    return [d for d in runners if d["rank"] <= k]


STRATS = {}


def strat(name, note=""):
    def deco(fn):
        STRATS[name] = (fn, note)
        return fn
    return deco


@strat("1 FAVOURITE (control)", "sp_rank 1")
def _fav(rs):
    return pick(rs, lambda d: d["rank"], min)


@strat("2a VOLUME most prior runs", "max n_prior (exposure)")
def _vol_n(rs):
    return pick(rs, lambda d: d["n_prior"], max)


@strat("2b VOLUME most places last 3", "max places_l3")
def _vol_p(rs):
    return pick(rs, lambda d: d["places_l3"] if d["n_prior"] else None, max)


@strat("3a CLASS best class PLACED in", "min best_class_placed")
def _cls_p(rs):
    return pick(rs, lambda d: d["best_class_placed"], min)


@strat("3b CLASS best class WON in", "min best_class_won")
def _cls_w(rs):
    return pick(rs, lambda d: d["best_class_won"], min)


@strat("3c CLASS best class RUN in", "min best_class_run")
def _cls_r(rs):
    return pick(rs, lambda d: d["best_class_run"], min)


@strat("4a DROP biggest class drop", "max class_drop (>0 only)")
def _drop(rs):
    return pick(rs, lambda d: d["class_drop"] if (d["class_drop"] or 0) > 0
                else None, max)


@strat("4b DROP dropper that won/placed LTO", "max class_drop, last_placed")
def _drop_f(rs):
    return pick(rs, lambda d: d["class_drop"] if ((d["class_drop"] or 0) > 0
                                                  and d["last_placed"]) else None,
                max)


@strat("5a UNEXPOSED fewest runs, top 3", "min n_prior within sp_rank<=3")
def _unx3(rs):
    return pick(rs, lambda d: d["n_prior"], min, pool=top(rs, 3))


@strat("5b UNEXPOSED fewest runs, all", "min n_prior, whole field")
def _unxa(rs):
    return pick(rs, lambda d: d["n_prior"], min)


@strat("6a TOP-2 better class line", "min best_class_placed within sp_rank<=2")
def _h2c(rs):
    return pick(rs, lambda d: d["best_class_placed"], min, pool=top(rs, 2))


@strat("6b TOP-2 more prior runs", "max n_prior within sp_rank<=2")
def _h2v(rs):
    return pick(rs, lambda d: d["n_prior"], max, pool=top(rs, 2))


@strat("6c TOP-3 better class line", "min best_class_placed within sp_rank<=3")
def _h3c(rs):
    return pick(rs, lambda d: d["best_class_placed"], min, pool=top(rs, 3))


@strat("6d TOP-3 more prior runs", "max n_prior within sp_rank<=3")
def _h3v(rs):
    return pick(rs, lambda d: d["n_prior"], max, pool=top(rs, 3))


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------

class Book:
    """n / wins / SP return / expected wins from market rank, split by month."""

    def __init__(self):
        self.n = 0
        self.wins = 0
        self.ret = 0.0
        self.exp = 0.0
        self.favs = 0
        self.months = defaultdict(lambda: [0, 0, 0.0, 0.0])

    def add(self, d, month, rate):
        e = rate.get(min(d["rank"], RANK_CAP), 0.0)
        self.n += 1
        self.wins += d["won"]
        self.ret += d["sp"] if d["won"] else 0.0
        self.exp += e
        self.favs += d["rank"] == 1
        m = self.months[month]
        m[0] += 1
        m[1] += d["won"]
        m[2] += d["sp"] if d["won"] else 0.0
        m[3] += e

    strike = property(lambda s: 100.0 * s.wins / s.n if s.n else 0.0)
    roi = property(lambda s: 100.0 * (s.ret - s.n) / s.n if s.n else 0.0)
    lift = property(lambda s: 100.0 * (s.wins - s.exp) / s.n if s.n else 0.0)
    favpc = property(lambda s: 100.0 * s.favs / s.n if s.n else 0.0)

    def as_tier0(self):
        """Shape this book as a tier0 trait dict so month_test/lift_pp apply
        unchanged — the corpus's own month-stability idea, reused not remade."""
        return {"n": self.n, "wins": self.wins, "exp": self.exp,
                "months": {m: [v[0], v[1], v[3]] for m, v in self.months.items()}}

    def month_roi_test(self, min_n=MONTH_MIN_N):
        ms = [v for v in self.months.values() if v[0] >= min_n]
        if len(ms) < 2:
            return "THIN"
        return "HOLDS" if all(v[2] - v[0] > 0 for v in ms) else "FAILS"


def bands(d):
    """The strata: code, class band, field size band."""
    yield "code", "FLAT" if d["rtype"] == "F" else "JUMPS"
    c = d["rclass"]
    yield "class", ("unclassed" if not c else "cls1-3" if c <= 3
                    else "cls4-5" if c <= 5 else "cls6-7")
    f = d["field"]
    yield "field", "fld5-7" if f <= 7 else "fld8-11" if f <= 11 else "fld12+"


def control_rate(scored):
    """Store-wide win% by market rank (rank 7+ pooled) — tier0's control."""
    t = defaultdict(lambda: [0, 0])
    for race in scored:
        for d in race["runners"]:
            c = t[min(d["rank"], RANK_CAP)]
            c[0] += 1
            c[1] += d["won"]
    return {k: (v[1] / v[0] if v[0] else 0.0) for k, v in t.items()}, t


def run_strats(scored, rate):
    """Also books the FAVOURITE over each strategy's own race set — a strategy
    that can only name a horse in 982 of 1509 races must be judged against the
    jolly in those 982, not against the jolly everywhere (matched control)."""
    books, uniq, matched = {}, {}, {}
    strata = defaultdict(lambda: defaultdict(Book))
    for name in STRATS:
        books[name] = Book()
        uniq[name] = Book()
        matched[name] = Book()
    for race in scored:
        rs = race["runners"]
        fav = next((d for d in rs if d["rank"] == 1), None)
        for name, (fn, _) in STRATS.items():
            d, is_uniq = fn(rs)
            if d is None:
                continue
            books[name].add(d, race["month"], rate)
            if fav is not None:
                matched[name].add(fav, race["month"], rate)
            if is_uniq:
                uniq[name].add(d, race["month"], rate)
            for _, lab in bands(d):
                strata[name][lab].add(d, race["month"], rate)
    return books, uniq, matched, strata


# ---------------------------------------------------------------------------
# head-to-head (6) and story-v-line (7)
# ---------------------------------------------------------------------------

def head_to_head(scored, k, rate):
    """Within the market's first k: class-line pick v volume pick, races where
    they DIFFER. Both books, plus the raw won/won/neither counts."""
    cls, vol = Book(), Book()
    both_lost = 0
    for race in scored:
        pool = top(race["runners"], k)
        c, _ = pick(pool, lambda d: d["best_class_placed"], min)
        v, _ = pick(pool, lambda d: d["n_prior"], max)
        if c is None or v is None or c["horse"] == v["horse"]:
            continue
        cls.add(c, race["month"], rate)
        vol.add(v, race["month"], rate)
        if not c["won"] and not v["won"]:
            both_lost += 1
    return cls, vol, both_lost


def story_v_line(scored, rate):
    """Runners at sp_rank 2-3 whose class line beats the FAVOURITE's.

    Not one per race — this is a runner population, so ROI is per unit staked on
    every qualifier. 'Better' = strictly lower best_class_placed, and the
    favourite must have a class line to be beaten (unknown v unknown is not a
    win for the story).
    """
    b, b_won, b_run = Book(), Book(), Book()
    for race in scored:
        rs = race["runners"]
        fav = next((d for d in rs if d["rank"] == 1), None)
        if fav is None:
            continue
        for d in rs:
            if d["rank"] == 1 or d["rank"] > 3:
                continue
            for src, book in (("best_class_placed", b),
                              ("best_class_won", b_won),
                              ("best_class_run", b_run)):
                mine_, theirs = d[src], fav[src]
                if mine_ is not None and theirs is not None and mine_ < theirs:
                    book.add(d, race["month"], rate)
    return b, b_won, b_run


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def bar(n):
    return "  << UNDER THE BAR" if n < MIN_REPORT_N else ""


def row(label, b, note=""):
    if not b.n:
        return f"| {label} | 0 | - | - | - | - | - | - | {note} |"
    t0 = b.as_tier0()
    return (f"| {label} | {b.n} | {b.wins} | {b.strike:.1f}% | {b.roi:+.1f}% | "
            f"{b.lift:+.1f} | {month_test(t0, MONTH_MIN_N)} | "
            f"{b.month_roi_test()} | {b.favpc:.0f}% |"
            + ("" if b.n >= MIN_REPORT_N else "  <UNDER BAR>"))


HEAD = ("| selection | n | w | strike | ROI@SP | lift pp | month(lift) | "
        "month(ROI) | %fav |")
RULE = "|---|---|---|---|---|---|---|---|---|"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/school/raw")
    ap.add_argument("--score-from", default=SCORE_FROM)
    ap.add_argument("--out", default="class_line_test.md")
    a = ap.parse_args(argv)

    races = load_corpus(Path(a.raw))
    scored = build(races, a.score_from)
    rate, ctl = control_rate(scored)

    L = []
    w = L.append
    months = sorted({r["month"] for r in scored})
    w("# CLASS LINE v VOLUME — one hypothesis, mechanically tested")
    w("")
    w(f"corpus: {len(races)} races loaded from {a.raw}; "
      f"{len(scored)} scored (>= {a.score_from}, >= {MIN_FIELD} priced runners, "
      f"priced winner); "
      f"{sum(len(r['runners']) for r in scored)} priced runner rows")
    w(f"months scored: " + " ".join(f"{m[5:]}:{sum(1 for r in scored if r['month'] == m)}"
                                    for m in months))
    w("")
    w("HANDICAP v NON-HANDICAP: **not derivable** from the 13 corpus columns "
      "(no race name, no 'Hcap' flag, no official rating). rclass bands below "
      "stand in for it and are NOT the same question.")
    w("")
    allr = [d for r in scored for d in r["runners"]]
    w("## HOW MUCH HISTORY THE CORPUS ACTUALLY HAS (read this before the rest)")
    w("| fact | value |")
    w("|---|---|")
    w(f"| priced runners scored | {len(allr)} |")
    for lab, f in (("n_prior = 0 (no corpus history at all)",
                    lambda d: d["n_prior"] == 0),
                   ("n_prior 1-2", lambda d: 1 <= d["n_prior"] <= 2),
                   ("n_prior 3+", lambda d: d["n_prior"] >= 3),
                   ("has best_class_placed", lambda d: d["best_class_placed"]),
                   ("has best_class_won", lambda d: d["best_class_won"]),
                   ("has best_class_run", lambda d: d["best_class_run"]),
                   ("today's race unclassed (rclass 0)", lambda d: not d["rclass"])):
        c = sum(1 for d in allr if f(d))
        w(f"| {lab} | {c} ({100 * c / len(allr):.0f}%) |")
    w(f"| mean n_prior | {sum(d['n_prior'] for d in allr) / len(allr):.2f} |")
    w("")
    w("## THE CONTROL — every priced runner in the scored races, by market rank")
    w("| market rank | n | wins | win% |")
    w("|---|---|---|---|")
    for k in sorted(ctl):
        n, wn = ctl[k]
        lab = f"{k}" if k < RANK_CAP else f"{RANK_CAP}+"
        w(f"| {lab} | {n} | {wn} | {100 * wn / n:.1f}% |")
    w("")
    w("lift pp = win% minus the win% the picks' own market ranks predict from "
      "that control (the market held constant). month(lift) is tier0.month_test "
      f"verbatim (lift > 0 every month with {MONTH_MIN_N}+ picks, 2 months min); "
      "month(ROI) is the same shape applied to ROI. %fav = share of picks that "
      "were the favourite.")
    w("")

    books, uniq, matched, strata = run_strats(scored, rate)

    w("## 1-5 THE MECHANICAL SELECTIONS (one horse a race, ties to shortest SP)")
    w(HEAD)
    w(RULE)
    for name in sorted(STRATS):
        w(row(name, books[name]))
    w("")
    w("### MATCHED CONTROL — the favourite over each strategy's OWN races, and "
      "the gap")
    w("| selection | n | strike | fav strike (same races) | strike gap pp | "
      "ROI | fav ROI | ROI gap pp |")
    w("|---|---|---|---|---|---|---|---|")
    for name in sorted(STRATS):
        b, f = books[name], matched[name]
        if not b.n:
            continue
        w(f"| {name} | {b.n} | {b.strike:.1f}% | {f.strike:.1f}% | "
          f"{b.strike - f.strike:+.1f} | {b.roi:+.1f}% | {f.roi:+.1f}% | "
          f"{b.roi - f.roi:+.1f} |" + ("" if b.n >= MIN_REPORT_N else "  <UNDER BAR>"))
    w("")
    w("### the same selections with NO TIEBREAK (races where the criterion had "
      "exactly one holder)")
    w(HEAD)
    w(RULE)
    for name in sorted(STRATS):
        w(row(name, uniq[name]))
    w("")

    w("## 6 HEAD TO HEAD — class line v volume, inside the market's first k")
    w("(only races where the two measures name DIFFERENT horses)")
    w(HEAD)
    w(RULE)
    for k in (2, 3):
        c, v, bl = head_to_head(scored, k, rate)
        w(row(f"6 top-{k}: better CLASS line", c))
        w(row(f"6 top-{k}: more PRIOR RUNS", v))
        w(f"| 6 top-{k}: neither won | {bl} | - | - | - | - | - | - | - |")
    w("")

    w("## 7 STORY v LINE — sp_rank 2-3, class line better than the favourite's")
    w("(a runner population, not one a race: stake one unit on every qualifier)")
    w(HEAD)
    w(RULE)
    b, bw, br = story_v_line(scored, rate)
    w(row("7a beats fav on best class PLACED", b))
    w(row("7b beats fav on best class WON", bw))
    w(row("7c beats fav on best class RUN", br))
    w("")

    w("## STRATA — code / class band / field size (each strategy split)")
    for name in sorted(STRATS):
        w("")
        w(f"### {name} — {STRATS[name][1]}")
        w(HEAD)
        w(RULE)
        for lab in ("FLAT", "JUMPS", "cls1-3", "cls4-5", "cls6-7", "unclassed",
                    "fld5-7", "fld8-11", "fld12+"):
            b = strata[name].get(lab)
            if b and b.n:
                w(row(lab, b))
    w("")
    w(f"MIN_REPORT_N = {MIN_REPORT_N} (mine.py). Anything marked <UNDER BAR> "
      "recommends nothing.")

    text = "\n".join(L) + "\n"
    Path(a.out).write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
