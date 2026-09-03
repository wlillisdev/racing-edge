"""THE WHY LEDGER — the brain's other half (the master, 2026-09-03):

  "read all races every day, then check results and see what won, what lost,
   and understand why a horse won or lost. There is something to be learned
   from each horse's result. If you do this every day consistently, diligently,
   accurately, and store it and remember and recall it, you will have 30 years
   of experience just like me, sooner rather than later. I only learned from
   watching races and reverse-engineering the result, figuring out why they won
   or lost. All the information is in plain sight, you just have to know how to
   read it. The best horse wins."

The yardstick ledger (school/yardstick.py) banks every runner's MORNING read;
this module takes each race's result the same night and reverse-engineers it:
why the winner won from what was in plain sight (the morning read, the market,
the in-running comments), whether the morning read had it, and why our
top-read horse lost when it did. One model call a night for the whole card,
banked to data/school/why/<day>.csv, RECALLED the next morning for every race
of the same shape (course / code / class / trip) so the read walks in with
what happened here before and why. Nothing here is a rule until the doorbell
rings — it is memory, in his words, at scale.
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

WHY_DIR = Path("data/school/why")
MAX_RACES = 40            # one call a night; the card is rarely bigger
COMMENT_CHARS = 160

FIELDS = ["date", "race_id", "course", "off_time", "code", "race_class", "distance_f",
          "winner", "winner_mkt_rank", "winner_sp", "why_won", "told_by",
          "in_morning_read", "our_top", "our_top_finished", "why_lost", "lesson"]

SYSTEM = (
    "You are the apprentice of a handicapper with 30 years' experience. His teaching: "
    "\"I only learned from watching races and reverse-engineering the result, figuring "
    "out why they won or lost. All the information is in plain sight, you just have to "
    "know how to read it. The best horse wins.\" For EVERY race below you are given the "
    "morning read (the engine's top horses with the lenses that fired for and against "
    "them, their market rank and price) and the result (first four with SP and the "
    "in-running comment; our top-read horse's finish if it was not in the first four).\n"
    "For each race, in ONE line each, in facts not theories: WHY the winner won — the "
    "fact that was in plain sight (a lens, the market, the comment: pace, finish, class "
    "drop, mark, course form, yard); WHAT told it (name the lens or fact); whether the "
    "morning read HAD it (yes = it was the top read or a named lens fired; no = the "
    "read missed it; owed = the read could not see it); if our top-read horse lost, "
    "WHY it lost from its comment and the lenses; and one LESSON only if the race "
    "teaches something a reader could use next time (else empty). No excuses, no "
    "hedging. Answer with JSON only:\n"
    '{"races": [{"race_id": "...", "winner": "...", "why_won": "...", "told_by": "...", '
    '"in_morning_read": "yes|no|owed", "our_top": "...", "our_top_finished": "...", '
    '"why_lost": "...", "lesson": "..."}]}'
)


def _lens_list(s: str) -> str:
    return ", ".join(x for x in (s or "").split("|") if x) or "none"


def build_prompt(day, yrows: list[dict], results) -> tuple[str, list[str]]:
    """The night's brief: every race the morning read AND the results hold.
    Returns (prompt, race_ids included). Top four of the morning by score,
    first four home with SP and comment, our top horse's line if it was not
    in the first four."""
    by_race: dict[str, list[dict]] = {}
    for r in yrows:
        if str(r.get("date")) == str(day):
            by_race.setdefault(str(r["race_id"]), []).append(r)
    res_by_id = {res.race_id: res for res in results}
    blocks, ids = [], []
    for rid in sorted(by_race, key=lambda k: (by_race[k][0].get("off_time") or "")):
        res = res_by_id.get(rid)
        if res is None or not res.runners:
            continue
        rows = sorted(by_race[rid], key=lambda r: (-int(r.get("score") or 0),
                                                   int(r.get("mkt_rank") or 99)))
        r0 = rows[0]
        head = (f"RACE {rid}: {r0.get('course')} {r0.get('off_time')} — code {r0.get('code')} "
                f"Cl{r0.get('race_class') or '?'} {r0.get('distance_f') or '?'}f, "
                f"{r0.get('field_size') or len(rows)} ran, race quality {r0.get('race_quality')}")
        morning = ["  MORNING READ (top by score):"]
        for r in rows[:4]:
            morning.append(
                f"    {r.get('horse')} — mkt {r.get('mkt_rank')} @{r.get('price')}, score "
                f"{r.get('score')}, for: {_lens_list(r.get('aligned'))}; against: "
                f"{_lens_list(r.get('flags'))}; cautions: {_lens_list(r.get('cautions'))}")
        finishers = sorted([x for x in res.runners if x.position],
                           key=lambda x: x.position)
        result = ["  RESULT:"]
        for x in finishers[:4]:
            result.append(f"    {x.position}. {x.horse or x.horse_id} SP {x.sp_dec or '?'} — "
                          f"'{(x.comment or '')[:COMMENT_CHARS]}'")
        top = r0
        mine = res.of(str(top.get("horse_id")))
        if mine is not None and (not mine.position or mine.position > 4):
            fin = mine.position or (mine.status or "did not finish")
            result.append(f"    OUR TOP READ {top.get('horse')} finished {fin} SP "
                          f"{mine.sp_dec or '?'} — '{(mine.comment or '')[:COMMENT_CHARS]}'")
        blocks.append("\n".join([head] + morning + result))
        ids.append(rid)
        if len(ids) >= MAX_RACES:
            break
    prompt = (f"THE CARD OF {day} — {len(ids)} races read this morning and resulted "
              f"tonight. Reverse-engineer every one.\n\n" + "\n\n".join(blocks))
    return prompt, ids


def parse(text: str) -> list[dict]:
    """The model's JSON, or [] — never a crash (the night must go on)."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return []
    try:
        d = json.loads(m.group())
    except json.JSONDecodeError:
        return []
    out = []
    for r in d.get("races") or []:
        if not isinstance(r, dict) or not r.get("race_id"):
            continue
        out.append({k: str(r.get(k) or "").strip() for k in
                    ("race_id", "winner", "why_won", "told_by", "in_morning_read",
                     "our_top", "our_top_finished", "why_lost", "lesson")})
    return out


