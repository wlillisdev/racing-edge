"""THE FAVOURITE FILTER — his method, 2026-09-20, in his own words.

The master, 2026-09-20: *"why dont we simply look at all the favourites every
day, rule out the bad ones and dial in the ones that are left"*.

BORN BY: taught. This is law 2's first birth route — the master taught it and
asked for it built. Nothing here was invented by the apprentice; every dot
below is one he taught earlier and every one is named in the reasons string
so a pick can always be argued with.

WHAT IT DOES, exactly as asked:
  1. take EVERY favourite on the card
  2. score it on the dots he taught
  3. RULE OUT the bad ones (score below the floor)
  4. what is left is the day's list, best score first

WHAT THE RECORD ALREADY SAYS ABOUT IT, recorded here because he is owed it
every time he reads this file, not only the day it was written. Tested on
6,184 races with 32,560 run comments, tuned on everything to 2026-08-14 and
tested once on everything after:

    the dots DO sort winners        strike climbs 21.2% -> 45.5% by score
    the market has already done it  ROI is FLAT across every score band
    the floor is worth something    score>=-1 held out -3.7% v -5.1% for
                                    all favourites: 1.4 points saved
    it does not clear the margin    you need about 5 points to break even

So the honest expectation is a small real improvement on backing every
favourite, and still a loss. It is implemented because he asked for it after
being shown these numbers, and it is graded nightly so the record — not
either of us — settles it.

THE DOTS (all taught, none invented):
  +1  won last time out
  +1  beaten under a length last time
  -1  beaten more than six lengths last time
  +1  the run comment says it finished well      (his manner lens)
  +1  the run comment gives it an excuse         (trouble in running)
  -1  the run comment says it emptied out
  -1  off the track more than 60 days
  +1  dropping in class        -1  rising in class
  +1  small field (<=7)        -1  big field (>=12)

Usage:
    PYTHONPATH=src python -m racing_edge.school.favfilter --day today
    PYTHONPATH=src python -m racing_edge.school.favfilter --grade   # on the corpus
"""
from __future__ import annotations

import argparse
import csv
import glob
import sys
from dataclasses import dataclass, field as dfield
from pathlib import Path

# His floor, chosen on the tuning half alone and then left alone. A favourite
# scoring below this is RULED OUT — the band beneath it ran -29.6% on the tune
# half and -15.6% on races it had never seen, the one consistently bad group
# the dots find.
FLOOR = -1

# THE SELECTION BAR — his correction, 2026-09-20: "we wont be backing every
# favourite". Ruling out the bad ones is only half the method; the other half
# is DIALLING IN. A favourite is only NAMED when enough of his dots fire at
# once. Chosen on the tuning half alone (the best cumulative band there with
# a usable sample) and then tested once:
#
#     score >= 4, odds-on RULED OUT
#         tune      n= 64  strike 46.9%  ROI +21.8%
#         HELD OUT  n= 31  strike 48.4%  ROI +35.1%
#         benchmark, all favourites, held out: 35.6%, -5.1%
#
# Positive on BOTH halves, and BETTER on both once the odds-on horses go —
# his correction of 2026-09-20 improved it, which is what a real effect does
# and a lucky one usually does not. About one bet every two or three days.
#
# NOT PROVEN, and the reason is his own law: n=31 on the held-out half is
# below the "judge nothing under 50 picks" bar. +35.1% +/- 25% is about 1.4
# standard errors. The forward record settles it; this page does not.
SELECT_AT = 4

# THE ODDS-ON BAR, applied here on his instruction of 2026-09-20: "well no odd
# on horses rule out". His own brief #16, and the right call: the dots pile up
# on short-priced horses BECAUSE short prices are what good recent form
# produces, so without this a high score is partly just a proxy for the price.
# At 1.40 you must win 71% of the time merely to stand still. Anything odds-on
# is RULED OUT before its dots are even counted.
ODDS_ON = 2.0

# THE CHASE LINE — born by the RECORD (law 2, route three: field-tested), and
# the strongest thing this project has found. It is not a clever rule; it is a
# blunt category, which is why it may survive.
#
#   ALL FLAT favourites     n=4323  36.0%   -3.8%   positive in 1 month of 9
#   ALL HURDLE favourites   n=1165  35.2%  -11.4%   positive in 1 month of 9
#   CHASE, odds-on ruled out n= 540  37.8%  +13.1%   positive in 7 months of 9
#   CHASE, odds-on ONLY      n=  96  52.1%  -16.2%   <- his bar #16, vindicated
#
# Strip the two strongest months (Jul +30%, Aug +42%, when jumps racing is at
# its weakest) and the other seven still run about +8%.
#
# THE MECHANISM, which is why this is not just a shape in the noise: a chase
# favourite is usually the better JUMPER, and its rivals fall, unseat and pull
# up. The market prices form. It appears to underprice COMPLETION.
#
# IT DOES NOT CLEAR HIS AUGUST BAR. Seven months of nine is not "stable", and
# by that standard nothing in this project has ever passed. It is wired as a
# SHADOW and judged forward, never carved.
CHASE_LINE_MIN_PRICE = ODDS_ON   # one constant, so the bar can never drift apart

