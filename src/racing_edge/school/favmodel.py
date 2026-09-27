"""THE FAVOURITE MODEL — his filter, plus everything the archive knows, learned.

The master, 2026-09-27: "ai has the intelligence n power to reverse engineer
this now it has a solid base of learning ... why dont you just do it".

WHAT IT IS. A logistic model over 35 facts about each favourite (evens or
bigger, four or more priced runners): his filter's own score, the price and
the gap to the second favourite, class, race type, going, trip, the mark and
the mark against his last winning mark and against the top-rated, weight
against top weight, draw, age, days off, last run, career record, course /
trip / going form, trainer and jockey strike, rivals who won last time.

HOW IT WAS JUDGED (walk-forward, every month predicted by a model that never
saw it, April - September 2026, 179 days):
    the filter as live      top-2 40.8%   nap 80/179 = 44.7%
    this model              top-2 45.8%   nap 88/179 = 49.2%
Ahead in four months of six. Real on unseen months, modest in size: the
record decides whether it holds live.

ONE FEATURE FUNCTION. `features()` is the only place a fact is computed, for
training and for the 07:30 card alike, and a horse's past always comes from
the archive — so the live inputs are built exactly as the learned ones were.
Today's own facts (price, mark, weight, draw, age, going) come off the card.

NO NEW SOFTWARE ON THE BOX. Training uses scikit-learn in the study session;
the fitted model is exported to data/model/favmodel.json as plain numbers and
scored here in pure Python.

Usage:
    PYTHONPATH=src python -m racing_edge.school.favmodel --train   # study session
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

MODEL = Path("data/model/favmodel.json")
COMMENT_DIRS = ("data/school/comments", "data/school/holdout/comments")
JUDGE_FROM = "2026-03-01"       # Jan-Feb only warm the history up
ODDS_ON = 2.0                   # his ruling: no odds on

FEATURES = [
    "price", "second_fav_ratio", "field", "class", "pattern", "chase", "hurdle",
    "flat", "all_weather", "ireland", "going", "trip_f", "mark", "mark_v_top",
    "weight_v_top", "age", "draw_rel", "days_off", "last_pos", "last_btn",
    "runs", "wins", "win_rate", "place_rate", "mark_v_last_win", "mark_v_last_run",
    "course_places", "trip_places", "going_places", "trainer_strike",
    "trainer_runs", "trainer_14d", "jockey_strike", "rivals_won_lto", "filter_score",
]
NAN = float("nan")


def _fl(v, d=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _dig(s) -> str:
    return "".join(c for c in str(s) if c.isdigit())


def going_code(g) -> int:
    g = (g or "").lower()
    if "heavy" in g or "soft" in g or "yielding" in g:
        return 0
    if "firm" in g:
        return 2
    if "standard" in g or "slow" in g:
        return 3
    return 1


def trip_f(v) -> float:
    return _fl(str(v or "").strip().rstrip("f"), 0.0) or 0.0


def comments(dirs=COMMENT_DIRS) -> dict:
    out = {}
    for d in dirs:
        for f in glob.glob(f"{d}/*.csv"):
            for r in csv.reader(open(f, encoding="utf-8", errors="replace")):
                if len(r) >= 3:
                    out[(r[0], r[1])] = r[2]
    return out


class State:
    """Everything known about horses, trainers and jockeys from EARLIER days."""

    def __init__(self):
        self.hist = defaultdict(list)
        self.trn = defaultdict(list)
        self.jky = defaultdict(lambda: [0, 0])

    def add_day(self, day: str, races: list[dict]) -> None:
        for r in races:
            tf = trip_f(r.get("dist_f"))
            gc = going_code(r.get("going"))
            cls = int(_dig(r.get("class")) or 0) or None
            for x in r.get("runners") or []:
                won = str(x.get("position")) == "1"
                self.hist[x["horse_id"]].append({
                    "date": day, "rid": _dig(r["race_id"]),
                    "pos": str(x.get("position") or ""), "btn": _fl(x.get("ovr_btn")),
                    "or": _fl(x.get("or")), "cls": cls, "course": r.get("course"),
                    "dist": tf, "going": gc})
                self.trn[x.get("trainer_id")].append((day, won))
                self.jky[x.get("jockey_id")][0] += 1
                self.jky[x.get("jockey_id")][1] += won


def favourite(race: dict):
    """(favourite, priced runners best first), or None when the race is not
    in the model's world: under four priced runners, or an odds-on favourite."""
    run = [x for x in race.get("runners") or [] if (_fl(x.get("sp_dec")) or 0) > 1.0]
    if len(run) < 4:
        return None
    run.sort(key=lambda x: _fl(x["sp_dec"]))
    if _fl(run[0]["sp_dec"]) < ODDS_ON:
        return None
    return run[0], run


