"""Corpus fetcher for the school — production version (direct Racing API).

Writes the same per-day CSV the mine/pack tools read, plus a comments
side-file packets can use (this session's MCP-fetched corpus has no
comments; on PythonAnywhere the API is already paid for, so store them).

Auth is HTTP Basic (RACING_API_USERNAME / RACING_API_PASSWORD from the
environment), NOT an api key.

Usage: PYTHONPATH=src python -m racing_edge.school.fetch \
           --start 2026-01-01 --end 2026-08-14 [--raw data/school/raw]
Skips days whose CSV already exists, so it is safe to re-run nightly with
--start yesterday --end yesterday to keep the corpus rolling.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

BASE = os.environ.get("RACING_API_BASE", "https://api.theracingapi.com/v1")
TYPE_MAP = {"Flat": "F", "Hurdle": "H", "Chase": "C", "NH Flat": "N"}


def _digits(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit()) or "0"


def fetch_day(day: str, auth: tuple[str, str]) -> list[dict]:
    races, skip = [], 0
    while True:
        resp = requests.get(
            f"{BASE}/results",
            params={"start_date": day, "end_date": day,
                    "region": ["gb", "ire"], "limit": 50, "skip": skip},
            auth=auth, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        races += data.get("results", [])
        skip += 50
        if skip >= int(data.get("total", 0)):
            return races
        time.sleep(0.6)  # stay inside the plan's rate limit


def day_rows(races: list[dict]) -> tuple[list[list], list[list]]:
    rows, comments = [], []
    for rc in races:
        rid = _digits(rc.get("race_id"))
        course = (rc.get("course") or "").replace(" (IRE)", "").replace(",", " ")
        region = "I" if rc.get("region") == "IRE" else "G"
        rtype = TYPE_MAP.get(rc.get("type"), (rc.get("type") or "O")[:1] or "O")
        rclass = _digits(rc.get("class"))
        dist = (rc.get("dist_f") or "0").rstrip("f") or "0"
        for r in rc.get("runners", []):
            rows.append([rc.get("date"), rid, course, region, rtype, rclass,
                         dist, _digits(r.get("horse_id")),
                         r.get("sp_dec") or "0", r.get("position") or "0",
                         r.get("btn") or "0", _digits(r.get("jockey_id")),
                         _digits(r.get("trainer_id"))])
            if r.get("comment"):
                comments.append([rid, _digits(r.get("horse_id")),
                                 r["comment"].replace("\n", " ")])
    return rows, comments


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--raw", default="data/school/raw")
    a = ap.parse_args(argv)
    user = os.environ["RACING_API_USERNAME"]
    pw = os.environ["RACING_API_PASSWORD"]
    raw = Path(a.raw)
    raw.mkdir(parents=True, exist_ok=True)
    cdir = raw.parent / "comments"
    cdir.mkdir(parents=True, exist_ok=True)

    d = date.fromisoformat(a.start)
    end = date.fromisoformat(a.end)
    while d <= end:
        day = d.isoformat()
        out = raw / f"{day}.csv"
        if not out.exists():
            rows, comments = day_rows(fetch_day(day, (user, pw)))
            with open(out, "w", newline="") as fh:
                csv.writer(fh).writerows(rows)
            with open(cdir / f"{day}.csv", "w", newline="") as fh:
                csv.writer(fh).writerows(comments)
            print(f"{day}: {len(rows)} runners", flush=True)
        d += timedelta(days=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
