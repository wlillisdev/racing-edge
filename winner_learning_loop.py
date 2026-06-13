"""
winner_learning_loop.py — Track A: daily open-eyes winner-learning loop.

For every race winner, independently of the numeric scoring model:
  1. blind_read   — an LLM reads the winner's PRE-RACE form with open eyes and
                    gives an honest assessment + a pre-race win likelihood. It is
                    NOT told the result, so there is no hindsight leakage.
  2. (reveal)     — the result is revealed.
  3. explain_win  — the LLM works out WHY it won: the decisive factor, the
                    contributing winning factors, and whether the blind read
                    would have caught it (was_findable).

Results bank into `winner_reads`; `winning_patterns` aggregates the recurring
reasons. Over time this builds a model-independent picture of what actually wins
— used to improve, or eventually replace, the score.

Design notes (senior build):
  - Never imports score_runner: "open eyes" is enforced structurally.
  - Idempotent: re-running a date skips winners already read (saves LLM cost);
    DB writes are upserts on the natural keys.
  - Failure-isolated: one bad winner logs and is skipped, never aborts the day.
  - Graceful: no API key / no SDK / DB down → logs and exits cleanly, like the
    rest of the codebase.
  - Reproducible: prompt_version + model stored per row.
  - Pure core (build_form_payload, aggregate_patterns, derive_findable) is unit
    tested without DB or LLM.

Usage (runs after results land — evening pipeline or PA scheduled task):
    python winner_learning_loop.py                 # today
    python winner_learning_loop.py 2026-06-12      # a specific date
    python winner_learning_loop.py --backfill 7    # last 7 days
    python winner_learning_loop.py --rebuild-only  # just rebuild patterns
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from typing import Optional

from src.db import get_db
from src.helpers import log, today_str

try:
    from src.llm_client import get_llm_client, llm_available
except Exception:  # pragma: no cover - llm layer optional
    get_llm_client = lambda *a, **k: None          # noqa: E731
    llm_available = lambda: False                  # noqa: E731

# --- Config (no magic numbers) ----------------------------------------------
PROMPT_VERSION = "v1"
READ_MODEL = "claude-sonnet-4-6"   # reasoning-capable, cost-sane for ~40/day
# Suggested factor vocabulary — the LLM prefers these but may add its own.
FACTOR_VOCAB = [
    "class drop", "class rise", "first-time headgear", "headgear retained",
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
    "draw, trainer/jockey, days since last run, and the strength of the field. "
    "Give an honest assessment and an unbiased pre-race win likelihood."
)
EXPLAIN_SYSTEM = (
    "This horse WON its race. You are given your own pre-race read and the result. "
    "Work out WHY it won: the single decisive factor and the contributing winning "
    "factors. Judge honestly whether your pre-race read would realistically have "
    "flagged it (was_findable). Prefer these factor tags where they apply, but add "
    "others as needed: " + ", ".join(FACTOR_VOCAB) + "."
)


# --- Pure core (unit-tested without DB/LLM) ---------------------------------
def build_form_payload(race: dict, winner: dict, field: list[dict]) -> dict:
    """PRE-RACE only payload for the blind read. Contains NO result/position/SP."""
    return {
        "race": {
            "course": race.get("course"),
            "going": race.get("going"),
            "distance_furlongs": race.get("distance_f"),
            "class": race.get("race_class"),
            "type": race.get("race_type"),
            "field_size": race.get("field_size"),
        },
        "horse": {
            "name": winner.get("horse_name"),
            "form": winner.get("form_string"),
            "official_rating": winner.get("official_rating"),
            "rpr": winner.get("rpr"),
            "topspeed": winner.get("ts_rating"),
            "age": winner.get("age"),
            "draw": winner.get("draw"),
            "trainer": winner.get("trainer"),
            "jockey": winner.get("jockey"),
            "morning_price": winner.get("sp_morning"),
            "days_since_run": winner.get("last_run_days"),
        },
        "field": [
            {"name": r.get("horse_name"), "form": r.get("form_string"),
             "or": r.get("official_rating"), "rpr": r.get("rpr"),
             "morning_price": r.get("sp_morning")}
            for r in field if r.get("horse_id") != winner.get("horse_id")
        ],
    }


def derive_findable(blind: dict, explain: dict) -> bool:
    """Trust the LLM's was_findable, but fall back to the blind likelihood."""
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
        seen_today = {_norm_factor(f) for f in factors if str(f).strip()}
        for f in seen_today:
            a = agg.setdefault(f, {"n": 0, "find": 0, "last": None})
            a["n"] += 1
            a["find"] += 1 if r.get("was_findable") else 0
            d = r.get("read_date")
            ds = d.isoformat() if hasattr(d, "isoformat") else str(d or "")
            if ds and (a["last"] is None or ds > a["last"]):
                a["last"] = ds
    return [(f, a["n"], a["find"], a["last"]) for f, a in agg.items()]