def features(race: dict, fav: dict, run: list[dict], st: State, day: str,
             com: dict) -> list[float]:
    from racing_edge.school import favfilter as F
    dd = date.fromisoformat(day)
    sp = _fl(fav["sp_dec"])
    h = st.hist[fav["horse_id"]]
    cls = int(_dig(race.get("class")) or 0)
    typ = (race.get("type") or "").lower()
    tf = trip_f(race.get("dist_f"))
    gc = going_code(race.get("going"))
    orr = _fl(fav.get("or"))
    ors = [_fl(x.get("or")) for x in run if _fl(x.get("or")) is not None]
    wts = [_fl(x.get("weight_lbs")) for x in run if _fl(x.get("weight_lbs"))]
    last = h[-1] if h else None
    wins = [q for q in h if q["pos"] == "1"]
    winors = [q["or"] for q in wins if q["or"] is not None]
    tr = [w for d0, w in st.trn[fav.get("trainer_id")]
          if (dd - date.fromisoformat(d0)).days <= 365]
    tr14 = [w for d0, w in st.trn[fav.get("trainer_id")]
            if (dd - date.fromisoformat(d0)).days <= 14]
    jr, jw = st.jky[fav.get("jockey_id")]
    draw = _fl(fav.get("draw"))
    aw = (race.get("surface") == "AW") or "(AW)" in (race.get("course") or "")
    fscore = NAN
    if last:
        c = com.get((last["rid"], _dig(fav["horse_id"])), "")
        sc = F.score_favourite(
            F.LastRun(last["pos"], last["btn"], c,
                      (dd - date.fromisoformat(last["date"])).days, last["cls"]),
            rclass=cls or None, field_size=len(run), price=sp)
        fscore = NAN if sc is None else float(sc.score)
    return [
        sp, _fl(run[1]["sp_dec"]) / sp, float(len(run)), float(cls),
        1.0 if race.get("pattern") else 0.0,
        1.0 if "chase" in typ else 0.0, 1.0 if "hurdle" in typ else 0.0,
        1.0 if typ.startswith("flat") else 0.0, 1.0 if aw else 0.0,
        1.0 if (race.get("region") or "").upper().startswith("IRE") else 0.0,
        float(gc), tf,
        orr if orr is not None else NAN,
        (orr - max(ors)) if (orr is not None and ors) else NAN,
        (_fl(fav.get("weight_lbs")) - max(wts)) if (wts and _fl(fav.get("weight_lbs"))) else NAN,
        _fl(fav.get("age"), NAN),
        (draw / len(run)) if (draw and typ.startswith("flat")) else NAN,
        float((dd - date.fromisoformat(last["date"])).days) if last else NAN,
        (_fl(last["pos"], 20.0) if last else NAN),
        (last["btn"] if last and last["btn"] is not None else NAN),
        float(len(h)), float(len(wins)), (len(wins) / len(h) if h else NAN),
        (sum(q["pos"] in ("1", "2", "3") for q in h) / len(h) if h else NAN),
        (orr - winors[-1]) if (orr is not None and winors) else NAN,
        (orr - last["or"]) if (orr is not None and last and last["or"] is not None) else NAN,
        float(sum(q["course"] == race.get("course") and q["pos"] in ("1", "2", "3") for q in h)),
        float(sum(abs((q["dist"] or 0) - tf) <= 1 and q["pos"] in ("1", "2", "3") for q in h)),
        float(sum(q["going"] == gc and q["pos"] in ("1", "2", "3") for q in h)),
        (sum(tr) / len(tr) if len(tr) >= 30 else NAN), float(len(tr)),
        (sum(tr14) / len(tr14) if len(tr14) >= 5 else NAN),
        (jw / jr if jr >= 30 else NAN),
        float(sum(1 for x in run[1:] if st.hist[x["horse_id"]]
                  and st.hist[x["horse_id"]][-1]["pos"] == "1")),
        fscore,
    ]


