"""
ground_breeding_signal.py — the GROUND + BREEDING read, as a SHADOW signal.

Built on the Pro window, but deliberately NON-ACTING: it computes a read for
every Method pick and logs it, WITHOUT changing the live pick. The point is to
measure — over real results — whether the read actually separates winners from
losers before it ever earns a place in the live overlay. (Same discipline as
the rest of the system: prove it in shadow, promote only what the data backs.)

Two lenses, both things you've said matter and that merge:
  • GROUND — does the horse handle today's going?  Read first from the horse's
    OWN record (already on disk in full_form_<date>.json — zero extra API calls),
    then, for unexposed types, from the SIRE's progeny aptitude on that going.
  • BREEDING — is it bred for today's GOING and TRIP?  The sire's progeny
    strike-rate at this going and around this distance (Standard-tier
    /sires/{id}/analysis/distances). This is what reads the unexposed horse the
    bare form can't — the maiden / bumper / point-to-pointer (the Best Mate case).

The read is pure and transparent (points + reasons). Nothing here is added to
method_case; the day's reads go to data/ground_breeding_<date>.json and are
settled against results into data/ground_breeding_log.csv. `--report` shows
win% / place% / ROI bucketed by the read's verdict — the lift test.

Usage:
  python ground_breeding_signal.py [YYYY-MM-DD]        # build today's reads (shadow)
  python ground_breeding_signal.py --settle [DATE]     # settle vs results
  python ground_breeding_signal.py --report            # the lift test (by verdict)
"""

from __future__ import annotations

import argparse
import csv
import os
from typing import Optional

from racecard_loader import load_racecard
from src.api_client import get_client
from src.helpers import data_path, log, safe_load_json, safe_write_json, today_str

LOG = "ground_breeding_log.csv"

# Going descriptions to pass to the sire analysis `going` filter, per band.
GOING_FILTER = {
    "firm":  "Firm,Good To Firm",
    "good":  "Good",
    "soft":  "Soft,Good To Soft,Yielding,Heavy",
    "heavy": "Heavy,Soft",
    "aw":    "Standard,Standard To Slow,Slow,Fast",
}
# A sire read only counts when the sample is real.
SIRE_MIN_RUNNERS = 40
SIRE_GOOD_SR = 14.0       # progeny win% at/above this on the going+trip = positive
SIRE_POOR_SR = 4.0        # ...at/below this (over a big sample) = negative
TRIP_TOLERANCE_F = 1.5    # furlongs either side of today's trip counts as "this trip"


# --------------------------------------------------------------------------- #
# pure helpers — going band, distance, parsing
# --------------------------------------------------------------------------- #
def going_band(going: str) -> str:
    """Canonical ground band: firm / good / soft / heavy / aw / unknown."""
    s = (going or "").strip().lower()
    if not s:
        return "unknown"
    if "heavy" in s:
        return "heavy"
    if "soft" in s or "yielding" in s or "holding" in s:
        return "soft"
    if "firm" in s or "hard" in s:
        return "firm"
    if "good" in s:
        return "good"
    if any(k in s for k in ("standard", "slow", "fast", "tapeta", "polytrack", "fibresand")):
        return "aw"
    return "unknown"


def _to_float(v) -> Optional[float]:
    try:
        f = float(str(v).strip().rstrip("%"))
        return f
    except (TypeError, ValueError):
        return None


def _to_furlongs(row: dict) -> Optional[float]:
    """Distance of a sire-analysis row in furlongs, however the API labels it."""
    for k in ("dist_f", "distance_f", "furlongs"):
        f = _to_float(row.get(k))
        if f is not None:
            return f
    for k in ("dist_y", "distance_y", "yards"):
        y = _to_float(row.get(k))
        if y is not None:
            return round(y / 220.0, 1)
    # string form like "1m2f" / "5f"
    s = str(row.get("dist") or row.get("distance") or "").lower()
    if s:
        f = 0.0
        m = 0
        cur = ""
        for ch in s:
            if ch.isdigit() or ch == ".":
                cur += ch
            elif ch == "m":
                m = int(_to_float(cur) or 0); cur = ""
            elif ch == "f":
                f += (_to_float(cur) or 0); cur = ""
        return round(m * 8 + f, 1) if (m or f) else None
    return None


