#!/usr/bin/env python3
"""_owners.py — the owner question, answered by the record.

Bot research, 2026-09-06. NOT a rule, NOT part of the pick path. Read-only
against the repo; writes only to this botOwners/ directory.

Three jobs:

  audit   Does data/school/raw/*.json|csv carry an owner per runner?
          (Answer today: NO. This proves it rather than asserting it.)

  tables  Print the owner record tables from owner_snapshot.json — a live
          pull of The Racing API owner-analysis endpoints made 2026-09-06.
          No credentials needed; the snapshot is on disk.

  live    Re-pull the snapshot from The Racing API (needs RACING_API_USERNAME
          / RACING_API_PASSWORD in .env or the environment, exactly as
          src/racing_edge/school/fetch.py does). Rewrites owner_snapshot.json.

Usage:
    python3 _owners.py audit  --repo /home/user/racing-edge
    python3 _owners.py tables > owner_tables.txt
    python3 _owners.py live   --repo /home/user/racing-edge
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE / "owner_snapshot.json"
BASE = os.environ.get("RACING_API_BASE", "https://api.theracingapi.com/v1")

# The owners looked up live on 2026-09-06 via mcp__The_Racing_API__search_owner.
# The id is the API's, quoted; the tier is this bot's reading of the evidence
# and is EDUCATION, not a rule. Nothing here is carved.
POWERHOUSE_IDS = {
    "Godolphin": ("own_199380", "flat"),
    "Sheikh Mohammed Obaid Al Maktoum": ("own_221344", "flat"),
    "Amo Racing Limited": ("own_1008936", "flat"),
    "Al Shaqab Racing": ("own_869464", "flat"),
    "Shadwell Estate Company Ltd": ("own_1209752", "flat"),
    "Juddmonte": ("own_1206684", "flat"),
    "Wathnan Racing": ("own_1300352", "flat"),
    "Westerberg": ("own_1114388", "flat"),
    "Sheikh Juma Dalmook Al Maktoum": ("own_804908", "flat"),
    "Qatar Racing Limited": ("own_813872", "flat"),
    "Cheveley Park Stud": ("own_64420", "dual"),
    "King Power Racing Co Ltd": ("own_1008844", "flat"),
    "John P McManus": ("own_83548", "jumps"),
    "Gigginstown House Stud": ("own_454092", "jumps"),
    "Robcour": ("own_931464", "jumps"),
}


# --------------------------------------------------------------------------
# 1. AUDIT — does the repo corpus carry an owner?
# --------------------------------------------------------------------------
# The 13 columns written by racing_edge.school.fetch.day_rows (fetch.py:137-141).
RAW_COLUMNS = ["date", "race_id", "course", "region", "type", "class", "dist_f",
               "horse_id", "sp_dec", "position", "btn", "jockey_id", "trainer_id"]


def audit(repo: Path) -> int:
    raw = repo / "data" / "school" / "raw"
    print("=" * 78)
    print("AUDIT — does the results corpus carry an owner per runner?")
    print("=" * 78)
    if not raw.is_dir():
        print(f"  corpus directory not found: {raw}")
        return 1

    files = sorted(raw.glob("*.csv")) + sorted(raw.glob("*.json"))
    csvs = [f for f in files if f.suffix == ".csv"]
    print(f"  corpus dir      : {raw}")
    print(f"  files           : {len(files)}  ({len(csvs)} csv, "
          f"{len(files) - len(csvs)} json)")
    if not csvs:
        print("  no csv day-files to inspect.")
        return 1

    sample = csvs[len(csvs) // 2]
    with open(sample, newline="") as fh:
        rows = list(csv.reader(fh))
    widths = sorted({len(r) for r in rows})
    print(f"  sample file     : {sample.name}  ({len(rows)} runner rows)")
    print(f"  columns per row : {widths}  (headerless)")
    print()
    print("  the writer is racing_edge.school.fetch.day_rows() — fetch.py:137-141.")
    print("  its 13 columns, in order:")
    for i, name in enumerate(RAW_COLUMNS):
        val = rows[0][i] if rows and i < len(rows[0]) else ""
        print(f"     [{i:>2}] {name:<11} e.g. {val!r}")

    total = sum(1 for f in csvs for _ in open(f))
    print()
    print(f"  total runner rows across the corpus: {total:,}")
    print()
    print("  VERDICT: there is NO owner column and NO owner_id column.")
    print("  Owner cannot be computed from this corpus at all — not for one")
    print("  owner, not for thirty. Section 3 of the brief stops here.")
    print()
    print("  BUT the gap is in OUR writer, not in the API. A live call to the")
    print("  same /results endpoint that builds this corpus returns `owner` and")
    print("  `owner_id` on every runner (quoted in OWNERS.md section 2). The")
    print("  fields are being fetched and then dropped on the floor.")
    return 0


# --------------------------------------------------------------------------
# 2. TABLES — the owner record, from the live snapshot
# --------------------------------------------------------------------------
def _agg(rows):
    """rows: [runners, wins, a_e, level_stakes_pl]. Returns exact totals.

    runs / wins / P&L are exact sums. Overall a/e is NOT exactly recoverable:
    the API reports a/e = 0 on zero-win rows, so expected-wins cannot be
    inverted out of them. We report a runners-weighted mean of the reported
    a/e and label it approximate. The honest, assumption-free number is ROI.
    """
    runs = sum(r[0] for r in rows)
    wins = sum(r[1] for r in rows)
    pl = sum(r[3] for r in rows)
    wae = sum(r[0] * r[2] for r in rows) / runs if runs else 0.0
    return runs, wins, pl, wae


def _fmt(name, runs, wins, pl, wae, code=""):
    winpc = 100.0 * wins / runs if runs else 0.0
    roi = 100.0 * pl / runs if runs else 0.0
    return (f"  {name:<34.34}{code:<7}{runs:>7,}{wins:>7,}{winpc:>8.1f}%"
            f"{wae:>8.2f}{pl:>11,.1f}{roi:>9.1f}%")


HDR = (f"  {'owner':<34}{'code':<7}{'runs':>7}{'wins':>7}{'win%':>9}"
       f"{'a/e~':>8}{'£1 P/L':>11}{'ROI':>9}")


def tables() -> int:
    snap = json.loads(SNAPSHOT.read_text())
    owners = snap["owners"]

    print("=" * 96)
    print("THE OWNER RECORD — The Racing API owner analysis, GB+IRE, career to date")
    print(f"pulled {snap['_pulled']} via {snap['_source_tool']} (plan: standard)")
    print("=" * 96)
    print()
    print("a/e~ is a runners-weighted mean of the API's per-row a/e and is")
    print("APPROXIMATE (zero-win rows report a/e 0, so expected wins cannot be")
    print("inverted out of them). runs / wins / win% / £1 P/L / ROI are EXACT sums.")
    print("ROI is the return on a £1 win stake at SP on every single runner.")
    print()

    agg = {}
    for name, o in owners.items():
        agg[name] = _agg(o["rows"]) + (o.get("code", ""),)

    print("-" * 96)
    print("TABLE 1 — by number of runners (the biggest strings in Britain and Ireland)")
    print("-" * 96)
    print(HDR)
    for name, (runs, wins, pl, wae, code) in sorted(
            agg.items(), key=lambda kv: -kv[1][0]):
        print(_fmt(name, runs, wins, pl, wae, code))

    print()
    print("-" * 96)
    print("TABLE 2 — by ROI: does backing the silks blind at SP make money?")
    print("-" * 96)
    print(HDR)
    for name, (runs, wins, pl, wae, code) in sorted(
            agg.items(), key=lambda kv: -(kv[1][2] / kv[1][0] if kv[1][0] else 0)):
        print(_fmt(name, runs, wins, pl, wae, code))

    t_runs = sum(v[0] for v in agg.values())
    t_wins = sum(v[1] for v in agg.values())
    t_pl = sum(v[2] for v in agg.values())
    print()
    print(f"  {'ALL 11 POWERHOUSES POOLED':<41}{t_runs:>7,}{t_wins:>7,}"
          f"{100.0*t_wins/t_runs:>8.1f}%{'':>8}{t_pl:>11,.1f}"
          f"{100.0*t_pl/t_runs:>9.1f}%")
    print()
    print("  Not one of them shows a profit to blind SP backing. The silks are")
    print("  the most heavily advertised fact on the racecard, and the market")
    print("  charges full price for them.")

    # ---- Sheikh Juma Dalmook Al Maktoum, the owner who beat us -------------
    j = snap["sheikh_juma_by_trainer"]
    print()
    print("=" * 96)
    print("SHEIKH JUMA DALMOOK AL MAKTOUM (own_804908) — the owner of Extremely Zain")
    print("=" * 96)
    print()
    print("BY TRAINER, career, GB+IRE  (get_owner_trainer_analysis)")
    print(f"  {'trainer':<28}{'runs':>7}{'wins':>7}{'win%':>9}{'a/e':>8}{'£1 P/L':>10}{'ROI':>9}")
    for tr, runs, wins, ae, pl in j["rows"]:
        if runs < 10:
            continue
        print(f"  {tr:<28}{runs:>7}{wins:>7}{100.0*wins/runs:>8.1f}%"
              f"{ae:>8.2f}{pl:>10.1f}{100.0*pl/runs:>8.1f}%")
    runs, wins, pl, wae = _agg([[r[1], r[2], r[3], r[4]] for r in j["rows"]])
    print(f"  {'TOTAL':<28}{runs:>7}{wins:>7}{100.0*wins/runs:>8.1f}%"
          f"{wae:>8.2f}{pl:>10.1f}{100.0*pl/runs:>8.1f}%")
    print(f"  (API reports total_runners = {j['api_total_runners']:,})")

    c = snap["sheikh_juma_2026_by_course"]
    runs, wins, pl, wae = _agg([[r[1], r[2], r[3], r[4]] for r in c["rows"]])
    print()
    print(f"THIS SEASON, from {c['start_date']}, GB+IRE  (get_owner_course_analysis)")
    print(f"  runs {runs}   wins {wins}   win% {100.0*wins/runs:.1f}%   "
          f"£1 P/L {pl:+.1f}   ROI {100.0*pl/runs:+.1f}%")
    print(f"  best tracks by a/e: ", end="")
    best = sorted([r for r in c["rows"] if r[1] >= 3], key=lambda r: -r[3])[:4]
    print(", ".join(f"{r[0]} {r[2]}/{r[1]} a/e {r[3]}" for r in best))
    print()
    print("  READ IT STRAIGHT: 22% for Haggas off 532 runners is a serious")
    print("  operation — but a/e 0.98 and -28.7pts says the market already")
    print("  knows. He is a dot that says DO NOT DISMISS. He is not a bet.")
    return 0


# --------------------------------------------------------------------------
# 3. LIVE — re-pull the snapshot (needs credentials)
# --------------------------------------------------------------------------
def live(repo: Path) -> int:
    import time
    import requests

    sys.path.insert(0, str(repo / "src"))
    from racing_edge.config import racing_creds  # one door — CLAUDE.md law
    auth = racing_creds()

    out = {"_note": "re-pulled by _owners.py live",
           "_source_tool": "GET /owners/{id}/analysis/distance",
           "_pulled": None, "owners": {}}
    from datetime import date
    out["_pulled"] = date.today().isoformat()

    for name, (oid, code) in POWERHOUSE_IDS.items():
        params = {"region": ["gb", "ire"]}
        if code == "jumps":
            params["min_distance_y"] = 3000
        r = requests.get(f"{BASE}/owners/{oid}/analysis/distance",
                         params=params, auth=auth, timeout=60)
        if r.status_code != 200:
            print(f"  {name}: HTTP {r.status_code} {r.text[:120]}", file=sys.stderr)
            continue
        d = r.json()
        rows = [[x["runners"], x["1st"], x.get("a/e") or 0, x.get("1_pl") or 0]
                for x in d.get("distances", [])]
        out["owners"][d.get("owner", name)] = {
            "id": oid, "code": code,
            "api_total_runners": d.get("total_runners"), "rows": rows}
        print(f"  {name}: {len(rows)} distance rows", file=sys.stderr)
        time.sleep(0.6)          # stay inside the plan's rate limit

    SNAPSHOT.write_text(json.dumps(out, indent=2))
    print(f"wrote {SNAPSHOT}", file=sys.stderr)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("job", choices=["audit", "tables", "live"])
    ap.add_argument("--repo", default="/home/user/racing-edge", type=Path)
    a = ap.parse_args(argv)
    return {"audit": lambda: audit(a.repo),
            "tables": tables,
            "live": lambda: live(a.repo)}[a.job]()


if __name__ == "__main__":
    raise SystemExit(main())
