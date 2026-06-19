"""
jockey_intent_signal.py — the JOCKEY-INTENT read, as a SHADOW signal.

The most INDEPENDENT lens in the system: not form, but who the connections put
up. The form-based NAP can't see this; that independence is exactly what makes
it worth something (the audit's lesson — real conviction needs lenses that
don't share DNA). Non-acting: computed for every Method pick, logged, settled,
measured — promoted to the live overlay only if the results back it.

Two reads off the jockey booking (both you raised):
  • STABLE-JOCKEY INTENT — when a yard runs more than one and its NUMBER-ONE
    jockey takes a horse that is NOT the stable's market-elect, that quietly-
    fancied one is the message. "Townend on the second string is a huge signal."
    (And the flip: if the stable jockey is on a DIFFERENT runner, this one is the
    lesser of the yard — a mild negative.)
  • JOCKEY/TRAINER COMBO — a hot jockey+trainer partnership (strike-rate over a
    real sample) is a positive in its own right; a cold one a small negative.

Stable-jockey identity comes from /trainers/{id}/analysis/jockeys (Standard) —
the jockey with the lion's share of the yard's rides. Cached (it moves slowly).

Reads -> data/jockey_intent_<date>.json, settled into data/jockey_intent_log.csv.
`--report` is the lift test: win/place/ROI bucketed by verdict.

Usage:
  python jockey_intent_signal.py [YYYY-MM-DD]
  python jockey_intent_signal.py --settle [DATE]
  python jockey_intent_signal.py --report
"""

from __future__ import annotations

import argparse
import csv
import os
import statistics
from typing import Optional

from racecard_loader import load_racecard
from src.api_client import get_client
from src.helpers import data_path, log, safe_load_json, safe_write_json, today_str

LOG = "jockey_intent_log.csv"

MAIN_MIN_RIDES = 20       # a "stable jockey" must have a real body of rides for the yard
MAIN_SHARE = 0.25         # ...and a meaningful share of them
COMBO_MIN_RIDES = 15
COMBO_GOOD_SR = 18.0      # jockey+trainer win% at/above this = positive
COMBO_POOR_SR = 5.0       # ...at/below this over a big sample = small negative
COMBO_POOR_MIN = 40


