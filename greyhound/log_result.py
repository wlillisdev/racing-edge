#!/usr/bin/env python3
"""Log a race result against the engine's prediction and update the learned
track draw-bias table.

Usage:
    python greyhound/log_result.py <card.json> <race_no> <finish> [sp]

    finish = finishing order as trap numbers, winner first, e.g. 5,1,4
    sp     = optional starting price of the WINNER, e.g. 3/1

Appends to greyhound/results_log.csv (the calibration dataset — same role
as performance_log.csv on the horse side) and increments the winner's trap
count in greyhound/track_bias.json (draw bias activates in scoring only
after 30+ logged races at a track+distance).
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from scorer import score_card  # noqa: E402

HERE = Path(__file__).parent
LOG_PATH = HERE / "results_log.csv"
BIAS_PATH = HERE / "track_bias.json"

FIELDS = [
    "date", "track", "race_no", "grade", "distance",
    "sel_trap", "sel_name", "sel_score", "sel_confidence",
    "winner_trap", "sel_finish_pos", "winner_sp", "crowded",
]


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 1
    card_path = Path(sys.argv[1])
    race_no = int(sys.argv[2])
    finish = [int(t) for t in sys.argv[3].split(",") if t.strip()]
    sp = sys.argv[4] if len(sys.argv) > 4 else ""
    if not finish:
        print("ERROR: empty finishing order", file=sys.stderr)
        return 1

    card = json.loads(card_path.read_text())
    result = score_card(card)
    race = next((r for r in result["races"] if r["race_no"] == race_no), None)
    if race is None:
        print(f"ERROR: race {race_no} not in {card_path}", file=sys.stderr)
        return 1

    meeting = result["meeting"]
    track = str(meeting.get("track_code", "?")).upper()
    sel = race["selection"]
    winner_trap = finish[0]
    sel_finish = finish.index(sel["trap"]) + 1 if sel["trap"] in finish else ""

    # dedup: one row per (date, track, race_no)
    key = (meeting.get("date", ""), track, str(race_no))
    rows = []
    if LOG_PATH.exists():
        with LOG_PATH.open() as fh:
            rows = [r for r in csv.DictReader(fh)]
        if any((r["date"], r["track"], r["race_no"]) == key for r in rows):
            print(f"already logged: {key} — not double-counting")
            return 0

    rows.append({
        "date": meeting.get("date", ""),
        "track": track,
        "race_no": race_no,
        "grade": race.get("grade", ""),
        "distance": race.get("distance", ""),
        "sel_trap": sel["trap"],
        "sel_name": sel["name"],
        "sel_score": sel["score"],
        "sel_confidence": sel["confidence"],
        "winner_trap": winner_trap,
        "sel_finish_pos": sel_finish,
        "winner_sp": sp,
        "crowded": race["pace_map"]["crowding_risk"],
    })
    with LOG_PATH.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    # update learned draw bias (atomic write, lesson from the horse side)
    bias = {}
    if BIAS_PATH.exists():
        try:
            bias = json.loads(BIAS_PATH.read_text())
        except json.JSONDecodeError:
            print("WARNING: track_bias.json corrupt, rebuilding", file=sys.stderr)
    dist_key = str(race.get("distance", "?"))
    stats = bias.setdefault(track, {}).setdefault(dist_key, {"races": 0})
    stats["races"] = stats.get("races", 0) + 1
    trap_key = str(winner_trap)
    stats[trap_key] = stats.get(trap_key, 0) + 1
    tmp = BIAS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(bias, indent=2))
    tmp.replace(BIAS_PATH)

    hit = "WON" if winner_trap == sel["trap"] else f"finished {sel_finish or 'unplaced'}"
    print(f"logged: {track} R{race_no} — selection T{sel['trap']} {sel['name']} {hit}")
    print(f"bias table: {track}/{dist_key} now {stats['races']} races "
          f"(activates at 30)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