def _row_runs_wins(row: dict) -> tuple[int, int]:
    runs = _to_float(row.get("runners") or row.get("runs") or row.get("rides")) or 0
    wins = _to_float(row.get("1st") or row.get("wins") or row.get("won")) or 0
    return int(runs), int(wins)


# --------------------------------------------------------------------------- #
# pure reads
# --------------------------------------------------------------------------- #
def horse_ground_read(runs: list[dict], band: str) -> tuple[float, list[str], dict]:
    """The horse's OWN going record on today's band (from full_form runs)."""
    if band in ("unknown",) or not runs:
        return 0.0, [], {"on_band_runs": 0, "on_band_wins": 0}
    on_runs = on_wins = on_places = 0
    other_extreme_wins = 0
    for r in runs:
        b = going_band(str(r.get("going") or r.get("ground") or ""))
        pos = str(r.get("position") or r.get("pos") or "").strip()
        if b == band:
            on_runs += 1
            if pos == "1":
                on_wins += 1
            elif pos in ("2", "3"):
                on_places += 1
        elif band in ("heavy", "soft", "firm") and b in ("firm", "good") and pos == "1" and band != "firm":
            other_extreme_wins += 1          # wins on quicker ground, today is testing
    data = {"on_band_runs": on_runs, "on_band_wins": on_wins, "on_band_places": on_places}
    if on_wins >= 2:
        return 5.0, [f"Proven on {band}: {on_wins} wins from {on_runs}"], data
    if on_wins == 1:
        return 4.0, [f"Won on {band} ({on_wins}/{on_runs})"], data
    if on_runs >= 4 and on_places == 0:
        return -4.0, [f"Winless & unplaced on {band} (0/{on_runs}) — ground looks wrong"], data
    if on_runs == 0 and other_extreme_wins >= 1 and band in ("heavy", "soft"):
        return -2.5, [f"Unproven on {band}; all wins on quicker ground"], data
    return 0.0, [], data


def sire_ground_trip_read(sire_rows: list[dict], distance_f: Optional[float],
                          band: str) -> tuple[float, list[str], dict]:
    """The SIRE's progeny aptitude at today's going (rows already going-filtered)."""
    if not sire_rows:
        return 0.0, [], {"runners": 0, "wins": 0}
    # Prefer rows near today's trip; fall back to all rows if no trip given.
    rel = sire_rows
    if distance_f:
        near = [r for r in sire_rows
                if (_to_furlongs(r) is not None and abs(_to_furlongs(r) - distance_f) <= TRIP_TOLERANCE_F)]
        if near:
            rel = near
    runs = sum(_row_runs_wins(r)[0] for r in rel)
    wins = sum(_row_runs_wins(r)[1] for r in rel)
    if runs < 10:
        return 0.0, [], {"runners": runs, "wins": wins}
    sr = 100.0 * wins / runs
    trip = f"~{distance_f:.0f}f" if distance_f else "all trips"
    data = {"runners": runs, "wins": wins, "sr": round(sr, 1)}
    if runs >= SIRE_MIN_RUNNERS and sr >= SIRE_GOOD_SR:
        return 3.0, [f"Sire's progeny strong on {band} {trip} ({sr:.0f}% of {runs})"], data
    if runs >= max(SIRE_MIN_RUNNERS, 60) and sr <= SIRE_POOR_SR:
        return -3.0, [f"Sire's progeny weak on {band} {trip} ({sr:.0f}% of {runs})"], data
    return 0.0, [], data


