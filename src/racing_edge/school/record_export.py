"""THE RECORD, MADE READABLE — export nap.db to a git-tracked CSV.

The master, 2026-09-20: *"we need to do a full audit and fix on this system...
we need to make it work or quit at this point"*, and then one month to show a
return.

The audit of that day found the fault this module closes. Law 1 says the
record judges everything and picks settle at SP in `data/nap.db`. But
`.gitignore` excludes `data/*.db` — correctly, because the box writes it and
box-written artefacts are never git-tracked. The consequence went unnoticed
for weeks: **the record that judges the work cannot be read from the session
that does the work.** Every strike rate quoted in this project has therefore
been quoted from a summary of the record, or from memory, which is the least
trustworthy instrument available.

With a one-month deadline running, that is no longer a tidiness problem. It
is the instrument that measures the month. If nothing changes, the report on
day 30 is my recollection again.

WHAT THIS EXPORTS, AND WHAT IT DELIBERATELY DOES NOT:

  exports  — OUR OWN picks and their outcomes: the day, the race, the horse,
             the banked price, the SP, won/lost, and the same for the
             SP-favourite benchmark line the ledger already keeps.
  does NOT — any raw card, any field, any runner we did not back. Nothing
             here is corpus data, so the standing rule against committing
             raw material dated after 2026-08-14 is not touched: this is the
             record of our own bets, which is the one thing that must be
             auditable.

The export is DERIVED and rewritten wholesale each run. It is never the
source of truth — `nap.db` is — so a corrupt or stale CSV is fixed by
re-running, never by editing. The record itself is still never edited
(law 1); this only copies it into a form the repo can hold.

Usage:
    PYTHONPATH=src python -m racing_edge.school.record_export
    PYTHONPATH=src python -m racing_edge.school.record_export --db data/nap.db \
        --csv data/record.csv --md docs/THE_RECORD.md
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

DB = Path("data/nap.db")
CSV_OUT = Path("data/record.csv")
MD_OUT = Path("docs/THE_RECORD.md")

# The first morning under the rebuilt read, mirrored from study.naplog.V2_FROM.
# Kept as a literal so the export can run against a copied db with no import.
V2_FROM = "2026-09-03"

FIELDS = ["date", "engine", "course", "race_id", "horse", "banked_price",
          "sp_dec", "won", "confident", "status",
          "fav_horse", "fav_sp", "fav_won"]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"pragma table_info({table})")}


# nap.db's `won` column is NOT a boolean. Discovered 2026-09-23, the first
# night the record could actually be read:
#     1  won        0  lost       -1  named pass       -2  void
# The first version of this function did `"WON" if row["won"] else "LOST"`,
# and -1 and -2 are TRUTHY — so all thirteen named passes and all three voids
# were reported as WINS. It also looked for a BLANK horse to spot a pass, but
# the engine writes the horse as "NO BET". Sixteen of seventy-eight rows were
# wrong, and the instrument built to make the record honest was the thing
# lying about it.
WON, LOST, PASS, VOID = 1, 0, -1, -2


def _status(row: dict) -> str:
    """A pass is a position, not a win and not a missing day.

    ORDER MATTERS. The pass test comes FIRST, because a pass is a pass whether
    or not anything has settled it — asking "is it pending?" before "is it a
    pass?" turns today's declined day into a bet awaiting a result."""
    horse = (row.get("horse") or "").strip().upper()
    w = row.get("won")
    if w == PASS or horse in ("", "NO BET"):
        return "PASS"
    if w == VOID:
        return "VOID"
    if w is None:
        return "PENDING"
    return "WON" if w == WON else "LOST"


def rows(db: Path = DB) -> list[dict]:
    """Every banked day, oldest first, with the favourite line beside it."""
    if not Path(db).exists():
        return []
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "nap"):
            return []
        naps = [dict(r) for r in conn.execute("SELECT * FROM nap ORDER BY date")]
        favs: dict[str, dict] = {}
        if _table_exists(conn, "favline"):
            favs = {r["date"]: dict(r)
                    for r in conn.execute("SELECT * FROM favline")}
        has_conf = "confident" in _cols(conn, "nap")
    finally:
        conn.close()

    out = []
    for n in naps:
        f = favs.get(n["date"], {})
        out.append({
            "date": n["date"],
            "engine": "v2" if n["date"] >= V2_FROM else "v1",
            "course": n.get("course") or "",
            "race_id": n.get("race_id") or "",
            "horse": n.get("horse") or "",
            "banked_price": n.get("price"),
            "sp_dec": n.get("sp_dec"),
            "won": "" if n.get("won") is None else int(n["won"]),
            "confident": int(n.get("confident") or 0) if has_conf else "",
            "status": _status(n),
            "fav_horse": f.get("horse") or "",
            "fav_sp": f.get("sp_dec"),
            "fav_won": "" if f.get("won") is None else int(f["won"]),
        })
    return out


def _pl(settled: list[dict], won_key: str, sp_key: str) -> float:
    """Level stakes to one point a bet, settled at SP. A winner with no SP
    recorded returns the stake and nothing more — it is never guessed."""
    total = 0.0
    for r in settled:
        if r[won_key] == 1:
            sp = r.get(sp_key)
            total += (float(sp) - 1.0) if sp else 0.0
        else:
            total -= 1.0
    return total


