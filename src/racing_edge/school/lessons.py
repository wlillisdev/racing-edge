"""THE LESSON REGISTER — where a repeated lesson has to go, and cannot rot.

The master, 2026-09-07: "nothing changing has to change or else it is
pointless."

He is right, and this module is the answer to it. The why ledger has
dissected ten races a night since 2026-09-03 and the weekly synthesis surfaces
what repeats. Nothing then happened. A lesson could repeat thirty times in six
weeks, be written down every time, and never become a change, a test or even a
question — because there was nowhere for it to go and nothing that noticed it
had been ignored.

Law 2 already names three ways a rule is born: he teaches it, he validates it
at the doorbell, or THE RECORD FIELD-TESTS IT. The third route was never
wired. This is the wiring, and it carves nothing:

    SURFACED  -> a lesson the ledger keeps repeating, counted, with its races
    DOORBELL  -> put to him, with the count, waiting on his word
    TESTING   -> he said test it: named test, named bar, named date
    CARVED    -> it earned belief and is in the code, with its receipt
    KILLED    -> it was tested and failed, or he struck it. Dead, and stays dead.

The only thing this module DOES is refuse to let a lesson sit at SURFACED
quietly. An open lesson older than STALE_DAYS is a RED LINE on the 09:30
health page, in the same way the receipts register turned an unreceipted rule
into a failing test. What the register cannot do is decide: promotion is his
word, always (framework #5 — a pattern the ledgers surface goes to his
doorbell, never gets carved).

Usage:
    PYTHONPATH=src python -m racing_edge.school.lessons            # the report
    PYTHONPATH=src python -m racing_edge.school.lessons --open     # only the open ones
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

from racing_edge.domain.units import uk_today

REGISTER = Path("data/lessons.csv")

# A lesson that has been open this long without his ruling is a RED LINE.
# Seven days is his own weekly rhythm: the Sunday synthesis is the moment
# every open lesson should have been put to him at least once.
STALE_DAYS = 7

STATUSES = ("SURFACED", "DOORBELL", "TESTING", "CARVED", "KILLED")
OPEN = ("SURFACED", "DOORBELL", "TESTING")

FIELDS = ["id", "first_seen", "last_seen", "count", "status", "lesson",
          "shape", "source", "test", "bar", "ruling", "outcome"]


def load(path: Path = REGISTER) -> list[dict]:
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if r.get("id")]


def save(rows: list[dict], path: Path = REGISTER) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def _int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def note(rows: list[dict], lesson_id: str, *, lesson: str = "", shape: str = "",
         source: str = "", day: str = "") -> list[dict]:
    """Record that the ledger taught this lesson again today. A new id is
    SURFACED at count 1; a known id has its count and last_seen advanced.
    Never changes a status — only he does that, and a KILLED lesson that
    resurfaces still counts, so a bad ruling is visible in the record."""
    day = day or uk_today().isoformat()
    for r in rows:
        if r["id"] == lesson_id:
            r["count"] = str(_int(r.get("count")) + 1)
            r["last_seen"] = day
            return rows
    rows.append({"id": lesson_id, "first_seen": day, "last_seen": day,
                 "count": "1", "status": "SURFACED", "lesson": lesson,
                 "shape": shape, "source": source, "test": "", "bar": "",
                 "ruling": "", "outcome": ""})
    return rows


def days_open(row: dict, today: date | None = None) -> int:
    today = today or uk_today()
    try:
        return (today - date.fromisoformat(row["first_seen"])).days
    except (ValueError, KeyError):
        return 0


def stale(rows: list[dict], today: date | None = None,
          stale_days: int = STALE_DAYS) -> list[dict]:
    """Open lessons that have sat longer than the bar — the red line. Sorted
    oldest first, because the oldest is the one that has been ignored most."""
    out = [r for r in rows if r.get("status") in OPEN
           and days_open(r, today) >= stale_days]
    return sorted(out, key=lambda r: days_open(r, today), reverse=True)


def health_line(rows: list[dict], today: date | None = None) -> tuple[bool, str]:
    """(ok, line) for the 09:30 page. NOT ok when a lesson has been open past
    the bar: the record learned something, said so, and nothing happened."""
    if not rows:
        return True, "lessons: register empty — the why ledger has taught nothing yet"
    open_rows = [r for r in rows if r.get("status") in OPEN]
    st = stale(rows, today)
    counts = {s: sum(1 for r in rows if r.get("status") == s) for s in STATUSES}
    tail = " · ".join(f"{s.lower()} {counts[s]}" for s in STATUSES if counts[s])
    if not st:
        return True, f"lessons: {len(rows)} known ({tail}); none open past {STALE_DAYS} days"
    oldest = st[0]
    return False, (
        f"LESSONS NOT ACTED ON — {len(st)} of {len(open_rows)} open lesson(s) "
        f"past {STALE_DAYS} days; oldest {days_open(oldest, today)}d: "
        f"{oldest['id']} — {oldest['lesson'][:90]}. The record learned it and "
        f"nothing changed: rule on it, test it, or kill it.")


def report(rows: list[dict], only_open: bool = False,
           today: date | None = None) -> str:
    show = [r for r in rows if r.get("status") in OPEN] if only_open else rows
    L = ["# THE LESSON REGISTER — what the record taught, and what happened next",
         "",
         "(the master, 2026-09-07: \"nothing changing has to change or else it "
         "is pointless\". A lesson enters at SURFACED and may only leave by his "
         "word. Nothing here is carved by the register.)",
         ""]
    ok, line = health_line(rows, today)
    L += [("· " if ok else "RED — ") + line, ""]
    L += ["| id | status | seen | open | lesson | next |", "|---|---|---|---|---|---|"]
    for r in sorted(show, key=lambda r: (STATUSES.index(r.get("status", "SURFACED"))
                                         if r.get("status") in STATUSES else 9,
                                         -days_open(r, today))):
        nxt = r.get("test") or r.get("ruling") or "awaiting his word"
        L.append(f"| {r['id']} | {r.get('status', '')} | {r.get('count', '')} | "
                 f"{days_open(r, today)}d | {r.get('lesson', '')[:80]} | {nxt[:60]} |")
    if len(L) == 8:
        L.append("| (none) | | | | | |")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="THE LESSON REGISTER")
    ap.add_argument("--csv", default=str(REGISTER))
    ap.add_argument("--open", action="store_true", help="only unresolved lessons")
    a = ap.parse_args(argv)
    rows = load(Path(a.csv))
    print(report(rows, only_open=a.open))
    ok, _ = health_line(rows)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
