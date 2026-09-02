"""THE MASTER'S RULINGS — one table, verbatim, dated, recalled where the read happens.

The master (audit 2026-09-02, STEP 6): "Every ruling I give in chat is stored the
hour I give it, verbatim and dated, in one table the reads actually recall at the
point of use, with a text twin, and every recall counted so the audit can name
knowledge never consulted."

The table IS its text twin: data/rulings.csv, git-tracked, one row per ruling —
date, source, tags, the ruling verbatim, recalls. `recall()` is the only reader
the deep read uses (cli/nap.py hands the rendered block to the morning prompt
beside the banked lessons) and every call increments the count of the rows it
returned; `never_consulted()` is the audit's question. Rulings are the master's
words, not rules: the rulebook (study/morningread.py) stays closed and a ruling
becomes a law only by his word or the record.
"""

from __future__ import annotations

import csv
import os
from datetime import date
from pathlib import Path

RULINGS = Path("data/rulings.csv")
FIELDS = ("date", "source", "tags", "ruling", "recalls")


def _counts_path(path: Path) -> Path:
    """RECALL COUNTS LIVE BESIDE THE TABLE, NOT IN IT (second audit, 2026-09-02):
    the table is git-tracked and the box pulls before every task — a counter
    written into the tracked CSV would dirty the box's tree and block every
    future pull. Counts go in an untracked JSON twin (data/*.json is ignored)."""
    return path.with_name(path.stem + "_recalls.json")


def _load_counts(path: Path) -> dict[str, int]:
    import json
    cp = _counts_path(path)
    try:
        return {str(k): int(v) for k, v in json.loads(cp.read_text()).items()}
    except (OSError, ValueError):
        return {}


def _save_counts(path: Path, counts: dict[str, int]) -> None:
    import json
    cp = _counts_path(path)
    cp.parent.mkdir(parents=True, exist_ok=True)
    tmp = cp.with_suffix(".tmp")
    tmp.write_text(json.dumps(counts, indent=0, sort_keys=True))
    os.replace(tmp, cp)


def load(path: Path = RULINGS) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="") as fh:
        rows = [dict(r) for r in csv.DictReader(fh)]
    counts = _load_counts(path)
    for r in rows:
        r["recalls"] = counts.get(r["ruling"], 0)
    return rows


def _save(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({**{k: r.get(k, "") for k in FIELDS}, "recalls": 0})
    os.replace(tmp, path)          # atomic: a crash mid-write never eats the table


def add(ruling: str, tags: str = "", day: date | str | None = None,
        source: str = "chat", path: Path = RULINGS) -> dict:
    """Store a ruling verbatim. Idempotent on the exact text (a re-paste is not a
    second ruling). Returns the stored row."""
    text = (ruling or "").strip()
    if not text:
        raise ValueError("a ruling needs words — refusing to store an empty row")
    rows = load(path)
    for r in rows:
        if r["ruling"] == text:
            return r
    d = day.isoformat() if isinstance(day, date) else (day or date.today().isoformat())
    row = {"date": d, "source": source, "tags": tags, "ruling": text, "recalls": 0}
    rows.append(row)
    _save(rows, path)
    return row


def recall(tags: list[str] | None = None, limit: int = 40,
           path: Path = RULINGS) -> list[dict]:
    """The point-of-use reader: returns the newest rulings (all, or those sharing a
    tag) and COUNTS the recall on every row returned."""
    rows = load(path)
    if tags:
        want = {t.strip() for t in tags if t.strip()}
        chosen = [r for r in rows
                  if want & {t.strip() for t in (r["tags"] or "").split("|")}]
    else:
        chosen = list(rows)
    chosen = sorted(chosen, key=lambda r: r["date"])[-limit:]
    if chosen:
        counts = _load_counts(path)
        for r in chosen:
            counts[r["ruling"]] = counts.get(r["ruling"], 0) + 1
            r["recalls"] = counts[r["ruling"]]
        _save_counts(path, counts)          # the table itself is never touched
    return chosen


def never_consulted(path: Path = RULINGS) -> list[dict]:
    return [r for r in load(path) if not r["recalls"]]


def render(rows: list[dict]) -> str:
    """The block the morning prompt carries — verbatim, dated, above the lessons."""
    if not rows:
        return ""
    lines = ["THE MASTER'S RULINGS (his words, verbatim, dated — they outrank every "
             "lesson below; a ruling is not a rule until he or the record says so):"]
    for r in rows:
        tag = f" [{r['tags']}]" if r.get("tags") else ""
        lines.append(f"- [{r['date']}]{tag} \"{r['ruling']}\"")
    return "\n".join(lines)
