"""
form_reader_ai.py — AI "Form Reader" pipeline stage.

Reads tipster-language form data (spotlight, comment, quotes, stable_tour) the
way a professional analyst would, per runner, and writes a structured verdict
file keyed by horse_id:

    data/form_read_YYYY-MM-DD.json

Each value is the structured verdict (verdict / rating / one_line_read /
key_positives / key_negatives / narrative_signal) plus the model id used.

Inputs:
    data/shortlist_YYYY-MM-DD.json   (per-race enriched runners + morning_price)
    data/full_form_YYYY-MM-DD.json   (career profiles keyed by horse_id)

Gating (we cannot see NAP scores at this stage):
    - skip confirmed non-runners
    - skip debutants that have no narrative at all
    - cap to MAX_READS_PER_RACE per race, choosing the shortest morning price
      (the market's most-fancied) as a proxy for "top candidates"

Degrades gracefully: if ANTHROPIC_API_KEY is absent or the SDK/network is
unavailable, write {} and log a clear WARNING, return 0. The existing pipeline
is unaffected.

Exit codes:
    0  — success (INCLUDING the degraded empty case)
    1  — only on a write error

================================================================================
INTEGRATION PATCH — for the orchestrator to wire into nap_selector_v3.py.
(Do NOT implement here; this is documentation only.)

The form read is applied as a BOUNDED overlay on top of the existing NAP score
so it can never dominate the model — it only nudges and breaks ties.

1. LOAD (once, near where full_form is loaded in nap_selector_v3.main):

       from src.helpers import data_path, safe_load_json, today_str
       _form_read = safe_load_json(
           data_path(f"form_read_{today_str()}.json")
       ) or {}
       # _form_read is keyed by horse_id; missing key => no overlay for that horse.

2. BOUNDED SCORE NUDGE (apply where each runner's total score is finalised,
   e.g. just after compute_* scores are summed into `top`/the candidate dict):

       fr = _form_read.get(str(runner.get("horse_id") or ""))
       if fr and isinstance(fr.get("rating"), (int, float)):
           # rating 0-100; centre at 50; scale to a max of +/-3 points of 100.
           delta = max(-3.0, min(3.0, (fr["rating"] - 50) / 50.0 * 3.0))
           top["score"] = top["score"] + delta            # bounded +/-3
           one_line = (fr.get("one_line_read") or "").strip()
           if one_line:
               top["reasons"].append(f"AI form read: {one_line}")  # append to reasons[]

   The nudge is clamped to +/-3.0 on a ~100-point scale so the AI layer can
   refine ordering but never overrides the quantitative model.

3. TIE-BREAKER (only inside a tight race flagged by detect_race_cluster):

       if detect_race_cluster(scored):                    # existing call
           # within this race, when two candidates' scores are within a small
           # epsilon, prefer the higher AI form `rating` as the tie-breaker:
           def _ai_rating(r):
               fr = _form_read.get(str(r.get("horse_id") or ""))
               return fr.get("rating", 0) if isinstance(fr, dict) else 0
           scored.sort(key=lambda r: (round(r["score"], 1), _ai_rating(r)),
                       reverse=True)
       # Outside clustered races the existing ordering is unchanged; the AI
       # rating only resolves near-ties where the quant model is ambivalent.

All three steps are no-ops when form_read_*.json is empty or a horse is absent,
so the integration is safe even when the form reader degraded to {}.
================================================================================
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from src.helpers import (
    data_path,
    log,
    safe_load_json,
    safe_write_json,
    today_str,
)
from src.form_reader_client import get_form_reader

# How many runners per race to send to the AI form reader (cost/latency guard).
MAX_READS_PER_RACE: int = 3


def _career_summary_for(horse_id: str, full_form: dict) -> dict:
    """Extract a compact career summary for a horse from full_form profiles."""
    if not isinstance(full_form, dict):
        return {}
    for race in full_form.get("races") or []:
        for profile in race.get("profiles") or []:
            if str(profile.get("horse_id") or "") == horse_id:
                return {
                    "runs":                profile.get("runs"),
                    "wins":                profile.get("wins"),
                    "best_ground":         profile.get("best_ground"),
                    "best_distance_f":     profile.get("best_distance_f"),
                    "course_wins":         profile.get("course_wins"),
                    "course_runs":         profile.get("course_runs"),
                    "class_wins":          profile.get("class_wins") or [],
                    "career_form_summary": profile.get("career_form_summary"),
                }
    return {}


def _has_narrative(runner: dict) -> bool:
    """True if the runner carries any tipster-language narrative text."""
    for key in ("spotlight", "comment", "quotes", "stable_tour"):
        if (runner.get(key) or "").strip():
            return True
    return False


def _is_non_runner(runner: dict) -> bool:
    """Best-effort confirmed non-runner detection (permissive — defaults False)."""
    for key in ("is_non_runner", "non_runner"):
        val = runner.get(key)
        if val is True:
            return True
        if isinstance(val, str) and val.strip().lower() in ("1", "true", "yes", "y"):
            return True
    return False


def _select_candidates(runners: list[dict]) -> list[dict]:
    """Gate + cap a race's runners down to the top candidates to read.

    Skips confirmed non-runners and narrative-less debutants, then keeps the
    MAX_READS_PER_RACE shortest morning prices (market's most fancied).
    """
    eligible: list[dict] = []
    for r in runners:
        if _is_non_runner(r):
            continue
        if r.get("is_debutant") and not _has_narrative(r):
            continue
        eligible.append(r)

    # Shortest decimal price first; missing prices sink to the back.
    def _price_key(r: dict) -> float:
        price = r.get("morning_price")
        try:
            p = float(price)
            return p if p > 1.0 else float("inf")
        except (TypeError, ValueError):
            return float("inf")

    eligible.sort(key=_price_key)
    return eligible[:MAX_READS_PER_RACE]


def _build_payload(runner: dict, race: dict, full_form: dict) -> dict:
    """Assemble the per-runner JSON payload sent to the form reader."""
    horse_id = str(runner.get("horse_id") or "")
    return {
        "horse": runner.get("horse"),
        "race_context": {
            "course":     race.get("course"),
            "off_time":   race.get("off_time"),
            "race_name":  race.get("race_name"),
            "type":       race.get("type"),
            "going":      race.get("going"),
            "distance_f": race.get("distance_f"),
            "field_size": race.get("field_size"),
        },
        "ratings": {
            "rpr": runner.get("rpr"),
            "ts":  runner.get("ts"),
            "or":  runner.get("ofr"),
        },
        "form_string":     runner.get("form"),
        "days_since_run":  runner.get("last_run"),
        "draw":            runner.get("draw"),
        "weight_lbs":      runner.get("lbs"),
        "headgear":        runner.get("headgear"),
        "first_time_gear": runner.get("first_time_gear"),
        "first_time_wind_op": runner.get("first_time_wind_op"),
        "trainer_14d":     runner.get("trainer_14_days") or {},
        "career":          _career_summary_for(horse_id, full_form),
        "narrative": {
            "spotlight":     (runner.get("spotlight") or "").strip(),
            "comment":       (runner.get("comment") or "").strip(),
            "quotes":        (runner.get("quotes") or "").strip(),
            "stable_tour":   (runner.get("stable_tour") or "").strip(),
            "prev_trainers": runner.get("prev_trainers") or [],
        },
        "morning_price": runner.get("morning_price"),
    }


def _write_result(date_str: str, results: dict) -> int:
    """Write the form_read file. Returns 0 on success, 1 on write error."""
    dest = data_path(f"form_read_{date_str}.json")
    if not safe_write_json(dest, results):
        log(f"form_reader_ai: failed to write {dest}", "ERROR")
        return 1
    log(f"form_reader_ai: results saved to {dest} ({len(results)} runners)")
    return 0


def main() -> int:
    log("form_reader_ai.py started")
    date_str = today_str()

    # Degrade gracefully: no client => write {} and succeed.
    reader = get_form_reader()
    if reader is None:
        log(
            "form_reader_ai: form reader unavailable (no API key / SDK / network) "
            "— writing empty result; pipeline unaffected",
            "WARNING",
        )
        return _write_result(date_str, {})

    shortlist = safe_load_json(data_path(f"shortlist_{date_str}.json"))
    if not shortlist:
        log("form_reader_ai: shortlist unavailable — writing empty result", "WARNING")
        return _write_result(date_str, {})

    full_form = safe_load_json(data_path(f"full_form_{date_str}.json")) or {}

    races: list[dict] = shortlist.get("races") or []
    results: dict[str, dict] = {}
    read_count = 0

    for race in races:
        runners = race.get("runners") or []
        candidates = _select_candidates(runners)
        for runner in candidates:
            horse_id = str(runner.get("horse_id") or "")
            if not horse_id or horse_id in results:
                continue
            payload = _build_payload(runner, race, full_form)
            verdict = reader.read_form(payload)
            read_count += 1
            if verdict is None:
                log(
                    f"form_reader_ai: no verdict for {runner.get('horse')} "
                    f"({horse_id}) — skipping",
                    "INFO",
                )
                continue
            verdict["model"] = reader.model
            results[horse_id] = verdict

    generated_at = datetime.now(timezone.utc).isoformat()
    log(
        f"form_reader_ai: read {read_count} runners, "
        f"{len(results)} verdicts captured at {generated_at}"
    )

    rc = _write_result(date_str, results)
    if rc == 0:
        summary = (
            f"form_reader_ai: SUCCESS — {len(results)} verdicts across "
            f"{len(races)} races for {date_str}"
        )
        log(summary)
        print(summary)
    return rc


if __name__ == "__main__":
    sys.exit(main())
