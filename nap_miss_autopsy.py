"""
nap_miss_autopsy.py — the post-race learning loop, YOUR way: "why didn't I back
the winner?"

For each day, take OUR NAP (and jump NAP). If it didn't win, read the actual
winner's PRE-RACE form against our pick — open eyes, no hindsight on our pick —
and record the line(s) of the method the winner had that we MISSED, and whether
the method already contains that signal (a weighting fault) or lacks it (a new
signal to add).

This is the miss-focused complement to winner_learning_loop (which reads every
winner). The question here is sharper and about US:
    not "why did this win" but "which line of OUR method would have caught it,
    and did we have it?"

Misses bank into `nap_misses`; `nap_miss_patterns` aggregates them into our
blind spots — for your judgement, never auto-rules.

Usage (after results land):
    python nap_miss_autopsy.py                 # today
    python nap_miss_autopsy.py 2026-06-15
    python nap_miss_autopsy.py --backfill 7
    python nap_miss_autopsy.py --report        # show blind spots only, no LLM
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from typing import Optional

from src.db import get_db
from src.helpers import data_path, log, safe_load_json, today_str
import model_cost_guard as guard
# Reuse the proven plumbing from the winner loop.
from winner_learning_loop import race_result, load_racecards, find_winner, _norm_factor

try:
    from src.llm_client import get_llm_client, llm_available
    from src.api_client import get_client
except Exception:  # pragma: no cover - optional layers
    get_llm_client = lambda *a, **k: None          # noqa: E731
    llm_available = lambda: False                  # noqa: E731
    get_client = lambda *a, **k: None              # noqa: E731

PROMPT_VERSION = "v1"
READ_MODEL = "claude-opus-4-8"

# The method's lines — a miss is mapped to these (from HANDICAPPING_METHOD.md).
METHOD_VOCAB = [
    "improving form / trajectory", "well-in on the weights", "ahead of the handicapper",
    "proven going", "proven trip", "proven course", "class drop", "right class",
    "breeding aptitude", "trainer in form", "trainer course record", "jockey booking",
    "consistent gamble / market support", "longest traveller / intent",
    "first-time headgear", "wind op", "stable switch", "back to winning trip",
    "strong pace setup / front-runner", "freshness / back from a break",
    "form working out (franked)", "ran better than result last time",
]

MISS_SCHEMA = {
    "type": "object",
    "properties": {
        "winner_edge": {"type": "string", "description": "The single edge the WINNER had over our pick."},
        "missed_factors": {"type": "array", "items": {"type": "string"},
                           "description": "Lines of the method the winner had that we missed/under-weighted. Prefer the vocabulary."},
        "we_had_the_line": {"type": "boolean",
                            "description": "True if the method DOES contain this signal (a weighting fault); False if it's a NEW signal we lack."},
        "was_findable": {"type": "boolean",
                         "description": "Realistically flaggable pre-race from the form?"},
        "rationale": {"type": "string"},
    },
    "required": ["winner_edge", "missed_factors", "was_findable", "rationale"],
}
MISS_SYSTEM = (
    "You are an expert form reader doing a post-race autopsy. OUR selection did "
    "NOT win this race; another horse did. You have both horses' PRE-RACE form "
    "and the result. Reading with open eyes, work out WHY the winner beat our "
    "pick: the single edge the winner had, and which lines of the method we "
    "MISSED or under-weighted. For each, judge honestly whether the method "
    "already contains that signal (a weighting fault) or lacks it (a new signal). "
    "Say whether it was findable beforehand. Prefer these method lines where they "
    "apply, add others only if genuinely needed: " + ", ".join(METHOD_VOCAB) + "."
)


# --- Pure core (unit-tested without DB/LLM/API) -----------------------------
def runner_brief(r: dict) -> dict:
    return {"name": r.get("horse"), "form": r.get("form"), "or": r.get("ofr"),
            "rpr": r.get("rpr"), "ts": r.get("ts"), "draw": r.get("draw"),
            "trainer": r.get("trainer"), "jockey": r.get("jockey"),
            "days_since_run": r.get("last_run"), "morning_price": r.get("sp_dec"),
            "headgear": r.get("headgear"), "spotlight": r.get("spotlight")}


def build_miss_payload(race: dict, our: dict, winner: dict,
                       our_pos: Optional[str], winner_sp) -> dict:
    return {
        "race": {"course": race.get("course"),
                 "going": race.get("going_detailed") or race.get("going"),
                 "distance_furlongs": race.get("distance_f"),
                 "class": race.get("class"), "type": race.get("type"),
                 "field_size": race.get("field_size")},
        "our_pick": runner_brief(our),
        "winner": runner_brief(winner),
        "result": {"our_pick_finished": our_pos, "winner_sp": winner_sp},
    }


def runner_result(result: Optional[dict], horse_id: str) -> tuple:
    """(position, sp) for horse_id from an API result, else (None, None)."""
    for r in ((result or {}).get("runners") or (result or {}).get("results") or []):
        if str(r.get("horse_id") or "") == str(horse_id):
            pos = str(r.get("position") or r.get("finish_position") or "").strip()
            sp = r.get("sp_dec") or r.get("bsp") or r.get("sp")
            try:
                sp = float(sp)
            except (TypeError, ValueError):
                sp = None
            return pos or None, sp
    return None, None


def aggregate_misses(rows: list[dict]) -> list[tuple]:
    """Pure: collapse nap_misses rows into (factor, times_missed, findable, last_seen)."""
    agg: dict[str, dict] = {}
    for r in rows:
        try:
            factors = json.loads(r.get("missed_factors") or "[]")
        except (TypeError, ValueError):
            factors = []
        for f in {_norm_factor(x) for x in factors if str(x).strip()}:
            a = agg.setdefault(f, {"n": 0, "find": 0, "last": None})
            a["n"] += 1
            a["find"] += 1 if r.get("was_findable") else 0
            d = r.get("miss_date")
            ds = d.isoformat() if hasattr(d, "isoformat") else str(d or "")
            if ds and (a["last"] is None or ds > a["last"]):
                a["last"] = ds
    return [(f, a["n"], a["find"], a["last"]) for f, a in agg.items()]


def picks_for(date_str: str) -> list[dict]:
    """Our NAP + jump NAP for the date (whatever the selector saved)."""
    doc = safe_load_json(data_path(f"nap_candidates_{date_str}.json")) or {}
    return [p for p in (doc.get("nap"), doc.get("jump_nap")) if p and p.get("horse_id")]


# --- LLM --------------------------------------------------------------------
def explain_miss(llm, payload: dict, on_usage=None) -> Optional[dict]:
    return llm.call_structured(MISS_SYSTEM, payload, MISS_SCHEMA,
                               model=READ_MODEL, on_usage=on_usage)


# --- DB ---------------------------------------------------------------------
_MISS_UPSERT = """
INSERT INTO nap_misses
  (race_id, miss_date, course, our_pick, our_pick_id, our_pick_pos, our_pick_sp,
   winner, winner_id, winner_sp, winner_edge, missed_factors, we_had_line,
   was_findable, rationale, prompt_version, model)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE
  winner=VALUES(winner), winner_id=VALUES(winner_id), winner_sp=VALUES(winner_sp),
  winner_edge=VALUES(winner_edge), missed_factors=VALUES(missed_factors),
  we_had_line=VALUES(we_had_line), was_findable=VALUES(was_findable),
  rationale=VALUES(rationale), prompt_version=VALUES(prompt_version), model=VALUES(model)
