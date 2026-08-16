"""THE NIGHT SCHOOL — one cron line, ~50 graded races a night, zero credits.

The master, 2026-08-16: 'the goal here also is to expedite the process...
we have enough races every day that we can learn from, and we don't, we
need to do this economical with credits also.'

Chains the free loop: fetch yesterday's results (direct API, the paid
subscription — no model credits) -> grade every 5+ runner race for every
policy on trial -> print the ladder's verdict for the health email.

Policies on trial live one per line in data/school/policies.txt ('fav' is
always graded as the benchmark). Adding a challenger is one line in that
file — no code, no credits.

Cron (PythonAnywhere, after the results settle):
  PYTHONPATH=src python -m racing_edge.school.night --champion cell:mr1

Safe to re-run: fetch skips days already on disk; grading appends only the
new day.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path


def trial_policies(school_dir: Path) -> list[str]:
    f = school_dir / "policies.txt"
    pols = ["fav"]
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and line not in pols:
                pols.append(line)
    return pols


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--champion", default=os.environ.get("SCHOOL_CHAMPION"))
    ap.add_argument("--day", default=(date.today() - timedelta(days=1)).isoformat())
    ap.add_argument("--school", default="data/school")
    a = ap.parse_args(argv)
    school = Path(a.school)
    raw = school / "raw"

    # 1. fetch — free on the subscription; skipped without credentials so
    # the grader still runs wherever the corpus already exists.
    if os.environ.get("RACING_API_USERNAME"):
        from racing_edge.school.fetch import main as fetch_main
        fetch_main(["--start", a.day, "--end", a.day, "--raw", str(raw)])
    elif not (raw / f"{a.day}.csv").exists():
        print(f"night school: no API credentials and no corpus for {a.day} "
              "— nothing to grade tonight (fail loud, not silent)")
        return 1

    # 2. grade every policy on trial across the whole card
    from racing_edge.school.daily import main as daily_main
    pols = trial_policies(school)
    args = ["--from", a.day, "--to", a.day,
            "--csv", str(school / "daily_policy.csv")]
    for p in pols:
        args += ["--policy", p]
    daily_main(args)

    # 3. the ladder rules — this line rides into health/email
    if a.champion:
        from racing_edge.school.ladder import load_rows, verdict
        print(verdict(load_rows(school / "daily_policy.csv"), a.champion))
    else:
        print("night school: no champion named (set SCHOOL_CHAMPION) — "
              "graded, no verdict")
    return 0


if __name__ == "__main__":
    sys.exit(main())