def summarise(all_rows: list[dict]) -> dict:
    """Only WON and LOST are bets. A pass risked nothing and a void could not
    be settled; counting either as a result flatters or damns the record."""
    bets = [r for r in all_rows if r["status"] in ("WON", "LOST", "PENDING")]
    settled = [r for r in all_rows if r["status"] in ("WON", "LOST")]
    wins = [r for r in settled if r["won"] == 1]
    fav_settled = [r for r in settled if r["fav_won"] != ""]
    fav_wins = [r for r in fav_settled if r["fav_won"] == 1]
    pl = _pl(settled, "won", "sp_dec")
    fav_pl = _pl(fav_settled, "fav_won", "fav_sp")
    return {
        "days": len(all_rows),
        "passes": sum(1 for r in all_rows if r["status"] == "PASS"),
        "voids": sum(1 for r in all_rows if r["status"] == "VOID"),
        "bets": len(bets),
        "pending": sum(1 for r in all_rows if r["status"] == "PENDING"),
        "settled": len(settled),
        "wins": len(wins),
        "strike": (100.0 * len(wins) / len(settled)) if settled else 0.0,
        "pl": pl,
        "roi": (100.0 * pl / len(settled)) if settled else 0.0,
        "fav_settled": len(fav_settled),
        "fav_wins": len(fav_wins),
        "fav_strike": (100.0 * len(fav_wins) / len(fav_settled)) if fav_settled else 0.0,
        "fav_pl": fav_pl,
        "fav_roi": (100.0 * fav_pl / len(fav_settled)) if fav_settled else 0.0,
    }


def render(all_rows: list[dict], s: dict) -> str:
    L = ["# THE RECORD — every banked day, and what it returned",
         "",
         "Derived from `data/nap.db` by "
         "`PYTHONPATH=src python -m racing_edge.school.record_export`. "
         "**Never edit this file** — edit nothing and re-run; `nap.db` is the "
         "source of truth (law 1) and this is only a readable copy of it, so "
         "the numbers can be checked from the repo instead of taken on trust.",
         "",
         "Level stakes, one point a bet, settled at SP. A pass is shown as a "
         "position, not a missing day. The favourite line is the benchmark the "
         "ledger already keeps on the same races — it is the thing to beat, "
         "never the picker.",
         ""]
    if not all_rows:
        L += ["_No record yet: `data/nap.db` is absent or empty here. On the box "
              "it is written by the 07:30 bank and the 22:00 settle._", ""]
        return "\n".join(L) + "\n"

    L += [f"**{s['settled']} settled** · {s['wins']} wins · "
          f"strike **{s['strike']:.1f}%** · P/L **{s['pl']:+.2f} pts** · "
          f"ROI **{s['roi']:+.1f}%**",
          "",
          f"**The favourite on the same races:** {s['fav_settled']} settled · "
          f"{s['fav_wins']} wins · strike {s['fav_strike']:.1f}% · "
          f"P/L {s['fav_pl']:+.2f} pts · ROI {s['fav_roi']:+.1f}%",
          "",
          f"({s['days']} days banked · {s['bets']} bets · {s['passes']} passes · "
          f"{s.get('voids', 0)} voids · {s['pending']} pending)",
          "",
          "| date | eng | course | horse | price | SP | result | fav | fav SP | fav |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in all_rows:
        def _n(v):
            return f"{float(v):.2f}" if v not in (None, "") else "-"
        fav = {1: "WON", 0: "lost"}.get(r["fav_won"], "-")
        L.append(f"| {r['date']} | {r['engine']} | {r['course']} | "
                 f"{r['horse'] or '(pass)'} | {_n(r['banked_price'])} | "
                 f"{_n(r['sp_dec'])} | {r['status']} | {r['fav_horse'] or '-'} | "
                 f"{_n(r['fav_sp'])} | {fav} |")
    return "\n".join(L) + "\n"


def export(db: Path = DB, csv_path: Path = CSV_OUT, md_path: Path = MD_OUT) -> int:
    all_rows = rows(db)
    s = summarise(all_rows)
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in all_rows:
            w.writerow(r)
    Path(md_path).parent.mkdir(parents=True, exist_ok=True)
    Path(md_path).write_text(render(all_rows, s), encoding="utf-8")
    return len(all_rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Export nap.db to a git-tracked record")
    ap.add_argument("--db", default=str(DB))
    ap.add_argument("--csv", default=str(CSV_OUT))
    ap.add_argument("--md", default=str(MD_OUT))
    a = ap.parse_args(argv)
    n = export(Path(a.db), Path(a.csv), Path(a.md))
    if n == 0:
        print(f"record export: no rows ({a.db} absent or empty) -> {a.csv}, {a.md}")
    else:
        s = summarise(rows(Path(a.db)))
        print(f"record export: {n} days -> {a.csv}, {a.md} "
              f"({s['settled']} settled, strike {s['strike']:.1f}%, "
              f"ROI {s['roi']:+.1f}%; fav ROI {s['fav_roi']:+.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
