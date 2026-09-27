"""HIS RULEBOOK, TESTED ON FAVOURITES — the full results archive, 2026-09-27.

The master, 2026-09-27: "u have the full form read we have been teaching you
for last 6 months ... u reframe it and how u implement it", then "u can test
it properly from today, u can get all the information needed".

The results archive carries draw, weight, official rating, age, going,
trainer and jockey on every runner. data/archive/results_2026.csv.gz holds
all 9,600 GB+IRE races from 1 Jan to 26 Sep 2026. This module asks two
questions of it, and prints both answers:

  1. RULE BY RULE: among favourites at evens or bigger (his odds-on ruling),
     does each rule he taught separate winners from losers — on BOTH halves
     (1 Mar - 14 Aug, and 15 Aug on)? History is built from earlier days only.
  2. THE REAL QUESTION: added to the favourite filter as dots, do the rules
     that held make the filter's own picks (top two a day, the nap first)
     win more often?

Usage:  PYTHONPATH=src python -m racing_edge.school.rulebook_test
"""
import csv
import glob
import json
import math
import sys
from collections import defaultdict
from datetime import date

from racing_edge.school import favfilter as F




def fl(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def dist(v):
    return fl(str(v or "").rstrip("f"))


def going_group(g):
    g = (g or "").lower()
    if "heavy" in g or "soft" in g or "yielding" in g:
        return "soft"
    if "firm" in g or "good to firm" in g:
        return "fast"
    if "standard" in g or "slow" in g:
        return "aw"
    return "good"



ARCHIVE = "data/archive/results_2026.csv.gz"
COMMENT_DIRS = ("data/school/comments", "data/school/holdout/comments")


def load_archive(path=ARCHIVE):
    """Races as dicts with their runners, from the full-field archive."""
    import gzip
    races = {}
    with gzip.open(path, "rt", newline="") as fh:
        for row in csv.DictReader(fh):
            r = races.get(row["race_id"])
            if r is None:
                r = races[row["race_id"]] = {k: row[k] for k in (
                    "date", "race_id", "course", "region", "type", "class",
                    "pattern", "going", "surface", "dist_f")}
                r["runners"] = []
            r["runners"].append({k: row[k] for k in (
                "horse_id", "position", "sp_dec", "ovr_btn", "draw", "weight_lbs",
                "or", "age", "headgear", "jockey_id", "trainer_id")})
    return sorted(races.values(), key=lambda r: (r["date"], r["race_id"]))


def main() -> int:
    races = load_archive()
    print(f"{len(races)} races, {races[0]['date']} .. {races[-1]['date']}")
    hist = defaultdict(list)          # horse -> list of run dicts (earlier days only)
    jock = defaultdict(lambda: [0, 0])    # (jockey, course) -> rides, wins
    drawb = defaultdict(lambda: [[0, 0], [0, 0], [0, 0]])   # course -> thirds [runs, wins]
    by_day = defaultdict(list)
    for r in races:
        by_day[r["date"]].append(r)

    rows = []
    for day in sorted(by_day):
        for r in by_day[day]:
            run = [x for x in r.get("runners") or [] if (fl(x.get("sp_dec")) or 0) > 1.0]
            if len(run) < 4:
                continue
            run.sort(key=lambda x: fl(x["sp_dec"]))
            f = run[0]
            sp = fl(f["sp_dec"])
            if sp < 2.0 or day < "2026-03-01":
                continue
            cls = int("".join(c for c in str(r.get("class") or "") if c.isdigit()) or 0)
            typ = (r.get("type") or "")
            flat = typ.lower().startswith("flat")
            chase = "chase" in typ.lower()
            h = hist[f["horse_id"]]
            last = h[-1] if h else None
            orr = fl(f.get("or"))
            rt = {}
            # --- 2b-ii THE FIVE-PART SOLID TEST ---
            if h:
                won_ever = any(q["pos"] == "1" for q in h)
                in_form = last["pos"] in ("1", "2", "3")
                fit = (date.fromisoformat(day) - date.fromisoformat(last["date"])).days <= 60
                raised = (orr is not None and last["or"] is not None and orr > last["or"])
                rt["2b-ii SOLID: all five parts"] = won_ever and in_form and fit and not raised
                rt["2b-ii has actually won"] = won_ever
                rt["2b-ii in form (placed last run)"] = in_form
            # --- 3g THE WINNING MARK (handicaps: a rating on the horse, not pattern) ---
            if orr is not None and not r.get("pattern"):
                wins = [q for q in h if q["pos"] == "1" and q["or"] is not None]
                if wins:
                    rt["3g at or below his last winning mark"] = orr <= wins[-1]["or"]
                if last and last["or"] is not None:
                    raised = orr > last["or"]
                    rt["3g first run off a raised mark (against)"] = raised
                    if raised and last["pos"] == "1":
                        # his receipts are 3yos (Captain Cairney, Kokbastau); "straight
                        # back out" has no number from him, so it is not tested
                        rt["3g-ii raised last-time winner aged 3 (for)"] = (fl(f.get("age")) or 9) <= 3
            # --- 3e weight / the tight lead: top weight is not a cross ---
            wts = [fl(x.get("weight_lbs")) for x in run if fl(x.get("weight_lbs"))]
            if wts and fl(f.get("weight_lbs")):
                rt["3e fav carries top weight"] = fl(f["weight_lbs"]) >= max(wts)
            # --- 3f THE DRAW (flat, course bias learned from earlier days only) ---
            dr = fl(f.get("draw"))
            if flat and dr and len(run) >= 8:
                b = drawb[r["course"]]
                if sum(t[0] for t in b) >= 300:
                    share = [t[1] / t[0] if t[0] else 0 for t in b]
                    third = min(2, int(3 * (dr - 1) / len(run)))
                    rt["3f drawn in the course's worst third"] = third == share.index(min(share))
                    rt["3f drawn in the course's best third"] = third == share.index(max(share))
            # --- 3h THE TRACK KNOWS ITS OWN ---
            if h:
                rt["3h placed at today's course before"] = any(
                    q["course"] == r["course"] and q["pos"] in ("1", "2", "3") for q in h)
            # --- trip and going fit (rule 6 corroboration: FIT) ---
            dd = dist(r.get("dist_f"))
            if h and dd:
                rt["6c placed within 1f of today's trip"] = any(
                    q["dist"] and abs(q["dist"] - dd) <= 1 and q["pos"] in ("1", "2", "3") for q in h)
                gg = going_group(r.get("going"))
                rt["6c placed on today's going"] = any(
                    q["going"] == gg and q["pos"] in ("1", "2", "3") for q in h)
            # --- 3i species / the improver-favourite trap ---
            if (fl(f.get("age")) or 9) <= 4:
                rt["3i unexposed (<=6 runs, age<=4) — the trap"] = len(h) <= 6
            # --- 6 class ---
            rt["6 class 1-4 (preferred)"] = 1 <= cls <= 4
            rt["6 class 6 flat (a pass)"] = cls == 6 and flat
            # --- #22 the anchor bar ---
            rt["#22 no anchor: fav 6/1+ (5/1+ below Cl3)"] = sp >= (7.0 if 1 <= cls <= 3 else 6.0)
            # --- no completed chase ---
            if chase:
                rt["no completed chase (chase favs)"] = not any(q["chase"] and q["pos"].isdigit() for q in h)
            # --- 8 beat the danger: a rival won its last run ---
            rt["8 a rival won its last run"] = any(
                hist[x["horse_id"]] and hist[x["horse_id"]][-1]["pos"] == "1" for x in run[1:])
            # --- 3b direction: margin shrinking over the last two ---
            if len(h) >= 2 and h[-1]["btn"] is not None and h[-2]["btn"] is not None:
                rt["3b last two runs improving"] = h[-1]["btn"] < h[-2]["btn"]
            # --- #30 the course jockey ---
            jr, jw = jock[(f.get("jockey_id"), r["course"])]
            if jr >= 15:
                rt["#30 course jockey 15%+ (15+ rides)"] = jw / jr >= 0.15
            # --- layoff (already a dot) for reference ---
            if last:
                rt["ref: off 60+ days"] = (date.fromisoformat(day) - date.fromisoformat(last["date"])).days > 60
            rows.append((day, f["position"] == "1", sp, rt, cls))
        # history grows only after the whole day
        for r in by_day[day]:
            n = len(r.get("runners") or [])
            dd = dist(r.get("dist_f"))
            gg = going_group(r.get("going"))
            chase = "chase" in (r.get("type") or "").lower()
            for x in r.get("runners") or []:
                hist[x["horse_id"]].append({
                    "date": day, "course": r["course"], "pos": str(x.get("position") or ""),
                    "btn": fl(x.get("ovr_btn")), "or": fl(x.get("or")), "dist": dd,
                    "going": gg, "chase": chase})
                k = (x.get("jockey_id"), r["course"])
                jock[k][0] += 1
                jock[k][1] += str(x.get("position")) == "1"
                dr = fl(x.get("draw"))
                if dr and (r.get("type") or "").lower().startswith("flat") and n >= 8:
                    t = min(2, int(3 * (dr - 1) / n))
                    drawb[r["course"]][t][0] += 1
                    drawb[r["course"]][t][1] += str(x.get("position")) == "1"


    def stat(sub):
        n = len(sub); w = sum(1 for s in sub if s[1])
        return n, w, (100 * w / n if n else 0.0)


    def z(a, b):
        if not a[0] or not b[0]:
            return 0.0
        p = (a[1] + b[1]) / (a[0] + b[0])
        se = math.sqrt(p * (1 - p) * (1 / a[0] + 1 / b[0])) or 1
        return (a[1] / a[0] - b[1] / b[0]) / se


    halves = (("tune", lambda d: d <= "2026-08-14"), ("held", lambda d: d > "2026-08-14"))
    for name, sel in halves:
        s = stat([r for r in rows if sel(r[0])])
        print(f"{name}: all eligible favourites n={s[0]} strike {s[2]:.1f}%")
    keys = []
    for r in rows:
        for k in r[3]:
            if k not in keys:
                keys.append(k)
    print(f"\n{'rule':46} {'half':4} {'fires n':>7} {'strike':>7} {'not n':>6} {'strike':>7} {'diff':>6} {'z':>5}  verdict")
    for k in keys:
        res = []
        for name, sel in halves:
            a = stat([r for r in rows if sel(r[0]) and r[3].get(k) is True])
            b = stat([r for r in rows if sel(r[0]) and r[3].get(k) is False])
            res.append((name, a, b, a[2] - b[2], z(a, b)))
        same = (res[0][3] > 0) == (res[1][3] > 0)
        strong = same and all(abs(x[4]) >= 1.5 for x in res)
        verdict = ("HOLDS" if strong else "same way, weak" if same else "flips")
        for i, (name, a, b, dff, zz) in enumerate(res):
            print(f"{k[:46]:46} {name:4} {a[0]:7d} {a[2]:6.1f}% {b[0]:6d} {b[2]:6.1f}% {dff:+6.1f} {zz:+5.1f}  "
                  + (verdict if i == 1 else ""))

    # ---- 2. the combination test -------------------------------------------
    com = {}
    for d in COMMENT_DIRS:
        for f in glob.glob(f"{d}/*.csv"):
            for r in csv.reader(open(f)):
                if len(r) >= 3:
                    com[(r[0], r[1])] = r[2]
    dig = lambda s: "".join(c for c in str(s) if c.isdigit())
    by_day = defaultdict(list)
    for r in races:
        by_day[r["date"]].append(r)

    hist = defaultdict(list)
    drawb = defaultdict(lambda: [[0, 0], [0, 0], [0, 0]])
    cand = defaultdict(list)
    cov = [0, 0]
    for day in sorted(by_day):
        for r in by_day[day]:
            run = [x for x in r.get("runners") or [] if (fl(x.get("sp_dec")) or 0) > 1.0]
            if len(run) < 4 or day < "2026-03-01": continue
            run.sort(key=lambda x: fl(x["sp_dec"]))
            f = run[0]; sp = fl(f["sp_dec"])
            h = hist[f["horse_id"]]
            if not h: continue
            l = h[-1]
            cls = int(dig(r.get("class")) or 0)
            c = com.get((l["rid"], dig(f["horse_id"])), "")
            cov[0] += 1; cov[1] += bool(c)
            last = F.LastRun(l["pos"], l["btn"], c, (date.fromisoformat(day) - date.fromisoformat(l["date"])).days, l["cls"] or None)
            sc = F.score_favourite(last, rclass=cls or None, field_size=len(run), price=sp)
            if sc is None or sc.ruled_out: continue
            extra = 0
            orr = fl(f.get("or"))
            if 1 <= cls <= 4: extra += 1                                           # 6
            age = fl(f.get("age")) or 9
            if age <= 4 and len(h) > 6: extra -= 1                                 # 3i
            won_ever = any(q["pos"] == "1" for q in h)
            raised = orr is not None and l["or"] is not None and orr > l["or"]
            if won_ever and l["pos"] in ("1", "2", "3") and last.days_since <= 60 and not raised:
                extra += 1                                                         # 2b-ii
            wins = [q for q in h if q["pos"] == "1" and q["or"] is not None]
            if orr is not None and not r.get("pattern") and wins and orr <= wins[-1]["or"]:
                extra += 1                                                         # 3g
            wts = [fl(x.get("weight_lbs")) for x in run if fl(x.get("weight_lbs"))]
            if wts and fl(f.get("weight_lbs")) and fl(f["weight_lbs"]) >= max(wts):
                extra += 1                                                         # 3e
            dr = fl(f.get("draw")); flat = (r.get("type") or "").lower().startswith("flat")
            if flat and dr and len(run) >= 8 and sum(t[0] for t in drawb[r["course"]]) >= 300:
                b = drawb[r["course"]]; share = [t[1] / t[0] if t[0] else 0 for t in b]
                if min(2, int(3 * (dr - 1) / len(run))) == share.index(min(share)): extra -= 1   # 3f
            cand[day].append(dict(won=f["position"] == "1", sp=sp, old=sc.score, new=sc.score + extra))
        for r in by_day[day]:
            n = len(r.get("runners") or []); flat = (r.get("type") or "").lower().startswith("flat")
            for x in r.get("runners") or []:
                hist[x["horse_id"]].append(dict(date=day, rid=dig(r["race_id"]), pos=str(x.get("position") or ""),
                                                btn=fl(x.get("ovr_btn")), or_=None, cls=int(dig(r.get("class")) or 0) or None))
                hist[x["horse_id"]][-1]["or"] = fl(x.get("or"))
                dr = fl(x.get("draw"))
                if dr and flat and n >= 8:
                    t = min(2, int(3 * (dr - 1) / n)); drawb[r["course"]][t][0] += 1
                    drawb[r["course"]][t][1] += str(x.get("position")) == "1"
    print(f"\ncomment coverage on favourites' last runs: {100*cov[1]/cov[0]:.0f}%")
    for half, sel in (("tune", lambda d: d <= "2026-08-14"), ("held", lambda d: d > "2026-08-14")):
        for key in ("old", "new"):
            t = [0, 0, 0.0]; nap = [0, 0]
            for day, cs in cand.items():
                if not sel(day): continue
                cs = sorted(cs, key=lambda c: (-c[key], c["sp"]))[:2]
                for i, c in enumerate(cs):
                    t[0] += 1; t[1] += c["won"]; t[2] += (c["sp"] - 1) if c["won"] else -1
                    if i == 0: nap[0] += 1; nap[1] += c["won"]
            print(f"{half} {'live filter' if key=='old' else 'filter + rulebook dots':24} top-2 a day: n={t[0]:4d} strike {100*t[1]/t[0]:5.1f}%  P/L {t[2]:+7.1f} | the NAP alone: {nap[1]}/{nap[0]} = {100*nap[1]/nap[0]:.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
