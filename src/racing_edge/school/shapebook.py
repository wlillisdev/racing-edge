"""THE SHAPE BOOK — the master's race-type memory, rebuilt from the record.

Born 2026-08-30, his words: "when I say shape of race, to me it is: I have
seen a similar race previously, read the form of it, and know from
experience that this type of race the winner will come from 2nd or 3rd
favourite, or the fav is a good thing. This is why it's important that you
have this stored and building on it so you can leverage this knowledge as
we move forward."

Thirty years gives him retrieval over every similar race he has watched.
This module gives the student the same memory: every race in the corpus is
fingerprinted (code x class-band x field-band x favourite-strength) and the
book records, for each shape, WHERE THE WINNER CAME FROM — favourite,
2nd-3rd in the market, or beyond. Descriptive priors, not betting angles:
the earlier mine hunted ROI cells and the month-stability bars rightly
killed them; strike-by-market-rank per shape is the stabler, humbler
question the master actually asks. Re-run as results accrue — the memory
grows with the record ("building on it as we move forward").

Known v1 limit, named honestly: the corpus rows carry no handicap flag, so
the fingerprint cannot yet split handicaps from conditions races. That
column joins when the corpus loader next runs.

Usage: PYTHONPATH=src python -m racing_edge.school.shapebook \
           [--raw data/school/raw] [--out docs/SHAPE_BOOK.md] [--min-n 30]
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from statistics import median

from racing_edge.school.mine import load_corpus


def _class_band(rclass: int) -> str:
    if rclass in (1, 2):
        return "Cl1-2"
    if rclass in (3, 4):
        return "Cl3-4"
    if rclass == 5:
        return "Cl5"
    if rclass >= 6:
        return "Cl6+"
    return "unclassed"


def _field_band(n: int) -> str:
    if n <= 7:
        return "2-7"
    if n <= 11:
        return "8-11"
    if n <= 15:
        return "12-15"
    return "16+"


def _fav_band(fav_sp: float) -> str:
    # decimal SP of the market leader: how strong is the anchor?
    if fav_sp < 2.5:
        return "fav<6/4"
    if fav_sp <= 4.0:
        return "fav 6/4-3/1"
    return "fav>3/1"


def build(raw: Path, min_n: int = 30):
    cells: dict[tuple, dict] = defaultdict(
        lambda: {"n": 0, "fav": 0, "r2": 0, "r3": 0, "out": 0,
                 "no_win": 0, "win_sps": []})
    for race in load_corpus(raw):
        priced = sorted([r for r in race if r.sp > 1.0], key=lambda r: r.sp)
        if len(priced) < 2:
            continue
        winner = next((r for r in priced if r.pos == "1"), None)
        key = (priced[0].rtype, _class_band(priced[0].rclass),
               _field_band(len(priced)), _fav_band(priced[0].sp))
        c = cells[key]
        c["n"] += 1
        if winner is None:            # winner unpriced/void — count the race,
            c["no_win"] += 1          # never guess the rank
            continue
        rank = priced.index(winner) + 1
        if rank == 1:
            c["fav"] += 1
        elif rank == 2:
            c["r2"] += 1
        elif rank == 3:
            c["r3"] += 1
        else:
            c["out"] += 1
        c["win_sps"].append(winner.sp)
    return {k: v for k, v in cells.items() if v["n"] >= min_n}


def triage(c: dict) -> str:
    """The master's glance, spoken (his word, 2026-08-30: "you need to get
    to the point where you will read a race and say: oh I know this type,
    it is best avoided — or this is the one where we will find a gem, or
    get on the jolly"). Descriptive labels on the shape's own record —
    thresholds present the data, they are not betting rules."""
    decided = max(c["n"] - c["no_win"], 1)
    fav = 100 * c["fav"] / decided
    top3 = 100 * (c["fav"] + c["r2"] + c["r3"]) / decided
    if fav >= 45 and top3 >= 85:
        return "GET ON THE JOLLY — the fav is a good thing; don't get clever"
    if top3 >= 78 and fav < 40:
        return "GEM BEHIND THE JOLLY — front of market but often NOT the fav: 2nd-3rd fav hunting ground"
    if top3 < 65:
        return "BEST AVOIDED — lottery shape; never a nap, bandit water only"
    return "FULL READ DECIDES — no strong shape prior"


def render(cells: dict, raw: Path, min_n: int) -> str:
    total = sum(c["n"] for c in cells.values())
    lines = [
        "# THE SHAPE BOOK — where winners come from, by race type",
        "",
        "(The master, 2026-08-30: \"I have seen a similar race previously...",
        "know from experience that this type of race the winner will come",
        "from 2nd or 3rd favourite, or the fav is a good thing... have this",
        "stored and building on it.\" His memory, rebuilt from the record.",
        f"Corpus: {total} races with a priced field, cells shown at "
        f"n>={min_n}. Regenerate after each settled stretch: "
        "`PYTHONPATH=src python -m racing_edge.school.shapebook`.",
        "V1 limit named: no handicap/non-handicap split yet — the raw rows",
        "carry no flag; joins at the next corpus refresh.)",
        "",
        "READ IT LIKE THE MASTER DOES: 'fav%' answers \"is the jolly a good",
        "thing in this shape?\"; 'top3%' answers \"does the winner come from",
        "the front of the market?\"; a LOW top3% shape is an anything-can-",
        "win lottery — the shape itself says pass or go bandit-hunting.",
        "",
        "| shape (type · class · field · fav) | n | fav% | 2nd fav% | "
        "3rd fav% | top3% | outside% | med win SP | THE GLANCE |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for key in sorted(cells, key=lambda k: -cells[k]["n"]):
        c = cells[key]
        rtype, cls, fld, fav = key
        code = {"F": "flat", "N": "jumps"}.get(rtype, rtype)
        n, decided = c["n"], max(c["n"] - c["no_win"], 1)
        top3 = c["fav"] + c["r2"] + c["r3"]
        med = f"{median(c['win_sps']):.1f}" if c["win_sps"] else "-"
        lines.append(
            f"| {code} · {cls} · {fld} · {fav} | {n} "
            f"| {100*c['fav']/decided:.0f} | {100*c['r2']/decided:.0f} "
            f"| {100*c['r3']/decided:.0f} | {100*top3/decided:.0f} "
            f"| {100*c['out']/decided:.0f} | {med} | {triage(c)} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/school/raw")
    ap.add_argument("--out", default="docs/SHAPE_BOOK.md")
    ap.add_argument("--min-n", type=int, default=30)
    a = ap.parse_args()
    cells = build(Path(a.raw), a.min_n)
    out = Path(a.out)
    out.write_text(render(cells, Path(a.raw), a.min_n))
    print(f"shape book: {len(cells)} cells -> {out}")


if __name__ == "__main__":
    main()
