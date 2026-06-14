"""
winner_learning_loop.py — Track A: daily open-eyes winner-learning loop.

For EVERY race winner (not just our picks), independently of the numeric model:
  1. blind_read   — an LLM reads the winner's PRE-RACE form with open eyes and
                    gives an honest assessment + a pre-race win likelihood. It is
                    NOT told the result, so there is no hindsight leakage.
  2. (reveal)     — the result is revealed.
  3. explain_win  — the LLM works out WHY it won: the decisive factor, the
                    contributing winning factors, and whether the blind read
                    would have caught it (was_findable).

Data sources (deliberately full-field, not candidate-only):
  - data/racecards_<date>.json — all races, all runners, all form (morning
    snapshot → point-in-time). Falls back to the deep-backtest racecard cache
    for historical backfill.
  - the Racing API result per race → identifies the actual winner (cached).

Results bank into `winner_reads`; `winning_patterns` aggregates the recurring
reasons. Over time this is a model-independent picture of what actually wins —
to improve, or eventually replace, the score.

Design (senior build): never imports score_runner ("open eyes" is structural);
idempotent (skips winners already read, caches race results); failure-isolated
per winner; graceful when the LLM/API/DB is absent; reproducible (prompt_version
+ model per row); pure core unit-tested without DB/LLM/API.

Usage (after results land — evening pipeline or PA scheduled task):
    python winner_learning_loop.py                 # today
    python winner_learning_loop.py 2026-06-12      # a date
    python winner_learning_loop.py --backfill 7    # last 7 days
    python winner_learning_loop.py --rebuild-only  # rebuild patterns only
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.db import get_db
from src.helpers import data_path, log, safe_load_json, today_str
import model_cost_guard as guard

try:
    from src.llm_client import get_llm_client, llm_available
    from src.api_client import get_client
except Exception:  # pragma: no cover - optional layers
    get_llm_client = lambda *a, **k: None          # noqa: E731
    llm_available = lambda: False                  # noqa: E731
    get_client = lambda *a, **k: None              # noqa: E731

# --- Config (no magic numbers) ----------------------------------------------
PROMPT_VERSION = "v1"
READ_MODEL = "claude-opus-4-8"     # best judgement for open-eyes reads; cost-guarded
# Skip the *obvious* winners — a short-priced favourite winning teaches nothing
# about finding non-obvious winners (the actual goal). Reading only value winners
# sharpens the corpus AND keeps Opus affordable. Set WINNER_SKIP_BELOW_SP=0 to
# read every winner.
SKIP_BELOW_SP = float(os.environ.get("WINNER_SKIP_BELOW_SP", "3.0"))
_RESULT_CACHE = "winner_cache"      # data/winner_cache/<race_id>.json

FACTOR_VOCAB = [
    "class edge", "ratings edge", "class drop", "class rise",
    "first-time headgear", "headgear retained",
    "proven going", "proven distance", "step up in trip", "step down in trip",
    "strong recent form", "back from a break", "well drawn", "trainer in form",
    "jockey booking", "market support", "weight advantage", "improving profile",
    "course winner", "drop in grade", "front-runner uncontested",
]

# --- LLM schemas ------------------------------------------------------------
BLIND_SCHEMA = {
    "type": "object",
    "properties": {
        "assessment": {"type": "string", "description": "Honest pre-race read of this horse on form."},
        "win_likelihood": {"type": "string", "enum": ["high", "medium", "low"]},
        "key_positives": {"type": "array", "items": {"type": "string"}},
        "key_concerns": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["assessment", "win_likelihood"],
}
EXPLAIN_SCHEMA = {
    "type": "object",
    "properties": {
        "decisive_factor": {"type": "string", "description": "The single biggest reason it won."},
        "winning_factors": {"type": "array", "items": {"type": "string"},
                            "description": "Contributing factors; prefer the suggested vocabulary."},
        "was_findable": {"type": "boolean",
                         "description": "Would the pre-race read realistically have flagged this winner?"},
        "rationale": {"type": "string"},
    },
    "required": ["decisive_factor", "winning_factors", "was_findable", "rationale"],
}

BLIND_SYSTEM = (
    "You are an expert racing form reader. Assess the given horse PURELY on its "
    "pre-race form and the race context — you do NOT know the result. Read with "
    "open eyes: weigh recent form, class, going and distance suitability, ratings, "
    "draw, trainer/jockey, days since last run, the spotlight comment, and the "
    "strength of the field. Give an honest assessment and an unbiased pre-race "
    "win likelihood."
)
EXPLAIN_SYSTEM = (
    "This horse WON its race. You are given your own pre-race read and the result. "
    "Work out WHY it won: the single decisive factor and the contributing winning "
    "factors. Judge honestly whether your pre-race read would realistically have "
    "flagged it (was_findable). Prefer these factor tags where they apply, but add "
    "others as needed: " + ", ".join(FACTOR_VOCAB) + "."
)


# --- Pure core (unit-tested without DB/LLM/API) -----------------------------
def build_form_payload(race: dict, winner: dict, field: list[dict]) -> dict:
    """PRE-RACE only payload (racecard fields). Contains NO result/position/SP."""
    def runner_brief(r: dict) -> dict:
        return {"name": r.get("horse"), "form": r.get("form"),
                "or": r.get("ofr"), "rpr": r.get("rpr"),
                "morning_price": r.get("sp_dec")}
    return {
        "race": {
            "course": race.get("course"),
            "going": race.get("going_detailed") or race.get("going"),
            "distance_furlongs": race.get("distance_f"),
            "class": race.get("class"),
            "type": race.get("type"),
            "field_size": race.get("field_size"),
        },
        "horse": {
            "name": winner.get("horse"),
            "form": winner.get("form"),
            "official_rating": winner.get("ofr"),
            "rpr": winner.get("rpr"),
            "topspeed": winner.get("ts"),
            "age": winner.get("age"),
            "draw": winner.get("draw"),
            "trainer": winner.get("trainer"),
            "jockey": winner.get("jockey"),
            "morning_price": winner.get("sp_dec"),
            "days_since_run": winner.get("last_run"),
            "spotlight": winner.get("spotlight"),
            "comment": winner.get("comment"),
        },
        "field": [runner_brief(r) for r in field
                  if r.get("horse_id") != winner.get("horse_id")],
    }


def derive_findable(blind: dict, explain: dict) -> bool:
    if isinstance(explain.get("was_findable"), bool):
        return explain["was_findable"]
    return str(blind.get("win_likelihood", "")).lower() in ("high", "medium")


def _norm_factor(f: str) -> str:
    return " ".join(str(f).strip().lower().split())


def aggregate_patterns(reads: list[dict]) -> list[tuple]:
    """Pure: collapse winner_reads rows into (factor, occurrences, findable, last_seen)."""
    agg: dict[str, dict] = {}
    for r in reads:
        try:
            factors = json.loads(r.get("winning_factors") or "[]")
        except (TypeError, ValueError):
            factors = []
        for f in {_norm_factor(x) for x in factors if str(x).strip()}:
            a = agg.setdefault(f, {"n": 0, "find": 0, "last": None})
            a["n"] += 1
            a["find"] += 1 if r.get("was_findable") else 0
            d = r.get("read_date")
            ds = d.isoformat() if hasattr(d, "isoformat") else str(d or "")
            if ds and (a["last"] is None or ds > a["last"]):
                a["last"] = ds
    return [(f, a["n"], a["find"], a["last"]) for f, a in agg.items()]


def find_winner(result: Optional[dict]) -> Optional[dict]:
    """Pure: extract {horse_id, sp} of the position-1 finisher from an API result."""
    if not result:
        return None
    for r in (result.get("runners") or result.get("results") or []):
        if str(r.get("position") or r.get("finish_position") or "").strip() == "1":
            sp = r.get("sp_dec") or r.get("bsp") or r.get("sp")
            try:
                sp = float(sp)
            except (TypeError, ValueError):
                sp = None
            return {"horse_id": str(r.get("horse_id") or ""), "sp": sp}
    return None


# --- LLM stages -------------------------------------------------------------
def blind_read(client, payload: dict, on_usage=None) -> Optional[dict]:
    return client.call_structured(BLIND_SYSTEM, payload, BLIND_SCHEMA,
                                  model=READ_MODEL, on_usage=on_usage)


def explain_win(client, blind: dict, form: dict, result: dict, on_usage=None) -> Optional[dict]:
    return client.call_structured(
        EXPLAIN_SYSTEM,
        {"pre_race_read": blind, "form": form, "result": result},
        EXPLAIN_SCHEMA, model=READ_MODEL, on_usage=on_usage,
    )


# --- I/O --------------------------------------------------------------------
def load_racecards(d: str) -> list[dict]:
    """Morning snapshot for the date; fall back to the deep-backtest cache."""
    doc = safe_load_json(data_path(f"racecards_{d}.json"))
    if doc:
        return doc.get("racecards") or doc.get("races") or []
    cached = safe_load_json(data_path(f"backtest_cache/racecards/{d}.json"))
    return (cached or {}).get("races", []) if cached else []


def race_result(api, race_id: str) -> Optional[dict]:
    """Fetch a race result, cached per race_id so re-runs are free."""
    p = Path(data_path(f"{_RESULT_CACHE}/{race_id}.json"))
    if p.exists():
        return safe_load_json(str(p))
    try:
        res = api.get_race_results(race_id)
    except Exception as exc:  # noqa: BLE001
        log(f"winner_learning: result fetch failed {race_id} — {exc}", "WARNING")
        return None
    if res:
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            p.write_text(json.dumps(res))
        except OSError:
            pass
    return res


# --- DB ---------------------------------------------------------------------
def _already_read(db, d: str) -> set:
    rows = db.fetch_all("SELECT race_id, horse_id FROM winner_reads WHERE read_date=%s", (d,))
    return {(r["race_id"], r["horse_id"]) for r in rows}


_UPSERT = """
INSERT INTO winner_reads
  (race_id, horse_id, read_date, course, horse_name, sp_decimal,
   blind_assessment, blind_likelihood, decisive_factor, winning_factors,
   was_findable, rationale, prompt_version, model)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE
  blind_assessment=VALUES(blind_assessment), blind_likelihood=VALUES(blind_likelihood),
  decisive_factor=VALUES(decisive_factor), winning_factors=VALUES(winning_factors),
  was_findable=VALUES(was_findable), rationale=VALUES(rationale),
  prompt_version=VALUES(prompt_version), model=VALUES(model)
