"""THE YARDSTICK LEDGER — every runner's full read, banked and graded.

The master, 2026-09-03: "the stored races as learning data... the calibration
of the system, we need to do it, but calculated and surgical." Every morning
the engine already computes a full conviction read on EVERY runner in every
readable race (pipeline.nap.evaluate_field) and throws away everything but the
nap. From tonight that whole read is banked here — one CSV per morning, one
row per runner — and settled against the result, so the record itself can
answer which lenses lift the win rate above what the market already expects.

NOTHING HERE CHANGES A PICK OR A RULE. It records and measures only — same
posture as school/tier0.py's "a report, never a rule". The rulebook stays
closed (CLAUDE.md law 2): a rule is born only when the master teaches it,
validates it (doorbell), or the record field-tests it long enough — never
invented here, however clean a lift number looks.

Shape deliberately mirrors school/tier0.py: control = win% by market rank
(the market's own expectation), lift = a lens's actual win% minus what its
runners' market ranks alone would predict, month_test = tier0's own bar
(reused, not re-invented) for whether a lift survives month over month.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

from racing_edge.domain.units import book_code, uk_today
from racing_edge.school import tier0
from racing_edge.study.naplog import NapLog, version

LEDGER_DIR = Path("data/school/yardstick")

# one CSV per morning, this header, in this order — every reader/writer below
# agrees on it so a stray dict key never silently drops a column
FIELDS = [
    "date", "version", "race_id", "course", "off_time", "code", "race_class",
    "is_handicap", "field_size", "race_quality", "horse_id", "horse",
    "mkt_rank", "price", "score", "confident", "mark_known", "aligned",
    "flags", "cautions", "pos", "sp_dec", "won",
    "signposts",      # the master's old AI (2026-09-05) — dots, graded like a lens
]

# --------------------------------------------------------------------------- #
# lens_key — one stable key per aligned/flag/caution tag, figures stripped so
# "raised 9lb" and "raised 12lb" tally as ONE lens, not two accidental ones
# --------------------------------------------------------------------------- #
import re

_FIGURE_RE = re.compile(
    r"#?\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?\s*(?:lb|kg|f|yo|%)?"
)


def lens_key(tag: str) -> str:
    """Normalise an aligned/flag/caution label to a stable key: lowercase,
    strip anything from the first ' (' / ' —' / ':' onward (the detail —
    percentages, run counts, the '#N' footnote), then strip any figures left
    in the head of the label (a raised-mark caution names the lb in the head,
    not a parenthetical) so the SAME lens with a different number reads as
    one key, never a family of near-duplicates."""
    s = (tag or "").strip().lower()
    cuts = [i for i in (s.find(" ("), s.find(" —"), s.find(":")) if i != -1]
    if cuts:
        s = s[: min(cuts)]
    s = _FIGURE_RE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def _joined_keys(tags) -> str:
    return "|".join(dict.fromkeys(lens_key(t) for t in tags if lens_key(t)))


# --------------------------------------------------------------------------- #
# rows_from_field — one row per NapPick (duck-typed: .race .runner .price
# .conviction .race_quality — pipeline.nap.NapPick's own shape, not copied)
# --------------------------------------------------------------------------- #
def _day_str(day) -> str:
    return day.isoformat() if hasattr(day, "isoformat") else str(day)


def rows_from_field(day, field, signposts: dict | None = None) -> list[dict]:
    """field: list[NapPick] (pipeline.nap) — EVERY priced runner in EVERY
    readable race the morning read touched, not just the nap. mkt_rank is
    1..n by price WITHIN the race (ties by horse_id, the mine's own rule).
    pos/sp_dec/won start blank — settle_day fills them once the result is in.
    signposts: school.signposts.build's {horse_id: {"keys": [...]}} — each
    key lands in the row's `signposts` column, '|'-joined, so the scoreboard
    grades every Signpost against the market exactly like a lens."""
    sp = signposts or {}
    by_race: dict[str, list] = defaultdict(list)
    for p in field:
        by_race[p.race.race_id].append(p)
    d_str = _day_str(day)
    v = version(day)
    rows: list[dict] = []
    for race_id, picks in by_race.items():
        race = picks[0].race
        ranked = sorted(picks, key=lambda p: (p.price if p.price else 9e9,
                                              p.runner.horse_id))
        for i, p in enumerate(ranked, 1):
            c = p.conviction
            rows.append({
                "date": d_str,
                "version": v,
                "race_id": race_id,
                "course": race.course,
                "off_time": race.off_time,
                "code": book_code(race.race_type) or "",
                "race_class": race.race_class if race.race_class is not None else "",
                "is_handicap": int(bool(race.is_handicap)),
                "field_size": race.field_size,
                "race_quality": p.race_quality,
                "horse_id": p.runner.horse_id,
                "horse": p.runner.horse,
                "mkt_rank": i,
                "price": p.price if p.price is not None else "",
                "score": c.score,
                "confident": int(bool(c.confident)),
                "mark_known": int(bool(c.mark_known)),
                "aligned": _joined_keys(c.aligned),
                "flags": _joined_keys(c.flags),
                "cautions": _joined_keys(c.cautions),
                "pos": "",
                "sp_dec": "",
                "won": "",
                "signposts": "|".join(dict.fromkeys(
                    k for k in sp.get(p.runner.horse_id, {}).get("keys", []) if k)),
            })
    return rows


# --------------------------------------------------------------------------- #
# bank / settle_day / load — the CSV twin, one file per morning
# --------------------------------------------------------------------------- #
def _path_for(day, root: Path) -> Path:
    return root / f"{_day_str(day)}.csv"


def bank(day, field, root: Path = LEDGER_DIR, signposts: dict | None = None) -> Path:
    """Write <root>/<day>.csv, OVERWRITING that day's file — one morning, one
    file, idempotent (a re-run of the morning read re-banks the same rows,
    never appends a second copy)."""
    root.mkdir(parents=True, exist_ok=True)
    path = _path_for(day, root)
    rows = rows_from_field(day, field, signposts)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    import os
    os.replace(tmp, path)
    return path


def settle_day(day, results, root: Path = LEDGER_DIR) -> int:
    """Fill pos/sp_dec/won for the day's rows from `results` — the SAME
    list[domain.models.RaceResult] cli/nap.py's settle path holds (mirrors
    cli/nap.py:_settle_tables, ~line 379: race = next(r for r in results if
    r.race_id == row['race_id']); me = next(rr for rr in race.runners if
    rr.horse_id == row['horse_id'])). Non-runner / absent / no-status-no-
    position rows get won='' (unmeasured, the bet never happened); a fallen
    or pulled-up runner RAN and lost. Recomputed whole from `results` every
    call, so a re-run (idempotent) always lands on the same numbers. Returns
    the count of rows given a decisive win/loss this call."""
    path = _path_for(day, root)
    if not path.exists():
        return 0
    with open(path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    settled = 0
    for row in rows:
        race = next((r for r in results if r.race_id == row["race_id"]), None)
        if race is None:
            continue                          # no result for this race yet
        me = next((rr for rr in race.runners if rr.horse_id == row["horse_id"]),
                  None)
        if me is None:
            row["pos"], row["sp_dec"], row["won"] = "", "", ""
            continue                          # absent from the result — non-runner
        status = (getattr(me, "status", "") or "").upper()
        if status in NapLog.NON_RUNNER:
            row["pos"], row["sp_dec"], row["won"] = "", "", ""
            continue
        if me.position is None and not status:
            row["pos"], row["sp_dec"], row["won"] = "", "", ""
            continue                          # withdrawn, no status either
        won = 1 if me.position == 1 else 0
        row["pos"] = me.position if me.position is not None else status
        row["sp_dec"] = me.sp_dec if me.sp_dec is not None else ""
        row["won"] = won
        settled += 1
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    import os
    os.replace(tmp, path)
    return settled


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _typed(row: dict) -> dict:
    r = dict(row)
    r["race_class"] = _int(row.get("race_class"))
    r["is_handicap"] = _int(row.get("is_handicap")) or 0
    r["field_size"] = _int(row.get("field_size")) or 0
    r["race_quality"] = _int(row.get("race_quality")) or 0
    r["mkt_rank"] = _int(row.get("mkt_rank")) or 0
    r["price"] = _float(row.get("price"))
    r["score"] = _int(row.get("score")) or 0
    r["confident"] = _int(row.get("confident")) or 0
    r["mark_known"] = _int(row.get("mark_known")) or 0
    r["sp_dec"] = _float(row.get("sp_dec"))
    won_raw = row.get("won")
    r["won"] = _int(won_raw) if won_raw not in (None, "") else None
    pos_raw = row.get("pos") or ""
    r["pos"] = int(pos_raw) if str(pos_raw).lstrip("-").isdigit() else pos_raw
    return r


def load(root: Path = LEDGER_DIR, days: int | None = None) -> list[dict]:
    """Every row in the ledger, typed (ints/floats where sensible), oldest
    file first. `days` limits to the trailing N morning files."""
    if not root.exists():
        return []
    files = sorted(root.glob("*.csv"))
    if days is not None:
        files = files[-days:]
    out: list[dict] = []
    for f in files:
        with open(f, newline="") as fh:
            out.extend(_typed(row) for row in csv.DictReader(fh))
    return out


# --------------------------------------------------------------------------- #
# scoreboard — the record judging its own read, market rank as the control
# --------------------------------------------------------------------------- #
def _control(rows: list[dict]) -> dict[int, tuple[int, int]]:
    """{capped mkt_rank: (n, wins)} over SETTLED rows — the market's own
    scoreboard, exactly the idea tier0.py banks (win% by market rank)."""
    t: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["won"] not in (0, 1):
            continue
        k = min(max(r["mkt_rank"], 1), tier0.RANK_CAP)
        c = t[k]
        c[0] += 1
        c[1] += r["won"]
    return {k: (v[0], v[1]) for k, v in t.items()}


def _lens_table(rows: list[dict], field_name: str,
                rate: dict[int, float]) -> dict[str, dict]:
    """{lens key: {"n","wins","exp","months"}} — the tier0.month_test shape,
    built over settled rows carrying `field_name` (aligned/flags/cautions).
    exp is the wins the runners' market ranks alone would predict — the
    market held constant, so what's left is (or isn't) the lens's own."""
    agg: dict[str, dict] = {}
    for r in rows:
        if r["won"] not in (0, 1):
            continue
        keys = dict.fromkeys(k for k in (r.get(field_name) or "").split("|") if k)
        if not keys:
            continue
        k_rank = min(max(r["mkt_rank"], 1), tier0.RANK_CAP)
        e = rate.get(k_rank, 0.0)
        month = (r.get("date") or "")[:7]
        for k in keys:
            c = agg.setdefault(k, {"n": 0, "wins": 0, "exp": 0.0,
                                   "months": defaultdict(lambda: [0, 0, 0.0])})
            c["n"] += 1
            c["wins"] += r["won"]
            c["exp"] += e
            m = c["months"][month]
            m[0] += 1
            m[1] += r["won"]
            m[2] += e
    return agg


