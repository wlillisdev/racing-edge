"""
race_shape_ai.py — AI "Race Shape / Pace Projection" pipeline stage.

Projects the likely PACE SHAPE of each race the way a professional pace analyst
would, looking at the WHOLE FIELD (running styles, draw, recent form) rather than
one runner at a time, and writes a structured projection file keyed by race_id:

    data/race_shape_YYYY-MM-DD.json

Pace is a major edge that the numeric NAP model is blind to: a hold-up horse in a
slow-run, lone-leader race is tactically doomed regardless of its ratings, while a
front-runner who gets an uncontested lead in an even-paced field is gifted the race.
This stage gives the selector a bounded pace overlay to exploit that edge.

Each value in the output is the race-level projection:

    {
      "pace_scenario": HOT_PACE | EVEN_PACE | SLOW_PACE | LONE_LEADER,
      "pace_summary": str,
      "advantaged_styles": [FRONT_RUNNER | PROMINENT | MID_DIVISION | HOLD_UP],
      "per_runner": [ {horse_id, running_style, pace_fit, note}, ... ],
      "horses": { horse_id: {running_style, pace_fit, note}, ... },  # O(1) lookup map
      "model": <model id used>
    }

`per_runner` is the model's raw array; `horses` is the same data re-keyed by
horse_id so nap_selector can look up a horse's pace_fit in O(1).

Inputs:
    data/shortlist_YYYY-MM-DD.json   (per-race enriched runners + form/draw)

Gating (cost/latency guard):
    - skip races with field_size < MIN_FIELD_SIZE (tiny fields have no real shape)
    - send at most MAX_RUNNERS_PER_RACE runners per race to the model
    - one LLM call per qualifying race (the whole field in a single payload)

Degrades gracefully: if ANTHROPIC_API_KEY is absent or the SDK/network is
unavailable, write {} and log a clear WARNING, return 0. The existing pipeline
is unaffected.

Exit codes:
    0  — success (INCLUDING the degraded empty case)
    1  — only on a write error

================================================================================
INTEGRATION PATCH — for the orchestrator to wire into nap_selector_v3.py.
(Do NOT implement here; this is documentation only.)

The pace projection is applied as a BOUNDED ±2 overlay on top of the existing NAP
score, mirroring exactly how the AI form-read ±3 overlay is already wired in
score_runner. It only nudges and never overrides the quantitative model.

1. LOAD (once, near where _form_read is loaded in nap_selector_v3.main):

       from src.helpers import data_path, safe_load_json, today_str
       _race_shape = safe_load_json(
           data_path(f"race_shape_{today_str()}.json")
       ) or {}
       # _race_shape is keyed by race_id; each value has a "horses" map keyed by
       # horse_id. A missing race_id or horse_id => no overlay for that runner.

2. THREAD THE PARAM (add a race_shape kwarg to score_runner, mirroring form_read):

       def score_runner(
           runner: dict, race: dict, all_runners: list[dict],
           full_form: Optional[dict], market_movers: Optional[dict],
           trainer_profiles: Optional[dict] = None,
           form_read: Optional[dict] = None,
           race_shape: Optional[dict] = None,          # <-- NEW
       ) -> dict:

   and pass it through at the call site exactly as form_read is passed:

       scored = [
           score_runner(r, race, all_runners, full_form, market_movers,
                        trainer_profiles, _form_read, _race_shape)   # <-- NEW arg
           for r in all_runners
       ]

3. BOUNDED ±2 SCORE NUDGE (apply just after the AI form-read ±3 block in
   score_runner, so both overlays stack on the clamped `total`):

       pace_fit: Optional[int] = None
       pace_style: str = ""
       pace_note: str = ""
       pace_reasons: list[str] = []
       if race_shape:
           _rs = race_shape.get(str(race.get("race_id") or ""))
           if isinstance(_rs, dict):
               _ph = (_rs.get("horses") or {}).get(str(runner.get("horse_id") or ""))
               if isinstance(_ph, dict) and isinstance(_ph.get("pace_fit"), (int, float)):
                   pace_fit = int(_ph["pace_fit"])
                   pace_style = str(_ph.get("running_style") or "")
                   pace_note = str(_ph.get("note") or "").strip()
                   # pace_fit 0-100, centre at 50; scale to a max of +/-2 points.
                   delta = max(-2.0, min(2.0, (pace_fit - 50) / 50.0 * 2.0))
                   total = max(0.0, min(100.0, total + delta))      # bounded +/-2
                   scenario = str(_rs.get("pace_scenario") or "")
                   if pace_note:
                       pace_reasons.append(
                           f"AI pace ({scenario or '—'}): {pace_style or '—'} — "
                           f"{pace_note} [{delta:+.1f}]"
                       )

   Then include pace_reasons in the returned reasons[] list (append after
   ai_reasons), and optionally surface pace_fit / pace_style on the result dict:

       "pace_fit": pace_fit, "pace_style": pace_style,
       "reasons": (... + ai_reasons + pace_reasons),

   The nudge is clamped to +/-2.0 on a ~100-point scale — strictly smaller than
   the form-read +/-3 — so pace refines ordering but never dominates. It is a
   no-op whenever race_shape_*.json is empty, the race_id is absent, or the
   horse is absent, so the integration is safe even when this stage degraded
   to {}.
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
from src.llm_client import get_llm_client

# Skip fields smaller than this — too few runners to have a meaningful shape.
MIN_FIELD_SIZE: int = 5

# Cost/latency guard: cap how many runners we describe per race in the payload.
MAX_RUNNERS_PER_RACE: int = 20

# Output token cap per race (one whole-field projection per call).
MAX_TOKENS: int = 1500

# Frozen persona/instructions — the volatile per-race field goes in the payload.
SYSTEM_PROMPT: str = (
    "You are a professional horse-racing PACE ANALYST for UK racing. You read the "
    "whole field of a race and project how the race will be RUN tactically, not who "
    "is best on ratings. Using each runner's recent form figures, draw, and any "
    "running-style hints, infer each horse's likely running style and how the "
    "collective makeup shapes the pace.\n\n"
    "Classify every runner's running style as exactly one of: FRONT_RUNNER "
    "(needs/wants the lead), PROMINENT (races handy, just behind the pace), "
    "MID_DIVISION (settles midfield), or HOLD_UP (held up for a late run).\n\n"
    "Then judge the race-level pace scenario as exactly one of:\n"
    "  HOT_PACE   — several front-runners/prominent types ensuring a strong, "
    "contested gallop (favours hold-up/closers).\n"
    "  EVEN_PACE  — a sensible, fairly-run race with no dominant bias.\n"
    "  SLOW_PACE  — few front-runners, likely a steadily-run/tactical race that "
    "favours those handy and able to quicken (penalises one-paced closers).\n"
    "  LONE_LEADER — exactly one clear front-runner likely to get an uncontested "
    "lead and dictate (strongly favours that leader and prominent types).\n\n"
    "List advantaged_styles: the running styles the projected pace favours.\n\n"
    "For each runner give a pace_fit integer 0-100, where 50 is neutral: above 50 "
    "means the projected pace SUITS this horse's style/draw; below 50 means it is "
    "tactically against them. Keep notes terse and concrete (one short clause).\n\n"
    "Be decisive but honest: if running styles are genuinely unclear, lean toward "
    "EVEN_PACE and pace_fit values near 50. Output ONLY the structured JSON."
)

# Allowed enum values mirrored in the schema (single source of truth).
_RUNNING_STYLES = ["FRONT_RUNNER", "PROMINENT", "MID_DIVISION", "HOLD_UP"]
_PACE_SCENARIOS = ["HOT_PACE", "EVEN_PACE", "SLOW_PACE", "LONE_LEADER"]

# Structured-output JSON schema the model response must satisfy.
RACE_SHAPE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["pace_scenario", "pace_summary", "advantaged_styles", "per_runner"],
    "properties": {
        "pace_scenario": {"type": "string", "enum": _PACE_SCENARIOS},
        "pace_summary": {"type": "string"},
        "advantaged_styles": {
            "type": "array",
            "items": {"type": "string", "enum": _RUNNING_STYLES},
        },
        "per_runner": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["horse_id", "running_style", "pace_fit", "note"],
                "properties": {
                    "horse_id": {"type": "string"},
                    "running_style": {"type": "string", "enum": _RUNNING_STYLES},
                    "pace_fit": {"type": "integer", "minimum": 0, "maximum": 100},
                    "note": {"type": "string"},
                },
            },
        },
    },
}


def _style_hints(runner: dict) -> dict:
    """Collect any explicit running-style / pace hints carried on a runner.

    These are best-effort: the model treats absent hints as unknown and infers
    style from form + draw. Only non-empty values are included to keep the
    payload compact.
    """
    hints: dict = {}
    for key in (
        "running_style",
        "run_style",
        "pace",
        "pace_figure",
        "early_position",
        "run_to_position",
        "comment",
        "spotlight",
    ):
        val = runner.get(key)
        if isinstance(val, str):
            val = val.strip()
        if val:
            hints[key] = val
    return hints


def _build_payload(race: dict, runners: list[dict]) -> dict:
    """Assemble the whole-field JSON payload describing one race's pace shape."""
    field: list[dict] = []
    for r in runners:
        field.append(
            {
                "horse_id": str(r.get("horse_id") or ""),
                "horse": r.get("horse"),
                "draw": r.get("draw"),
                "form_string": r.get("form"),
                "days_since_run": r.get("last_run"),
                "headgear": r.get("headgear"),
                "style_hints": _style_hints(r),
            }
        )
    return {
        "race_context": {
            "race_id": str(race.get("race_id") or ""),
            "course": race.get("course"),
            "off_time": race.get("off_time"),
            "race_name": race.get("race_name"),
            "type": race.get("type"),
            "going": race.get("going"),
            "distance_f": race.get("distance_f"),
            "field_size": race.get("field_size"),
        },
        "runners": field,
    }


