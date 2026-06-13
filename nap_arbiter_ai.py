"""
nap_arbiter_ai.py — AI "Second-Opinion Arbiter" pipeline stage.

Runs AFTER nap_selector_v3. It asks an independent senior tipster (the shared
LLM layer) to pick THE nap of the day from the same pool of options the numeric
model considered, rank a top 3, and state whether it AGREES / PARTIALLY agrees
/ DISAGREES with the model's chosen NAP. It is a cheap blunder-catcher: when the
AI strongly disagrees, that is a signal for a human to take a second look — the
arbiter never overrides the quantitative model, it only flags.

Inputs:
    data/nap_candidates_YYYY-MM-DD.json  (from nap_selector_v3: nap, watchlist,
                                          no_bet_races, day_verdict, best_of_card,
                                          jump_nap, shadow, ...)
    data/shortlist_YYYY-MM-DD.json       (broader per-race context; optional)

Outputs:
    data/arbiter_YYYY-MM-DD.json   structured result + model_nap compared against + model id
    reports/arbiter_YYYY-MM-DD.txt human-readable second opinion

Structured schema (what the LLM returns):
    {
      "ai_nap": {"horse": str, "course": str, "off_time": str, "reason": str},
      "ai_top3": [{"horse": str, "reason": str}, ...],   # up to 3
      "agreement": "AGREE" | "PARTIAL" | "DISAGREE",
      "agreement_note": str,
      "confidence": int   # 0-100
    }

Degrades gracefully: if the LLM layer is unavailable (no API key / SDK / network)
OR nap_candidates is missing, write a minimal stub noting "arbiter unavailable"
and return 0. The existing pipeline is unaffected.

Exit codes:
    0  — success (INCLUDING every degraded case)
    1  — only on a write error

================================================================================
INTEGRATION — for the orchestrator to wire in. (Documentation only; do NOT
implement here, and these files are read-only for this component.)

1. daily_pipeline.py — insert ONE line into PIPELINE_STEPS, AFTER nap_selector_v3
   and BEFORE cluster_review:

       ("nap_selector_v3",        "nap_selector_v3.py",       []),
       ("nap_arbiter_ai",         "nap_arbiter_ai.py",        []),   # <-- ADD
       ("cluster_review",         "cluster_review.py",        []),

   The arbiter is non-gating: it always exits 0 (even degraded), so it can never
   block the downstream cluster_review / briefing / email steps.

2. morning_briefing_report.py — add an "■ AI SECOND OPINION" section (e.g. just
   after the "■ TODAY'S NAP" section). Load the arbiter file and surface the AI's
   independent pick + its agreement verdict, making DISAGREE visually prominent:

       from src.helpers import data_path, safe_load_json, today_str
       arb = safe_load_json(data_path(f"arbiter_{today_str()}.json")) or {}
       res = arb.get("result") or {}
       if res:
           lines.append(_section("AI SECOND OPINION"))
           agree = (res.get("agreement") or "UNKNOWN").upper()
           flag = "  ⚠⚠ DISAGREES WITH MODEL ⚠⚠" if agree == "DISAGREE" else ""
           ai = res.get("ai_nap") or {}
           lines.append(f"  AI NAP: {(ai.get('horse') or '?').upper()} "
                        f"— {ai.get('course','?')}, {ai.get('off_time','?')}")
           lines.append(f"  Agreement: {agree}{flag}  "
                        f"(confidence {res.get('confidence','?')}/100)")
           lines.append(f"  {res.get('agreement_note','')}")
           lines.append("")
       # When `arb`/`res` is empty (arbiter degraded), the section is simply
       # omitted — the briefing renders exactly as it does today.

   Presentation guidance: render AGREE in normal weight, PARTIAL as a soft
   caution, and DISAGREE with the prominent ⚠⚠ banner above so a human reviewer
   immediately sees the model and the independent tipster diverged.
================================================================================
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Optional

from src.helpers import (
    data_path,
    log,
    report_path,
    safe_load_json,
    safe_write_json,
    today_str,
)
from src.llm_client import get_llm_client, llm_available

# How many alternative candidates (beyond the model NAP) to present to the AI.
MAX_ALTERNATIVES: int = 12
# How many "key reasons" to include per candidate (keep the payload compact).
MAX_REASONS: int = 4
# Output token cap. The full schema (ai_nap + ai_top3×3 + agreement + note +
# confidence) in JSON is ~400-600 tokens; 2048 gives headroom for verbose notes.
MAX_TOKENS: int = 2048


# ---------------------------------------------------------------------------
# Frozen persona + schema
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a sharp, independent senior horse-racing tipster reviewing a UK "
    "card. You are given a quantitative model's chosen NAP (its single most "
    "confident bet of the day) plus a compact list of the strongest alternative "
    "runners across the card. Form your OWN opinion from scratch — do not defer "
    "to the model. Then:\n"
    " (a) Name THE nap of the day — the one horse you would bet — chosen ONLY "
    "from the options provided (the model NAP or one of the alternatives).\n"
    " (b) Rank your top 3 picks for the day.\n"
    " (c) State whether you AGREE, PARTIALLY agree, or DISAGREE with the model's "
    "NAP, and explain why in one or two sentences.\n"
    " (d) Give a confidence score 0-100 in your own NAP.\n"
    "Use AGREE when your NAP is the model's NAP. Use PARTIAL when you would keep "
    "the model's NAP on your shortlist but slightly prefer another, or have a "
    "notable reservation. Use DISAGREE when you would bet a different horse. Be "
    "concise, specific, and honest. Respond ONLY with the required JSON."
)

RESULT_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "ai_nap": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "horse": {"type": "string"},
                "course": {"type": "string"},
                "off_time": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["horse", "course", "off_time", "reason"],
        },
        "ai_top3": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "horse": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["horse", "reason"],
            },
        },
        "agreement": {"type": "string", "enum": ["AGREE", "PARTIAL", "DISAGREE"]},
        "agreement_note": {"type": "string"},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "required": ["ai_nap", "ai_top3", "agreement", "agreement_note", "confidence"],
}


# ---------------------------------------------------------------------------
# Payload construction
# ---------------------------------------------------------------------------

def _candidate_brief(c: dict) -> dict:
    """Compact view of a single candidate for the AI payload."""
    if not isinstance(c, dict):
        return {}
    reasons = c.get("reasons") or []
    if isinstance(reasons, list):
        key_reasons = [str(r) for r in reasons[:MAX_REASONS]]
    else:
        key_reasons = []
    return {
        "horse": c.get("horse"),
        "course": c.get("course"),
        "off_time": c.get("off_time"),
        "score": c.get("score"),
        "grade": c.get("grade"),
        "morning_price": c.get("morning_price"),
        "race_type": c.get("race_type"),
        "going": c.get("going"),
        "key_reasons": key_reasons,
    }


def _collect_alternatives(candidates: dict, nap: Optional[dict]) -> list[dict]:
    """Gather the strongest alternatives across the card (watchlist + tops).

    Pulls from best_of_card, jump_nap, watchlist and shadow, de-duplicating by
    (horse, course, off_time) and excluding the model's own NAP, then caps the
    list to MAX_ALTERNATIVES (strongest score first).
    """
    nap_key = None
    if isinstance(nap, dict):
        nap_key = (nap.get("horse"), nap.get("course"), nap.get("off_time"))

    pool: list[dict] = []
    best = candidates.get("best_of_card")
    if isinstance(best, dict):
        pool.append(best)
    jump = candidates.get("jump_nap")
    if isinstance(jump, dict):
        pool.append(jump)
    for key in ("watchlist", "shadow"):
        items = candidates.get(key) or []
        if isinstance(items, list):
            pool.extend(c for c in items if isinstance(c, dict))

    seen: set = set()
    alternatives: list[dict] = []
    for c in pool:
        key = (c.get("horse"), c.get("course"), c.get("off_time"))
        if nap_key is not None and key == nap_key:
            continue
        if key in seen:
            continue
        seen.add(key)
        alternatives.append(_candidate_brief(c))

    # Strongest first by numeric score; missing scores sink to the back.
    def _score_key(b: dict) -> float:
        try:
            return float(b.get("score"))
        except (TypeError, ValueError):
            return float("-inf")

    alternatives.sort(key=_score_key, reverse=True)
    return alternatives[:MAX_ALTERNATIVES]


def _build_payload(candidates: dict, shortlist: Optional[dict]) -> dict:
    """Assemble the JSON payload sent to the arbiter LLM."""
    nap = candidates.get("nap")
    model_nap_brief: Optional[dict] = (
        _candidate_brief(nap) if isinstance(nap, dict) else None
    )

    course_count = 0
    race_count = 0
    if isinstance(shortlist, dict):
        races = shortlist.get("races") or []
        if isinstance(races, list):
            race_count = len(races)
            course_count = len(
                {r.get("course") for r in races if isinstance(r, dict)}
            )

    return {
        "date": candidates.get("date"),
        "model_version": candidates.get("model_version"),
        "model_day_verdict": candidates.get("day_verdict"),
        "card_summary": {"races": race_count, "courses": course_count},
        "model_nap": model_nap_brief,
        "alternatives": _collect_alternatives(candidates, nap),
        "instruction": (
            "Pick your nap of the day from model_nap + alternatives only, rank "
            "your top 3, and judge whether you agree with model_nap."
        ),
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _format_report(date_str: str, generated_hm: str, record: dict) -> str:
    """Render a human-readable arbiter report."""
    sep = "═" * 60
    lines: list[str] = [
        sep,
        "  AI SECOND-OPINION ARBITER",
        f"  Date: {date_str}",
        f"  Generated: {generated_hm}  |  Model: {record.get('model') or 'n/a'}",
        sep,
        "",
    ]

    if record.get("status") != "ok" or not record.get("result"):
        lines.append("■ ARBITER UNAVAILABLE")
        lines.append(f"  {record.get('note') or 'No second opinion produced.'}")
        lines.append("")
        lines.append(sep)
        return "\n".join(lines) + "\n"

    res = record["result"]
    model_nap = record.get("model_nap") or {}
    agree = (res.get("agreement") or "UNKNOWN").upper()

    lines.append("■ MODEL NAP (numeric)")
    if model_nap:
        lines.append(
            f"  {str(model_nap.get('horse') or '?').upper()} "
            f"— {model_nap.get('course','?')}, {model_nap.get('off_time','?')}  "
            f"(score {model_nap.get('score','?')})"
        )
    else:
        lines.append("  None selected by the model.")
    lines.append("")

    ai = res.get("ai_nap") or {}
    lines.append("■ AI NAP (independent)")
    lines.append(
        f"  {str(ai.get('horse') or '?').upper()} "
        f"— {ai.get('course','?')}, {ai.get('off_time','?')}"
    )
    if ai.get("reason"):
        lines.append(f"  {ai['reason']}")
    lines.append("")

    lines.append("■ AGREEMENT")
    if agree == "DISAGREE":
        lines.append("  ⚠⚠ DISAGREES WITH MODEL ⚠⚠")
    lines.append(
        f"  Verdict: {agree}  |  Confidence: {res.get('confidence','?')}/100"
    )
    if res.get("agreement_note"):
        lines.append(f"  {res['agreement_note']}")
    lines.append("")

    top3 = res.get("ai_top3") or []
    lines.append("■ AI TOP 3")
    if top3:
        for i, pick in enumerate(top3, 1):
            if not isinstance(pick, dict):
                continue
            lines.append(f"  {i}. {str(pick.get('horse') or '?').upper()}")
            if pick.get("reason"):
                lines.append(f"     {pick['reason']}")
    else:
        lines.append("  None provided.")
    lines.append("")
    lines.append(sep)
    return "\n".join(lines) + "\n"


def _write_outputs(date_str: str, generated_hm: str, record: dict) -> int:
    """Write the JSON + text outputs. Returns 0 on success, 1 on write error."""
    json_dest = data_path(f"arbiter_{date_str}.json")
    if not safe_write_json(json_dest, record):
        log(f"nap_arbiter_ai: failed to write {json_dest}", "ERROR")
        return 1
    log(f"nap_arbiter_ai: result saved to {json_dest}")

    report_text = _format_report(date_str, generated_hm, record)
    report_dest = report_path(f"arbiter_{date_str}.txt")
    try:
        with open(report_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
    except OSError as exc:
        log(f"nap_arbiter_ai: failed to write {report_dest} — {exc}", "ERROR")
        return 1
    log(f"nap_arbiter_ai: report saved to {report_dest}")
    return 0


def _stub_record(date_str: str, note: str, model_nap: Optional[dict] = None) -> dict:
    """Build a minimal degraded-mode record."""
    return {
        "date": date_str,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "unavailable",
        "note": note,
        "model": None,
        "model_nap": model_nap,
        "result": None,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    log("nap_arbiter_ai.py started")
    date_str = today_str()
    generated_hm = datetime.now().strftime("%H:%M")

    # Degrade: no LLM layer => write stub, succeed.
    if not llm_available():
        log(
            "nap_arbiter_ai: LLM layer unavailable (no API key / SDK / network) "
            "— writing arbiter-unavailable stub; pipeline unaffected",
            "WARNING",
        )
        return _write_outputs(
            date_str,
            generated_hm,
            _stub_record(date_str, "arbiter unavailable — LLM layer disabled"),
        )

    # Degrade: no model candidates => nothing to arbitrate.
    candidates = safe_load_json(data_path(f"nap_candidates_{date_str}.json"))
    if not candidates:
        log("nap_arbiter_ai: nap_candidates unavailable — writing stub", "WARNING")
        return _write_outputs(
            date_str,
            generated_hm,
            _stub_record(date_str, "arbiter unavailable — no nap_candidates input"),
        )

    nap = candidates.get("nap") if isinstance(candidates, dict) else None
    model_nap_brief = _candidate_brief(nap) if isinstance(nap, dict) else None

    client = get_llm_client()
    if client is None:
        log("nap_arbiter_ai: get_llm_client returned None — writing stub", "WARNING")
        return _write_outputs(
            date_str,
            generated_hm,
            _stub_record(
                date_str,
                "arbiter unavailable — LLM client init failed",
                model_nap_brief,
            ),
        )

    shortlist = safe_load_json(data_path(f"shortlist_{date_str}.json"))
    payload = _build_payload(candidates, shortlist)

    result = client.call_structured(
        SYSTEM_PROMPT, payload, RESULT_SCHEMA, max_tokens=MAX_TOKENS
    )

    if result is None:
        log(
            "nap_arbiter_ai: no structured response from LLM — writing stub",
            "WARNING",
        )
        return _write_outputs(
            date_str,
            generated_hm,
            _stub_record(
                date_str,
                "arbiter unavailable — LLM returned no result",
                model_nap_brief,
            ),
        )

    record = {
        "date": date_str,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "note": "",
        "model": client.default_model,
        "model_nap": model_nap_brief,
        "result": result,
    }

    rc = _write_outputs(date_str, generated_hm, record)
    if rc == 0:
        agree = str((result.get("agreement") or "UNKNOWN")).upper()
        ai_nap = (result.get("ai_nap") or {}).get("horse") or "?"
        summary = (
            f"nap_arbiter_ai: SUCCESS — agreement={agree} "
            f"ai_nap={ai_nap} confidence={result.get('confidence','?')} "
            f"for {date_str}"
        )
        log(summary)
        print(summary)
    return rc


if __name__ == "__main__":
    sys.exit(main())