def _race_bands(rows: list[dict]) -> dict[str, dict]:
    """Per race-quality band (<2 below the bar, >=2 a betting race): races
    with a settled winner among these rows, favourite strike, whether the
    winner sat in the market top-3, and our own top-score horse's strike."""
    by_race: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_race[r["race_id"]].append(r)
    bands = {b: {"n": 0, "fav_n": 0, "fav_win": 0, "top3_hit": 0,
                "pick_n": 0, "pick_win": 0} for b in ("below", "betting")}
    for rs in by_race.values():
        settled = [r for r in rs if r["won"] in (0, 1)]
        winner = next((r for r in settled if r["won"] == 1), None)
        if winner is None or not settled:
            continue                          # no identified winner among priced rows
        band = "betting" if rs[0]["race_quality"] >= 2 else "below"
        b = bands[band]
        b["n"] += 1
        fav = next((r for r in settled if r["mkt_rank"] == 1), None)
        if fav is not None:
            b["fav_n"] += 1
            b["fav_win"] += fav["won"]
        b["top3_hit"] += 1 if winner["mkt_rank"] <= 3 else 0
        pick = max(settled, key=lambda r: (r["score"], -r["mkt_rank"]))
        b["pick_n"] += 1
        b["pick_win"] += pick["won"]
    return bands