def dataset(races: list[dict], com: dict | None = None):
    """Walk the archive day by day: features for each eligible favourite from
    the state BEFORE that day, then fold the day in. Returns rows and the
    final state (everything known up to the last day held)."""
    com = comments() if com is None else com
    by_day = defaultdict(list)
    for r in races:
        by_day[r["date"]].append(r)
    st = State()
    rows = []
    for day in sorted(by_day):
        if day >= JUDGE_FROM:
            for r in by_day[day]:
                fr = favourite(r)
                if fr is None:
                    continue
                fav, run = fr
                rows.append({"day": day, "race_id": r["race_id"], "sp": _fl(fav["sp_dec"]),
                             "won": 1 if str(fav.get("position")) == "1" else 0,
                             "x": features(r, fav, run, st, day, com)})
        st.add_day(day, by_day[day])
    return rows, st


# --------------------------------------------------------------------------- #
# scoring — pure Python, so the box needs nothing new
# --------------------------------------------------------------------------- #

def load_model(path: Path = MODEL) -> dict | None:
    if not Path(path).exists():
        return None
    return json.loads(Path(path).read_text())


def contributions(model: dict, x: list[float]) -> list[float]:
    out = []
    for i, v in enumerate(x):
        v = model["median"][i] if (v is None or v != v) else v
        out.append(model["coef"][i] * (v - model["mean"][i]) / model["scale"][i])
    return out


def probability(model: dict, x: list[float]) -> float:
    z = model["intercept"] + sum(contributions(model, x))
    return 1.0 / (1.0 + math.exp(-z))


# --------------------------------------------------------------------------- #
# the 07:30 card
# --------------------------------------------------------------------------- #

def race_from_card(c: dict) -> dict:
    """A racecard in the archive's shape: the 07:30 price stands where the
    SP stood in training (the one input that cannot be the same)."""
    runners = []
    for x in c.get("runners") or []:
        odds = x.get("odds") or []
        dec = _fl(odds[0].get("decimal")) if odds else None
        runners.append({"horse_id": str(x.get("horse_id") or ""),
                        "horse": x.get("horse") or "",
                        "sp_dec": dec or 0.0, "draw": x.get("draw") or "",
                        "weight_lbs": x.get("lbs") or "", "or": x.get("ofr") or "",
                        "age": x.get("age") or "", "jockey_id": x.get("jockey_id") or "",
                        "trainer_id": x.get("trainer_id") or "", "position": ""})
    return {"date": str(c.get("date") or "")[:10], "race_id": str(c.get("race_id") or ""),
            "course": c.get("course") or "", "off": c.get("off_time") or "",
            "region": c.get("region") or "", "type": c.get("type") or "",
            "class": c.get("race_class") or "", "pattern": c.get("pattern") or "",
            "going": c.get("going") or "", "surface": c.get("surface") or "",
            "dist_f": c.get("distance_f") or c.get("dist_f") or "", "runners": runners}


