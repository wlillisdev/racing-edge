"""
race_shortlist.py — Shortlist races and horses worth deeper analysis.

Philosophy: cast wide, filter late.
The shortlist is an INTELLIGENCE layer, not a betting filter.
Almost every runner should pass — the NAP selector does the strict narrowing.

Race filters (minimal):
    field_size >= MIN_FIELD_SIZE (default 4)
    field_size <= MAX_FIELD_SIZE (default 20)
    race type not in EXCLUDED_TYPES

Runner filters (permissive):
    has a horse name (always true)
    NOT a confirmed non-runner

Every runner gets flags attached:
    has_form          — form string present
    is_debutant       — no form string (first run)
    morning_price     — best available bookmaker decimal price
    first_time_gear   — headgear worn for first time today
    first_time_wind_op — running first time after wind surgery
    trainer_14_days   — trainer's wins/runs/% in last 14 days

Saves:
    data/shortlist_YYYY-MM-DD.json
    reports/shortlist_YYYY-MM-DD.txt

Exit codes:
    0  — success
    1  — failure (no racecard, write error)
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from src.helpers import data_path, log, report_path, safe_write_json, today_str
from racecard_loader import load_racecard

MIN_FIELD_SIZE: int = 4
MAX_FIELD_SIZE: int = 20
EXCLUDED_TYPES: frozenset[str] = frozenset()


def _best_morning_price(runner: dict) -> float | None:
    odds_list = runner.get("odds") or []
    best: float | None = None
    for entry in odds_list:
        try:
            dec = float(entry.get("decimal") or 0)
            if dec > 1.0:
                if best is None or dec > best:  # best available = longest decimal
                    best = dec
        except (TypeError, ValueError):
            continue
    return best


def _build_runner_flags(runner: dict) -> dict:
    form = (runner.get("form") or "").strip()
    has_form = bool(form.replace("-", "").replace("/", ""))
    morning_price = _best_morning_price(runner)
    headgear_run = str(runner.get("headgear_run") or "").strip()
    first_time_gear = headgear_run == "1"
    headgear = (runner.get("headgear") or "").strip()
    wind_run = str(runner.get("wind_surgery_run") or "").strip()
    first_time_wind_op = wind_run == "1"
    t14 = runner.get("trainer_14_days") or {}
    trainer_14_days = {
        "wins":    t14.get("wins", ""),
        "runs":    t14.get("runs", ""),
        "percent": t14.get("percent", ""),
    }
    return {
        "has_form":          has_form,
        "is_debutant":       not has_form,
        "morning_price":     morning_price,
        "first_time_gear":   first_time_gear,
        "headgear":          headgear if first_time_gear else "",
        "first_time_wind_op": first_time_wind_op,
        "trainer_14_days":   trainer_14_days,
    }


def _shortlist_race(race: dict) -> tuple[bool, list[dict]]:
    field_size = int(race.get("field_size") or 0)
    race_type  = str(race.get("type") or "").strip()
    runners    = race.get("runners") or []
    if not (MIN_FIELD_SIZE <= field_size <= MAX_FIELD_SIZE):
        return False, []
    if race_type in EXCLUDED_TYPES:
        return False, []
    enriched: list[dict] = []
    for runner in runners:
        horse_name = (runner.get("horse") or "").strip()
        if not horse_name:
            continue
        flags = _build_runner_flags(runner)
        enriched.append({
            "horse_id":           str(runner.get("horse_id") or ""),
            "horse":              horse_name,
            "jockey":             str(runner.get("jockey") or ""),
            "trainer":            str(runner.get("trainer") or ""),
            "trainer_id":         str(runner.get("trainer_id") or ""),
            "jockey_id":          str(runner.get("jockey_id") or ""),
            "form":               (runner.get("form") or ""),
            "draw":               runner.get("draw"),
            "lbs":                runner.get("lbs"),
            "ofr":                runner.get("ofr"),
            "rpr":                runner.get("rpr"),
            "ts":                 runner.get("ts"),
            "last_run":           runner.get("last_run"),
            "spotlight":          (runner.get("spotlight") or "").strip(),
            "comment":            (runner.get("comment") or "").strip(),
            "quotes":             (runner.get("quotes") or "").strip(),
            "stable_tour":        (runner.get("stable_tour") or "").strip(),
            "prev_trainers":      runner.get("prev_trainers") or [],
            "headgear":           (runner.get("headgear") or "").strip(),
            "headgear_run":       str(runner.get("headgear_run") or "").strip(),
            "wind_surgery_run":   str(runner.get("wind_surgery_run") or "").strip(),
            "trainer_14_days":    runner.get("trainer_14_days") or {},
            "odds":               runner.get("odds") or [],
            **flags,
        })
    return bool(enriched), enriched


def _format_text_report(date_str: str, generated_at: str, shortlist: dict) -> str:
    races: list[dict] = shortlist.get("races") or []
    total_runners = sum(len(r.get("runners", [])) for r in races)
    lines: list[str] = [
        "RACING INTELLIGENCE SYSTEM — SHORTLIST REPORT",
        f"Date:      {date_str}",
        f"Generated: {generated_at}",
        f"Races:     {len(races)}",
        f"Runners:   {total_runners}",
        "",
    ]
    for idx, race in enumerate(races, start=1):
        course    = race.get("course", "")
        off_time  = race.get("off_time", "")
        race_name = race.get("race_name", "")
        race_type = race.get("type", "")
        going     = race.get("going", "")
        dist      = race.get("distance_f", "")
        runners   = race.get("runners") or []
        lines.append(
            f"=== RACE {idx}: {course.upper()} {off_time} | "
            f"{race_type} | {dist}f | {going} ==="
        )
        lines.append(f"  {race_name}")
        for r in runners:
            horse   = r.get("horse", "")
            trainer = r.get("trainer", "")
            jockey  = r.get("jockey", "")
            form    = r.get("form") or "—"
            price   = r.get("morning_price")
            price_s = f"{price:.1f}" if price else "—"
            flags: list[str] = []
            if r.get("is_debutant"):
                flags.append("DEBUT")
            if r.get("first_time_gear"):
                flags.append(f"NEW {r.get('headgear','GEAR').upper()}")
            if r.get("first_time_wind_op"):
                flags.append("WIND OP")
            t14 = r.get("trainer_14_days", {})
            if t14.get("percent") and int(t14.get("percent") or 0) >= 30:
                flags.append(f"HOT TRAINER {t14['wins']}-{t14['runs']} {t14['percent']}%")
            flag_s = f"  [{', '.join(flags)}]" if flags else ""
            lines.append(
                f"  • {horse} | {trainer}/{jockey} | Form: {form} | {price_s}{flag_s}"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    log("race_shortlist.py started")
    date_str = today_str()
    racecard = load_racecard(date_str)
    if racecard is None:
        log("race_shortlist: racecard unavailable — run run_daily.py first", "ERROR")
        return 1
    racecards: list[dict] = racecard.get("racecards") or []
    if not racecards:
        log("race_shortlist: racecard list is empty", "ERROR")
        return 1
    log(f"race_shortlist: evaluating {len(racecards)} races")
    shortlisted_races: list[dict] = []
    for race in racecards:
        is_ok, enriched_runners = _shortlist_race(race)
        if is_ok:
            shortlisted_races.append({
                "race_id":   race.get("race_id", ""),
                "course":    race.get("course", ""),
                "off_time":  race.get("off_time", ""),
                "race_name": race.get("race_name", ""),
                "type":      race.get("type", ""),
                "going":     race.get("going", ""),
                "distance_f": race.get("distance_f", ""),
                "field_size": race.get("field_size", 0),
                "runners":   enriched_runners,
            })
    generated_at_iso = datetime.now(timezone.utc).isoformat()
    generated_at_hm  = datetime.now(timezone.utc).strftime("%H:%M")
    shortlist_doc: dict = {
        "date":         date_str,
        "generated_at": generated_at_iso,
        "race_count":   len(shortlisted_races),
        "races":        shortlisted_races,
    }
    json_dest = data_path(f"shortlist_{date_str}.json")
    if not safe_write_json(json_dest, shortlist_doc):
        log(f"race_shortlist: failed to write JSON to {json_dest}", "ERROR")
        return 1
    log(f"race_shortlist: JSON saved to {json_dest}")
    report_text = _format_text_report(date_str, generated_at_hm, shortlist_doc)
    report_dest = report_path(f"shortlist_{date_str}.txt")
    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
        log(f"race_shortlist: text report saved to {report_dest}")
    except OSError as exc:
        log(f"race_shortlist: failed to write text report — {exc}", "ERROR")
        return 1
    total_runners = sum(len(r.get("runners", [])) for r in shortlisted_races)
    summary = (
        f"race_shortlist: SUCCESS — {len(shortlisted_races)} of {len(racecards)} races, "
        f"{total_runners} runners shortlisted for {date_str}"
    )
    log(summary)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
