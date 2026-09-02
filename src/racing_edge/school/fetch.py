"""Corpus fetcher for the school — production version (direct Racing API).

Writes the same per-day CSV the mine/pack tools read, plus a comments
side-file packets can use (this session's MCP-fetched corpus has no
comments; on PythonAnywhere the API is already paid for, so store them).

Auth is HTTP Basic (RACING_API_USERNAME / RACING_API_PASSWORD from the
environment), NOT an api key.

Usage: PYTHONPATH=src python -m racing_edge.school.fetch \
           --start 2026-01-01 --end 2026-08-14 [--raw data/school/raw]
Skips days already fetched (rows on disk, or a confirmed-empty marker), so
it is safe to re-run nightly with --start yesterday --end yesterday.
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

from racing_edge.domain.units import book_code

BASE = os.environ.get("RACING_API_BASE", "https://api.theracingapi.com/v1")


def empty_marker(path: Path) -> Path:
    """The sidecar that says 'the API answered total=0 for this day' — a
    blank day (no meetings) is a fact, not a failed fetch."""
    return path.with_suffix(".empty")


def day_fetched(path: Path) -> bool:
    """ONE definition of 'this day is on disk': the file exists AND holds at
    least one runner row, OR the day is marked CONFIRMED EMPTY by the API
    (fourth audit 2026-09-02, bot B3: a genuine no-racing day could never
    hold a row, so it was refetched every night forever). fetch.main and
    school.night both ask here."""
    try:
        if path.exists() and path.stat().st_size > 0:
            return True
        return empty_marker(path).exists()
    except OSError:
        return False


def _digits(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit()) or "0"


RETRY_WAITS = (5, 15, 30, 60, 120)   # seconds — a 429 is a queue, not a failure


def _get_page(day: str, skip: int, auth: tuple[str, str]):
    """One results page, RIDING OUT the rate limit (2026-09-02, live on the
    box: the 21-day backfill hit 429 Too Many Requests on the third day and
    the whole night died with a traceback). 429 and 5xx wait and retry with
    the server's Retry-After when it names one; anything else raises."""
    last = None
    for wait in RETRY_WAITS + (None,):
        resp = requests.get(
            f"{BASE}/results",
            params={"start_date": day, "end_date": day,
                    "region": ["gb", "ire"], "limit": 50, "skip": skip},
            auth=auth, timeout=60)
        status = getattr(resp, "status_code", 200)
        if status == 429 or 500 <= status < 600:
            last = resp
            if wait is None:
                break
            try:
                wait = max(wait, int(resp.headers.get("Retry-After", 0)))
            except (TypeError, ValueError):
                pass
            print(f"  {day} skip={skip}: HTTP {status} — waiting {wait}s", flush=True)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp
    last.raise_for_status()
    return last


def fetch_day(day: str, auth: tuple[str, str]) -> list[dict]:
    races, skip = [], 0
    while True:
        resp = _get_page(day, skip, auth)
        data = resp.json()
        races += data.get("results", [])
        skip += 50
        if "total" not in data:
            # audit 2026-09-02: a missing 'total' defaulted to 0 and the loop
            # returned after ONE page — hundreds of runners silently dropped
            raise ValueError(f"results page for {day} carries no 'total' — "
                             "refusing to guess the page count")
        if skip >= int(data["total"]):
            return races
        time.sleep(0.6)  # stay inside the plan's rate limit


def day_rows(races: list[dict]) -> tuple[list[list], list[list]]:
    rows, comments = [], []
    for rc in races:
        rid = _digits(rc.get("race_id"))
        course = (rc.get("course") or "").replace(" (IRE)", "").replace(",", " ")
        region = "I" if rc.get("region") == "IRE" else "G"
        # the book letter (F/H/C/N) from ONE site — fourth audit 2026-09-02:
        # a private TYPE_MAP here duplicated domain.units.book_code
        rtype = book_code(rc.get("type")) or (rc.get("type") or "O")[:1] or "O"
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
    from racing_edge.config import racing_creds
    user, pw = racing_creds()                 # .env or environment — one door
    raw = Path(a.raw)
    raw.mkdir(parents=True, exist_ok=True)
    cdir = raw.parent / "comments"
    cdir.mkdir(parents=True, exist_ok=True)

    d = date.fromisoformat(a.start)
    end = date.fromisoformat(a.end)
    while d <= end:
        day = d.isoformat()
        out = raw / f"{day}.csv"
        # 'fetched' means ROWS INSIDE, not a file on disk (audit 2026-09-02: an
        # empty file from a failed day was never retried — the proxy, not the thing)
        if not day_fetched(out):
            races = fetch_day(day, (user, pw))
            rows, comments = day_rows(races)
            with open(out, "w", newline="") as fh:
                csv.writer(fh).writerows(rows)
            with open(cdir / f"{day}.csv", "w", newline="") as fh:
                csv.writer(fh).writerows(comments)
            if not races:
                # the API said total=0 and raised nothing: a blank day, kept
                # as a fact so tomorrow's night does not pay for it again
                empty_marker(out).write_text(f"{day}: API returned 0 results\n")
            print(f"{day}: {len(rows)} runners", flush=True)
            time.sleep(1.0)                   # a breath between days, for the rate limit
        d += timedelta(days=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