def bank(day, rows: list[dict], yrows: list[dict], results, root: Path = WHY_DIR) -> Path:
    """One file a night, overwritten whole (idempotent). The race's shape and
    the winner's market rank and SP ride in from the yardstick and the result,
    so recall can match on shape without re-reading anything."""
    root.mkdir(parents=True, exist_ok=True)
    shape: dict[str, dict] = {}
    for r in yrows:
        if str(r.get("date")) == str(day):
            shape.setdefault(str(r["race_id"]), r)
    ranks: dict[str, dict[str, dict]] = {}
    for r in yrows:
        if str(r.get("date")) == str(day):
            ranks.setdefault(str(r["race_id"]), {})[str(r.get("horse_id"))] = r
    res_by_id = {res.race_id: res for res in results}
    path = root / f"{day}.csv"
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            rid = r["race_id"]
            s = shape.get(rid, {})
            res = res_by_id.get(rid)
            win = next((x for x in (res.runners if res else ()) if x.position == 1), None)
            wrow = ranks.get(rid, {}).get(str(win.horse_id), {}) if win else {}
            w.writerow({
                "date": str(day), "race_id": rid, "course": s.get("course", ""),
                "off_time": s.get("off_time", ""), "code": s.get("code", ""),
                "race_class": s.get("race_class", ""), "distance_f": s.get("distance_f", ""),
                "winner": (win.horse if win and win.horse else r.get("winner", "")),
                "winner_mkt_rank": wrow.get("mkt_rank", ""),
                "winner_sp": (win.sp_dec if win else ""),
                "why_won": r.get("why_won", ""), "told_by": r.get("told_by", ""),
                "in_morning_read": r.get("in_morning_read", ""),
                "our_top": r.get("our_top", ""), "our_top_finished": r.get("our_top_finished", ""),
                "why_lost": r.get("why_lost", ""), "lesson": r.get("lesson", ""),
            })
    return path


def load(root: Path = WHY_DIR, days: int | None = None) -> list[dict]:
    """Every banked why, oldest first (optionally the trailing N day files)."""
    files = sorted(root.glob("*.csv")) if root.exists() else []
    if days:
        files = files[-days:]
    out: list[dict] = []
    for f in files:
        with open(f, newline="") as fh:
            out.extend(csv.DictReader(fh))
    return out


