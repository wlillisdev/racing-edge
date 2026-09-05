"""SIGNPOSTS — the master's "AI back in the day" (2026-09-05: "here is some
information we can look at, it is my AI back in the day... implement all of
these, they are another dot").

The Racing Post's Signposts page is structured pointers, no opinions:
trainer and jockey combinations, the rating clearest in a handicap, the yard
at the course by race type, the same race last year, the horse that has won
fresh before, the yard gone cold. Every one of them is derivable from data the
system already pays for (the yard's jockey table, the card's own ratings, the
corpus of resulted races, the results door, the horse's history).

They enter the system as DOTS, never as rules: one block per runner in the
pre-race readout the deep read reasons over, and one column in the yardstick
ledger so the record grades each one against the market's expectation before
anyone thinks of carving it. Nothing here moves the engine's score.
"""
from __future__ import annotations

import difflib
from collections import defaultdict
from datetime import date, timedelta

# the master's own bar for "meaningful" (Signposts prints nothing under 3 wins)
COMBO_MIN_RIDES = 5
COURSE_TYPE_MIN_RUNS = 5
RATING_CLEAR_LB = 3
FRESH_DAYS = 180
COLD_YARD_DAYS = 45
LAST_YEAR_WINDOW = 7          # ± days around the same date last year


# --------------------------------------------------------------------------- #
# 1. the jockey/trainer combination
# --------------------------------------------------------------------------- #
def combo_line(rides: int, wins: int) -> tuple[str, str] | None:
    """('combo 5-8 63%', key) when the rider has enough rides for the yard."""
    if rides < COMBO_MIN_RIDES:
        return None
    pct = 100.0 * wins / rides
    key = "combo 33%+" if pct >= 33 else ("combo 20%+" if pct >= 20 else "combo cold")
    return f"jockey/trainer combo {wins}-{rides} {int(pct + 0.5)}%", key


# --------------------------------------------------------------------------- #
# 2. rating clear (the Postmark pick)
# --------------------------------------------------------------------------- #
def rating_clear(race) -> tuple[str, int] | None:
    """(horse_id, margin) of the runner whose card rating is clearest in a
    HANDICAP, when the margin is RATING_CLEAR_LB or more. The Postmark read
    off the card's own performance_rating (rpr as the fallback)."""
    if not getattr(race, "is_handicap", False):
        return None
    rated = []
    for r in race.runners:
        v = r.performance_rating if r.performance_rating is not None else r.rpr
        if v is not None:
            rated.append((int(v), r.horse_id))
    if len(rated) < 2:
        return None
    rated.sort(reverse=True)
    margin = rated[0][0] - rated[1][0]
    return (rated[0][1], margin) if margin >= RATING_CLEAR_LB else None


# --------------------------------------------------------------------------- #
# 3. the yard at the course by race type, 5. the cold yard — from the corpus
# --------------------------------------------------------------------------- #
def _norm_course(s: str) -> str:
    return (s or "").strip().lower().replace(" (ire)", "")


def yard_tables(corpus_races) -> tuple[dict, dict]:
    """From school.mine.load_corpus's races: ({(trainer_id, course, code):
    [runs, wins]}, {trainer_id: (last win date, runs since)}) — ONE pass."""
    by_ct: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
    runs: dict[str, list[tuple[str, bool]]] = defaultdict(list)
    for race in corpus_races:
        for r in race:
            tid = str(r.trainer or "")
            if not tid or tid == "0":
                continue
            key = (tid, _norm_course(r.course), (r.rtype or "")[:1].upper())
            won = str(r.pos) == "1"
            by_ct[key][0] += 1
            by_ct[key][1] += int(won)
            runs[tid].append((r.date, won))
    cold: dict[str, tuple[str, int]] = {}
    for tid, rr in runs.items():
        rr.sort()
        last_win = ""
        since = 0
        for d, won in rr:
            if won:
                last_win, since = d, 0
            else:
                since += 1
        cold[tid] = (last_win, since)
    return dict(by_ct), cold


def course_type_line(tables: dict, trainer_id: str, course: str, code: str) -> tuple[str, str] | None:
    runs, wins = tables.get((str(trainer_id), _norm_course(course), (code or "")[:1].upper()), (0, 0))
    if runs < COURSE_TYPE_MIN_RUNS:
        return None
    pct = 100.0 * wins / runs
    name = {"F": "flat", "H": "hurdles", "C": "chases", "N": "bumpers"}.get((code or "")[:1].upper(), code)
    key = ("yard here/" + name + " 25%+") if pct >= 25 else ("yard here/" + name + " cold" if pct < 8 else "")
    return f"yard at this course in {name}: {wins}-{runs} {pct:.0f}% (corpus)", key


def cold_yard_line(cold: dict, trainer_id: str, today) -> tuple[str, str] | None:
    last_win, since = cold.get(str(trainer_id), ("", 0))
    if not last_win:
        return None
    days = (today - date.fromisoformat(last_win)).days
    if days < COLD_YARD_DAYS:
        return None
    return f"yard's last winner in the corpus {last_win} ({days} days, {since} runs since)", "cold yard"


# --------------------------------------------------------------------------- #
# 4. the same race last year — from a results window on the proven door
# --------------------------------------------------------------------------- #
def _strip_sponsor(name: str) -> str:
    words = [w for w in (name or "").lower().replace("(", " ").replace(")", " ").split()
             if not any(ch.isdigit() for ch in w)]
    drop = {"stakes", "handicap", "the", "and", "&", "race", "gbb", "gbbplus", "plus",
            "heritage", "class", "of", "at", "on", "for", "to", "a", "in"}
    return " ".join(w for w in words if w not in drop)