"""
_PATTERN_UPSERT = """
INSERT INTO winning_patterns (factor, occurrences, findable_count, last_seen)
VALUES (%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE
  occurrences=VALUES(occurrences), findable_count=VALUES(findable_count),
  last_seen=VALUES(last_seen)
"""


def rebuild_patterns(db) -> int:
    reads = db.fetch_all("SELECT winning_factors, was_findable, read_date FROM winner_reads")
    rows = aggregate_patterns(reads)
    for r in rows:
        db.execute(_PATTERN_UPSERT, r)
    return len(rows)


# --- Orchestration ----------------------------------------------------------
def process_date(d: str, db, llm, api, meter=None) -> dict:
    races = load_racecards(d)
    done = _already_read(db, d)
    stats = {"date": d, "races": len(races), "new": 0, "skipped": 0,
             "skipped_fav": 0, "no_result": 0, "failed": 0, "halted": 0}
    on_usage = (lambda u: meter.add(READ_MODEL, u)) if meter is not None else None

    for race in races:
        race_id = str(race.get("race_id") or "")
        runners = race.get("runners") or []
        if not race_id or not runners:
            continue

        win = find_winner(race_result(api, race_id))
        if not win or not win["horse_id"]:
            stats["no_result"] += 1
            continue
        # Skip obvious favourites — no learning value, and keeps Opus affordable.
        if SKIP_BELOW_SP > 0 and win.get("sp") and win["sp"] < SKIP_BELOW_SP:
            stats["skipped_fav"] += 1
            continue
        if (race_id, win["horse_id"]) in done:
            stats["skipped"] += 1
            continue

        winner = next((r for r in runners if r.get("horse_id") == win["horse_id"]), None)
        if not winner:
            stats["no_result"] += 1
            continue

        # Hard cost cap — stop making LLM calls once the month's budget is hit.
        if guard.should_halt(d):
            stats["halted"] += 1
            continue

        try:
            form = build_form_payload(race, winner, runners)
            blind = blind_read(llm, form, on_usage)
            if not blind:
                stats["failed"] += 1
                continue
            result = {"finishing_position": 1, "sp": win["sp"], "won": True}
            explain = explain_win(llm, blind, form, result, on_usage)
            if not explain:
                stats["failed"] += 1
                continue
            db.execute(_UPSERT, (
                race_id, win["horse_id"], d, race.get("course"), winner.get("horse"),
                win["sp"], blind.get("assessment"), blind.get("win_likelihood"),
                explain.get("decisive_factor"),
                json.dumps([_norm_factor(f) for f in explain.get("winning_factors", [])]),
                1 if derive_findable(blind, explain) else 0,
                explain.get("rationale"), PROMPT_VERSION, READ_MODEL,
            ))
            stats["new"] += 1
        except Exception as exc:  # noqa: BLE001 — isolate one winner
            log(f"winner_learning: {win['horse_id']} failed — {exc}", "WARNING")
            stats["failed"] += 1
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=today_str())
    ap.add_argument("--backfill", type=int, default=0, help="Process the last N days")
    ap.add_argument("--rebuild-only", action="store_true")
    args = ap.parse_args()

    db = get_db()

    if args.rebuild_only:
        print(f"Rebuilt winning_patterns: {rebuild_patterns(db)} factors.")
        return 0

    if not llm_available():
        log("winner_learning: LLM unavailable (no API key/SDK) — nothing to do", "WARNING")
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
        log("winner_learning: month budget reached — skipping all LLM reads", "WARNING")
        return 0

    meter = guard.CostMeter()
    totals = {"races": 0, "new": 0, "skipped": 0, "skipped_fav": 0,
              "no_result": 0, "failed": 0, "halted": 0}
    for d in dates:
        s = process_date(d, db, llm, api, meter)
        for k in totals:
            totals[k] += s[k]
        print(f"  {d}: races={s['races']} new={s['new']} skipped={s['skipped']} "
              f"skipped_fav={s['skipped_fav']} no_result={s['no_result']} "
              f"failed={s['failed']} halted={s['halted']}")

    # Record spend, alert if over budget, and show this run's cost.
    month_total = guard.commit(meter, args.date, "winner_learning")
    budget = guard.check_and_alert(month_total, args.date)
    n = rebuild_patterns(db)
    print(f"Done. new={totals['new']} skipped={totals['skipped']} "
          f"failed={totals['failed']} halted={totals['halted']} | patterns={n}")
    print(f"This run: {meter.calls} calls, ${meter.usd:.2f}. "
          f"{guard.status_line(args.date)} [{budget}]")
    log(f"winner_learning: {totals} | run_usd={meter.usd:.2f} month_usd={month_total:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