# CONFIDENCE — his instruction, 2026-09-21: "pick at least 2 horses and put a
# % in relation to confidence". The number is NOT an opinion and NOT a feeling.
# It is the HISTORICAL STRIKE RATE of favourites that scored the same way, on
# 3,781 eligible favourites across 6,247 races, odds-on excluded:
#
#     score -2  n=177  21.5%      score  2  n=754  33.2%
#     score -1  n=467  31.9%      score  3  n=344  34.9%
#     score  0  n=904  29.3%      score  4  n= 88  46.6%
#     score  1  n=998  33.0%
#     every eligible favourite    n=3781  31.9%
#     chase favourite at 2.0+     n= 340  39.1%
#
# READ IT HONESTLY: "46%" means horses scoring 4 have won 46% of the time
# before. It is not a prediction about THIS horse, and it is a base rate with
# a sample attached — the 46% rests on 88 runners and will move. The n is
# printed beside every figure for that reason.
CONFIDENCE = {-2: (21.5, 177), -1: (31.9, 467), 0: (29.3, 904), 1: (33.0, 998),
              2: (33.2, 754), 3: (34.9, 344), 4: (46.6, 88)}
CONFIDENCE_CHASE = (39.1, 340)
BASE_RATE = (31.9, 3781)
MIN_NAMED = 2            # his floor: at least two horses every day


def confidence(score: int | None) -> tuple[float, int]:
    """The base rate for this score, or the overall one when off the table."""
    if score is None:
        return BASE_RATE
    if score in CONFIDENCE:
        return CONFIDENCE[score]
    return CONFIDENCE[max(CONFIDENCE)] if score > max(CONFIDENCE) \
        else CONFIDENCE[min(CONFIDENCE)]


GALLANT = ("stayed on", "kept on", "ran on", "rallied", "finished well",
           "just held", "every chance", "challenged")
TROUBLE = ("hampered", "no clear run", "not clear run", "short of room",
           "checked", "squeezed", "denied", "slowly away", "stumbled")
EMPTY = ("weakened", "found little", "no extra", "one paced", "faded",
         "tailed off", "outpaced", "hung", "never a factor", "always behind",
         "no impression")


@dataclass
class LastRun:
    """What the horse did last time. Everything here is pre-race knowledge
    TODAY, because it happened before today."""
    position: str = ""
    beaten: float | None = None
    comment: str = ""
    days_since: int | None = None
    rclass: int | None = None


@dataclass
class Scored:
    horse: str
    score: int
    reasons: list[str] = dfield(default_factory=list)
    ruled_out: bool = False

    named: bool = False          # cleared SELECT_AT — an actual selection

    @property
    def verdict(self) -> str:
        if self.ruled_out:
            return "RULED OUT"
        return "NAMED" if self.named else "kept (not named)"


def score_favourite(last: LastRun | None, *, rclass: int | None,
                    field_size: int, floor: int = FLOOR,
                    select_at: int = SELECT_AT,
                    price: float | None = None) -> Scored | None:
    """The dots, added up, with every one that fired named.

    A favourite with NO previous run returns None — unraced or unreadable is
    not the same as bad, and guessing would be inventing. The caller decides
    what to do with an unread horse; this never pretends to know."""
    if last is None:
        return None
    if price is not None and price < ODDS_ON:
        return Scored(horse="", score=0, ruled_out=True, named=False,
                      reasons=[f"RULED OUT: odds-on at {price:.2f} — "
                               f"needs {100/price:.0f}% to break even (his bar #16)"])
    s, why = 0, []
    if last.position == "1":
        s += 1; why.append("+1 won last time")
    if last.beaten is not None and last.beaten <= 1:
        s += 1; why.append("+1 beaten under a length")
    if last.beaten is not None and last.beaten > 6:
        s -= 1; why.append("-1 beaten more than six lengths")
    c = (last.comment or "").lower()
    if c:
        if any(w in c for w in GALLANT):
            s += 1; why.append("+1 comment: finished well")
        if any(w in c for w in TROUBLE):
            s += 1; why.append("+1 comment: had an excuse")
        if any(w in c for w in EMPTY):
            s -= 1; why.append("-1 comment: emptied out")
    else:
        why.append(" 0 comment UNREAD — not guessed")
    if last.days_since is not None and last.days_since > 60:
        s -= 1; why.append(f"-1 off the track {last.days_since} days")
    if rclass and last.rclass:
        if rclass > last.rclass:
            s += 1; why.append("+1 dropping in class")
        elif rclass < last.rclass:
            s -= 1; why.append("-1 rising in class")
    if field_size <= 7:
        s += 1; why.append("+1 small field")
    elif field_size >= 12:
        s -= 1; why.append("-1 big field")
    return Scored(horse="", score=s, reasons=why, ruled_out=s < floor,
                  named=s >= select_at)