def last_year_window(day) -> tuple[str, str]:
    d = day - timedelta(days=365)
    return ((d - timedelta(days=LAST_YEAR_WINDOW)).isoformat(),
            (d + timedelta(days=LAST_YEAR_WINDOW)).isoformat())


def same_race_last_year(raw_results: dict, race) -> dict | None:
    """The race a year ago that best matches today's (same course, trip within
    half a furlong, names alike) — {date, name, winner, winner_sp, runners:
    {horse_id: (pos, field, sp, or)}} or None."""
    want_c = _norm_course(race.course)
    want_d = float(race.distance_f or 0)
    want_n = _strip_sponsor(getattr(race, "race_name", "") or "")
    want_cls = str(race.race_class or "")
    best, best_score = None, 0.0
    for rr in (raw_results or {}).get("results") or []:
        if _norm_course(rr.get("course")) != want_c:
            continue
        try:
            d = float(str(rr.get("dist_f") or "0").rstrip("f"))
        except ValueError:
            d = 0.0
        if want_d and abs(d - want_d) > 0.5:
            continue
        sim = difflib.SequenceMatcher(None, want_n, _strip_sponsor(rr.get("race_name"))).ratio()
        cls_same = "".join(ch for ch in str(rr.get("class") or "") if ch.isdigit()) == want_cls
        score = sim + (0.15 if cls_same and want_cls else 0.0)
        if score > best_score:
            best, best_score = rr, score
    if best is None or best_score < 0.45:
        return None
    runners = {}
    win = None
    for x in best.get("runners") or []:
        try:
            pos = int(x.get("position"))
        except (TypeError, ValueError):
            pos = None
        runners[str(x.get("horse_id"))] = (pos, len(best.get("runners") or []),
                                           x.get("sp_dec"), x.get("or"))
        if pos == 1:
            win = x
    return {"date": best.get("date"), "name": best.get("race_name"),
            "winner": (win or {}).get("horse", "?"), "winner_sp": (win or {}).get("sp_dec"),
            "winner_or": (win or {}).get("or"), "runners": runners}


# --------------------------------------------------------------------------- #
# 6. fresh start — from the history we already hold
# --------------------------------------------------------------------------- #
def fresh_start_line(hist, today) -> tuple[str, str] | None:
    """When today is a run after FRESH_DAYS off: has the horse WON after such
    a break before? The line either way, so the reader knows."""
    runs = sorted(hist, key=lambda h: h.date)
    if not runs:
        return None
    gap_today = (today - runs[-1].date).days
    if gap_today < FRESH_DAYS:
        return None
    won_fresh = [(runs[i].date, (runs[i].date - runs[i - 1].date).days)
                 for i in range(1, len(runs))
                 if (runs[i].date - runs[i - 1].date).days >= FRESH_DAYS and runs[i].won]
    if won_fresh:
        d, g = won_fresh[-1]
        return f"fresh ({gap_today} days) — has WON fresh before: {d} after {g} days", "won fresh before"
    return f"fresh ({gap_today} days) — never won after a break this long", "fresh, never won fresh"


# --------------------------------------------------------------------------- #
# the assembly: one block per runner
# --------------------------------------------------------------------------- #
def build(day, races, evidence_by_race: dict, corpus_races=None,
          last_year_raw: dict | None = None) -> dict[str, dict]:
    """{horse_id: {"lines": [...], "keys": [...]}} for every runner of every
    race given. races: iterable of Race; evidence_by_race: {race_id:
    list[RunnerEvidence]}; corpus_races from school.mine.load_corpus (or
    None); last_year_raw the raw results document for last year's window
    (or None). Never raises on a missing source — the dot is simply absent."""
    out: dict[str, dict] = {}
    tables, cold = yard_tables(corpus_races) if corpus_races else ({}, {})
    for race in races:
        ev_by = {e.runner.horse_id: e for e in (evidence_by_race or {}).get(race.race_id, [])}
        clear = rating_clear(race)
        last = same_race_last_year(last_year_raw, race) if last_year_raw else None
        code = getattr(race, "code_letter", None) or _code_of(race)
        for r in race.runners:
            lines, keys = [], []
            ev = ev_by.get(r.horse_id)
            if ev is not None:
                c = combo_line(ev.combo_rides, ev.combo_wins)
                if c:
                    lines.append(c[0]); keys.append(c[1])
            if clear and clear[0] == r.horse_id:
                lines.append(f"rating clear in the handicap by {clear[1]}lb (the Postmark)")
                keys.append("rating clear")
            if tables:
                ct = course_type_line(tables, r.trainer_id, race.course, code)
                if ct:
                    lines.append(ct[0])
                    if ct[1]:
                        keys.append(ct[1])
                cy = cold_yard_line(cold, r.trainer_id, day)
                if cy:
                    lines.append(cy[0]); keys.append(cy[1])
            if last:
                mine = last["runners"].get(r.horse_id)
                if mine:
                    pos, n, sp, or_ = mine
                    lines.append(f"ran in this race last year ({last['date']}): "
                                 f"{pos or 'unplaced'} of {n} at SP {sp or '?'} off {or_ or '?'}")
                    keys.append("ran here last year" + (" — placed" if pos and pos <= 3 else ""))
            if ev is not None:
                fs = fresh_start_line(ev.history, day)
                if fs:
                    lines.append(fs[0]); keys.append(fs[1])
            if lines:
                out[r.horse_id] = {"lines": lines, "keys": keys}
        if last:
            out.setdefault(f"race:{race.race_id}", {"lines": [
                f"THIS RACE LAST YEAR ({last['date']}): won by {last['winner']} at SP "
                f"{last['winner_sp'] or '?'} off {last['winner_or'] or '?'}"], "keys": []})
    return out


def _code_of(race) -> str:
    from racing_edge.domain.units import book_code
    return book_code(getattr(race, "race_type", "")) or ""