def _field_size(race: dict, runners: list[dict]) -> int:
    """Resolve a race's field size, falling back to the runner count."""
    fs = race.get("field_size")
    try:
        fs_int = int(fs)
        if fs_int > 0:
            return fs_int
    except (TypeError, ValueError):
        pass
    return len(runners)


def _to_horse_map(per_runner: list) -> dict:
    """Re-key the model's per_runner array by horse_id for O(1) lookup."""
    horses: dict[str, dict] = {}
    if not isinstance(per_runner, list):
        return horses
    for entry in per_runner:
        if not isinstance(entry, dict):
            continue
        hid = str(entry.get("horse_id") or "")
        if not hid:
            continue
        horses[hid] = {
            "running_style": entry.get("running_style"),
            "pace_fit": entry.get("pace_fit"),
            "note": entry.get("note"),
        }
    return horses


def _write_result(date_str: str, results: dict) -> int:
    """Write the race_shape file. Returns 0 on success, 1 on write error."""
    dest = data_path(f"race_shape_{date_str}.json")
    if not safe_write_json(dest, results):
        log(f"race_shape_ai: failed to write {dest}", "ERROR")
        return 1
    log(f"race_shape_ai: results saved to {dest} ({len(results)} races)")
    return 0


def main() -> int:
    log("race_shape_ai.py started")
    date_str = today_str()

    # Degrade gracefully: no client => write {} and succeed.
    client = get_llm_client()
    if client is None:
        log(
            "race_shape_ai: LLM layer unavailable (no API key / SDK / network) "
            "— writing empty result; pipeline unaffected",
            "WARNING",
        )
        return _write_result(date_str, {})

    shortlist = safe_load_json(data_path(f"shortlist_{date_str}.json"))
    if not shortlist:
        log("race_shape_ai: shortlist unavailable — writing empty result", "WARNING")
        return _write_result(date_str, {})

    races: list[dict] = shortlist.get("races") or []
    results: dict[str, dict] = {}
    call_count = 0
    skipped_small = 0

    for race in races:
        race_id = str(race.get("race_id") or "")
        runners = race.get("runners") or []
        if not race_id or race_id in results:
            continue
        if _field_size(race, runners) < MIN_FIELD_SIZE:
            skipped_small += 1
            continue

        payload = _build_payload(race, runners[:MAX_RUNNERS_PER_RACE])
        projection = client.call_structured(
            SYSTEM_PROMPT,
            payload,
            RACE_SHAPE_SCHEMA,
            max_tokens=MAX_TOKENS,
        )
        call_count += 1
        if projection is None:
            log(
                f"race_shape_ai: no projection for race {race_id} "
                f"({race.get('course')} {race.get('off_time')}) — skipping",
                "INFO",
            )
            continue

        per_runner = projection.get("per_runner") or []
        results[race_id] = {
            "pace_scenario": projection.get("pace_scenario"),
            "pace_summary": projection.get("pace_summary"),
            "advantaged_styles": projection.get("advantaged_styles") or [],
            "per_runner": per_runner,
            "horses": _to_horse_map(per_runner),
            "model": client.default_model,
        }

    generated_at = datetime.now(timezone.utc).isoformat()
    log(
        f"race_shape_ai: projected {call_count} races "
        f"({len(results)} captured, {skipped_small} skipped for small field) "
        f"at {generated_at}"
    )

    rc = _write_result(date_str, results)
    if rc == 0:
        summary = (
            f"race_shape_ai: SUCCESS — {len(results)} pace projections across "
            f"{len(races)} races for {date_str}"
        )
        log(summary)
        print(summary)
    return rc


if __name__ == "__main__":
    sys.exit(main())