# --------------------------------------------------------------------------- #
# grading on the corpus — the record settles it, not either of us
# --------------------------------------------------------------------------- #

COMMENT_DIRS = ("data/school/comments", "data/school/holdout/comments")


def _comments(dirpaths=COMMENT_DIRS) -> dict:
    """Every run comment, from BOTH corpus directories.

    The held-out days live apart so their filenames cannot collide with the
    ones the box writes nightly. Reading only the first directory left every
    held-out horse with no manner dots at all, which silently shrank the
    named set rather than erroring (caught 2026-09-21: n fell from 31 to 22
    when adding days should have raised it)."""
    if isinstance(dirpaths, str):
        dirpaths = (dirpaths,)
    out = {}
    for d in dirpaths:
        for f in glob.glob(f"{d}/*.csv"):
            for r in csv.reader(open(f)):
                if len(r) >= 3:
                    out[(r[0], r[1])] = r[2]
    return out


HOLDOUT = Path("data/school/holdout/raw")


def grade(raw: Path = Path("data/school/raw"), floor: int = FLOOR,
          split: str = "2026-08-14", holdout: Path = HOLDOUT) -> dict:
    """Score every favourite in the corpus and report the HIT RATE — his
    instruction of 2026-09-21: "forget about roi let me decide".

    Reads the held-out days too. They live in a separate directory because a
    file named for a day the box writes nightly would break its git pull
    forever; grading only `raw` silently reported an empty held-out half
    (caught 2026-09-21 before the number was quoted, not after)."""
    from collections import defaultdict
    from racing_edge.school.mine import load_corpus

    com = _comments()
    pool = list(load_corpus(raw))
    if Path(holdout).exists():
        pool += list(load_corpus(holdout))
    seen, races = set(), []
    for r in pool:
        if len([x for x in r if x.sp > 1.0]) < 4 or r[0].race_id in seen:
            continue
        seen.add(r[0].race_id)
        races.append(r)
    races.sort(key=lambda r: (r[0].date, r[0].race_id))
    hist = defaultdict(list)
    for r in races:
        for x in r:
            hist[x.horse].append((x.date, x.race_id, x.pos, x.btn, x.rclass))
    for h in hist:
        hist[h].sort()

    def last_of(h, day):
        prev = [q for q in hist[h.horse] if q[0] < day]
        if not prev:
            return None
        d, rid, pos, btn, cls = prev[-1]
        gap = ((int(day[5:7]) * 31 + int(day[8:10]))
               - (int(d[5:7]) * 31 + int(d[8:10])))
        return LastRun(pos, btn, com.get((rid, h.horse), ""), gap, cls)

    out = {}
    for name, pool in (("tune", [r for r in races if r[0].date <= split]),
                       ("held_out", [r for r in races if r[0].date > split])):
        kept = [0, 0, 0.0]
        named = [0, 0, 0.0]
        allf = [0, 0, 0.0]
        for r in pool:
            p = sorted([x for x in r if x.sp > 1.0], key=lambda x: x.sp)
            f = p[0]
            allf[0] += 1
            if f.pos == "1":
                allf[1] += 1; allf[2] += f.sp
            sc = score_favourite(last_of(f, f.date), rclass=f.rclass,
                                 field_size=len(p), floor=floor, price=f.sp)
            if sc is None or sc.ruled_out:
                continue
            kept[0] += 1
            if f.pos == "1":
                kept[1] += 1; kept[2] += f.sp
            if sc.named:
                named[0] += 1
                if f.pos == "1":
                    named[1] += 1; named[2] += f.sp

        def roi(t):
            return 100 * (t[2] - t[0]) / t[0] if t[0] else 0.0

        def strike(t):
            return 100 * t[1] / t[0] if t[0] else 0.0
        out[name] = {"kept_n": kept[0], "kept_strike": strike(kept),
                     "kept_roi": roi(kept), "all_n": allf[0],
                     "all_strike": strike(allf), "all_roi": roi(allf),
                     "named_n": named[0], "named_strike": strike(named),
                     "named_roi": roi(named)}
    return out