def _version_table(rows: list[dict]) -> dict[str, dict]:
    """{version: {"n","wins","pnl"}} over settled rows — level stakes at SP,
    the same money gauge naplog.profit_loss uses."""
    out: dict[str, dict] = {}
    for r in rows:
        if r["won"] not in (0, 1):
            continue
        v = out.setdefault(r["version"], {"n": 0, "wins": 0, "pnl": 0.0})
        v["n"] += 1
        if r["won"] == 1:
            v["wins"] += 1
            v["pnl"] += (r["sp_dec"] or 0.0) - 1.0
        else:
            v["pnl"] -= 1.0
    return out


def _pct(n, d) -> str:
    return f"{100 * n / d:.1f}%" if d else "-"


def scoreboard(rows: list[dict]) -> str:
    """The yardstick's own report — every table headed with what it means.
    Nothing here is a rule (CLAUDE.md law 2): the master teaches, the master
    validates (doorbell), or the record field-tests long enough to earn
    belief — a clean lift number on its own buys nothing."""
    settled = [r for r in rows if r["won"] in (0, 1)]
    ctrl = _control(rows)
    rate = {k: (w / n if n else 0.0) for k, (n, w) in ctrl.items()}

    L = [
        "# THE YARDSTICK — every runner's read, banked and graded against the market",
        "",
        "(the master, 2026-09-03: \"the stored races as learning data... the "
        "calibration of the system, we need to do it, but calculated and "
        "surgical\" — this changes no pick and no rule, it only measures. "
        "NOTHING BELOW IS A RULE until the doorbell rings.)",
        "",
        f"rows banked: {len(rows)} · settled: {len(settled)}",
        "",
        "## THE CONTROL — win% by market rank, over settled rows",
        "What the market alone would have told you — everything below is measured AGAINST this.",
        "| rank | n | wins | win% |",
        "|---|---|---|---|",
    ]
    for k in sorted(ctrl):
        n, w = ctrl[k]
        lab = f"{k}" if k < tier0.RANK_CAP else f"{tier0.RANK_CAP}+"
        L.append(f"| {lab} | {n} | {w} | {_pct(w, n)} |")

    def _section(title: str, note: str, field_name: str) -> list[str]:
        agg = _lens_table(rows, field_name, rate)
        out = ["", f"## {title}", note,
               "| lens | n | wins | expected wins | lift (pp) | month test |",
               "|---|---|---|---|---|---|"]
        for k in sorted(agg, key=lambda k: -agg[k]["n"]):
            c = agg[k]
            out.append(f"| {k} | {c['n']} | {c['wins']} | {c['exp']:.1f} | "
                       f"{tier0.lift_pp(c):+.1f} | {tier0.month_test(c)} |")
        if len(out) == 5:
            out.append("| (none seen yet) | | | | | |")
        return out

    L += _section(
        "LENSES FOR — the aligned tags",
        "n / wins / wins the market rank alone predicted / lift in percentage "
        "points over settled rows carrying this lens. Lift should be positive.",
        "aligned")
    L += _section(
        "LENSES AGAINST — flags",
        "same measure as above, over rows carrying this flag. Lift should be "
        "NEGATIVE — these are meant to cost, not gain.",
        "flags")
    L += _section(
        "LENSES AGAINST — cautions",
        "same measure as above, over rows carrying this caution. Lift should "
        "be negative.",
        "cautions")
    L += _section(
        "SIGNPOSTS — the master's old AI (Racing Post Signposts, 2026-09-05)",
        "combo / rating clear / yard at this course by type / ran here last "
        "year / fresh / cold yard — each a dot, graded against the market "
        "exactly like a lens. Belief comes from the month test, never from one "
        "lift number.",
        "signposts")

    bands = _race_bands(rows)
    L += ["", "## RACE QUALITY — below the bar (<2) vs a betting race (>=2)",
          "Per race with a settled winner: favourite strike, whether the "
          "winner sat in the market's top 3, and our own top-score horse's strike.",
          "| band | races | fav strike | top-3 coverage | our pick strike |",
          "|---|---|---|---|---|"]
    for band, lab in (("below", "< 2 (below the bar)"),
                      ("betting", ">= 2 (betting race)")):
        b = bands[band]
        L.append(f"| {lab} | {b['n']} | "
                 f"{b['fav_win']}/{b['fav_n']} ({_pct(b['fav_win'], b['fav_n'])}) | "
                 f"{b['top3_hit']}/{b['n']} ({_pct(b['top3_hit'], b['n'])}) | "
                 f"{b['pick_win']}/{b['pick_n']} ({_pct(b['pick_win'], b['pick_n'])}) |")

    vt = _version_table(rows)
    L += ["", "## BY VERSION — v1 (pre-2026-09-03) vs v2 (the rebuilt read)",
          "n, wins, strike and level-stakes P/L at SP, over settled rows.",
          "| version | n | wins | strike | P/L @ SP |",
          "|---|---|---|---|---|"]
    for v in sorted(vt):
        c = vt[v]
        L.append(f"| {v} | {c['n']} | {c['wins']} | {_pct(c['wins'], c['n'])} | "
                 f"{c['pnl']:+.1f} |")
    if not vt:
        L.append("| (none settled yet) | | | | |")

    L += ["", "---",
          "Nothing above is a rule — it is a measurement. A rule is born only "
          "three ways (CLAUDE.md law 2): the master teaches it, the master "
          "validates it (doorbell), or the record field-tests it long enough "
          "to earn belief."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=(uk_today() - timedelta(days=1)).isoformat())
    ap.add_argument("--root", default=str(LEDGER_DIR))
    a = ap.parse_args(argv)
    root = Path(a.root)
    rows = load(root)
    text = scoreboard(rows)
    out = root.parent / "yardstick.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(text)
    print(f"yardstick: {len(rows)} row(s) in the ledger (as of {a.day}) -> {out}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