def _num(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def recall(course: str, code: str, race_class, distance_f, rows: list[dict] | None = None,
           n: int = 8, root: Path = WHY_DIR) -> list[str]:
    """THE MEMORY, RECALLED (the master: "store it and remember and recall
    it"): the most recent whys of the same SHAPE — same course scores 2, same
    code 1, class within one 1, trip within two furlongs 1; a match needs 2+.
    Rendered one line each for the morning prompt."""
    rows = load(root) if rows is None else rows
    want_c = (course or "").strip().lower()
    cls = _num(race_class)
    dist = _num(distance_f)
    scored = []
    for r in rows:
        s = 0
        if want_c and (r.get("course") or "").strip().lower() == want_c:
            s += 2
        if code and r.get("code") == code:
            s += 1
        rc = _num(r.get("race_class"))
        if cls is not None and rc is not None and abs(rc - cls) <= 1:
            s += 1
        rd = _num(r.get("distance_f"))
        if dist is not None and rd is not None and abs(rd - dist) <= 2:
            s += 1
        if s >= 2 and r.get("why_won"):
            scored.append((s, r.get("date", ""), r))
    scored.sort(key=lambda t: (t[1], t[0]), reverse=True)
    lines = []
    for _s, _d, r in scored[:n]:
        line = (f"{r.get('date')} {r.get('course')} {r.get('off_time')} {r.get('code')} "
                f"Cl{r.get('race_class') or '?'} {r.get('distance_f') or '?'}f: "
                f"{r.get('winner')} (mkt {r.get('winner_mkt_rank') or '?'} @{r.get('winner_sp') or '?'}) "
                f"won — {r.get('why_won')} [told by: {r.get('told_by')}; "
                f"the morning read had it: {r.get('in_morning_read') or '?'}]")
        if r.get("why_lost"):
            line += f" | our top {r.get('our_top')} finished {r.get('our_top_finished')}: {r.get('why_lost')}"
        if r.get("lesson"):
            line += f" | lesson: {r.get('lesson')}"
        lines.append(line)
    return lines


def digest(rows: list[dict]) -> list[str]:
    """The night's count, for the console and health: races reverse-engineered,
    how many the morning read had, what told the winners most often."""
    if not rows:
        return ["  why ledger: nothing reverse-engineered"]
    had = Counter((r.get("in_morning_read") or "?").lower() for r in rows)
    told = Counter(w for r in rows for w in [(r.get("told_by") or "").strip().lower()] if w)
    lessons = [r.get("lesson") for r in rows if r.get("lesson")]
    out = [f"  why ledger: {len(rows)} races reverse-engineered — the morning read had "
           f"the winner: yes {had.get('yes', 0)} · no {had.get('no', 0)} · owed {had.get('owed', 0)}"]
    if told:
        out.append("  what told the winners most: " +
                   "; ".join(f"{k} ({v})" for k, v in told.most_common(5)))
    for les in lessons[:5]:
        out.append(f"  lesson: {les}")
    return out


def main(argv=None) -> int:
    import argparse

    from racing_edge.domain.units import uk_today
    ap = argparse.ArgumentParser(description="THE WHY LEDGER — reverse-engineer the card")
    ap.add_argument("--day", default=uk_today().isoformat())
    ap.add_argument("--root", default=str(WHY_DIR))
    a = ap.parse_args(argv)
    day = date.fromisoformat(a.day)
    from racing_edge.school.yardstick import load as yload
    yrows = [r for r in yload() if str(r.get("date")) == a.day]
    if not yrows:
        print(f"why ledger {a.day}: no morning reads banked for the day — nothing to "
              "reverse-engineer (the yardstick banks from the first 07:30 after it landed)")
        return 0
    from racing_edge.data.client import get_client
    from racing_edge.data.normalise import results_from_raw
    results = results_from_raw(get_client().results_by_date(a.day))
    prompt, ids = build_prompt(day, yrows, results)
    if not ids:
        print(f"why ledger {a.day}: {len(yrows)} reads but no results yet — tomorrow's night")
        return 0
    from racing_edge.ai.reason import get_reasoner
    reasoner = get_reasoner("study", max_tokens=6000)
    if reasoner is None:
        print("why ledger: model OFF (no ANTHROPIC_API_KEY) — nothing reverse-engineered")
        return 0
    text = reasoner(SYSTEM, prompt)
    rows = parse(text)
    if not rows:
        print(f"why ledger {a.day}: the model answered nothing parseable — {len(ids)} races "
              "unlearned tonight (fail loud)")
        return 1
    path = bank(day, rows, yrows, results, Path(a.root))
    print(f"why ledger {a.day}: {len(rows)} of {len(ids)} races banked → {path}")
    for line in digest(rows):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