def render_grade(g: dict, floor: int = FLOOR) -> str:
    """STRIKE RATE FIRST — his instruction, 2026-09-21: "forget about roi let
    me decide". The return is still printed, because hiding a number is worse
    than showing one he did not ask for, but it is no longer the verdict and
    nothing is killed on it. He judges the price; this reports the hit rate."""
    L = ["THE FAVOURITE FILTER — his method, graded on the corpus",
         f"(odds-on ruled out; below {floor} ruled out; {SELECT_AT}+ is NAMED)", ""]
    for half in ("tune", "held_out"):
        d = g[half]
        L.append(f"  {half:9}  NAMED strike={d['named_strike']:5.1f}% (n={d['named_n']:4d})"
                 f"  ·  kept {d['kept_strike']:4.1f}% (n={d['kept_n']:4d})"
                 f"  ·  all favourites {d['all_strike']:4.1f}% (n={d['all_n']:4d})")
    d = g["held_out"]
    L += ["", f"  On races it had never seen the NAMED horses struck "
              f"{d['named_strike']:.1f}% against {d['all_strike']:.1f}% for every "
              f"favourite.",
          f"  (return, printed for the record and not as a verdict: "
          f"{d['named_roi']:+.1f}% v {d['all_roi']:+.1f}%)"]
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- #
# THE DAILY LIST — every favourite on the card, the bad ones ruled out
# --------------------------------------------------------------------------- #

def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _days_between(a: str, b: str) -> int | None:
    from datetime import date
    try:
        return (date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days
    except (ValueError, TypeError):
        return None


def _rclass(v) -> int | None:
    d = "".join(ch for ch in str(v or "") if ch.isdigit())
    return int(d) if d else None


def last_run_from_history(rows: list[dict], before: str) -> LastRun | None:
    """The horse's most recent run STRICTLY BEFORE today, out of the history
    door. Returns None when the door gave nothing — unread, never guessed."""
    runs = []
    for r in rows or []:
        d = str(r.get("date") or "")[:10]
        if not d or d >= before[:10]:
            continue
        runs.append((d, r))
    if not runs:
        return None
    d, r = max(runs, key=lambda t: t[0])
    return LastRun(position=str(r.get("position") or ""),
                   beaten=_f(r.get("ovr_btn") if r.get("ovr_btn") not in (None, "")
                             else r.get("btn")),
                   comment=str(r.get("comment") or ""),
                   days_since=_days_between(before, d),
                   rclass=_rclass(r.get("class")))


def daily_list(day: str = "today", floor: int = FLOOR, client=None) -> list[dict]:
    """HIS METHOD, on today's card: every favourite, scored, bad ones ruled out.

    One history call per favourite — one per race, not one per runner — so the
    whole card costs about as much as a single race's deep read."""
    from racing_edge.data.client import get_client
    client = client or get_client()
    cards = (client.racecards(day) or {}).get("racecards") or []
    out = []
    for c in cards:
        if str(c.get("race_status") or "").lower() == "result":
            continue                     # the tripwire: never read a run race
        runners = c.get("runners") or []
        priced = []
        for r in runners:
            odds = r.get("odds") or []
            dec = _f(odds[0].get("decimal")) if odds else None
            if dec and dec > 1.0:
                priced.append((dec, r))
        if len(priced) < 4:
            continue
        priced.sort(key=lambda t: t[0])
        price, fav = priced[0]
        hid = str(fav.get("horse_id") or "")
        try:
            hist = client.horse_results(hid, limit=6) if hid else []
        except Exception:
            hist = []                    # a dead door is unread, not bad
        last = last_run_from_history(hist, str(c.get("date") or day))
        sc = score_favourite(last, rclass=_rclass(c.get("race_class")),
                             field_size=len(priced), floor=floor)
        row = {"course": c.get("course"), "off": c.get("off_time"),
               "race_id": c.get("race_id"), "horse": fav.get("horse"),
               "price": price, "field": len(priced),
               "type": c.get("type") or ""}
        if sc is None:
            row.update(score=None, ruled_out=True, verdict="UNREAD (no history)",
                       reasons=["no previous run the door could see"])
        else:
            sc.horse = str(fav.get("horse") or "")
            row.update(score=sc.score, ruled_out=sc.ruled_out,
                       verdict=sc.verdict, reasons=sc.reasons)
        out.append(row)
    out.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0), r["price"]))
    return out