"""
_PATTERN_UPSERT = """
INSERT INTO nap_miss_patterns (factor, times_missed, findable_count, last_seen)
VALUES (%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE
  times_missed=VALUES(times_missed), findable_count=VALUES(findable_count),
  last_seen=VALUES(last_seen)
"""


def _already(db, d: str) -> set:
    rows = db.fetch_all("SELECT race_id FROM nap_misses WHERE miss_date=%s", (d,))
    return {r["race_id"] for r in rows}


def rebuild_patterns(db) -> int:
    rows = db.fetch_all("SELECT missed_factors, was_findable, miss_date FROM nap_misses")
    agg = aggregate_misses(rows)
    for r in agg:
        db.execute(_PATTERN_UPSERT, r)
    return len(agg)


def report(db, top: int = 30) -> None:
    rows = db.fetch_all(
        "SELECT factor, times_missed, findable_count, last_seen "
        "FROM nap_miss_patterns ORDER BY times_missed DESC, findable_count DESC LIMIT %s",
        (top,))
    print("=" * 66)
    print("WHAT WE KEEP MISSING — NAP blind spots (for your judgement)")
    print("=" * 66)
    if not rows:
        print("  (no misses recorded yet — run the autopsy after some results)")
        return
    print(f"  {'method line':<36}{'missed':>7}{'findable':>10}  last")
    print("  " + "-" * 60)
    for r in rows:
        print(f"  {r['factor']:<36}{r['times_missed']:>7}{r['findable_count']:>10}"
              f"  {r['last_seen']}")
    print("  " + "-" * 60)
    print("  'findable' = how often it was realistically flaggable pre-race.")
    print("  High + findable = a real blind spot to fix. Your call, not auto-rules.")


# --- Orchestration ----------------------------------------------------------
def process_date(d: str, db, llm, api, meter=None) -> dict:
    picks = picks_for(d)
    races = {str(r.get("race_id") or ""): r for r in load_racecards(d)}
    done = _already(db, d)
    stats = {"date": d, "picks": len(picks), "misses_read": 0, "hits": 0,
             "no_result": 0, "failed": 0, "halted": 0}
    on_usage = (lambda u: meter.add(READ_MODEL, u)) if meter is not None else None

    for pick in picks:
        race_id = str(pick.get("race_id") or "")
        race = races.get(race_id)
        if not race or race_id in done:
            continue
        result = race_result(api, race_id)
        win = find_winner(result)
        if not result or not win or not win.get("horse_id"):
            stats["no_result"] += 1
            continue
        our_id = str(pick.get("horse_id") or "")
        our_pos, our_sp = runner_result(result, our_id)
        if our_pos == "1" or win["horse_id"] == our_id:
            stats["hits"] += 1               # we won — nothing to learn here
            continue

        runners = race.get("runners") or []
        winner = next((r for r in runners if str(r.get("horse_id") or "") == win["horse_id"]), None)
        our = next((r for r in runners if str(r.get("horse_id") or "") == our_id), None)
        if not winner or not our:
            stats["no_result"] += 1
            continue
        if guard.should_halt(d):
            stats["halted"] += 1
            continue
        try:
            payload = build_miss_payload(race, our, winner, our_pos, win.get("sp"))
            ex = explain_miss(llm, payload, on_usage)
            if not ex:
                stats["failed"] += 1
                continue
            db.execute(_MISS_UPSERT, (
                race_id, d, race.get("course"),
                our.get("horse"), our_id, our_pos, our_sp,
                winner.get("horse"), win["horse_id"], win.get("sp"),
                ex.get("winner_edge"),
                json.dumps([_norm_factor(f) for f in ex.get("missed_factors", [])]),
                1 if ex.get("we_had_the_line") else 0,
                1 if ex.get("was_findable") else 0,
                ex.get("rationale"), PROMPT_VERSION, READ_MODEL,
            ))
            stats["misses_read"] += 1
        except Exception as exc:  # noqa: BLE001 — isolate one race
            log(f"nap_miss_autopsy: {race_id} failed — {exc}", "WARNING")
            stats["failed"] += 1
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=today_str())
    ap.add_argument("--backfill", type=int, default=0, help="Process the last N days")
    ap.add_argument("--report", action="store_true", help="Show blind spots only (no LLM)")
    args = ap.parse_args()

    db = get_db()
    if args.report:
        report(db)
        return 0

    if not llm_available():
        print("LLM unavailable — set ANTHROPIC_API_KEY. No reads performed.")
        return 0
    llm = get_llm_client(default_model=READ_MODEL)
    api = get_client()

    dates = [args.date]
    if args.backfill > 0:
        base = datetime.strptime(args.date, "%Y-%m-%d").date()
        dates = [(base - timedelta(days=i)).isoformat() for i in range(args.backfill)]

    if guard.should_halt(args.date):
        print(f"COST HALT — {guard.status_line(args.date)}. No reads this run.")
        return 0

    meter = guard.CostMeter()
    totals = {"picks": 0, "misses_read": 0, "hits": 0, "no_result": 0, "failed": 0, "halted": 0}
    for d in dates:
        s = process_date(d, db, llm, api, meter)
        for k in totals:
            totals[k] += s[k]
        print(f"  {d}: picks={s['picks']} misses_read={s['misses_read']} hits={s['hits']} "
              f"no_result={s['no_result']} failed={s['failed']} halted={s['halted']}")

    month_total = guard.commit(meter, args.date, "nap_miss_autopsy")
    budget = guard.check_and_alert(month_total, args.date)
    n = rebuild_patterns(db)
    print(f"Done. misses_read={totals['misses_read']} hits={totals['hits']} | blind-spot factors={n}")
    print(f"This run: {meter.calls} calls, ${meter.usd:.2f}. {guard.status_line(args.date)} [{budget}]")
    print()
    report(db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