# --- LLM stages -------------------------------------------------------------
def blind_read(client, payload: dict) -> Optional[dict]:
    return client.call_structured(BLIND_SYSTEM, payload, BLIND_SCHEMA, model=READ_MODEL)


def explain_win(client, blind: dict, form: dict, result: dict) -> Optional[dict]:
    return client.call_structured(
        EXPLAIN_SYSTEM,
        {"pre_race_read": blind, "form": form, "result": result},
        EXPLAIN_SCHEMA, model=READ_MODEL,
    )


# --- DB access --------------------------------------------------------------
def _winners(db, d: str) -> list[dict]:
    return db.fetch_all(
        "SELECT race_id, horse_id, horse_name, sp_decimal "
        "FROM results WHERE result_date=%s AND won=1", (d,))


def _race(db, race_id: str) -> Optional[dict]:
    return db.fetch_one("SELECT * FROM races WHERE race_id=%s", (race_id,))


def _field(db, race_id: str) -> list[dict]:
    return db.fetch_all("SELECT * FROM runners WHERE race_id=%s", (race_id,))


def _already_read(db, d: str) -> set:
    rows = db.fetch_all(
        "SELECT race_id, horse_id FROM winner_reads WHERE read_date=%s", (d,))
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
    reads = db.fetch_all(
        "SELECT winning_factors, was_findable, read_date FROM winner_reads")
    rows = aggregate_patterns(reads)
    for r in rows:
        db.execute(_PATTERN_UPSERT, r)
    return len(rows)


# --- Orchestration ----------------------------------------------------------
def process_date(d: str, db, client) -> dict:
    winners = _winners(db, d)
    done = _already_read(db, d)
    stats = {"date": d, "winners": len(winners), "new": 0, "skipped": 0, "failed": 0}

    for w in winners:
        key = (w["race_id"], w["horse_id"])
        if key in done:
            stats["skipped"] += 1
            continue
        try:
            race = _race(db, w["race_id"])
            if not race:
                stats["failed"] += 1
                continue
            field = _field(db, w["race_id"])
            form = build_form_payload(race, {**w, **_winner_runner(field, w)}, field)

            blind = blind_read(client, form)
            if not blind:
                stats["failed"] += 1
                continue
            result = {"finishing_position": 1, "sp": w.get("sp_decimal"), "won": True}
            explain = explain_win(client, blind, form, result)
            if not explain:
                stats["failed"] += 1
                continue

            db.execute(_UPSERT, (
                w["race_id"], w["horse_id"], d, race.get("course"), w.get("horse_name"),
                w.get("sp_decimal"),
                blind.get("assessment"), blind.get("win_likelihood"),
                explain.get("decisive_factor"),
                json.dumps([_norm_factor(f) for f in explain.get("winning_factors", [])]),
                1 if derive_findable(blind, explain) else 0,
                explain.get("rationale"), PROMPT_VERSION, READ_MODEL,
            ))
            stats["new"] += 1
        except Exception as exc:  # noqa: BLE001 — isolate one winner's failure
            log(f"winner_learning: {w.get('horse_id')} failed — {exc}", "WARNING")
            stats["failed"] += 1
    return stats


def _winner_runner(field: list[dict], w: dict) -> dict:
    """The winner's runner row (form/ratings) from the field, if present."""
    for r in field:
        if r.get("horse_id") == w.get("horse_id"):
            return r
    return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=today_str())
    ap.add_argument("--backfill", type=int, default=0, help="Process the last N days")
    ap.add_argument("--rebuild-only", action="store_true")
    args = ap.parse_args()

    db = get_db()

    if args.rebuild_only:
        n = rebuild_patterns(db)
        print(f"Rebuilt winning_patterns: {n} factors.")
        return 0

    if not llm_available():
        log("winner_learning: LLM unavailable (no API key/SDK) — nothing to do", "WARNING")
        print("LLM unavailable — set ANTHROPIC_API_KEY. No reads performed.")
        return 0
    client = get_llm_client(default_model=READ_MODEL)

    dates = [args.date]
    if args.backfill > 0:
        base = datetime.strptime(args.date, "%Y-%m-%d").date()
        dates = [(base - timedelta(days=i)).isoformat() for i in range(args.backfill)]

    totals = {"winners": 0, "new": 0, "skipped": 0, "failed": 0}
    for d in dates:
        s = process_date(d, db, client)
        for k in totals:
            totals[k] += s[k]
        print(f"  {d}: winners={s['winners']} new={s['new']} "
              f"skipped={s['skipped']} failed={s['failed']}")

    n = rebuild_patterns(db)
    print(f"Done. Reads new={totals['new']} skipped={totals['skipped']} "
          f"failed={totals['failed']} | patterns={n}")
    log(f"winner_learning: {totals}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