# --------------------------------------------------------------------------- #
# pure helpers
# --------------------------------------------------------------------------- #
def _to_float(v) -> Optional[float]:
    try:
        return float(str(v).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None


def runner_price(runner: dict) -> Optional[float]:
    decs = []
    for o in (runner.get("odds") or []):
        d = _to_float(o.get("decimal"))
        if d and d > 1.0:
            decs.append(d)
    if decs:
        return round(statistics.median(decs), 2)
    sp = _to_float(runner.get("sp_dec"))
    return sp if sp and sp > 1.0 else None


def combo_map(stats: list[dict]) -> dict:
    """jockey_id -> {rides, wins, sr, share} from a trainer's jockey analysis."""
    rows = []
    for s in (stats or []):
        jid = str(s.get("jockey_id") or "")
        rides = _to_float(s.get("rides") or s.get("runners") or s.get("rides_count")) or 0
        wins = _to_float(s.get("1st") or s.get("wins") or s.get("won")) or 0
        if not jid or rides <= 0:
            continue
        sr = _to_float(s.get("win_%") or s.get("win_percent") or s.get("percentage"))
        if sr is None:
            sr = 100.0 * wins / rides
        rows.append((jid, int(rides), int(wins), round(sr, 1)))
    total = sum(r[1] for r in rows) or 1
    return {jid: {"rides": rides, "wins": wins, "sr": sr, "share": round(rides / total, 3)}
            for jid, rides, wins, sr in rows}


def main_stable_jockeys(cmap: dict) -> set:
    """The yard's number-one rider(s): top by rides, clearing the thresholds."""
    if not cmap:
        return set()
    top_rides = max(v["rides"] for v in cmap.values())
    return {jid for jid, v in cmap.items()
            if v["rides"] == top_rides and v["rides"] >= MAIN_MIN_RIDES and v["share"] >= MAIN_SHARE}


def _yard_runners(race: dict, trainer_id: str) -> list[dict]:
    return [r for r in (race.get("runners") or [])
            if str(r.get("trainer_id") or "") == trainer_id and trainer_id]


def jockey_intent_read(runner: dict, race: dict, cmap: dict) -> dict:
    """Stable-jockey intent + jockey/trainer combo read for one runner."""
    jid = str(runner.get("jockey_id") or "")
    tid = str(runner.get("trainer_id") or "")
    pts = 0.0
    reasons: list[str] = []

    mains = main_stable_jockeys(cmap)
    yard = _yard_runners(race, tid)
    multi = len(yard) >= 2

    # --- stable-jockey intent (only meaningful when the yard runs more than one) ---
    if multi:
        priced = [(r, runner_price(r)) for r in yard]
        priced = [(r, p) for r, p in priced if p is not None]
        if priced:
            shortest = min(p for _, p in priced)
            this_price = runner_price(runner)
            on_a_main = any(str(r.get("jockey_id") or "") in mains for r, _ in priced)
            if jid in mains and this_price is not None and this_price > shortest * 1.05:
                pts += 4.0
                reasons.append(f"Stable jockey on the yard's longer one ({this_price:.1f} vs "
                               f"elect {shortest:.1f}) — quietly fancied")
            elif on_a_main and jid not in mains:
                pts -= 2.0
                reasons.append("Yard's main jockey is on a different runner — this is the lesser")

    # --- jockey/trainer combo strike-rate ---
    c = cmap.get(jid)
    if c:
        if c["rides"] >= COMBO_MIN_RIDES and c["sr"] >= COMBO_GOOD_SR:
            pts += 2.0
            reasons.append(f"Hot J/T combo: {c['sr']:.0f}% over {c['rides']} rides")
        elif c["rides"] >= COMBO_POOR_MIN and c["sr"] <= COMBO_POOR_SR:
            pts -= 1.0
            reasons.append(f"Cold J/T combo: {c['sr']:.0f}% over {c['rides']} rides")

    total = round(pts, 1)
    verdict = "positive" if total >= 3 else ("negative" if total <= -3 else "neutral")
    return {
        "horse_id": str(runner.get("horse_id") or ""),
        "horse": runner.get("horse"), "jockey": runner.get("jockey"),
        "trainer": runner.get("trainer"),
        "course": race.get("course"), "off_time": race.get("off_time"),
        "pts": total, "verdict": verdict,
        "reasons": reasons or ["no jockey-intent signal"],
        "data_ok": bool(cmap),
    }


# --------------------------------------------------------------------------- #
# fetch + build (shadow)
# --------------------------------------------------------------------------- #
def _combo(trainer_id: str) -> dict:
    if not trainer_id:
        return {}
    cache = data_path(os.path.join("cache", f"tj_{trainer_id}.json"))
    cached = safe_load_json(cache)
    if cached is not None:
        return cached.get("cmap", {})
    stats: list[dict] = []
    try:
        stats = get_client().get_trainer_analysis_jockeys(trainer_id) or []
    except Exception as exc:  # noqa: BLE001
        log(f"jockey_intent: trainer/jockey analysis failed {trainer_id} — {exc}", "WARNING")
    cmap = combo_map(stats)
    safe_write_json(cache, {"trainer_id": trainer_id, "cmap": cmap})
    return cmap


def _race_and_runner(doc: dict, horse_id: str):
    for race in (doc.get("racecards") or []):
        for r in (race.get("runners") or []):
            if str(r.get("horse_id") or "") == horse_id:
                return race, r
    return None, None


def build(date_str: Optional[str] = None) -> dict:
    date_str = date_str or today_str()
    method = safe_load_json(data_path(f"method_pick_{date_str}.json")) or {}
    picks = method.get("race_picks") or []
    doc = load_racecard(date_str) or {}
    reads: list[dict] = []
    for p in picks:
        race, runner = _race_and_runner(doc, str(p.get("horse_id") or ""))
        if race is None:
            continue
        cmap = _combo(str(runner.get("trainer_id") or ""))
        reads.append(jockey_intent_read(runner, race, cmap))
    out = {"date": date_str, "reads": reads}
    safe_write_json(data_path(f"jockey_intent_{date_str}.json"), out)
    pos = sum(1 for r in reads if r["verdict"] == "positive")
    neg = sum(1 for r in reads if r["verdict"] == "negative")
    log(f"jockey_intent: {len(reads)} reads ({pos} positive / {neg} negative) — SHADOW")
    return out


# --------------------------------------------------------------------------- #
# settle + lift report
# --------------------------------------------------------------------------- #
def _logged_dates() -> set:
    path = data_path(LOG)
    if not os.path.exists(path):
        return set()
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["date"] for r in csv.DictReader(fh)}


def settle(date_str: str) -> None:
    out = safe_load_json(data_path(f"jockey_intent_{date_str}.json"))
    if not out or not out.get("reads"):
        print(f"No jockey-intent reads to settle for {date_str}.")
        return
    if date_str in _logged_dates():
        print(f"{date_str} already settled.")
        return
    try:
        doc = get_client().get_results_by_date(date_str) or {}
    except Exception as exc:  # noqa: BLE001
        log(f"jockey_intent settle: results fetch failed {date_str} — {exc}", "WARNING")
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
    print(f"jockey_intent: settled {len(rows)} reads for {date_str}")
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
    path = data_path(LOG)
    if not os.path.exists(path):
        print("No jockey-intent log yet — settle some days first.")
        return
    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8")))
    days = sorted({r["date"] for r in rows})
    print("=" * 64)
    print(f"JOCKEY-INTENT LIFT TEST — {len(rows)} reads over {len(days)} day(s)")
    print("  (SHADOW — does the booking pick out winners the form can't?)")
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
        print("\n  Sample OK. Promote only if positive clearly beats negative.")


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
    print(f"JOCKEY-INTENT READ — {out['date']}   (SHADOW — not acting on picks)")
    print("=" * 70)
    for rd in sorted(out["reads"], key=lambda r: -r["pts"]):
        print(f"  {rd['pts']:+5.1f}  [{rd['verdict']:<8}] {str(rd['horse']):<18} "
              f"{str(rd['jockey'])[:16]:<16} {str(rd['course'])[:10]}")
        for r in rd["reasons"]:
            print(f"        · {r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
