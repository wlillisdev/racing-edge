"""
trainer_profile_reader.py — Fetch trainer & jockey analysis profiles for today's shortlist.

Fetches:
  • Per-trainer course analysis  (/trainers/{id}/analysis/courses)
  • Per-trainer jockey combo     (/trainers/{id}/analysis/jockeys)
  • Per-jockey course analysis   (/jockeys/{id}/analysis/courses)

Saves:
  data/trainer_profiles_YYYY-MM-DD.json

The JSON is structured for O(1) lookup by trainer_id / jockey_id / course name
so nap_selector_v3.py can use it with zero extra I/O per runner.

API calls are rate-limited to one every 0.5 seconds. Individual failures are
handled gracefully — a failed lookup produces empty data rather than aborting.

Exit codes:
  0 — success
  1 — failure (no shortlist, write error)
"""

from __future__ import annotations

import time
import sys
from datetime import datetime, timezone

from src.helpers import data_path, log, safe_load_json, safe_write_json, today_str
from src.api_client import get_client

API_DELAY_SECONDS: float = 0.5


def _to_float(value: object) -> float | None:
    try:
        return float(str(value).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None


def _build_course_lookup(rows: list[dict]) -> dict[str, dict]:
    """Index course stats by lowercase course name."""
    lookup: dict[str, dict] = {}
    for row in rows:
        name = str(row.get("course") or "").strip().lower()
        if not name:
            continue
        lookup[name] = {
            "runners": int(row.get("runners") or 0),
            "wins":    int(row.get("1st") or 0),
            "win_pct": _to_float(row.get("win_%") or row.get("win_pct")),
            "ae":      _to_float(row.get("a/e")  or row.get("ae")),
        }
    return lookup


def _build_jockey_combo_lookup(rows: list[dict]) -> dict[str, dict]:
    """Index trainer×jockey combo stats by jockey_id."""
    lookup: dict[str, dict] = {}
    for row in rows:
        jid = str(row.get("jockey_id") or "").strip()
        if not jid:
            continue
        lookup[jid] = {
            "jockey":  str(row.get("jockey") or ""),
            "runners": int(row.get("runners") or 0),
            "wins":    int(row.get("1st") or 0),
            "win_pct": _to_float(row.get("win_%") or row.get("win_pct")),
            "ae":      _to_float(row.get("a/e")  or row.get("ae")),
        }
    return lookup


def main() -> int:
    log("trainer_profile_reader.py started")
    date_str = today_str()

    shortlist = safe_load_json(data_path(f"shortlist_{date_str}.json"))
    if shortlist is None:
        log(
            "trainer_profile_reader: shortlist unavailable — "
            "run race_shortlist.py first",
            "ERROR",
        )
        return 1

    trainer_ids: set[str] = set()
    jockey_ids:  set[str] = set()

    for race in shortlist.get("races") or []:
        for runner in race.get("runners") or []:
            tid = str(runner.get("trainer_id") or "").strip()
            jid = str(runner.get("jockey_id") or "").strip()
            if tid:
                trainer_ids.add(tid)
            if jid:
                jockey_ids.add(jid)

    log(
        f"trainer_profile_reader: {len(trainer_ids)} trainer(s), "
        f"{len(jockey_ids)} jockey(s)"
    )

    try:
        client = get_client()
    except Exception as exc:
        log(f"trainer_profile_reader: API client init failed — {exc}", "ERROR")
        return 1

    # ------------------------------------------------------------------
    # Fetch trainer data (2 API calls per trainer)
    # ------------------------------------------------------------------
    trainers_data: dict[str, dict] = {}
    trainer_list = sorted(trainer_ids)
    total_trainers = len(trainer_list)
    call_count = 0

    for idx, trainer_id in enumerate(trainer_list):
        log(f"trainer_profile_reader: [{idx+1}/{total_trainers}] trainer {trainer_id}")

        try:
            courses_raw = client.get_trainer_analysis_courses(trainer_id)
        except Exception as exc:
            log(f"trainer_profile_reader: trainer {trainer_id} courses — {exc}", "WARNING")
            courses_raw = []
        call_count += 1
        time.sleep(API_DELAY_SECONDS)

        try:
            jockeys_raw = client.get_trainer_analysis_jockeys(trainer_id)
        except Exception as exc:
            log(f"trainer_profile_reader: trainer {trainer_id} jockeys — {exc}", "WARNING")
            jockeys_raw = []
        call_count += 1
        time.sleep(API_DELAY_SECONDS)

        trainers_data[trainer_id] = {
            "courses": _build_course_lookup(courses_raw),
            "jockeys": _build_jockey_combo_lookup(jockeys_raw),
        }

    # ------------------------------------------------------------------
    # Fetch jockey data (1 API call per jockey)
    # ------------------------------------------------------------------
    jockeys_data: dict[str, dict] = {}
    jockey_list = sorted(jockey_ids)
    total_jockeys = len(jockey_list)

    for idx, jockey_id in enumerate(jockey_list):
        log(f"trainer_profile_reader: [{idx+1}/{total_jockeys}] jockey {jockey_id}")

        try:
            courses_raw = client.get_jockey_analysis_courses(jockey_id)
        except Exception as exc:
            log(f"trainer_profile_reader: jockey {jockey_id} courses — {exc}", "WARNING")
            courses_raw = []
        call_count += 1
        if idx < total_jockeys - 1:
            time.sleep(API_DELAY_SECONDS)

        jockeys_data[jockey_id] = {
            "courses": _build_course_lookup(courses_raw),
        }

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    payload: dict = {
        "date":          date_str,
        "generated_at":  datetime.now(timezone.utc).isoformat(),
        "api_calls":     call_count,
        "trainer_count": len(trainers_data),
        "jockey_count":  len(jockeys_data),
        "trainers":      trainers_data,
        "jockeys":       jockeys_data,
    }

    dest = data_path(f"trainer_profiles_{date_str}.json")
    if not safe_write_json(dest, payload):
        log(f"trainer_profile_reader: failed to write {dest}", "ERROR")
        return 1

    summary = (
        f"trainer_profile_reader: SUCCESS — {len(trainers_data)} trainers, "
        f"{len(jockeys_data)} jockeys, {call_count} API calls for {date_str}"
    )
    log(summary)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
