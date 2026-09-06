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


PAST_YEARS = 1                # the results-by-DATE door serves 12 months, no more
RESULTS_DOOR_DAYS = 364       # (live, 2026-09-05: 422 'start date must be 12 months
                              # or less in the past'; 364 not 365 so the window
                              # sits INSIDE the door however the door counts a
                              # year) — earlier runnings come through the HORSES
                              # (earlier_runnings below)
CHAIN_FETCH_MAX = 60          # history fetches per race for the chain, at most
                              # (24 → 60 on 2026-09-06, "why 1 year": ~6 new
                              # horses a field reaches the ten runnings the
                              # Racing Post's own table shows; free calls,
                              # one race a morning)
CHAIN_HISTORY_LIMIT = 40      # runs per horse the chain reads


def last_year_window(day) -> tuple[str, str]:
    """±7 days around the same date a year back, the START clamped inside the
    door's 12 months — a year is 365 days, the window's far edge is not."""
    d = day - timedelta(days=365)
    start = max(d - timedelta(days=LAST_YEAR_WINDOW), day - timedelta(days=RESULTS_DOOR_DAYS))
    return start.isoformat(), (d + timedelta(days=LAST_YEAR_WINDOW)).isoformat()


def past_windows(day, years: int = PAST_YEARS) -> list[tuple[str, str]]:
    """The results-by-date windows the door will answer — one a year, and
    only those whose start sits inside RESULTS_DOOR_DAYS (law #29, the master
    2026-08-31 and twice on 2026-09-05: 'past winners give key clues'; the
    door's own limit found live the same afternoon)."""
    out = []
    for y in range(1, years + 1):
        d = day - timedelta(days=365 * y + (y // 4))      # leap days, roughly
        start = d - timedelta(days=LAST_YEAR_WINDOW)
        if (day - start).days > RESULTS_DOOR_DAYS:
            start = day - timedelta(days=RESULTS_DOOR_DAYS)
            if start > d + timedelta(days=LAST_YEAR_WINDOW):
                break                                     # the whole window is beyond the door
        out.append((start.isoformat(), (d + timedelta(days=LAST_YEAR_WINDOW)).isoformat()))
    return out


def same_race_last_year(raw_results: dict, race) -> dict | None:
    """The race a year ago that best matches today's (same course, trip within
    half a furlong, names alike) — {date, name, winner, winner_sp, runners:
    {horse_id: (pos, field, sp, or)}} or None."""
    best, best_score = None, 0.0
    for rr in (raw_results or {}).get("results") or []:
        score = match_score(race, rr.get("course"), rr.get("race_name"), rr.get("dist_f"),
                            rr.get("class"))
        if score > best_score:
            best, best_score = rr, score
    if best is None or best_score < MATCH_MIN:
        return None
    return _entry(best)


MATCH_MIN = 0.45


def match_score(race, course, race_name, dist_f, race_class=None) -> float:
    """How much a past race looks like today's: same course (else 0), trip
    within half a furlong (else 0), the sponsor-stripped names alike, a
    class match worth a little."""
    if _norm_course(course) != _norm_course(race.course):
        return 0.0
    try:
        d = float(str(dist_f or "0").rstrip("f"))
    except ValueError:
        d = 0.0
    want_d = float(race.distance_f or 0)
    if want_d and abs(d - want_d) > 0.5:
        return 0.0
    want_n = _strip_sponsor(getattr(race, "race_name", "") or "")
    sim = difflib.SequenceMatcher(None, want_n, _strip_sponsor(race_name)).ratio()
    want_cls = str(race.race_class or "")
    cls_same = "".join(ch for ch in str(race_class or "") if ch.isdigit()) == want_cls
    return sim + (0.15 if cls_same and want_cls else 0.0)


def _entry(best: dict) -> dict:
    """One roll entry from a raw race document (the results-by-date page or
    the results-by-id door — the same shape)."""
    runners = {}
    win = None
    lbs = []
    for x in best.get("runners") or []:
        try:
            pos = int(x.get("position"))
        except (TypeError, ValueError):
            pos = None
        runners[str(x.get("horse_id"))] = (pos, len(best.get("runners") or []),
                                           x.get("sp_dec"), x.get("or"))
        try:
            lbs.append(int(x.get("weight_lbs") or 0))
        except (TypeError, ValueError):
            pass
        if pos == 1:
            win = x
    w = win or {}
    try:
        w_lbs = int(w.get("weight_lbs") or 0) or None
    except (TypeError, ValueError):
        w_lbs = None
    return {"date": best.get("date"), "name": best.get("race_name"),
            "race_id": best.get("race_id") or "",
            "winner": w.get("horse", "?"), "winner_sp": w.get("sp_dec"),
            "winner_or": w.get("or"), "runners": runners,
            "winner_wt": w.get("weight") or "", "winner_lbs": w_lbs,
            "top_weight_won": bool(w_lbs and lbs and w_lbs >= max(lbs)),
            "winner_fav": bool(str(w.get("sp") or "").upper().endswith("F")
                               or str(w.get("sp") or "").upper().endswith("J")),
            "winner_trainer": w.get("trainer") or "", "winner_jockey": w.get("jockey") or "",
            "winner_draw": w.get("draw") or "", "field": len(runners)}


def past_winners_roll(raw_by_year, race) -> list[dict]:
    """The same race in each past year's window, newest first — the Racing
    Post's PAST WINNERS table, from the results door."""
    roll = []
    for raw in raw_by_year or []:
        m = same_race_last_year(raw, race)
        if m:
            roll.append(m)
    roll.sort(key=lambda m: str(m.get("date") or ""), reverse=True)
    return roll


def _fmt_sp(sp_dec) -> str:
    try:
        return f"{float(sp_dec):.2f}"
    except (TypeError, ValueError):
        return "?"


def race_dna(roll: list[dict]) -> list[str]:
    """Law #29 in lines: the roll, then the shape written down — the weight
    band the winners carried, how often the top weight won, how often the
    favourite, which yards keep winning it. Facts, no verdict."""
    if not roll:
        return []
    lines = [f"THIS RACE, PAST WINNERS ({len(roll)} runnings): " + " · ".join(
        f"{str(m['date'])[:4]} {m['winner']} {m['winner_wt'] or '?'} SP {_fmt_sp(m['winner_sp'])}"
        f"{' (fav)' if m['winner_fav'] else ''} off {m['winner_or'] or '?'}"
        f" ({m['winner_trainer'] or '?'}/{m['winner_jockey'] or '?'}"
        f"{', dr ' + str(m['winner_draw']) if m['winner_draw'] else ''})"
        for m in roll)]
    lbs = [m["winner_lbs"] for m in roll if m.get("winner_lbs")]
    parts = []
    if lbs:
        lo, hi = min(lbs), max(lbs)
        parts.append(f"winners carried {lo // 14}-{lo % 14} to {hi // 14}-{hi % 14}")
        parts.append(f"top weight won {sum(1 for m in roll if m['top_weight_won'])}/{len(roll)}")
    parts.append(f"favourite won {sum(1 for m in roll if m['winner_fav'])}/{len(roll)}")
    yards: dict[str, int] = defaultdict(int)
    for m in roll:
        if m["winner_trainer"]:
            yards[m["winner_trainer"]] += 1
    rep = [f"{t} {n}" for t, n in sorted(yards.items(), key=lambda kv: -kv[1]) if n >= 2]
    if rep:
        parts.append("yards that keep winning it: " + ", ".join(rep))
    lines.append("THE RACE'S DNA (#29): " + " · ".join(parts))
    return lines


def dna_fit_line(roll: list[dict], runner) -> tuple[str, str] | None:
    """Does today's runner fit the winners' weight band? (the master, law #29:
    'whether today's candidates fit it') — the line either way when the roll
    holds three runnings or more and the runner's weight is known."""
    lbs = [m["winner_lbs"] for m in roll if m.get("winner_lbs")]
    w = getattr(runner, "weight_lbs", None)
    if len(lbs) < 3 or not w:
        return None
    lo, hi = min(lbs), max(lbs)
    if lo <= w <= hi:
        return f"carries {w // 14}-{w % 14}: inside the winners' band ({len(lbs)} runnings)", "fits DNA weight"
    side = "above" if w > hi else "below"
    return (f"carries {w // 14}-{w % 14}: {side} every winner of this race in "
            f"{len(lbs)} runnings ({lo // 14}-{lo % 14} to {hi // 14}-{hi % 14})",
            f"{side} DNA weight")


# --------------------------------------------------------------------------- #
# the workaround (the master, 2026-09-05: "find a workaround to find past
# winners, not just the easy way"): the results-by-DATE door stops at 12
# months, but a HORSE's own results reach back its whole career, and the
# results-by-ID door serves any race in full (live-checked on a 16-month-old
# Grade 1). So the race's earlier runnings are found THROUGH THE HORSES: every
# run in today's runners' histories and in last year's field's histories that
# matches this race by course, trip and stripped name names an earlier
# running's race_id; each id is fetched once, in full, by id.
# --------------------------------------------------------------------------- #
def _year_of(entry: dict) -> str:
    return str(entry.get("date") or "")[:4]


def earlier_runnings(client, race, histories: dict, roll: list[dict],
                     max_fetch: int = CHAIN_FETCH_MAX) -> list[dict]:
    """Extend `roll` (the runnings already held) with earlier runnings found
    through the horses. histories: {horse_id: tuple[PastRun]} for today's
    runners (already fetched by the morning read — no new call). Last year's
    field (from roll[0]) is fetched, at most max_fetch horses. Every new
    race_id goes to client.result_by_id. Returns the roll, newest first;
    never raises — a dead door is simply a shorter roll."""
    from racing_edge.data.normalise import past_runs_from_raw
    known_ids = {str(m.get("race_id") or "") for m in roll}
    known_years = {_year_of(m) for m in roll}
    found: dict[str, str] = {}                        # race_id -> year seen

    def _scan(runs):
        for h in runs:
            if not h.race_id or h.race_id in known_ids or h.race_id in found:
                continue
            if match_score(race, h.course, getattr(h, "race_name", ""), h.distance_f,
                           h.race_class) >= MATCH_MIN:
                y = str(h.date)[:4]
                if y not in known_years:
                    found[h.race_id] = y

    for hid in {r.horse_id for r in race.runners}:
        _scan(histories.get(hid, ()))
    # THE CHAIN, LINK BY LINK (the master, 2026-09-06, the Garrowby: "why 1
    # year, we need to get rid of these mistakes" — the Racing Post's table
    # held ten years; the sheet held one). Last year's field finds the year
    # before; THAT field finds the year before that; and so on until the
    # fetch budget is spent or no field names an earlier running. One hop was
    # the bug: the 2024 running was fetched and its horses never asked.
    fetched = 0
    seen_h: set[str] = set(histories)
    queue: list[str] = list((roll[0].get("runners") or {}).keys()) if roll else []
    asked_ids: set[str] = set()
    out = list(roll)
    while True:
        while queue and fetched < max_fetch:
            hid = queue.pop(0)
            if hid in seen_h:
                continue
            seen_h.add(hid)
            try:
                rows = client.horse_results(hid, limit=CHAIN_HISTORY_LIMIT)
            except Exception:
                continue
            fetched += 1
            _scan(past_runs_from_raw(rows, hid))
        new = [(rid, y) for rid, y in found.items()
               if rid not in asked_ids and y not in known_years]
        if not new:
            break
        for rid, y in sorted(new, key=lambda t: t[1], reverse=True):
            asked_ids.add(rid)
            if y in known_years:
                continue
            try:
                doc = client.result_by_id(rid)
            except Exception:
                doc = None
            if not doc or not doc.get("runners"):
                continue
            e = _entry(doc)
            e["race_id"] = rid
            out.append(e)
            known_years.add(y)
            # the next link: this running's field is asked in turn
            queue.extend(k for k in (e.get("runners") or {}) if k not in seen_h)
    out.sort(key=lambda m: str(m.get("date") or ""), reverse=True)
    return out


def deepen(client, race, histories: dict, signposts: dict, day) -> list[dict]:
    """For ONE race the reader will see: rebuild its PAST WINNERS block and
    each runner's 'ran here before' / DNA-weight dots from the roll extended
    through the horses. Mutates `signposts` in place; returns the roll."""
    held = signposts.get(f"race:{race.race_id}", {}).get("roll") or []
    roll = earlier_runnings(client, race, histories, held)
    if not roll:
        return roll
    for r in race.runners:
        ent = signposts.get(r.horse_id) or {"lines": [], "keys": []}
        keep = [(ln, k) for ln, k in zip(ent["lines"], ent["keys"])
                if not (ln.startswith("ran in this race (") or ln.startswith("carries "))]
        lines, keys = [x[0] for x in keep], [x[1] for x in keep]
        for m in roll:
            mine = m["runners"].get(r.horse_id)
            if mine:
                pos, n, sp, or_ = mine
                lines.append(f"ran in this race ({m['date']}): "
                             f"{pos or 'unplaced'} of {n} at SP {sp or '?'} off {or_ or '?'}")
                keys.append("ran here before" + (" — placed" if pos and pos <= 3 else ""))
        fit = dna_fit_line(roll, r)
        if fit:
            lines.append(fit[0]); keys.append(fit[1])
        if lines:
            signposts[r.horse_id] = {"lines": lines, "keys": keys}
        elif r.horse_id in signposts:
            del signposts[r.horse_id]
    signposts[f"race:{race.race_id}"] = {"lines": race_dna(roll), "keys": [], "roll": roll}
    return roll


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
    raw_years = ([last_year_raw] if isinstance(last_year_raw, dict)
                 else list(last_year_raw or []))
    for race in races:
        ev_by = {e.runner.horse_id: e for e in (evidence_by_race or {}).get(race.race_id, [])}
        clear = rating_clear(race)
        roll = past_winners_roll(raw_years, race) if raw_years else []
        last = roll[0] if roll else None
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
            for m in roll:
                mine = m["runners"].get(r.horse_id)
                if mine:
                    pos, n, sp, or_ = mine
                    lines.append(f"ran in this race ({m['date']}): "
                                 f"{pos or 'unplaced'} of {n} at SP {sp or '?'} off {or_ or '?'}")
                    keys.append("ran here before" + (" — placed" if pos and pos <= 3 else ""))
            if roll:
                fit = dna_fit_line(roll, r)
                if fit:
                    lines.append(fit[0]); keys.append(fit[1])
            if ev is not None:
                fs = fresh_start_line(ev.history, day)
                if fs:
                    lines.append(fs[0]); keys.append(fs[1])
            if lines:
                out[r.horse_id] = {"lines": lines, "keys": keys}
        if last:
            out.setdefault(f"race:{race.race_id}",
                           {"lines": race_dna(roll), "keys": [], "roll": roll})
    return out


def _code_of(race) -> str:
    from racing_edge.domain.units import book_code
    return book_code(getattr(race, "race_type", "")) or ""