def score_cards(cards: list[dict], day: str, model: dict, races: list[dict],
                com: dict | None = None) -> list[dict]:
    """Every eligible favourite on today's card with the model's probability
    and the three facts that pushed it most, best first."""
    com = comments() if com is None else com
    past = [r for r in races if r["date"] < day]
    _, st = dataset([], com)           # empty walk, then fold the whole past in
    by_day = defaultdict(list)
    for r in past:
        by_day[r["date"]].append(r)
    for d in sorted(by_day):
        st.add_day(d, by_day[d])
    out = []
    for c in cards:
        if str(c.get("race_status") or "").lower() == "result":
            continue
        race = race_from_card(c)
        fr = favourite(race)
        if fr is None:
            continue
        fav, run = fr
        x = features(race, fav, run, st, day, com)
        p = probability(model, x)
        con = contributions(model, x)
        top = sorted(range(len(con)), key=lambda i: -abs(con[i]))[:3]
        out.append({"race_id": race["race_id"], "course": race["course"], "off": race["off"],
                    "horse": fav["horse"], "horse_id": fav["horse_id"],
                    "price": _fl(fav["sp_dec"]), "prob": p, "x": x,
                    "why": [f"{FEATURES[i]} {'+' if con[i] > 0 else '-'}" for i in top]})
    out.sort(key=lambda r: (-r["prob"], r["price"]))
    return out


# --------------------------------------------------------------------------- #
# training — the study session only (scikit-learn is not on the box)
# --------------------------------------------------------------------------- #

def _fit(X, Y):
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    X = np.array(X, dtype=float)
    med = np.nanmedian(X, axis=0)
    med = np.where(np.isnan(med), 0.0, med)
    Xf = np.where(np.isnan(X), med, X)
    mean, scale = Xf.mean(axis=0), Xf.std(axis=0)
    scale = np.where(scale == 0, 1.0, scale)
    lr = LogisticRegression(C=0.1, max_iter=5000).fit((Xf - mean) / scale, Y)
    return {"median": med.tolist(), "mean": mean.tolist(), "scale": scale.tolist(),
            "coef": lr.coef_[0].tolist(), "intercept": float(lr.intercept_[0])}


def _topk(rows, key, k=2):
    t, nap = [0, 0], [0, 0]
    by = defaultdict(list)
    for r in rows:
        by[r["day"]].append(r)
    for d in by:
        for i, r in enumerate(sorted(by[d], key=lambda r: (-key(r), r["sp"]))[:k]):
            t[0] += 1; t[1] += r["won"]
            if i == 0:
                nap[0] += 1; nap[1] += r["won"]
    return t, nap


def train(path: Path = MODEL, races: list[dict] | None = None) -> str:
    from racing_edge.school.archive import load
    races = load() if races is None else races
    rows, _ = dataset(races)
    months = sorted({r["day"][:7] for r in rows})[1:]      # first month only trains
    walk = []
    for m in months:
        before = [r for r in rows if r["day"][:7] < m]
        mdl = _fit([r["x"] for r in before], [r["won"] for r in before])
        for r in rows:
            if r["day"][:7] == m:
                walk.append(dict(r, p=probability(mdl, r["x"])))
    fi = FEATURES.index("filter_score")

    def fkey(r):
        v = r["x"][fi]
        from racing_edge.school.favfilter import FLOOR
        return -99 if (v != v or v < FLOOR) else v
    ft, fn = _topk(walk, fkey)
    mt, mn = _topk(walk, lambda r: r["p"])
    model = _fit([r["x"] for r in rows], [r["won"] for r in rows])
    model.update(features=FEATURES, trained_on=f"{rows[0]['day']}..{rows[-1]['day']}",
                 n=len(rows), base_strike=sum(r["won"] for r in rows) / len(rows),
                 walk_forward={"months": months, "filter_top2": ft, "filter_nap": fn,
                               "model_top2": mt, "model_nap": mn})
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(model, indent=1))
    return (f"trained on {len(rows)} favourites ({model['trained_on']})\n"
            f"walk-forward {months[0]}..{months[-1]}:\n"
            f"  the filter  top-2 {ft[1]}/{ft[0]} = {100*ft[1]/ft[0]:.1f}%  nap {fn[1]}/{fn[0]} = {100*fn[1]/fn[0]:.1f}%\n"
            f"  the model   top-2 {mt[1]}/{mt[0]} = {100*mt[1]/mt[0]:.1f}%  nap {mn[1]}/{mn[0]} = {100*mn[1]/mn[0]:.1f}%\n"
            f"-> {path}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The favourite model")
    ap.add_argument("--train", action="store_true")
    a = ap.parse_args(argv)
    if a.train:
        print(train())
    return 0


if __name__ == "__main__":
    sys.exit(main())
