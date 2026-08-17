"""THE SELF-AUDITOR — the system finds its own faults and acts at 3 strikes.

The master, 2026-08-17: 'you need to be able to find your own errors and
fix them, why is it me always finding and fixing things... what is
stopping you?' What was stopping it: faults were logged, then WAITED for
a human. His own Step D says a fault appearing 3+ times becomes a
numbered correction — this enforces that automatically, in the school
lane only (the live rulebook still needs his doorbell, by his own law).

After every marked exam, tag the computable faults per race:
  took_fav_fav_lost   — miss category (b): rented the market's opinion
  winner_unconsidered — miss category (c): the reading missed the race
  wrong_twin          — right pair, chose the loser of it
  over_price_cap      — picked above 11.0 (a brief violation, always)

Faults accumulate in data/school/faults.csv. When a fault's lifetime
count crosses 3, the auditor APPENDS a numbered correction to
docs/SCHOOL_BRIEF.md (version bump, earlier text never edited) and,
where a mechanical counter-policy exists, adds it to policies.txt so
the night grind starts grading the fix the same night.

Usage: PYTHONPATH=src python -m racing_edge.school.audit
         --picks data/school/picks/DAY.csv --key data/school/keys/DAY.csv
         [--raw data/school/raw] [--brief docs/SCHOOL_BRIEF.md]
         [--school data/school]
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

from racing_edge.school.mine import load_corpus

STRIKES = 3   # the master's Step D: 3+ occurrences = numbered correction

# fault -> (correction text template, trial policy or None)
PRESCRIPTIONS = {
    "took_fav_fav_lost": (
        "Renting the market's opinion keeps failing ({n} strikes, {days}): "
        "when the case for the favourite is only its price, that is not a "
        "case. Re-walk the defection rule honestly before settling on the "
        "fav — 'nothing else has a case' must cite a fact per rival.",
        None),
    "winner_unconsidered": (
        "The reading keeps missing the race entirely ({n} strikes, {days}): "
        "before locking a pick, name the ONE horse the market respects that "
        "your case ignores (firm price, weak paper — law 4d) and say why it "
        "loses. If you cannot, the read is not finished.",
        "shape:crowdfav"),
    "wrong_twin": (
        "Right pair, wrong choice, {n} times ({days}): of the final two, "
        "state which has the WIN habit and which merely runs well, and "
        "which the pace map favours — then choose. A coin-flip written "
        "down is still a coin-flip; find the separating fact.",
        None),
    "over_price_cap": (
        "Picked above the 11.0 cap {n} times ({days}) — this is a straight "
        "brief violation, not a judgement fault. The cap is absolute.",
        None),
}


def tag_faults(picks_file: Path, key_file: Path, raw: Path) -> list[tuple[str, str]]:
    """-> [(fault_name, race_id)] for one marked exam."""
    with open(key_file, newline="") as fh:
        key = {r[0]: {"winner": r[1], "fav": r[3]} for r in csv.reader(fh)}
    sp_of = {}
    for race in load_corpus(raw):
        for r in race:
            sp_of[(r.race_id, r.horse)] = r.sp
    faults = []
    with open(picks_file, newline="") as fh:
        for row in csv.reader(fh):
            if not row or len(row) < 3:
                continue
            race_id, pick = row[0], row[1]
            second = row[4].strip() if len(row) > 4 else ""
            k = key.get(race_id)
            if k is None:
                continue
            if sp_of.get((race_id, pick), 0.0) > 11.0:
                faults.append(("over_price_cap", race_id))
            if pick == k["winner"]:
                continue
            if pick == k["fav"]:
                faults.append(("took_fav_fav_lost", race_id))
            elif second and second == k["winner"]:
                faults.append(("wrong_twin", race_id))
            elif k["fav"] != k["winner"]:
                faults.append(("winner_unconsidered", race_id))
    return faults


def update_ledger(school: Path, day: str, faults: list[tuple[str, str]]) -> Counter:
    """Append this exam's faults; return lifetime counts AFTER the append."""
    ledger = school / "faults.csv"
    new = not ledger.exists()
    with open(ledger, "a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["exam_day", "fault", "race_id"])
        for f, rid in faults:
            w.writerow([day, f, rid])
    counts: Counter = Counter()
    days: dict[str, set] = {}
    with open(ledger, newline="") as fh:
        for row in csv.DictReader(fh):
            counts[row["fault"]] += 1
            days.setdefault(row["fault"], set()).add(row["exam_day"])
    counts.days = days   # type: ignore[attr-defined]
    return counts


def _already_corrected(brief_text: str, fault: str) -> bool:
    return f"[auto-correction: {fault}]" in brief_text


def apply_corrections(school: Path, brief_path: Path, counts: Counter) -> list[str]:
    """3+ strikes -> append a numbered correction + start any counter-policy
    trial. Returns the fault names acted on."""
    brief = brief_path.read_text()
    acted = []
    next_num = sum(1 for ln in brief.splitlines()
                   if ln.lstrip()[:3].rstrip(".").isdigit()) + 1
    for fault, n in counts.items():
        if n < STRIKES or _already_corrected(brief, fault):
            continue
        text, policy = PRESCRIPTIONS.get(fault, ("", None))
        if not text:
            continue
        days = ", ".join(sorted(getattr(counts, "days")[fault]))
        version = brief.count("## v") + 1
        brief += (
            f"\n## v{version} (auto) — correction from the self-auditor\n\n"
            f"{next_num}. **[auto-correction: {fault}]** "
            + text.format(n=n, days=days) + "\n")
        next_num += 1
        if policy:
            pf = school / "policies.txt"
            existing = pf.read_text() if pf.exists() else ""
            if policy not in existing:
                with open(pf, "a") as fh:
                    fh.write(f"{policy}\n")
        acted.append(fault)
    if acted:
        brief_path.write_text(brief)
    return acted


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--picks", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--raw", default="data/school/raw")
    ap.add_argument("--brief", default="docs/SCHOOL_BRIEF.md")
    ap.add_argument("--school", default="data/school")
    a = ap.parse_args(argv)
    day = Path(a.picks).stem
    faults = tag_faults(Path(a.picks), Path(a.key), Path(a.raw))
    counts = update_ledger(Path(a.school), day, faults)
    print(f"exam {day}: {len(faults)} fault(s) tagged "
          f"({', '.join(f for f, _ in faults[:6])}{'…' if len(faults) > 6 else ''})")
    for f, n in counts.most_common():
        print(f"  lifetime {f}: {n}")
    acted = apply_corrections(Path(a.school), Path(a.brief), counts)
    for f in acted:
        print(f"  ⚡ 3-STRIKE CORRECTION APPENDED to the brief: {f} "
              "(school lane — the live rulebook still needs the master)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
