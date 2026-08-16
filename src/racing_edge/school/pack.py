"""PHASE 2 Step A — PACK: build an exam packet for a past race day.

For each race on the day with 5+ runners: every runner's last 4 corpus runs
(date, course, distance, class, position, beaten lengths, SP), days since
last run, C&D wins, jockey/trainer 14-day form, and the day's SP. Results
for the day are WITHHELD from the packet; the marking key (winner, winner
SP, favourite) is written to a separate file the sitter must not open until
picks are locked.

Corpus comments are not stored (token cost of the MCP fetch); the packet
carries bare form. The production fetcher on PythonAnywhere can store
comments, so later rounds can show them.

Usage: PYTHONPATH=src python -m racing_edge.school.pack --day 2026-08-08
       [--names data/school/names/2026-08-08.csv] [--raw data/school/raw]
Writes data/school/packets/DAY.md and data/school/keys/DAY.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

from racing_edge.school.mine import Runner, _days_between, load_corpus

MIN_FIELD = 5


def _fmt_sp(sp: float) -> str:
    return f"{sp:g}" if sp else "?"


def build(day: str, raw: Path, names_file: Path | None,
          packets_dir: Path, keys_dir: Path) -> tuple[Path, Path]:
    races = load_corpus(raw)
    names: dict[str, str] = {}
    if names_file and names_file.exists():
        with open(names_file, newline="") as fh:
            names = {r[0]: r[1] for r in csv.reader(fh) if len(r) >= 2}

    hist: dict[str, list[Runner]] = defaultdict(list)
    jt: dict[str, list[tuple[str, bool]]] = defaultdict(list)
    day_races = []
    for race in races:
        d = race[0].date
        if d < day:
            for r in race:
                hist[r.horse].append(r)
                jt["j" + r.jockey].append((d, r.pos == "1"))
                jt["t" + r.trainer].append((d, r.pos == "1"))
        elif d == day:
            day_races.append(race)

    day_races = [rc for rc in day_races if len(rc) >= MIN_FIELD]
    if not day_races:
        raise SystemExit(f"no races with {MIN_FIELD}+ runners on {day} in corpus")

    def name(hid):
        return names.get(hid, f"#{hid}")

    def form14(key, before):
        lo_y, lo_m, lo_d = map(int, before.split("-"))
        from datetime import date, timedelta
        lo = (date(lo_y, lo_m, lo_d) - timedelta(days=14)).isoformat()
        rows = [w for (d, w) in jt.get(key, ()) if lo <= d < before]
        return len(rows), sum(rows)

    lines, key_rows = [], []
    lines.append(f"# EXAM PACKET — {day} (results withheld; SP shown per the "
                 f"method). Races with {MIN_FIELD}+ runners.")
    for race in day_races:
        r0 = race[0]
        cls = f"Cl{r0.rclass}" if r0.rclass else "unclassed"
        lines.append(f"\n## {r0.race_id} | {r0.course} ({r0.region}) "
                     f"{r0.rtype} {r0.dist:g}f {cls} | {len(race)} ran")
        fav = min((r for r in race if r.sp > 0), key=lambda r: (r.sp, r.horse),
                  default=None)
        winner = next((r for r in race if r.pos == "1"), None)
        key_rows.append([r0.race_id,
                         winner.horse if winner else "0",
                         _fmt_sp(winner.sp) if winner else "0",
                         fav.horse if fav else "0"])
        for r in sorted(race, key=lambda r: (r.sp or 999)):
            h = hist.get(r.horse, [])
            last4 = h[-4:][::-1]
            dsl = _days_between(h[-1].date, day) if h else None
            cd = sum(1 for p in h if p.pos == "1" and p.course == r.course
                     and p.dist == r.dist)
            jr, jw = form14("j" + r.jockey, day)
            tr_, tw = form14("t" + r.trainer, day)
            lines.append(f"\n**{name(r.horse)}** SP {_fmt_sp(r.sp)} | "
                         f"last run {dsl if dsl is not None else '?'}d ago | "
                         f"C&D wins {cd} | jky14 {jw}/{jr} | trn14 {tw}/{tr_}")
            if not last4:
                lines.append("  - no corpus form (unraced or pre-corpus)")
            for p in last4:
                pcls = f"Cl{p.rclass}" if p.rclass else "uncl"
                lines.append(f"  - {p.date} {p.course} {p.dist:g}f {pcls}: "
                             f"pos {p.pos} btn {getattr(p, 'btn', '?')} "
                             f"SP {_fmt_sp(p.sp)}")
    packets_dir.mkdir(parents=True, exist_ok=True)
    keys_dir.mkdir(parents=True, exist_ok=True)
    pk = packets_dir / f"{day}.md"
    ky = keys_dir / f"{day}.csv"
    pk.write_text("\n".join(lines))
    with open(ky, "w", newline="") as fh:
        csv.writer(fh).writerows(key_rows)
    return pk, ky


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", required=True)
    ap.add_argument("--raw", default="data/school/raw")
    ap.add_argument("--names", default=None)
    ap.add_argument("--packets", default="data/school/packets")
    ap.add_argument("--keys", default="data/school/keys")
    a = ap.parse_args(argv)
    pk, ky = build(a.day, Path(a.raw),
                   Path(a.names) if a.names else None,
                   Path(a.packets), Path(a.keys))
    print(f"packet: {pk}\nkey (DO NOT OPEN until picks locked): {ky}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
