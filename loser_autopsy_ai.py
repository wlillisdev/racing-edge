"""
loser_autopsy_ai.py — AI "Loser Autopsy" learning loop.

Each evening, after results land, this stage performs a FORENSIC post-mortem on
a losing NAP: it compares our pick against the horse that actually won and asks
the LLM to diagnose *why* we lost, *which signal* the quantitative model missed,
and a *concrete* model adjustment (which constant / weight / filter in
nap_selector to nudge, and in which direction). Over time the appended log
accumulates these proposed tweaks so patterns in our failures become visible —
this is the compounding-improvement engine that complements the rule-based
loser_diagnostics.py with model-tweak proposals.

Inputs (read-only, located the same way loser_diagnostics.py does):
    data/nap_candidates_YYYY-MM-DD.json   -> ["nap"]  (our official NAP record)
    data/results_YYYY-MM-DD.json          -> ["official_results"] rows where
                                             candidate_type == "nap"; each row
                                             carries won / position /
                                             beaten_lengths / sp_decimal.
    data/results_enriched_YYYY-MM-DD.json -> (optional) same official_results
                                             rows enriched with
                                             beaten_by_winner / winner_sp.
    data/shortlist_YYYY-MM-DD.json        -> (optional) per-race runners used to
                                             recover the winner's form / price.

Outputs (OWNED by this module):
    reports/loser_autopsy_YYYY-MM-DD.txt    (readable autopsy / stub note)
    data/loser_autopsy_log.json             (running list of all autopsies +
                                             proposed tweaks; load-append-save)

Date handling:
    Default date is YESTERDAY (results need to exist before an autopsy is
    possible). An explicit YYYY-MM-DD may be passed as argv[1]. If neither
    yesterday's nor an explicit date's results exist, this also falls back to
    today_str() (the same value loser_diagnostics.py / result_enricher.py use)
    so it co-operates with the evening pipeline's same-day run.

Degrades gracefully (never raises into the pipeline):
    - No LLM (no API key / SDK / network)  => write a stub note, return 0.
    - No results / NAP won / no NAP         => write a "no autopsy needed /
                                               pending results" note, return 0.
    - Only a genuine WRITE error            => return 1.

Exit codes:
    0  — success, INCLUDING every degraded case.
    1  — only on a write error.

================================================================================
INTEGRATION (documentation only — DO NOT implement here; the orchestrator wires
this in. These files are read-only to this module.)

1. evening_audit_pipeline.py — add ONE line to PIPELINE_STEPS, AFTER
   results_auditor and performance_tracker (results + per-bet tracking must
   exist before an autopsy can run):

       ("loser_autopsy_ai",   "loser_autopsy_ai.py",    []),

   e.g.:
       PIPELINE_STEPS = [
           ("results_auditor",     "results_auditor.py",     []),
           ("performance_tracker", "performance_tracker.py", []),
           ("loser_autopsy_ai",    "loser_autopsy_ai.py",    []),   # <-- insert
           ("profit_report",       "profit_report.py",       []),
           ("email_audit",         "email_audit.py",         []),
       ]

2. weekly_learning_report.py — can summarise data/loser_autopsy_log.json: load
   the running list and group autopsies by `category` and
   `proposed_tweak.target` to surface the most-recurring failure modes and the
   model adjustments they imply (e.g. "5 losses this week point at
   compute_suitability_score — raise its weight"). No change is required to that
   file for this module to function; it is purely a downstream consumer.
================================================================================
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from src.helpers import (
    data_path,
    format_odds,
    log,
    report_path,
    safe_load_json,
    safe_write_json,
    today_str,
)
from src.llm_client import get_llm_client

# Cap output tokens — a single autopsy is compact.
MAX_TOKENS: int = 1024

# Running log of every autopsy + proposed tweak (NOT date-stamped — it grows).
LOG_FILENAME: str = "loser_autopsy_log.json"


# ---------------------------------------------------------------------------
# Frozen persona + structured-output schema (single source of truth).
# ---------------------------------------------------------------------------

SYSTEM_PROMPT: str = (
    "You are a forensic UK horse-racing analyst performing a post-mortem on a "
    "losing NAP selection from a quantitative model. You are given OUR pick (its "
    "model score, grade, sub-scores and the reasons the model liked it) and the "
    "horse that ACTUALLY WON the same race.\n\n"
    "Diagnose, concretely and without hedging:\n"
    "  - what_we_missed: the specific signal/angle our model under-weighted or "
    "missed that the winner had.\n"
    "  - winner_edge: in one clause, the winner's decisive edge over our pick.\n"
    "  - category: a short snake_case failure category (e.g. "
    "suitability_underweighted, market_signal_missed, trainer_intent_missed, "
    "form_quality_overrated, draw_or_pace_missed, class_drop_missed, "
    "place_profile_promoted, beaten_by_better).\n"
    "  - proposed_tweak: a SINGLE concrete model adjustment naming which "
    "nap_selector_v3.py element to change — a scoring function "
    "(compute_form_score / compute_suitability_score / compute_context_score / "
    "compute_trainer_score / compute_market_score), a constant/weight, or a gate/"
    "filter/threshold — and the DIRECTION (raise/lower/add/veto). Give target, "
    "change (one actionable sentence) and rationale (why this loss justifies it).\n"
    "  - severity: LOW (likely just beaten by a better horse / variance), MEDIUM "
    "(a real but minor blind spot), HIGH (a systematic flaw worth fixing now).\n\n"
    "Be specific to THIS race. If the winner was simply superior and our process "
    "was sound, say so honestly with LOW severity and a minimal tweak. Output "
    "ONLY the structured JSON."
)

SEVERITY_LEVELS = ["LOW", "MEDIUM", "HIGH"]

AUTOPSY_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "category",
        "what_we_missed",
        "winner_edge",
        "proposed_tweak",
        "severity",
    ],
    "properties": {
        "category": {"type": "string"},
        "what_we_missed": {"type": "string"},
        "winner_edge": {"type": "string"},
        "proposed_tweak": {
            "type": "object",
            "additionalProperties": False,
            "required": ["target", "change", "rationale"],
            "properties": {
                "target": {"type": "string"},
                "change": {"type": "string"},
                "rationale": {"type": "string"},
            },
        },
        "severity": {"type": "string", "enum": SEVERITY_LEVELS},
    },
}


# ---------------------------------------------------------------------------
# Date resolution
# ---------------------------------------------------------------------------

def _resolve_date() -> str:
    """Pick the date to autopsy.

    Priority:
      1. Explicit YYYY-MM-DD passed as argv[1].
      2. Yesterday (results normally land for the prior day).
      3. today_str() fallback, used only if yesterday has no results but today
         does (same-day evening pipeline run).
    """
    # Explicit argument wins.
    for arg in sys.argv[1:]:
        arg = arg.strip()
        try:
            date.fromisoformat(arg)
            return arg
        except ValueError:
            continue

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    today = today_str()

    # Prefer the day that actually has a results file.
    if safe_load_json(data_path(f"results_{yesterday}.json")) is not None:
        return yesterday
    if safe_load_json(data_path(f"results_{today}.json")) is not None:
        return today
    # Neither exists — default to yesterday so the stub note is dated sensibly.
    return yesterday


# ---------------------------------------------------------------------------
# Winner lookup
# ---------------------------------------------------------------------------

def _find_winner_in_results(
    results_doc: dict,
    race_id: str,
    our_horse_name: str,
) -> Optional[dict]:
    """Find the actual winner's result row in the same race as our NAP.

    Scans official + shadow + watchlist result rows for a position==1 horse in
    *race_id* that is not our own horse. Returns the raw row or None.
    """
    our = (our_horse_name or "").strip().lower()
    for key in ("official_results", "shadow_results", "watchlist_results"):
        for row in results_doc.get(key) or []:
            if str(row.get("race_id") or "") != race_id:
                continue
            pos = row.get("position")
            try:
                pos_int = int(str(pos).strip().rstrip("stndrh"))
            except (TypeError, ValueError):
                pos_int = None
            won = bool(row.get("won")) or pos_int == 1
            name = str(row.get("horse") or "").strip()
            if won and name and name.lower() != our:
                return row
    return None


def _winner_from_shortlist(
    shortlist: Optional[dict],
    race_id: str,
    winner_name: Optional[str],
) -> dict:
    """Recover the winner's racecard form/price from the shortlist, if present.

    Matches by horse name within the winner's race. Returns a compact dict of
    whatever form context is available (possibly empty if no shortlist).
    """
    if not shortlist or not winner_name:
        return {}
    target = winner_name.strip().lower()
    for race in shortlist.get("races") or []:
        if race_id and str(race.get("race_id") or "") != race_id:
            continue
        for runner in race.get("runners") or []:
            if str(runner.get("horse") or "").strip().lower() == target:
                return {
                    "form_string": runner.get("form"),
                    "rpr": runner.get("rpr"),
                    "ts": runner.get("ts"),
                    "or": runner.get("ofr"),
                    "morning_price": runner.get("morning_price"),
                    "days_since_run": runner.get("last_run"),
                    "trainer_14d": runner.get("trainer_14_days") or {},
                    "headgear": runner.get("headgear"),
                }
    return {}


# ---------------------------------------------------------------------------
# Payload assembly
# ---------------------------------------------------------------------------

def _build_payload(
    nap_record: dict,
    nap_result: dict,
    winner_row: Optional[dict],
    winner_form: dict,
    enriched_row: Optional[dict],
) -> dict:
    """Assemble the our-pick-vs-winner JSON payload sent to the LLM."""
    # Winner price: prefer enriched winner_sp, else the winner result row, else
    # the recovered shortlist morning price.
    winner_sp = None
    if enriched_row is not None:
        winner_sp = enriched_row.get("winner_sp")
    if winner_sp is None and winner_row is not None:
        winner_sp = winner_row.get("sp_decimal")
    if winner_sp is None:
        winner_sp = winner_form.get("morning_price")

    winner_name = None
    if winner_row is not None:
        winner_name = winner_row.get("horse")
    if not winner_name and enriched_row is not None:
        winner_name = enriched_row.get("beaten_by_winner")

    return {
        "race_context": {
            "race_id": nap_result.get("race_id") or nap_record.get("race_id"),
            "course": nap_result.get("course") or nap_record.get("course"),
            "off_time": nap_result.get("off_time") or nap_record.get("off_time"),
            "grade": nap_result.get("grade") or nap_record.get("grade"),
        },
        "our_nap": {
            "horse": nap_record.get("horse") or nap_result.get("horse"),
            "score": nap_record.get("score") if nap_record.get("score") is not None
            else nap_result.get("score"),
            "grade": nap_record.get("grade") or nap_result.get("grade"),
            "sub_scores": {
                "form": nap_record.get("form_score"),
                "suitability": nap_record.get("suitability_score"),
                "context": nap_record.get("context_score"),
                "trainer": nap_record.get("trainer_score"),
                "market": nap_record.get("market_score"),
                "wisdom": nap_record.get("wisdom_score"),
                "draw": nap_record.get("draw_score"),
            },
            "form_string": nap_record.get("form"),
            "price": nap_record.get("sp_decimal") or nap_result.get("sp_decimal"),
            "key_reasons": (nap_record.get("reasons") or [])[:8],
            "warnings": nap_record.get("warnings") or [],
            "result": {
                "position": nap_result.get("position"),
                "beaten_lengths": nap_result.get("beaten_lengths"),
            },
        },
        "actual_winner": {
            "horse": winner_name,
            "finishing_detail": {
                "position": (winner_row or {}).get("position", 1),
                "beaten_lengths": (winner_row or {}).get("beaten_lengths"),
            },
            "price": winner_sp,
            "form": winner_form or None,
            "race_pace_indicator": (enriched_row or {}).get("race_pace_indicator"),
        },
    }


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def _stub_report(date_str: str, generated_hm: str, reason: str) -> str:
    sep = "=" * 56
    return "\n".join(
        [
            sep,
            "  LOSER AUTOPSY (AI)",
            f"  Date: {date_str}  |  Generated: {generated_hm}",
            sep,
            "",
            "  No autopsy performed.",
            f"  Reason: {reason}",
            "",
            sep,
        ]
    )


def _autopsy_report(
    date_str: str,
    generated_hm: str,
    payload: dict,
    autopsy: dict,
) -> str:
    sep = "=" * 56
    nap = payload.get("our_nap") or {}
    win = payload.get("actual_winner") or {}
    ctx = payload.get("race_context") or {}
    tweak = autopsy.get("proposed_tweak") or {}

    nap_price = nap.get("price")
    win_price = win.get("price")
    nap_price_str = format_odds(nap_price) if nap_price else "N/A"
    win_price_str = format_odds(win_price) if win_price else "N/A"
    res = nap.get("result") or {}
    bl = res.get("beaten_lengths")
    bl_str = f" (beaten {bl}L)" if bl is not None else ""

    lines = [
        sep,
        "  LOSER AUTOPSY (AI)",
        f"  Date: {date_str}  |  Generated: {generated_hm}",
        sep,
        "",
        f"  RACE: {ctx.get('course', '')} {ctx.get('off_time', '')}"
        f"  |  Grade: {ctx.get('grade', '')}",
        "",
        f"  OUR NAP : {str(nap.get('horse') or 'Unknown').upper()}  "
        f"(score {nap.get('score')}, {nap.get('grade', '')}, SP {nap_price_str})",
        f"            finished {res.get('position', 'N/R')}{bl_str}",
        f"  WINNER  : {str(win.get('horse') or 'Unknown').upper()}  "
        f"(SP {win_price_str})",
        "",
        f"  FAILURE CATEGORY : {str(autopsy.get('category', 'unknown')).upper()}",
        f"  SEVERITY         : {autopsy.get('severity', 'LOW')}",
        "",
        "  WHAT WE MISSED:",
        f"  {autopsy.get('what_we_missed', '')}",
        "",
        "  WINNER'S EDGE:",
        f"  {autopsy.get('winner_edge', '')}",
        "",
        "  PROPOSED MODEL TWEAK:",
        f"  Target   : {tweak.get('target', '')}",
        f"  Change   : {tweak.get('change', '')}",
        f"  Rationale: {tweak.get('rationale', '')}",
        "",
        sep,
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _save_report(date_str: str, text: str) -> int:
    """Write the text report. Returns 0 on success, 1 on write error."""
    dest = report_path(f"loser_autopsy_{date_str}.txt")
    try:
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(text)
        log(f"loser_autopsy_ai: text report saved -> {dest}")
        return 0
    except OSError as exc:
        log(f"loser_autopsy_ai: failed to write text report — {exc}", "ERROR")
        return 1


def _append_log(entry: dict) -> int:
    """Load-append-save the running autopsy log. Returns 0 / 1 (write error)."""
    dest = data_path(LOG_FILENAME)
    existing = safe_load_json(dest)
    if isinstance(existing, dict) and isinstance(existing.get("autopsies"), list):
        autopsies = existing["autopsies"]
    elif isinstance(existing, list):
        autopsies = existing
    else:
        autopsies = []

    autopsies.append(entry)

    doc = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(autopsies),
        "autopsies": autopsies,
    }
    if not safe_write_json(dest, doc):
        log(f"loser_autopsy_ai: failed to write log — {dest}", "ERROR")
        return 1
    log(f"loser_autopsy_ai: log updated -> {dest} ({len(autopsies)} entries)")
    return 0


def _write_stub(date_str: str, generated_hm: str, reason: str) -> int:
    """Write a stub note (text report only). Returns the report write code."""
    log(f"loser_autopsy_ai: {reason} — writing stub note", "INFO")
    return _save_report(date_str, _stub_report(date_str, generated_hm, reason))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    log("loser_autopsy_ai.py started")

    date_str = _resolve_date()
    now = datetime.now(timezone.utc)
    generated_hm = now.strftime("%H:%M")
    log(f"loser_autopsy_ai: date={date_str}")

    # ------------------------------------------------------------------
    # 1. Results must exist before we can autopsy anything.
    # ------------------------------------------------------------------
    results_doc = safe_load_json(data_path(f"results_{date_str}.json"))
    if results_doc is None:
        return _write_stub(
            date_str, generated_hm,
            "results not yet available — autopsy pending results",
        )

    # ------------------------------------------------------------------
    # 2. Locate the official NAP and its result (same logic as
    #    loser_diagnostics.py).
    # ------------------------------------------------------------------
    candidates_doc = safe_load_json(
        data_path(f"nap_candidates_{date_str}.json")
    ) or {}
    nap_candidate = candidates_doc.get("nap") or {}

    official_results = results_doc.get("official_results") or []
    nap_results = [
        r for r in official_results if r.get("candidate_type") == "nap"
    ]

    if not nap_results:
        return _write_stub(
            date_str, generated_hm,
            "no official NAP today — no autopsy needed",
        )

    if any(r.get("won") for r in nap_results):
        return _write_stub(
            date_str, generated_hm,
            "NAP WON — no autopsy needed",
        )

    # Take the first (there is normally exactly one) losing NAP.
    nap_result = nap_results[0]
    horse_id = str(nap_result.get("horse_id") or "")
    horse_name = str(nap_result.get("horse") or "")

    # Prefer the richer candidate record (carries sub-scores + reasons); fall
    # back to the result row if it does not match.
    if str(nap_candidate.get("horse_id") or "") == horse_id and horse_id:
        nap_record = nap_candidate
    else:
        nap_record = nap_result

    # ------------------------------------------------------------------
    # 3. Identify the actual winner + recover its form/price.
    # ------------------------------------------------------------------
    race_id = str(nap_result.get("race_id") or "")

    enriched_doc = safe_load_json(
        data_path(f"results_enriched_{date_str}.json")
    )
    enriched_row: Optional[dict] = None
    if enriched_doc:
        for r in enriched_doc.get("official_results") or []:
            if str(r.get("horse_id") or "") == horse_id and horse_id:
                enriched_row = r
                break
            if str(r.get("race_id") or "") == race_id and \
                    str(r.get("horse") or "").lower() == horse_name.lower():
                enriched_row = r
                break

    winner_row = _find_winner_in_results(results_doc, race_id, horse_name)
    winner_name = None
    if winner_row is not None:
        winner_name = str(winner_row.get("horse") or "")
    if not winner_name and enriched_row is not None:
        winner_name = enriched_row.get("beaten_by_winner")

    shortlist = safe_load_json(data_path(f"shortlist_{date_str}.json"))
    winner_form = _winner_from_shortlist(shortlist, race_id, winner_name)

    payload = _build_payload(
        nap_record, nap_result, winner_row, winner_form, enriched_row
    )

    # ------------------------------------------------------------------
    # 4. Degrade gracefully: no LLM => stub note, success.
    # ------------------------------------------------------------------
    client = get_llm_client()
    if client is None:
        return _write_stub(
            date_str, generated_hm,
            "LLM layer unavailable (no API key / SDK / network) — "
            "autopsy skipped; pipeline unaffected",
        )

    autopsy = client.call_structured(
        SYSTEM_PROMPT,
        payload,
        AUTOPSY_SCHEMA,
        max_tokens=MAX_TOKENS,
    )

    if autopsy is None:
        return _write_stub(
            date_str, generated_hm,
            "LLM returned no structured autopsy — pipeline unaffected",
        )

    autopsy["model"] = client.default_model

    # ------------------------------------------------------------------
    # 5. Write the readable report.
    # ------------------------------------------------------------------
    report_text = _autopsy_report(date_str, generated_hm, payload, autopsy)
    rc = _save_report(date_str, report_text)
    if rc != 0:
        return rc

    # ------------------------------------------------------------------
    # 6. Append to the running learning log.
    # ------------------------------------------------------------------
    log_entry = {
        "date": date_str,
        "logged_at": now.isoformat(),
        "race_id": race_id,
        "course": payload["race_context"].get("course"),
        "off_time": payload["race_context"].get("off_time"),
        "our_nap": payload["our_nap"].get("horse"),
        "our_score": payload["our_nap"].get("score"),
        "our_position": (payload["our_nap"].get("result") or {}).get("position"),
        "winner": payload["actual_winner"].get("horse"),
        "category": autopsy.get("category"),
        "severity": autopsy.get("severity"),
        "what_we_missed": autopsy.get("what_we_missed"),
        "winner_edge": autopsy.get("winner_edge"),
        "proposed_tweak": autopsy.get("proposed_tweak"),
        "model": autopsy.get("model"),
    }
    rc = _append_log(log_entry)
    if rc != 0:
        return rc

    summary = (
        f"loser_autopsy_ai: COMPLETE — {payload['our_nap'].get('horse')} lost to "
        f"{payload['actual_winner'].get('horse')}; "
        f"category={autopsy.get('category')} severity={autopsy.get('severity')} "
        f"tweak->{(autopsy.get('proposed_tweak') or {}).get('target')}"
    )
    log(summary)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