def ground_breeding_read(runner: dict, race: dict, horse_runs: list[dict],
                         sire_rows: list[dict]) -> dict:
    """Combine the horse's own ground record with the sire's ground+trip aptitude.

    For an exposed horse the OWN record leads. For an unexposed type (few runs,
    no record on the going) the SIRE read carries it — the read the bare form
    can't give you on a maiden / bumper / point-to-pointer.
    """
    band = going_band(str(race.get("going_detailed") or race.get("going") or ""))
    distance_f = _to_float(race.get("distance_f"))
    exposure = len(horse_runs or [])

    g_pts, g_reasons, g_data = horse_ground_read(horse_runs or [], band)
    s_pts, s_reasons, s_data = sire_ground_trip_read(sire_rows or [], distance_f, band)

    reasons = list(g_reasons)
    has_own = g_data.get("on_band_runs", 0) > 0          # ran on today's going at least once
    if not has_own:
        # No own evidence on the going — THIS is the unexposed case the bare form
        # can't read. Lean on the breeding, and weight it up first/second time out.
        if s_reasons:
            reasons.append("Unproven on the going — reading the breeding:")
            reasons += s_reasons
        breeding_pts = s_pts * (1.5 if exposure <= 2 else 1.0)
    elif abs(g_pts) >= 4:
        # The horse has told you directly (proven, or clearly wrong on the ground)
        # — its own record overrides the sire's general aptitude.
        breeding_pts = 0.0
    else:
        # Own evidence is only mild — let the sire read tip it.
        reasons += s_reasons
        breeding_pts = s_pts

    total = round(g_pts + breeding_pts, 1)
    verdict = "positive" if total >= 3 else ("negative" if total <= -3 else "neutral")
    return {
        "horse_id": str(runner.get("horse_id") or ""),
        "horse": runner.get("horse"),
        "course": race.get("course"), "off_time": race.get("off_time"),
        "band": band, "distance_f": distance_f, "exposure": exposure,
        "ground_pts": round(g_pts, 1), "breeding_pts": round(breeding_pts, 1),
        "pts": total, "verdict": verdict,
        "reasons": reasons or ["no ground/breeding signal"],
        "data_ok": bool(horse_runs or sire_rows),
    }


# --------------------------------------------------------------------------- #
# fetch layer (sire analysis, cached — breeding is ~static)
# --------------------------------------------------------------------------- #
def _sire_rows(sire_id: str, band: str, race_type: str) -> list[dict]:
    if not sire_id or band == "unknown":
        return []
    cache = data_path(os.path.join("cache", f"sire_{sire_id}_{band}.json"))
    cached = safe_load_json(cache)
    if cached is not None:
        return cached.get("rows", [])
    rows: list[dict] = []
    try:
        rows = get_client().get_sire_analysis_distances(
            sire_id, going=GOING_FILTER.get(band), type_=race_type or None) or []
    except Exception as exc:  # noqa: BLE001
        log(f"ground_breeding: sire analysis failed {sire_id} — {exc}", "WARNING")
    safe_write_json(cache, {"sire_id": sire_id, "band": band, "rows": rows})
    return rows


def _race_and_runner(doc: dict, horse_id: str) -> tuple[Optional[dict], Optional[dict]]:
    for race in (doc.get("racecards") or []):
        for r in (race.get("runners") or []):
            if str(r.get("horse_id") or "") == horse_id:
                return race, r
    return None, None


def build(date_str: Optional[str] = None) -> dict:
    date_str = date_str or today_str()
    method = safe_load_json(data_path(f"method_pick_{date_str}.json")) or {}
    picks = method.get("race_picks") or []
    if not picks:
        log("ground_breeding: no method picks to read", "INFO")
        out = {"date": date_str, "reads": []}
        safe_write_json(data_path(f"ground_breeding_{date_str}.json"), out)
        return out

    doc = load_racecard(date_str) or {}
    full_form = safe_load_json(data_path(f"full_form_{date_str}.json")) or {}
    horses = full_form.get("horses") or {}

    reads: list[dict] = []
    for p in picks:
        hid = str(p.get("horse_id") or "")
        race, runner = _race_and_runner(doc, hid)
        if race is None:
            continue
        band = going_band(str(race.get("going_detailed") or race.get("going") or ""))
        rt = str(race.get("type") or "")
        sire_rows = _sire_rows(str(runner.get("sire_id") or ""), band, rt)
        read = ground_breeding_read(runner, race, horses.get(hid, []), sire_rows)
        reads.append(read)

    out = {"date": date_str, "reads": reads}
    safe_write_json(data_path(f"ground_breeding_{date_str}.json"), out)
    pos = sum(1 for r in reads if r["verdict"] == "positive")
    neg = sum(1 for r in reads if r["verdict"] == "negative")
    log(f"ground_breeding: {len(reads)} reads ({pos} positive / {neg} negative) — SHADOW, not acting")
    return out


# --------------------------------------------------------------------------- #
# settle + lift report (the measurement)
# --------------------------------------------------------------------------- #
def _logged_dates() -> set:
    path = data_path(LOG)
    if not os.path.exists(path):
        return set()
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["date"] for r in csv.DictReader(fh)}