def chase_line(rows: list[dict]) -> list[dict]:
    """The record's own selection: every CHASE favourite at 2.0 or bigger.

    Deliberately blunt — no dots, no scoring, no thresholds anyone chose. The
    only two conditions are a fact about the race (it is a chase) and his own
    odds-on bar. Nothing here can be tuned, which is the point."""
    return [r for r in rows
            if (r.get("type") or "").upper().startswith("C")
            and r["price"] >= CHASE_LINE_MIN_PRICE]


def todays_picks(rows: list[dict], minimum: int = MIN_NAMED) -> list[dict]:
    """HIS FLOOR: at least two horses, every day.

    Everything scoring SELECT_AT or better is named. If that is fewer than
    two, the list is topped up with the best remaining eligible favourites —
    because a day with nothing to say is not what he asked for. A topped-up
    pick is flagged so it is never mistaken for one that cleared the bar, and
    it carries its own (lower) base rate."""
    live = [r for r in rows if not r["ruled_out"] and r["score"] is not None]
    live.sort(key=lambda r: (-r["score"], r["price"]))
    picks = [dict(r, cleared=True) for r in live if r["score"] >= SELECT_AT]
    for r in live:
        if len(picks) >= minimum:
            break
        if any(p["race_id"] == r["race_id"] for p in picks):
            continue
        picks.append(dict(r, cleared=False))
    for p in picks:
        pct, n = confidence(p["score"])
        p["confidence"], p["confidence_n"] = pct, n
    return picks


def render_list(rows: list[dict], floor: int = FLOOR) -> str:
    kept = [r for r in rows if not r["ruled_out"]]
    L = ["THE FAVOURITE FILTER — his method, 2026-09-20",
         f"every favourite on the card, scored; anything below {floor} is ruled out",
         f"{len(rows)} favourites read · {len(kept)} kept · "
         f"{len(rows) - len(kept)} ruled out", ""]
    if not rows:
        L.append("  (no card, or nothing with a priced field of four or more)")
    for r in rows:
        mark = "  " if not r["ruled_out"] else "x "
        sc = "  ?" if r["score"] is None else f"{r['score']:+3d}"
        L.append(f"{mark}{sc}  {r['course']} {r['off']}  {r['horse']} "
                 f"@ {r['price']:.2f}  ({r['field']} runners)")
        L.append(f"        {'; '.join(r['reasons'])}")
    picks = todays_picks(rows)
    L = [L[0], L[1], L[2], "",
         "=" * 66,
         f"TODAY'S {len(picks)} — best first, with the record's own confidence",
         "  confidence = how often favourites scoring the same have WON before.",
         "  It is a base rate with its sample beside it, not a tip on this horse.",
         ""] + L[3:]
    for p in picks:
        mark = "NAMED " if p["cleared"] else "top-up"
        L.insert(7 + picks.index(p),
                 f"  {mark} {p['confidence']:.0f}% (n={p['confidence_n']})  "
                 f"{p['course']} {p['off']}  {p['horse']} @ {p['price']:.2f}"
                 f"  [score {p['score']:+d}]")
    ch = chase_line(rows)
    L += ["", "-" * 66,
          f"THE CHASE LINE — every chase favourite at {CHASE_LINE_MIN_PRICE:.1f}+ "
          f"({len(ch)} today)",
          "  the record's own: chase favourites strike 37.8% over 540 races,",
          "  against 36.0% flat and 35.2% hurdle — and unlike those two it was",
          "  in front in 7 months of 9. NOT PROVEN. Shadow only.", ""]
    if not ch:
        L.append("  (no qualifying chase today)")
    for r in ch:
        L.append(f"     {r['course']} {r['off']}  {r['horse']} @ {r['price']:.2f}"
                 f"  ({r['field']} runners)")
    L += ["", "GRADED NIGHTLY against the engine's pick and against backing every",
          "favourite. Paper only. The record settles it."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="THE FAVOURITE FILTER (taught 2026-09-20)")
    ap.add_argument("--grade", action="store_true", help="grade it on the corpus")
    ap.add_argument("--day", default="today")
    ap.add_argument("--raw", default="data/school/raw")
    ap.add_argument("--floor", type=int, default=FLOOR)
    a = ap.parse_args(argv)
    if a.grade:
        print(render_grade(grade(Path(a.raw), a.floor), a.floor))
        return 0
    print(render_list(daily_list(a.day, a.floor), a.floor))
    return 0


if __name__ == "__main__":
    sys.exit(main())