def settle(date_str: str) -> None:
    out = safe_load_json(data_path(f"ground_breeding_{date_str}.json"))
    if not out or not out.get("reads"):
        print(f"No ground/breeding reads to settle for {date_str}.")
        return
    if date_str in _logged_dates():
        print(f"{date_str} already settled.")
        return
    try:
        doc = get_client().get_results_by_date(date_str) or {}
    except Exception as exc:  # noqa: BLE001
        log(f"ground_breeding settle: results fetch failed {date_str} — {exc}", "WARNING")
        return
    res: dict[str, dict] = {}
    for race in (doc.get("results") or []):
        for r in (race.get("runners") or []):
            hid = str(r.get("horse_id") or "")
            if hid:
                try:
                    pos = int(str(r.get("position") or "").strip())
                except (TypeError, ValueError):
                    pos = 99
                res[hid] = {"pos": pos, "sp": r.get("sp_dec") or r.get("sp")}
    if not res:
        print(f"Results not in yet for {date_str} — leaving unsettled.")
        return

    rows = []
    for rd in out["reads"]:
        r = res.get(rd["horse_id"])
        if r is None:
            continue
        sp = _to_float(r["sp"])
        rows.append({"date": date_str, "horse": rd["horse"], "verdict": rd["verdict"],
                     "pts": rd["pts"], "won": int(r["pos"] == 1), "placed": int(r["pos"] <= 3),
                     "sp": sp if sp else ""})
    _append(rows)
    print(f"ground_breeding: settled {len(rows)} reads for {date_str}")
    report()


def _append(rows: list[dict]) -> None:
    if not rows:
        return
    path = data_path(LOG)
    is_new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "horse", "verdict", "pts", "won", "placed", "sp"])
        if is_new:
            w.writeheader()
        w.writerows(rows)


def report() -> None:
    """The lift test: win% / place% / ROI bucketed by the read's verdict.

    If POSITIVE reads win materially more than NEGATIVE ones over a real sample,
    the signal separates winners from losers and has earned a look in the live
    overlay. Until then it stays in shadow.
    """
    path = data_path(LOG)
    if not os.path.exists(path):
        print("No ground/breeding log yet — settle some days first.")
        return
    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8")))
    days = sorted({r["date"] for r in rows})
    print("=" * 64)
    print(f"GROUND/BREEDING LIFT TEST — {len(rows)} reads over {len(days)} day(s)")
    print("  (SHADOW — does a positive read actually pick out winners?)")
    print("=" * 64)
    print(f"  {'verdict':<10}{'n':>5}{'win%':>7}{'plc%':>7}{'ROI%':>8}")
    for v in ("positive", "neutral", "negative"):
        vr = [r for r in rows if r["verdict"] == v]
        n = len(vr)
        if not n:
            print(f"  {v:<10}{0:>5}      —      —       —")
            continue
        win = sum(r["won"] == "1" for r in vr)
        plc = sum(r["placed"] == "1" for r in vr)
        bets = [r for r in vr if r["sp"] not in ("", "None") and _to_float(r["sp"])]
        pl = sum((_to_float(r["sp"]) - 1) if r["won"] == "1" else -1 for r in bets)
        roi = 100 * pl / len(bets) if bets else 0.0
        print(f"  {v:<10}{n:>5}{100*win/n:>6.0f}%{100*plc/n:>6.0f}%{roi:>7.1f}%")
    if len(rows) < 50:
        print(f"\n  SAMPLE TOO SMALL ({len(rows)}/50 reads): shadow only. Do not promote yet.")
    else:
        print("\n  Sample OK. Promote to the live overlay only if positive clearly beats negative.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=today_str())
    ap.add_argument("--settle", nargs="?", const="TODAY", metavar="DATE")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    if args.report:
        report()
        return 0
    if args.settle:
        settle(today_str() if args.settle == "TODAY" else args.settle)
        return 0

    out = build(args.date)
    print(f"GROUND/BREEDING READ — {out['date']}   (SHADOW — not acting on picks)")
    print("=" * 70)
    for rd in sorted(out["reads"], key=lambda r: -r["pts"]):
        print(f"  {rd['pts']:+5.1f}  [{rd['verdict']:<8}] {str(rd['horse']):<20} "
              f"{str(rd['course'])[:10]:<10} {rd['band']}")
        for r in rd["reasons"]:
            print(f"        · {r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
